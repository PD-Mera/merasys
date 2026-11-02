# Đăng ký, đăng nhập và cấu hình trên giao diện

Core chỉ dùng hai biến env:

```dotenv
WEB_HOST=0.0.0.0
WEB_PORT=21707
```

Không dùng DASHBOARD_TOKEN hoặc Basic Auth. PostgreSQL URL, Google key/Sheet ID, token agent, Telegram/chat/topic và chu kỳ/ngưỡng được nhập ở /settings. Các biến env cũ tương ứng không được đọc. Đây là thay đổi cấu hình **core**; agent vẫn cần URL/IP/token lúc cài và bộ PostgreSQL độc lập vẫn cần cấu hình khởi tạo DB của nó.

## Tài khoản duy nhất

- Lần đầu truy cập / sẽ là đăng ký. Tạo username 3–64 ký tự chữ/số/_.@- và mật khẩu tùy chọn, không để trống (tối đa 256 ký tự).
- Khi đã có tài khoản, / hiển thị đăng nhập. Server từ chối đăng ký thêm, kể cả hai request cùng lúc: bảng owner chỉ có thể có một dòng id=1.
- Mật khẩu dùng scrypt với salt riêng, không lưu plaintext. Phiên đăng nhập là cookie HttpOnly/SameSite=Strict, Secure khi truy cập HTTPS; token phiên chỉ lưu hash ở server, hết hạn sau 12 giờ. Đăng xuất xóa phiên; đổi/reset mật khẩu kết thúc mọi phiên.
- Giới hạn 5 lần thử đăng nhập mỗi IP trong 15 phút; đặt chỗ lần thử trước khi kiểm tra hash để hạn chế request đồng thời vượt giới hạn.
- API quản trị yêu cầu cookie và header X-Merasys-Request: 1 trên request ghi, kiểm tra Origin. API agent vẫn dùng Bearer token riêng, không dùng tài khoản web.
- Tài khoản đầu tiên là quản trị viên; hãy tạo tài khoản trước khi cho người khác truy cập máy chủ lần đầu. Không có endpoint tạo tài khoản thứ hai hoặc bỏ tài khoản trên web.

## Nơi lưu cấu hình

Docker bind mount ./state vào /app/state có quyền ghi; code vẫn mount read-only. Tài khoản, session và cấu hình bootstrap lưu trong state/control.sqlite3 bằng SQLite cục bộ. Nhờ vậy web khởi động được cả khi chưa có PostgreSQL hoặc DB đang lỗi. Các worker đọc chung cấu hình, tự nạp thay đổi; không phải restart khi sửa tham số trên web. Chu kỳ đang chờ cũng được đánh thức khi cấu hình thay đổi.

Dữ liệu giám sát, lịch sử và outbox vẫn ở PostgreSQL độc lập. Đổi Database URL chọn DB khác, KHÔNG tự sao chép dữ liệu từ DB cũ. Mật khẩu DB, key Google và token được lưu trong state có quyền truy cập hạn chế; API cấu hình có xác thực trả đầy đủ Database URL (gồm mật khẩu) để hiển thị và chỉnh sửa trên web; token agent cũng được trả đầy đủ để sửa và sao chép theo IP; Google key và Telegram bot token chỉ trả cờ đã cấu hình. Ô secret trống giữ giá trị cũ; checkbox xóa hoặc JSON {} có thể bỏ cấu hình đó theo mô tả.

