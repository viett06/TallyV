# Service OCR độc lập còn lưu trong repo

Đối chiếu ngày 14/11/2026. **Đánh giá chấm công TallyV không còn gọi service này.** Client `app/services/ocr.py`, schema OCR và các biến `OCR_ENABLED`, `OCR_BACKEND`, `OCR_API_URL`, `OCR_DOCKER_API_URL`, `OCR_API_TIMEOUT` của backend chấm công đã được gỡ. Không khởi động service hoặc thêm các biến này để chạy đánh giá; dùng [tiền xử lý PII/VLM](vlm-evidence.md).

`ocr_service/`, `requirements-ocr.txt`, `scripts/run_ocr.sh` và tests service được giữ như công cụ thử nghiệm độc lập. Nó không phải package tiền xử lý PII, không nằm trong stack Compose chính và không được nối lại vào luồng ảnh gốc. Chatbot OCR trang PDF dùng implementation riêng trong `app/chatbot`, không gọi service PP-OCR này.

## Mã và cấu hình riêng của service

[`ocr_service/app.py`](../ocr_service/app.py) định nghĩa FastAPI app riêng, không import settings hoặc DB TallyV. Model CPU được nạp một lần trong lifespan; khóa suy luận xử lý tuần tự. Service kiểm tra file weights local trước khi nạp; không cần cài Paddle vào backend TallyV. Các phiên bản dependency của công cụ nằm trong [`requirements-ocr.txt`](../requirements-ocr.txt) và [`ocr_service/Dockerfile`](../ocr_service/Dockerfile).

| Biến của service | Mặc định / ý nghĩa |
| --- | --- |
| `OCR_SERVICE_MODELS_DIR` | `../tallyv-ocr/models` tính từ gốc repo; cần thư mục detector và recognizer |
| `OCR_SERVICE_MODEL_VARIANT` | `small`; cũng nhận `medium` |
| `OCR_SERVICE_API_TOKEN` | Rỗng; khi có giá trị, `POST /ocr` yêu cầu Bearer token |
| `OCR_SERVICE_CPU_THREADS` | `4`, giới hạn từ 1 đến 64 |
| `OCR_SERVICE_MAX_UPLOAD_BYTES` | `8388608` bytes |
| `OCR_SERVICE_MAX_IMAGE_PIXELS` | `16000000` pixel |

Hai thư mục weights phải có tên `PP-OCRv6_<variant>_det` và `PP-OCRv6_<variant>_rec`; mỗi thư mục chứa `inference.json`, `inference.pdiparams`, `inference.yml`. Checksum small từng được chuẩn bị nằm tại [`models.sha256`](../ocr_service/models.sha256); file này không mô tả weights medium. Không có bước tải weights nào trong hướng dẫn vận hành chấm công hiện tại.

## Chạy riêng cho thử nghiệm bằng ảnh giả lập

Khi đã có môi trường OCR và weights phù hợp, chạy từ gốc repo:

```sh
OCR_PYTHON=/absolute/path/to/ocr-venv/bin/python \
OCR_SERVICE_MODELS_DIR=/absolute/path/to/models \
bash scripts/run_ocr.sh
```

Launcher mặc định dùng Python ở `../tallyv-ocr/venv/bin/python`, bind `127.0.0.1:8001`, một Uvicorn worker; có thể đổi cổng qua `OCR_SERVICE_PORT`. Nó không tự cài package hoặc tải weights. Service đọc `OCR_SERVICE_*` từ môi trường process, không tự nạp `.env` của TallyV.

```sh
curl --fail-with-body http://127.0.0.1:8001/health
curl --fail-with-body -F 'file=@/absolute/path/to/synthetic.png' http://127.0.0.1:8001/ocr
```

Nếu đã đặt token, thêm header `Authorization: Bearer <token>` cho `POST /ocr`. API không có xác thực khi token rỗng; công cụ thử nghiệm này không cung cấp gateway production hoặc chứng minh cô lập mạng chỉ bằng các cờ thư viện offline.

## Hợp đồng HTTP

`GET /health` trả trạng thái và tên model khi startup hoàn tất. `POST /ocr` nhận multipart trường `file`, chỉ nhận PNG/JPEG và trả cấu trúc như sau:

```json
{
  "model": "PP-OCRv6_small",
  "lines": [{"text": "SYNTHETIC TEXT", "score": 0.99, "box": [0.1, 0.1, 0.9, 0.2]}]
}
```

`box` là tọa độ chuẩn hóa 0–1, có thể vắng mặt. `score` là điểm nhận dạng, không phải xác suất đúng đã hiệu chuẩn. File tạm được chuẩn hóa, đặt tên phía server và xóa sau yêu cầu. Lỗi file trả 400/413/415; thiếu/sai token trả 401; lỗi suy luận trả 503 với thông báo chung, không log nội dung ảnh/chữ.

Tests trong [`tests/test_ocr_service.py`](../tests/test_ocr_service.py) dùng runtime giả để kiểm tra HTTP, giới hạn, token và xóa file tạm. Chúng không đo chất lượng OCR thật và không nối service vào đánh giá chấm công.

Bản nghiên cứu cũ về cách tự host nằm tại [self-host-ppocrv6-small.md](self-host-ppocrv6-small.md); đó là tài liệu lịch sử, không phải bước bắt buộc của TallyV.
