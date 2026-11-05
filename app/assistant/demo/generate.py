import io

from docx import Document
from docx.shared import Pt
from openpyxl import Workbook

PROMPT = "Dựa vào dữ liệu, hoàn thiện thông báo tái ký theo mẫu cho nhân viên hết hạn hợp đồng trong tháng 12/2026, đã được duyệt tái ký. Mỗi người một hồ sơ riêng."


def files(missing=False, plain_template=False):
    document = Document()
    document.styles["Normal"].font.name = "Times New Roman"
    document.styles["Normal"].font.size = Pt(12)
    document.sections[0].header.paragraphs[0].text = "CÔNG TY MẪU · DỮ LIỆU GIẢ LẬP"
    document.add_heading("THÔNG BÁO CHUẨN BỊ TÁI KÝ HỢP ĐỒNG", 0)
    if plain_template:
        document.add_paragraph("Kính gửi: [Họ và tên]")
        document.add_paragraph("Mã nhân viên: [Mã nhân viên]")
        document.add_paragraph("Phòng ban: [Phòng ban]")
    else:
        p = document.add_paragraph("Kính gửi: ")
        p.add_run("{{ho_").bold = True
        p.add_run("ten}}").bold = True
        table = document.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        for key, value in [
            ("Mã nhân viên", "{{ma_nv}}"),
            ("Phòng ban", "{{phong_ban}}"),
            ("Số hợp đồng", "{{so_hd}}"),
            ("Ngày hết hạn", "{{ngay_het_han}}"),
        ]:
            cells = table.add_row().cells
            cells[0].text = key
            cells[1].text = value
    document.add_paragraph(
        "Phòng Nhân sự đang chuẩn bị hồ sơ tái ký theo danh sách đã xác nhận. Anh/Chị vui lòng liên hệ HR để kiểm tra thông tin và được hướng dẫn các bước tiếp theo."
    )
    document.add_paragraph("Trân trọng,\nPHÒNG NHÂN SỰ")
    word = io.BytesIO()
    document.save(word)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "NhanVien"
    sheet.append(["Mã nhân viên", "Họ và tên", "Phòng ban", "Số hợp đồng", "Ngày hết hạn", "Email", "Trạng thái"])
    rows = [
        ["NV001", "Nguyễn An Nhiên", "Vận hành", "HD-001", "2026-12-05", "an.nhien@example.com", "Đã duyệt tái ký"],
        [
            "NV002",
            "Trần Minh Khôi",
            "" if missing else "Tài chính",
            "HD-002",
            "2026-12-12",
            "minh.khoi@example.com",
            "Đã duyệt tái ký",
        ],
        ["NV003", "Lê Hải Yến", "Nhân sự", "HD-003", "2026-12-18", "hai.yen@example.com", "Đã duyệt tái ký"],
        ["NV004", "Phạm Gia Huy", "Công nghệ", "HD-004", "2026-12-28", "gia.huy@example.com", "Đã duyệt tái ký"],
        ["NV005", "Vũ Bảo Linh", "Vận hành", "HD-005", "2026-12-31", "bao.linh@example.com", "Đã duyệt tái ký"],
        ["NV006", "Đỗ Tuấn Nam", "Kinh doanh", "HD-006", "2026-11-30", "tuan.nam@example.com", "Đã duyệt tái ký"],
        ["NV007", "Bùi Ngọc Mai", "Tài chính", "HD-007", "2027-01-03", "ngoc.mai@example.com", "Đã duyệt tái ký"],
        ["NV008", "Hồ Đức Anh", "Công nghệ", "HD-008", "2026-12-20", "duc.anh@example.com", "Chờ duyệt tái ký"],
    ]
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    for col in sheet.columns:
        sheet.column_dimensions[col[0].column_letter].width = 25
    excel = io.BytesIO()
    workbook.save(excel)
    return [("Mau_thong_bao.docx", "template", word.getvalue()), ("Du_lieu_nhan_vien.xlsx", "data", excel.getvalue())]
