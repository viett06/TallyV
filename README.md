# TallyV

TallyV nhập bảng điều chỉnh chấm công từ email hoặc hồ sơ tạo tay. Backend che thông tin cá nhân trên ảnh, chạy OCR nội bộ rồi gửi ảnh đủ điều kiện đến VLM để đánh giá và phân loại. HR rà soát, xác nhận và xuất Excel.

**Assistant** xử lý dữ liệu và soạn báo cáo. **Chatbot** tra cứu quy định từ PDF. Hai tính năng có cấu hình model riêng. HR hiện nhập công số vào SAP từ kết quả đã duyệt.

## Chạy thử bằng Mailpit

Cần Docker Compose, Python 3.11 và [trọng số OCR](docs/vlm-evidence.md#chạy-ocr-nội-bộ). Chạy từ gốc repo. Chạy `scripts/init_env.py` một lần để tạo `.env`.

```sh
python3 scripts/init_env.py
docker compose -f compose.yaml -f compose.demo.yaml up -d --build
```

Mở [TallyV](http://127.0.0.1:8000), đăng nhập bằng `DEMO_USERNAME` và `DEMO_PASSWORD` trong `.env`. Chọn kỳ, đợt và bấm **Tạo dữ liệu demo**. Dữ liệu đi qua [Mailpit](http://127.0.0.1:8025) và xuất hiện ở **Hộp thư** và **Trường hợp**.

Bộ Mailpit dùng để thử nhập Excel và HR rà soát. Dùng [workbook giả lập](samples/attendance-ocr-demo.xlsx) đi cùng profile để thử bài đánh giá OCR/VLM. Đặt `OPENROUTER_API_KEY` khi thử VLM. [Hướng dẫn dùng workbook và kiểm tra ảnh sau che](docs/attendance.md#dữ-liệu-thử)

Với Outlook, dùng overlay `compose.outlook.yaml` để worker truy cập dịch vụ email. [Thiết lập Outlook](docs/outlook.md)

## Phát triển và kiểm thử

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m pytest -q tests
ruff check app main.py scripts tests ocr_service alembic
docker compose config --quiet
```

Compose chạy migration khi khởi động API. Khi chạy API và worker trực tiếp, dùng `alembic upgrade head`, `python -m scripts.seed_catalog`, `uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log` và `python -m app.worker` ở terminal riêng. Chạy PostgreSQL, MinIO và OCR để API native truy cập bằng `docker compose -f compose.yaml -f compose.local.yaml up -d --build db minio minio-init ocr`. Để dùng Vite trong khi phát triển, chạy `npm --prefix frontend run dev`.

## Tài liệu

- [Chấm công, mẫu Excel và quy trình HR](docs/attendance.md)
- [Che PII, OCR nội bộ và VLM](docs/vlm-evidence.md)
- [Outlook](docs/outlook.md) và [kho dữ liệu](docs/object-storage.md)
- [Assistant](docs/assistant.md) và [Chatbot quy định](docs/chatbot-retrieval.md)
- [Kiến trúc và kiểm tra vận hành](docs/architecture.md)
