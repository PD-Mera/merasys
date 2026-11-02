# Merasys

Hệ thống giám sát server, Docker Compose và RabbitMQ; cấu hình qua web và Google Sheet, lưu dữ liệu trong PostgreSQL và cảnh báo qua Telegram.

Một repo Git chung, gồm ba thư mục triển khai độc lập:

| Thư mục | Chức năng | Hướng dẫn |
|---|---|---|
| `merasys-core/` | API, dashboard, đồng bộ Sheet và cảnh báo | [README core](merasys-core/README.md) |
| `merasys-agent/` | Agent systemd trên từng server | [README agent](merasys-agent/README.md) |
| `merasys-postgres-db/` | PostgreSQL và dữ liệu trên host | [README DB](merasys-postgres-db/README.md) |

Triển khai theo thứ tự DB → core → agent. Xem [cài mới](merasys-core/FRESH-INSTALL.md), [cấu hình qua web](merasys-core/WEB-CONFIG.md) và [hướng dẫn Git/publish](merasys-core/PUBLISH.md).

Mã nguồn, tests, cấu hình mẫu, Dockerfile và Compose của core chỉ lưu trong `merasys-core/`. Chỉnh sửa và chạy lệnh triển khai từ thư mục tương ứng; không có bản sao hoặc symlink code ở gốc repo.

Giữ nguyên cấu hình thật, secrets, `state/` và dữ liệu PostgreSQL khi cập nhật. Không đưa các dữ liệu này lên Git. Không chạy test hoặc cài môi trường test trên máy này.

Frontend: React 19.3 + TypeScript 5.9 + Vite 7.3 trên Node 22. Backend: Python/FastAPI/Uvicorn; PostgreSQL lưu giám sát, SQLite lưu tài khoản/cấu hình. Xem [build và triển khai frontend](merasys-core/FRONTEND.md).
