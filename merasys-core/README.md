# Merasys

**Bản hiện tại: 0.6.0.** core chỉ để WEB_HOST/WEB_PORT trong env. Web tự hiện đăng ký lần đầu, sau đó đăng nhập; chỉ một tài khoản. Các tham số còn lại nhập trên màn Cấu hình, không dùng dashboard token. Xem [WEB-CONFIG.md](WEB-CONFIG.md).

Cài mới từ đầu, gồm agent cài một dòng bash: [FRESH-INSTALL.md](FRESH-INSTALL.md).

Chuyển từ bản tên cũ trên server: [MIGRATE-MERASYS.md](MIGRATE-MERASYS.md). Không đổi database/role/password hoặc xóa data chỉ vì đổi tên sản phẩm.

Toàn hệ thống dùng **một repo Git chung**, giữ nguyên ba folder triển khai bên dưới. Bộ chuẩn bị Git và lệnh push: [PUBLISH.md](PUBLISH.md). Không tạo repo riêng trong folder agent; updater agent dùng AGENT_SUBDIR=merasys-agent.

Ba thư mục triển khai độc lập:

| Thư mục | Đặt ở đâu | Chức năng |
|---|---|---|
| merasys-postgres-db | Máy 109 hoặc máy DB riêng | PostgreSQL, dữ liệu bind mount ra host |
| merasys-core | Máy 109 | API/dashboard, đồng bộ Sheet, cảnh báo Telegram, dọn dữ liệu |
| merasys-agent | Mỗi server cần giám sát | Systemd agent, gửi heartbeat, Docker và trạng thái system service về 109 |

```text
Sheet → core đồng bộ → PostgreSQL ← API core ← agent 239/240/241
                            ↓
                       worker → Telegram
```

Core và DB dùng Docker Compose trên Linux. Agent chạy trực tiếp bằng systemd, cần Python 3 nhưng không cần pip hoặc Docker Compose.

## Thứ tự triển khai

Trước lần đồng bộ đầu tiên, tạo thêm tab **TelegramUsers** trong cùng spreadsheet với hai cột `Người phụ trách | Telegram user ID`. Chi tiết khai báo, mention nhiều người và nâng cấp bản đang chạy: [TELEGRAM-USERS.md](TELEGRAM-USERS.md).

1. Chạy bộ DB theo README của `merasys-postgres-db`, chờ healthy.
2. Chạy core theo [DOCKER-SETUP.md](DOCKER-SETUP.md); env chỉ có WEB_HOST/WEB_PORT. Mở web đăng ký, nhập DB URL, Google key/Sheet, Telegram và token agent trong Cấu hình.
3. Khai báo IP/container/Compose trong Sheet, chờ đồng bộ thành công.
4. Chép bộ agent lên từng máy, chạy `sudo bash install.sh`, nhập URL/IP/token theo hướng dẫn.

Core và DB chạy `sudo docker compose up -d --build` từ thư mục tương ứng; agent chạy `sudo bash install.sh` hoặc bootstrap một dòng. Web không phụ thuộc init-db/PostgreSQL khi boot; lần đầu lưu DB URL trên giao diện sẽ khởi tạo/nâng cấp schema. Chỉ chạy một core cho một DB và một agent trên mỗi server. Sao lưu state/ của core cùng DB. Lịch sử uptime và nâng cấp xem UPTIME-UPGRADE.md.

## Google Sheet — một tab

Tab mặc định `Monitoring`, thứ tự cột mới:

| Bật giám sát | Dự án | Tên dịch vụ | IP server | Type | Người phụ trách | Tên compose | Tên queue | RabbitMQ connection | Queue config | Server config | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TRUE | | Máy chủ 239 | 10.9.3.239 | server | Tuấn | | | | | {"disks":[{"path":"/","min_free_gb":20}]} | Heartbeat |
| TRUE | VisualSense | Tra soát vi phạm truyền hình | 10.9.3.241 | compose | Nghĩa | visual_sense | | | | | Giám sát toàn bộ Compose |

