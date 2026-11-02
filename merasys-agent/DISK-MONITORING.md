# Dung lượng trống theo GB

Cập nhật core và DB trước, sau đó cập nhật agent; cuối cùng bật policy trên Sheet. Trong dòng Type=server đang bật, cột Server config nằm sau Queue config, trước Note:

```json
{"disks":[{"path":"/","min_free_gb":20},{"path":"/data","min_free_gb":100,"recover_free_gb":110,"require_mount":true}]}
```

- Chỉ khai báo đường dẫn thực tế. `/` cảnh báo dưới 20 GB, phục hồi từ 25 GB mặc định. `/data` cảnh báo dưới 100 GB, phục hồi từ 110 GB theo ví dụ.
- recover_free_gb mặc định min_free_gb + 5, phải lớn hơn min_free_gb. Các ngưỡng là số GB dương, hỗ trợ thập phân. 1 GB = 1.000.000.000 byte.
- require_mount mặc định false, đặt true nếu path phải là mount point riêng. Kiểm tra trong namespace của systemd service; ProtectHome có thể chặn /home.
- Tối đa 16 path. Để trống hoặc {"disks":[]} để tắt; compose/rabbitmq để trống Server config.
- Agent nhận path từ phản hồi core, đo từ vòng sau; không đặt ngưỡng trong env. Chờ khoảng 2–3 vòng report (mặc định 60 giây/vòng).
- Core xác nhận số lần lỗi/phục hồi, cảnh báo từng path và tag người phụ trách server. Không chuyển heartbeat thành DOWN chỉ vì thiếu dung lượng.
- Chỉ đo filesystem, không SMART hoặc ghi file thử. Mỗi path có timeout 5 giây, ưu tiên ổ local. Lỗi đọc/mất mount/không có quyền báo riêng.

Core vẫn nhận agent cũ khi chưa bật policy disks. Bật policy mà agent chưa cập nhật có thể báo thiếu số liệu, nên cập nhật agent trước khi khai báo.
