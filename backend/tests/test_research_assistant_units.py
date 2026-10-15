"""Unit checks for the research assistant: inline citation grounding, validation of
structured parts (recommendation cards, drivers, conflicts), table and PDF reading, source
classes, and the growth and share calculations. No database or network."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain import calculations as calc
from app.domain.quantities import GWH, Period
from app.domain.results import CalcStatus, ReasonCode
from app.services.assistant import grounding
from app.services.research import pages, sources
from tests import booklet_fixtures as fx

OBS = {
    "id": "E1",
    "kind": "observation",
    "value": "50100",
    "period_start": "2002-01-01",
    "period_end": "2002-12-31",
}
WEB_OFFICIAL = {
    "id": "E2",
    "kind": "web",
    "text": "Electricity generated in 2023 reached 41,234 GWh.",
    "published": "2024-05-02",
}
WEB_NEWS = {"id": "E3", "kind": "web", "text": "A newspaper reported 40,000 GWh in 2023."}
LEDGER = [OBS, WEB_OFFICIAL, WEB_NEWS]


# ------------------------------------------------------------------ inline citations


def test_numbers_must_be_cited_in_the_same_sentence() -> None:
    ok = grounding.validate("Generation was 50,100 GWh in 2002 [E1].", ["E1"], LEDGER)
    assert ok.ok, ok.problems
    uncited = grounding.validate("Generation was 50,100 GWh.\n\nSources: [E1].", ["E1"], LEDGER)
    assert not uncited.ok and "without an inline citation" in uncited.problems[0]
    wrong = grounding.validate("The official figure is 41,234 GWh [E3].", ["E3"], LEDGER)
    assert not wrong.ok and "not in cited evidence" in wrong.problems[0]


def test_arabic_sentences_and_digits_are_checked() -> None:
    ok = grounding.validate("بلغ التوليد ٥٠١٠٠ جيجاواط ساعة [E1]؟ نعم.", ["E1"], LEDGER)
    assert ok.ok, ok.problems
    bad = grounding.validate("بلغ التوليد ٦٠٠٠٠ جيجاواط ساعة [E1].", ["E1"], LEDGER)
    assert not bad.ok


def test_inline_markers_are_found() -> None:
    assert grounding.inline_markers("a [E1] b [E12], c [X3]") == ["E1", "E12"]


# ------------------------------------------------------------------ structured parts

CARD = {
    "finding": "Generation was 50,100 GWh in 2002.",
    "evidence": "Published value [E1].",
    "action": "Review capacity planning.",
    "expected_benefit": "Earlier identification of gaps (not quantified).",
    "prerequisites": "A peak-demand series.",
    "uncertainty": "Two years only.",
    "citations": ["E1"],
}


def test_cards_with_invented_benefits_or_missing_fields_are_withheld() -> None:
    final = {
        "recommendations": [
            CARD,
            {**CARD, "expected_benefit": "Could save 25% of fuel costs."},
            {**CARD, "prerequisites": ""},
            {**CARD, "citations": []},
            {**CARD, "citations": ["E99"]},
        ]
    }
    out = grounding.validate_structured(final, LEDGER, question="q", mode="analyze")
    assert out["recommendations"] == [CARD]
    assert out["withheld"] == {"recommendations": 4}
    # Cards belong to Analyze and Research only.
    ask = grounding.validate_structured(final, LEDGER, question="q", mode="ask")
    assert "recommendations" not in ask


def test_drivers_are_labelled_and_evidence_needs_citations() -> None:
    final = {
        "drivers": [
            {"driver": "weather", "basis": "hypothesis", "relation": "Heat may raise demand."},
            {"driver": "population", "basis": "evidence", "relation": "More residents."},
            {
                "driver": "desalination",
                "basis": "evidence",
                "relation": "Generation was 50,100 GWh [E1].",
                "citations": ["E1"],
            },
            {"driver": "astrology", "basis": "hypothesis", "relation": "No."},
            {"driver": "weather", "basis": "assumption", "relation": "A 3% rise each year."},
        ]
    }
    out = grounding.validate_structured(
        final, LEDGER, question="What if demand rises 3% a year?", mode="scenario"
    )
    assert [(d["driver"], d["basis"]) for d in out["drivers"]] == [
        ("weather", "hypothesis"),
        ("desalination", "evidence"),
        ("weather", "assumption"),  # the 3% was stated by the user
    ]
    assert out["withheld"] == {"drivers": 2}
    assert len(grounding.DRIVERS) == 10


def test_hypotheses_cannot_carry_invented_numbers() -> None:
    final = {
        "evidence_points": [{"statement": "50,100 GWh in 2002.", "citations": ["E1"]}],
        "hypotheses": [{"statement": "Cooling explains 40% of demand."}],
        "assumptions": [{"statement": "Definitions are unchanged."}],
    }
    out = grounding.validate_structured(final, LEDGER, question="q", mode="analyze")
    assert out["evidence_points"][0]["citations"] == ["E1"]
    assert "hypotheses" not in out and out["withheld"] == {"hypotheses": 1}
    assert out["assumptions"] == [{"statement": "Definitions are unchanged.", "citations": []}]


def test_conflicts_need_two_values_each_written_in_its_source() -> None:
    good = {
        "topic": "Generation 2023",
        "values": [
            {"evidence_id": "E2", "value_text": "41,234"},
            {"evidence_id": "E3", "value_text": "40,000"},
        ],
    }
    swapped = {
        "topic": "Generation 2023",
        "values": [
            {"evidence_id": "E2", "value_text": "40,000"},
            {"evidence_id": "E3", "value_text": "41,234"},
        ],
    }
    out = grounding.validate_structured(
        {"conflicts": [good, swapped]}, LEDGER, question="q", mode="research"
    )
    assert [c["topic"] for c in out["conflicts"]] == ["Generation 2023"]
    assert out["conflicts"][0]["values"] == good["values"]
    assert out["withheld"] == {"conflicts": 1}


# ------------------------------------------------------------------ pages and sources


def test_tables_are_read_as_rows_not_snippets() -> None:
    html = """<html><head><title>Bulletin</title></head><body>
      <p>Intro text.</p>
      <table><caption>Electricity generated (GWh)</caption>
        <tr><th>Year</th><th>Generated</th></tr>
        <tr><td>2022</td><td>40,100</td></tr>
        <tr><td>2023</td><td>41,234</td></tr>
      </table><script>ignore(1234)</script></body></html>"""
    page = pages.extract(html)
    assert "Table: Electricity generated (GWh)" in page.text
    assert "Year | Generated" in page.text and "2023 | 41,234" in page.text
    assert "ignore" not in page.text


def test_pdf_without_reader_is_reported_not_guessed(monkeypatch) -> None:  # noqa: ANN001
    import builtins

    real_import = builtins.__import__

    def no_pypdf(name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if name == "pypdf" or name.startswith("pypdf."):
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    with pytest.raises(pages.PdfUnavailable):
        pages.extract_pdf(b"%PDF-1.4 test")


def _pdf(text: str, created: str = "D:20240502120000") -> bytes:
    """A one-page PDF (Helvetica text, a title and a creation date), built byte by byte."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Title (Statistical bulletin) /CreationDate ({created}) >>".encode(),
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_text_title_and_publication_date_are_read() -> None:
    pytest.importorskip("pypdf")
    page = pages.extract_pdf(_pdf("Electricity generated in 2023: 41,234 GWh"))
    assert "[page 1]" in page.text and "41,234 GWh" in page.text
    assert page.title == "Statistical bulletin"
    assert page.published == "2024-05-02", "the document's own date, not the period covered"
    # A damaged file raises, and the caller reports it as unreadable.
    with pytest.raises(Exception):  # noqa: B017, PT011
        pages.extract_pdf(b"%PDF-1.4 not really a pdf")


