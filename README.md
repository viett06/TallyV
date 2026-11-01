# TallyV — MVP rà soát điều chỉnh chấm công

Ứng dụng nghiệp vụ HR bằng tiếng Việt, hỗ trợ hộp thư Outlook thử nghiệm của người phát triển và chế độ Mailpit dành riêng cho dữ liệu mô phỏng. Quy trình hiện tại: tiếp nhận email/Excel → đánh giá và phân loại khi HR bấm nút → HR rà soát, xác nhận và xuất kết quả. Chưa kết nối SAP thật.

## Phạm vi tích hợp SAP

Hiện tại TallyV chỉ **tổng hợp, đánh giá và phân loại** để HR dùng kết quả và nhập nghiệp vụ lên SAP. Mục tiêu sau này là tích hợp **TallyV thành module/ứng dụng mở rộng trong SAP**, rồi **tự động hóa phần nhập SAP sau khi HR kiểm tra và xác nhận**. Mỗi kiểu case sai công số có thể cần cách nhập, trường dữ liệu và thao tác SAP khác nhau; cần mô tả và ánh xạ đúng từng trường hợp. Không quy bài toán này thành sửa giờ vào/ra bằng một API chung. Việc dựng một cổng giả lập hay gửi sửa giờ sang dịch vụ HR riêng không được coi là đã đạt mục tiêu tích hợp.

Trong lúc chưa đăng ký được môi trường SAP, tạm giữ **Bảng công mô phỏng** để xem dữ liệu mẫu. Cổng ứng dụng demo và màn hình gửi điều chỉnh từ TallyV đã được bỏ khỏi giao diện. Xem [phạm vi và trạng thái tích hợp SAP](docs/sap-demo.md).

## Kết nối Outlook cho MVP

The synthetic MVP can read real test Outlook emails through **Composio-managed OAuth**, without creating your own Microsoft app registration. Create a Composio Hobby project, then run `python -m scripts.configure_composio` locally to enter its project API key through a hidden prompt. The setup creates a read-only Outlook auth config and updates `.env` while preserving application/database secrets. Follow [the end-to-end Composio guide](docs/composio-mvp.md), then restart API/worker and connect the test mailbox from TallyV. Use only fictional departments, employees, workbooks and evidence. Email subjects require both `[TALLYV-MVP]` and `[DCC]`. The initial connection syncs automatically; subsequent syncs run from the Sync button by default to conserve the free allowance. Email and attachments pass through Composio. Never use hospital production data in this environment.

The Microsoft-direct connector remains available with `OUTLOOK_TRANSPORT=microsoft`; see [docs/outlook.md](docs/outlook.md). Hospital deployment requires separate approval and a separate production environment. Neither this MVP nor choosing Microsoft-direct establishes hospital compliance.

Các bước demo bên dưới dùng `MAIL_PROVIDER=mailpit`; dữ liệu Mailpit được giữ riêng khỏi dữ liệu Outlook khi hiển thị và xuất báo cáo.

## Chạy demo từ đầu

Cần Docker Desktop/Compose, Python 3.11+ để tạo cấu hình. Lần build đầu có tải dependency; xử lý dữ liệu chạy tại local.

```bash
python3 scripts/init_env.py
# Set MAIL_PROVIDER=mailpit in .env for this demo.
# Read DEMO_USERNAME / DEMO_PASSWORD locally.
docker compose up --build -d
```

Mở **http://127.0.0.1:8000**, đăng nhập `hr.demo` bằng `DEMO_PASSWORD` trong `.env`. Nhấn **Tạo dữ liệu demo**. Worker tạo ảnh/Excel local, gửi **10 email qua SMTP Mailpit**, đọc lại qua API và nhập khoảng **60 trường hợp**, 5 khoa/phòng, 40 nhân viên, kỳ lương và đợt đang chọn (26 tháng trước–25 tháng hiện tại). Không seed trực tiếp trường hợp vào database. Sau khi tiếp nhận xong, nhấn **Đánh giá và phân loại**; chờ khoảng 20–60 giây cho OCR, xem tab Tiến trình xử lý.

