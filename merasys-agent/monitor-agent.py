#!/usr/bin/env python3
"""Docker-host monitoring agent; reports inventory to the central API."""
import argparse
import ipaddress
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

COMMAND = ["docker", "container", "ls", "--all", "--no-trunc", "--format", "{{json .}}"]


def read_services():
    result = subprocess.run(
        ["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-legend", "--no-pager"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=True,
        env={**os.environ, "LC_ALL": "C", "SYSTEMD_COLORS": "0"},
    )
    services = {}
    for line in result.stdout.decode("utf-8").splitlines():
        fields = line.split(None, 4)
        if not fields:
            continue
        if len(fields) < 4 or not fields[0].endswith(".service"):
            raise ValueError("Invalid systemctl inventory")
        services[fields[0]] = fields[2]
    return services


def load_config(path=None):
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "url": os.environ.get("MONITOR_URL", ""),
        "host": os.environ.get("SERVER_IP", ""),
        "token": os.environ.get("AGENT_TOKEN", ""),
        "interval_seconds": int(os.environ.get("REPORT_INTERVAL_SECONDS", "60")),
        "allow_http": os.environ.get("ALLOW_HTTP", "false").lower() == "true",
    }


def run_once(config):
    disks = []
    for path in config.get("_disk_paths", ["/"]):
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--disk-probe", path],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=True)
            if len(result.stdout) > 4096:
                raise ValueError("Disk report too large")
            disks.append(json.loads(result.stdout))
        except Exception as exc:
            disks.append({"path": path, "error": type(exc).__name__})
    services = None
    try:
        services = read_services()
    except Exception as exc:
        logging.warning("Cannot read systemd (%s); sending server heartbeat", type(exc).__name__)
    output = None
    try:
        result = subprocess.run(COMMAND, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=True)
        if len(result.stdout) > 4_000_000:
            raise ValueError("Inventory too large")
        output = result.stdout.decode("utf-8")
    except Exception as exc:
        logging.warning("Cannot read Docker (%s); sending server heartbeat", type(exc).__name__)
    body = json.dumps({"host": config["host"], "docker_output": output, "services": services, "disk_support": True, "disks": disks}).encode("utf-8")
    request = Request(config["url"].rstrip("/") + "/api/agent/report", data=body,
                      headers={"Authorization": "Bearer " + config["token"], "Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=20) as response:
        accepted = json.loads(response.read(65536))
        if response.status != 200 or not accepted.get("ok"):
            raise RuntimeError("Report rejected")
        paths = accepted.get("disk_paths", ["/"])
        if not isinstance(paths, list) or len(paths) > 16 or any(not isinstance(path, str) or not path.startswith("/") or len(path) > 200 or "\0" in path for path in paths):
            raise ValueError("Invalid disk paths from core")
        config["_disk_paths"] = paths
    logging.info("Report accepted for %s", config["host"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Optional JSON override; default uses environment variables")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--disk-probe", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.disk_probe:
        path = args.disk_probe
        try:
            usage = os.statvfs(path)
            result = {"path": path, "total_bytes": usage.f_blocks * usage.f_frsize,
                      "free_bytes": max(0, usage.f_bavail * usage.f_frsize), "is_mount": os.path.ismount(path)}
        except Exception as exc:
            result = {"path": path, "error": type(exc).__name__}
        print(json.dumps(result))
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    ipaddress.ip_address(config["host"])
    if len(config["token"]) < 32:
        raise ValueError("Agent token must be at least 32 characters")
    url = urlparse(config["url"])
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Invalid API URL")
    if url.scheme != "https" and not config.get("allow_http", False):
        raise ValueError("Use HTTPS, or explicitly allow HTTP inside a trusted private network")
    interval = int(config.get("interval_seconds", 60))
    if interval < 10:
        raise ValueError("interval_seconds must be at least 10")
    if args.validate_only:
        logging.info("Configuration valid for %s", config["host"])
        return
    while True:
        started = time.monotonic()
        try:
            run_once(config)
        except Exception as exc:
            # Do not log headers, token or request body.
            logging.error("Report failed (%s), HTTP status=%s", type(exc).__name__, getattr(exc, "code", "n/a"))
            if args.once:
                raise SystemExit(1)
        if args.once:
            return
        time.sleep(max(1, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
