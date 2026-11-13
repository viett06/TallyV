# Tiền xử lý PII độc lập và đánh giá VLM chạy nền

Hướng dẫn implementation hiện tại, đối chiếu ngày 14/11/2026. Phạm vi là ảnh bằng chứng chấm công; AI trong Assistant/Chatbot có cấu hình riêng.

## Subproject

`image-preprocessing/` là subproject Python có `pyproject.toml`, dependencies, CLI, cấu hình mẫu và tests riêng. Package `tallyv_image_preprocessing` không import ứng dụng TallyV, FastAPI, DB, storage, queue hoặc model AI. Xem [README của subproject](../image-preprocessing/README.md).

Công nghệ: Pillow để giải mã/chuẩn hóa/xuất ảnh; NumPy để che pixel; OpenCV để tính thống kê chất lượng; Pydantic để kiểm tra cấu hình. Không dùng OCR, Haar, YuNet, embedding hoặc deep learning để xử lý ảnh gốc.

Chỉ hỗ trợ hai nhóm bố cục đã cấu hình: `FACEID` và `DEVICE_ERROR`. Ảnh sai kích thước, không khớp hoặc khớp nhiều mẫu, hỏng file hay không còn bằng chứng sau che chuyển `MANUAL_REVIEW`. Không có chức năng duyệt ảnh chưa hỗ trợ để gửi VLM. HR vẫn xem ảnh gốc trong kho nội bộ và đưa kết luận thủ công.

## Gọi qua code, chưa dùng queue

API dùng FastAPI `BackgroundTasks` để gọi `app/services/image_background.py::run_batch` sau khi gửi response. Orchestrator dùng `asyncio.to_thread` cho xử lý pixel, storage/DB và lời gọi model đang đồng bộ, tránh chặn event loop. Mỗi lần chạy trong thread mở session DB riêng, không tái sử dụng session của request. Tối đa hai tác vụ xử lý ảnh đồng thời trong mỗi process.

Luồng gồm ba pha theo thứ tự:

1. Chuẩn hóa ảnh, xác minh checksum nguồn, đối chiếu kích thước và ít nhất hai anchor UI tĩnh. Tạo mảng đen, chỉ chép `keep_regions`, rồi tô đen đè các vùng mặt và PII. Xuất PNG mới từ pixel, không chép EXIF/XMP/comment/thumbnail; lưu bằng UUID riêng. Ảnh gốc không bị ghi đè.
2. Chờ xử lý xong **toàn bộ lượt hồ sơ**, sau đó xác minh trạng thái, phiên bản cấu hình và checksum để tạo danh sách bản ảnh hợp lệ. Nếu một bước tiền xử lý lỗi, cả lượt không được gọi VLM.
3. Chỉ gọi VLM trên các bản ảnh đã xử lý, không có fallback đọc ảnh gốc. Ảnh chưa hỗ trợ không nằm trong payload. Hồ sơ trộn ảnh hợp lệ và ảnh chưa hỗ trợ vẫn yêu cầu nhân viên đánh giá và không được duyệt lô.

Không tạo các job `PREPROCESS_EVIDENCE`, `RELEASE_VLM` hoặc `ANALYZE` mới cho luồng ảnh VLM. Worker chỉ giữ nhánh chuyển tiếp job `ANALYZE` tồn từ bản cũ qua tiền xử lý hiện tại. Các schema trong `app/schema/evidence_privacy.py` hiện là dữ liệu truyền giữa hàm, không phải message đang đẩy qua broker. Trường `queued` của response HTTP được giữ tương thích, nghĩa là số hồ sơ đã nhận để chạy nền.

Email vẫn dùng luồng nhập hiện có. Sau khi worker nhập email commit, nó gọi trực tiếp bộ chạy nền async cho bước xử lý PII, không yêu cầu đánh giá AI. Với hồ sơ tạo qua API, bước xử lý PII được đăng ký trực tiếp bằng `BackgroundTasks`. Không cần bật queue riêng để dùng subproject hoặc endpoint xử lý ảnh.

## Cấu hình và chạy

```sh
venv/bin/python -m pip install -r requirements.txt
# Khi phát triển package: venv/bin/python -m pip install -e ./image-preprocessing
venv/bin/alembic heads
# Áp dụng trên database đã chọn theo quy trình triển khai:
venv/bin/alembic upgrade head
```

