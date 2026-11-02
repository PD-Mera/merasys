# Chuyển toàn hệ thống sang Merasys

> Cấu hình core hiện đã chuyển sang web theo [WEB-CONFIG.md](WEB-CONFIG.md): chỉ WEB_HOST/WEB_PORT ở env, không còn dashboard token hoặc đọc secrets để chạy. Các bước giữ .env/secrets bên dưới chỉ để sao lưu và nhập lại giá trị trên UI. Việc chuyển tên agent/unit và giữ data PostgreSQL vẫn áp dụng.

Tên mới dùng đồng bộ cho repo, folder triển khai, package/CLI, Docker Compose/image, giao diện và systemd agent:

| Thành phần | Tên cũ | Tên mới |
|---|---|---|
| Repo/package | rnd-system-monitor | merasys |
| Core folder | rnd-system-monitor-core | merasys-core |
| Agent folder | rnd-system-monitor-agent | merasys-agent |
| PostgreSQL folder | rnd-system-monitor-postgres-db | merasys-postgres-db |
| CLI Python | rnd-monitor | merasys |
| Core Compose/image | rnd-monitor-core | merasys-core |
| PostgreSQL Compose project | tên suy ra từ folder cũ | merasys-db |
| Agent unit | rnd-monitor-agent | merasys-agent |
| Agent env | /etc/rnd-monitor-agent/agent.env | /etc/merasys-agent/agent.env |
| Agent code | /opt/rnd-monitor-agent/monitor-agent.py | /opt/merasys-agent/monitor-agent.py |
| Git updater | rnd-monitor-agent-update | merasys-agent-update |

Giữ nguyên module nội bộ monitor, tên bảng DB, Sheet, token, IP, URL API và dữ liệu lịch sử. POSTGRES_DB/POSTGRES_USER/DATABASE_URL hiện tại vẫn dùng được; không đổi DB/role/password chỉ để đổi thương hiệu. Bước này chưa chạy trên server, cần người vận hành thực hiện.

## Core

1. Sao lưu DB và giữ bản compose/env/secrets đang chạy để có thể quay lại.
2. Trong **folder core cũ**, chạy `sudo docker compose down` trước. Không chỉ chạy down ở folder mới, vì tên project mới không dừng container project cũ.
3. Upload/clone repo Merasys, dùng folder merasys-core. Chép .env và secrets/ từ bộ core cũ sang bộ mới. Giữ DATABASE_URL, Google key, agent-tokens và DASHBOARD_TOKEN. Không ghi đè .env bằng .env.example.
4. Nếu trước đó tùy chỉnh compose.yaml, mang các tùy chỉnh cần thiết sang bản mới. Với hostname/network/bind mount mặc định, không cần đổi URL agent vì host/port API vẫn giữ như cũ.
5. Trong merasys-core chạy lần lượt:

```bash
sudo docker compose build
sudo docker compose run --rm --no-deps init-db
sudo docker compose up -d --no-build
sudo docker compose ps
sudo docker compose logs --tail=30 web alerts
```

Chỉ tiếp tục sau khi lệnh trước thành công. Build lần này để có tag image mới merasys-core:0.5.0. Các lần sửa code thông thường vẫn dùng mount và restart như trước. init-db áp dụng nâng cấp bổ sung nếu có, không thay dữ liệu cũ. Ctrl+F5 để nạp giao diện Merasys.

## PostgreSQL

Có thể giữ DB đang chạy nguyên trạng và chỉ đổi core/agent trước, vì core dùng DATABASE_URL. Muốn đổi cả bộ triển khai DB:

1. Trong folder DB cũ, xác định đường dẫn **tuyệt đối** của data đang dùng, không mặc định rằng data của folder mới chứa dữ liệu. Nếu đang dùng ./data, chạy `realpath ./data` tại folder DB cũ và ghi lại kết quả. Nếu POSTGRES_DATA_DIR đã là đường dẫn riêng, dùng đúng đường dẫn đó.
2. Sao lưu DB; dừng core trước và chạy `sudo docker compose down` tại folder DB cũ. Không xóa thư mục data, không chạy down -v.
3. Chép .env cũ sang merasys-postgres-db/.env. Giữ POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, port/bind IP.
4. Sửa POSTGRES_DATA_DIR trong .env mới thành đường dẫn tuyệt đối tới **data cũ đã xác định**. Ví dụ `/opt/postgres-db/data` chỉ đúng nếu đó thực sự là nơi đã dùng. Không trỏ ./data ở folder mới khi chưa chuyển dữ liệu; PostgreSQL sẽ khởi tạo DB trống nếu đường dẫn rỗng.
5. Tại merasys-postgres-db:

```bash
sudo docker compose up -d
sudo docker compose ps
```

Đợi healthy rồi khởi động core mới. Vẫn dùng PostgreSQL 17, không chuyển định dạng data hoặc đổi password khi rename. Không chạy song song hai PostgreSQL dùng cùng data/cổng.

## Agent trên từng máy

Upload/clone merasys-agent. Khi nâng cấp, không tạo .env mẫu mới: installer sẽ ưu tiên .env tại folder hiện tại, nếu chưa có thì dùng /etc/merasys-agent/agent.env, hoặc kế thừa /etc/rnd-monitor-agent/agent.env của bản cũ.

```bash
cd merasys-agent
sudo bash install.sh
sudo systemctl status merasys-agent --no-pager
sudo journalctl -u merasys-agent -n 30 --no-pager
```

Installer giữ token/IP/URL, cài unit/path mới và disable/stop rnd-monitor-agent nếu unit cũ tồn tại để tránh báo cáo hai lần. Không xóa env/code/unit cũ để còn phương án quay lại; không khởi động lại unit cũ đồng thời với unit mới. Nếu trong folder upload đã có .env khác cấu hình đang chạy, hãy kiểm tra trước vì file đó được ưu tiên.

Script update.sh/git-update.sh tên mới chỉ cập nhật agent đã chuyển sang /opt/merasys-agent. Phải chạy install.sh một lần để chuyển tên, không chỉ chạy update.sh trên bản cũ.

## Git updater mới

Repo chung tên merasys, file agent nằm trong merasys-agent/monitor-agent.py. Trên mỗi máy sau khi chuyển unit:

```bash
sudo bash git-update.sh --setup https://github.com/PD-Mera/merasys.git main merasys-agent
sudo merasys-agent-update
```

Thay URL/nhánh theo repo thật; repo private cần quyền đọc Git cho root. Không dùng updater cũ rnd-monitor-agent-update sau khi chuyển. Lệnh mới giữ env/token và chỉ lấy code agent, không đổi core/DB. Không cần thay Sheet vì rename; chỉ cần sync nếu thay cấu hình giám sát.

Không chạy test hoặc triển khai trên server thật trong bước chuẩn bị rename này theo yêu cầu người dùng.
