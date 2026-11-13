# Đối chiếu ảnh lịch sử — đã ngừng dùng trong đánh giá

Từ đợt refactor ngày 14/11/2026, luồng đánh giá chấm công không còn MobileNetV2 embedding, cosine similarity, SIFT hoặc bước Gemini/JEV xử lý kết quả đối chiếu. Đây là trang thông báo thay thế hướng dẫn bật tính năng cũ.

Các module `evidence_history.py`, `evidence_image_features.py`, `evidence_facts.py` và CLI `scripts/index_evidence_history.py` đã được gỡ. Hệ thống không tạo job `INDEX_EVIDENCE` sau xác nhận HR, không tìm ảnh tham chiếu và không còn nhãn kết luận góc camera từ pipeline này. Không tải MobileNet hoặc cấu hình `EVIDENCE_HISTORY_*` để vận hành phiên bản hiện tại; settings cũ không bật lại tính năng.

Bảng/cột dữ liệu đối chiếu và kết quả cũ được giữ để bảo toàn lịch sử. Chúng không được dùng làm đầu vào VLM hoặc điều kiện duyệt lô. Không xóa dữ liệu hay weights cũ chỉ để nâng cấp ứng dụng; việc dọn dữ liệu cần được thực hiện riêng theo chính sách lưu trữ.

Luồng hiện tại là [tiền xử lý PII rồi đánh giá bằng VLM](vlm-evidence.md). Ảnh CCTV chưa hỗ trợ phải do nhân viên đánh giá, kể cả khi trước đây đã được gắn địa điểm hay tìm được góc tương tự. Xác nhận của HR không tạo ngoại lệ cho việc gửi ảnh chưa xử lý lên model.

Tài liệu khảo sát [nguồn ảnh camera](cctv-workplace-datasets-research.md) được giữ làm tham khảo và mẫu kiểm tra đường chặn VLM, không phải hướng dẫn khởi động lại pipeline đối chiếu đã bỏ.
