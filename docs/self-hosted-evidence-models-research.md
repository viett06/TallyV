# Nghiên cứu OCR và hiểu ảnh bằng chứng tự vận hành cho TallyV

> Snapshot nghiên cứu ngày 01/11/2026, giữ để tham khảo. Từ 14/11/2026, đề xuất OCR/hiểu cảnh và ranh giới implementation mô tả bên dưới không còn là luồng đánh giá đang chạy. Hiện tại dùng [tiền xử lý PII offline rồi VLM](vlm-evidence.md); không dùng OCR, JEV hoặc embedding lịch sử trong đánh giá. Nguồn và benchmark upstream bên dưới chưa được kiểm tra lại trong đợt đồng bộ docs này.

Ngày đối chiếu nguồn: **01/11/2026**. Phạm vi: demo ý tưởng trong ba tuần, ngân sách dịch vụ bằng 0, máy cá nhân hạn chế tài nguyên; hướng tới dữ liệu nhạy cảm trong bệnh viện. Đây là đánh giá ứng viên, chưa phải kết quả kiểm thử trên ảnh thực tế của bệnh viện hoặc xác nhận đủ điều kiện triển khai.

Tại thời điểm khảo sát, TallyV gọi Tesseract local với `lang="eng"` và tìm một số mã/ngày/từ khóa trong chữ đọc được; chưa có model hiểu cảnh nhận ảnh gốc. Việc Docker có cài gói tiếng Việt chưa đồng nghĩa hàm OCR hiện sử dụng nó. Nguồn: [analysis.py](../app/services/analysis.py), [Dockerfile](../Dockerfile).

## Kết luận đề xuất

Thử **PP-OCRv6 small chạy CPU** cho chữ hiển thị trên ảnh trước; đối chứng bằng PP-OCRv5 mobile detector + Latin recognizer. Nếu CPU quá chậm, đo thêm v6 tiny thay vì mặc định giảm chất lượng. Chỉ bổ sung **Qwen3-VL-2B-Instruct chạy nội bộ** khi cần mô tả bối cảnh; phiên bản 4B là phương án đối chứng nếu có tài nguyên. Đây là quyết định kỹ thuật đề xuất, chưa có đo đạc tại TallyV.

OCR và hiểu ảnh là hai công việc khác nhau. Không nên chọn một model đọc tài liệu rồi mặc định rằng nó có thể đánh giá CCTV, xác minh người trong ảnh hay kết luận đủ công. Các giới hạn nghiệp vụ dưới đây là yêu cầu thiết kế đề xuất.

| Bằng chứng người dùng mô tả | TallyV nên trích xuất/hỗ trợ | Giới hạn cần giữ |
| --- | --- | --- |
| Ảnh từ máy quét mặt/cổng vào | Chữ, mã nhân viên nếu thực sự hiển thị, thời gian, tên thiết bị/cổng, trạng thái trên giao diện | Không đối chiếu khuôn mặt để xác định danh tính. Một lần xuất hiện không chứng minh đủ ca làm việc. |
| Ảnh CCTV khu vực làm việc | Timestamp nếu đọc được; mô tả quan sát trực tiếp như có người tại bàn hoặc khu vực nào | Không suy ra người đó là ai, năng suất, có làm việc liên tục, hay công số được hưởng từ một ảnh. |
| Điện thoại chụp màn hình máy chấm công lỗi | Nội dung thông báo, mã lỗi, thời gian hiển thị, tình trạng chữ bị lóa/mờ | Ảnh có chữ báo lỗi không tự chứng minh thiết bị thực sự lỗi vào thời điểm yêu cầu; cần HR đối chiếu nguồn/log nếu có. |

## Các model được kiểm tra

### OCR chuyên đọc chữ

