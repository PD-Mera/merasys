# Bàn giao giao diện Merasys
> Bản hiện tại: một tài khoản duy nhất; trang / tự chuyển đăng ký/đăng nhập. Cấu hình ở /settings, env core chỉ WEB_HOST/WEB_PORT. API ghi cần X-Merasys-Request: 1 và cookie same-origin; giữ apiFetch và nút Cấu hình/Đăng xuất. Dashboard token và đọc config từ secrets/env trong tài liệu cũ đã được thay bằng WEB-CONFIG.md. Chỉ sửa UI theo phạm vi được giao, không thay logic account/config.


## 1. Nhiệm vụ và giới hạn bắt buộc

Bạn là agent **chỉ phụ trách giao diện**. Được thay đổi cách trình bày dashboard để đẹp, rõ, dễ đọc và thuận tiện thao tác. **Không được thay đổi logic giám sát, dữ liệu, API, xác thực, DB hoặc triển khai.**

Giới hạn này áp dụng cho công việc bàn giao giao diện. Nếu một yêu cầu cần thay backend, chỉ ghi rõ phần cần backend hỗ trợ và bàn giao lại; không tự sửa để hoàn thành giao diện. Không được mở rộng phạm vi chỉ vì thấy code có thể refactor hoặc cần cải thiện.

### File được phép sửa

1. `merasys-core/monitor/dashboard.html` — file giao diện đưa lên server.
2. `monitor/dashboard.html` ở gốc workspace — bản source tương ứng, chỉ đồng bộ cho giống file trên.

Nếu bạn đang mở trực tiếp folder `merasys-core`, file được phép sửa là `monitor/dashboard.html` trong folder đó. Không tự tạo bản sao source khi folder source gốc không có trong workspace được giao.

HTML hiện chứa toàn bộ HTML, CSS, JavaScript và SVG inline. Có thể chỉnh layout, typography, màu, icon, responsive, accessibility và mã render DOM. Có thể thay cấu trúc DOM/selector nếu cập nhật các chỗ liên quan trong chính file, giữ đầy đủ hành vi và ý nghĩa dữ liệu hiện tại.

Không tách thêm file CSS/JS/font/ảnh cần endpoint mới: backend chưa phục vụ thư mục static. Ưu tiên giữ file tự chứa, dùng system font và SVG inline; không thêm npm, bundler, CDN hoặc thư viện mới.

### Không được sửa

- Mọi file Python, bao gồm `web.py`, `alerts.py`, `collector.py`, `sheet.py`, `ingest.py`, `db.py`, `settings.py`, `cli.py`.
- `compose.yaml`, `Dockerfile`, `.dockerignore`, `pyproject.toml`, `.env`, `.env.example`, cấu hình, secrets, migration/schema DB.
- Các bộ `merasys-agent` và `merasys-postgres-db`.
- API contract, chu kỳ gọi API, timeout, cơ chế cookie phiên đăng nhập, đường dẫn API, phân loại đối tượng, cách xác định UP/DOWN/UNKNOWN/DISABLED, ngưỡng dữ liệu quá hạn và cách đếm tổng quan.
- Logic cảnh báo Telegram, xác nhận lỗi/phục hồi, nhắc lại, hàng đợi, thao tác cấu hình Google Sheet.

Không đọc/hiển thị secrets, không đưa token/mật khẩu vào HTML, URL, console hoặc localStorage. Không thêm request ghi dữ liệu ngoài endpoint archive mục đã tắt đã được triển khai. Không sửa các file khác để “hỗ trợ frontend”.

## 2. Quy định làm việc của người dùng

- **Không chạy test trên máy này, không cài thư viện test, không tạo môi trường test.** Không build/chạy ứng dụng, dựng DB giả hoặc gọi đó là preview để né giới hạn này. Rà soát code bằng cách đọc nếu cần.
- Không triển khai lên server hoặc thay đổi dịch vụ đang chạy nếu chưa được người dùng giao việc đó.
- Khi kết thúc, phải ghi rõ **file nào cần đưa lên server** và **lệnh áp dụng**. Không nói đã cập nhật server khi mới sửa source.
- Giữ nguyên `.env`, `secrets/` và dữ liệu người dùng.

## 3. Dự án và kiến trúc liên quan

