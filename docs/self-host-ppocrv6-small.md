# Nghiên cứu cũ: tự vận hành PP-OCRv6 small bằng CPU

> Trạng thái ngày 14/11/2026: tài liệu thử nghiệm lịch sử, không còn là phương án tích hợp đánh giá chấm công. Backend đã bỏ client OCR và chỉ dùng [PII → VLM](vlm-evidence.md). Các phiên bản, liên kết và đề xuất bên dưới là snapshot nghiên cứu ngày 01/11/2026, chưa được rà soát lại theo upstream. Mã service độc lập thực tế được mô tả tại [ocr-api.md](ocr-api.md).

Đối chiếu nguồn ngày **01/11/2026**. Hướng dẫn demo riêng, **chưa cài đặt/chạy thử** tổ hợp dưới đây. Chưa sửa OCR hoặc worker của TallyV. Chỉ dùng ảnh giả lập trong bước kiểm chứng.

## 1. Tạo môi trường thử riêng

Ví dụ dùng Python **3.11**, `paddleocr==3.7.0`, `paddlex[ocr-core]==3.7.0`, `paddlepaddle==3.3.0` bản CPU. Đây là tổ hợp đề xuất để kiểm thử, không phải ma trận tương thích đã được chúng tôi chạy xác nhận.

