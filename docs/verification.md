# Nghiệm thu MVP local — 30/10/2026

Đây là dữ liệu và kết quả **mô phỏng**, không phải dữ liệu hoặc chính sách bệnh viện thật.

## Môi trường đã chạy

Docker Desktop; PostgreSQL 16; Mailpit 1.27; FastAPI + SQLAlchemy + Alembic; React/TypeScript/Vite/Tailwind; Tesseract 5 local (ngôn ngữ eng; gói vie được cài sẵn). Không dùng LLM trong chế độ mặc định.

Ứng dụng: http://127.0.0.1:8000. Hộp thư demo: http://127.0.0.1:8025.

## Kiểm thử đã thực hiện

| Nội dung | Kết quả / bằng chứng |
|---|---|
| Unit và integration API | `python -m pytest -q`: **18 passed**. SQLite tạm riêng; không đụng dữ liệu demo. |
| TypeScript + frontend build | `npm run build` chạy thành công tại host và trong Docker. |
| Migration PostgreSQL | `alembic upgrade head` và `alembic check`: không có thay đổi schema còn thiếu. |
| Dependency / whitespace | `pip check`, `git diff --check`: đạt. |
| SMTP thật → tiếp nhận thật | Gửi 10 email từ script vào SMTP Mailpit, sau đó backend đọc MIME/file qua Mailpit API; 60 trường hợp, không seed trực tiếp case. |
| Email đã đọc | Đánh dấu cả 10 email `Read=true` trước khi worker khởi chạy. Hộp thư báo `total=10`, `unread=0`; vẫn tiếp nhận đủ. |
| Đồng bộ nhiều lần | Số email và trường hợp không tăng. Message-ID/source ID được kiểm tra; file trùng có tham chiếu file gốc. |
| Bảo toàn số dòng | Tất cả batch thỏa `row_count = imported_count + duplicate_count + error_count`. Lỗi anchor cấp file được báo riêng, không tính như thêm một dòng nguồn. |
| Liên kết ảnh | Unit test anchor two-cell trải nhiều dòng bị chặn. Demo có ảnh neo sai cột báo lỗi; MP-1-012 có hai ảnh đúng dòng. |
| File sửa đổi | 60 case / 61 phiên bản: MP-1-001 giữ bản gốc và một `PROPOSED`. Unit test xác nhận cũ mất hiệu lực, chấp nhận bản sửa có audit, nguồn cũ `SUPERSEDED`. |
| Retry sau lỗi | Unit test gây lỗi sau khi xử lý nhưng trước commit: transaction rollback; lần chạy sau chỉ có một case và một ảnh liên kết. |
| Phân loại/schema | Pydantic kiểm tra JSON/schema, kể cả payload model không có trường họ tên. Lỗi JSON được lưu FAILED và không tạo fallback giả. |
| Lỗi Ollama thực tế | Chạy adapter LOCAL_LLM vào endpoint local không có server trên MP-5-009: FAILED/ConnectError, UI hiển thị lỗi và phương thức Model nội bộ. Sau đó nhấn Phân tích lại để trở về RULE_BASED. Không có model thật được tải/chạy. |
| OCR thực tế | Tesseract đọc ảnh mẫu. Lưu nguyên text OCR; O→0 chỉ chuẩn hóa trong phần số mã MP và có ghi chú. Không suy diễn ký tự ngày còn mơ hồ. Ảnh chỉ có watermark/caption mà không có dữ kiện nghiệp vụ được đánh dấu UNREADABLE. |
| Duyệt lô | Lô có dòng thiếu điều kiện bị HTTP 409 và không duyệt một phần. Dòng đủ điều kiện xác nhận được; UI có hộp xác nhận số dòng, checkbox ngoại lệ bị khóa, backend kiểm tra lại. |
| HR trên UI | Đã sửa phân loại MP-3-004, yêu cầu bổ sung kèm ghi chú, thấy audit theo hr.demo. Đã chọn MP-3-001 qua checkbox và xác nhận qua modal; bảng đổi thành Đã xác nhận. |
| Xuất Excel | Smoke kiểm tra số dòng và cột kỳ/loại lỗi khớp filter DB. Unit test chuỗi `=HYPERLINK(...)` được xuất kiểu string, không phải công thức. |
| Quyền và dữ liệu không đáng tin | API/ảnh/file/export khi chưa đăng nhập trả 401. `/data/...` trả 404. Origin khác nguồn bị 403. HTML/script email là dữ liệu JSON/text, không được thực thi. Macro/external workbook links và ô công thức không được xử lý như mã lệnh. |
| Thay đổi quy tắc | Unit test sửa rule làm mất hiệu lực xác nhận, phân tích về PENDING và có audit. |
| Restart thật | Restart PostgreSQL, Mailpit, API, worker; snapshot sau restart bằng trước: 60 case, 10 email, nội dung kết luận, hash ảnh, audit và job nghiệp vụ giữ nguyên. `scripts/persistence_check.py` lưu báo cáo dưới data/demo local. |
| Desktop / mobile | Kiểm tra trực tiếp bằng browser ở desktop và 390×844. Mobile: `scrollWidth=390`, viewport=390; bảng cuộn nội bộ (984/356), không tràn toàn trang. |
| Dữ liệu local / Internet | Frontend chỉ fetch `/api`, bundle/font local, CSP `connect-src 'self'`. Endpoint Mailpit/Ollama giới hạn host local/private, không redirect hoặc proxy môi trường. Worker chỉ nối Docker internal; `/proc/net/route` không có default route Internet. Không cloud, CDN, analytics hay dữ liệu gửi ra ngoài trong luồng demo. Đây không phải kiểm toán packet capture toàn máy. |
| Reset | Script cần chuỗi xác nhận rõ ràng và worker phải dừng; giữ tài khoản/danh mục. Không thực hiện xóa bộ demo đã chuẩn bị khi bàn giao. |

