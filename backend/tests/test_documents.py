"""Report documents and their exports without a database: Arabic shaping and right-to-left
ordering, the embedded font subset, PDF structure, Excel cells (numbers as numbers, text
never a formula, right-to-left sheets), CSV formula protection, and the research and
platform report builders (citations renumbered as references, nothing computed)."""

from __future__ import annotations

import csv
import io
import re
import zipfile
import zlib
from pathlib import Path

import pytest

from app.services.datasets.analysis import analyse
from app.services.documents import export, fonts, text
from app.services.documents.build import dataset_document, platform_document, research_document
from app.services.documents.model import Document, validate
from app.services.documents.xlsx import Number, Sheet, workbook
from app.services.sync.xlsx import Workbook

ROWS = [["2020", "Muscat", "10120.5"], ["2021", "Muscat", "10500"], ["2022", "Muscat", "11020.25"],
        ["2020", "Dhofar", "2100"], ["2021", "Dhofar", "2200"], ["2022", "Dhofar", "2350"]]  # fmt: skip
INFO = {
    "name": "gen.csv",
    "file_type": "csv",
    "sheet": None,
    "created_at": "2026-10-27T07:00:00+00:00",
    "sha256": "ab" * 32,
}


def _font() -> fonts.Font:
    try:
        return fonts.report_font()
    except fonts.FontError:
        pytest.skip("no TrueType font with Arabic and Latin letters on this machine")


# ------------------------------------------------------------------ shaping and ordering


def test_arabic_letters_take_their_joined_forms_with_lam_alef() -> None:
    assert [hex(ord(c)) for c in text.shape("السلام")] == [
        "0xfe8d",
        "0xfedf",
        "0xfeb4",
        "0xfefc",
        "0xfee1",
    ]
    assert text.shape("لا") == "ﻻ", "an isolated lam-alef ligature"
    assert text.shape("دار") == "ﺩﺍﺭ", "dal and alef never join the next letter"
    assert text.shape("كَتَبَ") == text.shape("كتب"), "short-vowel marks are left out"
    assert text.shape("Muscat 2024") == "Muscat 2024"


@pytest.mark.parametrize(
    ("logical", "rtl", "expected"),
    [
        ("abc (GWh) 12.5%", False, "abc (GWh) 12.5%"),
        ("عام 2024", True, "2024 ماع"),
        ("قيمة (+18.67%).", True, ".(+18.67%) ةميق"),
        ("من Generation (GWh) إلى", True, "ىلإ Generation (GWh) نم"),
        ("A 2,100 B", False, "A 2,100 B"),
    ],
)
def test_lines_are_ordered_for_display(logical: str, rtl: bool, expected: str) -> None:
    assert text.visual(logical, rtl) == expected


def test_line_direction_follows_the_document_unless_the_line_has_no_such_letter() -> None:
    assert text.direction("Peak load (MW) حسب Region", True) is True
    assert text.direction("Generation (GWh)", True) is False
    assert text.direction("2024", True) is True
    assert text.direction("مسقط", False) is True
    assert text.direction("Oman مسقط", False) is False


def test_wrapping_keeps_words_and_cuts_only_overlong_ones() -> None:
    assert text.wrap("one two three four", 9, len) == ["one two", "three", "four"]
    assert text.wrap("abcdefghij", 4, len) == ["abcd", "efgh", "ij"]


# ------------------------------------------------------------------ font subset


def test_the_font_subset_keeps_used_glyphs_and_still_loads(tmp_path: Path) -> None:
    font = _font()
    used = {font.glyph(ord(c)) for c in "OSRIP 2024"} | {font.glyph(0xFEDF)}
    subset = font.subset(used)
    assert len(subset) < len(font.data) / 3
    path = tmp_path / "subset.ttf"
    path.write_bytes(subset)
    again = fonts.load(str(path))
    assert again.glyph(ord("O")) == font.glyph(ord("O")), "glyph ids are unchanged"
    assert b"GSUB" not in subset[: 12 + 16 * 40], "shaping tables are not embedded"


