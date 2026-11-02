import logging
import json
import re
import time
from datetime import timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .db import AvailabilityCursor, Health, Incident, Outbox, Target, TelegramUser, heartbeat, now

log = logging.getLogger(__name__)


def shortened(value, limit):
    value = str(value).strip()
    return value if len(value) <= limit else value[:limit - 1] + "…"


def render_owners(value, telegram_users):
    """Render validated ID links or plain @username mentions, never Sheet HTML."""
    owners = list(dict.fromkeys(name.strip() for name in value.split(",") if name.strip()))
    rendered, used = [], 0
    for index, owner in enumerate(owners):
        label = shortened(owner, 200)
        identity = str(telegram_users.get(owner.casefold(), ""))
        username = identity if re.fullmatch(r"@[a-zA-Z0-9_]{1,32}", identity) else ""
        if username:
            label = f"{label} ({username})"
        # Keep the complete message within Telegram's text limit, closing every tag.
        if used + len(label) + 2 > 1200:
            rendered.append(f"… (+{len(owners) - index} người; xem Sheet)")
            break
        used += len(label) + 2
        user_id = identity
        if re.fullmatch(r"[1-9][0-9]{0,15}", user_id) and int(user_id) <= 2 ** 52 - 1:
            rendered.append(f'<a href="tg://user?id={user_id}">{escape(label)}</a>')
        else:
            rendered.append(escape(label))
    return ", ".join(rendered) or "Chưa khai báo"


def telegram_message(message, telegram_users=None):
    """Render legacy/new plain outbox messages into bounded, escaped Telegram HTML."""
    lines = message.splitlines()
    if not lines:
        return "<b>Thông báo giám sát</b>"
    recovery = lines[0].startswith(("🟢", "ℹ️"))
    fields, body, when = [], [], ""
    in_result = False
    for line in lines[1:]:
        if line.startswith("Thời điểm: "):
            when = line.removeprefix("Thời điểm: ")
            continue
        if line.startswith("Thời gian sự cố: "):
            fields.append(("Thời gian sự cố", shortened(line.removeprefix("Thời gian sự cố: "), 60)))
            continue
        if line in {"Sự cố trước đó:", ""}:
            continue
        if line.startswith("Kết quả: "):
            in_result = True
            body.append(line.removeprefix("Kết quả: "))
            continue
        if not in_result and any(line.startswith(label + ": ") for label in ("Server", "Compose project", "Container", "System service", "Dự án", "Phụ trách", "Note", "Thời gian sự cố", "Queue", "Connection", "Vhost", "Username", "Ổ đĩa")):
            label, value = line.split(": ", 1)
            if not any(existing_label == label for existing_label, _ in fields):
                fields.append((label, value if label == "Phụ trách" else shortened(value, 160 if label != "Note" else 120)))
        else:
            body.append(line)
    heading = lines[0]
    if heading.startswith("🟢"):
        for old, new in {
            "Compose có service DOWN": "Compose đã phục hồi",
            "Container bị DOWN": "Container đã phục hồi",
            "System service bị DOWN": "System service đã phục hồi",
            "Server mất heartbeat": "Server đã kết nối lại",
            "Không đọc được Docker": "Đã đọc được Docker",
            "Không đọc được systemd": "Đã đọc được systemd",
            "Google Sheet không đồng bộ": "Google Sheet đã đồng bộ",
            "Queue RabbitMQ bị DOWN": "Queue RabbitMQ đã phục hồi",
            "Không kiểm tra được queue RabbitMQ": "Đã kiểm tra được queue RabbitMQ",
            "Ổ đĩa sắp hết dung lượng": "Ổ đĩa đã đủ dung lượng trống",
            "Không đọc được dung lượng ổ đĩa": "Đã đọc được dung lượng ổ đĩa",
        }.items():
            heading = heading.replace(old, new)
    result = [f"<b>{escape(shortened(heading, 140))}</b>", ""]
    for label, value in fields[:8]:
        display_label = {"Compose project": "Compose", "System service": "Service", "Note": "Ghi chú"}.get(label, label)
        rendered = f"<code>{escape(value)}</code>" if label in {"Server", "Compose project", "Container", "System service"} else escape(value)
        if label == "Phụ trách":
            rendered = render_owners(value, telegram_users or {})
        result.append(f"<b>{display_label}:</b> {rendered}")
    if recovery:
        # Do not repeat the previous DOWN inventory in a recovery notification.
        result.extend(["", "Đã ngừng giám sát đối tượng này." if lines[0].startswith("ℹ️") else "Điều kiện cảnh báo đã hết."])
    else:
        members = []
        for line in body:
            match = re.fullmatch(r"(.+?): (UP|DOWN|UNKNOWN) \((.*)\)", line)
            if match:
                members.append(match.groups())
        if members:
            failed = [m for m in members if m[1] != "UP"]
            result.extend(["", f"<b>Dịch vụ lỗi: {len(failed)}/{len(members)}</b>"])
            for name, status, detail in failed[:6]:
                containers = detail.split(", ")
                states = [c.rsplit("=", 1)[-1] for c in containers if "=" in c]
                bad_states = sorted({s for s in states if s != "running"})
                description = ", ".join(bad_states) if bad_states else ("không có container" if not states else status)
                if len(states) > 1:
                    description = f"{sum(s != 'running' for s in states)}/{len(states)} container lỗi · {description}"
                result.append(f"• <code>{escape(shortened(name, 100))}</code> — {escape(shortened(description, 100))}")
            if len(failed) > 6:
                result.append(f"… và {len(failed) - 6} service khác. Xem dashboard để biết chi tiết.")
        else:
            detail = "\n".join(line for line in body if line and line != "Agent gửi heartbeat thành công")
            if detail:
                result.extend(["", escape(shortened(detail, 600))])
    if when:
        result.extend(["", f"<i>{escape(shortened(when, 60))}</i>"])
    # Every tag is closed before delivery; never truncate the rendered HTML.
    return "\n".join(result)