PaddleOCR phát hành PP-OCRv6 cùng phiên bản 3.7.0 ngày 11/06/2026. Dòng này nhắm cả chữ trong cảnh thực, màn hình số và tình huống công nghiệp. [README chính thức](https://github.com/PaddlePaddle/PaddleOCR#-recent-updates).

| Ứng viên | Quy mô/kích thước công bố | Vai trò trong thử nghiệm |
| --- | --- | --- |
| PP-OCRv6 tiny, detector + recognizer | Tổng khoảng 1.5M tham số; file detector 1.9 MB, recognizer 4.4 MB | Phương án giảm tài nguyên; phải đo khả năng đọc dấu tiếng Việt và chữ nhỏ. |
| PP-OCRv6 small, detector + recognizer | Tổng khoảng 7.7M tham số; file detector 9.6 MB, recognizer 20.4 MB | Ứng viên OCR chính để thử trước trên CPU. |
| PP-OCRv5 mobile detector + `latin_PP-OCRv5_mobile_rec` | File detector 4.7 MB, Latin recognizer 14 MB | Baseline thay thế nếu môi trường chạy v6 có vấn đề. |

Số tham số v6: [tài liệu thuật toán](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv6/PP-OCRv6.html). Kích thước file từng model: [bảng model của pipeline OCR](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md). **MB ở bảng là lưu trữ model, không phải RAM cần để chạy.**

V6 small/medium hỗ trợ 50 ngôn ngữ; tiny hỗ trợ 49, bỏ tiếng Nhật. **Tiếng Việt có tên trong cả ba danh sách**. Tuy vậy, benchmark Latin do tác giả công bố cho tiny là 63.8%, small 84.0%; không nên lựa chọn tiny chỉ vì nhỏ, và không dùng các điểm đó làm tỷ lệ đúng trên ảnh bệnh viện. Đây là kết quả benchmark của nhóm phát triển, chưa phải đo độc lập tại TallyV. [Báo cáo PP-OCRv6, phụ lục A và bảng 11](https://arxiv.org/html/2606.13108v1#A1).

V5 dùng nhận dạng tiếng Việt qua **`latin_PP-OCRv5_mobile_rec`**, mã ngôn ngữ `vi`; không thay thế bằng `en_PP-OCRv5_mobile_rec` hoặc mặc định cho rằng recognizer v5 tiếng Trung/Anh sẽ đọc đủ dấu. [Danh sách ngôn ngữ và model v5 chính thức](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md).

PaddleOCR có đường chạy CPU và nhiều hệ điều hành; tài liệu v6 có cả số đo trên Apple M4. Không thể suy ra tốc độ trên máy người dùng từ số đo đó. Cũng chưa tìm thấy mức RAM tối thiểu cố định của pipeline áp dụng cho mọi độ phân giải/số chữ. [Hướng dẫn và benchmark v6](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv6/PP-OCRv6.html).

Khi thử nghiệm phải chỉ rõ detector/recognizer small hoặc tiny; gọi `PaddleOCR()` không cấu hình đang mặc định v6 **medium** theo tài liệu hiện hành. [Pipeline OCR](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md).

### Model hiểu ảnh và OCR sinh văn bản

| Ứng viên | Khả năng được nguồn chính thức mô tả | Đánh giá phù hợp với TallyV |
| --- | --- | --- |
| **Qwen3-VL-2B-Instruct** | Nhận ảnh + chữ; hiểu hình ảnh/video; OCR đa ngôn ngữ. [Model card](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct) | Ứng viên VLM đầu tiên cho mô tả bối cảnh, nếu máy đáp ứng. Phải đo riêng timestamp, tiếng Việt và khả năng trả lời thiếu dữ kiện. |
| **Qwen3-VL-4B-Instruct** | Cùng họ model, quy mô lớn hơn. [Model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) | Đối chứng 2B khi có tài nguyên; chưa có bằng chứng tại đây rằng 4B tốt hơn cho ảnh chấm công của người dùng. |
| **SmolVLM-500M-Instruct** | Đọc/mô tả ảnh, hỏi đáp, chép chữ; model card ghi ngôn ngữ NLP là English. [Model card](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct) | Phương án thăm dò rất nhẹ cho mô tả đơn giản; không lấy làm OCR tiếng Việt chính. |
| **PaddleOCR-VL-1.6, 0.9B** | Chuyên phân tích tài liệu: chữ, bố cục, bảng, biểu đồ, công thức, con dấu và text spotting. [Model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) | Ứng viên cho ảnh tài liệu/phụ lục khó; không chọn chỉ dựa vào benchmark tài liệu để xử lý CCTV. |
| **Gemma 3 4B IT** | Nhận chữ + ảnh, hiểu ảnh; có cách chạy local bằng Transformers. [Google model card](https://ai.google.dev/gemma/docs/core/model_card_3), [weight card](https://huggingface.co/google/gemma-3-4b-it) | Có thể đối chứng, nhưng thêm một họ model chưa đem lại lợi ích rõ trong demo ba tuần; ưu tiên tập trung shortlist. |

Qwen3-VL công bố mở rộng OCR tới 32 ngôn ngữ và hỗ trợ ảnh thiếu sáng/mờ/nghiêng. Những mô tả đó là của tác giả, không xác lập độ chính xác cho chữ tiếng Việt trên CCTV bệnh viện. Repo có ví dụ dùng file ảnh/video local và giới hạn kích thước ảnh/frame để kiểm soát tài nguyên. [Repo Qwen3-VL](https://github.com/QwenLM/Qwen3-VL).

VLM có thể tạo câu trả lời hợp lý nhưng sai chữ. Kết quả OCR nên giữ cả ảnh vùng đọc được và chuỗi gốc; model hiểu bối cảnh không được tự sửa mã nhân viên/ngày giờ theo nội dung Excel. Nghiên cứu PP-OCRv6 cũng nêu hallucination là một vấn đề của OCR bằng VLM; điều đó không có nghĩa OCR chuyên dụng luôn đúng. [Báo cáo PP-OCRv6, phần giới thiệu và đánh giá hallucination](https://arxiv.org/html/2606.13108v1).

### Tài nguyên: số công bố và phần chưa biết

| Model | Số liệu/phương thức đã kiểm tra | Không được suy ra |
| --- | --- | --- |
| PP-OCRv6 small/tiny | Có đường CPU và benchmark chính thức; chưa có mức RAM tối thiểu cố định cho workload này. [Docs](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv6/PP-OCRv6.html) | File weights vài MB không đồng nghĩa tiến trình chỉ dùng vài MB RAM. |
| Qwen3-VL 2B/4B | Có hướng dẫn tự tải và chạy Transformers; nguồn đã xem không đưa một mức VRAM tối thiểu cho cấu hình ảnh TallyV. [2B](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct), [4B](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) | Không hứa máy yếu chạy nhanh, không gán “cần đúng 4 GB/8 GB VRAM”. Context, ảnh, lượng tử hóa và runtime đều cần đo. |
| SmolVLM 500M | Tác giả công bố **1.23 GB GPU RAM cho một ảnh**, có ví dụ fallback CPU. [Card](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct) | Đây không phải RAM toàn máy hoặc bảo đảm với mọi kích thước ảnh/batch. |
| PaddleOCR-VL-1.6 | Có ví dụ Transformers chọn CUDA nếu có, CPU nếu không; chưa thử pipeline này trên máy người dùng. [Card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) | 0.9B không tự động nhẹ hơn mọi pipeline OCR; document pipeline còn có các thành phần khác. |

Chưa benchmark hay tải model trong đợt nghiên cứu này. Khuyến nghị CPU-first là lựa chọn theo ràng buộc dự án, không phải kết luận về cấu hình tối thiểu. Miễn phí weights không tạo ra GPU cloud miễn phí và riêng tư.

### Giấy phép: kiểm tra weights riêng với code

- **PaddleOCR code**: Apache-2.0. Các weight card đã xem cho v6 tiny/small recognizer, v5 Latin recognizer và PaddleOCR-VL-1.6 cũng khai báo Apache-2.0. Cần lưu license/revision của đúng detector, recognizer và dependency khi đóng gói. [Code license](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE), [v6 tiny weights](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_rec), [v6 small weights](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec), [v5 Latin weights](https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec), [VL weights](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6).
- **Qwen3-VL**: code repo Apache-2.0; weight card 2B/4B Instruct cũng Apache-2.0. Không suy rộng giấy phép này cho mọi model mang tên Qwen. [Code license](https://github.com/QwenLM/Qwen3-VL/blob/main/LICENSE), [2B card](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct), [4B card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct).
- **SmolVLM-500M-Instruct**: weight card khai báo Apache-2.0; runtime và dependency cần được kiểm kê riêng. [Card](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct).
- **Gemma 3 4B**: weights theo điều khoản Gemma riêng; Hugging Face yêu cầu đồng ý điều kiện truy cập, không phải Apache-2.0 chỉ vì thư viện chạy có thể dùng Apache. [Weight card và điều kiện truy cập](https://huggingface.co/google/gemma-3-4b-it).
- **Không chọn Qwen2.5-VL-3B-Instruct làm mặc định cho hướng triển khai công ty**: license weights thực tế là **Qwen RESEARCH LICENSE**, chỉ cấp sử dụng non-commercial/research/evaluation, commercial phải xin giấy phép riêng. Đây là điều khoản được ghi trong repository weights; không suy từ giấy phép code Qwen. [LICENSE của đúng model](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/blob/main/LICENSE).

Đã kiểm tra thêm weight card của ba detector tương ứng: [v6 small](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det), [v6 tiny](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_det), [v5 mobile](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det) đều khai báo Apache-2.0. Vẫn cần giữ license và khóa đúng revision của artifact thực tế được triển khai.

## Phương án tích hợp từng được đề xuất — đã thay thế

1. Nhập Excel và ảnh vào hệ thống như luồng đã thống nhất; bước nhập không tự chạy đánh giá/phân loại.
2. Khi HR bấm **Đánh giá và phân loại**, OCR đọc chữ theo vùng. Mã nhân viên, thời gian, lỗi chỉ lấy khi nhìn thấy; thiếu thì giữ `null`.
3. VLM tùy chọn mô tả sự kiện nhìn thấy và loại ảnh. Không hỏi model “người này có đủ công không”.
4. Quy tắc TallyV đối chiếu các dữ kiện với yêu cầu. Nếu thiếu/khác nhau thì ghi “chưa đủ căn cứ” để HR kiểm tra, giữ ảnh và vùng chữ liên quan cho HR xem.
5. HR xác nhận kết quả nghiệp vụ. Tích hợp nhập SAP theo từng loại case là một lớp riêng cần thiết kế sau, không nằm trong phạm vi nghiên cứu OCR này.

Ví dụ hợp đồng dữ liệu để thử nghiệm:

```json
{
  "evidence_type": "terminal_screen",
  "observed_time_text": "2026-10-31 08:02:13",
  "visible_employee_id_text": null,
  "visible_error_text": "Không kết nối máy chủ",
  "scene_observation": "Màn hình thiết bị hiển thị thông báo lỗi",
  "readability": "partial",
  "source_regions": [],
  "requires_hr_review": true
}
```

Đây là schema đề xuất. Mỗi trường text phải có vùng ảnh hoặc lý do không đọc được; không sử dụng điểm “confidence” model tự kể như một xác suất chính xác đã hiệu chuẩn. Chữ trên ảnh là dữ liệu, kể cả khi chứa câu yêu cầu model thực hiện hành động; không được dùng làm lệnh điều khiển.

## Kế hoạch kiểm chứng bằng dữ liệu giả lập

Không cần gửi dữ liệu bệnh viện để chọn shortlist. Tạo bộ mẫu giả lập có đáp án do người viết tay, bao gồm người giả/dummy, timestamp và mã không thuộc nhân viên thật. Đây là kế hoạch đề xuất, chưa được thực hiện.

| Nhóm mẫu | Tình huống cần có | Đáp án cần chấm |
| --- | --- | --- |
| Giao diện quét mặt/cổng vào | Có/không mã, Việt/Anh, ngày giờ khác định dạng, timestamp bé | Chuỗi chữ, mã, ngày giờ đúng; không bịa mã/danh tính khi vắng chữ |
| Camera nơi làm việc | Có/không timestamp, nhiều người, che khuất, ghế trống, ảnh tối | Đọc giờ nếu có, mô tả điều nhìn thấy, không suy danh tính/đủ ca |
| Điện thoại chụp máy lỗi | “mất mạng”, mã lỗi, thông báo bình thường đối chứng, lóa/nghiêng/mờ | Đúng lỗi được hiển thị, không nhầm màn hình thành công thành lỗi |
| Mẫu âm tính/đánh lừa | Không chữ, timestamp không đọc được, ảnh không liên quan, dữ kiện trái Excel | Trả thiếu dữ kiện/không liên quan, không điền từ Excel hoặc tưởng tượng |

Đề xuất tối thiểu 90 ảnh (30 mỗi nhóm chính), chia theo mẫu gốc trước khi tạo biến thể. Không để một ảnh gốc ở tập phát triển và bản làm mờ của nó ở tập kiểm tra. Thêm bộ âm tính riêng và khóa tập kiểm tra trước khi điều chỉnh prompt/ngưỡng.

Đo riêng:

- **OCR:** CER (lỗi ký tự), tỷ lệ đúng nguyên chuỗi timestamp/mã/lỗi; chuẩn hóa Unicode có chủ đích, giữ cả chuỗi gốc và chuỗi chuẩn hóa.
- **Trích xuất:** field precision/recall và tỷ lệ điền sai trường vốn không có. Đặc biệt đếm mọi timestamp/mã nhân viên bị bịa; không chỉ báo một điểm OCR chung.
- **Ngữ cảnh ảnh:** nhầm loại bằng chứng, nhận sai thông báo lỗi/thành công, mô tả không có trong ảnh, bỏ sót tình huống cần HR kiểm tra. Không chấm khả năng đoán danh tính từ mặt.
- **Vận hành:** thời gian nạp model; p50/p95 giây/ảnh sau warm-up; peak RAM/VRAM; 1 ảnh/lần với kích thước đầu vào ghi rõ; tỷ lệ lỗi/timeout.
- **So sánh công bằng:** cùng ảnh và cách crop, báo cả chi phí tiền xử lý; Tesseract của bản cũ, v5 Latin, v6 small/tiny và VLM tùy chọn nhận cùng tập kiểm tra. Lưu model revision, runtime, tham số crop/resize và lượng tử hóa.

Mục tiêu demo đề xuất: mọi trường không đọc được có thể chuyển HR kiểm tra; không có hành động cập nhật công tự động từ ảnh; không có kết luận danh tính/đủ ca. Nếu dữ kiện quan trọng bị bịa trong tập kiểm tra, thu hẹp phạm vi hỗ trợ và giữ HR đọc ảnh. Qua tập giả lập chỉ chứng minh được luồng demo; chưa đủ để tuyên bố an toàn/đúng trên bệnh viện thật.

## Bảo mật khi dùng dữ liệu bệnh viện

Self-host cho phép đặt bước suy luận trong hạ tầng do mình kiểm soát; **không phải chứng nhận bảo mật cho cả TallyV**. Các mục dưới đây là thiết kế đề xuất, chưa được triển khai hoặc kiểm định trong đợt research này.

### Ranh giới dữ liệu ghi nhận tại thời điểm khảo sát

Cấu hình local được kiểm tra đang dùng Outlook qua Composio và bật chế độ thử nghiệm. `ComposioClient.graph_json` gọi proxy của Composio; provider lấy cả nội dung email và bytes tệp đính kèm qua đường này. Vì vậy, đổi riêng OCR sang model local vẫn chưa làm toàn bộ luồng dữ liệu thành nội bộ. Cần thẩm định hoặc thay đường nhận thư trước khi dùng dữ liệu thật của bệnh viện. Nguồn code: [client](../app/services/composio_client.py), [provider](../app/services/composio_provider.py), [chọn transport](../app/services/mailbox.py).

`store_bytes` hiện ghi trực tiếp tệp vào storage. UUID và SHA-256 không mã hóa nội dung. Tầng ứng dụng chưa tự mã hóa tệp; research này chưa kiểm tra mã hóa ổ đĩa, quản lý khóa hay backup của máy chủ. Nguồn: [storage.py](../app/services/storage.py). Đây là nhận xét giới hạn từ code, không phải audit bảo mật đầy đủ.

### Điều kiện triển khai đề xuất

- Đặt OCR/VLM trong mạng riêng của bệnh viện hoặc private cloud được bệnh viện phê duyệt. Tách dịch vụ nhận Outlook có Internet khỏi dịch vụ suy luận không được ra Internet; chỉ cho phép luồng cần thiết. Kiểm chứng bằng firewall và quan sát lưu lượng, không chỉ dựa vào lời cam kết của thư viện.
- API model chỉ nhận kết nối từ backend được xác thực; không công khai cổng. Nếu dùng vLLM, không coi riêng `--api-key` là đủ: tài liệu cảnh báo một số endpoint ngoài nhóm được bảo vệ vẫn cần gateway và kiểm soát mạng. [vLLM security](https://docs.vllm.ai/en/latest/usage/security/).
- Tải model/dependency ở môi trường chuẩn bị; khóa phiên bản/commit, kiểm tra giấy phép và chuyển artifact đã kiểm tra sang máy suy luận. Với Transformers, ưu tiên `safetensors`; tránh bật `trust_remote_code` khi không cần, kiểm tra mã nếu bắt buộc dùng. [Transformers security policy](https://github.com/huggingface/transformers/security/policy).
- Mã hóa kết nối và storage/backup; phân quyền HR theo phạm vi, xác thực phù hợp với bệnh viện; quản lý khóa riêng. Quy định thời hạn lưu và xóa cả bản sao/tệp tạm. Chỉ ghi nhật ký truy cập, quyết định và phiên bản model cần thiết, hạn chế ảnh gốc, khuôn mặt, nội dung OCR và giải trình trong log.
- Chỉ gửi vùng ảnh cần xử lý, che người/bệnh nhân không liên quan nếu không làm mất bằng chứng. Không cho model tự gọi SAP, duyệt web hay thực thi lệnh từ chữ trong ảnh. Backend kiểm tra dữ liệu có cấu trúc và HR xem lại kết quả.
- Kiểm thử mất kết nối và chặn egress, lỗi quyền truy cập, dữ liệu xuất hiện trong log, thời hạn xóa và khôi phục backup trước khi cân nhắc dữ liệu thật.

### Cấu hình offline tham khảo, không thay cho cách ly mạng

| Runtime thực sự được chọn | Cấu hình/kiểm tra |
| --- | --- |
| Hugging Face Hub | Tải sẵn artifact; `HF_HUB_OFFLINE=1` ngăn HTTP tới Hub, `HF_HUB_DISABLE_TELEMETRY=1` tắt telemetry của hệ sinh thái HF. Đây không phải firewall cho mọi thư viện. [HF environment variables](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables). |
| Ollama | `OLLAMA_NO_CLOUD=1` tắt chức năng cloud và web search; tải model trước và kiểm tra bind/network. Không chọn model cloud cho luồng này. [Ollama FAQ](https://docs.ollama.com/faq). |
| vLLM | `VLLM_NO_USAGE_STATS=1` tắt thống kê sử dụng; kiểm tra `--disable-log-requests` và không bật log đầu ra/prompt. Kiểm tra cả log proxy, ứng dụng và hệ thống quan sát. [Usage stats](https://docs.vllm.ai/en/latest/usage/usage_stats/), [CLI logging](https://docs.vllm.ai/en/latest/cli/serve/). |

Không cần cài cả ba runtime. Chọn runtime hỗ trợ chính xác checkpoint và phần cứng đã thử. Docker bridge mặc định vẫn cho container đi ra mạng ngoài; đóng gói bằng Docker tự nó không tạo môi trường offline. [Docker bridge networking](https://docs.docker.com/engine/network/drivers/bridge/).

Nếu chọn Ollama trên Mac, lưu ý tài liệu nêu Docker Desktop macOS không hỗ trợ GPU passthrough. Không dùng kết quả chạy native để hứa tốc độ tương tự trong container CPU. [Ollama FAQ](https://docs.ollama.com/faq).

### Đề xuất theo điều kiện demo tại thời điểm khảo sát

Model có thể tải miễn phí không có nghĩa là GPU cloud miễn phí. Với máy yếu và ngân sách bằng 0, ưu tiên thử OCR trên CPU, xử lý từng ảnh; phần hiểu cảnh chỉ chạy khi có tài nguyên phù hợp và cho phép chuyển HR xem lại khi chưa chạy được. Dùng ảnh giả lập trong demo; chưa có hạ tầng riêng được phê duyệt thì chưa dùng ảnh thật của bệnh viện. Đợt research này không tải weights, chạy benchmark hoặc truyền ảnh bằng chứng ra ngoài.

