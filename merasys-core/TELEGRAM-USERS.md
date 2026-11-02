# Mention người phụ trách trên Telegram

> Frontend hiện đã chuyển sang React trong `frontend/`. Các đường dẫn `monitor/*.html` trong hướng dẫn nâng cấp lịch sử bên dưới thuộc bản cũ; dùng [FRONTEND.md](FRONTEND.md) cho build/mount giao diện hiện tại. Các bước backend và sao lưu dữ liệu chỉ áp dụng theo tính năng cần nâng cấp.

> Token bot/chat/topic hiện đặt trên màn Cấu hình theo [WEB-CONFIG.md](WEB-CONFIG.md), không dùng env Telegram hoặc Basic Auth. Các API quản trị dùng cookie đăng nhập và X-Merasys-Request: 1; tab TelegramUsers và logic mention giữ nguyên.

Tạo tab tên chính xác `TelegramUsers` trong cùng Google spreadsheet đang dùng. Không đổi `GOOGLE_WORKSHEET`: biến đó vẫn trỏ tới tab khai báo giám sát. Hỗ trợ bảng hai cột cũ và bảng ba cột có thêm Telegram username ở cuối.

| Người phụ trách | Telegram user ID | Telegram username |
|---|---|---|
| dong.trinh1 | 123456789 | |
| nghia.nguyen1 | | nghia_example |

Các ID/username trên chỉ minh họa, phải thay bằng thông tin Telegram thật. Có mẫu CSV tại `config/telegram-users-template.csv`.

- Mỗi dòng là một người. Điền ID hoặc username; có cả hai thì ưu tiên ID. Username có thể có hoặc không có @, hệ thống chuẩn hóa thành @username. Tên khớp lựa chọn ở cột Người phụ trách của tab giám sát; so khớp không phân biệt hoa thường và bỏ khoảng trắng đầu/cuối. Username phải là tài khoản cá nhân thật; đổi username thì cần cập nhật lại Sheet.
- ID là số nguyên dương đầy đủ; không dùng `@username`, số điện thoại, chat ID âm hoặc thread ID. Định dạng cột ID thành Văn bản thuần túy trước khi điền để tránh biểu diễn số mũ.
- Cột Người phụ trách của tab giám sát vẫn chọn nhiều như trước, ví dụ `dong.trinh1, nghia.nguyen1`. Bot tra và mention từng tên có ID/username. Người không có cả hai thì chỉ hiển thị tên. Nếu dùng username, tin hiển thị `nghia.nguyen1 (@nghia_example)`; @username là mention dạng chữ, không đặt trong code hoặc link web.
- Server lấy người phụ trách từ dòng server; Compose lấy từ dòng Compose. Hệ thống không gom người phụ trách từ Compose sang server.
- Mention áp dụng cho cảnh báo sự cố, tin nhắc và phục hồi có trường Phụ trách. Tin hệ thống không có người phụ trách thì không thêm mention.
- ID được tra từ DB lúc gửi, gồm cả tin chưa gửi trong outbox. Tin đã gửi không bị sửa. Danh sách người phụ trách trong tin là danh sách ghi nhận khi tạo tin; ánh xạ ID được lấy ở lần đồng bộ gần nhất.
- Danh sách tên quá dài được rút gọn ở mức 1.200 ký tự và ghi số người còn lại để giới hạn độ dài tin Telegram. Không cắt giữa một link mention.
- Tab phải có hai tiêu đề cũ hoặc ba tiêu đề theo thứ tự trên. Các dòng hoàn toàn trống được bỏ qua. Tên có dấu phẩy/xuống dòng, ID/username sai định dạng hoặc một tên trùng với cấu hình ID/username khác nhau sẽ làm lần đồng bộ thất bại.
- Cả hai tab được tải và kiểm tra trước khi cập nhật DB trong cùng transaction. Thiếu tab, lỗi mạng hoặc dữ liệu sai giữ nguyên cấu hình và ánh xạ lần đồng bộ thành công trước đó. Xóa một dòng mapping rồi sync thành công sẽ bỏ mention của tên đó. Muốn xóa toàn bộ mapping, giữ dòng tiêu đề và xóa các dòng dữ liệu.
- Thêm tab không cần Google quyền ghi mới: service account hiện tại chỉ đọc cả hai tab trong cùng spreadsheet.