- Type nằm **sau IP server**, nhận server, compose hoặc rabbitmq, bắt buộc trên mọi dòng có dữ liệu kể cả FALSE. Dùng thứ tự 12 cột trên; Server config tùy chọn (Sheet 11 cột cũ vẫn dùng được), Note cuối có thể bỏ. RabbitMQ lấy tài khoản qua Connection duy nhất theo [RABBITMQ-UPGRADE.md](RABBITMQ-UPGRADE.md), không khai báo RabbitMQ username trong tab monitor.
- Giám sát filesystem theo ngưỡng GB còn trống trên dòng server: xem [DISK-UPGRADE.md](DISK-UPGRADE.md) để cập nhật core, agent và khai báo Server config. Không dùng ngưỡng phần trăm hoặc kiểm tra SMART.
- Server: điền IP, để trống Tên compose. Compose: điền IP và đúng Compose project name. Dự án có thể trống hoặc chọn nhiều bằng dropdown; tên dự án không chứa dấu phẩy.
- Tên dịch vụ là tên hiển thị tối đa 200 ký tự, để trống thì dùng tên kỹ thuật. Người phụ trách và Note có thể trống. Người phụ trách hỗ trợ dropdown chọn nhiều, tách bằng dấu phẩy (ví dụ `dong.trinh1, nghia.nguyen1`); tên người phụ trách không chứa dấu phẩy. Trên Google Sheets, chọn cột Người phụ trách → Dữ liệu → Xác thực dữ liệu → Trình đơn thả xuống, bật Cho phép chọn nhiều.
- **Đã bỏ cột Tên container và khai báo container riêng.** Xóa cột này, Tên service cũ và RabbitMQ username khỏi tab monitor. Dùng đúng thứ tự cột mới; Note cuối có thể bỏ.
- Agent vẫn thu thập container và label để kiểm tra từng service/replica **bên trong Compose**. Không khai báo hay cảnh báo container riêng.
- Khai báo container riêng cũ tự tắt sau đồng bộ thành công, không xóa lịch sử. Giữ nguyên IP/Tên compose khi chuyển cột để giữ định danh của Compose hiện tại.
- Dòng trùng IP/Compose được gộp dự án, người phụ trách và ghi chú; trạng thái bật và tên hiển thị phải thống nhất. Có thể không cần dòng server riêng: host có Compose được bật vẫn có mục heartbeat tự động.
- Dòng `server` được để trống Dự án. Dự án và Người phụ trách của server chỉ lấy từ dòng `server` cùng IP; không tổng hợp từ các Compose trên máy đó. Heartbeat tự tạo khi không có dòng `server` hiển thị hai trường này trống. Sau khi cập nhật code, chạy `sync-once` để sửa cả dữ liệu đã lưu trước đây; không cần thay đổi cấu trúc DB.
- Đặt FALSE hoặc xóa dòng để ngừng giám sát. Các mục thiếu khỏi Sheet sẽ tự tắt sau lượt đồng bộ thành công, giữ lịch sử. Header hợp lệ không có dòng dữ liệu sẽ tắt toàn bộ; lỗi tải, sai header hoặc dòng sai giữ cấu hình cũ và báo lỗi.
- IP trong mẫu chỉ là ví dụ. CSV mới ở config/sheet-template.csv để tham khảo, không import ghi đè Sheet đang dùng.

Bật Google Sheets API, tạo service account/JSON key, chia sẻ Sheet cho email tài khoản với quyền Viewer. Không đưa secrets lên Sheet. Đặt JSON key và token agent theo DOCKER-SETUP.md.

## Compose service

Tự khám phá service từ Docker labels project/service và kiểm tra mọi replica tìm thấy. Nhớ tên service trong DB để báo khi service đã thấy mất toàn bộ container; redeploy đổi tên/ID container vẫn theo dõi được. Bỏ qua one-off container từ docker compose run. Một cảnh báo gộp cho mỗi Compose, có chi tiết từng service/container; API có compose_services.

