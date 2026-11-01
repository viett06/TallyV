# TallyV: phạm vi tích hợp thành module trong SAP

## Mục tiêu đã thống nhất

TallyV hiện có nhiệm vụ **tổng hợp, đánh giá và phân loại** các case. Sau đó HR phải nhập nghiệp vụ tương ứng lên SAP.

Mục tiêu sau này: tích hợp TallyV thành module/ứng dụng mở rộng trong SAP, đồng thời **tự động hóa phần nhập SAP mà HR đang làm thủ công**. HR kiểm tra kết quả và xác nhận; hệ thống thực hiện đúng kiểu nhập SAP tương ứng với từng case sai công số. Trải nghiệm và nghiệp vụ cập nhật phải được kiểm chứng trong môi trường SAP.

Cổng ứng dụng React giả lập và luồng gửi sửa giờ sang một hệ thống HR riêng không đáp ứng mục tiêu tích hợp thành module SAP. Chỉ đặt một ô URL để mở TallyV cũng chưa đủ để kết luận đã tích hợp xong.

Công số là dữ liệu nghiệp vụ cần xác định trong SAP; không tự coi giờ vào/ra hoặc một khoảng ca mô phỏng là công số được duyệt.

## Phần cần tự động hóa sau khi tích hợp

Luồng đích: **TallyV tổng hợp/đánh giá/phân loại → xác định cách nhập SAP cho case → chuẩn bị dữ liệu cần nhập → HR kiểm tra/xác nhận trong SAP → thực hiện nhập và lưu kết quả xử lý**.

Phân loại nguyên nhân hiện tại của TallyV và kiểu nhập nghiệp vụ SAP là hai thông tin cần phân biệt. Không mặc định một nhãn nguyên nhân luôn tương ứng một thao tác SAP cố định; phải xem dữ liệu và tình huống của case.

Trước khi triển khai, mô tả từng kiểu case bằng: tình trạng công số đang sai, kết quả đúng cần đạt, cách HR hiện nhập SAP, các trường/giá trị/đơn vị cần nhập và điều kiện chọn cách nhập đó. Hiện chưa có các ví dụ và quy tắc này trong phiên làm việc; không tự đặt giá trị công số hay quy trình nhập thay cho nghiệp vụ thực tế.

Giải pháp không bị chốt trước thành API sửa giờ vào/ra hoặc bot bấm màn hình. Cơ chế tích hợp được chọn sau khi biết nghiệp vụ nhập và khả năng của môi trường SAP đích.

## Quy trình TallyV hiện tại

1. Quét Outlook, tiếp nhận email và đọc Excel vào hệ thống.
2. HR bấm **Đánh giá và phân loại** để chạy phân tích; quét email không tự đánh giá.
3. HR đọc nguồn/bằng chứng, xem phân loại, xử lý bản sửa và lưu kết luận rà soát.
4. Xem lịch sử và xuất kết quả. HR hiện vẫn dùng kết quả để nhập lên SAP; việc xác nhận trong TallyV chưa thực hiện bước nhập đó.

Luồng trên được giữ nguyên. Cổng ứng dụng demo và màn hình **Gửi điều chỉnh HR** đã được bỏ khỏi giao diện. Mở ứng dụng về **Tổng quan** như trước.

## Bảng công mô phỏng được giữ tạm

Mục **Bảng công mô phỏng** trong menu chỉ dùng để tham khảo dữ liệu giờ vào/ra giả lập khi chưa có SAP. Chọn kỳ/phòng ban rồi bấm **Nạp bảng công mẫu** nếu chưa có dữ liệu; thao tác này chỉ khởi tạo các bản ghi chưa tồn tại. **Xem trường hợp** quay về màn hình rà soát nguồn.

Bảng này không phải màn hình SAP, không phải bảng công số thật và không đại diện cho việc cập nhật SAP. Không có màn hình điền sẵn giờ đề xuất hay nút gửi sửa giờ trong luồng chính. Lịch ca AM/Ca sáng 08:00–16:00, PM 13:00–21:00 chỉ phục vụ dữ liệu mẫu, không phải quy định của công ty.

Dịch vụ `hr_mock_app:app` và các bảng mô phỏng vẫn được giữ để đọc dữ liệu. Backend thử nghiệm yêu cầu gửi sửa giờ/biên nhận từ bước phát triển trước vẫn còn trong mã và database, nhưng không được nối vào giao diện hay mô tả là quy trình SAP được chấp nhận. Chưa thực hiện refactor/xóa các bảng cũ.

## Chạy cấu hình hiện có

```bash
venv/bin/alembic upgrade head
cd frontend
npm run build
cd ..
docker compose -f compose.yaml -f compose.outlook.yaml -f compose.local.yaml up -d --no-deps --no-build hr-mock worker
```

Override local tái sử dụng image `tallyv-worker` hiện có và mount mã nguồn. Nếu chưa có image, bỏ `--no-build` để build. API local dùng `HR_MOCK_URL=http://127.0.0.1:8010`, worker Docker dùng `http://hr-mock:8010`. Khởi động lại API nếu không dùng `--reload`.

Nếu chạy toàn bộ bằng Docker từ đầu: `docker compose up --build -d`. Nếu chạy thuần Python: chạy thêm `venv/bin/uvicorn hr_mock_app:app --host 127.0.0.1 --port 8010 --no-access-log` và chỉ một worker. Không chạy worker Docker và Python đồng thời.

Bảng công mô phỏng sở hữu các bảng riêng trong cùng PostgreSQL để giảm tài nguyên; TallyV đọc qua HTTP. Mẫu Mailpit/Outlook được phân biệt theo source. Không xóa hoặc reset dữ liệu Outlook đã tiếp nhận khi sửa giao diện.

## Trạng thái SAP và bước tiếp theo

Chưa có tenant SAP BTP, Work Zone thật, SSO SAP hoặc kết nối dữ liệu SAP. Đăng ký Trial cá nhân đang vướng bước xác minh điện thoại; đây là trở ngại cấp tài khoản, không phải lỗi của TallyV.

Khi tài khoản hoạt động:

1. Kiểm tra tài nguyên và môi trường SAP thực tế được cấp trong Trial.
2. Xác định cách đưa chức năng TallyV vào SAP, nhận đúng người dùng/quyền HR và ngữ cảnh nhân viên.
3. Tích hợp luồng rà soát hiện tại để HR sử dụng trong SAP.
4. Thu thập các kiểu case và cách HR đang nhập SAP, xác định quy tắc chọn kiểu nhập và dữ liệu cần điền cho từng kiểu.
5. Kiểm chứng phần tự động nhập đúng nghiệp vụ trong SAP sau khi HR kiểm tra/xác nhận từng case. Không thay phần này bằng API cập nhật giờ giả lập.

Không coi BTP Trial là đã có sẵn đầy đủ SAP HR; không khẳng định đã triển khai module vào lõi SAP chỉ vì một ứng dụng mở được từ Work Zone. Những phần chưa làm phải được ghi rõ trong demo.

Nguồn thiết lập: [SAP BTP Trial](https://www.sap.com/products/technology-platform/trial.html), [tạo tài khoản Trial](https://developers.sap.com/tutorials/hcp-create-trial-account), [Work Zone standard edition trên Trial](https://developers.sap.com/tutorials/cp-portal-cloud-foundry-getting-started).