def test_a_font_that_forbids_embedding_is_refused(tmp_path: Path) -> None:
    font = _font()
    data = bytearray(font.data)
    offset = font.tables[b"OS/2"][0]
    data[offset + 8 : offset + 10] = (0x0002).to_bytes(2, "big")  # restricted licence
    path = tmp_path / "restricted.ttf"
    path.write_bytes(bytes(data))
    with pytest.raises(fonts.FontError, match="forbids_embedding"):
        fonts.load(str(path))


# ------------------------------------------------------------------ documents and exports


def _dataset_doc(language: str) -> Document:
    a = analyse(["Year", "Region", "Generation (GWh)"], ROWS)
    return Document.model_validate(
        dataset_document(INFO, a, None, language, "Generation", ["Why?"])
    )


@pytest.mark.parametrize("language", ["en", "ar"])
def test_pdf_reports_are_complete_pdf_files_with_a_text_layer(language: str) -> None:
    _font()
    pdf = export.to_pdf(_dataset_doc(language))
    assert pdf.startswith(b"%PDF-1.7") and pdf.rstrip().endswith(b"%%EOF")
    assert b"/ToUnicode" in pdf and b"/FontFile2" in pdf and b"/Identity-H" in pdf
    assert f"/Lang ({language})".encode() in pdf
    assert (b"/Direction /R2L" in pdf) == (language == "ar")
    assert b"/JavaScript" not in pdf and b"/OpenAction" not in pdf
    assert len(re.findall(rb"/Type /Page\b", pdf)) >= 2
    xref = int(pdf.rsplit(b"startxref", 1)[1].split()[0])
    assert pdf[xref : xref + 4] == b"xref"


def test_pdf_charts_are_drawn_from_the_report_tables_only() -> None:
    _font()
    pdf = export.to_pdf(_dataset_doc("en"))
    streams = [zlib.decompress(m) for m in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S)]
    drawing = b"\n".join(s for s in streams if b" re f" in s or b" l S" in s)
    assert drawing, "charts and tables are vector drawings"


