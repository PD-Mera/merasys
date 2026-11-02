#!/usr/bin/env bash
set -euo pipefail
umask 077
agent_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$agent_dir"

[[ "$(id -u)" == 0 ]] || { echo 'Chạy bằng: sudo bash install.sh' >&2; exit 1; }
[[ -x /usr/bin/python3 ]] || { echo 'Cần cài python3 trước (ví dụ apt install python3).' >&2; exit 1; }
command -v systemctl >/dev/null 2>&1 || { echo 'Server cần chạy systemd.' >&2; exit 1; }
# Explicit arguments replace runtime URL/IP/token; no arguments preserve interactive setup.
config_path="$agent_dir/.env"
explicit_config=false
if [[ "$#" -gt 0 ]]; then
    monitor_url='' server_ip='' agent_token=''
    while [[ "$#" -gt 0 ]]; do
        [[ "$#" -ge 2 ]] || { echo 'Thiếu giá trị tham số cài đặt.' >&2; exit 1; }
        case "$1" in
            --url) monitor_url="$2" ;;
            --server) server_ip="$2" ;;
            --token) agent_token="$2" ;;
            *) echo 'Chỉ hỗ trợ --url URL --server IP --token TOKEN.' >&2; exit 1 ;;
        esac
        shift 2
    done
    [[ -n "$monitor_url" && -n "$server_ip" && -n "$agent_token" ]] || { echo 'Cần đủ --url, --server và --token.' >&2; exit 1; }
    explicit_config=true
    config_path="$(mktemp "$agent_dir/.agent-config.XXXXXX")"
    trap 'rm -f -- "$config_path"' EXIT
fi
if ! "$explicit_config"; then
if [[ ! -e .env ]]; then
    if [[ -f /etc/merasys-agent/agent.env ]]; then
        install -m 0600 /etc/merasys-agent/agent.env .env
        echo 'Dùng lại cấu hình Merasys đã cài.'
    elif [[ -f /etc/rnd-monitor-agent/agent.env ]]; then
        install -m 0600 /etc/rnd-monitor-agent/agent.env .env
        echo 'Chuyển cấu hình agent cũ sang Merasys; giữ nguyên token/IP/URL.'
    fi
fi
if [[ ! -e .env ]]; then
    [[ -r /dev/tty ]] || { echo 'Cần terminal tương tác để nhập URL/IP/token.' >&2; exit 1; }
    read -r -p 'Địa chỉ API máy 109 (ví dụ http://192.168.1.109:8080): ' monitor_url </dev/tty
    read -r -p 'IP server này (đúng như Sheet): ' server_ip </dev/tty
    read -r -s -p 'Token riêng của server này (trùng trên 109): ' agent_token </dev/tty
    printf '\n'
fi
fi
if "$explicit_config" || [[ ! -e .env ]]; then
    [[ "$monitor_url" =~ ^https?://[[:alnum:].:/_-]+$ ]] || { echo 'URL không hợp lệ.' >&2; exit 1; }
    [[ "$server_ip" =~ ^[a-fA-F0-9.:]+$ ]] || { echo 'IP không hợp lệ.' >&2; exit 1; }
    [[ "$agent_token" =~ ^[a-zA-Z0-9_-]{32,}$ ]] || { echo 'Token phải có ít nhất 32 ký tự chữ/số/_/-.' >&2; exit 1; }
    allow_http=false
    if [[ "$monitor_url" == http://* ]]; then
        allow_http=true
        echo 'Đang dùng HTTP: chỉ triển khai trên mạng riêng tin cậy/VPN.'
    fi
    # Values above are restricted to characters safe in single-quoted dotenv values.
    printf "MONITOR_URL='%s'\nSERVER_IP='%s'\nAGENT_TOKEN='%s'\nREPORT_INTERVAL_SECONDS=60\nALLOW_HTTP=%s\n" \
        "$monitor_url" "$server_ip" "$agent_token" "$allow_http" > "$config_path"
    unset agent_token
else
    echo 'Dùng file .env đã có; không ghi đè cấu hình.'
fi
chmod 0600 "$config_path"
# Parse dotenv without executing its contents, then validate configuration.
/usr/bin/python3 - "$config_path" "$agent_dir/monitor-agent.py" <<'PY'
import os, shlex, subprocess, sys
from pathlib import Path
allowed = {"MONITOR_URL", "SERVER_IP", "AGENT_TOKEN", "REPORT_INTERVAL_SECONDS", "ALLOW_HTTP"}
values = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    key, sep, raw = line.partition("=")
    key = key.strip()
    if not sep or key not in allowed:
        raise SystemExit("Agent .env chứa dòng hoặc tên biến không hợp lệ")
    parts = shlex.split(raw, comments=True, posix=True)
    if len(parts) != 1:
        raise SystemExit("Giá trị env cần một giá trị (dùng dấu nháy nếu cần)")
    values[key] = parts[0]
subprocess.run([sys.executable, sys.argv[2], "--validate-only"], env={**os.environ, **values}, check=True)
PY
install -d -m 0755 /opt/merasys-agent
install -d -m 0700 /etc/merasys-agent
if [[ "$agent_dir/monitor-agent.py" != /opt/merasys-agent/monitor-agent.py ]]; then
    install -m 0644 monitor-agent.py /opt/merasys-agent/monitor-agent.py
fi
if "$explicit_config" && [[ -f /etc/merasys-agent/agent.env ]]; then
    cp -p /etc/merasys-agent/agent.env /etc/merasys-agent/agent.env.previous
fi
install -m 0600 "$config_path" /etc/merasys-agent/agent.env
install -m 0644 merasys-agent.service /etc/systemd/system/merasys-agent.service
systemctl daemon-reload
if systemctl cat rnd-monitor-agent.service >/dev/null 2>&1; then
    systemctl disable --now rnd-monitor-agent.service
    echo 'Đã dừng unit cũ rnd-monitor-agent để tránh hai agent cùng gửi report.'
fi
systemctl enable merasys-agent
systemctl restart merasys-agent
systemctl --no-pager --full status merasys-agent
echo 'Agent đã khởi động. Xem log: sudo journalctl -u merasys-agent -f'
