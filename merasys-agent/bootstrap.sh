#!/usr/bin/env bash
# curl -fsSL RAW_BOOTSTRAP_URL | sudo bash -s -- REPO_URL [BRANCH]
set -euo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo 'Chạy bootstrap bằng sudo bash.' >&2; exit 1; }
[[ "$#" -ge 1 && "$#" -le 2 ]] || { echo 'Dùng: bootstrap.sh REPO_URL [BRANCH]' >&2; exit 1; }
repo_url="$1"
branch="${2:-main}"
command -v systemctl >/dev/null 2>&1 || { echo 'Server phải chạy Linux/systemd.' >&2; exit 1; }
if ! command -v git >/dev/null 2>&1 || [[ ! -x /usr/bin/python3 ]] || ! command -v flock >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 util-linux openssh-client ca-certificates
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y git python3 util-linux openssh-clients ca-certificates
    elif command -v yum >/dev/null 2>&1; then
        yum install -y git python3 util-linux openssh-clients ca-certificates
    else
        echo 'Cần cài Git, /usr/bin/python3 và flock bằng package manager của server.' >&2
        exit 1
    fi
fi
/usr/bin/python3 - "$repo_url" <<'PY'
import re, sys
from urllib.parse import urlsplit
url = sys.argv[1]
if any(ord(c) < 32 for c in url):
    raise SystemExit("Repo URL không hợp lệ")
if not re.fullmatch(r"git@[A-Za-z0-9_.-]+:[A-Za-z0-9_./-]+", url):
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme in ("https", "ssh") and parsed.hostname and parsed.path and not parsed.password and not parsed.query and not parsed.fragment
        valid = valid and not (parsed.scheme == "https" and parsed.username)
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise SystemExit("Repo dùng HTTPS không nhúng token/password, hoặc SSH")
PY
git check-ref-format "refs/heads/$branch" >/dev/null || { echo 'Tên nhánh không hợp lệ.' >&2; exit 1; }
work_dir="$(mktemp -d /tmp/merasys-agent-install.XXXXXX)"
cleanup() {
    case "$work_dir" in /tmp/merasys-agent-install.*) rm -rf -- "$work_dir" ;; esac
}
trap cleanup EXIT
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=15' \
    git -c core.autocrlf=false clone --depth=1 --single-branch --branch "$branch" -- "$repo_url" "$work_dir/repo"
agent_dir="$work_dir/repo/merasys-agent"
for name in install.sh monitor-agent.py merasys-agent.service git-update.sh; do
    [[ -f "$agent_dir/$name" ]] || { echo "Repo thiếu merasys-agent/$name" >&2; exit 1; }
done
[[ ! -e "$agent_dir/.env" ]] || { echo 'Repo chứa .env thật; bỏ cấu hình riêng khỏi repo trước khi bootstrap.' >&2; exit 1; }
bash "$agent_dir/install.sh"
bash "$agent_dir/git-update.sh" --setup "$repo_url" "$branch" merasys-agent
echo 'Đã cài Merasys agent và cấu hình updater.'
echo 'Cập nhật lần sau: sudo merasys-agent-update'
