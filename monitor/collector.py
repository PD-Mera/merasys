import json
import logging
import time
from datetime import timedelta

from sqlalchemy import select

from .db import ComposeService, Sample, Target, heartbeat, now
from .sheet import sync_sheet

log = logging.getLogger(__name__)


class Inventory(dict):
    """Container states plus Compose membership obtained from canonical labels."""

    def __init__(self):
        super().__init__()
        self.compose = {}


def parse_inventory(output):
    result = Inventory()
    for line in output.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("Names"), str) or not isinstance(row.get("State"), str):
            raise ValueError("Docker inventory thiếu Names/State")
        result[row["Names"]] = row["State"]
        raw_labels = row.get("Labels", "")
        if not isinstance(raw_labels, str):
            raise ValueError("Docker inventory Labels không hợp lệ")
        labels = dict(part.split("=", 1) for part in raw_labels.split(",") if "=" in part)
        project = labels.get("com.docker.compose.project")
        service = labels.get("com.docker.compose.service")
        if project and service and labels.get("com.docker.compose.oneoff", "false").lower() != "true":
            result.compose.setdefault(project, {}).setdefault(service, []).append({"name": row["Names"], "state": row["State"]})
    return result


def compose_result(session, target, inventory, stamp):
    project = target.container.removeprefix("compose:")
    discovered = getattr(inventory, "compose", {}).get(project, {})
    known = {s.name: s for s in session.scalars(select(ComposeService).where(ComposeService.target_id == target.id))}
    details, failed = [], False
    # Remember service identity across redeploys, without binding to container IDs/names.
    for name in sorted(set(known) | set(discovered)):
        service = known.get(name)
        if service is None:
            service = ComposeService(target_id=target.id, name=name)
            session.add(service)
        containers = discovered.get(name, [])
        good = bool(containers) and all(c["state"] == "running" for c in containers)
        service.status = "UP" if good else "DOWN"
        service.reason = ", ".join(f'{c["name"]}={c["state"]}' for c in containers) or "Service đã từng phát hiện nhưng hiện không có container"
        service.containers, service.checked_at = containers, stamp
        details.append(f"{name}: {service.status} ({service.reason})")
        failed |= not good
    if not details:
        return "DOWN", f"Compose {project}: không tìm thấy service/container (không tính one-off job)"
    return ("DOWN" if failed else "UP"), f"Compose {project}\n" + "\n".join(details)


def record_result(session, host, inventory, reason="", max_gap_seconds=180, services=None, failure_threshold=3, recovery_threshold=2):
    stamp = now()
    targets = list(session.scalars(select(Target).where(Target.host == host, Target.enabled.is_(True)).order_by(Target.id).with_for_update()))
    for target in targets:
        if target.container and not target.container.startswith(("compose:", "systemd:")):
            continue  # Standalone container monitoring has been retired.
        if target.checked_at and stamp - target.checked_at >= timedelta(seconds=max_gap_seconds):
            # Fresh samples after an outage must build new consecutive counters.
            target.failures = target.successes = target.query_failures = target.query_successes = 0
        if not target.container:
            status, detail = "UP", "Agent gửi heartbeat thành công"
        elif target.container.startswith("systemd:"):
            name = target.container.removeprefix("systemd:")
            if services is None:
                status, detail = "UNKNOWN", "Agent không đọc được trạng thái systemd"
            else:
                state = services.get(name)
                status = "UP" if state == "active" else "DOWN"
                detail = f"Systemd {name}: {state}" if state else f"Systemd {name}: không nằm trong danh sách unit đã load"
        elif inventory is None:
            status, detail = "UNKNOWN", reason
        elif target.container.startswith("compose:"):
            status, detail = compose_result(session, target, inventory, stamp)
        target.status, target.reason, target.checked_at = status, detail, stamp
        target.failures = target.failures + 1 if status == "DOWN" else 0
        target.successes = target.successes + 1 if status == "UP" else 0
        query_ok = services is not None if target.container.startswith("systemd:") else inventory is not None
        target.query_failures = target.query_failures + 1 if not query_ok else 0
        target.query_successes = target.query_successes + 1 if query_ok else 0
        session.add(Sample(target_id=target.id, checked_at=stamp, status=status, reason=detail))
        from .availability import observe
        observe(session, target, stamp, failure_threshold, recovery_threshold, max_gap_seconds)
    heartbeat(session, f"host:{host}")


def run(settings, sessions):
    """Periodically import configuration; observations arrive only through agents."""
    while True:
        if not settings.sheet_ready:
            time.sleep(5)
            continue
        try:
            sync_sheet(settings, sessions)
            log.info("Sheet sync completed")
        except Exception as exc:
            log.error("Sheet sync failed: %s", type(exc).__name__)
            detail = str(exc)[:3000] if isinstance(exc, ValueError) else f"Lỗi đồng bộ Sheet ({type(exc).__name__}); kiểm tra quyền/cấu hình/mạng"
            try:
                with sessions.begin() as session:
                    heartbeat(session, "sheet", detail, success=False)
            except Exception:
                log.error("Cannot save Sheet sync error to DB")
        settings.wait(settings.sheet_sync_seconds)
