import io
import zipfile

import pytest
from docx import Document
from openpyxl import load_workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.assistant.demo.generate import files
from app.assistant.errors import InputError
from app.assistant.services import documents


def test_real_xlsx_and_docx_split_runs_preserve_template():
    inputs = files()
    raw, parts = documents.load_template(inputs[0][0], inputs[0][2])
    records = documents.parse_data(inputs[1][0], inputs[1][2])["records"]
    assert len(records) == 8
    assert records[0]["source"] == {"file": "Du_lieu_nhan_vien.xlsx", "sheet": "NhanVien", "row": 2}
    output = documents.render_template(
        raw,
        {
            "ho_ten": "Nguyễn An Nhiên",
            "ma_nv": "NV001",
            "phong_ban": "Vận hành",
            "so_hd": "HD-001",
            "ngay_het_han": "2026-12-05",
        },
    )
    doc = Document(io.BytesIO(output))
    assert doc.paragraphs[1].text == "Kính gửi: Nguyễn An Nhiên"
    assert next(r for r in doc.paragraphs[1].runs if "Nguyễn" in r.text).bold is True
    assert len(doc.tables) == 1 and doc.tables[0].rows[0].cells[1].text == "NV001"
    assert "CÔNG TY MẪU" in doc.sections[0].header.paragraphs[0].text
    assert not documents.slots(documents.paragraphs(output))
    with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(io.BytesIO(output)) as rendered:
        for name in original.namelist():
            if not name.startswith(("word/document.xml", "word/header")):
                assert original.read(name) == rendered.read(name)


def test_edit_insertion_preserves_original_and_rejects_bad_ids():
    content, items = documents.load_template("mau.txt", "Nội dung cũ".encode())
    key = next(p["id"] for p in items if p["text"])
    output = documents.edit_document(content, [{"id": key, "text": "Ghi chú: Nội dung cũ"}])
    assert next(p["text"] for p in documents.paragraphs(output) if p["id"] == key) == "Ghi chú: Nội dung cũ"
    with pytest.raises(InputError):
        documents.edit_document(content, [{"id": "other#1", "text": "x"}])


def test_formula_rejected_and_csv_unicode_columns_supported():
    inputs = files()
    wb = load_workbook(io.BytesIO(inputs[1][2]))
    wb.active["B2"] = '=HYPERLINK("https://example.com")'
    stream = io.BytesIO()
    wb.save(stream)
    with pytest.raises(InputError, match="công thức"):
        documents.parse_data("data.xlsx", stream.getvalue())
    parsed = documents.parse_data("data.csv", 'Họ tên;Đơn vị\n"Nguyễn A";"HR"'.encode())
    content, _ = documents.load_template("mau.txt", "Kính gửi {{Họ tên}}, {{Đơn vị}}".encode())
    result = documents.render_template(content, parsed["records"][0]["values"])
    assert "Kính gửi Nguyễn A, HR" in "\n".join(p["text"] for p in documents.paragraphs(result))


def test_pdf_text_reads_and_scan_requires_ocr():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 250 Td (Name: Alice) Tj 0 -20 Td (Code: NV009) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    result = io.BytesIO()
    writer.write(result)
    parsed = documents.parse_data("data.pdf", result.getvalue())
    assert parsed["records"][0]["values"] == {"Name": "Alice", "Code": "NV009"}
    blank = PdfWriter()
    blank.add_blank_page(width=100, height=100)
    result = io.BytesIO()
    blank.write(result)
    with pytest.raises(InputError, match="scan"):
        documents.parse_data("scan.pdf", result.getvalue())


def test_csv_source_rows_do_not_shift_after_blanks():
    parsed = documents.parse_data("data.csv", b"name,id\nAlice,001\n\nBob,002")
    assert parsed["records"][1]["source"]["row"] == 4


def test_labelled_blank_template_is_filled_without_changing_labels():
    from app.assistant.services.planner import create_plan

    inputs = files(plain_template=True)
    content, items = documents.load_template(inputs[0][0], inputs[0][2])
    records = documents.parse_data(inputs[1][0], inputs[1][2])["records"]
    plan = create_plan("Tạo hồ sơ cho tất cả nhân viên.", items, records)
    assert len(plan.rewrites) == 3 and not plan.question
    values = {field: records[0]["values"][column] for field, column in plan.mapping.items()}
    output = documents.render_template(content, values, [r.model_dump() for r in plan.rewrites])
    text = "\n".join(p["text"] for p in documents.paragraphs(output))
    assert "Kính gửi: Nguyễn An Nhiên" in text
    assert "Mã nhân viên: NV001" in text


def test_narrative_with_colon_is_not_misread_as_a_single_column():
    text = "Nhân viên Nguyễn An Bình có mã NV101, thuộc phòng Vận hành. Email: an.binh@example.com."
    parsed = documents.parse_data("data.txt", text.encode())
    assert parsed["records"] == [] and parsed["text"] == text
    text = "Danh sách nhân viên\n\nHọ tên: Nguyễn A\nMã: NV001"
    parsed = documents.parse_data("data.txt", text.encode())
    assert parsed["records"] == [] and parsed["text"] == text
