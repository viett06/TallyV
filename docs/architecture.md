# Kiến trúc backend TallyV

Cấu trúc tham khảo Docentra local: `app/api`, `app/schema`, `app/services`, `app/core`, `app/db`, model theo từng bảng, và model registry dành cho Alembic. TallyV giữ tên `app/models` (số nhiều) và thêm `app/crud` theo các folder được tạo sẵn trong dự án.

## Luồng xử lý

```text
HTTP request
  → app/api + app/schema       xác thực HTTP, validate request/response
  → app/services               điều kiện nghiệp vụ, audit, transaction của thao tác HR
  → app/crud                   truy vấn, bộ lọc, phân trang, khóa dòng
  → app/models + app/db        bảng SQLAlchemy, session, kết nối PostgreSQL

Worker
  → app/crud/jobs              claim job có lease / SKIP LOCKED
  → app/services               nhập email/Excel hoặc phân tích
  → commit toàn bộ job         thất bại thì rollback và retry

Alembic
  → app/db/config.py           DATABASE_URL; không cần settings tài khoản web
  → app/db/base_model.py       nạp toàn bộ models vào Base.metadata
  → alembic/versions           áp dụng lịch sử migration
```

## Trách nhiệm từng folder

Quét email chỉ lên lịch `IMPORT_EMAIL`. Nhập Excel tạo trường hợp, phiên bản và kết quả với trạng thái `NOT_STARTED` / `NOT_EVALUATED`; không lên lịch phân tích. HR nhấn **Đánh giá và phân loại** (`POST /api/analysis`) để lên lịch `ANALYZE` cho các phiên bản chưa đánh giá hoặc bị lỗi trong phạm vi đã chọn, gồm cả bản sửa `PROPOSED`. `GET /api/analysis` trả số lượng chờ/đang xử lý/hoàn tất/lỗi và trạng thái tiếp nhận. Đổi quy tắc chỉ làm mất hiệu lực kết quả, cần thao tác đánh giá riêng để chạy lại.

| Folder/file | Chứa | Không đặt tại đây |
|---|---|---|
| `main.py` | `create_app`, đăng ký middleware, AppError handler, router và frontend static | SQL, điều kiện duyệt, đọc workbook |
| `app/api` | APIRouter theo auth/catalog/cases/emails/files/jobs/rules/health; Depends; cookie; HTTP file/stream response | Logic duyệt, tạo phiên bản, câu SQL |
| `app/api/deps.py` | `DBSession`, `HRUser`, `Filters`; lấy session/user cho request | Commit hoặc chỉnh nội dung case |
| `app/schema` | Request/response Pydantic, bộ lọc, schema JSON từ model | ORM table, gọi database/network |
| `app/services` | Nghiệp vụ, trả dữ liệu cho router, staging thay đổi ORM, audit, transaction của HR | FastAPI Request/Response/Depends hoặc câu SQL |
| `app/crud` | Truy vấn, join, filter, phân trang, aggregate và khóa bản ghi | HTTPException, commit, gửi email, gọi OCR/LLM |
| `app/models` | SQLAlchemy table mapping, index, constraint, foreign key, default | Session, FastAPI, gọi dịch vụ |
| `app/db` | Declarative Base, URL kết nối, engine, SessionLocal và model registry | Nghiệp vụ HR hoặc secret đăng nhập web |
| `app/core` | Settings, AppError, middleware, timestamp và chuyển dữ liệu JSON | Query nghiệp vụ |
| `app/demo` | Danh mục và generator hoàn toàn mô phỏng | Đầu vào có hồ sơ thật hoặc đáp án cho bộ phân loại |
| `scripts` | CLI gọi vào app; các kiểm tra/evaluation/reset local | Logic route hoặc được worker import làm thư viện |
| `app/worker.py` | Dispatch công việc, transaction job, retry và scheduler | Câu SQL chọn job hoặc import CLI scripts |

Health endpoint chỉ thực hiện probe database qua CRUD; không có quy trình nghiệp vụ cần service ở giữa.

## Các module nghiệp vụ chính

- `services/cases.py`: điều kiện đủ duyệt, kết luận HR, duyệt lô nguyên tử, quyết định bản sửa, phân tích lại và audit. Row lock được lấy qua `crud/cases.py` trước khi thay trạng thái.
- `services/imports.py`: tiếp nhận email đúng phạm vi, nhập từng file, nhập được dòng hợp lệ dù có dòng lỗi, chống trùng, đề xuất phiên bản mới. Không tự commit giữa một job.
- `services/excel.py`: kiểm tra XLSX, ngày, công thức, giới hạn giải nén và liên kết ảnh. Không import DB, ORM hoặc HTTP client; có thể kiểm thử bằng bytes workbook.
- `services/analysis.py`: đề xuất nguyên nhân bằng quy tắc/Ollama, OCR local và kiểm tra đủ/thiếu/mâu thuẫn. Schema model nằm ở `schema/analysis.py`. Module không tự xác nhận HR.
- `services/exports.py`: dựng workbook và ép giá trị nguồn thành string để chống công thức. Router `api/files.py` chịu trách nhiệm HTTP StreamingResponse.
- `services/email_provider.py`: EmailProvider interface và Mailpit adapter nội bộ.
- `services/auth.py`: kiểm tra tài khoản, giới hạn thử đăng nhập, giải mã session và kiểm tra role. `api/deps.py` chuyển cookie HTTP thành lời gọi nghiệp vụ.
- `services/security.py`: password hash/verify và session signer. `services/storage.py`: lưu UUID, hash và kiểm tra đường dẫn local.

