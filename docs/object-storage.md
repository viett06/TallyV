# Kho dữ liệu TallyV

PostgreSQL lưu hồ sơ, audit, trạng thái và metadata. Kho file private lưu Excel nguồn, ảnh gốc, PNG đã che, artifact Assistant và PDF Chatbot. Việc khôi phục hồ sơ cần cả database lẫn kho file. Giữ nguyên UUID, tiền tố và checksum khi sao chép object.

## Kho local và MinIO

`STORAGE_BACKEND=local` lưu file dưới `STORAGE_DIR`, mặc định `data/`. Khi dùng MinIO, `scripts/init_env.py` cấu hình S3 cho lần cài mới. Với `.env` đã có, dùng `python -m scripts.configure_storage` để chuẩn bị biến kết nối.

- API ngoài Docker dùng `http://127.0.0.1:9000`, container dùng `http://minio:9000`.
- Trang quản trị MinIO tại [localhost:9001](http://127.0.0.1:9001). Ứng dụng dùng tài khoản riêng giới hạn theo bucket và prefix.
- Compose giữ Postgres và MinIO trong named volume. `minio-init` thoát mã 0 sau khi tạo quyền và bucket.

## Sao lưu và chuyển kho

Dừng API và worker trước khi chuyển file. Kiểm kê các file được tham chiếu từ cả ba tính năng và sao lưu chúng cùng database. `scripts.migrate_storage` kiểm tra và sao chép file nguồn chấm công từ hai bảng `attachments` và `evidence_files`. PNG sau che, PDF Chatbot và artifact Assistant cần kiểm kê và chuyển cùng đợt bằng quy trình phù hợp với kho.

```sh
venv/bin/python -m scripts.migrate_storage --source ./data
venv/bin/python -m scripts.migrate_storage --source ./data --apply
```

Lệnh đầu đối chiếu file. Lệnh có `--apply` sao chép sang kho S3 đã cấu hình. Chỉ đổi backend sau khi kiểm tra tải lại tất cả loại file cần giữ.

## AWS S3

Dùng bucket private và quyền IAM cho prefix TallyV. Đặt `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION` và `S3_ADDRESSING_STYLE=auto`. Để trống `S3_ENDPOINT_URL` và `S3_DOCKER_ENDPOINT_URL`. Khi dùng IAM role, để trống `S3_ACCESS_KEY_ID` và `S3_SECRET_ACCESS_KEY` để SDK lấy thông tin xác thực từ môi trường. Overlay AWS bỏ phụ thuộc MinIO khỏi API và worker.

```sh
docker compose -f compose.yaml -f compose.outlook.yaml -f compose.aws-storage.yaml \
  up -d --build ocr api worker
```

## Dữ liệu demo

`samples/` chứa workbook giả lập đi kèm repo. `data/` là vùng riêng ngoài Git dành cho file chạy thực tế, PDF nguồn và bản sinh demo. Xóa trong `data/` chỉ sau khi đã xác minh file không còn được database tham chiếu.

`scripts.reset_demo` xóa dữ liệu nghiệp vụ và job trong database. Chỉ dùng trên stack Mailpit riêng dành cho dữ liệu giả lập và dừng API/worker trước khi chạy.
