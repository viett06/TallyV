# Phạm vi bằng chứng ảnh của TallyV

## Các loại ảnh đầu vào cần hỗ trợ

Theo nghiệp vụ đã làm rõ, bằng chứng có thể gồm:

| Loại ảnh | Dữ liệu có thể trích từ ảnh nếu thực sự hiển thị | Phần cần đối chiếu hoặc HR kiểm tra |
|---|---|---|
| Ảnh chụp/lưu khi quét mặt vào tòa nhà | Ngày giờ, mã/tên nhân viên, máy/cổng, trạng thái do thiết bị hiển thị | Ảnh khuôn mặt riêng không cung cấp mã nhân viên bằng OCR; ghi nhận vào tòa nhà chưa đồng nghĩa đã ghi công |
| Ảnh camera tại nơi làm việc | Timestamp, tên camera/vị trí, nội dung cảnh quan sát được | Không suy ra danh tính hay đủ cả ca/công số từ việc thấy người ngồi tại một thời điểm; HR đối chiếu người và bối cảnh |
| Điện thoại chụp máy chấm công bị lỗi | Chữ/mã lỗi, trạng thái hiển thị, mã máy, ngày giờ nếu có | Một ảnh báo lỗi chưa tự chứng minh đúng thời điểm/lượt quét của nhân viên trong case |

Không mặc định mọi ảnh đều có đủ các trường trên. Thông tin không hiển thị phải để là chưa xác định, không tạo từ giải trình hoặc phỏng đoán của model rồi coi là quan sát từ ảnh.

## Phân biệt OCR và hiểu ảnh

OCR đọc phần chữ/số: timestamp, nhãn mã nhân viên, thông báo lỗi. Nhận biết đây là cảnh camera, màn hình quét mặt hay ảnh chụp lỗi thiết bị cần thêm xử lý nội dung ảnh; OCR thuần không bao phủ yêu cầu này.

Hướng xử lý bằng chứng: **nhận ảnh → nhận dạng loại bằng chứng → đọc chữ nếu có + mô tả quan sát phù hợp → trích thông tin có nguồn rõ ràng → đối chiếu với case → trình HR kết quả và những điểm chưa xác minh**.

Không đánh đồng ảnh ít/không có chữ với ảnh không dùng được. Tách riêng trạng thái đọc chữ, chất lượng ảnh và khả năng đối chiếu nghiệp vụ. Model nhìn thấy người/cảnh chỉ là quan sát, không phải kết luận danh tính, thời gian làm việc hay duyệt công.

Nếu có mã/tên được thiết bị hiển thị thì trích từ chữ và ghi rõ nguồn là màn hình thiết bị. Nếu chỉ có khuôn mặt, bản hiện tại để HR đối chiếu hoặc cần log quét chính thức; chưa có yêu cầu triển khai đối sánh sinh trắc khuôn mặt.

## Giới hạn của bản đang chạy

`app/services/analysis.py::read_evidence` đang gọi Tesseract với `lang="eng"`, rồi tìm mã mẫu `MPxxx`, ngày ISO và một số từ khóa tiếng Anh. Cơ chế này chỉ được thử với ảnh giả lập có chữ rõ; chưa đáp ứng đầy đủ ba dạng ảnh nghiệp vụ trên. Đánh dấu loại `CAMERA` hiện dựa trên chữ CAMERA trong text, không phải model nhận biết cảnh.

Ollama tùy chọn hiện chỉ nhận giải trình và kết quả kiểm tra bằng chứng, không nhận ảnh gốc. Bật `LOCAL_LLM` không tự bổ sung khả năng hiểu ảnh. Chưa có bộ nhận diện loại ảnh, model vision, mô hình đối sánh khuôn mặt, suy luận đủ công hay API nhập công số SAP.

## Trước khi thay bộ phân tích

- Chuẩn bị ảnh mẫu giả lập có bố cục đại diện cho ba loại bằng chứng, có/không có chữ, timestamp và thông tin nhân viên.
- Ghi đáp án ở mức thông tin quan sát được, thông tin cần trích và điểm chưa xác minh; không tạo đáp án duyệt công từ ảnh đơn lẻ.
- Kiểm tra chất lượng đọc tiếng Việt, ảnh chụp lệch/mờ/phản sáng và các định dạng ngày giờ thực tế.
- Chọn engine OCR và phương án hiểu ảnh dựa trên kết quả đo, giới hạn máy yếu và ngân sách hiện tại. Không tự tải model lớn hoặc gửi ảnh lên cloud trong bước làm rõ yêu cầu.
- Giữ HR ở bước xác nhận và tách việc đánh giá bằng chứng khỏi quy tắc nhập nghiệp vụ SAP theo từng kiểu case.
