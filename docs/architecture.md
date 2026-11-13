# Kiến trúc TallyV

Đối chiếu mã nguồn ngày 14/11/2026. TallyV gồm ba module dùng chung xác thực, PostgreSQL và kho file riêng tư: rà soát chấm công, Assistant và Chatbot quy định. Mỗi module có đường gọi AI riêng; việc bỏ LLM văn bản/OCR/JEV trong đánh giá chấm công không loại bỏ AI của Assistant hoặc Chatbot.

## Luồng chấm công

```text
Email → SYNC → IMPORT_EMAIL → Excel/ảnh gốc trong kho riêng tư
                             → hồ sơ, phiên bản, kết quả NOT_STARTED
                             → commit → tiền xử lý PII chạy nền, chưa gọi VLM

HR yêu cầu đánh giá → BackgroundTasks → run_batch
  → xử lý PII offline cho toàn bộ lượt hồ sơ
  → kiểm tra revision cấu hình, manifest và checksum các bản ảnh
  → VLM chỉ nhận ảnh đã xử lý hợp lệ + giải trình đã lọc + quy tắc HR
  → kết quả đề xuất → HR rà soát, xác nhận, xuất Excel
```

Nhập email không tự đánh giá bằng AI. Tạo hồ sơ qua API có ảnh cũng chỉ lên lịch tiền xử lý. `POST /api/analysis` và `POST /api/cases/{id}/reanalyze` chạy tiền xử lý trước rồi đánh giá. `POST /api/privacy/preprocess` chỉ xử lý PII. Phạm vi hàng loạt gồm cả phiên bản sửa `PROPOSED` theo bộ lọc hiện có.

Chỉ hai nhóm bố cục `FACEID` và `DEVICE_ERROR` đã cấu hình được phép tạo ảnh gửi model. Profile mặc định rỗng chặn tất cả ảnh. Ảnh không khớp bố cục, file hỏng hoặc PII chưa xử lý được chuyển cho nhân viên. Hồ sơ trộn ảnh hợp lệ và ảnh chưa hỗ trợ chỉ gửi phần hợp lệ cho VLM, vẫn có điều kiện thiếu và không được duyệt lô. Không có thao tác cho phép bỏ qua tiền xử lý. Xem [phạm vi bằng chứng](evidence-images.md) và [chi tiết PII/VLM](vlm-evidence.md).

## Trách nhiệm module

| Folder/file | Trách nhiệm |
| --- | --- |
| `main.py`, `app/api` | FastAPI, middleware, xác thực HTTP, router, file response và frontend đã build |
| `app/schema` | Pydantic request/response, bộ lọc, hợp đồng kết quả VLM và DTO truyền giữa các hàm nền |
| `app/services` | Nghiệp vụ, audit, transaction thao tác HR, adapter storage và điều phối xử lý |
| `app/crud` | Truy vấn, bộ lọc, phân trang, aggregate và row lock; không commit hoặc gọi model |
| `app/models`, `app/db` | SQLAlchemy mapping, registry, engine, session và metadata Alembic |
| `app/core`, `app/demo` | Cấu hình dùng chung, lỗi, thời gian, locale; danh mục và dữ liệu giả lập |
| `image-preprocessing/` | Package Python độc lập, xử lý pixel offline; không import app, DB, HTTP hoặc model AI |
| `app/assistant`, `app/chatbot` | Nghiệp vụ và AI riêng của Assistant/Chatbot |
| `app/worker.py` | Queue PostgreSQL hiện có cho email, demo, Assistant và backend HR mô phỏng |
| `scripts` | CLI quản trị, sinh demo và công cụ kiểm tra; kiểm tra phạm vi từng script trước khi chạy |
| `frontend` | React, TypeScript, Vite; các workspace dùng chung shell |

Các module chính của đường ảnh:

| Module | Trách nhiệm |
| --- | --- |
| `tallyv_image_preprocessing` | Giải mã, kiểm tra bố cục/anchor, giữ vùng nghiệp vụ, tô đen mặt/PII và xuất PNG mới |
| `services/evidence_privacy.py` | Đọc profile, lập lượt xử lý, lưu `EvidencePrivacy`, xác minh và nạp bản ảnh đã xử lý |
| `services/image_background.py` | Chạy hai giai đoạn qua asyncio; chờ toàn bộ tiền xử lý xong trước VLM |
| `services/assessment_input.py` | Lọc định danh khỏi giải trình, chuẩn bị quy tắc HR; không gọi model |
| `services/evidence_vlm.py` | Prompt đánh giá, kiểm tra category và một kết quả cho từng ảnh |
| `services/evidence_vision.py` | HTTP transport tới Ollama, OpenRouter hoặc Qwen Cloud; chỉ nhận `SanitizedImage` |
| `services/analysis.py` | Kiểm tra yêu cầu/revision, tổng hợp đủ/thiếu/mâu thuẫn và lưu kết quả; không tự xác nhận HR |
| `services/cases.py`, `services/rules.py` | Quyết định HR, bản sửa, duyệt lô nguyên tử và hủy hiệu lực khi đổi quy tắc |

Không còn client đánh giá LLM văn bản, OCR, Gemini/JEV hoặc đối chiếu MobileNet/cosine/SIFT trong đường đánh giá. Các cột/bảng lịch sử vẫn giữ, không được dùng làm đầu vào VLM hoặc điều kiện duyệt lô.

