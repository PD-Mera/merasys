# Nâng cấp uptime/downtime và bảng dịch vụ

> Frontend hiện đã chuyển sang React trong `frontend/`. Các đường dẫn `monitor/*.html` trong hướng dẫn nâng cấp lịch sử bên dưới thuộc bản cũ; dùng [FRONTEND.md](FRONTEND.md) cho build/mount giao diện hiện tại. Các bước backend và sao lưu dữ liệu chỉ áp dụng theo tính năng cần nâng cấp.

## Nội dung

- Lịch sử xác nhận UP/DOWN/UNKNOWN/DISABLED cho từng mục giám sát, gồm Compose và server. Không suy diễn quá khứ từ các sample cũ.
- Chọn 24 giờ, 7 ngày hoặc 30 ngày trong khung chi tiết; thanh lịch sử có thể nhấn từng vạch, kèm uptime, downtime, số khoảng DOWN, dài nhất và độ phủ.
- Compose có nút bung/thu các service ngay dưới entry trong bảng, không cần mở modal để xem trạng thái con. Lịch sử uptime hiện theo entry Compose tổng thể, chưa tính riêng từng replica/service con.
- Thêm cột Người phụ trách.
- Bảng có chiều cao giới hạn, tiêu đề cố định, 40 entry mỗi lượt. Khi cuộn xuống chỉ append phần tiếp theo; khi API tự cập nhật giữ neo cuộn và các Compose đang bung. Có nút Xem thêm cho bàn phím/trình duyệt không hỗ trợ observer.
- Chọn tất cả mục đã tắt chỉ áp dụng các entry đã tải, không chọn ngầm phần chưa hiển thị. Giới hạn dọn 200 mục/lần giữ nguyên.

## File cần đưa lên server

Khuyến nghị chép **toàn bộ folder monitor/** từ bộ core để tránh sót module mới, và file **compose.yaml**. Không thay .env hoặc secrets/. Không cần cập nhật agent, key, Sheet hoặc thư viện.

Các file runtime thay đổi cụ thể:

```text
monitor/availability.py       # mới
monitor/db.py
monitor/collector.py
monitor/ingest.py
monitor/sheet.py
monitor/alerts.py
monitor/cli.py
monitor/web.py
monitor/dashboard.html
compose.yaml
```

## Trình tự nâng cấp

Sao lưu PostgreSQL trước, theo hướng dẫn bộ DB. Từ thư mục core trên 109:

```bash
sudo docker compose down
```

Chép folder monitor/ và compose.yaml mới vào đúng vị trí. Giữ nguyên env/secrets. PostgreSQL triển khai riêng vẫn chạy. Sau đó:

```bash
sudo docker compose run --rm init-db
sudo docker compose up -d --no-build
sudo docker compose logs --tail=100 init-db web alerts
```

Chỉ bật core sau khi init-db thành công. Init tạo 3 bảng availability_intervals, availability_cursors, availability_daily; giữ dữ liệu hiện có. Khởi tạo lịch sử tại thời điểm nâng cấp. Agent gửi mẫu mới là lịch sử bắt đầu có dữ liệu xác nhận. Mở trình duyệt và Ctrl + F5. Không cần build image.

## Định nghĩa dữ liệu

- UP/DOWN thay đổi khi đủ mẫu theo FAILURE_THRESHOLD/RECOVERY_THRESHOLD đang cấu hình. Bắt đầu khoảng tại thời điểm nhận mẫu xác nhận, không lùi thời điểm DOWN về mẫu lỗi đầu tiên. Một vài mẫu lỗi thoáng qua không tự trở thành downtime.
- Truy vấn Docker lỗi thành UNKNOWN. Mất agent quá STALE_AFTER_SECONDS chuyển UNKNOWN tại thời điểm last_observed_at + timeout, kể cả worker chạy lại trễ; API cũng chiếu đúng khoảng mất dữ liệu khi đọc.
- Tắt/xóa khai báo: chuyển DISABLED và không tính vào thời gian được giám sát. Bật lại: UNKNOWN chờ xác nhận.
- Trước recorded_since: NO_DATA, không bịa lịch sử và không giả định UP. Không tự tính lại samples cũ thành lịch sử sự cố đã xác nhận.
- Uptime = UP/(UP+DOWN). UNKNOWN và DISABLED không nằm trong mẫu số; luôn trình bày UNKNOWN, NO_DATA, độ phủ toàn kỳ và độ phủ trong lúc giám sát để không nhầm 100% từ ít dữ liệu thành uptime cả tháng.
- Số khoảng DOWN và thời lượng chỉ tính phần giao với kỳ đã chọn. Khoảng bắt đầu trước kỳ được đánh dấu. Lịch sử hiển thị tối đa 100 khoảng DOWN gần nhất, nhưng tổng số/thời lượng vẫn tính toàn kỳ.
- Vạch đỏ nghĩa là có DOWN trong vạch, không phải toàn bộ khoảng đều DOWN. 24 giờ chia 24 vạch; 7 ngày chia 28 vạch (6 giờ); 30 ngày chia 30 vạch.
- Độ chính xác theo chu kỳ báo cáo, timeout và ngưỡng xác nhận; đây là lịch sử quan sát/giám sát, không đo trực tiếp mọi mili-giây hoạt động của ứng dụng.

## Lưu trữ

Mỗi đối tượng chỉ có một cursor và một khoảng đang mở. Mỗi lần báo cáo cập nhật cursor, chỉ tạo interval mới khi trạng thái xác nhận thay đổi. Không tạo một dòng lịch sử giống nhau mỗi phút.

Compose prune giữ sample chi tiết 7 ngày, giữ thông báo đã gửi 30 ngày. Interval đã kết thúc giữ 365 ngày; job dọn chuyển các interval cũ thành tổng hợp theo ngày UTC trước khi xóa chi tiết, tối đa 1000 interval/lượt để giới hạn công việc. Tổng hợp theo ngày giữ lâu dài. Khoảng đang mở không bị xóa. Các API UI hiện truy vấn tối đa 30 ngày nên không cần nạp toàn bộ lịch sử dài hạn vào RAM.

## Giới hạn bàn giao

Theo yêu cầu người dùng, không chạy test hoặc cài thư viện test trên máy phát triển. Đã rà soát code bằng cách đọc; chưa nghiệm thu runtime trên Linux, Docker và PostgreSQL thật. Đây là thay đổi cần nâng schema, không chỉ thay HTML/restart web.
