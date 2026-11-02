# Agent — Linux system service

Core và PostgreSQL dùng Docker Compose. Agent chạy trực tiếp bằng systemd để theo dõi cả Docker/Compose và các system service trên host.

## Cài một lệnh

Sau khi push repo chung lên GitHub public, có thể cài không cần chép folder bằng một dòng (thay ORG và nhánh):

```bash
curl -fsSL https://raw.githubusercontent.com/PD-Mera/merasys/main/merasys-agent/bootstrap.sh | sudo bash -s -- https://github.com/PD-Mera/merasys.git main
```

Script tải repo, cài dependency cần thiết, hỏi URL/IP/token và setup luôn updater. Cần Linux/systemd, sudo, curl và terminal tương tác. Repo private: upload bootstrap.sh rồi `sudo bash bootstrap.sh REPO_URL main`, với quyền đọc Git cho root đã cấu hình. Không dùng raw URL public cho repo private. Lần sau cập nhật bằng `sudo merasys-agent-update`. Hướng dẫn toàn hệ thống: FRESH-INSTALL.md ở gốc repo.

Chép thư mục này lên server cần giám sát, chạy từ thư mục đó:

```bash
sudo bash install.sh
```

Chỉ cần Python 3 tại /usr/bin/python3 và systemd (ví dụ Ubuntu/Debian). Không cần pip hoặc Docker Compose. Nếu cần giám sát container, server phải có Docker CLI/daemon; máy không dùng Docker vẫn giám sát được heartbeat và system services.

Script hỏi URL API 109, IP máy này trùng Sheet và token tạo trên web core tại Cấu hình → Token agent theo IP. Tạo `.env` quyền 0600, kiểm tra cấu hình, cài code vào /opt/merasys-agent, config vào /etc/merasys-agent/agent.env và bật service. Nếu .env đã tồn tại, dùng lại, không ghi đè. Env riêng của agent vẫn cần URL/IP/token; chỉ env core được rút còn WEB_HOST/WEB_PORT.

Nếu bản agent Docker cũ còn chạy, dừng nó trước khi cài bằng service (từ thư mục agent cũ chạy sudo docker compose down). Chỉ chạy một agent trên mỗi server. Core/DB Compose không thay đổi.

```bash
sudo systemctl status merasys-agent
sudo journalctl -u merasys-agent -f
# Sau khi sửa .env trong thư mục cài đặt, chạy installer lại:
sudo bash install.sh
# Dừng:
sudo systemctl disable --now merasys-agent
```

Agent chạy root để đọc Docker socket và systemd của host, chỉ dùng lệnh đọc cố định, không tự restart/điều khiển dịch vụ. Service tự khởi động khi boot. Không đưa DB password/Google key/Telegram token lên agent.

## Khai báo trên Sheet

Core hiện nhận các Type server, compose và rabbitmq. Sheet dùng thứ tự:

```text
Bật giám sát | Dự án | Tên dịch vụ | IP server | Type | Người phụ trách | Tên compose | Tên queue | RabbitMQ connection | Queue config | Server config | Note
```

Dòng server giám sát heartbeat, tùy chọn dung lượng theo Server config. Dòng compose điền Tên compose. RabbitMQ do core kiểm tra trực tiếp, không cần agent trên broker. Không khai báo container riêng hoặc cột Tên service cũ. Server config là cột tùy chọn, Note cuối có thể bỏ.

Agent vẫn gửi inventory systemd để hỗ trợ mở rộng, nhưng Sheet hiện chưa cho khai báo systemd/screen trực tiếp. Dung lượng còn trống theo GB: xem [DISK-MONITORING.md](DISK-MONITORING.md).

Mỗi 60 giây gửi heartbeat, Docker inventory và trạng thái systemd. Lỗi Docker vẫn gửi trạng thái systemd, lỗi systemd vẫn gửi Docker/heartbeat. Không có báo cáo quá thời hạn thì cảnh báo mất liên lạc, có thể do server/agent/mạng/API. Không buffer dữ liệu cũ. Bản đầu chưa có RAM/CPU hoặc kiểm tra HTTP/TCP.

API trả 409 nếu IP chưa khai báo/bật và đồng bộ từ Sheet; 401 nếu token sai. Theo dõi log Report accepted để xác nhận gửi thành công. Dùng HTTPS; HTTP chỉ trong mạng riêng tin cậy/VPN và ALLOW_HTTP=true. Giữ token bí mật.

Nếu file chuyển từ Windows thành CRLF và lỗi pipefail:

```bash
sed -i 's/\r$//' install.sh
sudo bash install.sh
```

Source script có thể nhận JSON qua --config cho nhu cầu riêng; cách cài chuẩn dùng env và systemd ở trên.

## Cập nhật agent đã cài

Muốn cập nhật qua Git bằng lệnh `sudo merasys-agent-update`, xem [GIT-UPDATE.md](GIT-UPDATE.md). Chỉ cần setup repo/nhánh một lần trên mỗi server, sau đó commit/push code mới và chạy lệnh update; giữ nguyên env/token.

Upload monitor-agent.py và update.sh mới vào một folder riêng trên server, rồi `sudo bash update.sh`. Script cập nhật code, giữ nguyên /etc/merasys-agent/agent.env và systemd unit, tạo một bản backup code .previous rồi restart merasys-agent. Không dùng install.sh khi chỉ cần nâng cấp code.

Agent mới hỗ trợ dung lượng filesystem theo GB: nhận đường dẫn từ core trong phản hồi report và đo ở vòng tiếp theo; không phải thêm ngưỡng vào env. Xem [DISK-MONITORING.md](DISK-MONITORING.md). Theo dõi bằng `sudo journalctl -u merasys-agent -n 30 --no-pager`.

## Repo chung cho toàn hệ thống

Agent nằm ở merasys-agent trong cùng repo với core và PostgreSQL. AGENT_SUBDIR khi setup git-update.sh là `merasys-agent`, không phải `.`. Xem [PUBLISH.md](PUBLISH.md) và PUBLISH.md ở gốc dự án. Không commit cấu hình thật. Chưa chạy test trên máy phát triển theo yêu cầu người dùng.
