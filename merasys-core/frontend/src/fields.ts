export const groups = [
  [
    "PostgreSQL",
    "DB giám sát triển khai độc lập. Lưu lần đầu sẽ kiểm tra kết nối và tạo/nâng cấp bảng cần thiết.",
    [
      [
        "database_url",
        "Database URL",
        "text",
        "Ví dụ: postgresql+psycopg://monitor:PASSWORD@127.0.0.1:5432/monitor. URL-encode mật khẩu có ký tự đặc biệt.",
      ],
    ],
  ],
  [
    "Google Sheet",
    "Dán JSON service account có quyền đọc spreadsheet. Không cần chép key vào folder secrets.",
    [
      [
        "google_sheet_id",
        "Spreadsheet ID",
        "text",
        "Lấy ID trong URL Google Sheet.",
      ],
      [
        "google_worksheet",
        "Tab giám sát",
        "text",
        "Ví dụ Monitoring. Các tab TelegramUsers/RabbitMQConnections giữ theo mẫu.",
      ],
      [
        "google_credentials_info",
        "Service account JSON",
        "json",
        "Chọn file hoặc dán toàn bộ JSON key. Không hiển thị lại key đã lưu.",
      ],
    ],
  ],
  [
    "Telegram",
    "Tất cả cảnh báo và tin thử gửi tới nhóm/topic này.",
    [
      [
        "telegram_bot_token",
        "Bot token",
        "password",
        "Để trống giữ token đang lưu.",
      ],
      ["telegram_chat_id", "Chat ID", "text", "ID nhóm thường có dạng -100…"],
      [
        "telegram_message_thread_id",
        "Message thread ID",
        "optional-number",
        "Để trống nếu không gửi vào topic forum.",
      ],
    ],
  ],
  [
    "Chu kỳ và ngưỡng",
    "Đơn vị thời gian là giây. Ngưỡng dữ liệu quá hạn cần lớn hơn chu kỳ report của agent và thời gian quét RabbitMQ.",
    [
      ["sheet_sync_seconds", "Đồng bộ Sheet", "number", "10–86400"],
      ["sheet_stale_after_seconds", "Sheet quá hạn sau", "number", "60–604800"],
      ["failure_threshold", "Số lần lỗi trước cảnh báo", "number", "1–100"],
      [
        "recovery_threshold",
        "Số lần thành công để phục hồi",
        "number",
        "1–100",
      ],
      [
        "stale_after_seconds",
        "Dữ liệu target quá hạn sau",
        "number",
        "30–86400",
      ],
      [
        "alert_poll_seconds",
        "Worker cảnh báo kiểm tra mỗi",
        "number",
        "5–3600",
      ],
      [
        "alert_reminder_seconds",
        "Nhắc lại sự cố mỗi",
        "number",
        "0 để tắt; tối đa 604800",
      ],
      ["rabbitmq_poll_seconds", "Quét RabbitMQ mỗi", "number", "10–3600"],
      [
        "display_timezone",
        "Múi giờ hiển thị",
        "text",
        "Ví dụ Asia/Bangkok hoặc Asia/Ho_Chi_Minh.",
      ],
    ],
  ],

] as const;
export const secretKeys = new Set<string>([
  "database_url",
  "google_credentials_info",
  "telegram_bot_token",
  "agent_tokens",
]);
