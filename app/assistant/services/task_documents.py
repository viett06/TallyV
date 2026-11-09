"""Render verified metrics and datasets into report templates and re-read outputs."""

import copy
import io
import re
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook

from app.assistant.errors import InputError
from app.assistant.services import datasets, documents, tools
from app.core.i18n import message


def inspect_template(item, content):
    result = {"id": item["id"], "name": item["name"], "fields": template_fields(item["name"], content)}
    if not item["name"].lower().endswith(".xlsx"):
        _, paragraphs = documents.load_template(item["name"], content)
        rewrites = []
        for index, paragraph in enumerate(paragraphs, 1):
            blank = re.fullmatch(r"(\s*[^:\n]{1,160}:\s*)([._…]{3,})(\s*)", paragraph["text"])
            if not blank:
                continue
            field = f"report_field_{index}"
            while field in result["fields"]:
                field += "_blank"
            paragraph["text"] = blank[1] + "{{" + field + "}}" + blank[3]
            result["fields"].append(field)
            rewrites.append({"paragraph_id": paragraph["id"], "text": paragraph["text"]})
        result["normalized_rewrites"] = rewrites
        result["paragraphs"] = paragraphs
    return result


def apply_rewrites(content, rewrites):
    archive, parts = documents.docx_parts(content)
    nodes = dict(documents.paragraph_nodes(parts))
    seen = set()
    for rewrite in rewrites:
        if rewrite.paragraph_id not in nodes or rewrite.paragraph_id in seen:
            raise InputError(message("assistant.data.invalid_dependencies"))
        seen.add(rewrite.paragraph_id)
        node = nodes[rewrite.paragraph_id]
        source = documents.paragraph_text(node)
        cursor = 0
        fixed_parts = documents.SLOT.split(rewrite.text)[::2]
        if not documents.SLOT.search(rewrite.text) or (
            source.strip() and not any(part.strip() for part in fixed_parts)
        ):
            raise InputError(message("assistant.data.fixed_wording"))
        for fixed in fixed_parts:
            if fixed:
                position = source.find(fixed, cursor)
                if position < 0:
                    raise InputError(message("assistant.data.fixed_wording"))
                cursor = position + len(fixed)
        if node.find(".//w:drawing", documents.NS) is not None or node.find(".//w:pict", documents.NS) is not None:
            raise InputError(message("assistant.data.fixed_wording"))
        documents.set_text(node, rewrite.text)
    return documents.save_parts(archive, parts)


def template_fields(name, content):
    if Path(name).suffix.lower() != ".xlsx":
        _, paragraphs = documents.load_template(name, content)
        return documents.slots(paragraphs)
    documents.office_archive(content)
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    fields = set()
    try:
        for sheet in book:
            if sheet.max_row > 1000 or sheet.max_column > 80:
                raise InputError(message("assistant.data.template_limit"))
            for row in sheet:
                for cell in row:
                    if cell.data_type == "f":
                        raise InputError(message("assistant.data.template_formulas"))
                    if isinstance(cell.value, str):
                        fields.update(m.group(1).strip() for m in documents.SLOT.finditer(cell.value))
    finally:
        book.close()
    return sorted(fields)


def metric_value(binding, snapshots):
    data = snapshots[binding.dataset]
    tools.require_columns(data, [*binding.where, *([binding.column] if binding.operation != "count_rows" else [])])
    rows = [
        r
        for r in data["rows"]
        if (not binding.row_id or r["id"] == binding.row_id)
        and all(str(r["values"].get(c, "")) == v for c, v in binding.where.items())
    ]
    if binding.operation == "count_rows":
        return len(rows)
    if binding.operation == "sum":
        from decimal import Decimal

        return tools.output_number(sum((tools.number(r["values"].get(binding.column, "")) for r in rows), Decimal(0)))
    if len(rows) != 1:
        raise InputError(message("assistant.data.ambiguous_metric"))
    return rows[0]["values"].get(binding.column, "")