Chưa biết service trong YAML chưa từng tạo, profile chưa bật hoặc số replica mong muốn khi replica đã bị xóa. Job service thường được kỳ vọng chạy liên tục; container cũ đã dừng nhưng chưa xóa vẫn được tính.

Khi chủ động bỏ service, dừng agent của máy tương ứng, từ thư mục core chạy rồi bật lại agent:

```bash
sudo docker compose run --rm collector forget-compose-service --host IP --compose PROJECT --service SERVICE
```

Nếu container còn tồn tại sẽ được tự khám phá lại.

## Trạng thái và cảnh báo

Dashboard có tổng quan, thẻ máy chủ và bảng lọc theo dự án/trạng thái. Chọn máy chủ để lọc dịch vụ; tìm bằng tên, IP, người phụ trách hoặc Note. Chọn đối tượng để mở chi tiết kết quả và các service trong Compose. Dữ liệu cập nhật mỗi 30 giây qua API, giữ nguyên bộ lọc; khi mất API sẽ có thông báo và các kết quả quá hạn chuyển Chưa rõ. Thời gian hiển thị theo DISPLAY_TIMEZONE. Nút Mở khai báo dẫn đến Sheet cấu hình. Giao diện React 19.3/TypeScript 5.9 nằm trong frontend/src/, build bằng Vite 7.3 trên Node 22. Thư mục frontend/dist/ được mount từ host; build lại frontend rồi reload trình duyệt, không cần restart backend. Xem [FRONTEND.md](FRONTEND.md). Không dùng CDN hoặc tải font bên ngoài.

- Agent gửi mỗi 60 giây. Server UP khi nhận heartbeat; quá 180 giây không nhận thì cảnh báo mất liên lạc, không khẳng định máy đã tắt. Cần 2 heartbeat mới sau gián đoạn để phục hồi.
- Container/Compose UP khi running; sau 3 mẫu lỗi liên tiếp thì cảnh báo, sau 2 mẫu tốt thì phục hồi. Bộ đếm theo báo cáo, không theo lượt worker đọc DB.
- Mất heartbeat: dịch vụ UNKNOWN, giữ sự cố cũ nhưng không báo phục hồi giả hoặc DOWN hàng loạt. Docker query lỗi vẫn gửi heartbeat, service UNKNOWN; sau 3 mẫu lỗi cảnh báo không đọc được Docker.
- Worker đọc DB mỗi 15 giây kể cả không có insert mới. Sheet không đồng bộ thành công quá 600 giây cũng cảnh báo. Mặc định không nhắc lại sự cố (ALERT_REMINDER_SECONDS=0); đặt số giây lớn hơn 0 nếu muốn nhắc định kỳ. Env đang chạy phải được đổi riêng; file mẫu không tự thay env cũ.
- Telegram dùng HTML formatting: tiêu đề/nhãn in đậm, IP/tên dịch vụ monospace; tên có dấu gạch dưới hoặc ký tự HTML được escape an toàn. Compose chỉ liệt kê service đang lỗi (tối đa 6, kèm số lỗi/tổng số); chi tiết đầy đủ vẫn trên dashboard. Tin phục hồi không lặp lại inventory DOWN cũ và có thời gian sự cố. Ghi chú dài được rút gọn.
- Telegram dùng outbox trong DB, retry/backoff và xử lý 429. Không tạo thêm tin nhắc nếu cùng sự cố còn tin chưa gửi; tin nhắc chưa gửi được hủy khi tắt nhắc lại hoặc sự cố đã hết. Khi tắt hoặc xóa mục giám sát, worker hủy các tin lỗi/phục hồi/nhắc lại chưa gửi của mục đó, đóng sự cố mà không báo phục hồi giả. Tin đã gửi không thu hồi; lịch sử sự cố và mẫu kiểm tra vẫn được giữ. Có thể lặp tin nếu Telegram đã nhận nhưng phản hồi bị mất. FIFO giữ thứ tự lỗi/phục hồi, có thể gửi tin cũ sau khi mạng phục hồi.
- Dashboard tự làm mới 30 giây, dùng tài khoản/phiên đăng nhập duy nhất; múi giờ đặt trên Cấu hình. /healthz kiểm tra API/DB, /api/status dùng cookie phiên cùng dashboard.

