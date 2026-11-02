# Cài mới Merasys

Một repo chung gồm merasys-postgres-db, merasys-core và merasys-agent. Cấu hình core qua web; chỉ WEB_HOST/WEB_PORT ở env. Chi tiết tài khoản/phiên/cấu hình: [WEB-CONFIG.md](WEB-CONFIG.md).

## 1. PostgreSQL trên 109

Clone repo đã push về server. Trong merasys-postgres-db:

```bash
cp .env.example .env
chmod 600 .env
nano .env
sudo docker compose up -d
sudo docker compose ps
```

Đặt POSTGRES_PASSWORD thật, giữ POSTGRES_DB=monitor/POSTGRES_USER=monitor nếu không có yêu cầu khác. Data mặc định ./data, không xóa. Bộ DB là hạ tầng độc lập và vẫn cần cấu hình khởi tạo riêng; yêu cầu env hai dòng áp dụng cho core. Có thể dùng PostgreSQL sẵn có thay vì bộ này.

## 2. Khởi động core

Trong merasys-core:

```bash
cp .env.example .env
sudo docker compose up -d --build
```

Env mẫu chỉ có:

```dotenv
WEB_HOST=0.0.0.0
WEB_PORT=21707
```

Mở http://IP_109:21707. Khi chưa có tài khoản, tạo tài khoản quản trị đầu tiên (mật khẩu tối thiểu 12 ký tự). Từ lần sau chỉ hiện đăng nhập, không cho tạo tài khoản thứ hai. Không còn Basic Auth/dashboard token.

Web vẫn mở được khi chưa cấu hình hoặc DB đang lỗi. Worker chờ cấu hình, không phải chạy init-db trước. Dữ liệu tài khoản/cấu hình bootstrap nằm trong state/ cạnh compose.yaml; dữ liệu giám sát vẫn ở PostgreSQL.

## 3. Cấu hình trên web

Mở Cấu hình, điền và lưu:

1. Database URL: postgresql+psycopg://monitor:PASSWORD@127.0.0.1:5432/monitor (password trùng DB; URL-encode ký tự đặc biệt). Lần đầu lưu sẽ kiểm tra kết nối và tạo/nâng cấp bảng.
2. Google Sheet ID, tab Monitoring, JSON service account có quyền đọc spreadsheet (chọn file JSON trên giao diện).
3. Telegram bot token/chat ID và thread ID nếu dùng forum topic.
4. Chu kỳ/ngưỡng/múi giờ nếu muốn đổi mặc định.

Tạo tab Monitoring theo config/sheet-template.csv; TelegramUsers theo mẫu (có thể chỉ giữ header). RabbitMQConnections chỉ cần khi có Type=rabbitmq. Dùng Đồng bộ Sheet ngay để xác nhận cấu hình hợp lệ.

Trong Token agent theo IP nhập IP của từng máy, nhấn Tạo/đổi token, sao chép token hiện một lần. Dòng server/compose trên Sheet cần đúng IP và đang bật. Không cần tạo agent-tokens.json hoặc folder secrets trong core.

## 4. Cài agent một dòng

Sau khi push code lên GitHub public, chạy trên từng server (thay ORG/repo/branch):

```bash
curl -fsSL https://raw.githubusercontent.com/PD-Mera/merasys/main/merasys-agent/bootstrap.sh | sudo bash -s -- https://github.com/PD-Mera/merasys.git main
```

Máy cần Linux/systemd, sudo và curl; bootstrap cài Git/Python3/flock còn thiếu bằng apt/dnf/yum. Nhập URL core (ví dụ http://10.0.2.109:21707), IP và token đã tạo trên web. Token nhập được che, không đặt trong URL/lệnh shell. Cần terminal tương tác.

Repo private: upload bootstrap.sh rồi `sudo bash bootstrap.sh REPO_URL main` với quyền đọc Git cho root đã có. Raw URL public không tải được repo private; xem merasys-agent/GIT-UPDATE.md. Không tự đổi quyền truy cập Git của người dùng.

```bash
sudo systemctl status merasys-agent --no-pager
sudo journalctl -u merasys-agent -n 30 --no-pager
```

Cập nhật sau này: commit/push code rồi `sudo merasys-agent-update`. Không cần đổi agent chỉ vì đổi giao diện đăng nhập/cấu hình của core; token agent cũ vẫn dùng được khi được nhập lại trên web.

## 5. Kiểm tra

Dashboard sẽ có dữ liệu sau các vòng report. Có thể dùng Thử cảnh báo → Kiểm tra kết quả để xác nhận Telegram đã nhận, không chỉ tin đã được xếp hàng. Nếu Telegram có lỗi DNS/ConnectionError, cần xử lý mạng từ core tới Telegram.

Server config giám sát dung lượng GB, Queue config cho ngưỡng RabbitMQ vẫn khai báo trên Sheet như các hướng dẫn tương ứng. Những cấu hình trước đây ở .env được thay bằng web; tham chiếu .env/secrets/dashboard token trong tài liệu nâng cấp cũ đã được thay thế bởi WEB-CONFIG.md.

Sao lưu state/ (khi core đã dừng để sao chép nhất quán) cùng PostgreSQL. Không commit state, env, data hoặc secret lên Git. HTTP chỉ dùng trong mạng riêng tin cậy/VPN; có thể đặt HTTPS reverse proxy. Chưa chạy test/build/cài gói hoặc gọi server thật trên máy phát triển.
