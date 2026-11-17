# Chatbot tra cứu quy định

HR nhập PDF, kiểm tra kết quả trích xuất và bấm **Công bố** để nhân viên tra cứu. Nhân viên đăng nhập tại `/employee` bằng tài khoản `EMPLOYEE`. Tài liệu mới ở trạng thái chưa công bố.

## Thiết lập và nhập PDF

Chatbot cần PostgreSQL với pgvector và `OPENROUTER_API_KEY`. Tải PDF trong giao diện HR hoặc dùng lệnh sau khi áp dụng migration.

```sh
venv/bin/python -m app.chatbot.create_employee employee.demo
venv/bin/python -m app.chatbot.import_pdfs /duong-dan-noi-bo/quy-dinh.pdf
```

Mỗi PDF tối đa 20 MB và 100 trang. Các trang có lớp chữ dùng văn bản nhúng. Trang scan được gửi đến model OCR của **Chatbot**. Dùng `--force-ocr` nếu cần OCR toàn bộ các trang khi nhập tệp mới. Có thể điền tiêu đề, đơn vị ban hành và loại văn bản để lọc.

## Tra cứu

Ô tìm kiếm trả đoạn trích và liên kết đến trang PDF. Hỏi đáp kết hợp BM25 và pgvector, xếp hạng lại các đoạn rồi gửi cho model trả lời. Backend kiểm tra ID nguồn và quyền công bố trước khi hiển thị trích dẫn. Cấu hình Chatbot qua `POLICY_OCR_MODEL`, `POLICY_RERANK_MODEL` và `POLICY_ANSWER_MODEL`.
