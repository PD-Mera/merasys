"""Filesystem space policy, report state and alerts; does not change server heartbeat."""
import json
import math
import posixpath

from .db import now

GB = 1_000_000_000


def parse_config(value):
    try:
        config = json.loads(value) if value else {}
    except ValueError:
        raise ValueError('Server config phải là JSON, ví dụ {"disks":[{"path":"/","min_free_gb":20}]}') from None
    if not isinstance(config, dict) or set(config) - {"disks"}:
        raise ValueError("Server config chỉ nhận object JSON với khóa disks")
    disks = config.get("disks", [])
    if not isinstance(disks, list) or len(disks) > 16:
        raise ValueError("disks phải là danh sách tối đa 16 đường dẫn")
    result, seen = [], set()
    for disk in disks:
        if not isinstance(disk, dict) or set(disk) - {"path", "min_free_gb", "recover_free_gb", "require_mount"}:
            raise ValueError("Mỗi disk chỉ nhận path, min_free_gb, recover_free_gb, require_mount")
        path, minimum = disk.get("path"), disk.get("min_free_gb")
        if not isinstance(path, str) or not path.startswith("/") or len(path) > 200 or any(ord(c) < 32 for c in path) or path.startswith("//"):
            raise ValueError("Disk path phải là đường dẫn Linux tuyệt đối, tối đa 200 ký tự, không chứa ký tự điều khiển")
        path = posixpath.normpath(path)
        if path in seen:
            raise ValueError("Disk path bị khai báo trùng")
        seen.add(path)
        recovery = disk.get("recover_free_gb", minimum + 5 if type(minimum) in (int, float) else None)
        if any(type(number) not in (int, float) or not math.isfinite(number) or not 0 < number <= 1_000_000_000 for number in (minimum, recovery)) or recovery <= minimum:
            raise ValueError("min_free_gb phải dương; recover_free_gb phải lớn hơn min_free_gb; tối đa 1000000000 GB")
        required = disk.get("require_mount", False)
        if type(required) is not bool:
            raise ValueError("require_mount phải là true hoặc false")
        result.append({"path": path, "min_free_gb": minimum, "recover_free_gb": recovery, "require_mount": required})
    return {"disks": result} if result else {}


def record(parent, reports, settings):
    configured = (parent.server_config or {}).get("disks", []) if parent.configured_enabled else []
    if not configured:
        parent.disk_metrics = {}
        return
    stamp = now()
    old = parent.disk_metrics or {}
    if old.get("checked_at"):
        from datetime import datetime
        if (stamp - datetime.fromisoformat(old["checked_at"].removesuffix("Z"))).total_seconds() >= settings.stale_after_seconds:
            old = {}
    previous = {item["path"]: item for item in old.get("disks", [])}
    current = {item.path: item for item in reports or []}
    result = []
    for config in configured:
        path = config["path"]
        prior = previous.get(path, {})
        report = current.get(path)
        if report is None and not prior:
            result.append({**config, "state": "UNKNOWN", "observed": "UNKNOWN", "reason": "Chờ agent nhận danh sách đường dẫn từ core",
                           "failures": 0, "successes": 0, "total_bytes": None, "free_bytes": None})
            continue
        state = prior.get("state", "UNKNOWN")
        low_latched = prior.get("low_latched", state == "LOW")
        failures, successes = prior.get("failures", 0), prior.get("successes", 0)
        invalid = report is None or report.error or report.total_bytes is None or report.free_bytes is None
        if report is not None and report.total_bytes is not None and report.free_bytes is not None:
            invalid = invalid or report.total_bytes <= 0 or report.free_bytes > report.total_bytes
        invalid = invalid or (config["require_mount"] and report is not None and not report.is_mount)
        if invalid:
            observed, reason = "ERROR", "Agent chưa hỗ trợ/chưa gửi số liệu ổ đĩa" if report is None else ("Đường dẫn không được mount riêng" if config["require_mount"] and not report.is_mount and not report.error else "Không đọc được dung lượng filesystem: " + (report.error or "số liệu không hợp lệ"))
        else:
            free = report.free_bytes / GB
            limit = config["recover_free_gb"] if low_latched else config["min_free_gb"]
            observed = "LOW" if free < limit else "UP"
            reason = f"Còn {free:.2f} GB; ngưỡng thấp {config['min_free_gb']} GB; phục hồi từ {config['recover_free_gb']} GB"
        if observed == "UP":
            failures, successes = 0, successes + 1
            if successes >= settings.recovery_threshold:
                state = "UP"
        else:
            failures, successes = failures + 1, 0
            if failures >= settings.failure_threshold:
                state = observed
        if state == "LOW":
            low_latched = True
        elif state == "UP":
            low_latched = False
        result.append({**config, "state": state, "observed": observed, "reason": reason, "low_latched": low_latched,
                       "failures": failures, "successes": successes, "total_bytes": report.total_bytes if report and not invalid else None,
                       "free_bytes": report.free_bytes if report and not invalid else None})
    parent.disk_metrics = {"checked_at": stamp.isoformat() + "Z", "disks": result}


def monitored_key(target_id, path):
    return f"disk:{target_id}:{path}"
