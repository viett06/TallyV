"""Byte-only document parsing/rendering. No ORM, HTTP or model calls."""

import csv
import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

from docx import Document
from lxml import etree
from openpyxl import load_workbook
from pypdf import PdfReader

from app.assistant.errors import InputError

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
SLOT = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
MAX_TEXT = 50000


def office_archive(content):
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        infos = archive.infolist()
        if len(infos) > 3000 or sum(i.file_size for i in infos) > 60 * 1024 * 1024:
            raise InputError("File Office vượt giới hạn giải nén 60 MB / 3000 phần.")
        if any(i.flag_bits & 1 for i in infos):
            raise InputError("Chưa hỗ trợ file Office có mật khẩu.")
        for info in infos:
            if info.filename.lower().endswith("vbaproject.bin"):
                raise InputError("Không xử lý macro trong MVP.")
            if info.filename.endswith(".rels"):
                root = etree.fromstring(
                    archive.read(info), parser=etree.XMLParser(resolve_entities=False, no_network=True)
                )
                if any(x.get("TargetMode") == "External" for x in root):
                    raise InputError("File Office có liên kết ngoài. Hãy lưu bản không chứa liên kết ngoài.")
        return archive
    except (zipfile.BadZipFile, etree.XMLSyntaxError) as error:
        raise InputError("File Office không hợp lệ hoặc sai định dạng.") from error


def docx_parts(content):
    archive = office_archive(content)
    if "word/document.xml" not in archive.namelist():
        raise InputError("Đây không phải tài liệu DOCX hợp lệ.")
    parts = {}
    for name in archive.namelist():
        if name == "word/document.xml" or re.fullmatch(r"word/(header|footer)\d+\.xml", name):
            parts[name] = etree.fromstring(
                archive.read(name), parser=etree.XMLParser(resolve_entities=False, no_network=True)
            )
    return archive, parts


def paragraph_nodes(parts):
    for name, root in parts.items():
        for index, paragraph in enumerate(root.findall(".//w:p", NS)):
            yield f"{name}#{index}", paragraph


def paragraph_text(node):
    return "".join(node.xpath(".//w:t/text()", namespaces=NS))


def paragraphs(content):
    _, parts = docx_parts(content)
    result = []
    for key, node in paragraph_nodes(parts):
        text = paragraph_text(node)
        style = node.find("w:pPr/w:pStyle", NS)
        result.append(
            {
                "id": key,
                "text": text,
                "style": style.get(W + "val", "") if style is not None else "",
                "location": "header" if "header" in key else "footer" if "footer" in key else "body",
            }
        )
    if len(result) > 500:
        raise InputError("Mẫu có quá nhiều đoạn. MVP hỗ trợ tối đa 500 đoạn.")
    if sum(len(p["text"]) for p in result) > MAX_TEXT:
        raise InputError("Nội dung DOCX vượt giới hạn 50.000 ký tự.")
    return result


def load_template(name, content):
    suffix = Path(name).suffix.lower()
    if suffix == ".txt":
        text = decode_text(content)
        doc = Document()
        for line in text.splitlines():
            doc.add_paragraph(line)
        stream = io.BytesIO()
        doc.save(stream)
        content = stream.getvalue()
    elif suffix != ".docx":
        raise InputError("File mẫu hiện hỗ trợ DOCX hoặc TXT. PDF hiện dùng làm dữ liệu, chưa làm mẫu đầu ra.")
    return content, paragraphs(content)


def slots(items):
    return sorted({m.group(1).strip() for p in items for m in SLOT.finditer(p["text"])})


def replace_range(paragraph, start, end, value):
    nodes = list(paragraph.findall(".//w:t", NS))
    if start == end:
        offset = 0
        for node in nodes:
            text = node.text or ""
            if offset <= start <= offset + len(text):
                position = start - offset
                node.text = text[:position] + value + text[position:]
                node.set(XML_SPACE, "preserve")
                return
            offset += len(text)
        return
    offset = 0
    first, last = None, None
    for index, node in enumerate(nodes):
        length = len(node.text or "")
        if first is None and offset <= start < offset + length:
            first = (index, start - offset)
        if offset < end <= offset + length:
            last = (index, end - offset)
            break
        offset += length
    if first is None or last is None:
        return
    a, x = first
    b, y = last
    prefix = (nodes[a].text or "")[:x]
    suffix = (nodes[b].text or "")[y:]
    nodes[a].text = prefix + value + (suffix if a == b else "")
    nodes[a].set(XML_SPACE, "preserve")
    for index in range(a + 1, b):
        nodes[index].text = ""
    if b != a:
        nodes[b].text = suffix
        nodes[b].set(XML_SPACE, "preserve")


