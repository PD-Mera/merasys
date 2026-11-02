# Cập nhật agent từ Git bằng một lệnh

Sau khi cấu hình một lần trên mỗi server:

```bash
sudo merasys-agent-update
```

Hỗ trợ GitHub, GitLab hoặc Git nội bộ qua HTTPS/SSH. Không cần Docker trên server agent. Không tự tạo repo, commit, push code hoặc cấu hình deploy key trên tài khoản của người dùng.

## Đưa code lên repo

Dùng một repo chung chứa merasys-core, merasys-agent và merasys-postgres-db. File agent nằm ở merasys-agent/monitor-agent.py. Chỉ commit code, tài liệu và mẫu cấu hình; không commit .env, agent.env, config.json thật, token hoặc private key. Xem `merasys-core/PUBLISH.md`; gitignore không tự xóa secrets đã được Git track từ trước.

Quy trình sau này: sửa agent trên máy phát triển → commit/push vào nhánh đã chọn → chạy lệnh update trên từng server. Server không tự cập nhật khi push, không cần webhook hoặc timer.

## Setup một lần trên từng server đã cài agent

1. Agent phải được cài theo đường dẫn chuẩn: /opt/merasys-agent/monitor-agent.py, env /etc/merasys-agent/agent.env, unit merasys-agent. Server cần Bash, Git, Python3, systemd và flock. Với Ubuntu/Debian chưa có Git: `sudo apt-get install git`.
2. Upload file **git-update.sh** vào server, không cần upload toàn bộ repo cho bước setup.
3. Thay URL và nhánh bằng repo thực tế rồi chạy:

Repo chung, file nằm trong merasys-agent/:

```bash
sudo bash git-update.sh --setup https://github.com/PD-Mera/merasys.git main merasys-agent
sudo merasys-agent-update
```

Repo private qua SSH, ví dụ GitLab nội bộ:

```bash
sudo bash git-update.sh --setup git@gitlab.example.com:team/merasys.git main merasys-agent
sudo merasys-agent-update
```

Vì updater chạy sudo/root, tài khoản root trên server phải có SSH key được repo cho phép đọc và host key Git đã được xác nhận trong known_hosts. Dùng deploy key chỉ đọc nếu phù hợp; không bật quyền ghi khi server chỉ tải code. GitHub hướng dẫn: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys. Có thể dùng HTTPS với credential helper đã cấu hình cho root, nhưng không nhúng PAT/password vào repo URL hoặc gửi token trong chat. Updater tắt terminal prompt; thiếu quyền Git thì dừng, giữ nguyên agent hiện tại.

Setup chỉ cài /usr/local/sbin/merasys-agent-update và ghi /etc/merasys-agent/git-update.json (root-only); không đổi env/token hoặc service đang chạy. Nếu Bash báo lỗi pipefail do CRLF: `sed -i 's/\r$//' git-update.sh` rồi chạy lại setup. Nếu sudo không tìm thấy lệnh qua PATH, dùng `sudo /usr/local/sbin/merasys-agent-update`.

## Cách updater hoạt động

- Khóa để tránh hai lần cập nhật chạy cùng lúc.
- Fetch nhánh đã chọn về bare cache /var/lib/merasys-agent-updater/repo.git. Không git pull/reset/clean vào thư mục agent hoặc cấu hình thật. Git fetch/refspec: https://git-scm.com/docs/git-fetch.
- Chỉ lấy monitor-agent.py từ commit vừa fetch. Không thực thi install.sh/update.sh trong repo và không lấy .env, unit, secrets hoặc file core.
- Kiểm tra cú pháp bằng Python cài trên server trước khi thay file. Không thực thi candidate trong bước kiểm tra cú pháp. Đây không phải xác nhận logic hoạt động hoặc tương thích API/core.
- Code không đổi thì không restart. Code thay đổi thì lưu một backup monitor-agent.py.previous, thay file bằng rename trong cùng thư mục, restart và kiểm tra service sau 2 giây.
- Nếu restart thất bại hoặc service không active ở bước kiểm tra này, phục hồi backup rồi restart lại. Service có thể gặp lỗi muộn hơn bước kiểm tra 2 giây; vẫn cần theo dõi report được core chấp nhận.
- Giữ nguyên agent.env, token, IP, URL, report interval và systemd unit. Khi nâng cấp có thay đổi API/schema cần cập nhật core trước theo hướng dẫn của bản đó; lệnh agent không tự nâng cấp core.
- File cập nhật hiện chỉ có monitor-agent.py. Nếu sau này agent tách thành nhiều module/thay unit hoặc dependencies thì cần nâng cấp cơ chế updater tương ứng.

Xem log sau cập nhật:

```bash
sudo journalctl -u merasys-agent -n 30 --no-pager
```

Đổi repo/nhánh/thư mục: chạy lại --setup với thông tin mới, rồi lệnh update. Không cần cài lại agent hoặc thay token. Nhánh quy định code được triển khai, nên chỉ push phiên bản muốn đưa lên các server vào nhánh đó.

Không chạy script, test, git fetch hoặc kết nối các server thật trên máy phát triển theo yêu cầu người dùng; các lệnh trên để người dùng thực hiện trên server Linux.
