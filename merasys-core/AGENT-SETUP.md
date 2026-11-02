# Cài nhanh core và agent

1. Chạy PostgreSQL độc lập theo merasys-postgres-db/README.md, hoặc chuẩn bị PostgreSQL đang có.
2. Chạy merasys-core với .env chỉ WEB_HOST=0.0.0.0 và WEB_PORT=21707.
3. Mở web, đăng ký tài khoản duy nhất. Vào Cấu hình, nhập DB URL, Google Sheet/key, Telegram và các tham số cần dùng; lưu.
4. Khai báo Sheet và bấm Đồng bộ Sheet ngay. Trong Token agent theo IP, tạo token từng máy và sao chép.
5. Trên mỗi server dùng bootstrap một dòng theo FRESH-INSTALL.md, hoặc upload merasys-agent và chạy sudo bash install.sh. Nhập URL/IP/token.
6. Kiểm tra journalctl -u merasys-agent và dashboard. Không cần cài lại agent cho riêng việc bỏ dashboard token của core nếu đã nhập lại token cũ trên UI.

Chi tiết: [FRESH-INSTALL.md](FRESH-INSTALL.md), [WEB-CONFIG.md](WEB-CONFIG.md). Core không còn đọc agent-tokens.json/Google key từ secrets hoặc cấu hình runtime từ env. Agent vẫn giữ env riêng để biết URL/IP/token lúc khởi động.
