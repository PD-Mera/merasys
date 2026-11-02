import ipaddress
import re

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import delete, select

from .db import Health, Target, TelegramUser, RabbitMQConnection, heartbeat, now
from .rabbitmq import QUEUE_HEADERS, identity, parse_connections, queue_config
from .disks import parse_config as parse_server_config

HEADERS = ["Bật giám sát", "Dự án", "Tên dịch vụ", "IP server", "Type", "Người phụ trách", "Tên compose", "Tên queue", "RabbitMQ connection", "Queue config", "Server config", "Note"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TELEGRAM_USERS_HEADERS = ["Người phụ trách", "Telegram user ID", "Telegram username"]


def parse_telegram_users(values):
    headers = [str(value).strip() for value in values[0]] if values else []
    if headers not in (TELEGRAM_USERS_HEADERS, TELEGRAM_USERS_HEADERS[:2]):
        raise ValueError("Tab TelegramUsers phải có các cột: " + " | ".join(TELEGRAM_USERS_HEADERS) + "; cột Telegram username tùy chọn")
    users, declared, errors = {}, {}, []
    for number, row in enumerate(values[1:], 2):
        cells = [str(value).strip() for value in row]
        if not any(cells):
            continue
        cells += [""] * max(0, 3 - len(cells))
        owner, user_id, username = cells[:3]
        try:
            if any(cells[len(headers):]):
                raise ValueError(f"chỉ cho phép {len(headers)} cột khai báo")
            if not owner or len(owner) > 200 or "," in owner or "\n" in owner or "\r" in owner:
                raise ValueError("Người phụ trách phải là một tên, tối đa 200 ký tự, không chứa dấu phẩy/xuống dòng")
            if user_id:
                if not re.fullmatch(r"[1-9][0-9]{0,15}", user_id) or int(user_id) > 2 ** 52 - 1:
                    raise ValueError("Telegram user ID phải là số nguyên dương dạng đầy đủ, không phải @username hay ID nhóm")
            if username:
                username = "@" + username.removeprefix("@").lower()
                if not re.fullmatch(r"@[a-zA-Z0-9_]{1,32}", username):
                    raise ValueError("Telegram username phải là @username, chỉ chứa chữ Latin, số hoặc _, tối đa 32 ký tự sau @")
            key = owner.casefold()
            identity = (user_id, username)
            if key in declared and declared[key] != identity:
                raise ValueError("cùng người phụ trách đang có ID/username khác nhau")
            declared[key] = identity
            if user_id or username:
                users[key] = identity
        except ValueError as exc:
            errors.append(f"TelegramUsers dòng {number}: {exc}")
    if errors:
        raise ValueError("; ".join(errors))
    return users


def parse_rows(values):
    def normalize_header(value):
        value = str(value).strip()
        return {"type": "Type", "ip server": "IP server"}.get(value.casefold(), value)
    headers = [normalize_header(x) for x in values[0]] if values else []
    # Existing Sheets keep working until the optional Server config column is added.
    accepted = (HEADERS, HEADERS[:-1], [h for h in HEADERS if h != "Server config"], [h for h in HEADERS[:-1] if h != "Server config"])
    if headers not in accepted:
        raise ValueError("Tiêu đề Sheet: " + " | ".join(HEADERS) + "; Note cuối có thể bỏ; xóa cột RabbitMQ username")
    width = len(headers)
    grouped, errors = {}, []
    for number, row in enumerate(values[1:], 2):
        cells = [str(value).strip() for value in row]
        if not any(cells):
            continue
        cells += [""] * max(0, width - len(cells))
        fields = dict(zip(headers, cells[:width]))
        try:
            if any(cells[width:]):
                raise ValueError(f"chỉ cho phép {width} cột khai báo")
            flag = fields["Bật giám sát"].upper()
            if flag not in {"TRUE", "FALSE"}:
                raise ValueError("Bật giám sát phải là TRUE hoặc FALSE")
            host = fields["IP server"]
            ipaddress.ip_address(host)
            monitor_type = fields["Type"].casefold()
            if monitor_type not in {"server", "compose", "rabbitmq"}:
                raise ValueError("Type phải là server, compose hoặc rabbitmq")
            compose = fields["Tên compose"]
            selector = ""
            rabbitmq = {}
            if monitor_type != "server" and fields.get("Server config"):
                raise ValueError("Server config chỉ được điền khi Type=server")
            server_config = parse_server_config(fields.get("Server config", "")) if monitor_type == "server" else {}
            if monitor_type != "rabbitmq" and any(fields.get(header) for header in QUEUE_HEADERS):
                raise ValueError("các cột RabbitMQ chỉ được điền khi Type=rabbitmq")
            if monitor_type == "rabbitmq":
                if compose:
                    raise ValueError("Type rabbitmq phải để trống Tên compose")
                rabbitmq = queue_config(fields)
                selector = "rabbitmq:" + identity(rabbitmq["connection_key"], rabbitmq["queue"])
            elif monitor_type == "server":
                if compose:
                    raise ValueError("Type server phải để trống Tên compose")
            else:
                if not compose:
                    raise ValueError("Type compose phải điền Tên compose")
                if len(compose) > 247 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", compose):
                    raise ValueError("tên Compose project không hợp lệ")
                selector = "compose:" + compose
            display_name = " ".join(fields["Tên dịch vụ"].split())
            if len(display_name) > 200:
                raise ValueError("Tên dịch vụ tối đa 200 ký tự")
            enabled = flag == "TRUE"
            key = (host, selector)
            item = grouped.setdefault(key, {"enabled": enabled, "projects": set(), "owners": set(), "notes": set(), "display_name": display_name})
            if "rabbitmq" in item and item["rabbitmq"] != rabbitmq:
                raise ValueError("các dòng cùng queue/connection phải có cùng cấu hình RabbitMQ")
            item["rabbitmq"] = rabbitmq
            if "server_config" in item and item["server_config"] != server_config:
                raise ValueError("các dòng cùng server phải có cùng Server config")
            item["server_config"] = server_config
            if item["enabled"] != enabled:
                raise ValueError("các dòng cùng IP và đối tượng phải có cùng trạng thái bật giám sát")
            if display_name:
                if item["display_name"] and item["display_name"] != display_name:
                    raise ValueError("các dòng cùng IP và đối tượng phải có cùng Tên dịch vụ")
                item["display_name"] = display_name
            item["projects"].update(x.strip() for x in fields["Dự án"].split(",") if x.strip())
            item["owners"].update(x.strip() for x in fields["Người phụ trách"].split(",") if x.strip())
            if fields.get("Note"):
                item["notes"].add(fields["Note"])
        except ValueError as exc:
            errors.append(f"Dòng {number}: {exc}")
    if errors:
        raise ValueError("; ".join(errors))
    # Headers-only is an intentional removal of all declarations.
    return grouped


def apply_rows(session, grouped, stale_after_seconds=180):
    existing = {(t.host, t.container): t for t in session.scalars(select(Target).order_by(Target.id).with_for_update())}
    # The fully validated Sheet is authoritative. Retain history, stop observation.
    for key, target in existing.items():
        if key not in grouped:
            target.configured_enabled = False
            if target.container:
                target.enabled = False
                target.failures = target.successes = target.query_failures = target.query_successes = 0
    for (host, container), config in grouped.items():
        target = existing.get((host, container))
        if target is None and config.get("rabbitmq"):
            # Retain the ID/history when upgrading the old username-based identity.
            queue = config["rabbitmq"]
            candidates = [t for t in existing.values() if t.host == host and t.container.startswith("rabbitmq:")
                          and (t.host, t.container) not in grouped
                          and (t.rabbitmq or {}).get("connection") == queue["connection"]
                          and (t.rabbitmq or {}).get("queue") == queue["queue"]]
            if len(candidates) == 1:
                target = candidates[0]
                target.container = container
        if target is None:
            target = Target(host=host, container=container)
            session.add(target)
        # Reset counters on explicit enable/disable changes.
        if target.configured_enabled != config["enabled"] or (target.rabbitmq or {}) != config.get("rabbitmq", {}):
            target.failures = target.successes = target.query_failures = target.query_successes = 0
            target.checked_at = None
            target.status = "UNKNOWN"
            target.rabbitmq_metrics = {}
        target.enabled = config["enabled"]
        target.configured_enabled = config["enabled"]
        if config["enabled"]:
            target.archived = False
        if config["display_name"] is not None:
            target.display_name = config["display_name"]
        target.projects = sorted(config["projects"])
        target.owners = sorted(config["owners"])
        target.declared_projects = target.projects
        target.declared_owners = target.owners
        target.note = "\n".join(sorted(config["notes"]))
        target.rabbitmq = config.get("rabbitmq", {})
        next_server_config = config.get("server_config", {}) if config["enabled"] else {}
        if (target.server_config or {}) != next_server_config:
            target.disk_metrics = {}
        target.server_config = next_server_config
    session.flush()
    # Keep derived server status/config atomic with changes to child rows.
    all_targets = list(session.scalars(select(Target)))
    enabled_hosts = {t.host for t in all_targets if t.configured_enabled and not t.container.startswith("rabbitmq:")}
    for host in {t.host for t in all_targets}:
        parent = next((t for t in all_targets if t.host == host and not t.container), None)
        if parent is None:
            if host not in enabled_hosts:
                continue  # A remote broker does not require an agent/heartbeat target.
            parent = Target(host=host, container="", configured_enabled=False)
            session.add(parent)
        parent.enabled = host in enabled_hosts
        if parent.enabled:
            parent.archived = False
        if not parent.enabled:
            parent.failures = parent.successes = parent.query_failures = parent.query_successes = 0
            parent.checked_at = None
            parent.status = "UNKNOWN"
        if parent.enabled and session.get(Health, f"host:{host}") is None:
            session.add(Health(name=f"host:{host}"))
        # Server metadata belongs to its own Sheet declaration, not its Compose children.
        # An automatically created heartbeat has no declared projects or owners.
        server_config = grouped.get((host, ""))
        parent.projects = sorted(server_config["projects"]) if server_config else []
        parent.owners = sorted(server_config["owners"]) if server_config else []
        parent.declared_projects = parent.projects
        parent.declared_owners = parent.owners
        if not server_config:
            parent.server_config, parent.disk_metrics = {}, {}
    # A host remains enabled only while it has at least one enabled declaration.
    from .availability import configure
    session.flush()
    stamp = now()
    for target in session.scalars(select(Target).order_by(Target.id)):
        if not target.archived:
            configure(session, target, stamp, stale_after_seconds)
    heartbeat(session, "sheet")


def sync_sheet(settings, sessions):
    credentials = Credentials.from_service_account_info(settings.google_credentials_info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    client.set_timeout(30)
    spreadsheet = client.open_by_key(settings.google_sheet_id)
    if settings.google_worksheet == "TelegramUsers":
        raise ValueError("GOOGLE_WORKSHEET phải là tab giám sát, không phải TelegramUsers")
    worksheet = spreadsheet.worksheet(settings.google_worksheet)
    grouped = parse_rows(worksheet.get_all_values())
    # Validate all tabs before changing anything; a failed read preserves the last snapshot.
    try:
        user_worksheet = spreadsheet.worksheet("TelegramUsers")
    except gspread.WorksheetNotFound:
        raise ValueError("Thiếu tab TelegramUsers: tạo tab với hai cột Người phụ trách | Telegram user ID") from None
    telegram_users = parse_telegram_users(user_worksheet.get_all_values())
    try:
        rabbitmq_connections = parse_connections(spreadsheet.worksheet("RabbitMQConnections").get_all_values())
    except gspread.WorksheetNotFound:
        rabbitmq_connections = None
    for config in grouped.values():
        rabbitmq = config.get("rabbitmq")
        if rabbitmq:
            connection = (rabbitmq_connections or {}).get(rabbitmq["connection_key"])
            if connection is None:
                raise ValueError("Thiếu tab RabbitMQConnections hoặc không có Connection khớp dòng queue")
            rabbitmq["vhost"] = connection["vhost"]
    with sessions.begin() as session:
        apply_rows(session, grouped, settings.stale_after_seconds)
        session.execute(delete(TelegramUser))
        session.add_all(TelegramUser(owner=owner, user_id=identity[0], username=identity[1]) for owner, identity in telegram_users.items())
        if rabbitmq_connections is not None:
            session.execute(delete(RabbitMQConnection))
            session.add_all(RabbitMQConnection(key=key, config=config) for key, config in rabbitmq_connections.items())