## Transaction và lỗi

CRUD không commit. Các thao tác HR và sửa rule commit trong service sau khi đã kiểm tra điều kiện và thêm audit. Nếu service phát sinh `AppError`, request giữ nguyên JSON lỗi `{"detail": ...}` và HTTP status như trước. Session kết thúc sẽ rollback phần chưa commit.

Import/phân tích được gọi bởi worker. Worker commit phần claim job trước, rồi xử lý job trong session/transaction mới. Dữ liệu nghiệp vụ và trạng thái DONE được commit cùng nhau. Lỗi giữa chừng rollback và job được lên lịch retry, không tạo case/ảnh trùng. Một worker/scheduler duy nhất giữ advisory lock PostgreSQL.

Response Pydantic giới hạn rõ các trường public. Đường dẫn file local không xuất hiện trong metadata ảnh/attachment; ảnh/file vẫn được phục vụ bằng endpoint có kiểm tra HR. Timestamp giữ biểu diễn ISO cũ (`+00:00`) để tương thích client và bản snapshot trước refactor.

## Quản lý database bằng Alembic

`app/db/base.py` chỉ định nghĩa Base. Mỗi file trong `app/models` import cùng Base này; `app/models/__init__.py` đăng ký các lớp. `app/db/base_model.py` nạp registry và là nguồn `target_metadata` trong `alembic/env.py`.

`app/db/config.py` đọc DATABASE_URL từ môi trường hoặc `.env`, chuẩn hóa `postgresql://` sang driver `postgresql+psycopg`. Không cần SECRET_KEY/DEMO_PASSWORD để import metadata. SQLite chỉ dùng cho kiểm thử cô lập; demo chạy PostgreSQL.

Khi thêm/sửa bảng:

1. Thêm/sửa model ở `app/models/<ten_bang>.py`.
2. Nếu là model mới, đăng ký import và `__all__` trong `app/models/__init__.py`.
3. Chạy `alembic revision --autogenerate -m "describe schema change"`.
4. Đọc lại migration, đặc biệt thao tác drop/rename/backfill, trước khi áp dụng.
5. Chạy `alembic upgrade head`, rồi `alembic check`.

Khi dùng Docker, thêm `docker compose exec api` trước lệnh Alembic. Lần refactor kiến trúc này không thay bảng/column/constraint nên giữ nguyên migration `305ed758b40c`, không tạo migration rỗng và không reset dữ liệu.

## Thêm một tính năng HTTP

1. Định nghĩa request/response trong `app/schema`.
2. Thêm query/row lock cần thiết vào `app/crud` theo chức năng.
3. Viết điều kiện nghiệp vụ/audit trong `app/services`, xác định transaction cần commit ở service hay worker.
4. Thêm route ở `app/api`, khai báo response_model và dùng `DBSession`/`HRUser`.
5. Đăng ký router ở `app/api/__init__.py` nếu có file router mới.
6. Kiểm thử hành vi qua endpoint hoặc interface của workflow; không dùng database demo cho unit tests.

Không cần thêm generic repository, base service hoặc domain layer trống chỉ để chuyển tiếp lời gọi. Các query dùng chung có thể gọi trực tiếp repository đang sở hữu chúng.

## Tương thích và xác minh

- 23 thao tác API giữ nguyên method/path; frontend và cookie session tiếp tục tương thích.
- 14 định nghĩa bảng, tên column, nullable, primary key, foreign key và default giữ nguyên.
- 18 kiểm thử nghiệp vụ ban đầu giữ nguyên nội dung xác minh; cập nhật import theo package mới.
- Bổ sung kiểm thử các read view sau partial import, contract AppError, timestamp ISO, và model registry không kéo theo web settings/session.
- Các lệnh CLI `python -m scripts.seed_catalog`, `python -m scripts.send_demo`, `python -m app.worker` vẫn dùng được. Generator và danh mục hiện nằm trong `app/demo`; worker không import CLI.
- Ruff được cấu hình ở `ruff.toml`; cài qua `requirements-dev.txt`.

### Kết quả kiểm tra sau khi cập nhật Docker

- `pytest`: **22 passed**; Ruff check/format và `git diff --check` đạt.
- `docker compose exec api alembic check`: **No new upgrade operations detected**.
- Snapshot trước/sau refactor khớp: **60 case, 10 email**, hash ảnh, audit, kết luận HR và job nghiệp vụ không đổi.
- Smoke chỉ đọc trên PostgreSQL thật: validate cả **60 chi tiết case**, **10 chi tiết email**, bootstrap/dashboard/jobs/auth, bộ lọc kỳ **24/36**, xuất Excel theo bộ lọc **6 dòng**. Không sửa dữ liệu nghiệp vụ để kiểm tra.
- API healthy và worker tiếp tục chạy tại `http://127.0.0.1:8000`.
