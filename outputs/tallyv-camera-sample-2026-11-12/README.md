# Bộ ảnh camera mẫu cho TallyV

Bộ ảnh gồm 17 tệp từ 5 góc tham chiếu và một góc chưa có trong kho. HA4M và HARMA cung cấp cảnh người tại bàn lắp ráp trong môi trường thực nghiệm. MEVA cung cấp cảnh cầu thang, chiếu nghỉ và ngoại cảnh từ khu huấn luyện, gồm khung hình có người đi qua và khung hình trống.

| Thư mục | Số ảnh | Cách dùng |
| --- | ---: | --- |
| `references/` | 5 | Tạo hồ sơ mẫu, đính kèm ảnh, xác nhận HR và chờ lập chỉ mục. |
| `queries/` | 9 | Tạo hồ sơ khác cùng nguồn dữ liệu. Trong đó 8 ảnh có góc đã lập chỉ mục và 1 ảnh có góc mới. |
| `reuse/` | 3 | Kiểm tra một bản trùng byte và hai khung hình rất gần với ảnh tham chiếu tương ứng. |

`manifest.csv` ghi URL gốc, mã góc, mốc khung hình, giấy phép, thay đổi khi trích xuất, SHA-256 và trạng thái đối chiếu dự kiến. `verification.csv` ghi trạng thái đo được qua luồng đối chiếu ảnh trong môi trường test cô lập dùng SQLite, storage local và checkpoint MobileNetV2-12. OCR và vision tắt trong lần xác minh này.

## Nạp và thử trên TallyV

1. Trong môi trường test, cấu hình `EVIDENCE_HISTORY_ENABLED=true` và đường dẫn checkpoint `EVIDENCE_HISTORY_MODEL_PATH` cho worker. Có thể chọn `STORAGE_BACKEND=local`.
2. Đính kèm từng ảnh `references/` vào hồ sơ test rồi xác nhận HR. Chờ worker lập chỉ mục. Các ảnh truy vấn cần ở hồ sơ khác và cùng nguồn dữ liệu với ảnh tham chiếu.
3. Phân tích hồ sơ truy vấn. Góc khớp mạnh dự kiến có trạng thái `KNOWN_VIEW_UNLOCATED` khi nhóm chưa gắn nhãn địa điểm. Các ảnh trong `reuse/` kiểm tra nhánh phát hiện ảnh tái sử dụng.
4. Dùng ngày công, ca, lượt quét, giải trình và đáp án giả lập của TallyV để chấm phân loại công số. Các mã góc và mốc khung hình trong bộ mẫu mô tả nguồn ảnh. Ảnh demo HA4M và HARMA chỉ trải vài giây của mỗi lượt quay.

[Checkpoint MobileNetV2-12](https://github.com/onnx/models/blob/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx) là mô hình worker dùng để tạo embedding. Xem thêm `docs/evidence-history.md` trong repo TallyV để cấu hình worker và kiểm tra tác vụ lập chỉ mục.

## Nguồn ảnh và ghi công

Tất cả ảnh dùng [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Giữ thông tin ghi công, nguồn, giấy phép và ghi chú sửa đổi khi chia sẻ ảnh.

- **HA4M** do nhóm tác giả Grazia Cicirelli, Roberto Marani, Laura Romeo, Manuel García Domínguez, Jónathan Heras, Anna G. Perri và Tiziana D’Orazio công bố. Các tệp PNG từ thư mục demo được sao chép và đổi tên. [Bài báo và danh sách tác giả](https://doi.org/10.1038/s41597-022-01843-z) · [Kho ISP/CNR](https://baltig.cnr.it/ISP/ha4m) · [Giấy phép](https://baltig.cnr.it/ISP/ha4m/-/blob/master/LICENSE)
- **HARMA** do nhóm ISP/CNR công bố. Các tệp PNG từ thư mục demo được sao chép và đổi tên. [Kho ISP/CNR](https://baltig.cnr.it/ISP/harma) · [Giấy phép](https://baltig.cnr.it/ISP/harma/-/blob/main/LICENSE)
- **MEVA KF1** do Kitware, Inc. và Intelligence Advanced Research Projects Activity (IARPA) công bố. Khung hình được trích từ AVI, chuyển thành JPEG, đổi tên và chỉnh về chiều rộng 1280 px nếu cần. [Dataset](https://mevadata.org/) · [Giấy phép](https://mevadata.org/resources/MEVA-data-license.txt)
