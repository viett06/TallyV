"""Private, bounded tabular snapshots. Row identities always point back to source cells."""

import csv
import hashlib
import io
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from app.assistant.config import settings
from app.assistant.errors import InputError
from app.assistant.services import documents
from app.assistant.services.storage import read_bytes, store_bytes
from app.core.i18n import message


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def save_snapshot(value):
    content = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    key, checksum = store_bytes(content)
    return {"key": key, "sha256": checksum}


def load_snapshot(reference):
    return json.loads(read_bytes(reference["key"], reference["sha256"]))


def source_datasets(item, content):
    name, attachment_id = item["name"], item["id"]
    suffix = Path(name).suffix.lower()
    tables = []
    if suffix == ".xlsx":
        documents.office_archive(content)
        try:
            book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
            try:
                if len(book.sheetnames) > 30:
                    raise InputError(message("assistant.data.sheet_limit"))
                for sheet in book:
                    if sheet.max_row > settings.max_data_rows + 1 or sheet.max_column > 40:
                        raise InputError(message("assistant.data.row_limit", limit=settings.max_data_rows))
                    rows = []
                    for row in sheet.iter_rows():
                        if any(cell.data_type == "f" for cell in row):
                            raise InputError(message("assistant.data.formulas"))
                        rows.append([cell.value for cell in row])
                    if any(any(value not in (None, "") for value in row) for row in rows):
                        tables.append((sheet.title, rows))
            finally:
                book.close()
        except InputError:
            raise
        except Exception as error:
            raise InputError(message("assistant.data.invalid_workbook")) from error
    elif suffix == ".csv":
        try:
            text = content.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("NUL in CSV")
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            tables.append(("CSV", list(csv.reader(io.StringIO(text), dialect))))
        except (UnicodeDecodeError, csv.Error, ValueError) as error:
            raise InputError(message("assistant.data.invalid_csv")) from error
    else:
        parsed = documents.parse_data(name, content, max_rows=settings.max_data_rows)
        if not parsed["records"]:
            raise InputError(message("assistant.data.tabular_required"))
        columns = list(dict.fromkeys(key for row in parsed["records"] for key in row["values"]))
        tables.append(("Data", [columns] + [[r["values"].get(c, "") for c in columns] for r in parsed["records"]]))
    result = {}
    total = 0
    for sheet, rows in tables:
        records = documents.table_records(rows, name, sheet, settings.max_data_rows)
        total += len(records)
        if total > settings.max_data_rows:
            raise InputError(message("assistant.data.row_limit", limit=settings.max_data_rows))
        dataset_id = f"source:{attachment_id}:{sheet}"
        entries = []
        for record in records:
            source = {**record["source"], "attachment_id": attachment_id, "sha256": item["sha256"]}
            entries.append({"id": digest(source)[:24], "values": record["values"], "lineage": [source]})
        result[dataset_id] = {
            "columns": list(records[0]["values"]),
            "rows": entries,
            "issues": [],
            "checks": [{"kind": "source_rows", "value": len(entries)}],
        }
    if not result:
        raise InputError(message("assistant.data.empty"))
    return result


def profile(dataset_id, dataset):
    columns = dataset["columns"]
    return {
        "id": dataset_id,
        "columns": columns,
        "row_count": len(dataset["rows"]),
        "row_scope": "all_nonblank_rows_including_hidden_rows",
        "samples": [row["values"] for row in dataset["rows"][:3]],
        "distinct": {
            col: list(dict.fromkeys(str(r["values"].get(col, "")) for r in dataset["rows"]))[:25] for col in columns
        },
        "distinct_counts": {col: len({str(r["values"].get(col, "")) for r in dataset["rows"]}) for col in columns},
    }


def write_cell(sheet, row, column, value):
    cell = sheet.cell(row, column, value)
    if isinstance(value, str):
        cell.data_type = "s"
    return cell


def workbook_bytes(named_datasets):
    book = Workbook()
    book.remove(book.active)
    used = set()
    for title, dataset in named_datasets:
        safe = "".join(c if c not in "[]:*?/\\" else "_" for c in title)[:27] or "Data"
        name = safe
        counter = 1
        while name.casefold() in used:
            name = f"{safe}_{counter}"
            counter += 1
        used.add(name.casefold())
        sheet = book.create_sheet(name)
        columns = dataset["columns"]
        for c, label in enumerate(columns, 1):
            cell = write_cell(sheet, 1, c, label)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="196D5A")
        for index, record in enumerate(dataset["rows"], 2):
            for c, col in enumerate(columns, 1):
                write_cell(sheet, index, c, record["values"].get(col, ""))
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for index, col in enumerate(columns, 1):
            width = min(48, max(16, len(str(col)) + 3))
            sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    output = stream.getvalue()
    # Read exported values rather than assuming successful serialization proves correctness.
    check = load_workbook(io.BytesIO(output), read_only=True, data_only=False)
    try:
        for sheet, (_, dataset) in zip(check, named_datasets):
            if sheet.max_row != len(dataset["rows"]) + 1:
                raise InputError(message("assistant.data.export_mismatch"))
            for actual, expected in zip(sheet.iter_rows(min_row=2), dataset["rows"]):
                for cell, column in zip(actual, dataset["columns"]):
                    value = expected["values"].get(column, "")
                    if (cell.value if cell.value is not None else "") != (value if value is not None else ""):
                        raise InputError(message("assistant.data.export_mismatch"))
    finally:
        check.close()
    return output