Sao lưu **state/** cùng với PostgreSQL để chuyển core sang máy khác mà giữ tài khoản/cấu hình. Dừng core trước khi sao chép toàn bộ state để giữ nhất quán SQLite/WAL. Không xóa state để reset password; không commit state vào Git. .gitignore đã loại state khỏi repo. Không cần folder secrets trong core nữa; key Google có thể tải file JSON trực tiếp qua màn cấu hình, còn agent tokens nhập hoặc tạo trên web.

## Cài mới core

Sau khi chạy DB theo merasys-postgres-db/README.md:

```bash
cd merasys-core
cp .env.example .env
sudo docker compose up -d --build
```

Mở http://IP_109:21707, đăng ký tài khoản rồi vào Cấu hình. Không cần init-db trước khi mở web; service init-db chỉ dành cho thao tác thủ công (profile tools), không chặn web. Worker chờ cấu hình thay vì bắt buộc DB tồn tại khi boot.

1. Nhập PostgreSQL URL, ví dụ postgresql+psycopg://monitor:PASSWORD@127.0.0.1:5432/monitor. URL-encode password có ký tự đặc biệt. Lưu lần đầu kiểm tra kết nối, tạo/nâng cấp bảng và khởi tạo lịch sử nếu cần. DB lỗi sẽ báo trên form và giữ cấu hình trước đó.
2. Nhập Google Sheet ID, tên tab Monitoring và JSON service account có quyền đọc Sheet; có nút chọn file JSON. Tab TelegramUsers/RabbitMQConnections và các cột monitor giữ nguyên các mẫu hiện có.
3. Nhập Telegram bot token, chat ID và thread ID tùy chọn; chỉnh chu kỳ/ngưỡng/múi giờ theo nhu cầu.
4. Lưu, rồi dùng Đồng bộ Sheet ngay. Key/URL/token không được ghi vào .env nữa.
5. Dùng Token agent theo IP → Tạo/đổi token. Token chỉ hiển thị một lần để sao chép vào installer. Nếu IP đã có token, xác nhận thay token và cập nhật lại agent tương ứng. Nhập Agent tokens JSON là thay toàn bộ map, để trống giữ nguyên.
6. Cài agent bằng bootstrap.sh như trước, nhập URL/IP/token đã tạo. Không cần đổi code agent cho riêng lần thay auth/config của core.

Env chỉ sửa khi đổi địa chỉ/cổng web, rồi `sudo docker compose up -d --force-recreate`. Không thay dependencies cho phần này; image hiện có vẫn dùng được nếu đã có đủ dependencies.

## Nâng cấp core cũ

1. Sao lưu PostgreSQL, .env và secrets cũ. Trong core cũ chạy `sudo docker compose down`.
2. Upload code và cấu hình triển khai theo [FRONTEND.md](FRONTEND.md) khi chuyển từ HTML sang React; build frontend trước khi recreate backend. Giữ .env thật đang dùng. Giữ nguyên data DB; không chép cấu hình thật lên Git.
3. File .env của core chỉ giữ WEB_HOST/WEB_PORT. Ví dụ cổng đang dùng 21707; không copy nguyên mẫu env cũ vào bản mới.
4. `sudo docker compose up -d --no-build --force-recreate` nếu đã có image Merasys và dependencies hiện tại; nếu cài lần đầu dùng --build. Mở web tạo tài khoản duy nhất. Cấu hình lại DB URL trỏ **DB cũ** để giữ lịch sử; nhập key Google, Sheet, Telegram và token agent cũ trên UI.
5. Có thể dán nguyên nội dung agent-tokens.json cũ vào Agent tokens JSON để giữ quyền các agent đang cài; không cần cài lại agent hoặc đổi token. Chép nội dung service account JSON cũ vào Google key trên form. Các file secrets cũ không được tự import hay xóa.
6. Đồng bộ Sheet và kiểm tra dashboard/tin thử. Các worker dùng cấu hình mới tự động. Khi chuyển core sang máy khác phải mang theo state/ và DB kết nối, không chỉ .env hai dòng.

## Quên mật khẩu

Chỉ người có quyền quản trị Docker trên server dùng CLI tương tác sau:

```bash
sudo docker compose run --rm --no-deps web reset-password
```

Nhập mật khẩu mới hai lần; giữ username, cấu hình, dữ liệu DB và kết thúc mọi phiên cũ. Không có API reset công khai.

## Phạm vi kiểm tra

Chỉ rà soát source và đồng bộ bộ triển khai; không chạy app, tests, cài dependencies, DB hoặc gửi Telegram thật trên máy này theo yêu cầu người dùng. Source test cũ dùng Basic Auth/Settings kiểu cũ không đại diện hợp đồng mới. Cần xác nhận luồng đăng ký/đăng nhập/lưu cấu hình và worker trên server khi triển khai.

## Frontend React

Đăng nhập, cấu hình và dashboard dùng chung frontend React. Build và mount theo [FRONTEND.md](FRONTEND.md); UI chỉ cần build lại rồi reload trình duyệt sau lần nâng cấp backend đầu tiên. Không có yêu cầu mật khẩu tối thiểu 12 ký tự.

Token agent nhập theo bảng IP: Thêm máy chủ, nhập token rồi Lưu token hoặc Tạo token tự động. Từng dòng lưu ngay; token đã lưu được hiển thị đầy đủ để sửa và sao chép, kể cả sau khi tải lại trang. Tạo/đổi hoặc xóa token đã có cần xác nhận. Nhập JSON hàng loạt nằm trong Nhập nâng cao và thay toàn bộ danh sách.

Có thể sửa IP của dòng token đã lưu. Lưu IP/token sẽ chuyển token sang IP mới trong một giao dịch; IP cũ bị bỏ, không ghi đè nếu IP mới đã được cấu hình. Cập nhật IP/token của agent và khai báo Sheet tương ứng khi chuyển IP.

Mỗi dòng IP đã lưu có nút Sao chép lệnh cài agent. Lệnh dùng bootstrap hiện có, kèm hướng dẫn URL core và IP; nhập token tương tác trên server. Nếu agent đã tồn tại, bootstrap giữ cấu hình hiện có.

## Cài agent một lệnh, không nhập lại

Trên trang Cấu hình, lưu IP/token rồi bấm **Sao chép lệnh cài agent**. Dán lệnh vào terminal của server cần giám sát. Core phục vụ script và bundle mã agent trực tiếp, không cần GitHub public hoặc quyền Git trên server. Ví dụ (thay URL/IP/token):

```bash
curl -fsSL 'http://IP_CORE:21707/agent/install.sh' | sudo bash -s -- --url 'http://IP_CORE:21707' --server '10.9.3.239' --token 'TOKEN_DA_LUU_TREN_CORE'
```

Script cần Linux/systemd, sudo và curl; tự cài Python3/tar nếu thiếu. Các tham số truyền vào cập nhật cấu hình agent kể cả đã cài; lưu bản cũ tại `/etc/merasys-agent/agent.env.previous`. Token nằm trong lệnh đã sao chép, vì vậy lệnh này cũng là thông tin đăng nhập của agent. Chế độ `install.sh` không có tham số vẫn giữ cách nhập tương tác/cấu hình cũ.
