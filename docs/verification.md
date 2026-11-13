# Kiểm thử và phạm vi xác minh

Đối chiếu mã nguồn ngày 14/11/2026. Tài liệu này mô tả kiểm tra cho đường tiền xử lý PII/VLM hiện tại. [Báo cáo ngày 30/10/2026](archive/verification-before-vlm.md) là lịch sử của engine đã bỏ; số liệu OCR, RULE_BASED và demo 60/60 trong đó không phải chất lượng VLM.

## Lệnh kiểm tra hiện tại

Chạy từ thư mục gốc, sau khi cài môi trường Python 3.11+ và dependency:

```sh
venv/bin/python -m pip install -r requirements-dev.txt
venv/bin/python -m pytest -q
venv/bin/python -m pytest -q image-preprocessing/tests
venv/bin/ruff check app main.py scripts tests image-preprocessing/src image-preprocessing/tests alembic
git diff --check
venv/bin/alembic heads
docker compose config --quiet
```

```sh
cd frontend
npm ci
npm run build
```

Tests ứng dụng dùng database SQLite và storage tạm; HTTP model/mail/HR được mock ở các bài kiểm tra tương ứng. Tests của subproject chạy độc lập không cần DB hoặc model. `alembic heads` chỉ kiểm tra lịch sử migration; không chứng minh DB đang chạy đã cập nhật.

Mốc kiểm tra ghi nhận sau refactor: **259 passed, 1 skipped** ở suite ứng dụng và **13 passed** ở subproject; frontend build, Ruff, `git diff --check` và Compose config đạt. Đây là kết quả của lượt kiểm tra đã ghi nhận, không phải bảo đảm cho một môi trường triển khai khác. Có hai cảnh báo MSAL về response mode trong test OAuth local. Không chạy migration trên DB thật hoặc gọi model bằng ảnh thật trong lượt refactor đó.

## Những hành vi đã có kiểm thử

| Phạm vi | Bài kiểm tra chính |
| --- | --- |
| Che pixel mặt/PII, bỏ metadata, không dùng HTTP trong tiền xử lý | `image-preprocessing/tests`, `tests/test_evidence_vlm.py` |
| Chặn ảnh không khớp, file hỏng, profile mơ hồ/tắt và ảnh không có vùng nghiệp vụ dùng được | `tests/test_evidence_vlm.py` |
| Chờ toàn bộ tiền xử lý, kiểm tra checksum/revision, không fallback ảnh gốc, chống kết quả lượt cũ ghi đè | `tests/test_evidence_vlm.py` |
| VLM chỉ nhận ảnh đã xử lý ở cả ba provider; phản hồi phải đúng category và đủ mỗi ảnh một lần | `tests/test_evidence_vision.py`, `tests/test_evidence_vlm.py` |
| Lọc định danh trong giải trình và chặn mô tả rule có định danh được phát hiện | `tests/test_assessment_input.py` |
| Không tạo queue ảnh mới; background API/worker import; trạng thái và đánh giá lại | `tests/test_manual_analysis.py`, `tests/test_evidence_vlm.py` |
| Ảnh thủ công không được duyệt lô; lô hỗn hợp bị từ chối nguyên tử; kết luận HR riêng với kết quả máy | `tests/test_evidence_vlm.py`, `tests/test_pipeline.py`, `tests/test_composio.py` |
| Thay quy tắc vô hiệu hóa kết quả; category do HR tạo dùng được trong VLM | `tests/test_rule_catalog.py` |
| Migration PII và bỏ điều kiện OCR giữ ảnh/kết quả lịch sử | `tests/test_evidence_privacy_migration.py` |
| Intake, phiên bản sửa, quyền tải file và storage local/S3 | `tests/test_pipeline.py`, `tests/test_read_models.py`, `tests/test_storage.py` |

Suite còn có kiểm tra riêng cho Outlook/Composio, HR mô phỏng, Assistant và Chatbot. Tests `test_ocr_service.py` chỉ dành cho service OCR độc lập còn lưu trong repo; chúng không có nghĩa đánh giá chấm công vẫn gọi OCR.

## Kiểm tra trên môi trường triển khai

Áp dụng migration theo quy trình triển khai, khởi động lại API/worker với dependency mới và kiểm tra bằng dữ liệu giả lập. Với profile mặc định rỗng, yêu cầu đánh giá phải kết thúc ở `MANUAL_REVIEW`, không gọi VLM. Với profile thử đã được kiểm tra, xem đúng ảnh preview sau che, theo dõi `GET /api/analysis`, kiểm tra kết quả VLM và audit HR. Không chỉ theo dõi `/api/jobs`, vì background ảnh không có job queue riêng.

Kiểm tra restart bằng cách xác minh ảnh và trạng thái còn lưu; tác vụ đang chạy không tự khôi phục. Nếu lượt cũ bị gián đoạn, dùng `POST /api/cases/{id}/reanalyze?restart_background=true` để lập lượt mới. Thao tác này không mở quyền gửi ảnh chưa xử lý.

`scripts/smoke.py` còn giả định có 60 hồ sơ, mọi kết quả `COMPLETED`, đủ dòng duyệt lô và chờ qua `/api/jobs`; vì vậy **chưa phù hợp làm smoke mặc định cho đường PII/VLM**. Script này còn ghi quyết định HR. Không chạy nguyên trạng để nghiệm thu kiến trúc mới.

`scripts/evaluate.py` chỉ tổng hợp category của kết quả `COMPLETED` so với `data/demo/answers.json`; không gọi model, không đo che PII hoặc chất lượng từng ảnh. Nó còn có thể đọc kết quả lịch sử trong DB. Nếu dùng cho VLM, cần tập thử riêng, kết quả mới đúng revision và phạm vi dữ liệu rõ ràng. Profile mặc định rỗng không tạo benchmark VLM.

## Giới hạn bằng chứng

Chưa có nghiệm thu độ bao phủ PII trên ảnh bệnh viện, benchmark VLM thật, đo tải lớn hoặc kiểm toán mạng/production của kiến trúc mới. Tests HTTP mock kiểm tra hợp đồng và ranh giới ứng dụng, không chứng minh provider thật hoạt động hay không lưu dữ liệu. Không dùng kết quả của engine cũ làm cam kết cho VLM.

Thay đổi docs không tự chạy migration, đổi `.env`, cấu hình profile, tải weights hoặc bật suy luận trên ảnh thật. Xem [hướng dẫn vận hành](vlm-evidence.md) và [kiến trúc](architecture.md).
