#!/usr/bin/env bash
# One-time setup: sudo bash git-update.sh --setup REPO_URL [BRANCH] [AGENT_SUBDIR]
# Updates: sudo merasys-agent-update
set -euo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo 'Chạy bằng sudo.' >&2; exit 1; }
for dependency in git flock systemctl install mktemp cmp; do
    command -v "$dependency" >/dev/null 2>&1 || { echo "Thiếu lệnh: $dependency" >&2; exit 1; }
done
[[ -x /usr/bin/python3 ]] || { echo 'Cần /usr/bin/python3.' >&2; exit 1; }
[[ -f /etc/merasys-agent/agent.env && -f /opt/merasys-agent/monitor-agent.py ]] || {
    echo 'Cần cài agent trước bằng install.sh.' >&2; exit 1;
}
exec 9>/run/lock/merasys-agent-update.lock
flock -n 9 || { echo 'Đang có lần cập nhật khác chạy.' >&2; exit 1; }
config_path=/etc/merasys-agent/git-update.json
cache_dir=/var/lib/merasys-agent-updater
git_dir="$cache_dir/repo.git"
installed=/opt/merasys-agent/monitor-agent.py

validate_source() {
    /usr/bin/python3 - "$repo_url" "$branch" "$subdir" <<'PY'
import re, sys
from urllib.parse import urlsplit
url, branch, subdir = sys.argv[1:]
if any(any(ord(c) < 32 for c in value) for value in (url, branch, subdir)):
    raise SystemExit("Cấu hình Git chứa ký tự điều khiển")
if re.fullmatch(r"git@[A-Za-z0-9_.-]+:[A-Za-z0-9_./-]+", url):
    pass
else:
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme in ("https", "ssh") and parsed.hostname and parsed.path and not parsed.password and not parsed.query and not parsed.fragment
        valid = valid and not (parsed.scheme == "https" and parsed.username)
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise SystemExit("Repo phải dùng HTTPS không nhúng credentials, hoặc SSH (git@host:org/repo.git)")
if not re.fullmatch(r"[A-Za-z0-9_./-]+", subdir) or subdir.startswith("/") or ".." in subdir.split("/"):
    raise SystemExit("AGENT_SUBDIR phải là đường dẫn tương đối trong repo, hoặc . cho repo riêng agent")
PY
    git check-ref-format "refs/heads/$branch" >/dev/null || { echo 'Tên nhánh Git không hợp lệ.' >&2; exit 1; }
}

if [[ "${1:-}" == --setup ]]; then
    [[ "$#" -ge 2 && "$#" -le 4 ]] || { echo 'Dùng: sudo bash git-update.sh --setup REPO_URL [BRANCH] [AGENT_SUBDIR]' >&2; exit 1; }
    repo_url="$2"
    branch="${3:-main}"
    subdir="${4:-merasys-agent}"
    validate_source
    script_path="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/$(basename -- "${BASH_SOURCE[0]}")"
    install -d -m 0755 /usr/local/sbin
    if [[ "$script_path" != /usr/local/sbin/merasys-agent-update ]]; then
        install -m 0755 "$script_path" /usr/local/sbin/merasys-agent-update
    fi
    /usr/bin/python3 - "$config_path" "$repo_url" "$branch" "$subdir" <<'PY'
import json, os, sys
path, url, branch, subdir = sys.argv[1:]
temporary = path + ".new"
with open(temporary, "w", encoding="utf-8") as stream:
    json.dump({"repo": url, "branch": branch, "subdir": subdir}, stream)
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY
    echo 'Đã lưu cấu hình. Chạy: sudo merasys-agent-update'
    echo 'Setup không tải code hoặc thay đổi agent đang chạy.'
    exit 0
fi
[[ "$#" == 0 ]] || { echo 'Chạy không có tham số để update; dùng --setup để đổi repo/nhánh.' >&2; exit 1; }
[[ -f "$config_path" ]] || { echo 'Chưa cấu hình Git. Chạy git-update.sh --setup trước.' >&2; exit 1; }
configuration="$(/usr/bin/python3 - "$config_path" <<'PY'
import json, sys
from pathlib import Path
config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in ("repo", "branch", "subdir"):
    value = config.get(key)
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise SystemExit("Cấu hình git-update.json không hợp lệ")
    print(value)
PY
)"
mapfile -t values <<< "$configuration"
repo_url="${values[0]}"
branch="${values[1]}"
subdir="${values[2]}"
validate_source
install -d -m 0700 "$cache_dir"
if [[ ! -d "$git_dir" ]]; then
    git init --bare "$git_dir" >/dev/null
fi
# Fetch only the selected branch; SSH authentication must already be available to root.
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes' \
    git --git-dir="$git_dir" fetch --depth=1 --no-tags "$repo_url" "+refs/heads/$branch:refs/merasys/agent"
commit="$(git --git-dir="$git_dir" rev-parse refs/merasys/agent)"
if [[ "$subdir" == . ]]; then subdir=""; fi
while [[ "$subdir" == ./* ]]; do subdir="${subdir#./}"; done
subdir="${subdir%/}"
agent_path="${subdir:+$subdir/}monitor-agent.py"
candidate="$(mktemp /opt/merasys-agent/.monitor-agent-update.XXXXXX)"
trap 'rm -f -- "$candidate"' EXIT
git --git-dir="$git_dir" show "$commit:$agent_path" > "$candidate"
# Parse syntax without executing downloaded code before installation.
/usr/bin/python3 - "$candidate" <<'PY'
import ast, sys
from pathlib import Path
path = Path(sys.argv[1])
if not 0 < path.stat().st_size <= 1_000_000:
    raise SystemExit("File agent rỗng hoặc lớn quá giới hạn")
ast.parse(path.read_text(encoding="utf-8-sig"), filename="monitor-agent.py")
PY
if cmp -s "$candidate" "$installed"; then
    printf 'Agent đã là bản mới nhất của nhánh %s (%s); không restart.\n' "$branch" "${commit:0:12}"
    exit 0
fi
install -m 0644 "$installed" "$installed.previous"
chmod 0644 "$candidate"
mv -f -- "$candidate" "$installed"
if systemctl restart merasys-agent; then
    sleep 2
    if systemctl is-active --quiet merasys-agent; then
        printf '%s\n' "$commit" > "$cache_dir/installed-commit"
        printf 'Đã cập nhật agent: %s. Giữ nguyên env/token và systemd unit.\n' "${commit:0:12}"
        exit 0
    fi
fi
echo 'Agent không khởi động được; khôi phục code trước.' >&2
install -m 0644 "$installed.previous" "$candidate"
mv -f -- "$candidate" "$installed"
systemctl restart merasys-agent || true
echo 'Xem lỗi: sudo journalctl -u merasys-agent -n 50 --no-pager' >&2
exit 1