Hệ thống giám sát Linux server, Docker container, Compose project và systemd service. Mỗi agent chạy systemd trên server đích, gửi heartbeat/inventory về core. Core chạy Docker Compose, lưu PostgreSQL và có worker đọc DB để cảnh báo Telegram. Cấu hình giám sát được nhập bằng một tab Google Sheet.

Dashboard hiển thị dữ liệu giám sát và có một thao tác quản trị giới hạn: chọn nhiều mục đã tắt để dọn khỏi danh sách (archive). Ngoài thao tác này, UI chỉ xem tổng quan, tìm/lọc, xem chi tiết và mở Sheet. Không có chức năng thay đổi cấu hình, restart container, xác nhận/đóng sự cố hoặc điều khiển agent.

Địa chỉ người dùng đang sử dụng: `http://10.0.2.109:21707`. Đây là địa chỉ mạng nội bộ; không giả định có thể truy cập từ môi trường làm việc. Chưa có thông tin đăng nhập được cấp trong bàn giao này. Không tự yêu cầu hoặc tìm mật khẩu trong `.env`.

### Cách phục vụ UI

- `GET /` trả HTML của `dashboard.html`, được backend đọc khi tiến trình web khởi động.
- `GET /api/status` trả JSON, yêu cầu cookie phiên đăng nhập như trang dashboard.
- `GET /healthz` chỉ phản ánh API kết nối DB, không xác nhận toàn bộ hạ tầng đang khỏe.
- Compose mount `./monitor` trên host vào `/app/monitor` trong container, chỉ đọc. Image chỉ cài thư viện.
- Sửa HTML cần restart `web` để backend đọc nội dung mới; không cần build image.

## 4. API contract — giữ nguyên

UI gọi `GET /api/status` với `credentials: 'same-origin'`, `cache: 'no-store'`. Không tự lưu mật khẩu hoặc thay xác thực bằng token mới. Tải lúc mở trang, làm mới mỗi **30 giây**, timeout **15 giây**, nút làm mới thủ công và làm mới khi quay lại tab; không tạo các lần gọi chồng nhau.

Các trường cấp cao:

| Trường | Ý nghĩa |
|---|---|
| `targets` | Danh sách mục giám sát gồm server, container, Compose và system service |
| `health` | Trạng thái các thành phần của hệ thống giám sát |
| `incidents` | Chỉ các sự cố đang mở; không phải lịch sử sự cố |
| `pending_notifications` | Số thông báo đang chờ gửi trong DB |
| `generated_at` | Thời điểm tạo snapshot, ISO UTC |
| `display_timezone` | Múi giờ hiển thị từ cấu hình, thường `Asia/Bangkok` |
| `stale_after_seconds` | Ngưỡng quá hạn dữ liệu target, thường 180 giây |
| `sheet_url` | URL Sheet để mở khai báo; có thể là null |

### Một target

Ví dụ minh họa cấu trúc, không phải dữ liệu thật để đưa cứng vào UI:

```json
{
  "id": 12,
  "host": "10.9.3.241",
  "container": "compose:visual_sense",
  "display_name": "Tra soát vi phạm truyền hình",
  "projects": ["VisualSense"],
  "owners": ["nghia.nguyen1"],
  "note": "Ghi chú dịch vụ từ Sheet",
  "status": "DOWN",
  "reason": "Kết quả kiểm tra chi tiết",
  "checked_at": "2026-10-30T09:42:44Z",
  "compose_services": [
    {
      "name": "visualsense_api",
      "status": "DOWN",
      "reason": "visualsense_api=exited",
      "containers": [{"name": "visualsense_api", "state": "exited"}],
      "checked_at": "2026-10-30T09:42:44Z"
    }
  ]
}
```

- `display_name`: tên hiển thị từ cột **Tên dịch vụ** sau cột Dự án trên Sheet. Dùng trường này làm tiêu đề chính trên bảng và khung chi tiết. Khi trống hoặc API cũ không có trường thì dùng tên kỹ thuật cũ. Hiển thị tên kỹ thuật trong phần Định danh giám sát ở chi tiết; tìm kiếm được cả tên hiển thị và tên kỹ thuật. Không dùng display_name để xác định loại, định danh hoặc trạng thái target.
- `container == '(server)'`: mục server/heartbeat.
- Bắt đầu `compose:`: Compose project; bỏ prefix khi hiển thị tên kỹ thuật, không thay display_name bằng tên Compose.
- Bắt đầu `systemd:`: system service; bỏ prefix khi hiển thị tên kỹ thuật.
- Selector cũ không thuộc loại đang hỗ trợ là dữ liệu lịch sử; không khai báo hoặc giám sát Docker container riêng nữa.
- `projects`, `owners`, `compose_services` là mảng; có thể rỗng. `checked_at` có thể null, `note` có thể trống.
- Mỗi Compose là một target; không đếm các phần tử `compose_services` thành target độc lập trong tổng số dịch vụ.

