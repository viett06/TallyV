# Che PII và đánh giá ảnh chấm công

Luồng chấm công dùng **PP-OCRv6 Small** nội bộ và **Qwen3-VL 8B Instruct** qua OpenRouter.

1. Backend đối chiếu checksum, kích thước và mốc UI với đúng một profile. Backend tạo ảnh nền đen, chép các vùng nghiệp vụ cho phép, rồi che đen khuôn mặt, tên, mã nhân viên và các vị trí PII đã cấu hình.
2. OCR chỉ nhận ảnh trung gian đã che. OCR trả hộp tọa độ chữ. Backend che các hộp phát hiện được ngoài vùng chữ nghiệp vụ cho phép.
3. Backend lưu PNG cuối cùng với checksum, revision cấu hình và trạng thái OCR. VLM chỉ nhận PNG vượt qua cả ba kiểm tra, sau khi cả lượt tiền xử lý hoàn tất. Ảnh gốc ở kho riêng để HR xem khi cần.

OCR định vị chữ. Profile xác định vùng mặt và PII cố định. Ảnh sai bố cục, bố cục mơ hồ hoặc ảnh hỏng chuyển HR rà soát. Lỗi OCR hay tọa độ sai chặn lượt gọi VLM. Với hồ sơ có cả ảnh hợp lệ và ảnh cần rà soát, VLM chỉ nhận các ảnh hợp lệ và HR vẫn phải xử lý hồ sơ.

## Chạy OCR nội bộ

Tải `inference.json`, `inference.pdiparams` và `inference.yml` của [PP-OCRv6_small_det](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det) vào `ocr_service/models/PP-OCRv6_small_det/`. Trọng số nằm ngoài Git. Kiểm tra checksum rồi khởi động từ gốc repo.

```sh
(cd ocr_service/models && shasum -a 256 -c ../models.sha256)
docker compose up -d --build ocr
docker compose exec -T ocr python -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8001/health').read().decode())"
```

Stack Docker mặc định gọi OCR tại `http://ocr:8001` trong mạng nội bộ. Khi API chạy trực tiếp, dùng `compose.local.yaml` để mở cổng OCR trên loopback, hoặc chạy OCR trực tiếp theo lệnh bên dưới. API native dùng `EVIDENCE_OCR_URL=http://127.0.0.1:8001`. Nếu đặt `OCR_SERVICE_API_TOKEN`, dùng cùng giá trị cho OCR, API và worker. Có thể đổi thư mục trọng số bằng `OCR_SERVICE_MODELS_DIR`.

Nếu chạy OCR trực tiếp, cài PaddlePaddle CPU 3.3.0 và `requirements-ocr.txt` trong Python 3.11 riêng, rồi chạy `bash scripts/run_ocr.sh`. Script dùng `.venv-ocr/bin/python` hoặc đường dẫn từ `OCR_PYTHON`.

`POST /ocr` nhận multipart `file` dạng PNG/JPEG. Phản hồi chứa model `PP-OCRv6_small_det` và `regions` là các hộp `[trái, trên, phải, dưới]` chuẩn hóa từ 0 đến 1.

## Cấu hình vùng che và VLM

Đặt `OPENROUTER_API_KEY` trong `.env`. Profile mặc định nằm ở `config/evidence-privacy/profiles.json`, có thể đổi bằng `EVIDENCE_PRIVACY_PROFILES_PATH`. Profile đi kèm chỉ khớp bảng thông tin trong [workbook giả lập](../samples/attendance-ocr-demo.xlsx).

Một profile `FACEID` hoặc `DEVICE_ERROR` gồm kích thước ảnh, mốc UI tĩnh, các vùng giữ lại (`keep_regions`) và các vùng che (`pii_regions`, `face_region`). `FACEID` yêu cầu vùng mặt. `keep_text_regions` chỉ dành cho các ô nghiệp vụ đã kiểm tra như giờ hoặc mã lỗi. Vùng này phải nằm trong vùng giữ lại, tách khỏi vùng mặt/PII. Xem [spec mẫu](../config/evidence-privacy/layout-spec.example.json).

```sh
venv/bin/python -m scripts.configure_evidence_privacy \
  --reference /duong-dan-noi-bo/reference.png \
  --spec /duong-dan-noi-bo/layout-spec.json \
  --profiles config/evidence-privacy/profiles.json \
  --preview /duong-dan-noi-bo/preview.png
```

CLI tạo preview che theo bố cục. Sau khi kiểm tra và bật profile, dùng **Xử lý PII trước** để xem PNG đã qua OCR trong TallyV. Chỉ đưa profile đã kiểm tra trên mẫu được phép sử dụng vào vận hành.

## Chạy nền và xử lý lỗi

FastAPI `BackgroundTasks` và `asyncio.to_thread` điều phối ảnh trong process. Worker nhập email có thể khởi động tiền xử lý sau khi lưu hồ sơ. VLM chỉ chạy khi HR yêu cầu đánh giá.

| Endpoint | Dùng để |
| --- | --- |
| `POST /api/privacy/preprocess` | Chạy riêng bước che PII và OCR |
| `POST /api/analysis` | Tiền xử lý rồi đánh giá ảnh đủ điều kiện |
| `GET /api/analysis` | Xem trạng thái của lượt đánh giá |
| `GET /api/evidence/{id}/sanitized` | Tải bản PNG đủ điều kiện |
| `POST /api/cases/{id}/reanalyze?restart_background=true` | Chạy lại hồ sơ khi lượt nền bị gián đoạn |

Sau khi sửa profile, xử lý lại để tạo bản PNG theo revision mới. [Kiểm thử và vận hành](architecture.md#kiểm-tra-khi-thay-đổi)