Bot dùng HTML link `tg://user?id=...` để mention người không cần username. Người được tag nên tham gia nhóm nhận cảnh báo. Telegram có điều kiện về thành viên nhóm/tương tác với bot và quyền riêng tư: https://core.telegram.org/bots/api#formatting-options. Cấu hình topic `TELEGRAM_MESSAGE_THREAD_ID` vẫn áp dụng.

## Nâng cấp core đang chạy

1. Tạo và điền tab TelegramUsers trước.
2. Trong thư mục core trên server, dừng hai worker trước khi upload code:

```bash
sudo docker compose stop collector alerts
```

3. Upload đè `monitor/db.py`, `monitor/sheet.py`, `monitor/alerts.py` từ bộ merasys-core vào cùng đường dẫn trên server.
4. Tạo bảng mapping bổ sung (hoặc thêm cột username nếu bảng đã có), đồng bộ rồi khởi động lại worker:

```bash
sudo docker compose run --rm --no-deps init-db
sudo docker compose run --rm --no-deps collector sync-once
sudo docker compose up -d --no-deps --no-build collector alerts
sudo docker compose logs --tail=50 collector alerts
```

Nếu init-db hoặc sync-once lỗi, xử lý lỗi đó trước khi thực hiện bước tiếp theo. Việc thêm bảng không xóa dữ liệu giám sát/lịch sử đang có. Không cần build image, đổi env hay cập nhật agent.

Không gửi tin thử Telegram hoặc chạy test trên máy phát triển theo yêu cầu người dùng.

## Thử cảnh báo từ dashboard

Nhấn **Thử cảnh báo** cạnh nút Làm mới. Nhập tiêu đề và nội dung tùy ý; muốn thử tag thì điền tên người phụ trách như Sheet, cách nhau bằng dấu phẩy (tối đa 20). Tin được ghi vào outbox PostgreSQL; worker alerts gửi tới chat/topic đang cấu hình với nhãn **THỬ NGHIỆM CẢNH BÁO**. Nội dung là văn bản thuần, được escape khi gửi HTML.

Nhấn **Kiểm tra kết quả** để xem trạng thái chờ/Telegram đã nhận và số lần gửi. Xếp hàng thành công không có nghĩa Telegram đã nhận: worker phải chạy và tin phải đến lượt trong FIFO. Retry, topic và ánh xạ ID/username sử dụng cùng cơ chế cảnh báo thật. Tin thử không tạo Incident và không thay đổi trạng thái hay uptime của đối tượng. Đây là kiểm tra đường gửi DB → worker → Telegram; muốn kiểm tra phát hiện DOWN thật phải tạo sự cố thực tế trên môi trường phù hợp.

Phần này bổ sung endpoint POST `/api/notifications/test` và GET `/api/notifications/test/{id}`, cùng HTTP Basic của dashboard. POST cần header `X-Monitor-Action: test-alert` và kiểm tra Origin như thao tác archive. Cập nhật `monitor/web.py`, `monitor/alerts.py`, `monitor/dashboard.html`, rồi `sudo docker compose restart web alerts`. Nếu đã triển khai phần TelegramUsers trước đó thì không cần init-db, build hay cập nhật agent cho riêng nút thử.

## Hàng đợi và yêu cầu gửi ngay

Khối Hệ thống giám sát hiển thị tổng số thông báo chờ và tối đa 5 tin đầu, gồm tiêu đề, số lần gửi, thời điểm tạo/thử lại và lỗi gần nhất. Dữ liệu làm mới theo snapshot 30 giây hoặc nút Làm mới.

Nút **Gửi ngay tin đầu** gọi POST `/api/notifications/retry` (HTTP Basic, header `X-Monitor-Action: retry-notification`, kiểm tra Origin), đặt lịch thử lại của tin đầu về hiện tại trong DB. Worker thực hiện gửi ở chu kỳ tiếp theo, bình thường khoảng 15 giây; nếu đang xử lý tác vụ khác có thể lâu hơn. Đây là yêu cầu thử lại, không phải xác nhận gửi thành công. Không đổi số lần thử, không tạo bản sao, không nhảy qua tin trước và không bỏ qua thời gian chờ Telegram HTTP 429. Tin không còn được giám sát vẫn bị hủy theo quy tắc cũ.

Worker khóa dòng outbox trong lúc gửi để phối hợp với thao tác retry và kiểm tra lại sent_at. Lỗi mạng/proxy/firewall vẫn phải xử lý trên server; nút retry chỉ bỏ lịch backoff. Cập nhật cùng ba file web.py, alerts.py và dashboard.html rồi restart web alerts; không thay schema DB.