### Trạng thái target

| Mã | Nhãn hiện tại | Ý nghĩa hiển thị |
|---|---|---|
| `UP` | Hoạt động | Kết quả gần nhất đang hoạt động |
| `DOWN` | Gián đoạn | Kết quả gần nhất lỗi/dừng |
| `UNKNOWN` | Chưa rõ | Chưa biết hoặc dữ liệu quá hạn |
| `DISABLED` | Đã tắt | Đã tắt giám sát |

Backend đã áp dụng trạng thái quá hạn khi tạo snapshot. UI hiện tiếp tục kiểm tra `checked_at` với `stale_after_seconds` để dữ liệu cũ không giữ màu xanh khi API lỗi. Giữ nguyên hàm `state()` về mặt ngữ nghĩa: DISABLED được ưu tiên; thiếu thời gian hoặc quá hạn thành UNKNOWN. Không suy diễn UNKNOWN thành DOWN, không đổi trạng thái để giao diện “đẹp hơn”.

UP server là có heartbeat; UP container là running; UP systemd là active. Các trạng thái này không khẳng định ứng dụng đang phục vụ HTTP tốt. Không dùng nhãn “mọi dịch vụ bình thường” khi còn dữ liệu thiếu hoặc API lỗi.

### Health và incidents

```json
{
  "component": "sheet",
  "last_ok_at": "2026-10-30T09:42:00Z",
  "error": "",
  "status": "UP",
  "stale_after_seconds": 600
}
```

Health có `sheet`, `alert-worker`, `host:IP`; trạng thái có thể UP, DEGRADED, STALE hoặc UNKNOWN. Panel thành phần hiện chỉ hiển thị các mục không bắt đầu `host:`; máy chủ đã có khu vực riêng. Giữ đúng ngưỡng của từng thành phần, không áp dụng chung ngưỡng target cho tất cả health.

Incident có `title`, `detail`, `opened_at`; không có ID thao tác hoặc API đóng sự cố. Các timestamp từ API là UTC, trình bày theo `display_timezone`; không hardcode giờ UTC hoặc giờ máy người xem.

API hiện **không cung cấp** RAM, CPU, disk, port mapping, SLA hoặc danh sách IP khách truy cập. Lịch sử uptime có endpoint availability riêng như phần bổ sung bên dưới; không nhúng dữ liệu giả vào chart. Không thêm số liệu/biểu đồ giả, không suy ra uptime 100% từ một snapshot. Yêu cầu thông tin port trước đây mới được trao đổi, chưa triển khai.

### Xóa khai báo khỏi Sheet

Sau đồng bộ thành công, target mất khỏi Sheet tự tắt giám sát và API trả trạng thái DISABLED; không xóa lịch sử. Host chỉ tắt khi không còn khai báo nào được bật. Còn một dòng khác cho cùng đối tượng thì tiếp tục giám sát theo cấu hình còn lại. Header hợp lệ không có dòng dữ liệu là chủ ý tắt toàn bộ; lỗi tải/sai header/dòng sai không áp dụng thay đổi. Worker hủy tin chưa gửi và đóng sự cố của mục đã tắt, không tạo cảnh báo phục hồi. UI phải trình bày DISABLED đúng, không suy diễn thành DOWN.

### Dọn nhiều mục đã tắt — API được phép dùng

`POST /api/targets/archive`, cùng cookie phiên đăng nhập; JSON `{"ids":[12,13]}`, tối đa 200 ID. Gửi Content-Type application/json, X-Monitor-Action archive-disabled và credentials same-origin. Backend kiểm tra nguồn request, từ chối mục đang bật bằng HTTP 409; không được bỏ các kiểm tra này hoặc tự lọc bỏ lỗi rồi gọi lại ngầm. Thành công trả `{"ok":true,"archived_count":2}`. Không có request đến Google hoặc thay Sheet.

