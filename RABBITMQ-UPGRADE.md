# RabbitMQ queue monitor từ core

> Bản hiện tại dùng [WEB-CONFIG.md](WEB-CONFIG.md): DB URL, chu kỳ quét và các tham số core đặt trên web, không nhập runtime settings vào env nữa. Queue config và RabbitMQConnections vẫn ở Sheet như bên dưới.

Agent không thay đổi. Worker `rabbitmq-checker` thuộc compose core gọi Management API, ghi kết quả và lịch sử vào PostgreSQL. Worker alerts đọc DB để cảnh báo như Compose. Không publish, consume, lấy message hoặc sửa queue.

## Khai báo

Sắp xếp tab monitor theo đúng thứ tự mới; chuyển cả cột dữ liệu theo tiêu đề, không chỉ đổi tên ô header:

```text
Bật giám sát | Dự án | Tên dịch vụ | IP server | Type | Người phụ trách | Tên compose | Tên queue | RabbitMQ connection | Queue config | Note
```

Type có `server`, `compose`, `rabbitmq`. Với server/compose, để trống Tên queue, RabbitMQ connection, Queue config. Có 11 cột, riêng Note ở cuối có thể bỏ. Xóa cột RabbitMQ username, Tên service cũ và Tên container nếu đang giữ. Sheet theo thứ tự cũ sẽ bị từ chối và giữ nguyên cấu hình DB đến khi sửa đúng.

| Bật giám sát | Dự án | Tên dịch vụ | IP server | Type | Người phụ trách | Tên compose | Tên queue | RabbitMQ connection | Queue config | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| TRUE | SocialBeat | Queue nhận video | 10.9.3.250 | rabbitmq | dong.trinh1 | | video_queue | rabbit-prod | {"min_consumers":1,"alert_threshold":1000} | Phục vụ Leader Detection |

- IP server là IP broker để hiển thị; địa chỉ gọi thực tế lấy từ Management URL của connection. Cần điền nhất quán hai chỗ.
- Dự án, Tên dịch vụ, Người phụ trách nhiều lựa chọn và Note hoạt động như các dòng khác. Queue không liên kết hoặc kế thừa dữ liệu Compose.
- Một dòng là một queue qua một connection. Định danh gồm IP + connection + queue. Nếu cần cùng queue với nhiều tài khoản thì tạo connection tên khác nhau, rồi khai báo các dòng queue tham chiếu các connection đó.
- Username/Password chỉ nằm trong tab RabbitMQConnections, không lấy từ dòng monitor hoặc hiển thị trong entry queue. Số liệu consumers/messages là của cả queue, không lọc theo user.
- Queue config là JSON object, ví dụ `{"min_consumers":1,"alert_threshold":1000}`. Cột này thay Min consumers ở cùng vị trí; giá trị số cũ như `1` phải chuyển thành `{"min_consumers":1}`. Chỉ hai khóa này được chấp nhận, sai JSON/khóa/kiểu số sẽ từ chối toàn bộ lần đồng bộ và giữ cấu hình trước đó.
- `min_consumers`: số nguyên từ 0 đến 999999, mặc định 0. Đặt 1 hoặc số mong muốn nếu ứng dụng dùng consumer thường trực. Consumer polling/batch có thể hợp lệ với 0 consumers.
- `alert_threshold`: số message đang chờ (`messages_ready`), không gồm `messages_unacknowledged`. Số nguyên dương tối đa 1000000000000. Khi ready đạt hoặc vượt ngưỡng, mẫu kiểm tra là DOWN với lý do vượt ngưỡng, không có nghĩa broker chết. Bỏ khóa hoặc đặt null để tắt; không dùng 0 để tắt.
- Để ô trống hoặc `{}`: mặc định min_consumers=0 và không giới hạn message chờ. Ví dụ `{"alert_threshold":500}` chỉ kiểm tra backlog; `{"min_consumers":1}` chỉ kiểm tra consumer. Cảnh báo vẫn chờ FAILURE_THRESHOLD lần lỗi liên tiếp chung của hệ thống; RECOVERY_THRESHOLD lần UP để phục hồi. Thay config giữ ID queue và lịch sử, đặt lại các bộ đếm xác nhận.
- Không có message hoặc không có traffic vẫn có thể UP; chưa kiểm tra rate/tuổi message và chưa chứng minh ứng dụng xử lý message thành công.
- Không tự sinh server heartbeat cho IP chỉ khai báo RabbitMQ; không cần agent trên broker.