- Mailpit local: http://127.0.0.1:8025; SMTP `127.0.0.1:1025`.
- PostgreSQL demo: localhost `54329`, user/database `tallyv`; mật khẩu được tạo trong `.env`.
- Toàn bộ cổng chỉ bind loopback. Không công khai lên Internet.
- `docker compose down` rồi `docker compose up -d` giữ nguyên database, file, hộp thư và trạng thái nhờ named volumes.
- Gửi lại dữ liệu mẫu: nút **Gửi bộ email mẫu** hoặc `docker compose exec api python -m scripts.send_demo`. Message-ID cố định giúp tiếp nhận lặp không tạo trường hợp trùng.

`init_env.py` không ghi mật khẩu vào log và không ghi đè `.env` đã tồn tại. `.env.example` chỉ là mẫu, không chứa secret thực tế.

## Quy trình demo 5 phút

1. **0:00–0:45** Đăng nhập, nhấn Tạo dữ liệu demo. Mở Tiến trình xử lý để thấy SMTP → đồng bộ → nhập. Dữ liệu hiển thị **Chưa đánh giá**; nhấn **Đánh giá và phân loại** để chạy OCR và phân tích.
2. **0:45–1:30** Chọn kỳ tháng 10 rồi tháng 9. Xem số khoa/phòng đã gửi và số liệu thay đổi theo database. Chọn Tất cả kỳ để thấy 10 email / 60 trường hợp.
3. **1:30–2:15** Mở Hộp thư: khoa 1 có dòng ngày mơ hồ và ảnh sai anchor; file sai mẫu; email không Excel; email ngoài phạm vi. Xem số dòng nguồn = nhập + trùng + dòng lỗi. Lỗi liên kết ảnh cấp file được báo riêng. Nhấn Đồng bộ nhiều lần: không tạo trùng.
4. **2:15–3:15** Mở MP-1-001: so sánh bản gốc với bản sửa, ghi lý do và giữ/áp dụng phiên bản. Xem MP-1-007/008 có ngày/mã nhân viên trong ảnh không khớp. MP-1-006 có ảnh không đọc được. MP-1-012 có hai ảnh cùng dòng.
5. **3:15–4:15** HR sửa phân loại, đánh dấu cần bổ sung kèm lý do. Lọc Đủ theo quy tắc demo, chọn dòng và xác nhận lô sau hộp xác nhận. Dòng ngoại lệ không chọn được; backend kiểm tra lại, giao dịch duyệt lô là toàn bộ hoặc không có dòng nào.
6. **4:15–5:00** Xem lịch sử ai sửa gì/khi nào/lý do. Lọc kỳ, trạng thái rồi Xuất Excel. Xác nhận trong TallyV là kết quả rà soát; cập nhật công số sẽ thực hiện trong SAP khi có môi trường tích hợp.

## Cấu trúc

Backend được tổ chức theo các folder trong `app/`, tham khảo cách tách router, schema, services, model registry và DB session của Docentra. Giữ `models/` và `crud/` theo cấu trúc của TallyV.

```text
main.py                  # Tạo FastAPI app, middleware, error handler, ghép router
hr_mock_app.py           # API HR mô phỏng chạy riêng tại cổng 8010
app/
  api/                   # Router theo tính năng + dependencies HTTP
  schema/                # Pydantic request, response, bộ lọc, schema phân loại
  services/              # Nghiệp vụ HR, nhập Excel, phân tích, file và xuất Excel
  crud/                  # Truy vấn SQLAlchemy, phân trang, row lock, hàng đợi
  models/                # Mỗi bảng một file; __init__.py đăng ký model
  core/                  # Cấu hình, AppError, middleware, UTC, serialization
  db/                    # URL database, Base, model registry và Session
  demo/                  # Danh mục và bộ sinh email/Excel/ảnh giả lập
  worker.py              # Chạy job và quản lý transaction, retry, scheduler
alembic/versions/        # Lịch sử migration database
scripts/                 # CLI: khởi tạo, gửi demo, smoke, đánh giá, reset
frontend/                # React + TypeScript + Vite + Tailwind
```