Chỉ bật checkbox cho target DISABLED. Chọn tất cả chỉ tác động kết quả hiện đang lọc; hiển thị tổng số được chọn và hộp xác nhận tên/host. Giới hạn 200 mục, thể hiện lỗi server rõ ràng, không tự giả lập thành công. Sau thành công tải lại /api/status để cập nhật. API status đã loại các target archived. Nếu bật lại trên Sheet, backend bỏ archive và trả lại target; UI không tự quản lý cờ này.

Đây là quyền dọn danh sách, không phải API xóa DB vĩnh viễn hay API tắt dịch vụ. Agent UI chỉ sửa cách trình bày/interaction của thao tác này trong HTML, không mở rộng backend hoặc quyền quản trị.

### Cột Type trên Sheet

Sheet hỗ trợ Type ngay sau IP server: server hoặc compose. Cột Tên container và việc giám sát container riêng đã được bỏ; tên container chỉ còn trong chi tiết service/replica của Compose. Các mục container cũ có thể còn trong lịch sử ở trạng thái Đã tắt để người quản trị dọn, không cho UI tạo/khôi phục kiểu giám sát container riêng. Đây là khai báo được backend kiểm tra; API/UI vẫn phân loại theo container=(server) hoặc prefix compose: như cũ. Không đổi cách suy ra loại, bộ đếm hay trạng thái trên UI. Tên dịch vụ/display_name vẫn là tên hiển thị, độc lập Type và định danh kỹ thuật. Không thêm loại RabbitMQ hoặc suy diễn loại mới từ label tự nhập.

### Uptime, lịch sử và bảng cập nhật

Backend đã bổ sung GET /api/targets/{id}/availability?period=24h|7d|30d, cùng cookie phiên đăng nhập. Chỉ gọi khi xem chi tiết, cache ngắn hạn 30 giây, hủy request cũ khi đổi đối tượng. Trả seconds theo UP/DOWN/UNKNOWN/DISABLED/NO_DATA, uptime_percent, coverage_percent (trong thời gian giám sát), window_coverage_percent (toàn kỳ), recorded_since, buckets, downtime_count, longest_down_seconds và tối đa 100 downtimes. Không suy diễn NO_DATA hoặc UNKNOWN là UP. Dữ liệu bắt đầu từ lúc nâng cấp, không bịa số liệu cũ.

UI phải giữ bảng có cột Người phụ trách; mỗi Compose mở/đóng danh sách service ngay dưới entry. Lazy rendering nạp 40 entry mỗi lượt bằng cách append, không dựng lại cả bảng khi cuộn. Poll giữ neo cuộn, bộ lọc, mục đang bung và lựa chọn dọn mục đã tắt. Nút chọn tất cả chỉ tác động entry đã tải. Bản thân /api/status vẫn trả snapshot đầy đủ; không gọi là phân trang API hoặc tải lịch sử cho mọi entry cùng lúc. Các phần chức năng này đã có backend, agent UI chỉ cải thiện trình bày và giữ contract.

## 5. Tính năng UI phải giữ

- Sidebar Tổng quan / Máy chủ / Dịch vụ / Sự cố.
- Bốn số tổng quan: số server, số dịch vụ được bật, số dịch vụ UP trên số được bật, số sự cố đang mở.
- Thẻ server; chọn một thẻ để lọc dịch vụ của host đó. Tỷ lệ dịch vụ UP trên thẻ chỉ đếm target dịch vụ đang bật: loại DISABLED khỏi cả tử và mẫu số. Không có dịch vụ bật thì hiển thị Chưa có dịch vụ đang giám sát và dấu —, không hiển thị 100%. Đây là tỷ lệ trạng thái snapshot, không phải uptime theo thời gian.
- Tab tất cả / dịch vụ / máy chủ; tìm theo tên, IP, dự án, người phụ trách và Note.
- Bộ lọc dự án và trạng thái, thao tác xóa bộ lọc. Tự cập nhật không xóa trạng thái lọc.
- Bảng ưu tiên DOWN, UNKNOWN, UP rồi DISABLED như hiện tại.
- Chi tiết đối tượng: loại, tên, host, trạng thái, lần kiểm tra cuối, dự án, phụ trách, reason, Note, từng service/container của Compose.
- Danh sách sự cố đang mở, panel Sheet/worker và số thông báo chờ gửi.
- Nút mở Sheet chỉ hiện khi có `sheet_url`; dùng URL do API cấp, mở tab mới kèm `noopener noreferrer`.
- Loading, chưa có dữ liệu, không có kết quả lọc, không có sự cố, lỗi xác thực và API không truy cập được phải có cách hiển thị riêng.
- API lỗi: giữ dữ liệu gần nhất nhưng báo dữ liệu cũ/mất kết nối. Không hiển thị trạng thái “đang kết nối” hoặc trạng thái khỏe từ dữ liệu quá hạn.

