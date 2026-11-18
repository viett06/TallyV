# Kiến trúc và vận hành

Luồng nghiệp vụ từ tiếp nhận, tổng hợp, đánh giá và phân loại đến thiết kế tự động cập nhật SAP được mô tả trong [Kiến trúc core chấm công và SAP](core-attendance-sap.md).

| Vị trí | Trách nhiệm |
| --- | --- |
| `main.py`, `app/api/` | FastAPI, xác thực, routes, tải file và phục vụ giao diện |
| `app/services/`, `app/crud/` | Quy tắc nghiệp vụ, truy vấn, điều phối xử lý và giao dịch |
| `app/models/`, `alembic/` | SQLAlchemy, metadata và migrations PostgreSQL |
| `app/worker.py` | Đồng bộ email, nhập Excel, tạo demo và chạy Assistant |
| `app/services/evidence_masking.py`, `evidence_privacy.py`, `image_background.py` | Che ảnh, gọi OCR, xác minh ảnh và điều phối phân tích |
| `ocr_service/`, `config/evidence-privacy/` | Detector OCR CPU và profile bố cục |
| `app/assistant/`, `app/chatbot/` | Hai tính năng có cấu hình AI riêng |
| `frontend/src/` | Giao diện React và TypeScript |

PostgreSQL giữ queue bền cho email, demo và Assistant. Worker dùng advisory lock để chỉ có một scheduler. Nhập Excel ghi hồ sơ và hoàn tất job trong cùng giao dịch. Tiền xử lý ảnh chạy sau commit. OCR/VLM dùng background trong process với session database riêng và có thể yêu cầu chạy lại nếu bị gián đoạn. [Vòng đời xử lý ảnh](vlm-evidence.md#chạy-nền-và-xử-lý-lỗi)

Dữ liệu gửi ra VLM gồm ảnh đã che, thông tin nghiệp vụ đã lọc từ hồ sơ và quy tắc phân loại. Artifact lưu private. Khi khôi phục hoặc chuyển môi trường, giữ cả database và kho file. [Vận hành kho dữ liệu](object-storage.md)

Backend dùng `app/locales/vi.json` cho thông báo. Frontend dùng `frontend/src/locales/vi.json` cho nội dung giao diện. Nhãn nhập/xuất và enum nghiệp vụ được quản lý riêng theo hợp đồng dữ liệu hiện có.

## Kiểm tra khi thay đổi

- Chạy test, Ruff, build frontend và kiểm tra cấu hình Compose theo [README](../README.md). Test dùng database và kho file tạm; các case gọi VLM và mailbox dùng HTTP giả lập.
- Với schema mới, chạy `alembic heads`, áp dụng `alembic upgrade head` trên môi trường đích rồi dùng `alembic check` khi cần đối chiếu database và ORM.
- Với OCR/VLM, dùng [workbook giả lập](../samples/attendance-ocr-demo.xlsx). Kiểm tra preview của ảnh đủ điều kiện, ảnh camera chuyển HR và lỗi OCR chặn đánh giá. Kết quả mock xác minh hành vi phần mềm. Để kiểm tra model thật, dùng ảnh giả lập trên môi trường đã cấu hình.
