# Bàn giao giao diện React

Đọc AGENTS.md trước khi làm. Frontend hiện dùng React 19.3, TypeScript 5.9 và Vite 7.3 trên Node 22.12+. Xem FRONTEND.md để build và cập nhật.

## Phạm vi UI

Chỉ sửa component và CSS trong `frontend/src/` khi nhiệm vụ chỉ liên quan giao diện. Không tạo lại `monitor/dashboard.html` hoặc bản sao source ở gốc repo. Không thay backend, schema DB, agent, cấu hình triển khai hay dependencies để hoàn thành việc UI nếu người dùng chưa yêu cầu.

Giữ hợp đồng API, cookie đăng nhập, header X-Merasys-Request và X-Monitor-Action. Không đưa secret vào frontend, localStorage hay URL. React render dữ liệu dạng text; không dùng innerHTML để hiển thị giá trị từ API.

## Các hành vi cần giữ

- Lấy `/api/status` mỗi 30 giây, làm mới khi quay lại tab, giữ bộ lọc và lựa chọn đang hợp lệ; không tạo request polling chồng nhau. Hủy request khi rời trang.
- Khi API lỗi, giữ dữ liệu gần nhất và hiển thị thông báo mất kết nối. Dữ liệu quá hạn là UNKNOWN; mục DISABLED giữ trạng thái đã tắt. Không suy diễn UNKNOWN thành DOWN hoặc phục hồi.
- Tách server/Compose/RabbitMQ đúng định danh; không cộng service Compose nội bộ vào số đối tượng giám sát. Hiển thị số liệu RabbitMQ và ổ đĩa kèm dấu hiệu dữ liệu cũ.
- Giữ tìm kiếm tên/IP/dự án/người phụ trách/ghi chú, lọc host/loại/trạng thái/dự án, nạp thêm từng 40 mục và mở rộng service Compose.
- Chỉ chọn dọn mục DISABLED, tối đa 200 mục/lần, xác nhận trước khi archive; giữ lịch sử và Sheet. Backend quyết định trạng thái hợp lệ.
- Chi tiết có lịch sử 24h/7d/30d, độ phủ dữ liệu, UNKNOWN/NO_DATA/DISABLED, downtime và các khoảng gián đoạn. Uptime tính UP/(UP+DOWN); không tự tính lại từ số lần poll. Vạch đỏ nghĩa là có DOWN trong khoảng, không có nghĩa toàn khoảng DOWN.
- Giữ thử cảnh báo Telegram, kiểm tra kết quả thực nhận và yêu cầu gửi lại tin đầu hàng đợi. Không báo đã gửi khi chỉ mới xếp hàng.
- Giữ responsive, nhãn trường nhập, focus bàn phím, trạng thái loading/lỗi và khả năng đóng modal bằng Escape khi không đang gửi thao tác.

## Bàn giao

Không chạy test hoặc cài môi trường test trên máy này. Không tự deploy khi chưa được yêu cầu. Nêu các file source đã sửa và cách build theo FRONTEND.md. Sau khi cơ chế React/mount đã triển khai lần đầu, cập nhật UI chỉ cần build frontend rồi reload trình duyệt; không restart backend.
