# TallyV gọi dịch vụ OCR tự host

Luồng: HR nhấn **Đánh giá và phân loại** hoặc **Phân tích lại** → worker đọc ảnh đã lưu → `POST /ocr` → model local → JSON → trích xuất và đối chiếu mã nhân viên/ngày như trước. Tiếp nhận email/Excel không tự chạy OCR. Kết quả OCR không tự xác nhận công.

## Mã dịch vụ

`ocr_service/app.py` là dịch vụ FastAPI riêng, không import cấu hình/database của TallyV. Nó kiểm tra đủ file model local rồi nạp PP-OCRv6 small một lần trong lifespan; một worker và khóa suy luận xử lý lần lượt các yêu cầu. Các model xoay/nắn ảnh tùy chọn đều tắt.

Chỉ nhận ảnh PNG/JPEG, mặc định tối đa 8 MiB và 16 triệu pixel. File tạm do server tự đặt tên, chuẩn hóa ảnh theo EXIF và xóa sau mỗi yêu cầu. Không lưu ảnh hay chữ nhận dạng vào log. Lỗi ảnh trả 400/413/415; lỗi suy luận trả 503 với thông báo chung. Nếu nạp model lúc khởi động thất bại, server không báo sẵn sàng.

API dùng trên loopback cho demo, chưa có xác thực hoặc giới hạn tải ở gateway. Không đưa cổng này ra Internet. Kiểm tra đường dẫn model local và tắt kiểm tra nguồn không thay thế firewall hay kiểm chứng chạy offline.

## Chuẩn bị model local

Git chỉ lưu mã dịch vụ, cấu hình chạy và checksum; thư mục `ocr_service/models/` chứa model tải về được ignore. Bộ model mặc định dùng khi chạy native hoặc Compose nằm tại `../tallyv-ocr/models/`, bên ngoài repo. Không cần chép thêm weights vào repo.

Bộ model đã đối chiếu với kho PaddlePaddle trên Hugging Face:

| Model | Revision cố định |
| --- | --- |
| [PP-OCRv6_small_det](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det/tree/106c97591b235f607453300d9fc8c1cad1b25488) | `106c97591b235f607453300d9fc8c1cad1b25488` |
| [PP-OCRv6_small_rec](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec/tree/bd619643acac4b9650c040234da8d944476ee3f1) | `bd619643acac4b9650c040234da8d944476ee3f1` |

Mỗi model cần ba file: `inference.json`, `inference.pdiparams`, `inference.yml`. Checksum SHA-256 của cả sáu file được lưu tại [`ocr_service/models.sha256`](../ocr_service/models.sha256).

Nếu máy đã có model, chỉ kiểm tra checksum từ thư mục gốc repo:

```bash
repo_dir="$PWD"
models_dir="$repo_dir/../tallyv-ocr/models"
(cd "$models_dir" && shasum -a 256 -c "$repo_dir/ocr_service/models.sha256")
```

Trên máy mới, chạy khối Bash sau từ thư mục gốc repo để tải đúng revision và kiểm tra toàn bộ file. Chỉ bước chuẩn bị này cần Internet; không chạy lại bước tải khi dịch vụ đang sử dụng model.

```bash
set -euo pipefail
repo_dir="$PWD"
models_dir="$repo_dir/../tallyv-ocr/models"
for model in PP-OCRv6_small_det PP-OCRv6_small_rec; do
    case "$model" in
        PP-OCRv6_small_det) revision=106c97591b235f607453300d9fc8c1cad1b25488 ;;
        PP-OCRv6_small_rec) revision=bd619643acac4b9650c040234da8d944476ee3f1 ;;
    esac
    mkdir -p "$models_dir/$model"
    for filename in inference.json inference.pdiparams inference.yml; do
        curl --fail --location --retry 3 \
            "https://huggingface.co/PaddlePaddle/$model/resolve/$revision/$filename" \
            --output "$models_dir/$model/$filename"
    done
done
(cd "$models_dir" && shasum -a 256 -c "$repo_dir/ocr_service/models.sha256")
```

Chỉ khởi động OCR khi cả sáu file đều báo `OK`. Nếu chọn thư mục model khác, thay `models_dir` khi chuẩn bị và đặt `OCR_SERVICE_MODELS_DIR` khi chạy native hoặc sửa bind mount của container tương ứng. Khi nâng cấp model, cập nhật cả revision và checksum có chủ đích.

Weights từng được commit vẫn còn trong lịch sử Git. Việc ignore và bỏ theo dõi chỉ áp dụng cho các commit tiếp theo, không viết lại lịch sử hoặc xóa file model trên máy.