PaddleOCR 3.7.0 khai báo Python 3.11 và phụ thuộc PaddleX từ 3.7.0 đến trước 3.8.0. [Metadata đúng tag](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/pyproject.toml). Tài liệu Paddle hiện hành cho macOS hướng dẫn PaddlePaddle 3.3.0 CPU, Python 3.11 nằm trong danh sách hỗ trợ; yêu cầu Python 64-bit **arm64**, không phải Python Intel chạy qua Rosetta. [Cài Paddle trên macOS](https://www.paddlepaddle.org.cn/documentation/docs/en/install/pip/macos-pip_en.html).

Có khác biệt giữa nguồn: hướng dẫn framework trong tag PaddleOCR 3.7.0 vẫn minh họa PaddlePaddle **3.2.0**; ví dụ này chọn **3.3.0** theo hướng dẫn macOS hiện hành. Cần smoke test tổ hợp trên máy đích trước khi coi là cấu hình chuẩn của TallyV. [Hướng dẫn trong tag 3.7.0](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/docs/version3.x/paddlepaddle_installation.en.md).

Ví dụ dùng thư mục riêng trong Documents để giữ weights và môi trường thử. Cần có Python 3.11 bản arm64 trước khi chạy. Các lệnh dưới đây dành cho người thực hiện sau khi đọc hướng dẫn, chưa được agent chạy:

```bash
mkdir -p ~/Documents/tallyv-ocr-demo
cd ~/Documents/tallyv-ocr-demo
python3.11 -c 'import platform; print(platform.machine(), platform.architecture())'
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install 'paddlepaddle==3.3.0' -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install 'paddleocr==3.7.0' 'paddlex[ocr-core]==3.7.0'
python -m pip check
python -c 'import paddle; print(paddle.__version__); paddle.utils.run_check()'
```

Không cần cài nhóm `[all]` cho OCR thông thường. Inference pretrained và cài công cụ training/export là hai đường khác nhau. [Hướng dẫn cài PaddleOCR 3.7.0](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/docs/version3.x/installation.en.md). Nếu pip báo thiếu wheel, dừng và kiểm tra OS/kiến trúc/Python; không tự thay bằng wheel không rõ nguồn. Với Linux/Windows, chọn hướng dẫn Paddle đúng OS thay cho giả định wheel macOS.

## 2. Chuẩn bị weights khi còn Internet

PaddleX có thể tự tải weights và đặt trong `official_models` dưới cache; `PADDLE_PDX_CACHE_HOME` đổi cache gốc. Nguồn tải mặc định là Hugging Face, có hỗ trợ BOS. [Cache source v3.7.0](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.0/paddlex/utils/cache.py), [model manager v3.7.0](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.0/paddlex/inference/utils/official_models.py), [flags](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.0/paddlex/utils/flags.py).

Tạo file `ocr_demo.py` trong thư mục thử với nội dung sau. Script chuẩn bị tải weights khi dùng `--prepare`; mặc định đọc weights local và xử lý một ảnh local. Đây là ví dụ do chúng tôi biên soạn từ API đã kiểm tra source, **chưa xác nhận bằng thực thi**.

```python
import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".pdx-cache"
os.environ["PADDLE_PDX_CACHE_HOME"] = str(CACHE)
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from paddleocr import PaddleOCR

NAMES = ("PP-OCRv6_small_det", "PP-OCRv6_small_rec")
MODELS = ROOT / "models"
cfg = dict(
    device="cpu",
    engine="paddle_static",
    enable_hpi=False,
    cpu_threads=4,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    text_detection_model_name=NAMES[0],
    text_recognition_model_name=NAMES[1],
)

if sys.argv[1:] == ["--prepare"]:
    ocr = PaddleOCR(**cfg)
    ocr.close()
    MODELS.mkdir(exist_ok=True)
    for name in NAMES:
        shutil.copytree(CACHE / "official_models" / name, MODELS / name)
    print("Prepared local weights:", MODELS)
    raise SystemExit(0)

if len(sys.argv) != 2:
    raise SystemExit("Use: python ocr_demo.py --prepare | /absolute/path/demo.png")

image = Path(sys.argv[1]).expanduser().resolve(strict=True)
for name in NAMES:
    if not (MODELS / name).is_dir():
        raise SystemExit("Missing local weights; run --prepare with Internet first")

ocr = PaddleOCR(
    **cfg,
    text_detection_model_dir=str(MODELS / NAMES[0]),
    text_recognition_model_dir=str(MODELS / NAMES[1]),
)
try:
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    for result in ocr.predict(str(image)):
        result.print()
        result.save_to_json(str(output_dir))
finally:
    ocr.close()
```

Các tên tham số model/đường dẫn và ba cờ tắt tiền xử lý được đối chiếu với [constructor 3.7.0](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/paddleocr/_pipelines/ocr.py). Tham số CPU/engine/threads đối chiếu với [common args](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/paddleocr/_common_args.py); `close()` với [pipeline base](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/paddleocr/_pipelines/base.py). Lưu JSON theo [ví dụ pipeline OCR](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/docs/version3.x/pipeline_usage/OCR.en.md).

Không truyền thêm `lang="vi"` hoặc `ocr_version` vào cấu hình trên: source cho biết chúng bị bỏ qua khi đã chỉ rõ model names/dirs. Không bỏ hai tên `_small_`, vì mặc định có thể chọn medium. Ba module tùy chọn đang tắt để giảm thành phần; sau này bật lại nếu kiểm thử chứng minh cần xoay ảnh/nắn ảnh, đồng thời chuẩn bị thêm weights tương ứng. [Constructor và chọn model](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/paddleocr/_pipelines/ocr.py).

Chạy bước chuẩn bị một lần, với `models/` chưa chứa hai thư mục đích:

```bash
export PADDLE_PDX_MODEL_SOURCE=BOS
python ocr_demo.py --prepare
python -m pip freeze > requirements-resolved.txt
```

Không xóa weights cũ để chạy lại nếu chưa sao lưu; `copytree` sẽ báo lỗi khi thư mục đích đã tồn tại. Có thể dùng thư mục thử mới khi kiểm tra bản model khác. Các archive/cache tải thành công cần được kiểm tra đủ nội dung và lưu license, nguồn tải, phiên bản cùng checksum; pin package không tự pin nội dung weights tải từ xa.

## 3. Chạy local và xác minh không cần mạng

Đặt một ảnh tự tạo có chữ/ngày giờ giả trong thư mục thử, rồi chạy, thay bằng đường dẫn thật của ảnh mẫu:

```bash
python ocr_demo.py /absolute/path/to/synthetic-demo.png
```

Sau khi một lần chạy thành công, tắt kết nối mạng của môi trường thử rồi chạy lại cùng lệnh. Kết quả mong muốn là vẫn có JSON/chữ từ ảnh, không cần tải thêm. Nếu thiếu model thì sửa gói weights trong giai đoạn chuẩn bị; không bật Internet với dữ liệu thật để “cho chạy được”.

`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` **chỉ bỏ bước kiểm tra kết nối model hoster**. Model manager vẫn có đường tải/fallback nếu cần; đây không phải nút tắt Internet. [Code model manager](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.0/paddlex/inference/utils/official_models.py). Vì vậy offline có chủ đích cần cả local model dirs, ảnh local, dependencies đã chuẩn bị và **deny egress ở tầng mạng**; kiểm tra log kết nối của môi trường thay vì chỉ thấy không có thông báo download.

Tắt Wi-Fi là phép thử demo đơn giản. Môi trường dùng dữ liệu bệnh viện cần cô lập mạng do đơn vị vận hành quản lý; giữ quyền đọc weights, chỉ cho ghi output/cache cần thiết, không công khai cổng suy luận. Script này chưa thực hiện các cấu hình hạ tầng đó. JSON và terminal log có thể chứa chữ nhạy cảm; ảnh giả là lựa chọn cho giai đoạn thử.

## 4. Trạng thái tích hợp hiện tại

Phương án nối OCR trực tiếp vào ảnh bằng chứng đã được bỏ. Không thêm OCR vào bước tiền xử lý và không gửi ảnh gốc cho model để tìm PII. Package [image-preprocessing](../image-preprocessing/README.md) che theo bố cục cố định, không dùng AI; ảnh chưa hỗ trợ chuyển cho nhân viên.

Service PP-OCR còn trong repo chỉ là công cụ thử riêng. Cấu hình, hợp đồng và giới hạn hiện có nằm tại [ocr-api.md](ocr-api.md). Phần fine-tune dưới đây là kiến thức nghiên cứu lịch sử, không phải kế hoạch đang triển khai.

## Có cần fine-tune hoặc tự train không?

**Đề xuất ở thời điểm nghiên cứu: dùng pretrained model trước, chưa fine-tune và chưa train từ đầu.** Đây là quyết định theo phạm vi ba tuần/ngân sách, không phải khẳng định model có sẵn sẽ đạt yêu cầu trên mọi ảnh bệnh viện.

- **Inference/self-host:** tải weights có sẵn, đưa ảnh mới vào, nhận vùng chữ và nội dung đọc được. Việc xử lý thêm ảnh không tự cập nhật weights; không cần huấn luyện lại cho từng ảnh.
- **Fine-tune:** tiếp tục huấn luyện weights có sẵn bằng dữ liệu đã gán nhãn của bài toán riêng.
- **Train từ đầu:** học weights mới thay vì dùng pretrained; cần tự xây dựng tập dữ liệu và quy trình huấn luyện/đánh giá lớn hơn. Chưa có nhu cầu được chứng minh cho TallyV.

Tách rõ hai thành phần OCR: **detector tìm vùng chữ**, **recognizer đọc vùng chữ**. Các tài liệu module mô tả riêng hai vai trò này. [Text detection](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/module_usage/text_detection.en.md), [text recognition](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/module_usage/text_recognition.en.md).

| Kết quả khi thử | Hướng xử lý đề xuất |
| --- | --- |
| Chữ đọc đúng nhưng TallyV không lấy được ngày/mã/lỗi | Sửa bước trích xuất/chuẩn hóa có kiểm soát; không cần fine-tune OCR. Không ép mã/ngày thành giá trị đang có trong Excel. |
| Timestamp rất bé, ảnh nghiêng hoặc vùng màn hình có nhiều nền | Thử crop vùng chữ, xoay đúng chiều và điều chỉnh độ phân giải/ngưỡng; đo lại trước khi chọn huấn luyện. |
| Bỏ sót vùng chữ có thể đọc được bằng mắt | Kiểm tra cấu hình detector; nếu vẫn lỗi lặp lại, cân nhắc fine-tune detector. |
| Vùng chữ đã được bắt đúng nhưng đọc sai font màn hình, dấu tiếng Việt hoặc ký tự đặc thù lặp lại | Cân nhắc fine-tune recognizer với crop chữ và bản chép chính xác. |
| Muốn hiểu người tại bàn làm việc hoặc tình trạng của thiết bị từ hình dạng/cảnh | Thêm VLM hoặc model phân tích ảnh riêng. Fine-tune một bộ đọc chữ không tự giải quyết bài toán hiểu cảnh này. |
| Ảnh bị lóa/mờ đến mức không nhìn được nội dung | Ghi nhận không đọc được, yêu cầu nguồn khác hoặc HR kiểm tra; không xem fine-tune là cách khôi phục chắc chắn chữ đã mất. |

PaddleOCR khuyên phân tích module gây lỗi rồi fine-tune đúng module, và cho phép nạp weights riêng sau huấn luyện qua model directory. Hướng dẫn fine-tune cũ có các con số dữ liệu tham khảo cho model đời trước; **không lấy chúng làm số lượng tối thiểu bảo đảm cho v6 hoặc bài toán bệnh viện**. [Custom development của pipeline](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html#4-custom-development), [hướng dẫn fine-tune đời trước](https://www.paddleocr.ai/v2.10.0/en/ppocr/model_train/finetune.html).

### Nếu sau này kết quả đo cho thấy cần fine-tune

1. Lưu nhóm lỗi có hệ thống và loại lỗi; chưa dùng dữ liệu thật khi chưa có quy trình được bệnh viện phê duyệt.
2. Gán nhãn đúng nhiệm vụ: detector cần vị trí vùng chữ trên ảnh; recognizer cần ảnh crop dòng chữ và chuỗi chữ đúng. Ví dụ một crop hiển thị `31/10/2026 08:02` phải được chép đúng như ảnh.
3. Chia train/validation/test theo ảnh gốc, thiết bị hoặc thời điểm; không để các bản crop/làm mờ của cùng một ảnh tràn sang tập test. Giữ riêng tập test để so sánh với pretrained.
4. Dùng training checkpoint và config **đúng v6 small**, không dùng thư mục inference thay cho checkpoint huấn luyện. Repo có [config detector](https://github.com/PaddlePaddle/PaddleOCR/blob/main/configs/det/PP-OCRv6/PP-OCRv6_small_det.yml) và [config recognizer](https://github.com/PaddlePaddle/PaddleOCR/blob/main/configs/rec/PP-OCRv6/PP-OCRv6_small_rec.yml). Config mẫu chưa điền pretrained checkpoint; phải cấu hình rõ để thực sự fine-tune. Giữ dictionary phù hợp, kiểm tra giới hạn độ dài nhãn, batch và tài nguyên trước khi chạy.
5. Đánh giá riêng tỷ lệ đúng toàn chuỗi timestamp/mã, lỗi ký tự tiếng Việt, mức bỏ sót và tốc độ/RAM. Chỉ thay model nếu tốt hơn trên test chưa dùng để chỉnh model và không làm giảm các trường quan trọng.
6. Export model đã huấn luyện sang định dạng inference, khóa phiên bản và nạp qua local directory; giữ pretrained để rollback.

Huấn luyện tốn tài nguyên hơn chạy suy luận; config v6 chính thức mặc định dùng GPU. Không cần đưa việc thuê GPU hoặc tự xây model vào phạm vi demo hiện tại. Đây là lộ trình đề xuất; chưa chuẩn bị dataset, fine-tune hoặc chạy benchmark trong phiên này.

