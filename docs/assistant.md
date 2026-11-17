# Assistant phân tích dữ liệu và soạn báo cáo

Mở **Assistant** tại `/?app=assistant`. Chọn mẫu phân tích số liệu hoặc soạn hồ sơ. Tải nguồn, nhập yêu cầu và đính kèm mẫu báo cáo nếu cần. Assistant chạy trên worker TallyV với job `ASSISTANT_GENERATE` và dùng cấu hình `ASSISTANT_*`.

## Phân tích và rà soát

- Nguồn thường dùng là XLSX hoặc CSV. Chế độ phân tích có thể đọc bảng có cấu trúc từ một số tệp TXT, DOCX hoặc PDF có lớp chữ. Với XLSX có công thức, chuẩn bị bản chỉ chứa giá trị.
- Assistant xác định bảng và phép xử lý, hỏi HR khi có phân loại chưa rõ rồi tính kết quả bằng công cụ. HR có thể xem dòng nguồn và sửa phân loại. Chỉnh sửa tạo revision mới và tính lại báo cáo.
- Kết quả có thể gồm Excel tổng hợp, bảng chi tiết, báo cáo DOCX/XLSX và ZIP có dấu vết nguồn. Với mẫu báo cáo, có thể dùng `{{total_rows}}`, `{{source_rows}}` và marker bảng `{{summary_table}}`. HR duyệt phiên bản đang xem.
- Mỗi yêu cầu đính kèm tối đa 6 tệp, mỗi tệp 15 MB. Giới hạn mặc định của tác vụ dữ liệu là 10.000 dòng. Cấu hình ở `ASSISTANT_MAX_DATA_ROWS`.

## Chạy model

`ASSISTANT_PROCESSING_MODE=LOCAL_LLM` mặc định dùng Ollama tại `http://127.0.0.1:11435` và model `llama3.2:latest`. Cấu hình bằng `ASSISTANT_OLLAMA_URL`, `ASSISTANT_OLLAMA_MODEL` và `ASSISTANT_MODEL_TIMEOUT`. Trong Docker, dùng `ASSISTANT_DOCKER_OLLAMA_URL` hoặc [overlay Ollama](../llm-service/README.md). `RULE_BASED` dùng cho luồng soạn tài liệu theo quy tắc.

## Hybrid Excel workflow

Chọn `ASSISTANT_PROCESSING_MODE=HYBRID` để xử lý bảng Excel theo từng giai đoạn có lưu tiến độ. Dùng `ASSISTANT_HYBRID_OLLAMA_MODEL` cho model nội bộ. `ASSISTANT_HYBRID_SHEET_PROVIDER` chọn nơi nhận thông tin schema của sheet. Khi đặt `openrouter`, bước này gửi nhãn cột và kiểu dữ liệu, không gửi các giá trị ô.

Với tính năng chạy script Hybrid, dùng runner nội bộ trên Linux với Docker/gVisor `runsc` và image `python:3.11-slim` đã chuẩn bị. Khởi động runner trên máy đó. Cấu hình `ASSISTANT_SANDBOX_TOKEN` ở cả runner và TallyV, cùng `ASSISTANT_SANDBOX_URL` và `OPENROUTER_API_KEY` ở TallyV.

```sh
python -m uvicorn scripts.assistant_sandbox:app --host 127.0.0.1 --port 8100 --no-access-log
```

Worker đối chiếu đầu ra của runner với kết quả chuẩn tính bằng công cụ nội bộ trước khi phát hành artifact. Với Docker Desktop và Linux VM, dùng [overlay sandbox](../compose.assistant-sandbox.local.yaml) và CA TLS nội bộ nếu runner được truy cập ngoài loopback.

## Kiểm tra

Dùng bộ mẫu trong giao diện để chạy từ yêu cầu đến báo cáo và thử sửa một nhóm phân loại. Trên môi trường có Ollama, `venv/bin/python -m scripts.verify_assistant_data` chạy kiểm tra với dữ liệu giả lập và SQLite tạm. Xem [thuật ngữ nghiệp vụ](../GLOSSARY.md).