Tạo tab **RabbitMQConnections** trong cùng spreadsheet, đúng 5 cột:

| Connection | Management URL | Username | Password | Vhost |
|---|---|---|---|---|
| rabbit-prod | http://10.9.3.250:15672 | monitor_user | mật khẩu thật | / |
| rabbit-prod-other | http://10.9.3.250:15672 | other_user | mật khẩu khác | / |

Tab monitor chỉ tra theo Connection; mỗi tên Connection phải tương ứng duy nhất một bộ URL/Username/Password/Vhost. Một broker nhiều vhost hoặc tài khoản thì dùng tên Connection khác nhau. Management URL chỉ gồm http(s)://host:port, không nhúng tài khoản hoặc path. API encode vhost/queue khi gọi. Tài khoản cần đăng nhập được Management API và xem được queue/vhost. Management plugin phải bật và mạng từ core đến API phải thông. Dùng HTTPS nếu có; code giữ xác minh chứng chỉ mặc định, không bỏ qua TLS.

Nâng cấp từ bản khai báo username: nếu chỉ có một target cũ khớp IP + Connection + queue thì giữ ID và lịch sử khi chuyển định danh. Nếu trước đó có nhiều target cùng IP/Connection/queue theo nhiều username, cần tách Connection thành tên khác nhau; lịch sử các target cũ vẫn giữ khi chúng bị tắt, không tự gộp lịch sử khác nhau.

Password được giữ nguyên ký tự, không strip; nên định dạng cột là Văn bản thuần túy. Mật khẩu nằm trong Sheet và DB, không trả về dashboard/API và không log URL/response body/credentials; DB engine ẩn tham số SQL khi báo lỗi. Người được quyền xem Sheet hoặc truy cập DB vẫn có thể đọc mật khẩu. Dùng tài khoản riêng cho giám sát, không dùng tài khoản quản trị khi không cần thiết.

Tab TelegramUsers vẫn giữ như hiện tại. Cả ba tab được kiểm tra trước khi áp dụng trong cùng transaction. Sai dòng, thiếu mapping hoặc lỗi đọc không áp dụng thay đổi. RabbitMQConnections có thể chưa tồn tại khi không có dòng rabbitmq; có dòng rabbitmq thì bắt buộc có connection khớp, kể cả dòng FALSE. Header-only xóa các connection khi không còn khai báo queue tham chiếu. Xóa dòng queue hoặc FALSE rồi sync thành công sẽ dừng kiểm tra/cảnh báo, giữ lịch sử theo cơ chế hiện tại.

## Trạng thái và chu kỳ

- UP: API đọc được queue, đủ số consumer tối thiểu; empty queue vẫn bình thường.
- DOWN: HTTP 404 (không tìm thấy trong phạm vi user/vhost), queue báo down/crashed/stopped, thiếu consumer hoặc messages_ready đạt/vượt alert_threshold đã khai báo.
- UNKNOWN: lỗi DNS/mạng/TLS/timeout, HTTP 401/403, lỗi API hoặc số liệu chưa đủ. Không kết luận broker chết chỉ từ lỗi API.
- Alerts xác nhận DOWN/không kiểm tra được theo FAILURE_THRESHOLD, phục hồi theo RECOVERY_THRESHOLD. Lịch sử UNKNOWN tách biệt downtime.
- Worker mặc định 60 giây mỗi vòng, timeout kết nối 3 giây và đọc 5 giây mỗi queue. Các queue kiểm tra tuần tự; số queue lớn có thể khiến vòng lâu hơn và cần điều chỉnh chu kỳ/ngưỡng stale. Tùy chọn `.env`: `RABBITMQ_POLL_SECONDS=60`. `STALE_AFTER_SECONDS` cần lớn hơn thời gian một vòng; mặc định 180 giây.
- Worker dừng/mất dữ liệu quá hạn sẽ tạo cảnh báo kết quả kiểm tra queue quá hạn. Khi lỗi DB, xem logs rabbitmq-checker; không in raw exception có thể chứa credentials.

