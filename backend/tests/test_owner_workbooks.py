"""The owner's November 2026 workbooks as import rows (imports/owner_workbooks.py): complete years
stay full years, every 2026 figure keeps its own period and is never a full year, rounded
billions become millions with their rounding noted, combined reporting areas are never split,
nothing is assigned to a wilayat, and figures without an indicator are listed with the reason.
The rows then pass the import validation (the verified scope starts in January 2021)."""

from __future__ import annotations

import csv
import io

from app.domain.enums import DataMode, RowOutcome
from app.services.imports import owner_workbooks as ow

URL = "https://api.ncsi.gov.om/uploads/pdfs/statistical_year_book_2026___issue_54_1777963604.pdf"


def _annual(name: str, year: str, value: str) -> dict[str, str]:
    return {"Indicator EN": name, "Year": year, "Value": value, "Area": "Oman",
            "Period type": "FULL_CALENDAR_YEAR", "Source URL": URL}  # fmt: skip


def test_complete_years_are_full_years_and_2025_is_provisional() -> None:
    out = ow.Mapped()
    ow.annual([_annual("Electricity production", "2021", "40992.30"),
               _annual("Electricity production", "2025", "50973.50"),
               _annual("Cultivated area estimate", "2021", "266.0"),
               _annual("Total registered population", "2021", "4527.00"),
               _annual("Fish landed / produced", "2021", "922083")], out)  # fmt: skip
    rows = out.rows[URL]
    first = rows[0]
    assert (first["indicator_code"], first["period_start"], first["period_end"]) == (
        "ELEC_GROSS_GENERATION", "2021-01-01", "2021-12-31",
    )  # fmt: skip
    assert first["period_complete"] == "true" and first["value"] == "40992.3"
    assert rows[1]["revision_status"] == "provisional" and rows[0]["revision_status"] == "reported"
    # Thousands of feddan become feddan, with the rounding kept for comparisons.
    assert (rows[2]["value"], rows[2]["unit_code"], rows[2]["_step"]) == (
        "266000",
        "feddan",
        "1000",
    )
    reasons = {item: why for _, item, why in out.skipped}
    assert "four OSRIP axes" in reasons["Total registered population 2021"]
    assert "aquaculture" in reasons["Fish landed / produced 2021"]


def test_2026_figures_keep_their_own_period_and_are_never_full_years() -> None:
    out = ow.Mapped()
    ow.latest([
        {"المحور / Axis": "Electricity", "المؤشر / Indicator": "Total generation",
         "2026 value": "42873.4000", "2025 matching": "41164.9000",
         "Jan / period start": "2026-01-01", "Period end": "2026-09-30",
         "2026 reference period": "Jan–Sep 2026", "Publication date": "2026-11-07",
         "Source URL": "https://www.omandaily.om/article/1214358",
         "Evidence / interpretation": "Preliminary"},
        {"المحور / Axis": "Trade", "المؤشر / Indicator": "Total goods exports",
         "2026 value": "18.3000", "2025 matching": "15.3000",
         "Jan / period start": "2026-01-01", "Period end": "2026-08-31",
         "2026 reference period": "Jan–Aug 2026", "Publication date": "2026-11-03",
         "Source URL": "https://www.ncsi.gov.om/ar/newsPage/newsDetail?id=420",
         "Evidence / interpretation": "Rounded"},
        {"المحور / Axis": "Food security", "المؤشر / Indicator": "Vegetable price inflation",
         "2026 value": "20.1", "Source URL": "x"},
    ], out)  # fmt: skip
    power = out.rows["https://www.omandaily.om/article/1214358"]
    assert [(r["period_start"], r["period_end"], r["value"]) for r in power] == [
        ("2026-01-01", "2026-09-30", "42873.4"),
        ("2025-01-01", "2025-09-30", "41164.9"),
    ]
    assert {r["period_complete"] for r in power} == {"false"}
    assert {r["revision_status"] for r in power} == {"preliminary"}
    # The publication date is in the note: only statement records carry a statement date.
    assert "Published 2026-11-07." in power[0]["note"] and "statement_date" not in power[0]
    [exports, _] = out.rows["https://www.ncsi.gov.om/ar/newsPage/newsDetail?id=420"]
    # OMR 18.3 billion, rounded: 18,300 million, approximately, with a warning and its rounding.
    assert (exports["value"], exports["unit_code"], exports["value_operator"]) == (
        "18300", "million_OMR", "~",
    )  # fmt: skip
    assert exports["quality_status"] == "warning" and exports["_step"] == "100"
    assert exports["flow"] == "" and power[0]["flow"] == ""
    assert "0.1 billion" in exports["note"]
    assert [why for _, item, why in out.skipped if item == "Vegetable price inflation"] == [
        ow.LATEST_NOT_IN_REGISTRY
    ]


def test_combined_reporting_areas_are_never_split_and_no_wilayat_is_used() -> None:
    out = ow.Mapped()
    rows = [
        {"Sector": "Electricity", "Geographic coverage": "Muscat", "2026 value": "749.6",
         "2025 same period": "244.5", "Period end": "2026-09-30", "Source URL": "u"},
        {"Sector": "Electricity",
         "Geographic coverage": "North/South Al Batinah + Ad Dhahirah (combined)",
         "2026 value": "26071.2", "Period end": "2026-09-30", "Source URL": "u"},
    ]  # fmt: skip
    ow.regions(rows, out)
    staged = out.rows["u"]
    assert {r["area_code"] for r in staged} == {"OM-MA"}
    assert all(r["area_code"].count("-") == 1 for r in staged), "governorates only, never wilayats"
    assert "never split" in out.skipped[0][2]


def test_the_rows_pass_the_import_validation_and_2021_is_in_scope() -> None:
    from app.services.imports.validation import (
        AreaRef,
        IndicatorRef,
        Reference,
        UnitRef,
        suggest_mapping,
        validate_rows,
    )

    out = ow.Mapped()
    ow.annual([_annual("Electricity production", "2021", "40992.30"),
               _annual("Merchandise imports (recorded)", "2021", "11888.00")], out)  # fmt: skip
    ow.latest([{"المحور / Axis": "Electricity", "المؤشر / Indicator": "Total generation",
                "2026 value": "42873.4", "Jan / period start": "2026-01-01",
                "Period end": "2026-09-30", "Publication date": "2026-11-07",
                "Source URL": URL}], out)  # fmt: skip
    text = ow.csv_text(out.rows[URL])
    assert "_step" not in text.splitlines()[0], "the rounding is never written to the file"
    rows = list(csv.DictReader(io.StringIO(text)))
    assert [r["flow"] for r in rows] == ["", "import", ""]
    reference = Reference(
        indicators={
            "ELEC_GROSS_GENERATION": IndicatorRef(
                id="i", dimension="energy", measure="gross_generation", requires_commodity=False,
                requires_flow=False),
            "TRADE_MERCH_IMPORTS": IndicatorRef(
                id="t", dimension="currency", measure="merchandise_imports",
                requires_commodity=False, requires_flow=True),
        },
        units={"GWh": UnitRef(id="u", dimension="energy"),
               "million_OMR": UnitRef(id="m", dimension="currency")},
        areas={"OM": AreaRef(id="a", valid_from=None, valid_to=None)},
        commodities={}, partners={},
    )  # fmt: skip
    mapping = suggest_mapping(list(rows[0]))
    results = validate_rows(rows, mapping, reference, DataMode.VERIFIED_SOURCE)
    for result in results:
        assert result.outcome is not RowOutcome.REJECTED, [i.code for i in result.issues]
