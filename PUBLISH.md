# Một repo chung cho toàn hệ thống

Triển khai mới sau khi push: [FRESH-INSTALL.md](FRESH-INSTALL.md). Repo có bootstrap.sh trong merasys-agent để cài agent qua một dòng bash.

Repo chứa core, agent và PostgreSQL trong cùng một cây thư mục:

```text
merasys/
  merasys-core/
  merasys-agent/
  merasys-postgres-db/
  monitor/                     # bản source gốc
  config/
  tests/                       # source tests, không chạy trong bước chuẩn bị
  README.md
  PUBLISH.md
  ...các file triển khai/tài liệu ở gốc
```

Repo được khởi tạo trực tiếp tại gốc dự án merasys. Không có bộ source trung gian. .gitignore loại env thật, secrets, state, dữ liệu PostgreSQL và cache; .gitattributes chuẩn hóa LF cho Linux.

Remote dùng https://github.com/PD-Mera/merasys.git. Chạy các lệnh Git tại **gốc dự án merasys**:

```bash
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Prepare Merasys monitoring system"
git remote add origin https://github.com/PD-Mera/merasys.git
git push -u origin main
```

Nếu .git/remote đã tồn tại thì commit/push bình thường, không init hoặc add remote lần nữa. Cần Git user.name/user.email của bạn để commit. Không commit cấu hình thật/password/token/private key. Gitignore không tự gỡ secrets đã được track từ trước.

## Cập nhật agent từ repo chung

Trên mỗi server đã cài agent, upload git-update.sh và cấu hình một lần:

```bash
sudo bash git-update.sh --setup https://github.com/PD-Mera/merasys.git main merasys-agent
sudo merasys-agent-update
```

**AGENT_SUBDIR là merasys-agent, không phải dấu chấm.** Nếu trước đó đã setup repo riêng, chạy lại --setup với repo chung và thư mục này. Lệnh update chỉ lấy file merasys-agent/monitor-agent.py; không chép core, DB, env/token hoặc unit vào máy agent. Repo private cần quyền đọc Git cho root như merasys-agent/GIT-UPDATE.md.

## Core và DB

Core vẫn triển khai từ merasys-core; DB từ merasys-postgres-db, độc lập dữ liệu. Không chạy nhầm compose.yaml ở gốc khi đang làm theo hướng dẫn của một bộ triển khai. Đổi code core thì mount code/restart theo hướng dẫn từng thay đổi; migrate DB khi có yêu cầu init-db. Lệnh update agent không tự cập nhật core hoặc DB.

Sửa và commit trực tiếp tại repo gốc. Không cần chép lại code sang folder khác trước khi commit.

Nếu đang chạy bản tên cũ trên server, xem [MIGRATE-MERASYS.md](MIGRATE-MERASYS.md) trước khi triển khai tên mới để giữ env, token, dữ liệu và tránh chạy hai agent.
