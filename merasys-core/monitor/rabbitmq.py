"""Core-side queue checks. No AMQP publish, consume, acknowledgement or mutation."""
import hashlib
import json
import logging
import math
import re
import time
from datetime import timedelta
from urllib.parse import quote, urlsplit

import requests
from sqlalchemy import select

from .db import RabbitMQConnection, Sample, Target, heartbeat, now

log = logging.getLogger(__name__)
CONNECTION_HEADERS = ["Connection", "Management URL", "Username", "Password", "Vhost"]
QUEUE_HEADERS = ["Tên queue", "RabbitMQ connection", "Queue config"]


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def parse_connections(values):
    if not values or [str(value).strip() for value in values[0]] != CONNECTION_HEADERS:
        raise ValueError("Tab RabbitMQConnections cần các cột: " + " | ".join(CONNECTION_HEADERS))
    result, errors = {}, []
    for number, row in enumerate(values[1:], 2):
        # Password is kept exactly as supplied, including leading/trailing spaces.
        cells = [str(value) for value in row]
        if not any(value.strip() for value in cells):
            continue
        cells += [""] * max(0, 5 - len(cells))
        name, url, username, password, vhost = cells[:5]
        name, url, username, vhost = name.strip(), url.strip().rstrip("/"), username.strip(), vhost.strip()
        try:
            if any(value.strip() for value in cells[5:]):
                raise ValueError("chỉ được khai báo 5 cột")
            if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", name):
                raise ValueError("Connection chỉ dùng chữ, số, dấu chấm, _ hoặc -, tối đa 100 ký tự")
            try:
                parsed = urlsplit(url)
                _ = parsed.port
            except ValueError:
                raise ValueError("Management URL có hostname/cổng không hợp lệ") from None
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
                raise ValueError("Management URL phải là http(s)://host:port, không chứa tài khoản hoặc đường dẫn")
            if not username or len(username) > 200 or not password or not vhost:
                raise ValueError("cần Username (tối đa 200 ký tự), Password và Vhost")
            key = identity(name)
            config = {"name": name, "url": url, "username": username, "password": password, "vhost": vhost}
            if key in result and result[key] != config:
                raise ValueError("Connection trùng nhưng thông tin kết nối khác nhau")
            result[key] = config
        except ValueError as exc:
            # Never echo URLs, usernames, passwords or parser exceptions into logs.
            # All errors here are controlled validation messages; URL parser errors are replaced above.
            errors.append(f"RabbitMQConnections dòng {number}: {exc}")
    if errors:
        raise ValueError("; ".join(errors))
    return result


def queue_config(fields):
    queue, name, raw_config = (fields.get(header, "") for header in QUEUE_HEADERS)
    if not name or not queue or len(queue) > 255 or any(c in queue for c in "\r\n"):
        raise ValueError("Type rabbitmq cần RabbitMQ connection và Tên queue (tối đa 255 ký tự)")
    try:
        options = json.loads(raw_config) if raw_config else {}
    except ValueError:
        raise ValueError('Queue config phải là JSON, ví dụ {"min_consumers":1,"alert_threshold":1000}') from None
    if not isinstance(options, dict) or set(options) - {"min_consumers", "alert_threshold"}:
        raise ValueError("Queue config chỉ nhận object JSON với min_consumers và alert_threshold")
    minimum = options.get("min_consumers", 0)
    threshold = options.get("alert_threshold")
    if type(minimum) is not int or not 0 <= minimum <= 999999:
        raise ValueError("min_consumers phải là số nguyên từ 0 đến 999999")
    if threshold is not None and (type(threshold) is not int or not 1 <= threshold <= 10 ** 12):
        raise ValueError("alert_threshold phải là số nguyên dương tối đa 1000000000000, hoặc null để tắt")
    return {"connection": name, "queue": queue, "min_consumers": minimum, "alert_threshold": threshold, "connection_key": identity(name)}