Router nhận dữ liệu qua `schema`, lấy session/user qua dependencies, gọi `services`. Nghiệp vụ gọi `crud` để truy vấn và khóa dòng; `crud` không commit. Thao tác HR commit trong service, job nhập/phân tích commit trong worker để có thể rollback/retry toàn bộ. XLSX parser không phụ thuộc database hay network.

`app/db/base_model.py` là điểm nạp đầy đủ metadata cho Alembic. Ứng dụng không dùng `create_all` để quản lý schema. Chi tiết và cách thêm tính năng/model mới: [Kiến trúc backend](docs/architecture.md).

Cài công cụ phát triển và kiểm tra Python:

```bash
pip install -r requirements-dev.txt
ruff check app main.py alembic/env.py scripts tests
ruff format --check app main.py alembic/env.py scripts tests
python -m pytest -q
```

## Quy tắc dữ liệu mô phỏng

Tiêu đề được phép: `[DCC] [YYYY-MM] ...`, gửi từ `department1@demo.invalid` đến `department5@demo.invalid`, người nhận `hr@demo.invalid`, kỳ phải có trong danh mục. Email ngoài phạm vi giữ trạng thái **Cần kiểm tra phạm vi**, không tự nhập. Email đã đọc vẫn được tiếp nhận.

Sheet `DieuChinh` cần đúng 9 cột theo thứ tự:

`Mã trường hợp | Mã nhân viên | Họ tên | Phòng ban | Ngày xảy ra | Ca làm | Loại lượt thiếu | Lý do/giải trình | Bằng chứng`

- Ngày là ô ngày Excel hoặc `YYYY-MM-DD`; từ chối `01/02/2026` vì mơ hồ.
- Ca/lượt thiếu/giải trình có thể trống để HR thấy thiếu thông tin. Mã trường hợp, mã nhân viên, họ tên, phòng và ngày phải hợp lệ để tạo trường hợp.
- Ảnh neo cột I, dòng tương ứng. Nhiều ảnh cùng dòng được giữ riêng. Neo ngoài cột I, neo không xác định hoặc two-cell trải nhiều dòng bị báo lỗi; không ghép theo phỏng đoán.
- File cũ được lưu UUID bất biến. SHA-256 chống file trùng. Mã trường hợp + fingerprint nội dung/ảnh chống dòng trùng và phân biệt bản sửa.
- Bản sửa là `PROPOSED`. Nội dung đang dùng giữ nguyên; xác nhận cũ mất hiệu lực. HR phải chấp nhận/từ chối bản sửa kèm lý do. Khi áp dụng, nguồn cũ thành `SUPERSEDED`; kết luận mới chờ HR.
- **Phân loại nguyên nhân được nêu** khác **đủ dữ kiện theo quy tắc demo**. Tất cả đều chờ HR xác nhận. Không suy ra đủ công từ ảnh nhận diện hoặc camera.
- HR được sửa phân loại/kết luận/ghi chú; không sửa nguồn. Xác nhận ngoại lệ riêng lẻ cần đánh dấu đã xem bằng chứng và lý do tối thiểu 10 ký tự. Không duyệt lô ngoại lệ.
- Bảng Quy tắc mô phỏng cấu hình yêu cầu ảnh, OCR, ca và loại lượt thiếu. Thay đổi quy tắc đưa dữ liệu liên quan về **Chưa đánh giá** và hủy hiệu lực xác nhận; nhấn **Đánh giá và phân loại** để cập nhật kết quả. Đây **không phải quy định thật**.

## OCR local

Docker image cài Tesseract + ngôn ngữ eng/vie trước khi chạy. Mặc định `OCR_ENABLED=true`, không cần tải model. Ảnh mẫu chứa mã MPxxx, ngày ISO và trạng thái chữ rõ để kiểm tra trích xuất bằng Tesseract thật. Bộ đối chiếu MVP dùng chữ English trong ảnh mẫu; không tuyên bố hỗ trợ mọi ảnh tiếng Việt thực tế.

