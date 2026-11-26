# ruff: noqa: E501 - test cases are kept on one line each, as in tests/test_research_jobs_integration.py
"""The owner's electricity and water pack of November 2026 (imports/electricity_water_pack.py), read
from the workbook kept in docs/data-imports/2026-11-electricity-water:

* 2022 net actual consumption (36,427.1 GWh) and electricity distributed (36,178.6 GWh) stay two
  different indicators; every 2025 value is provisional;
* governorates only (no wilayat figure), the national totals kept beside the rounded sums;
* the utility's own figures under its own indicators and scope, never the national measures;
* the outlook: every item dated 2026 or later is a forecast, target, plan or option, never observed;
* a figure that differs from its source stops the mapping.
"""

from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import outlook
from app.services.imports import electricity_water_pack as ew
from app.services.imports.owner_workbooks import Mapped

BACKEND = Path(__file__).resolve().parents[1]
PACK = BACKEND.parent / "docs" / "data-imports" / "2026-11-electricity-water"
WORKBOOK = PACK / "OSRIP_Electricity_Water_2022_2032_Source_Verified.xlsx"


def _sheets() -> dict[str, list[dict[str, str]]]:
    sys.path.insert(0, str(BACKEND / "scripts"))
    import stage_owner_workbooks as sow

    from app.services.sync.xlsx import Workbook

    book = Workbook(WORKBOOK.read_bytes(), dates=True)
    names = (
        "Electricity_Annual",
        "Water_Annual",
        "Governorates_2025",
        "Nama_Water_Operations",
        "Nama_2026_2032",
    )
    return {n: sow.sheet_rows(book, n, 4) for n in names}


@pytest.fixture(scope="module")
def sheets() -> dict[str, list[dict[str, str]]]:
    return _sheets()


@pytest.fixture(scope="module")
def mapped(sheets) -> tuple[Mapped, list[dict]]:  # noqa: ANN001
    out = Mapped()
    ew.annual(sheets["Electricity_Annual"], "Electricity_Annual", out)
    ew.annual(sheets["Water_Annual"], "Water_Annual", out)
    ew.governorates(sheets["Governorates_2025"], out)
    ew.nama_operations(sheets["Nama_Water_Operations"], out)
    return out, ew.outlook_items(sheets["Nama_2026_2032"], "2026-11-24")


def rows(mapped_) -> list[dict[str, str]]:  # noqa: ANN001
    return [r for rs in mapped_[0].rows.values() for r in rs]


def value(mapped_, indicator: str, area: str, year: str) -> str:  # noqa: ANN001
    [r] = [r for r in rows(mapped_) if r["indicator_code"] == indicator and r["area_code"] == area
           and r["period_start"] == f"{year}-01-01" and "p. 131" in r["source_locator"]]  # fmt: skip
    return r["value"]


def test_2022_consumption_and_distribution_are_different_indicators(mapped) -> None:  # noqa: ANN001
    assert value(mapped, "ELEC_CONSUMPTION", "OM", "2022") == "36427.1"
    assert value(mapped, "ELEC_DISTRIBUTION", "OM", "2022") == "36178.6"
    # From 2023 the yearbook gives the same figure for both; they stay two series.
    assert (
        value(mapped, "ELEC_CONSUMPTION", "OM", "2025")
        == value(mapped, "ELEC_DISTRIBUTION", "OM", "2025")
        == "45033.1"
    )
    [note] = [
        r["note"]
        for r in rows(mapped)
        if r["indicator_code"] == "ELEC_CONSUMPTION" and r["period_start"] == "2022-01-01"
    ]
    assert "different published indicators" in note
    assert value(mapped, "ELEC_GROSS_GENERATION", "OM", "2025") == "50973.5"


def test_2025_is_provisional_and_earlier_years_are_as_published(mapped) -> None:  # noqa: ANN001
    for r in rows(mapped):
        if r["indicator_code"].endswith("_UTILITY"):
            continue
        expected = "provisional" if r["period_start"].startswith("2025") else "reported"
        assert r["revision_status"] == expected, (
            r["indicator_code"],
            r["area_code"],
            r["period_start"],
        )
        assert r["period_complete"] == "true" and r["period_end"][5:] == "12-31"