JavaScript được sửa để bố trí/render, điều hướng và tương tác UI, nhưng không thay cách lấy dữ liệu, phân loại, ngưỡng, đếm số hoặc ý nghĩa trạng thái. Giữ các hàm `kind()`, `state()`, logic số liệu trong `render()`, `renderHealth()` và cơ chế `refresh()` tương đương hành vi hiện tại. Nếu không cần sửa chúng, giữ nguyên.

## 6. Yêu cầu thiết kế và an toàn hiển thị

- Tiếng Việt; chữ nội dung chính khoảng 15–16px, nhãn phụ không quá nhỏ. Người dùng đã phản ánh giao diện cũ có chữ quá bé.
- Dễ đọc IP, tên container/Compose dài có dấu gạch dưới; dùng monospace khi phù hợp, không cắt mất khả năng xem đầy đủ.
- Desktop và điện thoại đều dùng được. Có thể cuộn ngang bảng, không để toàn trang tràn ngang.
- Không chỉ dùng màu để truyền trạng thái: phải có nhãn chữ. Độ tương phản dễ đọc, focus rõ, nút có tên truy cập được.
- Khung chi tiết có thể đóng bằng nút và Escape; giữ keyboard/focus semantics, ưu tiên dialog native hiện có.
- Nội dung từ Sheet, Docker, agent và API là dữ liệu không tin cậy. Giữ `esc()`/textContent khi render; không đưa nội dung API trực tiếp vào innerHTML, onclick hoặc CSS.
- Chỉ duy trì thao tác archive đã có; không thêm thao tác ghi DB khác, gửi Telegram, sửa Sheet hoặc điều khiển hạ tầng.
- Không thay `.env`, không hardcode port 21707 trong request; tiếp tục dùng endpoint tương đối `/api/status` cùng origin.
- Không dùng framework, package hoặc asset bên ngoài đòi sửa Dockerfile/API để chạy.

## 7. Bàn giao kết quả cho người dùng

Chỉ bàn giao các thay đổi giao diện và liệt kê chức năng được giữ. Ghi rõ không chạy test/không truy cập hoặc chưa cập nhật server nếu đúng như vậy. Không tuyên bố đã kiểm thử dữ liệu thật.

File đưa lên server (đường dẫn tương đối từ thư mục core):

```text
monitor/dashboard.html
```

Sau khi người dùng chép file, từ thư mục core trên server:

```bash
sudo docker compose restart web
```

Mở lại dashboard và Ctrl + F5. **Không build image**, không restart collector/alerts/agent/DB cho thay đổi UI. HTML được backend đọc khi web khởi động nên không chỉ refresh trình duyệt mà bỏ qua restart web.

## 8. Prompt có thể giao thẳng cho agent UI

> Đọc UI-HANDOFF.md và AGENTS.md trước khi làm. Hãy cải thiện giao diện Merasys trong monitor/dashboard.html của bộ merasys-core. Bạn chỉ được sửa giao diện trong file này và đồng bộ bản monitor/dashboard.html ở gốc workspace nếu có. Không sửa bất kỳ Python/backend, logic giám sát, API, DB, xác thực, Telegram, Sheet, agent, Docker, thư viện hoặc cấu hình nào. Giữ nguyên hành vi lấy dữ liệu, phân loại, trạng thái, bộ đếm, polling và bộ lọc; không thêm dữ liệu giả hoặc tính năng chưa có API. Ưu tiên chữ dễ đọc, responsive và khả năng thao tác bằng bàn phím. Không chạy test hoặc cài thư viện trên máy này. Kết thúc phải nêu đúng file cần đưa lên server và lệnh docker compose restart web; không tự triển khai.