```dotenv
EVIDENCE_PRIVACY_PROFILES_PATH=./image-preprocessing/config/profiles.json
EVIDENCE_VISION_PROVIDER=openrouter
OPENROUTER_API_KEY=<khóa dịch vụ được sử dụng>
```

Provider được chọn tường minh; không tự đổi provider khi lỗi:

| Provider | Model / cấu hình hiện có |
| --- | --- |
| `ollama` (mặc định) | `EVIDENCE_VISION_URL`, `EVIDENCE_VISION_MODEL` (mặc định `qwen3-vl:2b-instruct`); các bản Qwen3-VL 2B/4B và 8B được giới hạn trong `app/core/config.py` |
| `openrouter` | `OPENROUTER_API_KEY`; transport dùng `qwen/qwen3-vl-8b-instruct`, giới hạn provider `parasail`, không fallback |
| `qwen_cloud` | `DASHSCOPE_API_KEY`, `DASHSCOPE_WORKSPACE_ID` tùy chọn, `EVIDENCE_VISION_CLOUD_MODEL`; model mặc định `qwen3-vl-8b-instruct` |

Đây là giá trị từ source, không phải kết quả thử provider thật. API/worker cần đường mạng tới provider đã chọn. URL Ollama native mặc định `http://127.0.0.1:11434`; trong container phải trỏ tới endpoint truy cập được từ container. `compose.llm.yaml` chỉ chuẩn bị model text của Assistant, không cài Qwen3-VL hoặc tự đặt `EVIDENCE_VISION_URL`. Muốn dùng VLM local cần chuẩn bị runtime/model riêng tương ứng.

Tiền xử lý không cần khóa model. Thiếu khóa/provider không hoạt động hoặc phản hồi sai → đánh giá `FAILED`, không fallback sang OCR hay phân loại văn bản. Backend kiểm tra category trong danh mục HR và đúng một đánh giá cho mỗi ảnh. Tối đa 10 ảnh hợp lệ cho một lần suy luận của hồ sơ; vượt giới hạn chuyển nhân viên.

Các settings phân tích cũ như `PROCESSING_MODE`, `GEMINI_*`, `JEV_*`, `OCR_*`, `EVIDENCE_HISTORY_*` đã bỏ khỏi cấu hình chấm công. `ASSISTANT_*` và `POLICY_*` vẫn dành cho module riêng.

Cấu hình mặc định rỗng nên **mọi ảnh bị chặn AI** cho đến khi có bố cục phù hợp. Không dùng tọa độ minh họa cho ảnh thật. Cần đo vùng mặt, tên/mã, watermark và phần bằng chứng được giữ lại trên từng thiết bị/phiên bản UI. Anchor phải có chi tiết tĩnh, không chứa PII hoặc thông tin thay đổi. CLI từ chối anchor chồng lên vùng PII/mặt.

```sh
venv/bin/image-privacy-profile \
  --reference /duong-dan-noi-bo/reference.png \
  --spec /duong-dan-noi-bo/layout-spec.json \
  --profiles image-preprocessing/config/profiles.json \
  --preview /duong-dan-noi-bo/preview.png
```

CLI và spec mẫu nằm hoàn toàn trong subproject. Entry point cũ `python -m scripts.configure_evidence_privacy` chỉ chuyển tiếp tới CLI để giữ tương thích. Kiểm tra preview và nhiều biến thể trước khi bật `enabled`; không đưa ảnh gốc hoặc anchor có PII vào repository.

UI có nút **Xử lý PII trước**, trạng thái từng ảnh, liên kết xem đúng bản ảnh sẽ gửi model. `POST /api/privacy/preprocess` chỉ chạy tiền xử lý; `POST /api/analysis` chạy cả lượt tiền xử lý rồi mới đánh giá. Cả hai nhận bộ lọc nguồn/kỳ/khoa hiện có. Ảnh chưa hỗ trợ luôn bị chặn VLM, kể cả khi yêu cầu đánh giá lại.

## API và trạng thái

Các endpoint bên dưới đều yêu cầu phiên HR:

| Endpoint | Hành vi |
| --- | --- |
| `POST /api/privacy/preprocess` | Chỉ tiền xử lý theo bộ lọc nguồn/kỳ/đợt/khoa, không tự đánh giá |
| `POST /api/analysis` | Nhận lượt đánh giá; tiền xử lý toàn lượt trước VLM, trả số hồ sơ trong `queued` |
| `GET /api/analysis` | Số lượng chờ/đang xử lý/hoàn tất/lỗi; dùng thay việc chờ queue ảnh |
| `POST /api/cases/{id}/reanalyze` | Đánh giá lại phiên bản hiện hành; đang chạy thì 409, trừ yêu cầu khởi động lượt mới có `restart_background=true` |
| `GET /api/evidence/{id}/sanitized` | Preview đúng bản PNG được phép dùng; thiếu/hết hiệu lực trả lỗi, không trả ảnh gốc |

PII từng ảnh có trạng thái public `PENDING`, `READY` hoặc `MANUAL_REVIEW`. `READY` chỉ có nghĩa bản ảnh hợp lệ theo profile, không khẳng định giải trình đúng. Trạng thái đánh giá là `NOT_STARTED` → `WAITING_PRIVACY` → `RUNNING` → `COMPLETED`, `MANUAL_REVIEW` hoặc `FAILED`. Hồ sơ trộn ảnh thủ công và hợp lệ có thể `COMPLETED` ở phần VLM nhưng vẫn `MISSING`/`CONFLICT`, không đủ duyệt lô.

Chỉ kết quả VLM hoàn tất, đủ dữ kiện, category xác định, đúng revision và toàn bộ ảnh hợp lệ mới đủ điều kiện duyệt lô khi không có bản sửa chờ xử lý. HR vẫn là người xác nhận. Xác nhận ngoại lệ riêng lẻ không cấp quyền gửi ảnh bị chặn lên AI; chạy đánh giá hàng loạt không tự mở lại hồ sơ `MANUAL_REVIEW` đã được HR xác nhận.

Luồng đánh giá không còn LLM văn bản, OCR, JEV hoặc phân loại từ khóa. Điều kiện OCR đã được bỏ khỏi quy tắc HR bằng migration `739e52fa3c48`. Dữ liệu OCR và kết quả phân tích cũ vẫn giữ trong DB làm lịch sử, không được dùng làm đầu vào cho VLM hoặc để tự duyệt lô.

## Lifecycle và giới hạn hiện tại

Background hiện chạy trong process, chưa có bảo đảm lưu bền/at-least-once như broker. Nếu process khởi động lại, tác vụ đang chạy có thể bị gián đoạn. Trạng thái và bản ảnh đã xử lý vẫn lưu DB/storage. Với hồ sơ bị treo ở trạng thái đang chạy sau restart, HR có thể gọi `POST /api/cases/{id}/reanalyze?restart_background=true` để lập lượt mới. Request ID mới làm lượt cũ không được tiếp tục đánh giá. Không có thao tác này nào cho phép gửi ảnh chưa xử lý lên AI.

Cấu hình thay đổi làm bản ảnh cũ không được dùng cho lần suy luận tiếp theo; cần chạy lại xử lý PII. File đầu ra sai checksum hoặc bị mất bị vô hiệu hóa. Lỗi background ghi loại lỗi, không ghi nội dung ảnh, tên/mã hoặc đường dẫn riêng tư vào log. Có thể chạy lại qua API sau khi khắc phục.

TallyV hiện chỉ giữ adapter DB/storage và điều phối async. Sau này có thể thay `run_batch` bằng consumer queue mà giữ nguyên package xử lý và kiểm tra trước VLM. Hiện chưa cấu hình broker, worker privacy/AI riêng hoặc phân quyền bucket riêng.

Khớp bố cục chỉ an toàn khi PII thực sự nằm trong vùng đã cấu hình. Các chỉ số sáng/tối/Laplacian phục vụ rà soát chất lượng, không chứng minh ảnh không có người. Cần nghiệm thu trên dữ liệu được phép sử dụng, không cam kết tự động chính xác 100%.

Dockerfile cài package từ subproject; Compose mount `image-preprocessing/config` chỉ đọc vào API/worker. Cần cài lại package/build lại image sau khi sửa code subproject; mount mã `app/` trong `compose.local.yaml` không thay package đã cài. Không có `compose.privacy.yaml` hoặc cờ `--queue privacy/ai`.

Hướng dẫn kiểm thử, giới hạn smoke và kết quả đã ghi nhận: [verification.md](verification.md). Việc cập nhật docs không chạy migration, đổi `.env` hoặc bật suy luận trên ảnh thật.