def test_telegram_message(message, telegram_users):
    payload = json.loads(message)
    return (
        "🧪 <b>THỬ NGHIỆM CẢNH BÁO</b>\n\n"
        + f"<b>{escape(payload['title'])}</b>\n"
        + escape(payload["message"])
        + ("\n\n<b>Phụ trách:</b> " + render_owners(", ".join(payload["owners"]), telegram_users) if payload["owners"] else "")
        + "\n\n<i>Tin thử từ dashboard; không thay đổi trạng thái giám sát.</i>"
    )


def target_detail(target):
    rabbitmq = target.rabbitmq or {}
    return (
        f"Server: {target.host}\n"
        + (f"Queue: {rabbitmq.get('queue', '')}\nConnection: {rabbitmq.get('connection', '')}\nVhost: {rabbitmq.get('vhost', '')}\n" if target.container.startswith("rabbitmq:") else (f"System service: {target.container[8:]}\n" if target.container.startswith("systemd:") else (f"Compose project: {target.container[8:]}\n" if target.container.startswith("compose:") else (f"Container: {target.container}\n" if target.container else ""))))
        + f"Dự án: {', '.join(target.projects) or 'Chưa khai báo'}\n"
        + f"Phụ trách: {', '.join(target.owners) or 'Chưa khai báo'}\n"
        + (f"Note: {target.note}\n" if target.note else "")
        + f"Kết quả: {target.reason}"
    )


def notification_is_monitored(session, key, settings=None):
    """Recheck current configuration before sending even an old queued message."""
    category, separator, identity = key.partition(":")
    if not separator:
        return True
    if category == "system" and identity == "sheet" and settings is not None:
        return settings.sheet_ready
    if category == "disk":
        target_id, _, path = identity.partition(":")
        target = session.get(Target, int(target_id)) if target_id.isdecimal() else None
        return bool(target and target.enabled and target.configured_enabled and not target.container and
                    any(disk["path"] == path for disk in (target.server_config or {}).get("disks", [])))
    if category in {"target", "stale"}:
        if not identity.isdecimal():
            return True
        target = session.get(Target, int(identity))
        return target is not None and target.enabled and (not target.container or target.container.startswith(("compose:", "systemd:", "rabbitmq:")))
    if category in {"agent", "docker", "systemd"}:
        query = select(Target.id).where(Target.host == identity, Target.enabled.is_(True))
        if category == "agent":
            query = query.where(Target.container == "")
        elif category == "systemd":
            query = query.where(Target.container.startswith("systemd:"))
        else:
            query = query.where(Target.container != "", ~Target.container.startswith("systemd:"))
        return session.scalar(query.limit(1)) is not None
    return True  # Global monitoring-system alerts are independent of a Sheet row.