API xuất Excel được kiểm tra lại trên bản bàn giao: 60 dòng dữ liệu, lưu một bản tại `data/demo/tallyv-mo-phong.xlsx`. Khi click nút Xuất Excel trong trình duyệt nhúng, công cụ kiểm tra không nhận được sự kiện download; chưa xác minh được tệp tải về phía trình duyệt nhúng. API/file Excel thực tế đã kiểm tra thành công.

Có một cảnh báo deprecation từ Starlette TestClient về httpx trong môi trường test; không làm thất bại kiểm thử. Luồng HTTP thật được kiểm tra riêng qua smoke.

Smoke test gồm 8 nhóm kiểm tra tổng hợp, chạy thật trên PostgreSQL/Mailpit/worker và tạo một số thao tác HR demo. Trạng thái bàn giao vì vậy có vài trường hợp Đã xác nhận/Cần bổ sung cùng lịch sử kiểm thử; không phải tất cả đều chưa duyệt.

## Báo cáo phân loại trên bộ đáp án riêng

`answers.json` nằm trong thư mục demo, chỉ script đánh giá đọc; bộ phân loại không đọc đáp án. Mỗi nhóm có 5 trường hợp. Kết quả RULE_BASED:

| Nhóm tình huống mô phỏng | Phân loại nguyên nhân khớp đáp án |
|---|---:|
| Đầy đủ — quên chấm công | 5/5 |
| Đầy đủ — lỗi thiết bị | 5/5 |
| Đầy đủ — phép chưa ghi nhận | 5/5 |
| Thiếu giải trình | 5/5 (UNKNOWN) |
| Thiếu ảnh | 5/5 |
| Ảnh không đọc được | 5/5 |
| Ngày trong ảnh không khớp | 5/5 |
| Mã nhân viên trong ảnh không khớp | 5/5 |
| Giải trình mơ hồ | 5/5 (UNKNOWN) |
| Ngoài phạm vi ba loại lỗi | 5/5 (UNKNOWN) |
| Thiếu ca/lượt | 5/5 |
| Nhiều ảnh cùng dòng | 5/5 |
| **Tổng phân loại nguyên nhân** | **60/60** |

Đây là bộ mẫu tạo có chủ đích với từ khóa rõ để trình diễn luồng. **60/60 không phải độ chính xác trên email thực tế, chất lượng OCR, tính hợp lệ sửa công hay khả năng tổng quát hóa.** Nhóm tên “đầy đủ” mô tả dữ liệu được tạo; OCR vẫn có thể bỏ sót ký tự và đưa về cần kiểm tra.

Trong snapshot nghiệm thu: phân loại hệ thống 25 FORGOT_CHECK, 15 DEVICE_ERROR, 5 LEAVE_NOT_RECORDED, 15 UNKNOWN. Đánh giá theo code: 18 đủ theo quy tắc demo, 32 thiếu thông tin, 10 có mâu thuẫn. OCR: 56 ảnh đọc được dữ kiện, 5 ảnh không đọc được dữ kiện nghiệp vụ; text OCR thực tế vẫn được lưu riêng. Mọi kết quả đều cần HR; có 1 phiên bản sửa chờ quyết định.

Số liệu nguồn có cả file gửi trùng và phiên bản sửa: 84 dòng = 61 dòng tạo phiên bản + 12 dòng trùng + 11 dòng lỗi. Số 61 phiên bản khác với 60 trường hợp duy nhất. Xem `demo-metrics.json` cho snapshot tổng hợp.

## Giới hạn chưa kiểm chứng / chưa triển khai

- Không chạy thành công model Ollama thật, chưa đánh giá chất lượng LOCAL_LLM; chỉ kiểm tra schema/payload và đường lỗi local. Hướng dẫn chuẩn bị model là tùy chọn.
- Chưa tích hợp SAP, hộp thư thật, SSO, phản hồi email, nhận diện khuôn mặt hoặc quy trình production.
- OCR được nghiệm thu với ảnh tạo tại local có chữ English rõ; không đảm bảo ảnh điện thoại/tiếng Việt phức tạp. Thất bại/bất nhất được giữ để HR đọc ảnh.
- Không chạy benchmark tải lớn, pentest hoặc kiểm toán mạng toàn máy. Không hỗ trợ multi-worker/scheduler trong MVP, không có antivirus chuyên dụng.
- Reset xóa thật chưa được thực hiện trên bộ demo bàn giao. Không có dữ liệu thật nào trong bộ demo.

## Ảnh kiểm tra

- `screenshots/dashboard.jpg`: tổng quan lấy dữ liệu thật từ database.
- `screenshots/model-error.jpg`: lỗi Ollama local hiển thị đúng trên trường hợp demo.
- `screenshots/mobile.jpg`: bố cục mobile, bảng cuộn trong vùng riêng.