def set_text(paragraph, text):
    original = paragraph_text(paragraph)
    if original:
        # Preserve run properties outside the smallest changed span.
        prefix = 0
        while prefix < min(len(original), len(text)) and original[prefix] == text[prefix]:
            prefix += 1
        suffix = 0
        while suffix < min(len(original) - prefix, len(text) - prefix) and original[-suffix - 1] == text[-suffix - 1]:
            suffix += 1
        if prefix == len(original) and prefix == len(text):
            return
        if prefix == len(original):
            nodes = paragraph.findall(".//w:t", NS)
            nodes[-1].text = (nodes[-1].text or "") + text[prefix:]
            nodes[-1].set(XML_SPACE, "preserve")
        else:
            replace_range(
                paragraph, prefix, len(original) - suffix, text[prefix : len(text) - suffix if suffix else None]
            )
    else:
        run = etree.SubElement(paragraph, W + "r")
        node = etree.SubElement(run, W + "t")
        node.text = text
        node.set(XML_SPACE, "preserve")


def save_parts(archive, parts):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for info in archive.infolist():
            content = (
                etree.tostring(parts[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True)
                if info.filename in parts
                else archive.read(info)
            )
            output.writestr(info, content)
    return stream.getvalue()


def render_template(content, context, rewrites=()):
    archive, parts = docx_parts(content)
    rewrite_map = {r["paragraph_id"]: r["text"] for r in rewrites}
    found = set()
    for key, paragraph in paragraph_nodes(parts):
        if key in rewrite_map:
            set_text(paragraph, rewrite_map[key])
            found.add(key)
        text = paragraph_text(paragraph)
        for match in reversed(list(SLOT.finditer(text))):
            field = match.group(1).strip()
            if field not in context or not str(context[field]).strip():
                raise InputError(f"Chưa có dữ liệu đã xác nhận cho trường {field}.")
            replace_range(paragraph, match.start(), match.end(), str(context[field]))
    if found != set(rewrite_map):
        raise InputError("Vị trí điền mẫu không còn hợp lệ. Hãy tạo lại kế hoạch.")
    result = save_parts(archive, parts)
    if slots(paragraphs(result)):
        raise InputError("Hồ sơ còn trường chưa được điền.")
    return result


def edit_document(content, edits):
    archive, parts = docx_parts(content)
    nodes = dict(paragraph_nodes(parts))
    for edit in edits:
        if edit["id"] not in nodes:
            raise InputError("Đoạn tài liệu không hợp lệ.")
        if SLOT.search(edit["text"]):
            raise InputError("Không để placeholder chưa điền trong hồ sơ.")
        set_text(nodes[edit["id"]], edit["text"])
    return save_parts(archive, parts)


def decode_text(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputError("File văn bản cần được lưu dưới dạng UTF-8.") from error
    if "\x00" in text or len(text) > MAX_TEXT:
        raise InputError("File văn bản không hợp lệ hoặc vượt 50.000 ký tự.")
    return text


def cell_value(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value).strip()


def table_records(rows, name, sheet, max_rows):
    rows = [(index, list(r)) for index, r in enumerate(rows) if any(v not in ("", None) for v in r)]
    if len(rows) < 2:
        raise InputError("Bảng cần dòng tiêu đề và ít nhất một dòng dữ liệu.")
    headers = [cell_value(x) for x in rows[0][1]]
    while headers and not headers[-1]:
        headers.pop()
    if not headers or len(headers) > 40 or len(set(headers)) != len(headers) or any(not x for x in headers):
        raise InputError("Tiêu đề bảng phải đầy đủ, duy nhất và tối đa 40 cột.")
    if len(rows) - 1 > max_rows:
        raise InputError(f"MVP hỗ trợ tối đa {max_rows} bản ghi, không tự cắt bớt dữ liệu.")
    if any(any(cell_value(value) for value in row[len(headers) :]) for _, row in rows[1:]):
        raise InputError("Có dữ liệu nằm ngoài các cột tiêu đề. Hãy kiểm tra lại cấu trúc bảng.")
    return [
        {
            "values": {k: cell_value(row[i]) if i < len(row) else "" for i, k in enumerate(headers)},
            "source": {"file": name, "sheet": sheet, "row": index + 1},
        }
        for index, row in rows[1:]
    ]


def parse_data(name, content, max_rows=200):
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        text = decode_text(content)
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            rows = list(csv.reader(io.StringIO(text), dialect))
        except csv.Error as error:
            raise InputError("CSV không đúng cấu trúc bảng.") from error
        if any(len(row) > 40 for row in rows):
            raise InputError("CSV vượt 40 cột.")
        return {"records": table_records(rows, name, "CSV", max_rows), "text": ""}
    if suffix == ".xlsx":
        office_archive(content)
        try:
            workbook = load_workbook(io.BytesIO(content), data_only=False, read_only=True, keep_links=False)
            records = []
            for sheet in workbook:
                if sheet.max_row > max_rows + 1 or sheet.max_column > 40:
                    raise InputError("Excel vượt giới hạn 200 dòng / 40 cột trên mỗi sheet.")
                rows = []
                for row in sheet.iter_rows():
                    if any(cell.data_type == "f" for cell in row):
                        raise InputError("Excel có công thức. Hãy cung cấp bản chỉ chứa giá trị đã xác nhận.")
                    rows.append([cell.value for cell in row])
                if any(any(v is not None for v in row) for row in rows):
                    records.extend(table_records(rows, name, sheet.title, max_rows))
            workbook.close()
            if len(records) > max_rows:
                raise InputError("Tổng số bản ghi trong Excel vượt 200.")
            return {"records": records, "text": ""}
        except InputError:
            raise
        except Exception as error:
            raise InputError("Không đọc được workbook XLSX.") from error
    if suffix == ".docx":
        items = paragraphs(content)
        document = Document(io.BytesIO(content))
        records = []
        for index, table in enumerate(document.tables):
            if len(table.rows) > 1:
                records.extend(
                    table_records(
                        [[c.text for c in row.cells] for row in table.rows], name, f"Bảng {index + 1}", max_rows
                    )
                )
        if records:
            if len(records) > max_rows:
                raise InputError("Tài liệu Word vượt 200 bản ghi.")
            return {"records": records, "text": ""}
        text = "\n".join(p["text"] for p in items)
    elif suffix == ".pdf":
        try:
            pdf = PdfReader(io.BytesIO(content))
            if pdf.is_encrypted:
                raise InputError("Chưa hỗ trợ PDF có mật khẩu.")
            if len(pdf.pages) > 20:
                raise InputError("MVP hỗ trợ PDF tối đa 20 trang.")
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except InputError:
            raise
        except Exception as error:
            raise InputError("Không đọc được PDF.") from error
        if not text.strip():
            raise InputError("PDF không có lớp text hoặc là bản scan. MVP chưa tích hợp OCR tài liệu.")
    elif suffix == ".txt":
        text = decode_text(content)
    else:
        raise InputError(
            "Dữ liệu hỗ trợ XLSX, CSV, DOCX, PDF có text hoặc TXT. Hãy chuyển DOC/XLS cũ sang định dạng mới."
        )
    if not text.strip() or len(text) > MAX_TEXT:
        raise InputError("Tài liệu trống hoặc vượt 50.000 ký tự.")
    records = []
    unstructured = False
    for index, block in enumerate(re.split(r"\n\s*\n", text)):
        values = {}
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines and all(re.fullmatch(r"[^:,;.?!\n]{1,60}:.*", line) for line in lines):
            for line in lines:
                key, value = line.split(":", 1)
                if key.strip():
                    values[key.strip()] = value.strip()
            if values:
                records.append({"values": values, "source": {"file": name, "section": index + 1}})
        elif lines:
            unstructured = True
    if unstructured:
        # A sentence containing "Email:" is not a structured one-column record.
        # Keep all source text rather than discarding narrative portions around key/value blocks.
        records = []
    if len(records) > max_rows:
        raise InputError("Tài liệu vượt giới hạn 200 bản ghi.")
    return {"records": records, "text": text if not records else ""}
