# PostgreSQL độc lập bằng Docker Compose

Bộ triển khai DB này độc lập với `merasys-core` (ứng dụng merasys). Hai bên chỉ liên kết qua `DATABASE_URL`. Collector, alert worker và web chạy bằng bộ core riêng trên máy 109 (Docker Compose). Có thể chuyển riêng thư mục này sang máy DB mới.

## Chạy DB trên 109

Yêu cầu Docker Engine và Compose plugin đã được cài trên Linux. Chuyển nội dung thư mục `merasys-postgres-db` vào `/opt/postgres-db`. Thư mục này có thể đặt trên máy 109 hoặc máy DB khác, không cần mã nguồn hay Python của ứng dụng.

```bash
cd /opt/postgres-db
sudo cp .env.example .env
sudo chmod 0600 .env
sudo nano .env
sudo docker compose config --quiet
sudo docker compose up -d
sudo docker compose ps
```

Thay `POSTGRES_PASSWORD` bằng mật khẩu mạnh trước khi chạy. Ví dụ tạo mật khẩu không cần URL-encode bằng `python3 -c 'import secrets; print(secrets.token_hex(24))'`. Không chia sẻ hoặc commit `.env`.

Trong `.env` của thư mục `merasys-core` (file riêng với `.env` của DB):

```text
DATABASE_URL=postgresql+psycopg://monitor:MAT_KHAU_DA_DAT@127.0.0.1:5432/monitor
```

Mật khẩu chứa ký tự đặc biệt trong URL cần URL-encode. Nếu 109 đã có PostgreSQL chiếm cổng 5432, đặt `POSTGRES_PORT=5433` trong DB `.env` và sửa cổng trong `DATABASE_URL` tương ứng. Không chạy đồng thời DB Compose và DB native trên cùng cổng.

Tiếp tục các bước khởi động core bằng Compose trong README chính. Service ứng dụng sẽ thử lại khi DB chưa sẵn sàng; trước khi bật dịch vụ lần đầu, chờ DB healthy và chạy `init-db` thành công.

Dữ liệu lưu trực tiếp trên host bằng **bind mount**, mặc định tại `/opt/postgres-db/data` (thư mục `data` cạnh `compose.yaml`), không dùng Docker named volume. Có thể đổi `POSTGRES_DATA_DIR` trong `.env` sang đường dẫn tuyệt đối, ví dụ `/data/merasys/postgres`. Docker tự tạo thư mục nếu chưa có; PostgreSQL quản lý quyền sở hữu bên trong, không cần chmod 777.

Recreate container hoặc `docker compose down` không xóa thư mục dữ liệu này. Đổi `POSTGRES_DATA_DIR` không tự chuyển dữ liệu cũ. Nếu đã chạy cấu hình named volume trước đó, dump DB trước khi đổi mount, rồi restore vào DB mới theo hướng dẫn dưới; không xóa volume cũ trước khi xác nhận dữ liệu đã chuyển đủ.

`POSTGRES_USER` của official image được tạo là superuser để khởi tạo DB. Bản đầu dùng tài khoản này cho ứng dụng; có thể tách tài khoản ứng dụng quyền hạn hẹp hơn theo chính sách vận hành. Đổi biến mật khẩu trong `.env` không đổi mật khẩu của DB đã có dữ liệu; cần đổi bằng PostgreSQL rồi cập nhật cả ứng dụng và `.env`.

## Sao lưu

Chạy từ thư mục Compose, với quyền quản trị Docker:

```bash
umask 077
sudo docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > monitor.dump
test -s monitor.dump
```

Kiểm tra lệnh dump thành công trước khi coi file là backup. Sao lưu chứa dữ liệu dự án, cấu hình và thông báo; lưu nơi có quyền truy cập phù hợp. Không đưa backup vào thư mục mã nguồn để chia sẻ. Không copy trực tiếp thư mục `data` khi PostgreSQL đang chạy để coi là bản backup nhất quán; ưu tiên dump/restore.

## Chuyển DB sang máy khác

1. Dừng collector, alerts và web trên 109 để tránh ghi trong lúc cutover.
2. Dump DB bằng lệnh trên và chuyển backup an toàn sang máy mới.
3. Chuyển bộ cấu hình `merasys-postgres-db` (không copy dữ liệu đang chạy), tạo `.env`, chọn thư mục `POSTGRES_DATA_DIR` mới/rỗng, dùng cùng PostgreSQL major 17 rồi chạy `docker compose up -d`; chờ healthy. DB đích phải mới/rỗng trước khi restore, chưa chạy `init-db` trên đó.
4. Restore từ thư mục Compose trên máy mới:

```bash
sudo docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error' < monitor.dump
```

5. Để 109 kết nối DB từ xa, đặt `POSTGRES_BIND_IP` thành IP mạng riêng của máy DB mới rồi chạy lại `docker compose up -d`. Chỉ cho phép IP máy 109 truy cập cổng DB bằng firewall phù hợp Docker; ưu tiên mạng riêng/VPN hoặc cấu hình TLS. Compose này chưa cấu hình TLS PostgreSQL.
6. Sửa host/cổng/mật khẩu trong `DATABASE_URL` trên 109, bật lại Compose core để tự áp dụng schema trước API/worker.
7. Kiểm tra dữ liệu dashboard, collector, Sheet và Telegram trước khi ngừng DB cũ. Không bật hai bộ collector/worker cùng lúc.

Chuyển DB và dịch vụ cảnh báo ra ngoài 109 là hai thao tác riêng. Chỉ chuyển DB chưa giải quyết việc máy 109 chết thì worker cũng chết.

## Nâng phiên bản

`postgres:17` giữ cùng major để tránh tự nâng major ngoài ý muốn. Nâng patch theo quy trình backup/kiểm thử của đơn vị. Không đổi thẳng sang major khác rồi dùng lại thư mục dữ liệu; cần dump/restore hoặc quy trình pg_upgrade phù hợp. Đường dẫn mount trong container của cấu hình này dành cho official image PostgreSQL 17.