def test_governorates_only_with_the_national_total_kept(mapped) -> None:  # noqa: ANN001
    governorate = [
        r
        for r in rows(mapped)
        if "p. 134" in r["source_locator"] or "p. 137" in r["source_locator"]
    ]
    assert len(governorate) == 33 and {r["area_code"] for r in governorate} == {
        "OM-MA", "OM-ZU", "OM-MU", "OM-BU", "OM-DA", "OM-BS", "OM-BJ", "OM-SJ", "OM-SS", "OM-ZA", "OM-WU",
    }  # fmt: skip
    assert not [r for r in rows(mapped) if re.match(r"^OM-[A-Z]{2}-\d\d$", r["area_code"])], (
        "no wilayat figure"
    )
    elec = sum(
        Decimal(r["value"]) for r in governorate if r["indicator_code"] == "ELEC_DISTRIBUTION"
    )
    water = sum(
        Decimal(r["value"]) for r in governorate if r["indicator_code"] == "WATER_DISTRIBUTION"
    )
    assert elec == Decimal("45033.0") and water == Decimal("344.7"), "rounded governorate values"
    assert value(mapped, "ELEC_DISTRIBUTION", "OM", "2025") == "45033.1", (
        "the national total stays as published"
    )
    assert value(mapped, "WATER_DISTRIBUTION", "OM", "2025") == "344.6"


def test_the_utility_has_its_own_measures_and_scope(mapped) -> None:  # noqa: ANN001
    utility = [r for r in rows(mapped) if r["indicator_code"].endswith("_UTILITY")]
    assert {r["area_code"] for r in utility} == {"OM-GRP-NWS"}
    delivered = {
        r["period_start"][:4]: r["value"]
        for r in utility
        if r["indicator_code"] == "WATER_DELIVERED_UTILITY"
    }
    assert delivered == {"2023": "269.37", "2024": "280.28", "2025": "287.58"}
    assert not [
        r
        for r in rows(mapped)
        if r["area_code"] == "OM-GRP-NWS" and not r["indicator_code"].endswith("_UTILITY")
    ]


def test_the_outlook_never_calls_the_future_observed(mapped) -> None:  # noqa: ANN001
    items = mapped[1]
    assert len(items) == 19
    for i in items:
        assert outlook.check(i) == [], i["metric_code"]
        if i["year"] >= 2026:
            assert i["evidence_class"] in outlook.NOT_ACHIEVED, (i["metric_code"], i["year"])
    by = {(i["metric_code"], i["year"]): i for i in items}
    assert {i["evidence_class"] for i in items if i["year"] == 2032} <= {
        "forecast",
        "planned",
        "under_consideration",
    }
    assert (
        by[("ELEC_PEAK_DEMAND_MIS", 2032)]["value"] == "14147"
        and by[("ELEC_PEAK_DEMAND_MIS", 2032)]["unit"] == "MW"
    )
    assert by[("ELEC_RENEWABLE_SHARE_TARGET", 2030)]["evidence_class"] == "policy_target"
    assert by[("ELEC_RENEWABLE_SHARE", 2025)]["evidence_class"] == "estimate"
    assert by[("WATER_PLANT_GHUBRAH_III", 2027)]["evidence_class"] == "planned"
    assert "Under construction" in by[("WATER_PLANT_GHUBRAH_III", 2027)]["status_note_en"]
    assert by[("WATER_PLANT_SOHAR_ADDITIONAL", 2032)]["evidence_class"] == "under_consideration"
    assert (
        by[("ELEC_BESS_FIRST_COD", 2028)]["value"] is None
        and by[("ELEC_BESS_FIRST_COD", 2028)]["unit"] == "event"
    )
    assert all(i["source_sha256"] and len(i["source_sha256"]) == 64 for i in items)


def test_an_observed_2032_item_is_refused() -> None:
    item = {
        "evidence_class": "observed",
        "year": 2032,
        "issue_year": 2026,
        "unit": "MW",
        "value": "1",
        "source_url": "https://x.invalid/",
    }
    assert any("cannot be observed" in p for p in outlook.check(item))
    assert outlook.check({**item, "evidence_class": "forecast"}) == []


def test_a_figure_that_differs_from_its_source_stops_the_mapping(sheets) -> None:  # noqa: ANN001
    changed = [dict(r) for r in sheets["Electricity_Annual"]]
    for r in changed:
        if r.get("Indicator Code") == "consumption_total":
            r["2022"] = "36178.6"  # the distribution figure, as if the two were the same indicator
    with pytest.raises(ew.Mismatch, match="consumption_total 2022"):
        ew.annual(changed, "Electricity_Annual", Mapped())
