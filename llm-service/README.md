# Qwen 4B nội bộ cho TallyV

Ollama trong Docker chạy Qwen3.5 4B bản Q4_K_M dạng GGUF, dùng cho metadata Excel dạng text. [Unsloth lượng tử hóa từ model Qwen và phân phối GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF). Bước tải dùng revision cố định và kiểm tra SHA-256. Weights không vào Git hoặc Docker build context.

Chạy từ gốc repo:

```sh
sh llm-service/download-model.sh
docker compose -f compose.yaml -f compose.llm.yaml --profile llm up -d --wait ollama
docker compose -f compose.yaml -f compose.llm.yaml --profile llm exec -T ollama ollama show qwen3.5:4b-q4_K_M
```

Khi container khởi động, nó kiểm tra file mount chỉ đọc ở `/models`, import model từ `Modelfile` và báo healthy sau khi đăng ký xong. Ollama lưu bản import trong volume `ollama_data`. Runtime dùng mạng nội bộ của TallyV và tắt tính năng Ollama Cloud. Nó không cần tải weights khi khởi động.

Sau khi Ollama đã healthy, kết nối API và worker bằng cùng hai file Compose:

```sh
docker compose -f compose.yaml -f compose.llm.yaml --profile llm up -d --build api worker
```

Trong Docker, Assistant gọi `http://ollama:11434`. Để chạy workflow Hybrid, cấu hình runner sandbox và `ASSISTANT_PROCESSING_MODE=HYBRID` theo [hướng dẫn Assistant](../docs/assistant.md#hybrid-excel-workflow). Nếu chỉ cần Ollama cho các container trong dự án, không cần publish port.

Trên server, có thể chuẩn bị weights ở đường dẫn khác. Chạy `sh llm-service/download-model.sh /path/to/models` ở môi trường có Internet rồi chuyển file sang server. Đặt `TALLYV_LLM_MODELS_DIR=/path/to/models` để đổi mount. Nếu client ngoài Docker cần gọi API, thêm `-f compose.llm.publish.yaml` sau hai file trên. Port host mặc định là `127.0.0.1:11436`, chỉnh bằng `TALLYV_LLM_BIND_IP` và `TALLYV_LLM_HOST_PORT`. Địa chỉ nội bộ giữa các container vẫn giữ nguyên.
