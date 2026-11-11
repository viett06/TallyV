# Đối chiếu bằng chứng ảnh lịch sử

TallyV dùng MobileNetV2 ONNX để tạo embedding phần nền tại worker. Hệ thống tìm ảnh tương tự theo cosine qua các kỳ và người nộp trong cùng nguồn dữ liệu, rồi dùng đặc trưng SIFT và kiểm tra hình học để đánh giá bố cục. OCR và kiểm tra ca chạy riêng. Ảnh gốc, embedding, mã ảnh lịch sử và tên địa điểm lưu nội bộ. Gemini và JEV nhận dữ kiện rút gọn theo mã ảnh tạm của từng hồ sơ.

Kết quả “Phù hợp góc đã biết địa điểm” là đối chiếu bố cục với mẫu đã gắn địa điểm. Trạng thái này chưa xác minh được thời điểm chụp, lượt quét hay tính nguyên gốc. Khi kho thiếu mẫu đã gắn địa điểm, các nhóm góc tạm vẫn cho biết ảnh từng xuất hiện trong bối cảnh tương tự.

## Bật tính năng

1. Cài các phụ thuộc đã cập nhật trong `requirements.txt`. Với môi trường chạy Docker, build lại image của API và worker.
2. Chạy `alembic upgrade head` trên cơ sở dữ liệu TallyV cần dùng.
3. Tải [checkpoint MobileNetV2-12 chính thức](https://github.com/onnx/models/blob/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx). Worker kiểm tra SHA-256 trước khi nạp. Đặt file ở thư mục worker có thể đọc.

   ```bash
   curl -fL 'https://media.githubusercontent.com/media/onnx/models/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx' -o mobilenetv2-12.onnx
   shasum -a 256 mobilenetv2-12.onnx
   ```

   SHA-256 là `c0c3f76d93fa3fd6580652a45618618a220fced18babf65774ed169de0432ad5`.
4. Cấu hình đường dẫn trong `.env` rồi khởi động lại worker.

   ```dotenv
   EVIDENCE_HISTORY_ENABLED=true
   EVIDENCE_HISTORY_MODEL_PATH=/absolute/path/to/mobilenetv2-12.onnx
   OCR_ENABLED=true
   ```

   Với Docker Compose, có thể dùng `/app/data/models/mobilenetv2-12.onnx` và chép file vào volume dữ liệu bằng `docker compose exec worker mkdir -p /app/data/models` rồi `docker compose cp mobilenetv2-12.onnx worker:/app/data/models/mobilenetv2-12.onnx`. Tạo lại worker sau khi đổi biến môi trường. Dùng cấu hình Gemini và JEV hiện có nếu muốn chạy cả hai bước.

Khi bật tính năng, ảnh mới được đối chiếu trong lúc phân tích. Sau khi HR xác nhận từng hồ sơ hoặc duyệt hàng loạt, worker lấy ảnh đã lưu của phiên bản hiện hành, tính embedding và cập nhật kho tham chiếu. Có thể theo dõi tác vụ lập chỉ mục trong Hàng đợi. Trạng thái xác nhận HR được lưu trước khi worker xử lý. Chỉ ảnh của phiên bản hiện hành, còn được HR xác nhận và chưa bị loại khỏi kho mới được dùng để đối chiếu. Trạng thái này được kiểm tra lại khi worker chạy và khi tìm ảnh ứng viên.

## Nạp ảnh cũ được phép sử dụng

1. Nhập ảnh qua hồ sơ TallyV hiện có, hoặc dùng ảnh đã lưu trong các hồ sơ cũ. Lấy mã ảnh trên thẻ bằng chứng của hồ sơ. Nếu ảnh đã chạy OCR/vision, chỉ mục dùng các vùng và thông tin cảnh đã lưu khi xử lý nền.
2. Với hồ sơ đã được HR xác nhận trước khi bật tính năng, chỉ định mã từng ảnh được phép đưa vào kho.

   ```bash
   python -m scripts.index_evidence_history index 101 102 103
   ```

   Với Docker, chạy lệnh trên qua `docker compose exec worker`. Kết quả gồm trạng thái và mã nhóm nếu ảnh đủ chi tiết. Ảnh trùng hoặc gần trùng với mẫu đã có được ghi nhận riêng và không được thêm làm một mẫu độc lập.
3. Nếu có căn cứ định danh một nhóm, gắn tên bằng mã ảnh tham chiếu chứa căn cứ đó.

   ```bash
   python -m scripts.index_evidence_history label 101 --location "Sảnh A, cơ sở X" --basis "Biển tên cơ sở và khu vực hiện trong ảnh 101"
   ```

   Nếu quyền sử dụng một ảnh thay đổi, dùng `python -m scripts.index_evidence_history exclude 101`. Lệnh xóa đặc trưng của ảnh khỏi kho và ngăn ảnh tự được thêm lại. Chạy phân tích lại các hồ sơ từng dùng mẫu này nếu cần làm mới kết quả đã lưu.

## Chạy thử một hồ sơ

1. Duyệt một vài hồ sơ mẫu có góc chụp đã biết và chờ worker lập chỉ mục, hoặc nạp ảnh từ các hồ sơ mẫu đã duyệt.
2. Tạo hồ sơ mới, nhập ngày công, ca và lượt vào/ra cần giải trình, đính kèm một ảnh khác của góc đó rồi chọn phân tích hồ sơ.
3. Kiểm tra phần bằng chứng của hồ sơ để xem ngày/ca khớp hay lệch, chênh lệch với mốc vào/ra dự kiến, trạng thái đối chiếu nền và mã ảnh tham chiếu. Ca qua nửa đêm sử dụng ngày công và khoảng ca đã lưu. Khoảng so ca lấy theo giờ bắt đầu và kết thúc đang có trong hồ sơ.
4. Nếu dùng Gemini và JEV, kiểm tra loại lỗi đề xuất, phần dữ kiện hỗ trợ và trạng thái JEV. Hồ sơ vẫn do HR quyết định. Trạng thái kho trống hoặc lỗi truy xuất cho phép tiếp tục với OCR và các dữ kiện còn lại.

## Kiểm tra trên dữ liệu giả lập

Có thể chạy các ca kiểm tra với checkpoint thật. Bộ kiểm tra tạo ảnh và cơ sở dữ liệu cô lập tại thời điểm chạy, đồng thời giả lập phản hồi OCR, Gemini và JEV cho bài kiểm tra tích hợp.

```bash
TALLYV_TEST_IMAGE_MODEL=/absolute/path/to/mobilenetv2-12.onnx pytest tests/test_evidence_history.py
```

Ngưỡng đối chiếu hiện dùng cho MVP. Khi có ảnh thật, giữ riêng một tập hồ sơ kiểm tra và đo tỷ lệ gán nhầm địa điểm, đặc biệt với ảnh cận mặt, góc thay đổi phối cảnh, hai hành lang tương tự và ảnh từ camera có cùng góc nhưng khác thời điểm.
