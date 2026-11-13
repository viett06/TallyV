# Nguồn ảnh camera để kiểm thử đối chiếu bằng chứng TallyV

> Phạm vi cập nhật 14/11/2026: danh mục nguồn là snapshot khảo sát 12/11/2026, chưa tái xác minh giấy phép hoặc tải media. Luồng tìm góc camera bằng embedding/SIFT đã bị gỡ. CCTV hiện chưa được xử lý PII tự động và phải bị chặn VLM; các nguồn này chỉ còn dùng để nghiên cứu hoặc kiểm tra đường chuyển nhân viên. Xem [phạm vi ảnh hiện tại](evidence-images.md).

Khảo sát nguồn công bố ngày 12/11/2026. Nếu mục tiêu là **chạy thử TallyV nội bộ với giấy phép CC BY 4.0**, bắt đầu bằng **MEVA** để kiểm tra đối chiếu góc camera qua nhiều ngày. **HA4M** bổ sung cảnh người thao tác ở bàn lắp ráp. Nếu mục đích sử dụng thuộc phạm vi **phi thương mại**, **Edinburgh Office Monitoring** sát nhất với yêu cầu ghi người làm việc tại văn phòng.

## Nguồn ưu tiên

| Nguồn | Cảnh quay và cách lấy ảnh | Giấy phép |
| --- | --- | --- |
| **Edinburgh Office Monitoring** | Camera cố định trong 4 văn phòng, ghi hoạt động thường ngày. Có 456.714 ảnh màu 1280 × 720 trong 20 ngày, khoảng 1 khung/giây. Chủ yếu là một người làm việc hoặc phòng trống. Trang công bố có 4 ảnh ví dụ và gói TAR ảnh rời, AVI, nhãn và danh sách tên ảnh theo từng ngày. Gói ngày 2 khoảng 0,7 GB. [University of Edinburgh](https://homepages.inf.ed.ac.uk/rbf/OFFICEDATA/) · [TAR ngày 2](https://homepages.inf.ed.ac.uk/rbf/OFFICEDATA/TAR/day_2.tar) | **CC BY-NC-SA 3.0**. Trang công bố có yêu cầu ghi công khi dùng công khai. [Điều khoản](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| **MEVA KF1** | Camera giám sát nhiều góc trong nhà và ngoài trời tại khu huấn luyện. Có diễn viên tham gia các tình huống có và không có kịch bản. Tải chọn từng AVI từ S3 công khai, trích khung RGB từ camera mặt đất. Có thể bắt đầu bằng camera khu hành chính rồi chọn thêm góc ở khu mô phỏng bệnh viện. Cần xem clip để chọn đoạn có người trong cảnh phù hợp với bài test. [Kitware](https://mevadata.org/) · [Hướng dẫn tải](https://mevadata.org/resources/README-meva-kf1-data.html) | **CC BY 4.0**. Ghi công và ghi rõ phần sửa đổi khi chia sẻ bản trích hoặc bản chỉnh sửa. [Điều khoản](https://creativecommons.org/licenses/by/4.0/) |
| **HA4M** | 217 clip của 41 người lắp bộ truyền bánh răng trong hai phòng thí nghiệm. Camera Azure Kinect đặt trên chân máy trước bàn, có ảnh RGB theo lượt quay trong thư mục `Color`. Chọn các lượt khác nhau của cùng phòng thí nghiệm và dùng phòng còn lại để thử đối chiếu âm. Toàn bộ bộ đa phương thức khoảng 4,1 TB theo bài báo. Ưu tiên một số lượt RGB từ kho của tác giả hoặc Science Data Bank. Chưa kiểm tra tải từng lượt. [Bài mô tả](https://www.nature.com/articles/s41597-022-01843-z) · [Kho CNR](https://baltig.cnr.it/ISP/ha4m) · [Science Data Bank](https://www.scidb.cn/en/detail?dataSetId=c8d743ad2ea549dfa938cea320a38c46) | **CC BY 4.0** theo giấy phép trong kho dữ liệu. [Giấy phép HA4M](https://baltig.cnr.it/ISP/ha4m/-/blob/master/LICENSE) |

Với Edinburgh, lấy hai ảnh mẫu cùng phòng cách nhau 59 phút để chạy thử bước đầu. Khi lấy thêm ảnh, nhóm theo văn phòng và góc đã xác minh vì tiền tố tên tệp mẫu `inspacecam163_` được dùng ở nhiều văn phòng. Văn phòng 1 gồm ngày 1–12, văn phòng 2 gồm ngày 13–14, văn phòng 3 gồm ngày 15–17 và văn phòng 4 gồm ngày 18–20. [Ảnh mẫu 1](https://homepages.inf.ed.ac.uk/rbf/OFFICEDATA/IMAGES/inspacecam163_2016_02_25_15_23_50.jpg) · [Ảnh mẫu 2](https://homepages.inf.ed.ac.uk/rbf/OFFICEDATA/IMAGES/inspacecam163_2016_02_25_16_22_50.jpg) · [Bài báo của tác giả, mục 3](https://www.pure.ed.ac.uk/ws/portalfiles/portal/173678797/Ground_truthing_QASIM_DOA10112020_AFV.pdf)

Ví dụ chọn clip MEVA từ danh sách URL của Kitware. Hai tệp dưới đây có cùng mã camera, cách nhau bốn ngày. Danh sách cũng có `admin.G326` để lấy thêm một góc khu hành chính và `hospital.G341` để thử cảnh khác. Mã camera và thời gian lấy từ tên tệp. Nội dung cụ thể của các clip chưa được kiểm tra. [Danh sách URL Kitware](https://github.com/Kitware/MEVID/blob/main/mevid-v1-video-URLS.txt)

- `2018-03-07.16-50-00.16-55-00.admin.G329.r13.avi`
- `2018-03-11.11-20-00.11-25-00.admin.G329.r13.avi`

## Nguồn theo bối cảnh

| Nguồn | Khi nào nên dùng | Truy cập và giấy phép |
| --- | --- | --- |
| **MVOR** | Ảnh sẵn từ phòng can thiệp thật tại bệnh viện Đại học Strasbourg. Có 732 bộ ảnh đồng bộ, mỗi bộ gồm 3 ảnh màu từ 3 camera và 3 ảnh độ sâu. Mẫu lấy từ 4 ngày, thư mục tách ngày và camera. Hợp để thử góc lặp và nền bị che trong bối cảnh lâm sàng. | Tải ZIP từ máy chủ trường, lấy các thư mục `color`. **CC BY-NC-SA 4.0**. [CAMMA và hướng dẫn tải](https://github.com/CAMMA-public/mvor#download-the-mvor-dataset-and-install-the-dependencies) |
| **MA-SCE** | Nhân viên lâm sàng thực hiện thao tác tại buồng bệnh mô phỏng. Hai camera quay đồng bộ ở góc cao và ngang hông, ảnh màu 1920 × 1080 ở 30 fps, video MKV. Góc cao phù hợp với kịch bản gần CCTV. | King's College London dẫn sang Figshare. Chưa xác minh được giấy phép và quyền tải tệp vì trang Figshare trả 403 khi kiểm tra. [Hồ sơ King's College London](https://kclpure.kcl.ac.uk/portal/en/datasets/motion-analysis-in-simulated-clinical-environments-ma-sce/) |
| **MM-Office** | Bốn GoPro gắn trong một văn phòng, 880 clip mỗi camera, khoảng 30–90 giây/clip. Các cảnh theo kịch bản như vào phòng, ngồi, lấy đồ. Dùng mã cảm biến và mã lần quay để giữ hai nửa cùng lần quay trong một tập, hoặc lấy các góc khác nhau của cùng phòng làm đối chứng. | Zenodo có gói 12,9 GB chia 4 phần. Tác giả dẫn tới `LICENSE.pdf` riêng. Chưa đọc được nội dung PDF để xác nhận quyền sử dụng. [NTT](https://github.com/nttrd-mdlab/mm-office#details-of-dataset) · [Zenodo](https://zenodo.org/records/6088572) |
| **CarDA** | Công nhân dây chuyền mô phỏng quy trình lắp cửa ô tô trên dây chuyền thực nghiệm. Mỗi trạm có hai camera cố định đặt hai bên băng chuyền. Dữ liệu chia hai đợt tại cùng nhà xưởng và có MP4 30 fps. Hợp để thử nền lặp qua các lượt thao tác, kèm cặp đối chứng hai góc của cùng trạm. | Zenodo chia gói theo trạm, gói nhỏ nhất liệt kê là 921,8 MB. Chưa xác nhận được giấy phép tái sử dụng video từ mục quyền của bản ghi. [CarDA v2](https://zenodo.org/records/14644367) |
| **Graviti Ego-Exo Workplace Tasks** | Người lao động làm việc trong nhà máy, khách sạn và khu văn phòng. Ba góc cố định ghi đồng bộ với camera đeo đầu. Cảnh văn phòng chủ yếu được mô tả là dọn dẹp, lễ tân và không gian chung. | Có thể yêu cầu mẫu. Nhà cung cấp cấp phép thương mại theo giờ video. Cần xác nhận điều khoản cho lô cụ thể trước khi dùng. [Graviti](https://www.graviti.com/datasets/ego-exo-workplace/) |

Video từ camera gắn trên đầu như **xPhi-Ego-100** ghi công việc thật, nhưng nền di chuyển theo người đeo. Với nguồn có cả hai loại góc, dùng camera cố định `exo` để kiểm tra đối chiếu nền. [XPhi Robotics](https://huggingface.co/datasets/xphirobotics/xPhi-Ego-100) · [Assembly101](https://assembly-101.github.io/)

## Dùng mẫu với phiên bản hiện tại

1. Giữ manifest URL nguồn, giấy phép tại thời điểm lấy, ID camera/phiên và phần chỉnh sửa của từng ảnh. Quyền truy cập công khai không tự xác nhận quyền gửi ảnh có người cho nhà cung cấp AI.
2. Tách môi trường và hồ sơ thử khỏi dữ liệu nghiệp vụ. Nếu được phép dùng ảnh đã chọn, đính kèm qua luồng nhập hiện có để kiểm tra bố cục chưa hỗ trợ chuyển `MANUAL_REVIEW`. Với cấu hình mặc định rỗng, không ảnh nào được gửi VLM.
3. Kiểm tra trạng thái PII, không có preview gửi model và không có quyền mở chặn. HR xác nhận thủ công cũng không tạo chỉ mục hoặc cấp quyền gửi ảnh gốc. Hiện không có CLI lập chỉ mục, kho tham chiếu camera, cosine hoặc xác minh hình học trong đánh giá.
4. Kiểm thử hai loại tự động `FACEID`/`DEVICE_ERROR` bằng ảnh giả lập theo profile tương ứng. Không gắn profile FaceID cho CCTV chỉ để model nhận được ảnh. Đánh giá đúng/sai nguyên nhân phải dựa trên dữ kiện nghiệp vụ giả lập; nhãn góc camera không chứng minh danh tính hoặc công số.

Có thể dùng `STORAGE_BACKEND=local` hoặc bucket private đã cấu hình cho môi trường thử. Xem [lưu trữ](object-storage.md), [luồng PII/VLM](vlm-evidence.md) và [kiểm thử hiện tại](verification.md). Thao tác đồng bộ tài liệu này không tải media, đưa ảnh vào storage hoặc gọi model.
