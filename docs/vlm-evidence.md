# Tiền xử lý PII độc lập và background async

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

Không tạo các job `PREPROCESS_EVIDENCE`, `RELEASE_VLM` hoặc `ANALYZE` cho luồng ảnh VLM. Các schema trong `app/schema/evidence_privacy.py` hiện là dữ liệu truyền giữa hàm, không phải message đang đẩy qua broker. Trường `queued` của response HTTP được giữ tương thích, nghĩa là số hồ sơ đã nhận để chạy nền.

Email vẫn dùng luồng nhập hiện có. Sau khi worker nhập email commit, nó gọi trực tiếp bộ chạy nền async cho bước xử lý PII, không yêu cầu đánh giá AI. Với hồ sơ tạo qua API, bước xử lý PII được đăng ký trực tiếp bằng `BackgroundTasks`. Không cần bật queue riêng để dùng subproject hoặc endpoint xử lý ảnh.

## Cấu hình và chạy

```sh
venv/bin/python -m pip install -e ./image-preprocessing
venv/bin/alembic upgrade head
```

```dotenv
EVIDENCE_PRIVACY_PROFILES_PATH=./image-preprocessing/config/profiles.json
EVIDENCE_VISION_PROVIDER=openrouter
OPENROUTER_API_KEY=<khóa dịch vụ được sử dụng>
```

Cũng có thể chọn Ollama nội bộ với các biến `EVIDENCE_VISION_*` hiện có. Tiền xử lý không cần khóa API model. Nếu yêu cầu suy luận khi thiếu khóa, bước AI thất bại rõ ràng; không tự đổi provider.

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

Luồng đánh giá không còn LLM văn bản, OCR, JEV hoặc phân loại từ khóa. Điều kiện OCR đã được bỏ khỏi quy tắc HR bằng migration `739e52fa3c48`. Dữ liệu OCR và kết quả phân tích cũ vẫn giữ trong DB làm lịch sử, không được dùng làm đầu vào cho VLM hoặc để tự duyệt lô.

## Lifecycle và giới hạn hiện tại

Background hiện chạy trong process, chưa có bảo đảm lưu bền/at-least-once như broker. Nếu process khởi động lại, tác vụ đang chạy có thể bị gián đoạn. Trạng thái và bản ảnh đã xử lý vẫn lưu DB/storage. Với hồ sơ bị treo ở trạng thái đang chạy sau restart, HR có thể gọi `POST /api/cases/{id}/reanalyze?restart_background=true` để lập lượt mới. Request ID mới làm lượt cũ không được tiếp tục đánh giá. Không có thao tác này nào cho phép gửi ảnh chưa xử lý lên AI.

Cấu hình thay đổi làm bản ảnh cũ không được dùng cho lần suy luận tiếp theo; cần chạy lại xử lý PII. File đầu ra sai checksum hoặc bị mất bị vô hiệu hóa. Lỗi background ghi loại lỗi, không ghi nội dung ảnh, tên/mã hoặc đường dẫn riêng tư vào log. Có thể chạy lại qua API sau khi khắc phục.

TallyV hiện chỉ giữ adapter DB/storage và điều phối async. Sau này có thể thay `run_batch` bằng consumer queue mà giữ nguyên package xử lý và kiểm tra trước VLM. Hiện chưa cấu hình broker, worker privacy/AI riêng hoặc phân quyền bucket riêng.

Khớp bố cục chỉ an toàn khi PII thực sự nằm trong vùng đã cấu hình. Các chỉ số sáng/tối/Laplacian phục vụ rà soát chất lượng, không chứng minh ảnh không có người. Cần nghiệm thu trên dữ liệu được phép sử dụng, không cam kết tự động chính xác 100%.

Dockerfile đã cài package từ subproject; Compose mount cấu hình profile mới cho API/worker. Không cần `compose.privacy.yaml` hoặc `--queue privacy/ai`. Chưa chạy migration, đổi `.env` thật hay bật suy luận trên ảnh thật trong tác vụ này.
