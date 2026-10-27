"""A report document as PDF, Excel (.xlsx) or CSV, with the same content in each.

Excel: a "Report" sheet with the text (title, details, sections, bullet points) that names
the sheet holding each table, then one sheet per table and per chart's values, and a
References sheet. CSV: the same in one file, section by section, text cells protected
against spreadsheet formulas, numbers as numbers, missing values as empty cells.
"""

from __future__ import annotations

import csv
import io
import re

from app.services.documents import fonts, pdf
from app.services.documents.model import ChartBlock, Document, TableBlock
from app.services.documents.xlsx import Number, Sheet, workbook
from app.services.exports import safe_cell

_PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")

WORDS = {
    "en": {"report": "Report", "table": "Table", "chart": "Chart values", "see": "see sheet",
           "references": "References", "no": "No.", "title": "Title", "publisher": "Publisher",
           "published": "Published", "retrieved": "Retrieved", "url": "Address", "note": "Note"},
    "ar": {"report": "التقرير", "table": "جدول", "chart": "قيم الرسم", "see": "انظر الورقة",
           "references": "المراجع", "no": "رقم", "title": "العنوان", "publisher": "الناشر",
           "published": "تاريخ النشر", "retrieved": "تاريخ الاسترجاع", "url": "الرابط", "note": "ملاحظة"},
}  # fmt: skip


def _table_rows(
    block: TableBlock | ChartBlock, language: str
) -> tuple[list[str], list[bool], list[list[str | None]]]:
    """Header labels, which columns are numbers, and the rows of a table or a chart's table."""
    if isinstance(block, TableBlock):
        return [c.label for c in block.columns], [c.numeric for c in block.columns], block.rows
    columns = block.table.columns
    labels = []
    for c in columns:
        unit = f" ({c.unit.label_ar if language == 'ar' else c.unit.label_en})" if c.unit else ""
        labels.append(c.label.ar + unit if language == "ar" else c.label.en + unit)
    numeric = [c.kind == "number" for c in columns]
    rows = [[row.get(c.key) for c in columns] for row in block.table.rows]
    return labels, numeric, rows


def to_pdf(document: Document) -> bytes:
    return pdf.render(document, fonts.report_font())


def to_xlsx(document: Document, first: list[Sheet] | None = None) -> bytes:
    """The workbook; ``first`` sheets (such as a dataset's own rows) come before the report."""
    language = document.language
    w = WORDS[language]
    report = Sheet(w["report"])
    report.add([document.title], "title")
    if document.subtitle:
        report.add([document.subtitle], "note")
    for label, value in document.meta:
        report.add([label, value])
    sheets: list[Sheet] = []
    for section in document.sections:
        report.add([])
        report.add([section.heading], "header")
        for block in section.blocks:
            if block.type == "paragraph":
                report.add([block.text], "note" if block.note else "wrap")
            elif block.type == "bullets":
                for item in block.items:
                    report.add([f"• {item}"], "wrap")
            else:
                title = block.title or section.heading
                name = f"{len(sheets) + 1} {title}"
                kind = w["table"] if block.type == "table" else w["chart"]
                report.add([f"{kind}: {title} ({w['see']} {name[:31]})"])
                labels, numeric, rows = _table_rows(block, language)
                sheet = Sheet(name, freeze=2)
                sheet.add([title], "title")
                sheet.add(labels, "header")
                for row in rows:
                    sheet.add([Number(v) if n and v is not None and _PLAIN_NUMBER.match(v) else v
                               for v, n in zip(row, numeric, strict=True)])  # fmt: skip
                if block.note:
                    sheet.add([])
                    sheet.add([block.note], "note")
                sheets.append(sheet)
    if document.notice:
        report.add([])
        report.add([document.notice], "note")
    out = [*(first or []), report, *sheets]
    if document.references:
        refs = Sheet(w["references"], freeze=1)
        refs.add(
            [
                w["no"],
                w["title"],
                w["publisher"],
                w["published"],
                w["retrieved"],
                w["url"],
                w["note"],
            ],
            "header",
        )
        for n, r in enumerate(document.references, start=1):
            refs.add(
                [Number(str(n)), r.title, r.publisher, r.published, r.retrieved, r.url, r.note]
            )
        out.append(refs)
    return workbook(out, title=document.title, rtl=language == "ar")


def to_csv(document: Document) -> str:
    language = document.language
    w = WORDS[language]
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def text(value: str | None) -> str:
        return "" if value is None else safe_cell(value)

    writer.writerow([text(document.title)])
    if document.subtitle:
        writer.writerow([text(document.subtitle)])
    for label, value in document.meta:
        writer.writerow([text(label), text(value)])
    for section in document.sections:
        writer.writerow([])
        writer.writerow([text(f"## {section.heading}")])
        for block in section.blocks:
            if block.type == "paragraph":
                writer.writerow([text(block.text)])
            elif block.type == "bullets":
                for item in block.items:
                    writer.writerow([text(f"• {item}")])
            else:
                labels, numeric, rows = _table_rows(block, language)
                writer.writerow([])
                if block.title:
                    writer.writerow([text(block.title)])
                writer.writerow([text(label) for label in labels])
                for row in rows:
                    writer.writerow([
                        ("" if v is None else v) if n and (v is None or _PLAIN_NUMBER.match(v)) else text(v)
                        for v, n in zip(row, numeric, strict=True)
                    ])  # fmt: skip
                if block.note:
                    writer.writerow([text(block.note)])
    if document.references:
        writer.writerow([])
        writer.writerow([text(f"## {w['references']}")])
        writer.writerow(
            [w["no"], w["title"], w["publisher"], w["published"], w["retrieved"], w["url"]]
        )
        for n, r in enumerate(document.references, start=1):
            writer.writerow(
                [
                    n,
                    text(r.title),
                    text(r.publisher),
                    text(r.published),
                    text(r.retrieved),
                    text(r.url),
                ]
            )
    if document.notice:
        writer.writerow([])
        writer.writerow([text(document.notice)])
    # A byte-order mark first, so spreadsheet programs read Arabic text as UTF-8.
    return "﻿" + buffer.getvalue()
