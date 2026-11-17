# Rà soát chấm công

HR đồng bộ email hoặc tạo hồ sơ thủ công, kiểm tra nguồn và chạy **Đánh giá và phân loại**. Khi hồ sơ cần sửa, HR chấp nhận hoặc từ chối bản sửa trước khi xác nhận kết luận. Bộ lọc kỳ, đợt, khoa và nguồn áp dụng xuyên suốt Hộp thư, Trường hợp và xuất Excel.

## Kỳ lương và đợt rà soát

Kỳ lương tính từ ngày 26 tháng trước đến ngày 25 tháng được đặt tên. Mỗi đợt mở vào thứ Bảy và tổng hợp vào thứ Hai tiếp theo. Đợt thuộc kỳ của thứ Bảy, kể cả khi thứ Hai rơi vào kỳ mới. Ngày nhận email không thay đổi kỳ hoặc đợt khai báo. Hồ sơ từ email tháng thiếu mốc tuần nằm ở nhóm chưa gán đợt.

Ví dụ tiêu đề cho kỳ tháng 11/2026 và đợt ngày 7/11.

```text
[DCC] [2026-11] [WEEK:2026-11-07] Điều chỉnh chấm công
```

Với Outlook thử nghiệm, thêm `[TALLYV-MVP]`. [Thiết lập người gửi và hộp thư](outlook.md)

## Mẫu Excel

Tải mẫu từ TallyV hoặc dùng sheet `DieuChinh` với các cột sau theo đúng thứ tự.

```text
Mã trường hợp | Mã nhân viên | Họ tên | Phòng ban | Ngày xảy ra | Ca làm | Loại lượt thiếu | Lý do/giải trình | Bằng chứng
```

- Điền mã trường hợp, mã nhân viên, họ tên, phòng ban và ngày xảy ra. Dùng ô ngày Excel hoặc `YYYY-MM-DD` trong kỳ đã khai báo. Ngày dạng `01/02/2026` bị báo lỗi vì dễ hiểu theo hai cách.
- Neo ảnh tại cột I đúng dòng hồ sơ. Một dòng có thể có nhiều ảnh. Tệp tối đa 15 MB và 2.000 dòng. Ảnh PNG/JPEG tối đa 8 MB và 16 triệu pixel.
- Hồ sơ giữ mã và nguồn gốc khi có bản sửa. Email hoặc tệp gửi lại được đối chiếu để tránh tạo trùng. Hộp thư hiển thị lỗi từng dòng để HR yêu cầu gửi lại đúng mẫu.

## Dữ liệu thử

[Workbook giả lập OCR/VLM](../samples/attendance-ocr-demo.xlsx) thuộc kỳ tháng 11/2026. Workbook có ba bảng thông tin phù hợp với profile kèm theo và một cảnh camera minh họa để thử đường chuyển HR rà soát. Có thể dùng làm file đính kèm trong hộp thư Outlook thử nghiệm sau khi đăng ký người gửi, phòng ban và nhân viên tương ứng, hoặc trích ảnh riêng để đính kèm vào hồ sơ tạo tay.

Với ảnh hợp lệ, bấm **Xử lý PII trước** để xem bản cuối. Kiểm tra vùng mặt, tên, mã nhân viên và phần thông tin nghiệp vụ được giữ. Sau đó chọn **Đánh giá và phân loại**. [Luồng ảnh và cấu hình](vlm-evidence.md)

## Xác nhận và SAP

Kết quả VLM là gợi ý cho HR. Duyệt lô yêu cầu đủ dữ kiện, phiên bản hiện hành và toàn bộ ảnh hợp lệ. Ngoại lệ cần xác nhận riêng kèm lý do.

TallyV xuất kết quả đã rà soát để HR nhập SAP hiện có. **Bảng công mô phỏng** là bảng tra cứu giờ vào/ra mẫu. Việc tự điền vào SAP desktop còn phụ thuộc giao dịch, các trường công số và cấu hình SAP GUI Scripting trên môi trường được cấp.
