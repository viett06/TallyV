# Cổng tra cứu quy định dành cho nhân viên

Nhân viên mở `/employee` và đăng nhập bằng tài khoản có vai trò `EMPLOYEE`. Tạo hoặc đặt lại mật khẩu từ thư mục TallyV bằng `venv/bin/python -m app.chatbot.create_employee employee.demo`. Tài khoản dùng cookie riêng cho cổng. Trong Chatbot của HR, bấm **Công bố** để nhân viên tra cứu tài liệu và mở PDF nguồn. Mỗi tài liệu mới ở trạng thái chưa công bố.

## Kho văn bản và bộ lọc

Sau khi đăng nhập, cổng hiển thị danh mục văn bản đã công bố. Khi tải PDF trong trang HR, có thể điền tên hiển thị, đơn vị ban hành và loại văn bản. Có thể lọc theo loại hoặc theo từng PDF.

Ô tìm kiếm khớp nguyên cụm từ sau khi chuẩn hóa dấu, chữ hoa và khoảng trắng. Kết quả hiển thị các đoạn trích được tô sáng và mở đúng trang PDF. Nút trợ lý ở góc màn hình dùng luồng hỏi đáp có trích dẫn bên dưới.

## Truy xuất và trả lời

TallyV tham chiếu kiến trúc Azure AI Search của Microsoft. Hai nhánh xếp hạng độc lập gồm BM25 trên văn bản đã chuẩn hóa dấu tiếng Việt và cosine trên pgvector. BM25 bổ sung một ứng viên từ vựng gần nhất cho từ dài chưa có trong kho. Reciprocal Rank Fusion (RRF) hợp nhất hai danh sách theo thứ hạng. Cohere Rerank qua OpenRouter chọn tối đa tám đoạn từ tối đa 30 ứng viên đã hợp nhất. [Hybrid search](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview) · [RRF và semantic ranking](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking) · [Fuzzy search](https://learn.microsoft.com/en-us/azure/search/search-query-fuzzy) · [Cohere trên OpenRouter](https://docs.cohere.com/docs/cohere-on-openrouter)

Gemini nhận các đoạn đã xếp hạng và trả từng ý kèm ID đoạn. Backend kiểm tra ID và quyền công bố trước khi trả tên tệp, trang PDF, mục và đoạn trích cho giao diện. Mô hình mặc định dùng `OPENROUTER_API_KEY`, `POLICY_RERANK_MODEL=cohere/rerank-4-fast` và `POLICY_ANSWER_MODEL=google/gemini-2.5-flash`. Với kho mẫu, BM25 chạy trên các đoạn đã công bố và pgvector tìm cosine chính xác.

## Liên kết giữa tài liệu

- Công văn Than Uyên về nghỉ phép năm 2026, trang PDF 1, dẫn mẫu đăng ký kèm theo. Mẫu nằm ở trang PDF 2. Khi hỏi về mẫu, hệ thống có thể thêm trang đích nếu tìm được đúng tiêu đề và năm trong cùng tệp.
- Quy chế Ninh Hòa, trang PDF 12, dẫn phụ lục 01 và 02. Chưa xác định được trang đích tương ứng trong kho.
- Sổ tay Từ Dũ, các trang PDF 23, 25, 27 và 37, dẫn các quyết định nội bộ chưa nạp vào kho.

Ba PDF thuộc ba bệnh viện và chưa có dẫn chiếu đã xác minh từ một PDF đến hai PDF còn lại. GraphRAG của Microsoft dùng thực thể và quan hệ để mở rộng ngữ cảnh, đồng thời tạo báo cáo cộng đồng cho câu hỏi tổng hợp. Dữ liệu hiện có phù hợp với mở rộng liên kết đã xác minh trong cùng PDF. [Microsoft GraphRAG](https://microsoft.github.io/graphrag/) · [GraphRAG Local Search](https://microsoft.github.io/graphrag/query/local_search/)
