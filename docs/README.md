# Tài liệu TallyV

Đồng bộ với mã nguồn ngày 14/11/2026. [README chính](../README.md) là điểm bắt đầu cài đặt và chạy dự án. Các tài liệu dưới đây phân biệt hướng dẫn đang dùng, thành phần đã ngừng tích hợp và nghiên cứu theo thời điểm.

## Hiện trạng cần nhớ

- Chấm công: tiền xử lý PII offline trong package `image-preprocessing`, chạy nền qua code bằng asyncio/FastAPI `BackgroundTasks`, chờ cả lượt xong rồi mới gửi ảnh hợp lệ lên VLM.
- Chỉ hỗ trợ tự động bố cục `FACEID` và `DEVICE_ERROR` đã cấu hình. Profile mặc định rỗng; ảnh khác chuyển nhân viên và bị chặn VLM.
- Không còn LLM văn bản, OCR, JEV hoặc embedding/cosine/SIFT ảnh lịch sử trong đánh giá chấm công. Không có queue privacy/AI mới.
- Queue PostgreSQL hiện có vẫn dùng cho email, demo, Assistant và backend HR mô phỏng. Assistant/Chatbot giữ AI và cấu hình độc lập.
- Chưa kết nối SAP thật; xác nhận HR không tự cập nhật công số vào SAP.

## Hướng dẫn hiện hành

| Tài liệu | Phạm vi |
| --- | --- |
| [Kiến trúc](architecture.md) | Module, transaction, background và queue hiện có |
| [Tiền xử lý PII và VLM](vlm-evidence.md) | API, cấu hình provider/profile, lifecycle, khởi động lại lượt bị gián đoạn |
| [Package xử lý ảnh](../image-preprocessing/README.md) | Cài độc lập, gọi code, CLI và giới hạn mặt nạ cố định |
| [Bằng chứng ảnh](evidence-images.md) | Loại ảnh, ranh giới dữ liệu và phần cần HR đánh giá |
| [Kiểm thử](verification.md) | Lệnh kiểm tra, phạm vi mock, kết quả đã ghi nhận và giới hạn smoke cũ |
| [Kho file](object-storage.md) | Local/MinIO/S3, ảnh gốc/bản sau che, backup và giới hạn công cụ chuyển kho/reset |
| [Outlook qua Composio](composio-mvp.md) | Hộp thư thử nghiệm, sync và nhập workbook |
| [Microsoft-direct Outlook](outlook.md) | Transport Microsoft riêng và cấu hình ứng dụng |
| [Kỳ lương/đợt rà soát](weekly-review.md) | Khoảng 26–25, thứ Bảy/thứ Hai, nguồn và bộ lọc |
| [Phạm vi SAP](sap-demo.md) | Bảng công mô phỏng và phần chưa tích hợp |
| [Assistant](assistant.md) | Data task, drafting, Hybrid, queue và runner riêng |
| [Runtime Qwen cho Assistant](../llm-service/README.md) | Chuẩn bị Ollama/model text; không tự cấu hình VLM chấm công |
| [Chatbot quy định](chatbot-retrieval.md) | PDF, OCR trang scan, embedding/BM25, rerank và trả lời có trích dẫn |
| [Ngôn ngữ/locale](localization.md) | Catalog dùng chung và quy ước source hiện có |
| [Từ vựng nghiệp vụ](../GLOSSARY.md) | Khái niệm Task, Run, revision và quyết định HR; không phải danh sách tính năng đã triển khai |

## Thành phần cũ và báo cáo lịch sử

| Tài liệu | Trạng thái |
| --- | --- |
| [Ảnh lịch sử](evidence-history.md) | Thông báo ngừng pipeline MobileNet/cosine/SIFT; không còn CLI lập chỉ mục |
| [Service OCR](ocr-api.md) | Mã thử nghiệm độc lập còn trong repo, không được gọi bởi đánh giá chấm công |
| [Nghiệm thu 30/10/2026](archive/verification-before-vlm.md) | Snapshot engine cũ; số liệu OCR/RULE_BASED không áp dụng cho VLM |

## Thiết kế và nghiên cứu

Các bản nghiên cứu giữ nguồn, ngày khảo sát và giới hạn ban đầu. Đợt đồng bộ này đối chiếu implementation trong repo, không tái thẩm định benchmark, giấy phép, giá, luật hoặc chính sách upstream. Phần đề xuất không mặc nhiên là chức năng đang chạy.

| Tài liệu | Cách đọc |
| --- | --- |
| [Thiết kế Assistant ban đầu](assistant-system-design.md) | Snapshot kiến trúc trước/sau hướng data task; dùng runbook Assistant cho implementation |
| [Đặc tả workflow Assistant](assistant-agent-workflow.md) | Phần Hybrid đã có và yêu cầu mở rộng chưa đầy đủ |
| [Tham chiếu Microsoft](assistant-microsoft-research.md) | Căn cứ kiến trúc tại thời điểm khảo sát |
| [Nghiên cứu JCI/cloud](assistant-jci-research.md) | Nghiên cứu theo thời điểm, không phải kết luận tuân thủ |
| [Bộ nhớ Chatbot](chatbot-memory-research.md) | Đề xuất, chưa có job trích xuất bộ nhớ dài hạn |
| [Tham chiếu UI Vinmec](vinmec-ui-research.md) | Nguồn công khai và ý tưởng giao diện |
| [Nguồn ảnh camera](cctv-workplace-datasets-research.md) | Danh mục tham khảo; CCTV hiện chỉ thử đường chuyển nhân viên/chặn VLM |
| [Khảo sát OCR/vision cũ](self-hosted-evidence-models-research.md) | Phương án tích hợp đã được thay bằng PII/VLM |
| [Thử PP-OCRv6 CPU](self-host-ppocrv6-small.md) | Tutorial nghiên cứu lịch sử, không phải bước cài TallyV |

Khi thay đổi luồng hoặc cấu hình, cập nhật runbook sở hữu phần đó và mục lục này. Không dùng số lượng tests, bảng hay kết quả demo từ snapshot cũ để mô tả bản triển khai mới.
