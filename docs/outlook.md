# Kết nối Outlook

TallyV đọc thư và tệp đính kèm trong Inbox. Đồng bộ và nhập Excel chạy trên worker dùng chung. Phân quyền người gửi và nội dung workbook được kiểm tra trước khi tạo hồ sơ.

## Composio cho hộp thư thử nghiệm

Dùng một hộp thư riêng chứa dữ liệu giả lập. Thông tin thư và tệp phù hợp đi qua Composio. Cấu hình dùng `OUTLOOK_TEST_MODE=true`.

1. Tạo project trong [Composio](https://dashboard.composio.dev) và lấy project API key.
2. Chạy `venv/bin/python -m scripts.configure_composio` trên máy host. Script tạo cấu hình OAuth chỉ đọc và lưu khóa cùng auth config ID vào `.env`.
3. Khởi động stack với overlay Outlook rồi chọn **Kết nối Outlook** trong TallyV. Hoàn tất đăng nhập và cấp quyền tại Microsoft.

```sh
docker compose -f compose.yaml -f compose.outlook.yaml up -d --build
```

Lần kết nối đầu tiên tự lên lịch đồng bộ. Các lần sau dùng **Quét Outlook**. `COMPOSIO_POLL_INTERVAL=0` giữ chế độ quét thủ công. Nếu bật polling, giá trị tối thiểu là 60 giây.

## Microsoft Graph trực tiếp

Tạo ứng dụng Web trong Microsoft Entra, đặt redirect URI `http://localhost:8000/api/outlook/callback` cho local và cấp delegated scopes `User.Read`, `Mail.Read`. Dùng giá trị secret của ứng dụng trên backend. Đăng ký app và cấp quyền cần tuân theo cấu hình tenant. [Hướng dẫn đăng ký ứng dụng Microsoft](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app)

```dotenv
MAIL_PROVIDER=outlook
OUTLOOK_TRANSPORT=microsoft
OUTLOOK_TENANT_ID=common
OUTLOOK_CLIENT_ID=
OUTLOOK_CLIENT_SECRET=
OUTLOOK_REDIRECT_URI=http://localhost:8000/api/outlook/callback
OUTLOOK_SYNC_DAYS=90
OUTLOOK_TEST_MODE=true
```

Dùng đúng origin trong callback để mở TallyV. Với HTTPS, cập nhật `ALLOWED_ORIGINS` và bật `COOKIE_SECURE=true`. Khởi động API/worker với overlay Outlook. Sau khi đổi biến môi trường Compose, dùng `up -d` để tạo lại container với cấu hình mới.

## Nhập thư thử

1. Đăng ký khoa/phòng, địa chỉ người gửi và nhân viên mẫu trong TallyV. Phòng ban và mã nhân viên trong workbook phải khớp danh mục.
2. Gửi email đến địa chỉ nhận của hộp thư đã kết nối. Trong chế độ thử nghiệm, đặt tiêu đề có `[TALLYV-MVP]`, `[DCC]`, kỳ lương và ngày thứ Bảy của đợt, chẳng hạn `[TALLYV-MVP] [DCC] [2026-11] [WEEK:2026-11-07] Điều chỉnh chấm công`.
3. Chọn **Quét Outlook** rồi xem kết quả nhập trong **Hộp thư**. Khi cần đọc lại thư cũ, chọn chế độ quét lại và cửa sổ 1–365 ngày. Sau khi nhập xong, HR chủ động chạy **Đánh giá và phân loại**. [Mẫu workbook và quy trình](attendance.md)

Nếu chuyển transport, ngắt kết nối hộp thư cũ trước và kết nối lại sau khi chạy cấu hình mới. Thay đổi transport giữ các hồ sơ đã nhập.
