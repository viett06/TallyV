# Phạm vi bằng chứng ảnh của TallyV

Đối chiếu ngày 14/11/2026. Đánh giá chấm công hiện chỉ dùng **tiền xử lý PII offline → VLM trên bản ảnh đã xử lý → HR rà soát**. Không còn OCR, LLM phân loại văn bản, JEV hoặc đối chiếu embedding ảnh lịch sử trong đường này.

## Ảnh nào được xử lý tự động

| Loại đầu vào | Xử lý hiện tại | Điều kiện gửi VLM |
| --- | --- | --- |
| Ảnh trực tiếp từ FaceID | Khớp profile `FACEID`; che vùng mặt, tên/mã và PII theo tọa độ, chỉ giữ vùng nghiệp vụ cho phép | Đúng kích thước, khớp duy nhất profile đã bật và anchor tĩnh; bản PNG mới qua kiểm tra toàn vẹn |
| Ảnh màn hình thiết bị báo lỗi | Khớp profile `DEVICE_ERROR`; che PII và chỉ giữ vùng thông báo nghiệp vụ | Cùng điều kiện profile và toàn vẹn; mọi vùng có thể chứa mặt cũng phải được che hoặc nằm ngoài vùng giữ |
| Ảnh CCTV, điện thoại chụp cảnh, bố cục lạ hoặc chưa cấu hình | `MANUAL_REVIEW` | Không gửi VLM, không có nút cho phép bỏ qua |
| File hỏng, ảnh trống, sai kích thước, khớp nhiều profile hoặc không còn bằng chứng sau che | `MANUAL_REVIEW` | Không tạo bản ảnh được phép gửi model |

`DEVICE_ERROR` là ảnh có bằng chứng lỗi thiết bị trong bố cục đã hỗ trợ. Nó không có nghĩa mọi ảnh đen, nhiễu hoặc hỏng file đều chứng minh máy chấm công gặp sự cố. Thống kê độ sáng/Laplacian không chứng minh ảnh không chứa người hoặc không còn PII.

Profile mặc định rỗng nên mọi ảnh chờ nhân viên. Không nhận diện mặt bằng Haar, deep learning hoặc model từ xa. Mặt nạ cố định phụ thuộc vùng đã cấu hình; không cam kết chính xác 100% trên ảnh ngoài bố cục đã nghiệm thu. Xem [package xử lý ảnh](../image-preprocessing/README.md).

## Ranh giới dữ liệu và kết quả

Backend giữ ảnh gốc trong storage riêng tư để HR xem. Package tạo mảng pixel đen, chép `keep_regions`, che đè mặt/PII và xuất PNG mới không chép metadata nguồn. Adapter lưu file UUID riêng, revision cấu hình và SHA-256. VLM chỉ nhận bản này sau khi toàn bộ lượt tiền xử lý hoàn tất; không nhận ảnh gốc, dữ liệu OCR cũ hoặc chỉ mục lịch sử.

Giải trình được lọc bằng từ vựng cho phép và loại bỏ định danh; mô tả quy tắc HR có thông tin định danh được phát hiện sẽ bị chặn. Bộ lọc có thể làm mất ngữ nghĩa, cần HR kiểm tra kết quả. Đây không phải bước xác minh pháp lý rằng mọi nội dung đã được ẩn danh tuyệt đối.

VLM trả phân loại nguyên nhân và, với từng ảnh, `SUPPORTS`, `CONTRADICTS` hoặc `INSUFFICIENT`, kèm quan sát và giới hạn. Không suy ra danh tính, thời gian làm việc cả ca hoặc thành công của lượt chấm công chỉ từ khuôn mặt/cảnh. Nội dung bị che không được đoán lại. Thiếu ảnh hợp lệ dẫn tới `MANUAL_REVIEW`; lỗi provider/schema dẫn tới `FAILED`, không chuyển sang engine văn bản.

Hồ sơ có cả ảnh hợp lệ và ảnh cần nhân viên chỉ gửi phần hợp lệ; kết quả vẫn thiếu căn cứ và không đủ duyệt lô. HR có thể xác nhận ngoại lệ riêng lẻ sau khi xem nguồn, chọn phân loại và nhập lý do theo API review. Việc xác nhận thủ công không cấp quyền gửi ảnh bị chặn lên VLM.

## Chạy và nghiệm thu

Xem [cấu hình profile, background async và API](vlm-evidence.md). Dùng ảnh giả lập đại diện cho từng thiết bị/phiên bản UI, cả trường hợp lệch bố cục, nhiều mặt, watermark đổi chỗ và không có bằng chứng sau che. Kiểm tra các pixel được giữ lại và metadata đầu ra trước khi bật profile.

Tests kiểm tra không gửi ảnh thô, chỉ gửi phần đã xử lý, chặn checksum/revision sai, chờ toàn bộ tiền xử lý và giữ duyệt lô nguyên tử. Chưa có benchmark VLM trên ảnh bệnh viện thật; xem [trạng thái kiểm thử](verification.md).
