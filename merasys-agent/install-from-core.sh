#!/usr/bin/env bash
# Download the agent bundled with the running core, then install without prompts.
set -euo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo 'Chạy bằng sudo bash.' >&2; exit 1; }
install_args=("$@")
core_url=''
while [[ "$#" -gt 0 ]]; do
    [[ "$#" -ge 2 ]] || { echo 'Cần --url URL --server IP --token TOKEN.' >&2; exit 1; }
    case "$1" in
        --url) core_url="$2" ;;
        --server|--token) ;;
        *) echo 'Tham số không hợp lệ.' >&2; exit 1 ;;
    esac
    shift 2
done
[[ "$core_url" =~ ^https?://[[:alnum:].:/_-]+$ ]] || { echo 'Cần --url URL core hợp lệ.' >&2; exit 1; }
command -v systemctl >/dev/null || { echo 'Server cần Linux/systemd.' >&2; exit 1; }
if [[ ! -x /usr/bin/python3 ]] || ! command -v tar >/dev/null; then
    if command -v apt-get >/dev/null; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y python3 tar ca-certificates
    elif command -v dnf >/dev/null; then
        dnf install -y python3 tar ca-certificates
    elif command -v yum >/dev/null; then
        yum install -y python3 tar ca-certificates
    else
        echo 'Cần cài Python3 và tar trên server.' >&2; exit 1
    fi
fi
work_dir="$(mktemp -d /tmp/merasys-agent-install.XXXXXX)"
trap 'rm -rf -- "$work_dir"' EXIT
curl -fsSL "${core_url%/}/agent/bundle.tar.gz" -o "$work_dir/agent.tar.gz"
mkdir "$work_dir/source"
tar -xzf "$work_dir/agent.tar.gz" -C "$work_dir/source"
bash "$work_dir/source/install.sh" "${install_args[@]}"