## Cập nhật server

1. Sao lưu DB trước nâng cấp. Trong thư mục core, `sudo docker compose down`, rồi upload toàn bộ `monitor/` và `compose.yaml` từ bộ merasys-core. Giữ nguyên `.env` và secrets.
2. Thêm cột/tab, điền kết nối thật. Mẫu CSV ở config/sheet-template.csv và config/rabbitmq-connections-template.csv chỉ để tham khảo/import vào đúng tab.
3. Chạy lần lượt; xử lý lỗi trước khi chạy lệnh tiếp:

```bash
sudo docker compose run --rm --no-deps init-db
sudo docker compose run --rm --no-deps collector sync-once
sudo docker compose up -d --no-build
sudo docker compose logs --tail=50 rabbitmq-checker collector alerts
```

4. Mở dashboard Ctrl+F5. Queue là entry riêng trong nhóm Dịch vụ, có chi tiết connection/vhost, số liệu trong Kết quả và lịch sử uptime/downtime. Có thể có nhiều entry cùng queue nếu chọn nhiều connection, mỗi entry đếm riêng.

Không cần build image vì không thêm thư viện; không sửa agent hoặc triển khai lại PostgreSQL. init-db chỉ thêm bảng rabbitmq_connections và cột targets.rabbitmq, không xóa dữ liệu cũ. Chưa chạy test hoặc gọi RabbitMQ thật trên máy phát triển theo yêu cầu người dùng.

## Số liệu nhỏ cạnh nhãn RabbitMQ Queue

Dashboard hiển thị consumers, tổng message, ready, unacked, Publish/s, Deliver/s và Ack/s cạnh nhãn loại. Deliver/s là `message_stats.deliver_get_details.rate` (gồm deliver/get); Ack/s và Publish/s lấy từ rate RabbitMQ cung cấp. Không tự tính rate từ hai lần quét. Số liệu/rate không có hiện `—`, không giả định bằng 0. Các trường `*_count` cũng được giữ trong snapshot mới nhất khi API cung cấp, không suy ra uptime hoặc tốc độ từ các count này. Tham khảo https://www.rabbitmq.com/docs/monitoring.

Số liệu được ghi vào `targets.rabbitmq_metrics` (JSON), chỉ giữ bản gần nhất; không tạo bảng lịch sử metrics theo từng lần quét. Khi đọc API thất bại, số liệu lần thành công trước vẫn giữ và UI ghi Số liệu cũ. Tắt giám sát, dữ liệu quá hạn hoặc timestamp metrics không khớp lần kiểm tra mới nhất cũng được đánh dấu cũ. Thay cấu hình sẽ xóa snapshot cũ để chờ số liệu mới. Tần suất quét mặc định 60 giây và dashboard làm mới 30 giây; đây không phải luồng dữ liệu liên tục.

Nâng cấp phần này: dừng core trước khi upload `monitor/db.py`, `monitor/rabbitmq.py`, `monitor/sheet.py`, `monitor/web.py`, `monitor/dashboard.html`. Chạy `sudo docker compose run --rm --no-deps init-db` để thêm cột rabbitmq_metrics rồi `sudo docker compose up -d --no-build`. Không cần đổi Sheet hoặc agent; không xóa dữ liệu đang có.
