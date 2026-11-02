# Frontend React

Frontend dùng React 19.3, TypeScript 5.9 và Vite 7.3. Công cụ build/dev chạy trên Node 22 (tối thiểu 22.12). Production phục vụ HTML/CSS/JS đã build qua FastAPI, cùng origin với API và cookie đăng nhập; không chạy Vite dev server ngoài production.

Backend giữ Python/FastAPI/Uvicorn, SQLAlchemy/PostgreSQL cho dữ liệu giám sát và SQLite trong `state/` cho tài khoản, phiên và cấu hình. Không chuyển hay xóa dữ liệu khi cập nhật frontend. Mật khẩu không yêu cầu 12 ký tự; chấp nhận từ 1 đến 256 ký tự.

## Cấu trúc

- `frontend/src/`: component React và kiểu TypeScript. `Dashboard.tsx`, `Detail.tsx`, `TestAlert.tsx`, `Auth.tsx`, `Settings.tsx`.
- `frontend/package-lock.json`: khóa phiên bản dependency, dùng `npm ci` khi build.
- `frontend/dist/`: kết quả build, không commit lên Git.
- `monitor/frontend.py`: phục vụ index và assets. Đọc index mỗi request, không cache HTML khi khởi động.

Compose mount `./monitor` → `/app/monitor` và `./frontend/dist` → `/app/frontend/dist`, đều chỉ đọc trong backend. Worker vẫn hoạt động độc lập. Không sửa trực tiếp file build trong `dist/`.

## Triển khai Docker mới

Upload toàn bộ `frontend/` (không kèm node_modules/dist), `monitor/`, Dockerfile, `.dockerignore`, `pyproject.toml` và `compose.yaml` mới vào thư mục core. Những file `monitor/auth.html`, `monitor/dashboard.html`, `monitor/settings.html` cũ không còn dùng. Giữ nguyên `.env`, `state/`, secrets và dữ liệu DB.

Từ thư mục core trên server:

```bash
sudo docker compose up -d --build
```

Nếu tài khoản cần sudo để dùng Docker, thêm `sudo` trước `docker` trong lệnh build; truyền UID/GID qua `sudo env FRONTEND_UID="$(id -u)" FRONTEND_GID="$(id -g)" docker compose ...` để giữ quyền sở hữu file của người dùng.

Compose tự build/xuất frontend trước khi khởi động backend nhờ depends_on/service_completed_successfully. Không cần Node/npm trên host. Khi nâng cấp bản cũ, container được recreate nếu image hoặc mount thay đổi. Không cần migrate schema chỉ vì chuyển frontend. Không mở trang trong lúc bản build đầu tiên chưa được xuất ra `frontend/dist/`; backend trả 503 với hướng dẫn build khi chưa có index.

## Những lần chỉ đổi giao diện sau đó

Upload source `frontend/` mới, rồi từ thư mục core chạy:

```bash
mkdir -p frontend/dist
FRONTEND_UID=$(id -u) FRONTEND_GID=$(id -g) docker compose --profile tools run --rm --build --no-deps frontend-build
```

Sau đó reload trình duyệt (Ctrl+F5 nếu cần). Không restart backend hoặc worker. Build service chỉ xuất assets vào thư mục mount và thay index cuối cùng bằng rename; giữ các assets có hash của bản trước cho tab đang mở. Nếu build lỗi, bản đang phục vụ không bị thay. Không xóa `frontend/dist/assets/` trong lúc triển khai.

Đổi Python: restart các dịch vụ dùng module đã sửa. Đổi dependencies Python/Dockerfile: build lại image backend. Đổi mount/WEB_HOST/WEB_PORT: recreate container.

## Dev trên máy phát triển riêng

Node 22.12+ và backend đang chạy tại `127.0.0.1:21707`:

```bash
cd frontend
npm ci
npm run dev
```

Mở `http://localhost:5173`. Vite tự cập nhật component khi sửa source, proxy `/api` và `/healthz` tới FastAPI. Proxy giữ Host gốc để kiểm tra Origin/CSRF và cookie cùng origin tiếp tục hoạt động. Nếu đổi cổng backend, cập nhật proxy trong `vite.config.ts`.

Build với Node cài sẵn trên máy phát triển: `npm run build`. Trên production đang phục vụ, dùng build service phía trên để giữ assets của bản trước và xuất index cuối cùng. Đây là biên dịch TypeScript và đóng gói Vite; không chạy test. Theo yêu cầu người dùng, không chạy test, cài dependency test hoặc tạo môi trường test trên máy này.

Compose cần giữ thư mục `merasys-agent/` cạnh `merasys-core/` và mount nó chỉ đọc vào `/app/agent-source` để phục vụ cài agent một lệnh. Endpoint tải xuống chỉ chứa các file mã cài đặt đã định sẵn, không chứa cấu hình hoặc token của server.
