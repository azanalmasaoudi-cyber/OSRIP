"""Excel workbooks (.xlsx) written directly (standard library only).

Each sheet is a grid of cells: text is written as inline strings, which a spreadsheet never
runs as a formula; a number is written as a number only when its text is a plain decimal,
so it is exactly the value in the report (a missing value stays an empty cell, never zero).
Arabic sheets open right to left. No formulas, macros, external links or images.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from xml.sax.saxutils import escape

_NUMBER = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d{1,3})?$")
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_SHEET_NAME = re.compile(r"[\[\]:*?/\\]")
MAX_TEXT = 32_767

STYLE = {"normal": 0, "header": 1, "title": 2, "note": 3, "wrap": 4}


class Number(str):
    """A cell that holds a number, given as its exact decimal text."""


@dataclass
class Sheet:
    name: str
    rows: list[list[Any]] = field(default_factory=list)
    styles: dict[int, str] = field(default_factory=dict)  # row index -> style name
    freeze: int | None = None  # rows above this index stay in view

    def add(self, cells: list[Any], style: str | None = None) -> None:
        if style:
            self.styles[len(self.rows)] = style
        self.rows.append(cells)


def _column(index: int) -> str:
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _text(value: Any) -> str:
    return escape(_ILLEGAL.sub("", str(value))[:MAX_TEXT])


def _cell(ref: str, value: Any, style: int) -> str:
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>' if style else ""
    if isinstance(value, Number) and _NUMBER.match(value):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{s}><is><t xml:space="preserve">{_text(value)}</t></is></c>'


def _sheet_xml(sheet: Sheet, rtl: bool) -> str:
    widths: dict[int, int] = {}
    for r, row in enumerate(sheet.rows):
        if sheet.styles.get(r) in ("title", "note", "wrap"):
            continue  # long single-cell lines do not widen the first column
        for c, value in enumerate(row):
            if value is not None:
                widths[c] = max(widths.get(c, 8), min(60, len(str(value)) + 2))
    cols = "".join(
        f'<col min="{c + 1}" max="{c + 1}" width="{w}" customWidth="1"/>'
        for c, w in sorted(widths.items())
    )
    rows = []
    for r, row in enumerate(sheet.rows):
        style = STYLE.get(sheet.styles.get(r, "normal"), 0)
        cells = "".join(_cell(f"{_column(c)}{r + 1}", v, style) for c, v in enumerate(row))
        rows.append(f'<row r="{r + 1}">{cells}</row>')
    pane = ""
    if sheet.freeze:
        pane = (f'<pane ySplit="{sheet.freeze}" topLeftCell="A{sheet.freeze + 1}" activePane="bottomLeft" '
                'state="frozen"/>')  # fmt: skip
    direction = ' rightToLeft="1"' if rtl else ""
    view = f'<sheetView workbookViewId="0"{direction}>{pane}</sheetView>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetViews>{view}</sheetViews>"
        + (f"<cols>{cols}</cols>" if cols else "")
        + f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )


STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="14"/><name val="Calibri"/></font>'
    '<font><i/><sz val="9"/><color rgb="FF595959"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFEEF1F0"/><bgColor indexed="64"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
    '<alignment wrapText="1" vertical="top"/></xf></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
)


def _names(sheets: list[Sheet]) -> list[str]:
    out: list[str] = []
    for s in sheets:
        base = _SHEET_NAME.sub(" ", s.name).strip().strip("'")[:31] or "Sheet"
        name, n = base, 2
        while name.lower() in (o.lower() for o in out):
            suffix = f" ({n})"
            name = base[: 31 - len(suffix)] + suffix
            n += 1
        out.append(name)
    return out


def workbook(sheets: list[Sheet], *, title: str, rtl: bool) -> bytes:
    names = _names(sheets)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>"
        ),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{_text(title)}</dc:title><dc:creator>OSRIP</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>'
        ),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>OSRIP</Application></Properties>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{_text(n)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, n in enumerate(names, start=1)
            )
            + "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/styles.xml": STYLES,
    }
    for i, sheet in enumerate(sheets, start=1):
        files[f"xl/worksheets/sheet{i}.xml"] = _sheet_xml(sheet, rtl)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return out.getvalue()
