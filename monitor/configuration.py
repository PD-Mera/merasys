import ipaddress
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.engine import make_url

from . import control
from .db import Health, connect, initialize, now
from .settings import DEFAULTS, SECRET_KEYS

LIMITS = {"sheet_sync_seconds": (10,86400), "failure_threshold": (1,100), "recovery_threshold": (1,100),
          "stale_after_seconds": (30,86400), "alert_poll_seconds": (5,3600), "alert_reminder_seconds": (0,604800),
          "sheet_stale_after_seconds": (60,604800), "rabbitmq_poll_seconds": (10,3600)}


def validate(values):
    if set(values) - set(DEFAULTS):
        raise ValueError("Có tham số cấu hình không hỗ trợ")
    result = {**DEFAULTS, **values}
    for key, (minimum, maximum) in LIMITS.items():
        if type(result[key]) is not int or not minimum <= result[key] <= maximum:
            raise ValueError(f"{key} phải là số nguyên từ {minimum} đến {maximum}")
    for key in ("google_sheet_id", "google_worksheet", "telegram_bot_token", "telegram_chat_id", "display_timezone", "database_url"):
        if not isinstance(result[key], str) or len(result[key]) > 4096:
            raise ValueError(f"{key} không hợp lệ")
        result[key] = result[key].strip()
    if result["database_url"]:
        try:
            url = make_url(result["database_url"])
            if url.drivername not in {"postgresql", "postgresql+psycopg"} or not url.host or not url.database:
                raise ValueError()
            result["database_url"] = url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        except Exception:
            raise ValueError("Database URL cần dạng postgresql+psycopg://user:password@host:port/database") from None
    try:
        ZoneInfo(result["display_timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Múi giờ không hợp lệ") from None
    thread = result["telegram_message_thread_id"]
    if thread is not None and (type(thread) is not int or thread <= 0):
        raise ValueError("Telegram thread ID phải là số nguyên dương hoặc để trống")
    credentials = result["google_credentials_info"]
    if not isinstance(credentials, dict):
        raise ValueError("Google credentials phải là object JSON")
    if credentials:
        try:
            from google.oauth2.service_account import Credentials
            Credentials.from_service_account_info(credentials)
        except Exception:
            raise ValueError("Google service account JSON không hợp lệ") from None
    tokens = result["agent_tokens"]
    if not isinstance(tokens, dict) or len(tokens) > 1000:
        raise ValueError("Agent tokens phải là object JSON tối đa 1000 máy")
    for host, token in tokens.items():
        try:
            ipaddress.ip_address(host)
        except (ValueError, TypeError):
            raise ValueError("Agent tokens có IP không hợp lệ") from None
        if not isinstance(token, str) or not 32 <= len(token) <= 256 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in token):
            raise ValueError("Agent token cần 32–256 ký tự chữ/số/_/-")
    return result


def public(settings):
    config = settings.reload()
    database = "Chưa cấu hình"
    if config["database_url"]:
        url = make_url(config["database_url"])
        database = f"{url.host}:{url.port or 5432}/{url.database} · {url.username or ''}"
    return {"values": {key:value for key,value in config.items() if key not in SECRET_KEYS},
            "configured": {key: bool(config[key]) for key in SECRET_KEYS}, "database": database,
            "agent_hosts": sorted(config["agent_tokens"]), "web": {"host": settings.web_host, "port": settings.web_port}}


def prepare_database(url, stale_seconds):
    engine, sessions = connect(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        initialize(engine)
        with sessions.begin() as session:
            for name in ("sheet", "alert-worker", "rabbitmq-worker"):
                if session.get(Health, name) is None:
                    session.add(Health(name=name, last_attempt_at=now()))
            from .availability import initialize_history
            initialize_history(session, stale_seconds)
    finally:
        engine.dispose()


def save(settings, changes, clear):
    stored = control.configuration()
    current = {**DEFAULTS, **stored}
    if set(clear) - SECRET_KEYS:
        raise ValueError("Trường xóa secret không hợp lệ")
    for key in clear:
        current[key] = {} if isinstance(DEFAULTS[key], dict) else ""
    for key, value in changes.items():
        if key in SECRET_KEYS and value in ("", None):
            continue  # Blank password/JSON inputs preserve the existing secret.
        current[key] = value
    validated = validate(current)
    old_url = stored.get("database_url", "")
    if validated["database_url"] and validated["database_url"] != old_url:
        prepare_database(validated["database_url"], validated["stale_after_seconds"])
    control.save_configuration(validated, stored)
    settings.reload()
