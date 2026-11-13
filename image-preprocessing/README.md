# Image preprocessing

Subproject Python độc lập để xử lý PII trên ảnh xuất từ thiết bị FaceID và màn hình lỗi thiết bị có bố cục đã cấu hình. Không phụ thuộc TallyV, FastAPI, SQLAlchemy, queue hoặc model AI.

Công nghệ: Python 3.11+, Pillow để giải mã/chuẩn hóa/xuất ảnh sạch metadata; NumPy để thao tác pixel; OpenCV để tính chỉ số chất lượng; Pydantic để kiểm tra cấu hình vùng. Không sử dụng OCR, Haar, YuNet, deep learning hoặc HTTP.

## Cài đặt và kiểm thử độc lập

```sh
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
```

Trong TallyV, `requirements.txt` đã tham chiếu `./image-preprocessing`; có thể cài dev bằng `venv/bin/python -m pip install -e ./image-preprocessing` từ thư mục gốc.

## Gọi qua code

```python
from pathlib import Path
from tallyv_image_preprocessing import ProfileSet, process, process_async

profiles = ProfileSet.model_validate_json(Path("config/profiles.json").read_bytes())
result = process(Path("input.png").read_bytes(), profiles)

# Trong một async function:
result = await process_async(content, profiles)
if result.status == "READY":
    image_bytes = result.image.content
else:
    # Không gọi AI; yêu cầu nhân viên đánh giá.
    reason = result.reason
```

`process_async` dùng `asyncio.to_thread`, tránh chặn event loop. Package trả kết quả, không tự ghi file hay tạo tác vụ nền. Ứng dụng gọi quyết định lifecycle, storage và giới hạn số tác vụ. TallyV hiện dùng FastAPI `BackgroundTasks` và asyncio, không cần cấu hình queue cho luồng ảnh.

## Cấu hình và CLI

`config/profiles.json` mặc định rỗng: tất cả ảnh chuyển `MANUAL_REVIEW`. `config/layout-spec.example.json` chỉ là tọa độ minh họa, không dùng cho ảnh thật. Mỗi profile phải có kích thước đúng, ít nhất hai anchor giao diện tĩnh không chứa PII, vùng giữ lại, vùng tên/mã cần che, và vùng mặt nếu là `FACEID`.

```sh
image-privacy-profile \
  --reference /duong-dan-noi-bo/reference.png \
  --spec /duong-dan-noi-bo/layout-spec.json \
  --profiles config/profiles.json \
  --preview /duong-dan-noi-bo/preview.png
```

CLI đọc file cục bộ và tạo ảnh xem trước; không gọi AI. Profile mẫu mặc định `enabled=false`. Anchor được lưu dưới dạng pixel tham chiếu trong JSON nên phải chọn phần UI tĩnh không có dữ liệu nhạy cảm. Không đưa ảnh gốc vào repository.

## Bảo đảm và giới hạn

Chỉ hỗ trợ `FACEID` và `DEVICE_ERROR`. Ảnh không khớp hoặc khớp nhiều profile, sai kích thước, hỏng file hay không còn bằng chứng sau che không tạo ảnh được phép gửi AI. Đầu ra bắt đầu từ mảng đen, chỉ chép vùng được giữ lại, rồi che đè vùng PII/mặt. PNG được tạo mới từ pixel, không sao chép metadata nguồn.

Chỉ số độ sáng/Laplacian phục vụ kiểm tra chất lượng, không xác nhận ảnh không có người. Mặt nạ cố định chỉ bao phủ PII nằm đúng vùng đã cấu hình; cần nghiệm thu với ảnh và biến thể thực tế, không cam kết tự động đạt 100%.