Agent báo toàn bộ inventory nhưng chỉ các mục khai báo mới được cảnh báo. Chưa có cảnh báo RAM/CPU hoặc HTTP ứng dụng. Toàn bộ 109 hoặc DB chết cần watchdog ngoài hệ thống. Agent không chứa DB password, Google key hay Telegram token.

## Dọn mục đã tắt trên dashboard

Bảng có checkbox chọn nhiều và nút Xóa mục đã chọn, tối đa 200 mục/lần. Chỉ mục DISABLED được chọn; chọn tất cả chỉ áp dụng các mục đã tắt trong kết quả lọc hiện tại. Có hộp xác nhận liệt kê các mục trước khi thao tác. Muốn ngừng theo dõi mục đang bật thì tắt/xóa khai báo trên Sheet trước, đợi đồng bộ.

Đây là dọn danh sách bằng cờ archived trong DB, không xóa mẫu kiểm tra/lịch sử, không ghi Sheet và không điều khiển service. Mục đã dọn không hiện lại qua các lượt đồng bộ FALSE hoặc dòng đã xóa; chỉ tự xuất hiện khi mục được bật lại trên Sheet. Backend kiểm tra toàn bộ danh sách: nếu có mục đang bật/đã đổi trạng thái thì từ chối cả yêu cầu, không dọn một phần. Không cần quyền Editor Google.

## Nâng cấp, sao lưu và nghiệm thu

Code trong monitor/ được bind mount chỉ đọc vào /app/monitor. Sửa Python: chép file rồi restart các dịch vụ dùng module đó. Chỉ sửa giao diện: build frontend rồi reload trình duyệt theo [FRONTEND.md](FRONTEND.md). Chỉ build lại image backend khi đổi thư viện Python hoặc Dockerfile; lần đầu chuyển sang React cần build/recreate để áp dụng mount và route mới. Nếu thay schema: sao lưu DB, down core, chạy docker compose run --rm init-db rồi docker compose up -d; không cần build nếu không đổi thư viện. Xem DOCKER-SETUP.md để áp dụng cấu hình mount lần đầu. Init tạo bảng mới và thêm các cột Note/display_name nếu thiếu, không phải công cụ migration tổng quát. Chuyển DB bằng dump/restore theo README DB, sửa DATABASE_URL và recreate core. Chuyển core cần chuyển cả secrets; đổi URL API thì sửa config agent. Không copy thư mục data khi DB đang chạy để coi là backup nhất quán.

Nghiệm thu trên môi trường thử: dừng/chạy lại container, lỗi replica, service mất/redeploy/thêm mới, dừng agent, Docker query lỗi, quyền Sheet lỗi, Telegram lỗi, bật/tắt dòng và kiểm tra Note/nhiều dự án. Giữ một agent mỗi máy để bộ đếm đúng.

Các kiểm thử cũ chỉ áp dụng trước các cập nhật gần đây. Theo yêu cầu hiện tại, không chạy test trên máy này; phần uptime/lazy rendering mới chưa nghiệm thu Docker/PostgreSQL thật. Xem UPTIME-UPGRADE.md để nâng schema trước khi chạy. Source tests nằm ở tests/; agent folder đặt ngang hàng core khi chạy các tests liên quan script.

Frontend React và hướng dẫn triển khai: [FRONTEND.md](FRONTEND.md). PostgreSQL vẫn lưu dữ liệu giám sát, SQLite trong state/ vẫn lưu tài khoản, phiên và cấu hình; không đổi schema vì chuyển frontend.