## Background và queue

API đăng ký FastAPI `BackgroundTasks` sau response. `run_batch` đưa pixel, storage/DB và HTTP đồng bộ sang `asyncio.to_thread`; mỗi lần xử lý mở session riêng. Có giới hạn hai tác vụ xử lý pixel đồng thời trong mỗi process. Sau import email commit, worker gọi trực tiếp bộ chạy nền qua executor rồi asyncio. Không có broker, queue privacy/AI hoặc worker ảnh riêng.

API không tạo job `ANALYZE` mới. Nhánh tương thích trong worker đưa job `ANALYZE` còn tồn từ bản cũ qua tiền xử lý hiện tại. Không còn lập chỉ mục `INDEX_EVIDENCE`. Theo dõi đánh giá qua `GET /api/analysis` và trạng thái PII từng ảnh, không chờ job ảnh trong `/api/jobs`.

Background trong process không bảo đảm sống qua restart. Trạng thái và artifact lưu bền trong DB/storage, nhưng tác vụ không tự được phát lại như queue. Có thể lập lượt mới bằng `reanalyze?restart_background=true` sau khi xác định lượt cũ bị gián đoạn; request ID chặn lượt cũ ghi đè lượt mới. Đây là giới hạn hiện tại, queue tách privacy/AI là bước sau.

## Transaction và lưu trữ

CRUD không commit. Nghiệp vụ HR kiểm tra điều kiện, thêm audit rồi commit trong service. Worker commit claim trước, sau đó xử lý job trong session mới; dữ liệu import và trạng thái hoàn tất commit cùng nhau. Lỗi import rollback và retry theo lease/backoff. Một worker/scheduler giữ advisory lock PostgreSQL.

Ảnh xử lý nền có transaction riêng theo giai đoạn; không nằm trong transaction HTTP hoặc import. Lỗi tiền xử lý chặn VLM cho cả lượt. Lỗi model không có fallback phân loại văn bản. Đổi rule hủy hiệu lực kết quả liên quan; kết quả VLM kiểm tra lại snapshot quy tắc trước khi lưu.

File dùng [storage local/S3](object-storage.md). Ảnh gốc giữ riêng với bản PNG đã che; DB lưu UUID, checksum và revision. Endpoint ảnh gốc và ảnh sau che đều yêu cầu HR; ảnh sau che không có fallback về ảnh gốc. Không mount storage công khai. Không có phân quyền bucket riêng giữa privacy và AI ở phiên bản này.

## Database và cập nhật

`app/db/base_model.py` nạp registry cho Alembic. Không dùng `create_all` để quản lý database đang chạy; SQLite dành cho tests, PostgreSQL cho ứng dụng. Chatbot dùng pgvector trên PostgreSQL.

Các migration mới của đường ảnh là `628d41ef2b37` (thêm `evidence_privacy`) và `739e52fa3c48` (bỏ điều kiện quy tắc OCR cũ). Không xóa ảnh, text OCR hoặc kết quả lịch sử. Dùng `alembic heads` để kiểm tra head của checkout thay vì dựa vào số bảng hoặc head của tài liệu cũ.

```sh
venv/bin/python -m pip install -r requirements-dev.txt
venv/bin/alembic heads
# Trên database đã chọn và đã sao lưu theo quy trình triển khai:
venv/bin/alembic upgrade head
venv/bin/alembic check
```

Alembic đọc `DATABASE_URL` qua `app/db/config.py` mà không cần cấu hình đăng nhập web. Docker API chạy migration và seed danh mục trước Uvicorn. Cài lại dependency và build lại image khi package con thay đổi; chỉ mount lại `app/` không cập nhật package đã cài trong image.

## Assistant, Chatbot và HR mô phỏng

Assistant dùng `/api/assistant`, chủ sở hữu theo user, job `ASSISTANT_GENERATE` và cấu hình `ASSISTANT_*`. Chế độ Hybrid dùng LangGraph và runner tùy chọn; xem [hướng dẫn hiện tại](assistant.md). Không cần worker DraftV riêng.

Chatbot HR và cổng `/employee` dùng kho PDF, OCR trang scan, embedding/BM25, rerank và model trả lời riêng. Những thành phần này vẫn tồn tại trong `app/chatbot`; xem [tra cứu quy định](chatbot-retrieval.md).

`hr_mock_app:app` và backend gửi điều chỉnh thử nghiệm còn được giữ để bảo toàn dữ liệu. Giao diện chính chỉ có bảng công mô phỏng tham khảo; chưa kết nối SAP thật. Xem [phạm vi SAP](sap-demo.md).

## Thêm tính năng và kiểm tra

Đặt hợp đồng HTTP trong `schema`, route mỏng trong `api`, điều kiện nghiệp vụ/audit trong `services`, truy vấn và khóa trong `crud`. Đăng ký model mới với registry và review migration trước khi áp dụng. Không thêm lớp chuyển tiếp trống chỉ để tách folder.

Lệnh kiểm tra và giới hạn bằng chứng nghiệm thu nằm tại [verification.md](verification.md). Báo cáo lịch sử không thay cho kiểm tra trên bản triển khai hiện tại.
