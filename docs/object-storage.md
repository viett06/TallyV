# Kho file MinIO / AWS S3 của TallyV

Excel đính kèm và ảnh bằng chứng được lưu vào bucket private; PostgreSQL giữ metadata, tên file UUID, SHA-256 và liên kết nghiệp vụ. Ứng dụng dùng Boto3/S3, không dùng SDK riêng của MinIO. `STORAGE_BACKEND=local` giữ chế độ lưu file cũ cho kiểm thử hoặc chuyển đổi có chủ đích; `s3` không tự quay về local khi kho lỗi.

## Luồng dữ liệu

```text
Email → worker → bucket tallyv-files / tallyv/<UUID>.bin
Excel → tách ảnh → bucket tallyv-files / tallyv/<UUID>.png
HR → API có đăng nhập → đọc object → trả Excel / ảnh
Background async → đọc ảnh gốc → xử lý PII offline → object PNG UUID mới
Sau khi cả lượt xử lý xong → kiểm tra bản ảnh → VLM → kết quả PostgreSQL
```

Các cột `attachments.path`, `evidence_files.path` giữ tên UUID, không lưu URL có hostname hoặc đường dẫn máy. `evidence_privacy.sanitized_path` trỏ tới bản PNG sau che riêng, kèm SHA-256 và revision profile. Ảnh gốc không bị ghi đè. VLM chỉ nhận bản PNG đã kiểm tra; ảnh chưa hỗ trợ chuyển nhân viên. File xuất Excel được tạo trong bộ nhớ. Xem [luồng PII/VLM](vlm-evidence.md).

`data/` còn dùng cho dữ liệu cũ được giữ làm bản đối chiếu và file sinh demo/báo cáo kiểm thử. Không phải nơi lưu mới cho attachment/ảnh khi bật S3. Weights model được quản lý riêng, không nằm trong bucket file nghiệp vụ. Không cần service OCR cho đánh giá chấm công.

## Khởi tạo trên máy mới

```bash
python3 scripts/init_env.py
# Nếu .env đã tồn tại, tạo cấu hình MinIO mà vẫn giữ secrets hiện có:
python3 -m scripts.configure_storage
# Cài dependency cho API chạy native:
venv/bin/python -m pip install -r requirements.txt
# Build MinIO và chạy công việc tạo bucket/account một lần:
docker compose up -d --build minio minio-init
```