def evaluate(session, settings):
    stamp = now()
    from .availability import expire_all
    expire_all(session, stamp, settings.stale_after_seconds)
    problems, pending = {}, set()
    targets = list(session.scalars(select(Target)))
    active_targets = [t for t in targets if t.enabled and (not t.container or t.container.startswith(("compose:", "systemd:", "rabbitmq:")))]
    parents = {t.host: t for t in active_targets if not t.container}
    health = {h.name: h for h in session.scalars(select(Health))}
    stale = timedelta(seconds=settings.stale_after_seconds)
    agent_stale_hosts = set()
    for host, parent in parents.items():
        key = f"agent:{host}"
        host_health = health.get(f"host:{host}")
        reference = parent.checked_at or (host_health.created_at if host_health else stamp)
        if stamp - reference > stale:
            agent_stale_hosts.add(host)
            problems[key] = ("Server mất heartbeat", target_detail(parent) + "\nKhông nhận dữ liệu agent đúng hạn; có thể do server, agent hoặc đường truyền/API lỗi.")
        elif not parent.checked_at or parent.successes < settings.recovery_threshold:
            pending.add(key)
    sheet = health.get("sheet")
    sheet_reference = (sheet.last_ok_at or sheet.created_at) if sheet else stamp
    if settings.sheet_ready and stamp - sheet_reference > timedelta(seconds=settings.sheet_stale_after_seconds):
        problems["system:sheet"] = ("Google Sheet không đồng bộ", sheet.error or "Không có lần đồng bộ thành công gần đây")
    # A new sync failure should not falsely recover an already open Sheet incident.
    elif settings.sheet_ready and sheet and sheet.error:
        pending.add("system:sheet")
    for target in active_targets:
        key = f"target:{target.id}"
        is_systemd = target.container.startswith("systemd:")
        query_key = f"systemd:{target.host}" if is_systemd else f"docker:{target.host}"
        stale_key = f"stale:{target.id}"
        if target.container.startswith("rabbitmq:"):
            worker = health.get("rabbitmq-worker")
            reference = target.checked_at or (worker.created_at if worker else stamp)
            if not target.checked_at:
                cursor = session.get(AvailabilityCursor, target.id)
                if cursor:
                    reference = max(reference, cursor.recorded_since)
            if stamp - reference > stale:
                problems[stale_key] = ("Kết quả kiểm tra queue RabbitMQ quá hạn", target_detail(target))
                pending.add(key)
            elif target.status == "DOWN" and target.failures >= settings.failure_threshold:
                problems[key] = ("Queue RabbitMQ bị DOWN", target_detail(target))
            elif target.status == "UNKNOWN" and target.query_failures >= settings.failure_threshold:
                problems[key] = ("Không kiểm tra được queue RabbitMQ", target_detail(target))
            elif target.status != "UP" or target.successes < settings.recovery_threshold:
                pending.update({key, stale_key})
            continue
        parent = parents.get(target.host)
        if target.host in agent_stale_hosts:
            pending.update({key, query_key, stale_key})
            continue
        if target.container and parent and (parent.status != "UP" or not parent.checked_at or stamp - parent.checked_at > stale):
            # Preserve existing child incidents silently while parent is unreachable.
            pending.update({key, query_key, stale_key})
            continue
        if target.checked_at is None or stamp - target.checked_at > stale:
            host_health = health.get(f"host:{target.host}")
            reference = target.checked_at or (host_health.last_attempt_at if host_health else stamp)
            if stamp - reference > stale:
                problems[stale_key] = ("Kết quả kiểm tra quá hạn", target_detail(target))
            pending.update({key, query_key})
            continue
        if target.status == "DOWN":
            if target.failures >= settings.failure_threshold:
                title = "System service bị DOWN" if is_systemd else ("Compose có service DOWN" if target.container.startswith("compose:") else "Server mất heartbeat")
                problems[key] = (title, target_detail(target))
            else:
                pending.add(key)
        elif target.status != "UP" or target.successes < settings.recovery_threshold:
            pending.add(key)
        if target.container:
            if target.query_failures >= settings.failure_threshold:
                title = "Không đọc được systemd" if is_systemd else "Không đọc được Docker"
                details = target_detail(parent or target) + "\n" + title + "; chưa thể kết luận dịch vụ DOWN."
                problems[query_key] = (title, details)
            elif target.query_failures or target.query_successes < settings.recovery_threshold:
                pending.add(query_key)
    from .disks import monitored_key
    for host, parent in parents.items():
        if not parent.configured_enabled:
            continue
        metrics = parent.disk_metrics or {}
        disks = {disk["path"]: disk for disk in metrics.get("disks", [])}
        for config in (parent.server_config or {}).get("disks", []):
            path = config["path"]
            key = monitored_key(parent.id, path)
            disk = disks.get(path)
            if host in agent_stale_hosts or not disk or not parent.checked_at:
                pending.add(key)
                continue
            if disk.get("state") in {"LOW", "ERROR"}:
                title = "Ổ đĩa sắp hết dung lượng" if disk["state"] == "LOW" else "Không đọc được dung lượng ổ đĩa"
                detail = target_detail(parent).rsplit("Kết quả:", 1)[0] + f"Ổ đĩa: {path}\nKết quả: {disk['reason']}"
                problems[key] = (title, detail)
            elif disk.get("state") != "UP":
                pending.add(key)
    existing = {i.key: i for i in session.scalars(select(Incident))}
    local_time = stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.display_timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")
    for key, (title, detail) in problems.items():
        incident = existing.get(key)
        is_new = incident is None or not incident.active
        if incident is None:
            incident = Incident(key=key, title=title, detail=detail, active=True, opened_at=stamp, last_enqueued_at=stamp)
            session.add(incident)
        reminder_due = settings.alert_reminder_seconds > 0 and stamp - incident.last_enqueued_at >= timedelta(seconds=settings.alert_reminder_seconds)
        waiting = session.scalar(select(Outbox.id).where(Outbox.incident_key == key, Outbox.sent_at.is_(None)).limit(1))
        if is_new or (reminder_due and waiting is None):
            label = "🔴" if is_new else "⏰ Nhắc lại:"
            session.add(Outbox(incident_key=key, text=f"{label} {title}\n{detail}\nThời điểm: {local_time}"))
            incident.last_enqueued_at = stamp
        if is_new:
            incident.opened_at = stamp
        incident.active, incident.closed_at, incident.title, incident.detail = True, None, title, detail
    disabled_keys = {f"{category}:{t.id}" for t in targets if not t.enabled or (t.container and not t.container.startswith(("compose:", "systemd:", "rabbitmq:"))) for category in ("target", "stale")}
    enabled_hosts = {t.host for t in active_targets if t.container.startswith("compose:")}
    systemd_hosts = {t.host for t in active_targets if t.container.startswith("systemd:")}
    for key, incident in existing.items():
        if incident.active and key not in problems and key not in pending:
            incident.active, incident.closed_at = False, stamp
            disabled = key in disabled_keys or (key.startswith("docker:") and key[7:] not in enabled_hosts) or (key.startswith("systemd:") and key[8:] not in systemd_hosts) or (key.startswith("agent:") and key[6:] not in parents)
            disabled = disabled or (key.startswith("disk:") and not notification_is_monitored(session, key))
            disabled = disabled or (key == "system:sheet" and not settings.sheet_ready)
            if disabled:
                # Closing an intentionally removed monitor is not a recovery event.
                continue
            label = "🟢 Phục hồi"
            duration = max(0, int((stamp - incident.opened_at).total_seconds()))
            duration_text = f"{duration // 3600} giờ {(duration % 3600) // 60} phút" if duration >= 3600 else f"{duration // 60} phút"
            session.add(Outbox(incident_key=key, text=f"{label}: {incident.title}\nSự cố trước đó:\n{incident.detail}\nThời gian sự cố: {duration_text}\nThời điểm: {local_time}"))
    heartbeat(session, "alert-worker")


