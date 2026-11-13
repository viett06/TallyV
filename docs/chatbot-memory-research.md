# Nghiên cứu bộ nhớ cho chatbot TallyV

> Trạng thái đối chiếu 14/11/2026: đây là đề xuất mở rộng Chatbot, chưa có job trích xuất bộ nhớ hay kho mẩu nhớ dài hạn trong implementation hiện tại. Không cấu hình queue hoặc model theo đề xuất bên dưới để vận hành chấm công. Xem [Chatbot đang chạy](chatbot-retrieval.md) và [phạm vi các module](architecture.md). Các nguồn upstream là snapshot nghiên cứu, chưa được rà soát lại trong đợt đồng bộ docs.

## Hiện trạng

`POST /api/chatbot/employee/ask` nhận một câu hỏi và gọi trực tiếp `answer_question`. Giao diện giữ các lượt hỏi đáp trong `useState`; backend không nhận lịch sử hay ID hội thoại. PostgreSQL + pgvector đã có trong Compose. Module Assistant có mô hình hội thoại riêng. [API chatbot](../app/chatbot/employee_api.py) · [Widget](../frontend/src/chatbot/EmployeeChatWidget.tsx) · [Compose](../compose.yaml) · [Dịch vụ hội thoại Assistant](../app/assistant/services/conversations.py)

## Mẫu kiến trúc của Microsoft

