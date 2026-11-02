#!/usr/bin/env bash
set -euo pipefail
agent_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ "$(id -u)" == 0 ]] || { echo 'Chạy bằng: sudo bash update.sh' >&2; exit 1; }
[[ -f /etc/merasys-agent/agent.env && -f /opt/merasys-agent/monitor-agent.py ]] || {
    echo 'Chưa có agent được cài đặt; dùng install.sh cho lần cài đầu.' >&2; exit 1;
}
[[ -f "$agent_dir/monitor-agent.py" ]] || { echo 'Thiếu monitor-agent.py cạnh update.sh.' >&2; exit 1; }
if [[ "$agent_dir/monitor-agent.py" != /opt/merasys-agent/monitor-agent.py ]]; then
    install -m 0644 /opt/merasys-agent/monitor-agent.py /opt/merasys-agent/monitor-agent.py.previous
    install -m 0644 "$agent_dir/monitor-agent.py" /opt/merasys-agent/monitor-agent.py
fi
# Do not copy .env or replace the existing systemd unit during an update.
systemctl restart merasys-agent
systemctl --no-pager --full status merasys-agent
echo 'Đã cập nhật code; giữ nguyên /etc/merasys-agent/agent.env và systemd unit.'
echo 'Xem log: sudo journalctl -u merasys-agent -n 30 --no-pager'
