# Tham chiếu giao diện Vinmec cho TallyV

> Trạng thái tài liệu: snapshot tham chiếu giao diện ngày 11/11/2026; không mô tả phần mềm nội bộ của Vinmec hoặc thay thế hướng dẫn sử dụng. Luồng đang chạy và trạng thái ảnh được mô tả tại [README](../README.md) và [PII/VLM](vlm-evidence.md).

Rà soát nguồn công khai ngày 11/11/2026. Phạm vi là giao diện quản lý hồ sơ giải trình công của TallyV.

## Căn cứ công khai

- **Nghiệp vụ nhân sự.** Tin tuyển dụng chuyên viên thủ tục nhân sự của Vinmec nêu nhiệm vụ quản lý công ca, thông tin nhân sự và ưu tiên kinh nghiệm SAP hoặc phần mềm quản lý nhân sự tương tự. Tài liệu công khai tìm được chưa đủ để xác định phần mềm, phiên bản hay bố cục màn hình công ca nội bộ Vinmec hiện dùng. [Tin tuyển dụng Vinmec](https://www.vinmec.com/vie/bai-viet/vinmec-thong-bao-tuyen-dung-chuyen-vien-thu-tuc-nhan-su-vi)
- **Nhận diện Vinmec.** Ảnh giao diện MyVinmec do Vinmec công bố cho thấy nền trắng, xanh ngọc làm màu nhấn, biểu tượng đi cùng nhãn tiếng Việt và các nhóm chức năng có tiêu đề rõ. Đây là ứng dụng chăm sóc sức khỏe cho khách hàng, phù hợp để tham chiếu màu sắc và cách đặt nhãn. [Giới thiệu MyVinmec của Vinmec](https://www.vinmec.com/vie/bai-viet/vinmec-ra-mat-cong-dich-vu-cham-soc-khach-hang-truc-tuyen-duy-nhat-tren-ung-dung-myvinmec-vi) · [Ảnh giao diện do Vinmec công bố](https://www.vinmec.com/static/uploads/large_20220616_083309_243948_Screenshot_20220616_max_1800x1800_png_02727e5972.png)
- **Tiền lệ nhận diện Vingroup.** Hướng dẫn tài khoản Vinmec/Vin3S công khai có thanh điều hướng xanh, khối biểu mẫu trắng và nút đăng nhập màu vàng. Đây là tài liệu cũ cho cổng dịch vụ khách hàng. Màu vàng có thể dùng làm điểm nhấn nhỏ trong TallyV. [Hướng dẫn tài khoản Vinmec/Vin3S, trang 6](https://online.vinmec.com/themes/custom/vin_service/images/faq/huong-dan-dang-ky.pdf#page=6)
- **Mẫu giao diện nghiệp vụ.** Tài liệu SAP Fiori mô tả List Report với bộ lọc và bảng kết quả, kết hợp Object Page để xem và xử lý một bản ghi. SAP cũng dùng nhãn ngắn và màu mang ý nghĩa cho trạng thái nghiệp vụ. Đây là nguồn tham chiếu cho bố cục TallyV. [SAP List Report](https://help.sap.com/docs/bas/developing-sap-fiori-app-in-sap-business-application-studio/list-report-page?locale=en-US&state=PRODUCTION&version=Cloud) · [SAP List Report và Object Page](https://help.sap.com/docs/SAPUI5/b2f662dd9d7a4ec680056733050b4d34/c0eec49db81a441e878f528c8f3d28de.html) · [SAP Object Status](https://www.sap.com/design-system/fiori-design-web/v1-71/ui-elements/object-display-elements/)

## Áp dụng vào TallyV

- Dùng xanh ngọc đậm cho điều hướng và nút chính, nền trung tính sáng, bảng trắng, đường phân cách nhẹ và chữ tiếng Việt dễ đọc. Dành màu hổ phách cho mục cần chú ý và màu đỏ cho lỗi hoặc xung đột. Giữ chữ trạng thái để người dùng nhận biết được ý nghĩa qua nội dung.
- Bố trí danh sách theo nhịp xử lý của HR. Tên trang và thao tác chính ở đầu, bộ lọc theo kỳ, phòng ban và trạng thái ở trên bảng. Bảng giúp quét nhanh nhân viên, ngày công, kết quả phân tích và trạng thái duyệt.
- Đặt mã và trạng thái hồ sơ ở đầu phần chi tiết, sau đó là giải trình, bằng chứng và đánh giá. Trình bày đối chiếu ca, kết quả so ảnh, đề xuất phân loại và xác nhận HR bằng nhãn riêng để người đọc theo dõi nguồn từng kết quả.
- Giữ các mục điều hướng và thao tác nghiệp vụ hiện có. Trên màn hình hẹp, để bộ lọc xuống dòng và giới hạn cuộn ngang trong bảng.