MinIO image được build từ source chính thức: server `RELEASE.2025-10-15T17-29-55Z`, client `RELEASE.2025-08-13T08-35-41Z`. Không phụ thuộc tag `latest` hoặc binary cũ trên Docker Hub. Lần đầu build cần tải Go/dependency và có thể mất nhiều phút. MinIO Community đã được archive và không còn được duy trì; cấu hình này dành cho phát triển local trước khi chuyển sang S3. [Tình trạng upstream](https://github.com/minio/minio), [bản vá dùng để build](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z).

- S3 endpoint từ máy: `http://127.0.0.1:9000`.
- S3 endpoint từ container: `http://minio:9000`.
- Object browser: [http://127.0.0.1:9001](http://127.0.0.1:9001).
- Đăng nhập browser bằng `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` trong `.env`; không đưa chúng vào Git.
- Ứng dụng dùng cặp `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` riêng, chỉ có quyền với bucket/prefix TallyV, không quản trị MinIO.
- Bucket private; tải file qua API TallyV có kiểm tra đăng nhập. Cổng MinIO chỉ publish trên loopback.

## Chuyển dữ liệu cũ

`scripts/migrate_storage.py` hiện chỉ đọc các file được `attachments` và `evidence_files` tham chiếu. Script **chưa sao chép** bản ảnh trong `evidence_privacy`, artifact Assistant hoặc PDF Chatbot. Các bước bên dưới chỉ dành cho kho cũ chỉ có file nguồn chấm công; không dùng làm chuyển kho đầy đủ cho cài đặt đã có các dữ liệu khác. Cần kiểm kê, sao lưu và chuyển mọi object được các module tham chiếu trước khi đổi backend. Giữ nguyên UUID/prefix/checksum của từng loại file.

Dừng mọi process API và worker có thể ghi file hoặc chạy background ảnh trước khi chuyển. Công cụ chỉ kiểm tra advisory lock worker PostgreSQL; khóa này không kiểm tra các background trong API. Không chạy reset demo trong quá trình này.

```bash
docker compose stop api worker
# Dừng cả Uvicorn native nếu có; chạy CLI native từ môi trường đã cấu hình.
# Chỉ kiểm tra file nguồn, hash và các object đã có; chưa upload:
venv/bin/python -m scripts.migrate_storage --source ./data
# Upload file nguồn chấm công mà script hỗ trợ, rồi đối chiếu SHA-256:
venv/bin/python -m scripts.migrate_storage --source ./data --apply
# Chỉ bật sau khi toàn bộ file đã được kiểm tra thành công:
python3 -m scripts.configure_storage --activate
```

Script không sửa database, không xóa bản gốc và không ghi đè object đã tồn tại có nội dung khác. Có thể chạy lại để kiểm tra hoặc tiếp tục một lần chuyển bị gián đoạn. File ngoài hai bảng nguồn mà script đọc không tự đưa vào bucket, kể cả khi module khác đang tham chiếu.

Khởi động lại API native để nạp cấu hình mới. Với môi trường API native + Docker worker hiện tại:

```bash
docker compose -f compose.yaml -f compose.outlook.yaml -f compose.local.yaml build worker
docker compose -f compose.yaml -f compose.outlook.yaml -f compose.local.yaml up -d --no-deps --force-recreate worker
```

Nếu chạy cả API và worker bằng container:

```bash
docker compose -f compose.yaml -f compose.outlook.yaml up -d --build api worker
```

Đối với bản cài mới chưa có dữ liệu, dùng `python3 -m scripts.configure_storage --activate` rồi chạy stack; không cần migration. `scripts/init_env.py` đã bật S3 sẵn cho .env mới.

## Lưu bền và vận hành

MinIO dùng named volume `tallyv_object_data`. Restart/recreate container giữ object. Đây vẫn là lưu trữ trên ổ đĩa Docker Desktop của máy, chưa phải cloud, dự phòng nhiều máy hay backup. Cần giữ cả PostgreSQL và object data để khôi phục được hồ sơ. Không chạy `docker compose down -v` nếu muốn giữ dữ liệu.

`minio-init` kết thúc với mã 0 sau khi tạo bucket private và account/policy; trạng thái Exited (0) là bình thường. Có thể chạy lại sau khi đổi cấu hình bucket/account. Chưa cấu hình TTL tự xóa hồ sơ. `scripts.reset_demo` là thao tác phá hủy cho môi trường Mailpit mô phỏng riêng, chỉ chấp nhận local/MinIO local; không reset bucket AWS. Script không kiểm kê đầy đủ artifact PII/Assistant/Chatbot và không phải công cụ xóa dữ liệu đa module. Khi dùng S3, bản PNG sau che có thể còn mồ côi sau khi bản ghi bị reset. Không dùng script trên database chia sẻ với Outlook/Assistant/Chatbot đang cần giữ.

## Chuyển sang AWS S3

Logic nghiệp vụ và module storage không đổi. Các bước triển khai cần thực hiện:

1. Tạo bucket AWS private trong region phù hợp và cấp quyền IAM cho prefix TallyV (GetObject, PutObject, DeleteObject; ListBucket/GetBucketLocation nếu dùng công cụ quản trị/chuyển kho).
2. Sao chép các object từ MinIO sang S3, giữ nguyên prefix `tallyv/`, UUID và metadata SHA-256; kiểm tra lại nội dung với checksum trong database. Sao lưu database trước khi đổi kho.
3. Đặt `STORAGE_BACKEND=s3`, `S3_BUCKET=<bucket>`, `S3_REGION=<region>`, `S3_ENDPOINT_URL=`, `S3_DOCKER_ENDPOINT_URL=`, `S3_ADDRESSING_STYLE=auto`.
4. Xóa giá trị `S3_ACCESS_KEY_ID` và `S3_SECRET_ACCESS_KEY` để Boto3 dùng credential chain/IAM role của môi trường AWS. Không đưa khóa AWS vào source. Nếu dùng credential chain trên máy local, cấu hình AWS profile qua môi trường.
5. Chạy overlay AWS bên dưới và khởi động lại API/worker, kiểm tra tải Excel, ảnh gốc, preview PII, artifact của từng module và ghi file mới. Giữ MinIO cùng bản local cũ để đối chiếu trước khi dọn dữ liệu có chủ đích.

```bash
# Docker Compose >= 2.24.4. Overlay bỏ phụ thuộc minio-init.
# Chỉ chỉ định các dịch vụ ứng dụng; không khởi động minio/minio-init trên AWS.
docker compose -f compose.yaml -f compose.outlook.yaml -f compose.aws-storage.yaml up -d --build api worker
```

Boto3 tự chọn endpoint AWS khi `endpoint_url` không được đặt và hỗ trợ IAM role qua credential chain. [AWS: cấu hình Boto3](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html), [AWS: credentials](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html).

## Vai trò container

| Container | Trách nhiệm |
| --- | --- |
| `api` | Backend HTTP, UI, thao tác HR/tải file và background PII/VLM do API nhận. Khi chạy native, process đó sở hữu các background tương ứng. |
| `worker` | Queue email/demo/Assistant/HR mô phỏng; sau import commit gọi tiền xử lý PII nền qua code, chưa đánh giá AI. Không có queue ảnh mới. |
| `db` | PostgreSQL: hồ sơ, metadata/hash, trạng thái PII, kết quả VLM/lịch sử, audit, queue và bảng Assistant/Chatbot. File nghiệp vụ lưu ở storage. |
| `minio` | Kho object S3 local cho Excel và ảnh; volume riêng giữ dữ liệu qua restart. |
| `minio-init` | Tạo bucket private và account/policy; chạy xong thì thoát thành công. |
| `hr-mock` | Bảng công/hệ thống HR mô phỏng để thử nghiệm, không phải SAP thật. Có thể dùng cùng image worker nhưng command khác. |
| `mailpit` | Hộp thư SMTP giả lập, chỉ có khi thêm `compose.demo.yaml`; stack Outlook/Composio mặc định không chứa container này. |
| `ollama` | Runtime tùy chọn. Override `compose.llm.yaml` chuẩn bị model text cho Assistant; không tự cấu hình Qwen3-VL của đường đánh giá. |

Nhóm `tallyv` trong Docker Desktop là tên Compose project, không phải một container hay database riêng.

Service OCR thử nghiệm còn mã riêng trong repo nhưng không phải thành phần vận hành đánh giá chấm công. Xem [trạng thái service](ocr-api.md).

## Báo cáo lịch sử ngày 03/11/2026

Số liệu bên dưới thuộc lần kiểm tra trước refactor PII/VLM. Chưa kiểm tra lại chuyển kho toàn bộ module hoặc AWS thật bằng các số liệu đó; phần OCR là phép thử cũ, không phải đường xử lý hiện tại.

- Build thành công MinIO từ source, image API và worker có Boto3; cài Boto3 cho cả `.venv` và `venv` dùng bởi IDE.
- Sao chép 72 file được database tham chiếu từ `data/` sang MinIO, đọc lại SHA-256 khớp toàn bộ. Giữ nguyên database và file nguồn.
- Worker thực tế dùng `STORAGE_BACKEND=s3`, endpoint `http://minio:9000`; đọc lại đủ 72 file khớp checksum.
- API native qua TestClient đăng nhập và tải đủ 72 file, nội dung khớp SHA-256; API chưa đăng nhập trả 401, bucket ẩn danh trả 403.
- App account bị chặn thao tác đọc policy quản trị bucket. MinIO có thể liệt kê bucket đã được account cấp quyền; điều này không cấp quyền quản trị.
- Ghi một ảnh chữ giả lập mới vào MinIO, đọc từ kho để gọi OCR PP-OCRv6 thật, nhận đúng mã `MP036`, rồi xóa riêng object kiểm thử. Không tạo hồ sơ nghiệp vụ.
- `minio-init` chạy lại thành công; object browser trả 200 và MinIO healthy với named volume `tallyv_object_data`.
- `pytest`: 173 passed; Ruff lint toàn bộ đạt, format các file Python thay đổi đạt; hai cấu hình Compose local/AWS validate thành công. Chưa chạy đối chiếu với bucket AWS thật.