## Khởi động bằng môi trường bạn đã chuẩn bị

Giữ nguyên hai thư mục weights trong `../tallyv-ocr/models/` và môi trường `../tallyv-ocr/venv/`. Dừng API thử cũ bằng Ctrl+C trong Terminal đang chạy nó, rồi chạy:

```bash
cd /Users/levanviet/Documents/Workspace/vinmec/TallyV
bash scripts/run_ocr.sh
```

Launcher dùng Python trong môi trường OCR có sẵn, nhưng chạy mã `ocr_service.app` của TallyV. Không dùng lại file `ocr_api.py` cũ ở thư mục bên cạnh.

Có thể đổi vị trí môi trường và weights:

```bash
OCR_PYTHON=/absolute/path/to/ocr-venv/bin/python \
OCR_SERVICE_MODELS_DIR=/absolute/path/to/models \
bash scripts/run_ocr.sh
```

Nếu cần tạo môi trường mới, dùng Python 3.11 ARM64 trên macOS, cài PaddlePaddle CPU rồi cài dependency dịch vụ:

```bash
python3.11 -m venv .venv-ocr
.venv-ocr/bin/python -m pip install 'paddlepaddle==3.3.0' -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
.venv-ocr/bin/python -m pip install -r requirements-ocr.txt
OCR_PYTHON="$PWD/.venv-ocr/bin/python" bash scripts/run_ocr.sh
```

`requirements-ocr.txt` chỉ dành cho dịch vụ model. Backend/worker TallyV chỉ cần HTTPX sẵn có, không cài PaddleOCR vào worker Docker.

## Docker image riêng cho OCR

