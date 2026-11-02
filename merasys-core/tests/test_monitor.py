from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from monitor.alerts import deliver, evaluate
from monitor.collector import parse_inventory, record_result
from monitor.db import Base, ComposeService, Health, Incident, Outbox, Target, connect, heartbeat, initialize, now
from monitor.settings import Settings
from monitor.sheet import COMPOSE_HEADERS, FULL_HEADERS, HEADERS, NOTE_HEADERS, SERVICE_HEADERS, apply_rows, parse_rows


@pytest.fixture
def context(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    settings = Settings.load()
    engine, sessions = connect("sqlite:///" + str(tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    with sessions.begin() as s:
        for name in ("sheet", "alert-worker"):
            heartbeat(s, name)
        apply_rows(s, parse_rows([HEADERS, ["TRUE", "Dự án A, Dự án B", "192.168.1.239", "api", "Tuấn"]]))
    yield settings, sessions
    engine.dispose()


def check(context, inventory=None, count=1):
    settings, sessions = context
    for _ in range(count):
        with sessions.begin() as s:
            record_result(s, "192.168.1.239", inventory, "Docker error" if inventory is None else "")
        with sessions.begin() as s:
            evaluate(s, settings)


def active(sessions):
    with sessions() as s:
        return list(s.scalars(select(Incident).where(Incident.active.is_(True))))


def test_multiselect_and_duplicate_rows_merge():
    rows = parse_rows([HEADERS,
        ["TRUE", "A, B", "10.0.0.1", "api", "Tuấn"],
        ["TRUE", "B, C", "10.0.0.1", "api", "Nam"]])
    assert rows[("10.0.0.1", "api")]["projects"] == {"A", "B", "C"}


def test_invalid_sheet_rejected_atomically(context):
    _, sessions = context
    with pytest.raises(ValueError, match="Dòng 3"):
        parse_rows([HEADERS, ["FALSE", "A", "192.168.1.239", "api", ""], ["TRUE", "B", "not-ip", "api", ""]])
    with sessions() as s:
        assert s.scalar(select(Target).where(Target.container == "api")).enabled
    with pytest.raises(ValueError, match="Sheet rỗng"):
        parse_rows([HEADERS])


def test_bad_docker_output_is_not_empty_inventory():
    with pytest.raises((ValueError, TypeError)):
        parse_inventory('{"Names":"api"}')
    assert parse_inventory('') == {}
    assert parse_inventory('{"Names":"api","State":"running"}') == {"api": "running"}


def test_failure_counts_samples_not_worker_polls(context):
    settings, sessions = context
    check(context, inventory={"api": "exited"}, count=1)
    for _ in range(10):
        with sessions.begin() as s:
            evaluate(s, settings)
    assert not active(sessions)
    check(context, inventory={"api": "exited"}, count=2)
    incidents = active(sessions)
    assert len(incidents) == 1
    assert "Dự án A, Dự án B" in incidents[0].detail
    with sessions() as s:
        assert len(list(s.scalars(select(Outbox)))) == 1


def test_recovery_requires_two_samples(context):
    _, sessions = context
    check(context, inventory={}, count=3)
    check(context, inventory={"api": "running"})
    assert len(active(sessions)) == 1
    check(context, inventory={"api": "running"})
    assert not active(sessions)
    with sessions() as s:
        messages = list(s.scalars(select(Outbox).order_by(Outbox.id)))
        assert len(messages) == 2
        assert "Phục hồi" in messages[1].text


def test_unreachable_parent_suppresses_children_without_false_recovery(context):
    _, sessions = context
    check(context, inventory={}, count=3)
    with sessions.begin() as s:
        for t in s.scalars(select(Target)):
            t.checked_at = now() - timedelta(seconds=context[0].stale_after_seconds + 1)
        evaluate(s, context[0])
    incidents = active(sessions)
    assert len(incidents) == 2  # previous child incident stays open, plus server incident
    assert any(i.title == "Server mất heartbeat" for i in incidents)
    with sessions() as s:
        child = s.scalar(select(Target).where(Target.container == "api"))
        assert child.checked_at < now() - timedelta(seconds=context[0].stale_after_seconds)
        assert not any("Phục hồi" in t for t in s.scalars(select(Outbox.text)))


def test_docker_query_failure_and_recovery_even_if_container_down(context):
    _, sessions = context
    check(context, inventory=None, count=3)
    assert [i.title for i in active(sessions)] == ["Không đọc được Docker"]
    check(context, inventory={}, count=2)
    assert not any(i.title == "Không đọc được Docker" for i in active(sessions))


def test_agent_stale_without_new_inserts(context):
    settings, sessions = context
    with sessions.begin() as s:
        s.get(Health, "host:192.168.1.239").created_at = now() - timedelta(seconds=settings.stale_after_seconds + 10)
        evaluate(s, settings)
    assert [i.key for i in active(sessions)] == ["agent:192.168.1.239"]


def test_first_sheet_sync_never_succeeds_still_alerts(context):
    settings, sessions = context
    with sessions.begin() as s:
        h = s.get(Health, "sheet")
        h.last_ok_at = None
        h.created_at = now() - timedelta(seconds=settings.sheet_stale_after_seconds + 10)
        heartbeat(s, "sheet", "Access denied", success=False)
        evaluate(s, settings)
    assert any(i.key == "system:sheet" for i in active(sessions))


def test_disable_all_children_disables_derived_parent(context):
    settings, sessions = context
    check(context, inventory={}, count=3)
    with sessions.begin() as s:
        apply_rows(s, parse_rows([HEADERS, ["FALSE", "A, B", "192.168.1.239", "api", "Tuấn"]]))
    with sessions.begin() as s:
        assert not any(t.enabled for t in s.scalars(select(Target)))
        evaluate(s, settings)
    assert not active(sessions)
    with sessions() as s:
        assert "Ngừng giám sát" in list(s.scalars(select(Outbox.text)))[-1]


def test_missing_rows_retained(context):
    _, sessions = context
    with sessions.begin() as s:
        apply_rows(s, parse_rows([HEADERS, ["TRUE", "C", "10.0.0.2", "worker", "Nam"]]))
    with sessions() as s:
        assert s.scalar(select(Target).where(Target.container == "api")).enabled


def test_telegram_retry_and_rate_limit(context, monkeypatch):
    settings, sessions = context
    settings = replace(settings, telegram_bot_token="secret", telegram_chat_id="123")
    with sessions.begin() as s:
        s.add(Outbox(incident_key="test", text="hello"))
    post = Mock(return_value=Mock(status_code=429, json=lambda: {"parameters": {"retry_after": 30}}))
    monkeypatch.setattr("monitor.alerts.requests.post", post)
    deliver(settings, sessions)
    with sessions() as s:
        msg = s.scalar(select(Outbox))
        assert msg.sent_at is None
        assert msg.next_attempt_at > now()
        assert msg.attempts == 1
    deliver(settings, sessions)
    assert post.call_count == 1


def test_telegram_errors_do_not_leak_token(context, monkeypatch):
    settings, sessions = context
    settings = replace(settings, telegram_bot_token="MY_SECRET", telegram_chat_id="123")
    with sessions.begin() as s:
        s.add(Outbox(incident_key="test", text="hello"))
    monkeypatch.setattr("monitor.alerts.requests.post", Mock(side_effect=RuntimeError("https://MY_SECRET")))
    deliver(settings, sessions)
    with sessions() as s:
        assert "MY_SECRET" not in s.scalar(select(Outbox)).last_error


def test_dashboard_auth_and_stale_status(context):
    from fastapi.testclient import TestClient
    from monitor.web import create_app
    settings, sessions = context
    settings = replace(settings, dashboard_token="a-long-dashboard-token-123")
    check(context, inventory={"api": "running"}, count=2)
    with sessions.begin() as s:
        for target in s.scalars(select(Target)):
            target.checked_at = now() - timedelta(seconds=settings.stale_after_seconds + 1)
    with TestClient(create_app(settings, sessions)) as client:
        assert client.get("/").status_code == 401
        assert client.get("/healthz").status_code == 200
        auth = ("admin", settings.dashboard_token)
        response = client.get("/api/status", auth=auth)
        assert response.status_code == 200
        assert all(t["status"] == "UNKNOWN" for t in response.json()["targets"])
        assert "Dự án A" in client.get("/", auth=auth).text


def compose_inventory(*entries):
    import json
    return parse_inventory("\n".join(json.dumps({"Names": name, "State": state,
        "Labels": f"com.docker.compose.project={project},com.docker.compose.service={service},com.docker.compose.oneoff={oneoff}"})
        for name, state, project, service, oneoff in entries))


def add_compose(context):
    _, sessions = context
    with sessions.begin() as s:
        apply_rows(s, parse_rows([COMPOSE_HEADERS, ["TRUE", "A, B", "192.168.1.239", "", "customer-stack", "Nam"]]))


def test_compose_sheet_accepts_old_and_new_format():
    rows = parse_rows([COMPOSE_HEADERS, ["TRUE", "A, B", "10.0.0.1", "", "customer-stack", "Nam"]])
    assert rows[("10.0.0.1", "compose:customer-stack")]["projects"] == {"A", "B"}
    with pytest.raises(ValueError, match="chỉ điền"):
        parse_rows([COMPOSE_HEADERS, ["TRUE", "A", "10.0.0.1", "api", "stack", "Nam"]])


def test_compose_discovers_services_and_all_replicas(context):
    _, sessions = context
    add_compose(context)
    inventory = compose_inventory(
        ("stack-web-1", "running", "customer-stack", "web", "False"),
        ("stack-web-2", "exited", "customer-stack", "web", "False"),
        ("stack-db-1", "running", "customer-stack", "db", "False"),
        ("other-api", "exited", "other-stack", "api", "False"),
        ("stack-job", "exited", "customer-stack", "migrate", "True"))
    check(context, inventory=inventory, count=3)
    with sessions() as s:
        target = s.scalar(select(Target).where(Target.container == "compose:customer-stack"))
        services = list(s.scalars(select(ComposeService).where(ComposeService.target_id == target.id)))
        assert {x.name: x.status for x in services} == {"web": "DOWN", "db": "UP"}
        assert target.status == "DOWN"
        assert "stack-web-2=exited" in target.reason
        compose_alerts = [i for i in s.scalars(select(Incident)) if "Compose" in i.title]
        assert len(compose_alerts) == 1
        assert "A, B" in compose_alerts[0].detail


def test_compose_missing_service_is_remembered(context):
    _, sessions = context
    add_compose(context)
    check(context, inventory=compose_inventory(("old-api-1", "running", "customer-stack", "api", "False")), count=2)
    # All containers deleted: previously known service must not disappear from monitoring.
    check(context, inventory=compose_inventory(), count=3)
    with sessions() as s:
        target = s.scalar(select(Target).where(Target.container == "compose:customer-stack"))
        assert target.status == "DOWN"
        assert "hiện không có container" in target.reason
        assert any(i.title == "Compose có service DOWN" for i in active(sessions))
    # Redeploy changes container names, but service identity remains the same.
    check(context, inventory=compose_inventory(("new-api-1", "running", "customer-stack", "api", "False")), count=2)
    assert not any(i.title == "Compose có service DOWN" for i in active(sessions))


def test_compose_not_found_first_scan_is_down(context):
    _, sessions = context
    add_compose(context)
    check(context, inventory=compose_inventory(), count=3)
    assert any(i.title == "Compose có service DOWN" for i in active(sessions))


def test_compose_without_agent_stays_unknown(context):
    _, sessions = context
    add_compose(context)
    with sessions.begin() as s:
        evaluate(s, context[0])
    with sessions() as s:
        target = s.scalar(select(Target).where(Target.container == "compose:customer-stack"))
        assert target.status == "UNKNOWN"
    assert not any(i.title == "Compose có service DOWN" for i in active(sessions))


def test_compose_new_service_discovered_after_initial_scan(context):
    _, sessions = context
    add_compose(context)
    check(context, inventory=compose_inventory(("api-1", "running", "customer-stack", "api", "False")))
    check(context, inventory=compose_inventory(("api-2", "running", "customer-stack", "api", "False"),
                                            ("worker-1", "running", "customer-stack", "worker", "False")))
    with sessions() as s:
        assert {m.name for m in s.scalars(select(ComposeService))} == {"api", "worker"}


def test_note_sync_and_telegram(context):
    _, sessions = context
    with sessions.begin() as s:
        apply_rows(s, parse_rows([FULL_HEADERS, ["TRUE", "A", "192.168.1.239", "", "customer-stack", "Nam", "Liên hệ Nam trước khi restart"]]))
    check(context, inventory=compose_inventory(), count=3)
    with sessions() as s:
        target = s.scalar(select(Target).where(Target.container == "compose:customer-stack"))
        assert target.note == "Liên hệ Nam trước khi restart"
        assert any("Note: Liên hệ Nam trước khi restart" in m for m in s.scalars(select(Outbox.text)))
    rows = parse_rows([NOTE_HEADERS, ["TRUE", "A", "10.0.0.1", "api", "Nam", "Container note"]])
    assert rows[("10.0.0.1", "api")]["notes"] == {"Container note"}


def test_note_database_upgrade_preserves_existing_rows(tmp_path):
    from sqlalchemy import inspect, text
    engine, sessions = connect("sqlite:///" + str(tmp_path / "upgrade.db"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE targets DROP COLUMN note"))
        connection.execute(text("INSERT INTO targets (host, container, projects, owners, declared_projects, declared_owners, enabled, configured_enabled, status, reason, failures, successes, query_failures, query_successes) VALUES ('10.0.0.1', 'api', '[]', '[]', '[]', '[]', 1, 1, 'UP', '', 0, 2, 0, 2)"))
    initialize(engine)
    initialize(engine)  # upgrade is idempotent
    assert "note" in {c["name"] for c in inspect(engine).get_columns("targets")}
    with sessions() as s:
        target = s.scalar(select(Target))
        assert target.host == "10.0.0.1" and target.note == "" and target.status == "UP"
    engine.dispose()


def test_blank_project_can_monitor_server():
    rows = parse_rows([HEADERS, ["TRUE", "", "10.0.0.1", "", "Nam"]])
    assert rows[("10.0.0.1", "")]["projects"] == set()


def test_agent_api_auth_host_and_inventory(context, tmp_path):
    import json
    from fastapi.testclient import TestClient
    from monitor.web import create_app
    settings, sessions = context
    token = "a" * 64
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps({"192.168.1.239": token, "10.0.0.99": token}), encoding="utf-8")
    settings = replace(settings, agent_tokens_file=str(tokens), dashboard_token="dashboard-token-more-than-20")
    body = {"host": "192.168.1.239", "docker_output": '{"Names":"api","State":"running"}'}
    with TestClient(create_app(settings, sessions)) as client:
        assert client.post("/api/agent/report", json=body).status_code == 401
        headers = {"Authorization": "Bearer " + token}
        assert client.post("/api/agent/report", json={**body, "host": "10.0.0.99"}, headers=headers).status_code == 409
        assert client.post("/api/agent/report", json={**body, "docker_output": "invalid"}, headers=headers).status_code == 422
        assert client.post("/api/agent/report", json=body, headers=headers).status_code == 200
    with sessions() as s:
        parent = s.scalar(select(Target).where(Target.container == ""))
        assert parent.status == "UP" and "heartbeat" in parent.reason
        assert s.scalar(select(Target).where(Target.container == "api")).status == "UP"


def test_agent_stale_host_does_not_require_collector_heartbeat(context):
    settings, sessions = context
    with sessions.begin() as s:
        record_result(s, "192.168.1.239", parse_inventory('{"Names":"api","State":"running"}'), "")
        for t in s.scalars(select(Target)):
            t.checked_at = now() - timedelta(seconds=settings.stale_after_seconds + 10)
        evaluate(s, settings)
    assert [i.key for i in active(sessions)] == ["agent:192.168.1.239"]
    with sessions.begin() as s:
        record_result(s, "192.168.1.239", {}, "")
        evaluate(s, settings)
    assert any(i.key.startswith("agent:") for i in active(sessions))
    with sessions.begin() as s:
        record_result(s, "192.168.1.239", {}, "")
        evaluate(s, settings)
    # Require two fresh samples after the outage, not one old and one new sample.
    assert not any(i.key.startswith("agent:") for i in active(sessions))


def test_agent_no_first_report_gets_grace_then_alert(context):
    settings, sessions = context
    with sessions.begin() as s:
        evaluate(s, settings)
    assert not active(sessions)
    with sessions.begin() as s:
        s.get(Health, "host:192.168.1.239").created_at = now() - timedelta(seconds=settings.stale_after_seconds + 1)
        evaluate(s, settings)
    assert [i.key for i in active(sessions)] == ["agent:192.168.1.239"]


def test_agent_script_sends_heartbeat_when_docker_fails(monkeypatch):
    import importlib.util
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "merasys-agent" / "monitor-agent.py"
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "merasys-agent" / "monitor-agent.py"
    spec = importlib.util.spec_from_file_location("standalone_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.subprocess, "run", Mock(side_effect=FileNotFoundError))
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.status = 200
    response.read.return_value = b'{"ok": true}'
    post = Mock(return_value=response)
    monkeypatch.setattr(module, "urlopen", post)
    module.run_once({"host": "10.0.0.1", "token": "a" * 64, "url": "https://monitor.example.com"})
    payload = json.loads(post.call_args.args[0].data)
    assert payload == {"host": "10.0.0.1", "docker_output": None, "services": None}


def test_new_sheet_order_keeps_compose_owner_and_note_separate():
    assert FULL_HEADERS == ["Bật giám sát", "Dự án", "IP server", "Tên container", "Tên compose", "Người phụ trách", "Note"]
    rows = parse_rows([FULL_HEADERS,
        ["TRUE", "A, B", "10.0.0.1", "", "customer-stack", "Tuấn", "Ghi chú Compose"],
        ["TRUE", "", "10.0.0.2", "api", "", "Nam", "Ghi chú container"]])
    compose = rows[("10.0.0.1", "compose:customer-stack")]
    assert compose["owners"] == {"Tuấn"}
    assert compose["notes"] == {"Ghi chú Compose"}
    container = rows[("10.0.0.2", "api")]
    assert container["owners"] == {"Nam"}
    assert container["notes"] == {"Ghi chú container"}


def test_agent_reads_environment_and_validates_without_sending(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "merasys-agent" / "monitor-agent.py"
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "merasys-agent" / "monitor-agent.py"
    spec = importlib.util.spec_from_file_location("env_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key, value in {"MONITOR_URL": "https://monitor.example.com", "SERVER_IP": "10.0.0.1",
                       "AGENT_TOKEN": "a" * 64, "REPORT_INTERVAL_SECONDS": "45", "ALLOW_HTTP": "false"}.items():
        monkeypatch.setenv(key, value)
    assert module.load_config() == {"url": "https://monitor.example.com", "host": "10.0.0.1", "token": "a" * 64,
                                    "interval_seconds": 45, "allow_http": False}
    monkeypatch.setattr("sys.argv", ["monitor-agent.py", "--validate-only"])
    send = Mock()
    monkeypatch.setattr(module, "run_once", send)
    module.main()
    send.assert_not_called()


def test_sheet_system_service_and_conflicting_types():
    row = ["TRUE", "", "10.0.0.1", "", "", "Nam", "Web host", "nginx"]
    parsed = parse_rows([SERVICE_HEADERS, row])
    assert parsed[("10.0.0.1", "systemd:nginx.service")]["owners"] == {"Nam"}
    with pytest.raises(ValueError, match="chỉ điền một"):
        parse_rows([SERVICE_HEADERS, ["TRUE", "A", "10.0.0.1", "api", "", "Nam", "", "nginx"]])
    with pytest.raises(ValueError, match="không hợp lệ"):
        parse_rows([SERVICE_HEADERS, ["TRUE", "A", "10.0.0.1", "", "", "Nam", "", "nginx;reboot"]])


def test_system_service_without_docker_and_query_failure(context):
    settings, sessions = context
    with sessions.begin() as s:
        apply_rows(s, parse_rows([SERVICE_HEADERS,
            ["FALSE", "A", "192.168.1.239", "api", "", "Nam", "", ""],
            ["TRUE", "A", "192.168.1.239", "", "", "Nam", "", "nginx.service"]]))
    def report(services):
        with sessions.begin() as s:
            record_result(s, "192.168.1.239", None, services=services)
            evaluate(s, settings)
    for _ in range(3):
        report({"nginx.service": "failed"})
    assert [i.title for i in active(sessions)] == ["System service bị DOWN"]
    for _ in range(3):
        report(None)
    assert {i.title for i in active(sessions)} == {"System service bị DOWN", "Không đọc được systemd"}
    for _ in range(2):
        report({"nginx.service": "active"})
    assert not active(sessions)


def test_native_agent_parses_systemctl_states(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "merasys-agent" / "monitor-agent.py"
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "merasys-agent" / "monitor-agent.py"
    spec = importlib.util.spec_from_file_location("native_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = Mock(return_value=Mock(stdout=b"nginx.service loaded active running Web server\nworker.service loaded failed failed Worker\n"))
    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.read_services() == {"nginx.service": "active", "worker.service": "failed"}
    assert run.call_args.args[0][0] == "systemctl"
    run.return_value.stdout = b"unexpected format\n"
    with pytest.raises(ValueError):
        module.read_services()