def test_read_web_page_reads_a_pdf_report_as_evidence(monkeypatch) -> None:  # noqa: ANN001
    pytest.importorskip("pypdf")
    from app.domain.enums import DataMode
    from app.services.assistant.tools import Ledger
    from app.services.research import safe_fetch
    from app.services.research import service as research

    url = "https://www.ncsi.gov.om/test-fixture/bulletin.pdf"
    body = _pdf("Electricity generated in 2023: 41,234 GWh")
    monkeypatch.setattr(
        safe_fetch,
        "fetch",
        lambda *_a, **_k: safe_fetch.Fetched(url, 200, "application/pdf", "", False, raw=body),
    )
    ledger = Ledger(DataMode.SYNTHETIC)
    ledger.add({"kind": "web", "url": url, "title": "Bulletin", "query": "electricity 2023"})
    result = research.read_web_page(ledger, "E1", focus="electricity generated")
    assert result["status"] == "ok" and "41,234 GWh" in result["untrusted_page_text"]
    item = ledger.by_id()[result["evidence_id"]]
    assert item["content_kind"] == "pdf_excerpt" and item["source_class"] == "official"
    assert item["published"] == "2024-05-02" and item["published_basis"] == "document_metadata"
    # The number is grounded in the PDF text the model saw.
    verdict = grounding.validate(
        f"NCSI reports 41,234 GWh for 2023 [{item['id']}].", [item["id"]], ledger.items
    )
    assert verdict.ok, verdict.problems
    # A PDF without extractable text (e.g. scanned pages) is reported, never guessed at.
    body = _pdf("")
    scanned = research.read_web_page(ledger, "E1")
    assert scanned["status"] == "pdf_no_text" and "evidence_id" not in scanned


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.ncsi.gov.om/bulletin", "official"),
        ("https://data.worldbank.org/indicator/x", "international"),
        ("https://www.mdpi.com/2071-1050/1/1", "research"),
        ("https://doi.org/10.1000/xyz", "research"),
        ("https://news.example.com/oman-power", "secondary"),
    ],
)
def test_source_classes_and_ranking(url: str, expected: str) -> None:
    assert sources.classify(url)["source_class"] == expected
    assert sources.rank("official") < sources.rank("international") < sources.rank("research")
    assert sources.rank("research") < sources.rank("secondary")
    assert sources.evidence_class("research") == "research"