- **Foundry Agent Service Memory (preview)** phân biệt ngữ cảnh phiên hiện tại với bộ nhớ dài hạn do dịch vụ quản lý. Dịch vụ trích xuất thông tin, hợp nhất các mẩu nhớ và truy xuất theo phạm vi người dùng. Microsoft mô tả hồ sơ người dùng, tóm tắt hội thoại và bộ nhớ quy trình. Hồ sơ ổn định có thể nạp đầu hội thoại, còn tóm tắt liên quan được tìm theo lượt. Dịch vụ hỗ trợ chỉnh sửa/xóa từng mục, thời gian lưu và trì hoãn cập nhật sau khi hội thoại ngừng hoạt động. [Khái niệm](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory) · [Hướng dẫn và phạm vi](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage)
- **Microsoft Agent Framework** phân biệt `RedisHistoryProvider`, lưu lại nguyên văn hội thoại theo phiên, với `RedisContextProvider`, trích xuất chi tiết và tìm ngữ cảnh liên quan. Provider lịch sử tìm kiếm của Framework cũng có thể truy xuất tin nhắn đã lưu theo vector và phạm vi ứng dụng, agent, người dùng, phiên. Các lựa chọn này cho thấy lịch sử phiên và bộ nhớ đã chắt lọc có vòng đời riêng. [Redis providers](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/context-providers/redis) · [Chat History Memory Provider](https://learn.microsoft.com/en-us/agent-framework/concepts/agents/conversations/chat-history-memory-provider)

## Đề xuất cho MVP

| Thành phần | Lưu ở đâu | Nội dung |
| --- | --- | --- |
| Ngắn hạn | PostgreSQL | Hội thoại và tin nhắn theo `user_id` và `conversation_id`; nạp 4–6 lượt gần nhất trong ngân sách token, tóm tắt phần cũ khi vượt ngân sách. |
| Dài hạn | PostgreSQL | Mỗi mẩu nhớ là một thuộc tính có kiểu, với `user_id`, `fact_key`, `value`, `source_message_id`, thời điểm cập nhật và `expires_at` khi có thời hạn. Chỉ đọc các khóa liên quan từ một danh sách nhỏ; cân nhắc pgvector sau khi có nhu cầu tìm ngữ nghĩa trên dữ liệu phi cấu trúc. |
| Tài liệu HR | Kho RAG hiện tại | Quy định từ PDF đã công bố, luôn dẫn tệp và trang. Số dư phép, phân ca, hồ sơ cá nhân lấy từ HRIS được phân quyền nếu có tích hợp. |
| Cache tùy chọn | Redis | Cache bản tóm tắt và vài lượt gần nhất khi số liệu cho thấy tải đọc/độ trễ PostgreSQL tăng đáng kể. Key có phạm vi người dùng và hội thoại, TTL 30 phút là giá trị thử nghiệm. Cache miss hoặc Redis lỗi thì dựng lại từ PostgreSQL; vô hiệu hóa khi sửa/xóa và chỉ ghi cache sau khi DB commit. [Redis EXPIRE](https://redis.io/docs/latest/commands/expire/) |

Tách bộ nhớ trong `app/chatbot`. Phạm vi lấy từ ID nhân viên đã xác thực và module chatbot, thêm tenant nếu có. Backend kiểm tra quyền sở hữu khi đọc, ghi và xóa. Luồng hỏi đáp đọc ngữ cảnh phiên, dùng ngữ cảnh để diễn giải câu hỏi nối tiếp, rồi chạy Hybrid RAG và kiểm tra trích dẫn như hiện tại. Ví dụ sau câu hỏi về hạn nộp bảng công, “Vậy nộp cho ai?” được diễn giải thành câu hỏi về đơn vị nhận bảng chấm công; thông tin trả lời lấy lại từ PDF.

Với bộ nhớ dài hạn, bắt đầu bằng các thuộc tính ít rủi ro do nhân viên nói rõ, như ngôn ngữ, độ dài trả lời hoặc cách trình bày. Cho người dùng xem, sửa và quên từng mục. Khoa/phòng hoặc cơ sở ảnh hưởng việc áp dụng chính sách cần xác thực qua nguồn có thẩm quyền trước khi dùng để giới hạn tài liệu; thông tin tự khai chỉ giúp làm rõ câu hỏi. Giữ dữ liệu sức khỏe, mã định danh nhạy cảm, thông tin người khác và bí mật ngoài kho mẩu nhớ và payload trích xuất.

Sau lượt chat, dùng hàng đợi PostgreSQL và worker hiện có để trích xuất các tin nhắn mới bằng Gemini qua OpenRouter. Payload job chỉ chứa ID để worker đọc lại dữ liệu đã phân quyền. Có thể gom sau một khoảng ngừng chat theo mẫu Foundry. TallyV giữ OpenRouter và tự triển khai cơ chế bộ nhớ. [Worker](../app/worker.py) · [Hàng đợi PostgreSQL](../app/crud/jobs.py) Model trả JSON đề xuất gồm thao tác, khóa, giá trị và ID tin nhắn nguồn. Backend lọc khóa và xác thực nguồn, hợp nhất theo `(user_id, fact_key)`, bỏ qua nội dung mơ hồ hoặc tạm thời, và xử lý lại an toàn theo ID nguồn. Sửa và quên bằng thao tác rõ ràng cập nhật ngay; hủy hoặc bỏ qua job cũ để dữ liệu đã xóa không quay lại. Bắt đầu với lệnh “nhớ giúp tôi…”; sau đó bật tự động cho các khóa được phép sau khi đánh giá khả năng trích xuất. Đặt thời gian lưu lịch sử theo mục đích sử dụng, tách với TTL của cache.

## Thứ tự triển khai và nghiệm thu

1. **Hội thoại nhiều lượt.** Cùng nhân viên và cùng hội thoại có thể hỏi nối tiếp sau reload, bot dùng đúng chủ thể và vẫn dẫn trang PDF. Hội thoại mới không mang chủ đề đang hỏi của hội thoại cũ. Đổi tài khoản hoặc đoán ID hội thoại không truy cập được dữ liệu người khác.
2. **Mẩu nhớ có cấu trúc.** “Từ nay trả lời ngắn gọn” áp dụng sau khi mở hội thoại mới; “hôm nay trả lời ngắn thôi” chỉ áp dụng trong ngữ cảnh hiện tại. Thay đổi và xóa mục phải có hiệu lực sau reload. Retry hoặc tác vụ hoàn tất muộn không ghi đè giá trị mới hoặc khôi phục mục đã xóa.
3. **Đo rồi mở rộng.** Đo thời gian truy xuất ngữ cảnh và chi phí model trước khi thêm Redis hoặc tìm mẩu nhớ theo vector. Nếu dùng Redis, kiểm thử cache hết hạn, Redis ngắt kết nối và xóa dữ liệu xuyên qua cache. Luồng trả lời chính sách vẫn tiếp tục nếu tác vụ trích xuất bộ nhớ gặp lỗi.