- Tắt: `OCR_ENABLED=false` trong `.env`, `docker compose up -d --force-recreate api worker`.
- Nếu engine lỗi/không tồn tại: trạng thái `UNAVAILABLE`, OCR text rỗng; nếu ảnh không có chữ đọc được: `UNREADABLE`. Không tạo OCR giả.
- Lưu riêng text thực đọc, trường trích xuất và điểm đối chiếu. OCR không xác thực tính xác thực của ảnh.
- Ảnh camera là hình hành lang minh họa vẽ bằng Pillow local, không có người thật. Không nhận diện khuôn mặt.

## Ollama tùy chọn

Mặc định `PROCESSING_MODE=RULE_BASED`: nhãn **Chế độ quy tắc**, không sử dụng LLM. Không có model được tải khi app khởi động.

Chuẩn bị model *trước* khi bật chế độ model:

```bash
# Profile tùy chọn; không được chạy trong cấu hình mặc định.
docker compose --profile llm up -d ollama
# Chỉ nối mạng chuẩn bị để tải model. Không gửi nội dung email/Excel/ảnh.
docker network connect tallyv_access tallyv-ollama-1
docker compose exec ollama ollama pull qwen2.5:7b
docker network disconnect tallyv_access tallyv-ollama-1
```

Sau đó đặt `PROCESSING_MODE=LOCAL_LLM`, `OLLAMA_URL=http://ollama:11434`, `OLLAMA_MODEL=qwen2.5:7b` trong `.env`, chạy `docker compose up -d --force-recreate api worker`. Phân tích lại các trường hợp muốn thử. Đầu vào model chỉ có mã trường hợp, giải trình và kết quả kiểm tra bằng chứng; không truyền họ tên hoặc ảnh gốc. Ollama chỉ nằm trên mạng internal khi xử lý. Schema JSON được Pydantic kiểm tra. Lỗi kết nối/schema được lưu `FAILED`, `UNKNOWN`, yêu cầu kiểm tra; **không fallback ngầm**. Kết quả vẫn phải qua kiểm tra code và HR.