def test_excel_numbers_are_numbers_text_is_never_a_formula_and_arabic_is_right_to_left() -> None:
    sheet = Sheet("Data", freeze=1)
    sheet.add(["name", "value"], "header")
    sheet.add(['=HYPERLINK("http://x")', Number("10120.5")])
    sheet.add([None, Number("-3")])
    data = workbook([sheet], title="T", rtl=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode()
    assert "<f>" not in xml and 'rightToLeft="1"' in xml and 'state="frozen"' in xml
    assert '<c r="B2"><v>10120.5</v></c>' in xml
    book = Workbook(data)
    rows = book.sheet("Data")
    assert rows.get(2, 1) == '=HYPERLINK("http://x")', "kept as text"
    assert (rows.get(2, 2), rows.get(3, 2), rows.get(3, 1)) == ("10120.5", "-3", None)


def test_a_report_workbook_has_the_report_each_table_and_references() -> None:
    data = export.to_xlsx(_dataset_doc("en"))
    book = Workbook(data)
    names = book.sheet_names
    assert names[0] == "Report" and names[-1] == "References"
    stats = book.sheet(next(n for n in names if n.endswith("Statistics")))
    assert stats.get(2, 1) == "Column" and stats.get(3, 3) == "38290.75", (
        "the exact sum of the file's values"
    )


def test_csv_exports_protect_text_and_keep_numbers() -> None:
    doc = Document.model_validate(validate({
        "kind": "dataset", "language": "en", "title": "=cmd|' /C calc'!A0", "created_at": "2026-10-27",
        "sections": [{"heading": "S", "blocks": [{"type": "table", "columns": [{"label": "a"}, {"label": "v", "numeric": True}],
                                                  "rows": [["@SUM(A1)", "-5"], ["x", None]]}]}],
    }))  # fmt: skip
    rows = list(csv.reader(io.StringIO(export.to_csv(doc).lstrip("﻿"))))
    assert rows[0] == ["'=cmd|' /C calc'!A0"]
    assert ["'@SUM(A1)", "-5"] in rows and ["x", ""] in rows


def test_malformed_documents_are_refused() -> None:
    base = {"kind": "dataset", "language": "en", "title": "T", "created_at": "2026-10-27"}
    with pytest.raises(ValueError, match="one cell per column"):
        validate({**base, "sections": [{"heading": "S", "blocks": [
            {"type": "table", "columns": [{"label": "a"}], "rows": [["1", "2"]]}]}]})  # fmt: skip
    with pytest.raises(ValueError):
        validate({**base, "sections": [], "script": "<script>"})


# ------------------------------------------------------------------ builders


def test_research_report_keeps_the_verified_answer_and_numbers_its_sources() -> None:
    message = {
        "content": "Generation reached **31,732.5 GWh** [E2].\n\n- Up 1,546.5 GWh from 2025 E2 [E9], not fuel E10",
        "citations": ["E2", "E9"],
        "evidence": [
            {"id": "E2", "kind": "web", "title": "NCSI release", "url": "https://www.ncsi.gov.om/news/366",
             "publisher": {"en": "NCSI", "ar": "المركز الوطني للإحصاء والمعلومات"}, "published": "2026-09-01",
             "retrieved_at": "2026-10-25T10:00:00+00:00", "content_kind": "page_excerpt"},
            {"id": "E4", "kind": "observation", "indicator": "ELEC_GROSS_GENERATION", "area": "OM",
             "period_start": "2025-01-01", "period_end": "2025-07-31", "source": {"title": "Bulletin", "publisher": "NCSI"}},
        ],
        "calculations": [
            {"id": "E9", "kind": "calculation", "value": "1546.50000", "unit": "GWh", "inputs": ["E2", "E4"],
             "formula": {"en": "current − previous", "ar": "الحالية − السابقة"}},
        ],
        "structured": {"conflicts": [{"topic": "Gross generation", "note": "",
                                      "values": [{"evidence_id": "E2", "value_text": "31,732.5"}]}]},
        "model": "deepseek-flash",
    }  # fmt: skip
    doc = Document.model_validate(
        research_document("Latest generation?", message, "ar", "Generation")
    )
    assert doc.sections[0].blocks[0].text == "Latest generation?"
    summary = doc.sections[1].blocks
    assert summary[0].text == "Generation reached 31,732.5 GWh [1]."
    assert summary[1].items == ["Up 1,546.5 GWh from 2025 [1] [C1], not fuel E10"]
    calculations = next(s for s in doc.sections if s.heading == "الحسابات").blocks[0]
    assert calculations.rows == [["C1", "الحالية − السابقة", "1546.5", "GWh", "[1][2]"]]
    assert [r.url for r in doc.references] == ["https://www.ncsi.gov.om/news/366", None]
    assert doc.references[0].publisher == "المركز الوطني للإحصاء والمعلومات"
    assert doc.references[1].title == "Bulletin", "a calculation's input is a reference too"
    assert "31,732.5 [1]" in doc.sections[-1].blocks[0].items[0]


def test_platform_report_document_from_frozen_content() -> None:
    content = {
        "title": "Electricity 2024", "data_mode": "synthetic", "label": "SYNTHETIC", "section": "electricity",
        "filters": {"indicator": "X"}, "generated_at": "2026-10-01T00:00:00+00:00",
        "series": [{"indicator": {"name_en": "Generation", "name_ar": "التوليد"}, "area": {"name_en": "Oman", "name_ar": "عُمان"},
                    "unit": {"label_en": "GWh", "label_ar": "غيغاواط ساعة"}, "dataset_version": {"label": "v1"},
                    "observations": [{"period_start": "2024-01-01", "period_end": "2024-12-31", "value": "41234", "quality_status": "accepted"},
                                     {"period_start": "2025-01-01", "period_end": "2025-12-31", "value": None, "quality_status": "withheld"}]}],
        "calculations": [], "review_cards": [], "sources": [{"source": {"dataset_title": "Bulletin"}, "label": "v1"}],
    }  # fmt: skip
    doc = Document.model_validate(platform_document(content, "en"))
    table = doc.sections[0].blocks[0]
    assert table.rows == [
        ["2024-01-01 – 2024-12-31", "41234", "accepted", "v1"],
        ["2025-01-01 – 2025-12-31", None, "withheld", "v1"],
    ]
    assert doc.references[0].title == "Bulletin"