`ocr_service/Dockerfile` dùng Python 3.11 trên Debian Bookworm và PaddlePaddle 3.3.0 CPU, cài dependency từ `requirements-ocr.txt`. Kho CPU chính thức có wheel Python 3.11 cho Linux ARM64 và x86_64; Docker chọn kiến trúc mặc định của máy build. Đây là cấu hình CPU, không phải image GPU/CUDA. [Kho wheel chính thức](https://www.paddlepaddle.org.cn/packages/stable/cpu/paddlepaddle/).

Dockerfile có file ignore riêng, chỉ gửi hai file Python OCR và danh sách dependency vào build context. Không đóng gói venv, weights, `.env`, dữ liệu ảnh hoặc backend TallyV. [Dockerfile-specific ignore](https://docs.docker.com/build/concepts/context/#filename-and-location).

Tự build từ thư mục gốc TallyV:

```bash
cd /Users/levanviet/Documents/Workspace/vinmec/TallyV
docker build -f ocr_service/Dockerfile -t tallyv-ocr:local .
```

Build sẽ kiểm tra dependency và import PaddlePaddle/PaddleOCR, chưa nạp weights. Image chạy bằng user không phải root, có healthcheck và một Uvicorn worker. Bộ weights cần có hai thư mục `PP-OCRv6_small_det` và `PP-OCRv6_small_rec`, mỗi thư mục có đủ file inference như phần kiểm tra startup.

Dừng API native đang giữ cổng 8001 trước khi chạy container. Gắn thư mục model hiện có vào `/models` ở chế độ chỉ đọc:

```bash
docker run -d --name tallyv-ocr --init \
  --shm-size=1g \
  -p 127.0.0.1:8001:8001 \
  --mount type=bind,source=/Users/levanviet/Documents/Workspace/vinmec/tallyv-ocr/models,target=/models,readonly \
  tallyv-ocr:local
```

API bind `0.0.0.0` bên trong container; cổng được publish trên loopback của Mac. Cấu hình worker hiện tại vẫn gọi `http://host.docker.internal:8001`. Không cần chạy thêm OCR API native cùng cổng.

Kiểm tra:

```bash
docker logs --tail 30 tallyv-ocr
docker inspect --format '{{.State.Health.Status}}' tallyv-ocr
curl --fail-with-body http://127.0.0.1:8001/health
```

Các cờ offline trong image chỉ cấu hình thư viện; việc chặn toàn bộ kết nối ra ngoài cần cấu hình mạng riêng. Dockerfile đã được soạn để người dùng tự build; chưa xác nhận build hoặc chạy suy luận bằng image này.

## Hợp đồng HTTP

`GET /health` chỉ phục vụ khi startup đã hoàn tất. `POST /ocr` nhận multipart với trường `file`, trả:

```json
{
  "model": "PP-OCRv6_small",
  "lines": [{"text": "EMPLOYEE: MP036", "score": 0.99}]
}
```

`score` là điểm nhận dạng, không phải xác suất đúng đã hiệu chuẩn. `lines: []` là suy luận thành công nhưng không đọc được chữ. Chuỗi chữ trong ảnh là dữ liệu, không phải lệnh.

Thử bằng Terminal thứ hai:

```bash
curl --fail-with-body http://127.0.0.1:8001/health
curl --fail-with-body -F 'file=@/absolute/path/to/sample.png' http://127.0.0.1:8001/ocr
```

## Cấu hình TallyV

Trong `.env` của TallyV:

```dotenv
OCR_ENABLED=true
OCR_BACKEND=http
OCR_API_URL=http://127.0.0.1:8001
OCR_API_TIMEOUT=30
OCR_DOCKER_API_URL=http://host.docker.internal:8001
```

Backend native dùng `OCR_API_URL`. Compose API/worker dùng `OCR_DOCKER_API_URL`, vì `127.0.0.1` bên trong container là chính container đó. Worker cần đường tới host; trong cấu hình hiện tại `compose.outlook.yaml` đã nối worker vào mạng `access`. Kiểm tra từ worker:

```bash
docker compose exec worker python -c 'import httpx; r=httpx.get("http://host.docker.internal:8001/health", trust_env=False, timeout=5); r.raise_for_status(); print(r.json())'
```

Sau khi sửa `.env`, khởi động lại backend native bằng cách đang dùng. Với worker Docker ở chế độ API native + source bind mount:

```bash
docker compose -f compose.yaml -f compose.outlook.yaml -f compose.local.yaml up -d --no-deps --force-recreate worker
```

Nếu dùng toàn bộ TallyV trong Docker, build/recreate API và worker với các file Compose phù hợp thay vì khởi động thêm worker native.

TallyV kiểm tra schema JSON trước khi dùng, ghép các dòng bằng xuống dòng và giữ luồng trích xuất nghiệp vụ hiện có. HTTP client chỉ dùng endpoint nội bộ theo validator cấu hình, không theo redirect và không dùng proxy từ môi trường. Dịch vụ lỗi/timeout/schema sai → OCR `UNAVAILABLE`, chữ và trường trích xuất cũ được xóa, cần HR kiểm tra. Không tự chuyển sang Tesseract khi HTTP bị lỗi. Để chủ động dùng lại Tesseract, đặt `OCR_BACKEND=tesseract` và khởi động lại worker.

Các kết quả đã đánh giá không tự chạy lại khi đổi engine. Chọn **Phân tích lại** một trường hợp mô phỏng để thử; thao tác này đưa kết luận HR của trường hợp đó về chờ rà soát như luồng hiện có.

## API HTTPS cho PP-OCRv6 Medium

Dùng cùng image OCR của repo khi triển khai từ xa hoặc khi chuyển về nội bộ. Chuẩn bị hai thư mục model `PP-OCRv6_medium_det` và `PP-OCRv6_medium_rec` dưới thư mục weights. Mỗi thư mục cần `inference.json`, `inference.pdiparams` và `inference.yml`. Ghi lại revision và SHA-256 của weights để hai môi trường dùng cùng bản. [Weights phát hiện chữ](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det), [Weights nhận dạng chữ](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec)

Đặt `OCR_SERVICE_MODEL_VARIANT=medium` và `OCR_SERVICE_API_TOKEN` trên máy chạy service, rồi đặt HTTPS phía trước cổng OCR. TallyV gửi token qua header Bearer, gọi `POST /ocr` và yêu cầu phản hồi xác nhận `model=PP-OCRv6_medium`. Khi đổi sang máy nội bộ, giữ nguyên image, weights và cấu hình model. Nếu chạy service local với token, giữ `OCR_BACKEND=remote` và dùng endpoint HTTPS nội bộ. Với service loopback không cần token, dùng `OCR_BACKEND=http`.

## Giới hạn đã biết

Thực nghiệm trong chat cho thấy weights `PP-OCRv6_small_rec` đã tải thiếu các ký tự Việt `Ữ`, `Ệ`, `Ỏ` và chữ thường tương ứng. API hóa không khắc phục giới hạn này. Tích hợp hiện tại nhằm học/vận hành self-host và kiểm thử luồng, chưa xác nhận chất lượng OCR tiếng Việt hoặc trên ảnh bệnh viện.

## Nguồn kỹ thuật

- [PaddleOCR 3.7.0](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/docs/version3.x/pipeline_usage/OCR.en.md)
- [FastAPI UploadFile](https://fastapi.tiangolo.com/tutorial/request-files/) và [lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [HTTPX multipart](https://www.python-httpx.org/quickstart/#sending-multipart-file-uploads)