# ------------------------------------------------------------------ calculations


def test_compound_annual_growth_and_guards() -> None:
    one_year = calc.compound_annual_growth(
        fx.ELECTRICITY_GENERATION_Y1, fx.ELECTRICITY_GENERATION_Y2, 1
    )
    assert one_year.status is CalcStatus.OK and one_year.value == Decimal("4.375")
    y4 = fx.m("60500", GWH, Period(date(2005, 1, 1), date(2005, 12, 31)))
    four = calc.compound_annual_growth(fx.ELECTRICITY_GENERATION_Y1, y4, 4)
    assert four.value is not None and four.value.quantize(Decimal("0.0001")) == Decimal("5.9567")
    backwards = calc.compound_annual_growth(
        fx.ELECTRICITY_GENERATION_Y2, fx.ELECTRICITY_GENERATION_Y1, 1
    )
    assert backwards.status is not CalcStatus.OK and backwards.value is None
    no_span = calc.compound_annual_growth(
        fx.ELECTRICITY_GENERATION_Y1, fx.ELECTRICITY_GENERATION_Y2, 0
    )
    assert no_span.reason is ReasonCode.PERIODS_NOT_IN_ORDER
    zero = calc.compound_annual_growth(fx.m("0", GWH, fx.YEAR_1), fx.ELECTRICITY_GENERATION_Y2, 1)
    assert zero.reason is ReasonCode.NON_POSITIVE_START
    missing = calc.compound_annual_growth(
        fx.m(None, GWH, fx.YEAR_1), fx.ELECTRICITY_GENERATION_Y2, 1
    )
    assert missing.status is CalcStatus.MISSING, "missing is never treated as zero"
    other_unit = calc.compound_annual_growth(
        fx.WATER_CONSUMPTION_Y1, fx.ELECTRICITY_GENERATION_Y2, 1
    )
    assert other_unit.status is CalcStatus.INCOMPATIBLE


def test_share_of_total_and_guards() -> None:
    part = fx.m("12525", GWH)
    share = calc.share_of_total(part, fx.ELECTRICITY_GENERATION_Y2)
    assert share.value == Decimal("25")
    too_big = calc.share_of_total(fx.m("60000", GWH), fx.ELECTRICITY_GENERATION_Y2)
    assert too_big.reason is ReasonCode.COMPONENT_EXCEEDS_TOTAL
    other_year = calc.share_of_total(fx.m("100", GWH, fx.YEAR_1), fx.ELECTRICITY_GENERATION_Y2)
    assert other_year.status is CalcStatus.INCOMPATIBLE
    missing = calc.share_of_total(fx.m(None, GWH), fx.ELECTRICITY_GENERATION_Y2)
    assert missing.status is CalcStatus.MISSING
