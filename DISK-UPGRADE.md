# Giám sát dung lượng còn trống theo GB

> Core hiện cấu hình bằng web theo [WEB-CONFIG.md](WEB-CONFIG.md), env chỉ WEB_HOST/WEB_PORT. Cập nhật/lưu DB và token agent qua UI trước; các tham chiếu env/secrets cũ trong hướng dẫn nâng cấp không thay thế luồng mới. Server config và đo dung lượng trên agent giữ nguyên.

Agent đo filesystem trên Linux; core lưu số liệu/các bộ đếm trong DB và worker alerts cảnh báo Telegram. Không kiểm tra SMART, không ghi file thử vào ổ đĩa, không yêu cầu thư viện Python mới. 1 GB = 1.000.000.000 byte; có thể khác số GiB trong một số công cụ Linux. Dung lượng sử dụng được lấy từ f_bavail thay vì phần trống dự phòng chỉ dành cho root; tham khảo https://docs.python.org/3/library/os.html#os.statvfs.

## 1. Cập nhật core trước

Sao lưu DB. Trong thư mục compose của core trên 109:

```bash
sudo docker compose down
```

Upload đè **toàn bộ monitor/** từ merasys-core vào monitor/ trên server. Có module mới `disks.py`; không chỉ chép file HTML. Giữ nguyên .env, secrets và bộ PostgreSQL riêng. Compose/Dockerfile không đổi, không cần build.

```bash
sudo docker compose run --rm --no-deps init-db
sudo docker compose up -d --no-build
sudo docker compose logs --tail=30 web alerts
```

Chỉ khởi động nếu init-db thành công. init-db thêm `targets.server_config` và `targets.disk_metrics`, không xóa dữ liệu cũ. Core mới vẫn nhận agent cũ; chưa bật policy disks thì không tạo cảnh báo ổ đĩa. Chưa cần sửa Sheet ở bước này.

## 2. Cập nhật agent từng server

Upload **monitor-agent.py và update.sh** trong merasys-agent vào một thư mục tạm trên từng máy (ví dụ ~/merasys-agent-update). Không chép đè /etc/merasys-agent/agent.env, không đổi token.

```bash
cd ~/merasys-agent-update
sudo bash update.sh
sudo journalctl -u merasys-agent -n 30 --no-pager
```

update.sh thay code ở /opt/merasys-agent/monitor-agent.py và restart systemd unit hiện tại. Giữ nguyên env, unit, token, IP, URL và chu kỳ gửi. Bản code trước được lưu một bản ở /opt/merasys-agent/monitor-agent.py.previous khi source nằm ở thư mục upload khác. Không chạy install.sh để cập nhật nếu không muốn đụng cấu hình.

Nếu script bị chuyển sang CRLF lúc upload, chạy `sed -i 's/\r$//' update.sh` rồi `sudo bash update.sh`. Agent không chạy Docker. Nếu agent đang dùng đường dẫn cài khác đường dẫn chuẩn trên, cập nhật file theo ExecStart của unit thực tế, không dùng update.sh nguyên bản.

## 3. Bật cấu hình trên Sheet

Thêm cột **Server config** sau Queue config, trước Note:

```text
Bật giám sát | Dự án | Tên dịch vụ | IP server | Type | Người phụ trách | Tên compose | Tên queue | RabbitMQ connection | Queue config | Server config | Note
```

Sheet 11 cột cũ vẫn đọc được khi chưa thêm Server config. Note cuối có thể bỏ. Server config chỉ điền trên dòng Type=server, không điền ở compose/rabbitmq. Muốn giám sát ổ đĩa phải có dòng server riêng, TRUE; heartbeat tự sinh từ Compose không tự có policy ổ đĩa.

Ví dụ nội dung một ô:

```json
{"disks":[{"path":"/","min_free_gb":20},{"path":"/data","min_free_gb":100,"recover_free_gb":110,"require_mount":true}]}
```

- `/` dưới 20 GB thì thiếu dung lượng; mặc định phục hồi từ 25 GB trở lên.
- `/data` dưới 100 GB thì thiếu dung lượng; phục hồi từ 110 GB. Chỉ khai báo /data nếu máy thực sự dùng đường dẫn này.
- `recover_free_gb` mặc định min_free_gb + 5; có thể tự đặt nhưng phải lớn hơn min_free_gb.
- `require_mount` mặc định false. Đặt true cho đường dẫn phải là mount point riêng để tránh đọc dung lượng filesystem cha khi mount mất. Agent kiểm tra mount trong namespace của systemd service, không xác minh SMART hay định danh thiết bị vật lý.
- Tối đa 16 đường dẫn, đường dẫn tuyệt đối tối đa 200 ký tự; không chứa ký tự điều khiển. Chỉ nhận các khóa trên. min/recovery là số GB dương, hỗ trợ phần thập phân, tối đa 1000000000 GB.
- Để ô trống, `{}` hoặc `{"disks":[]}` thì tắt giám sát dung lượng. FALSE/xóa dòng server cũng tắt policy dù heartbeat server còn bật vì có Compose. Xóa một path thì chỉ ngừng cảnh báo path đó. Tin chưa gửi của policy bị bỏ được hủy, không gửi phục hồi giả.
- Nếu nhiều dòng cùng IP server, Server config phải thống nhất. Người phụ trách/dự án/note lấy từ chính dòng server; vẫn hỗ trợ nhiều người và mention qua TelegramUsers.

Trên core, đồng bộ:

```bash
sudo docker compose run --rm --no-deps collector sync-once
```

Sau khi sync thành công, agent nhận danh sách path trong phản hồi của report kế tiếp và bắt đầu đo ở vòng sau. Không phải cấu hình thêm ngưỡng trong env của agent. Mặc định report 60 giây; cần khoảng 2–3 vòng để lấy đường dẫn và xác nhận trạng thái. Khởi động lại agent sẽ lấy lại danh sách từ core. Core không gửi password/DB credentials trong phản hồi này.

## 4. Hiển thị và cảnh báo

Ctrl+F5 dashboard. Dòng server có badge dung lượng còn trống, bấm chi tiết xem tổng/còn trống, ngưỡng và trạng thái từng đường dẫn. Dữ liệu quá hạn có nhãn cũ; không suy diễn dung lượng từ report heartbeat hoặc số liệu cũ.

Disk kiểm tra trên từng report, dùng FAILURE_THRESHOLD lần lỗi liên tiếp và RECOVERY_THRESHOLD lần đủ dung lượng để xác nhận (mặc định 3/2). Có hysteresis: khi đã LOW phải đạt recover_free_gb mới tính là phục hồi. Mất mount, sai đường dẫn, không có quyền hoặc timeout tạo lỗi đọc dung lượng riêng. Một lượt đầu khi vừa khai báo path chưa có report được chờ để agent nhận config. Agent cũ không hỗ trợ sẽ tạo cảnh báo thiếu số liệu nếu đã bật policy, vì vậy cập nhật agent trước khi khai báo.

Mỗi path là một incident riêng trong DB; lịch sử Incident/outbox vẫn theo retention hiện tại. Chỉ giữ snapshot dung lượng mới nhất và bộ đếm trên target, không tạo thêm lịch sử dung lượng theo từng phút. Đây là bổ sung điều kiện cảnh báo, không làm server heartbeat thành DOWN hoặc thay đổi lịch sử uptime heartbeat. Sự cố server/agent mất heartbeat sẽ giữ nguyên incident disk đang có, không báo phục hồi giả trong lúc mất dữ liệu. Nhắc lại vẫn theo ALERT_REMINDER_SECONDS, không tự gửi lặp mỗi report.

Agent dùng os.statvfs trong tiến trình con, timeout 5 giây mỗi path để hạn chế một đường dẫn chậm ảnh hưởng report. Nên dùng cho filesystem local; nhiều path chậm có thể kéo dài vòng report. Unit hiện tại có ProtectHome=true nên một số path dưới /home có thể không truy cập được; không tự sửa sandbox của service khi update. Với đường dẫn bị chặn cần xem lại unit/phạm vi cho phép trên server.

Chưa chạy test, cài dependencies, gọi server hoặc gửi Telegram thật trên máy phát triển theo yêu cầu người dùng. Cần xác nhận dữ liệu thực tế từ agent sau khi cập nhật server.
