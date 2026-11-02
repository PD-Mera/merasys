# Core Docker — cấu hình bằng giao diện

Đọc [FRESH-INSTALL.md](FRESH-INSTALL.md) cho cài mới và [WEB-CONFIG.md](WEB-CONFIG.md) cho nâng cấp từ env/dashboard token. Agent chạy systemd riêng; DB PostgreSQL độc lập.

Folder core cần monitor/, Dockerfile, pyproject.toml, compose.yaml, .env. Source code mount read-only; state/ mount writable và chứa tài khoản, cookie session hashes, cấu hình bootstrap. Không cần secrets/ trong cấu hình mới.

```bash
cd merasys-core
cp .env.example .env
sudo docker compose up -d --build
```

Env chỉ gồm:

```dotenv
WEB_HOST=0.0.0.0
WEB_PORT=21707
```

Mở http://IP_SERVER:21707. Lần đầu đăng ký tài khoản duy nhất; sau đó đăng nhập. Cấu hình PostgreSQL, Google Sheet/key, Telegram/topic, token agent, chu kỳ/ngưỡng/múi giờ trên Cấu hình. Không dùng DASHBOARD_TOKEN hoặc Basic Auth. Web không phụ thuộc DB khi khởi động.

Khi lưu Database URL lần đầu hoặc đổi DB, core kiểm tra kết nối và init/nâng schema trước khi áp dụng. Đổi DB không tự chuyển dữ liệu. Các worker tự nạp cấu hình mới, không cần restart. Postgres mặc định localhost:5432 hoạt động qua host networking Linux; có thể đổi DB sang server khác bằng web.

Vận hành:

```bash
sudo docker compose ps
sudo docker compose logs --tail=50 web collector alerts rabbitmq-checker
# Sau sửa code:
sudo docker compose restart web collector alerts rabbitmq-checker prune
# Sau đổi WEB_HOST/WEB_PORT hoặc compose mounts:
sudo docker compose up -d --force-recreate
# Sau đổi thư viện/Dockerfile:
sudo docker compose up -d --build --force-recreate
# Đồng bộ chủ động, dùng cấu hình đã lưu trên web:
sudo docker compose run --rm --no-deps collector sync-once
# Reset password tương tác, giữ cấu hình và username:
sudo docker compose run --rm --no-deps web reset-password
```

init-db là công cụ thủ công (profile tools), không chặn web. Nếu DB đã cấu hình có thể chạy `sudo docker compose run --rm --no-deps init-db`; nếu chưa có DB URL, lệnh báo mở web để thiết lập và thoát. Worker chờ khi chưa có cấu hình.

Không xóa state/ khi recreate hoặc chuyển server. Sao lưu state lúc core dừng và sao lưu PostgreSQL riêng. Khi chuyển từ bản cũ cần mang .env/secrets cũ để nhập lại các giá trị qua UI, không tự xóa dữ liệu/đổi token agent. Không chạy nhiều core song song trên cùng DB.