def check_queue(config, connection, measured=None):
    measured = measured if measured is not None else {}
    measured.clear()
    url = connection["url"] + "/api/queues/" + quote(connection["vhost"], safe="") + "/" + quote(config["queue"], safe="")
    try:
        response = requests.get(url, auth=(connection["username"], connection["password"]), timeout=(3, 5), allow_redirects=False)
        if response.status_code == 404:
            return "DOWN", "Không tìm thấy queue trong vhost/phạm vi tài khoản đã khai báo"
        if response.status_code in {401, 403}:
            return "UNKNOWN", f"RabbitMQ HTTP {response.status_code}: tài khoản không đăng nhập được hoặc thiếu quyền xem queue"
        if response.status_code != 200:
            return "UNKNOWN", f"RabbitMQ Management API HTTP {response.status_code}"
        payload = response.json()
        if not isinstance(payload, dict):
            return "UNKNOWN", "RabbitMQ trả dữ liệu không hợp lệ"
        counts = [payload.get(key) for key in ("consumers", "messages_ready", "messages_unacknowledged")]
        if any(type(value) is not int or value < 0 for value in counts):
            return "UNKNOWN", "RabbitMQ chưa cung cấp đủ số liệu queue"
        consumers, ready, unacked = counts
        total = payload.get("messages")
        measured.update(consumers=consumers, messages_ready=ready, messages_unacknowledged=unacked,
                        messages=total if type(total) is int and total >= 0 else ready + unacked)
        stats = payload.get("message_stats")
        stats = stats if isinstance(stats, dict) else {}
        for source, destination in (("publish", "publish"), ("deliver_get", "deliver"), ("ack", "ack")):
            count = stats.get(source)
            measured[destination + "_count"] = count if type(count) is int and count >= 0 else None
            details = stats.get(source + "_details")
            rate = details.get("rate") if isinstance(details, dict) else None
            measured[destination + "_rate"] = rate if type(rate) in (int, float) and math.isfinite(rate) and rate >= 0 else None
        reason = f"Consumers: {consumers} (yêu cầu ≥ {config['min_consumers']}) · Ready: {ready} · Unacked: {unacked}"
        if payload.get("state") in {"down", "crashed", "stopped"}:
            return "DOWN", "RabbitMQ báo queue không hoạt động · " + reason
        violations = []
        if consumers < config["min_consumers"]:
            violations.append("Thiếu consumer")
        threshold = config.get("alert_threshold")
        if threshold is not None:
            reason += f" · Ngưỡng ready: {threshold}"
            if ready >= threshold:
                violations.append("Message chờ đạt/vượt ngưỡng")
        return ("DOWN", "; ".join(violations) + " · " + reason) if violations else ("UP", reason)
    except requests.exceptions.Timeout:
        return "UNKNOWN", "RabbitMQ Management API timeout"
    except requests.exceptions.RequestException:
        return "UNKNOWN", "Không kết nối được RabbitMQ Management API; kiểm tra DNS/mạng/TLS"
    except ValueError:
        return "UNKNOWN", "RabbitMQ trả dữ liệu JSON không hợp lệ"


def check_once(settings, sessions):
    with sessions() as session:
        connections = {row.key: dict(row.config) for row in session.scalars(select(RabbitMQConnection))}
        targets = [(target.id, dict(target.rabbitmq)) for target in session.scalars(select(Target).where(Target.enabled.is_(True), Target.container.startswith("rabbitmq:")).order_by(Target.id))]
    for target_id, config in targets:
        connection = connections.get(config.get("connection_key"))
        measured = {}
        status, reason = check_queue(config, connection, measured) if connection else ("UNKNOWN", "Chưa có cấu hình kết nối RabbitMQ trong DB")
        with sessions.begin() as session:
            target = session.scalar(select(Target).where(Target.id == target_id).with_for_update())
            current_connection = session.get(RabbitMQConnection, config.get("connection_key", ""))
            if target is None or not target.enabled or target.rabbitmq != config or (dict(current_connection.config) if current_connection else None) != connection:
                continue  # The Sheet changed while the HTTP request was in progress.
            stamp = now()
            if target.checked_at and stamp - target.checked_at >= timedelta(seconds=settings.stale_after_seconds):
                target.failures = target.successes = target.query_failures = target.query_successes = 0
            target.status, target.reason, target.checked_at = status, reason, stamp
            if measured:
                target.rabbitmq_metrics = {**measured, "observed_at": stamp.isoformat() + "Z"}
            target.failures = target.failures + 1 if status == "DOWN" else 0
            target.successes = target.successes + 1 if status == "UP" else 0
            target.query_failures = target.query_failures + 1 if status == "UNKNOWN" else 0
            target.query_successes = target.query_successes + 1 if status != "UNKNOWN" else 0
            session.add(Sample(target_id=target.id, checked_at=stamp, status=status, reason=reason))
            from .availability import observe
            observe(session, target, stamp, settings.failure_threshold, settings.recovery_threshold, settings.stale_after_seconds)
    with sessions.begin() as session:
        heartbeat(session, "rabbitmq-worker")


def run(settings, sessions):
    while True:
        if not settings.ready:
            time.sleep(5)
            continue
        started = time.monotonic()
        try:
            check_once(settings, sessions)
        except Exception as exc:
            log.error("RabbitMQ worker failed: %s", type(exc).__name__)
        settings.wait(max(1, settings.rabbitmq_poll_seconds - (time.monotonic() - started)))