def deliver(settings, sessions):
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.warning("Telegram not configured; notifications remain queued in DB")
        return
    with sessions() as session:
        # FIFO delivery keeps recovery after the corresponding failure notification.
        ids = list(session.scalars(select(Outbox.id).where(Outbox.sent_at.is_(None)).order_by(Outbox.id).limit(20)))
    for item_id in ids:
        with sessions.begin() as session:
            item = session.scalar(select(Outbox).where(Outbox.id == item_id, Outbox.sent_at.is_(None)).with_for_update())
            if item is None:
                continue
            if not notification_is_monitored(session, item.incident_key, settings):
                # Cancel unsent failure/recovery/reminder messages for removed monitors.
                # Already sent notifications and incident/sample history remain intact.
                session.delete(item)
                continue
            if item.text.startswith("⏰ Nhắc lại:"):
                incident = session.get(Incident, item.incident_key)
                if settings.alert_reminder_seconds == 0 or incident is None or not incident.active:
                    # Cancel unsent reminders after disabling them or resolving the incident.
                    session.delete(item)
                    continue
            if item.next_attempt_at > now():
                break
            item.attempts += 1
            try:
                telegram_users = {user.owner: user.user_id or user.username for user in session.scalars(select(TelegramUser))}
                message = {
                    "chat_id": settings.telegram_chat_id,
                    "text": test_telegram_message(item.text, telegram_users) if item.incident_key.startswith("test:") else telegram_message(item.text, telegram_users),
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                }
                if settings.telegram_message_thread_id is not None:
                    message["message_thread_id"] = settings.telegram_message_thread_id
                response = requests.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                    json=message, timeout=(5, 15),
                )
                payload = response.json()
                if response.status_code == 429:
                    delay = max(1, int(payload.get("parameters", {}).get("retry_after", 60)))
                    item.next_attempt_at = now() + timedelta(seconds=delay)
                    item.last_error = "Telegram rate limit"
                    break
                if not response.ok or not payload.get("ok"):
                    description = str(payload.get("description", "Telegram từ chối yêu cầu"))
                    description = description.replace(settings.telegram_bot_token, "[TOKEN]")
                    description = re.sub(r"https?://\S+", "[URL]", description)
                    item.last_error = f"Telegram HTTP {response.status_code}: {shortened(description, 300)}"
                    item.next_attempt_at = now() + timedelta(seconds=min(1800, 15 * 2 ** min(item.attempts, 7)))
                    log.warning("Telegram notification %s failed: %s", item.id, item.last_error)
                    break
                item.sent_at, item.last_error = now(), ""
            except Exception as exc:
                if isinstance(exc, SQLAlchemyError):
                    # Let the transaction roll back before reporting schema/DB errors.
                    raise
                # Never persist/log request URLs, which include the bot token.
                if isinstance(exc, requests.exceptions.SSLError):
                    detail = "TLS/SSL: không xác minh được kết nối Telegram"
                elif isinstance(exc, requests.exceptions.Timeout):
                    detail = "Timeout: kết nối/đọc phản hồi Telegram quá hạn"
                elif isinstance(exc, requests.exceptions.ConnectionError):
                    # Inspect locally for classification; never log the raw exception URL.
                    detail = "DNS: không phân giải được api.telegram.org" if any(marker in str(exc) for marker in ("NameResolutionError", "getaddrinfo", "Temporary failure in name resolution")) else "ConnectionError: không kết nối được Telegram; kiểm tra mạng/proxy/firewall"
                else:
                    detail = type(exc).__name__
                item.last_error = f"Telegram delivery failed: {detail}"
                item.next_attempt_at = now() + timedelta(seconds=min(1800, 15 * 2 ** min(item.attempts, 7)))
                log.warning("Telegram notification %s failed: %s", item.id, item.last_error)
                break


def run(settings, sessions):
    while True:
        if not settings.ready:
            time.sleep(5)
            continue
        try:
            with sessions.begin() as session:
                evaluate(session, settings)
        except Exception as exc:
            log.error("Alert evaluation failed: %s", type(exc).__name__)
        # Delivery must still run if incident evaluation fails; test messages are independent.
        try:
            deliver(settings, sessions)
        except Exception as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
            hint = " Run init-db to upgrade the database schema." if sqlstate in {"42703", "42P01"} else ""
            log.error("Telegram delivery loop failed: %s.%s", type(exc).__name__, hint)
        settings.wait(settings.alert_poll_seconds)