## Kiểm thử

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
cd frontend && npm ci && npm run build
```

Unit/integration API tests dùng database SQLite tạm riêng để không đụng demo. Luồng thực tế PostgreSQL, Mailpit, worker và OCR được kiểm tra bằng smoke script:

```bash
# Sau khi chạy stack và tạo demo; script sẽ ghi một kết quả xác nhận demo
# và một yêu cầu bổ sung demo để kiểm tra nghiệp vụ.
python -m scripts.smoke
# Đánh giá phân loại với đáp án riêng, không truyền đáp án cho bộ phân loại.
docker compose exec api python -m scripts.evaluate
```

Muốn kiểm tra read/unread: dừng worker, gửi mẫu, đánh dấu tất cả email đã đọc trong Mailpit, rồi bật worker và đồng bộ. Muốn kiểm tra lưu bền: restart api/worker, so số email/trường hợp/audit và mở lại ảnh. Báo cáo nghiệm thu thực tế nằm trong `docs/verification.md`.

## Reset demo (phá hủy dữ liệu mô phỏng đã nhập)

```bash
docker compose stop worker
# Không có --confirm đúng chuỗi thì script từ chối xóa.
docker compose exec api python -m scripts.reset_demo --confirm RESET-SYNTHETIC-DEMO
docker compose start worker
```

Reset giữ tài khoản HR/danh mục, xóa trường hợp, file, job và email Mailpit của ứng dụng. Worker đang chạy thì advisory lock chặn reset. Không dùng `docker compose down -v` nếu muốn giữ dữ liệu.

## Phát triển local

```bash
docker compose up -d db mailpit
source venv/bin/activate
alembic upgrade head
python -m scripts.seed_catalog
uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log
# Terminal khác, không chạy đồng thời worker Docker:
python -m app.worker
# Terminal khác, nếu không chạy dịch vụ hr-mock bằng Docker:
uvicorn hr_mock_app:app --host 127.0.0.1 --port 8010 --no-access-log
# Frontend khi phát triển: cd frontend && npm run dev
```

Local Python cần Tesseract riêng nếu bật OCR; không có thì UI báo cần HR xem ảnh. Khi dùng Vite proxy, mở http://127.0.0.1:5173. Sau `npm run build`, FastAPI phục vụ bundle ngay tại port 8000 (khởi động lại nếu trước đó chưa có thư mục dist).

Nếu chạy API bằng PyCharm/uvicorn trên máy nhưng dùng worker Docker cho Outlook, dùng override để worker đọc cùng mã nguồn và lưu file vào `./data`, cùng thư mục với API local:

```bash
docker compose -f compose.yaml -f compose.outlook.yaml -f compose.local.yaml up -d --no-deps hr-mock worker
```

Không chạy thêm worker Python cùng lúc. Khi đổi từ named volume Docker sang thư mục local, cần sao chép dữ liệu cũ từ `/app/data` của worker trước khi tạo lại container; giữ nguyên tên file và kiểm tra hash để các bản ghi đã tiếp nhận vẫn đọc được. Sau khi sửa mã Python, khởi động lại worker Docker để nạp mã mới. Khi trở lại chạy toàn bộ bằng Docker, bỏ override local và chuyển các file mới về named volume trước khi khởi động API/worker.

## Giới hạn thực tế và bảo mật

- MVP dùng nội bộ trên máy demo; không phải hệ thống production/SSO. Một tài khoản HR demo, cookie ký HMAC, HttpOnly/SameSite Strict, kiểm tra Origin/Fetch Metadata, giới hạn thử đăng nhập đơn giản trong process.
- Secret lấy từ biến môi trường; log chỉ ID job và loại lỗi. Không log mật khẩu, email, giải trình hay OCR đầy đủ. Tắt access log Uvicorn theo lệnh mặc định.
- Không mount storage công khai. Ảnh/file đi qua API có quyền HR, đường dẫn UUID được kiểm tra, file tải về dùng attachment. UI render email thành text, không chạy HTML hoặc tự mở URL.
- Workbook không thực thi macro/công thức, từ chối macro/external workbook links, kiểm tra kích thước nén/giải nén/ảnh. Công thức trong dòng gây lỗi dòng. Excel xuất cưỡng bức kiểu chuỗi cho giá trị không đáng tin.
- AI/OCR vẫn xử lý cục bộ; không dùng cloud AI/OCR, telemetry exporter, remote font, CDN, gửi email phản hồi hoặc SAP. Trình duyệt gọi API cùng origin và chuyển sang trang Microsoft khi HR đăng nhập. Mailpit/Ollama giới hạn host nội bộ; Outlook chỉ gọi Microsoft identity và Graph.
- Worker Compose gốc chỉ nối mạng internal. Chế độ Outlook dùng thêm `compose.outlook.yaml` để worker truy cập Microsoft identity/Graph theo quyền HR đã cấp. Cổng API/Mailpit/Postgres vẫn chỉ bind loopback. Chưa cấu hình Entra hoặc chưa cấp quyền thì không đọc được hộp thư thật.
- Giới hạn: XLSX 15 MB, tối đa 2000 dòng/30 cột, 60 MB giải nén; ảnh PNG/JPEG do Pillow đọc được, 8 MB/16 triệu pixel. Không PDF/OCR tài liệu nhiều trang, không macro, không nhận diện khuôn mặt.
- Retry không sửa nội dung nguồn sai: HR phải yêu cầu file sửa. Email ngoài phạm vi giữ lại để xem và gửi lại đúng mẫu, chưa có tính năng gán khoa/kỳ thủ công.
- Một worker, polling 30 giây, chưa tối ưu khối lượng lớn, chưa có antivirus/quarantine chuyên dụng hoặc cơ chế phục hồi file mồ côi sau process crash. File đã được lưu mà transaction rollback có thể còn UUID mồ côi; không làm phát sinh trường hợp trùng.
- Model/OCR không được coi là bằng chứng phê duyệt công. Không tuyên bố độ chính xác trên dữ liệu bệnh viện thật.

Tham khảo kỹ thuật: [Mailpit API](https://mailpit.axllent.org/docs/api-v1/), [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html), [SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/engines.html).