def build_word_table(dataset):
    table = etree.Element(documents.W + "tbl")
    properties = etree.SubElement(table, documents.W + "tblPr")
    borders = etree.SubElement(properties, documents.W + "tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = etree.SubElement(borders, documents.W + side)
        border.set(documents.W + "val", "single")
        border.set(documents.W + "sz", "4")
    grid = etree.SubElement(table, documents.W + "tblGrid")
    for _ in dataset["columns"]:
        etree.SubElement(grid, documents.W + "gridCol")
    values = [dataset["columns"], *[[r["values"].get(c, "") for c in dataset["columns"]] for r in dataset["rows"]]]
    for index, values_row in enumerate(values):
        row = etree.SubElement(table, documents.W + "tr")
        for value in values_row:
            cell = etree.SubElement(row, documents.W + "tc")
            paragraph = etree.SubElement(cell, documents.W + "p")
            run = etree.SubElement(paragraph, documents.W + "r")
            if index == 0:
                etree.SubElement(etree.SubElement(run, documents.W + "rPr"), documents.W + "b")
            etree.SubElement(run, documents.W + "t").text = str(value)
    return table


def render_docx(name, content, scalars, tables):
    content, _ = documents.load_template(name, content)
    archive, parts = documents.docx_parts(content)
    found = set()
    for _, node in list(documents.paragraph_nodes(parts)):
        text = documents.paragraph_text(node).strip()
        match = documents.SLOT.fullmatch(text)
        if match and match.group(1).strip() in tables:
            field = match.group(1).strip()
            parent = node.getparent()
            parent.replace(node, build_word_table(tables[field]))
            # Word cells must end with a paragraph even when they contain a nested table.
            if parent.tag == documents.W + "tc":
                etree.SubElement(parent, documents.W + "p")
            found.add(field)
    if found != set(tables):
        raise InputError(message("assistant.data.table_marker"))
    output = documents.render_template(documents.save_parts(archive, parts), scalars)
    for value in scalars.values():
        if documents.SLOT.search(str(value)):
            raise InputError(message("assistant.data.placeholder_value"))
    return output


def render_xlsx(content, scalars, tables):
    documents.office_archive(content)
    book = load_workbook(io.BytesIO(content), data_only=False, keep_links=False)
    found = set()
    try:
        for sheet in book:
            markers = [
                (cell.row, cell.column, cell.value)
                for row in sheet
                for cell in row
                if isinstance(cell.value, str) and documents.SLOT.search(cell.value)
            ]
            # Bottom-up insertion keeps the positions of earlier template markers stable.
            for row, col, value in sorted(markers, reverse=True):
                match = documents.SLOT.fullmatch(value.strip())
                if match and match.group(1).strip() in tables:
                    key = match.group(1).strip()
                    data = tables[key]
                    if len(data["rows"]) > 1000:
                        raise InputError(message("assistant.data.report_limit"))
                    if any(merged.max_row >= row for merged in sheet.merged_cells.ranges):
                        raise InputError(message("assistant.data.merged_table"))
                    if any(
                        sheet.cell(row, c).value not in (None, "") for c in range(col + 1, col + len(data["columns"]))
                    ):
                        raise InputError(message("assistant.data.table_overlap"))
                    sheet.insert_rows(row + 1, len(data["rows"]))
                    style = copy.copy(sheet.cell(row, col)._style)
                    matrix = [
                        data["columns"],
                        *[[r["values"].get(c, "") for c in data["columns"]] for r in data["rows"]],
                    ]
                    for offset, entries in enumerate(matrix):
                        for c, entry in enumerate(entries, col):
                            datasets.write_cell(sheet, row + offset, c, entry)._style = copy.copy(style)
                    found.add(key)
                else:

                    def replace(match):
                        key = match.group(1).strip()
                        if key not in scalars:
                            raise InputError(message("assistant.data.missing_binding", field=key))
                        return str(scalars[key])

                    replaced = documents.SLOT.sub(replace, value)
                    if (
                        match
                        and match.group(1).strip() in scalars
                        and isinstance(scalars[match.group(1).strip()], (int, float))
                    ):
                        replaced = scalars[match.group(1).strip()]
                    datasets.write_cell(sheet, row, col, replaced)
        if found != set(tables):
            raise InputError(message("assistant.data.table_marker"))
        stream = io.BytesIO()
        book.save(stream)
    finally:
        book.close()
    output = stream.getvalue()
    if template_fields("report.xlsx", output):
        raise InputError(message("assistant.data.remaining_fields"))
    return output


def render_report(item, content, plan, snapshots, source_rows):
    if plan.rewrites:
        if item["name"].lower().endswith(".xlsx"):
            raise InputError(message("assistant.data.xlsx_rewrites"))
        content, _ = documents.load_template(item["name"], content)
        content = apply_rewrites(content, plan.rewrites)
    scalars = {"total_rows": len(snapshots[plan.result]["rows"]), "source_rows": source_rows}
    scalars.update({key: metric_value(binding, snapshots) for key, binding in plan.bindings.items()})
    tables = {key: snapshots[ref] for key, ref in plan.tables.items()}
    fields = template_fields(item["name"], content)
    labels = {}
    if not item["name"].lower().endswith(".xlsx"):
        _, paragraphs = documents.load_template(item["name"], content)
        for paragraph in paragraphs:
            for match in documents.SLOT.finditer(paragraph["text"]):
                label = documents.SLOT.sub("", paragraph["text"]).strip().rstrip(":")
                if label:
                    labels[match.group(1).strip()] = label
    if not fields:
        raise InputError(message("assistant.data.template_fields_required"))
    if "summary_table" in fields and "summary_table" not in tables:
        tables["summary_table"] = snapshots[plan.summary or plan.result]
    required = set(fields) - set(scalars) - set(tables)
    if required:
        raise InputError(message("assistant.data.missing_binding", field=", ".join(sorted(required))))
    if any(len(data["rows"]) > 1000 for data in tables.values()):
        raise InputError(message("assistant.data.report_limit"))
    if Path(item["name"]).suffix.lower() == ".xlsx":
        output = render_xlsx(content, scalars, tables)
        paragraphs = []
        name = "Report.xlsx"
    else:
        output = render_docx(item["name"], content, scalars, tables)
        paragraphs = documents.paragraphs(output)
        name = "Report.docx"
    return (
        output,
        name,
        paragraphs,
        {
            "metrics": scalars,
            "labels": labels,
            "tables": {key: {"rows": len(data["rows"]), "columns": data["columns"]} for key, data in tables.items()},
        },
    )
