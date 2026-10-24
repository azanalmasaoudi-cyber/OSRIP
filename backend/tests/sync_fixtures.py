"""Test workbooks with the verified layout of the NCSI Monthly Statistical Bulletin, tables 21
and 22 (October 2026 issue), built in memory. Values are made up for the tests, except that
the layout, labels, marks and units follow the official workbook."""

from __future__ import annotations

import io
import json
import zipfile
from xml.sax.saxutils import escape

from app.services.sync.xlsx import column_index

FMT_STYLE = 1  # cellXfs index whose number format is '#,##0.0'

ELEC_REGIONS = [
    "-Muscat",
    "-Dhofar",
    "-  Musandam",
    "-Ad Dakhliyah",
    "-Al Batinah⁽³⁾ & Adh Dhahira",
    "-Ash Sharqiya⁽³⁾",
    "- Al Wusta",
    "- Others⁽⁴⁾",
    "Total",
]
WATER_REGIONS = ["-Muscat", "-Dhofar", "-Other Governorates", "Total"]


def _cell(ref: str, value: str | float) -> str:
    if isinstance(value, str):
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    return f'<c r="{ref}" s="{FMT_STYLE}"><v>{value!r}</v></c>'


def _sheet(cells: dict[str, str | float]) -> bytes:
    rows: dict[int, list[str]] = {}
    for ref, value in cells.items():
        letters = "".join(ch for ch in ref if ch.isalpha())
        number = int(ref[len(letters) :])
        rows.setdefault(number, []).append((column_index(letters), _cell(ref, value)))  # type: ignore[arg-type]
    body = "".join(
        f'<row r="{n}">' + "".join(c for _, c in sorted(rows[n])) + "</row>" for n in sorted(rows)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{body}</sheetData></worksheet>"
    ).encode()


def workbook(sheets: dict[str, dict[str, str | float]]) -> bytes:
    names = list(sheets)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        z.writestr(
            "xl/workbook.xml",
            (
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                + "".join(
                    f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                    for i, n in enumerate(names)
                )
                + "</sheets></workbook>"
            ),
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(
                    f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
                    for i in range(len(names))
                )
                + "</Relationships>"
            ),
        )
        z.writestr(
            "xl/styles.xml",
            (
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.0"/></numFmts>'
                '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>'
            ),
        )
        for i, n in enumerate(names):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet(sheets[n]))
    return buffer.getvalue()


def _electricity(gross: list[list[float]], net: list[list[float]]) -> dict[str, str | float]:
    """``gross``/``net``: per region [E ytd 2026, F ytd 2025, H Sep, I Aug, J Jul, L 2025]."""
    cells: dict[str, str | float] = {
        "A2": "21 - الكهرباء",
        "A3": "21 -  Electricity",
        "A4": "Item",
        "C4": "نسبة التغير  Changes %",
        "E4": "الجملة - نهاية سبتمبر",
        "H4": "⁽²⁾2026",
        "I4": "⁽²⁾2026",
        "J4": "⁽²⁾2026",
        "L4": "⁽¹⁾2025",
        "N4": "البيان",
        "C5": "يناير - سبتمبر",
        "E5": "Total (End - Sep)",
        "C6": "Jan - Sep",
        "E6": "⁽²⁾2026",
        "F6": "⁽¹⁾2025",
        "H6": "سبتمبر",
        "I6": "أُغسطس",
        "J6": "يوليو",
        "C7": "(26/25)",
        "H7": "Sep",
        "I7": "Aug",
        "J7": "Jul",
        "E8": "GW \\H",
        "I8": "جيجاوات / ساعة",
        "A9": "Gross Production",
        "A19": "Net Production",
        "A29": "1- Provisional",
        "A30": "2-Preliminary",
        "A31": "3-Includes North & South Governorate",
        "A32": "4-Includes Others Governorate",
        "A38": "Source : Authority for Public Services",
    }
    for block, start in ((gross, 10), (net, 20)):
        for i, (label, values) in enumerate(zip(ELEC_REGIONS, block, strict=True)):
            row = start + i
            cells[f"A{row}"] = label
            cells[f"C{row}"] = 1.23456  # the publisher's percentage change: not imported
            for col, value in zip("EFHIJL", values, strict=True):
                cells[f"{col}{row}"] = value
    return cells


def _water(production: list[list[float]], unit: str = "(000)M³") -> dict[str, str | float]:
    cells: dict[str, str | float] = {
        "A38": "22 - المياه",
        "A39": "22- Water",
        "A40": "Item",
        "E41": "Total (End - Sep)",
        "H40": "⁽²⁾2026",
        "I40": "⁽²⁾2026",
        "J40": "⁽²⁾2026",
        "L40": "⁽¹⁾2025",
        "E42": "⁽²⁾2026",
        "F42": "⁽¹⁾2025",
        "H43": "Sep",
        "I43": "Aug",
        "J43": "Jul",
        "E44": unit,
        "A45": "Production",
        "A51": "1- Provisional",
        "A52": "2-Preliminary",
    }
    for i, (label, values) in enumerate(zip(WATER_REGIONS, production, strict=True)):
        row = 46 + i
        cells[f"A{row}"] = label
        for col, value in zip("EFHIJL", values, strict=True):
            cells[f"{col}{row}"] = value
    return cells


def bulletin(
    scale: float = 1.0, *, august_total: float | None = None, water_unit: str = "(000)M³"
) -> bytes:
    """A bulletin workbook. Regional rows sum to the total; ``august_total`` changes the
    national August gross figure (a revision)."""
    regions = [
        [
            100.04 * (i + 1) * scale,
            90.0 * (i + 1),
            11.04 * (i + 1),
            12.0 * (i + 1),
            13.0 * (i + 1),
            120.0 * (i + 1),
        ]
        for i in range(8)
    ]
    total = [sum(r[k] for r in regions) for k in range(6)]
    gross = [*regions, total]
    if august_total is not None:
        gross[-1] = [*total[:3], august_total, *total[4:]]
    net = [[v * 0.97 for v in r] for r in gross]
    water_regions = [
        [1000.0 * (i + 1), 900.0 * (i + 1), 110.0, 120.0, 130.0, 1200.0 * (i + 1)] for i in range(3)
    ]
    water_total = [sum(r[k] for r in water_regions) for k in range(6)]
    return workbook(
        {
            "1": {"C2": "population"},
            "21": _electricity(gross, net),
            "22": _water([*water_regions, water_total], water_unit),
        }
    )


def listing_page(entries: list[dict[str, object]]) -> bytes:
    data = {
        "props": {
            "pageProps": {"initialPublications": {"publications": entries, "total": len(entries)}}
        }
    }
    return (
        '<html><head></head><body><div id="__next"></div>'
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        "</body></html>"
    ).encode()


def msb_entry(
    pub_id: int = 1968,
    *,
    month: str = "October",
    year: int = 2026,
    xls: str | None = "https://api.ncsi.gov.om/uploads/xls/msb_oct_2026_1.xlsx",
) -> dict[str, object]:
    return {
        "id": pub_id,
        "title_en": f"Monthly Statistical Bulletin :{month} {year}",
        "title_ar": f"النشرة الإحصائية الشهرية : {year}",
        "created_at": "2026-10-20T09:28:38.000000Z",
        "updated_at": "2026-10-23T09:13:15.000000Z",
        "xls_file_url": xls,
        "pdf_file_url": "https://api.ncsi.gov.om/uploads/pdfs/msb_oct_2026_1.pdf",
    }
