"""Synthetic, deliberately ambiguous workforce records for the data-task demo."""

import io

from docx import Document
from openpyxl import Workbook

from app.core.i18n import message


def files():
    book = Workbook()
    sheet = book.active
    sheet.title = "Staff"
    sheet.append(["Employee ID", "Role", "Year", "Department"])
    for row in [
        ["EMP001", "Cardiology physician", 2024, "Cardiology"],
        ["EMP002", "Pediatric nurse", 2024, "Pediatrics"],
        ["EMP003", "Head of emergency department", 2024, "Emergency"],
        ["EMP001", "Cardiology physician", 2025, "Cardiology"],
        ["EMP001", "Cardiology physician", 2025, "Cardiology"],
        ["EMP004", "Pharmacist", 2025, "Pharmacy"],
        ["EMP005", "Pediatric nurse", 2025, "Pediatrics"],
        ["EMP006", "Cardiology physician", 2026, "Cardiology"],
    ]:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 36
    excel = io.BytesIO()
    book.save(excel)
    document = Document()
    document.add_heading(message("assistant.demo.report_title"), 0)
    document.add_paragraph(message("assistant.demo.report_note"))
    document.add_paragraph(message("assistant.demo.total_rows"))
    document.add_paragraph("{{summary_table}}")
    word = io.BytesIO()
    document.save(word)
    return [("Synthetic_staff.xlsx", "data", excel.getvalue()), ("Report_template.docx", "template", word.getvalue())]
