"""The November 2026 wilayat evidence review as import rows (imports/wilayat_evidence.py), checked
against the registry the migrations define and against the workbook itself:

* all 63 wilayats matched by their Arabic names (spelling variants included, never across
  governorates), and their 2025 populations add up to the workbook's 5,359,557;
* commercial registrations kept apart by measure and period: 24 for 2025 (full year), 8 for the
  first quarter of 2026, 3 for the second, and 4 stocks at the end of June 2026;
* water at governorate level only, adding up to the national production;
* January-September 2026 as a partial year, the 252 coverage statuses as documentation, and
  figures with no OSRIP area or indicator listed with the reason;
* the rows pass the import validation (the verified scope starts in January 2021).
"""

from __future__ import annotations

import csv
import io
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import DataMode, RowOutcome
from app.services.imports import wilayat_evidence as we
from app.services.imports.owner_workbooks import Mapped, csv_text

BACKEND = Path(__file__).resolve().parents[1]
WORKBOOK = (
    BACKEND.parent
    / "docs"
    / "data-imports"
    / "2026-11-wilayat"
    / "OSRIP_Wilayat_Evidence_Development_Review_2026.xlsx"
)
_QUOTED = r"'((?:[^']|'')*)'"


def registry_areas() -> list[we.Area]:
    """The governorates and wilayats as migration 0005 creates them."""
    sql = (BACKEND / "alembic" / "sql" / "0005_geography_forecasts_up.sql").read_text(
        encoding="utf-8"
    )
    areas = [we.Area("OM", "Oman", "عُمان", "national", None)]
    for code, en, ar in re.findall(rf"\('(OM-[A-Z]{{2}})', {_QUOTED}, {_QUOTED}\)", sql):
        areas.append(we.Area(code, en.replace("''", "'"), ar, "governorate", "OM"))
    for gov, code, en, ar in re.findall(
        rf"\('(OM-[A-Z]{{2}})', '(OM-[A-Z]{{2}}-\d\d)', {_QUOTED}, {_QUOTED}\)", sql
    ):
        areas.append(we.Area(code, en.replace("''", "'"), ar, "wilayat", gov))
    return areas


@pytest.fixture(scope="module")
def registry() -> we.Registry:
    reg = we.Registry(registry_areas())
    assert len(reg.wilayats) == 63, "every registry wilayat has its own Arabic key"
    return reg


def test_the_governorate_table_names_the_registrys_eleven_governorates(
    registry: we.Registry,
) -> None:
    codes = set(we.GOVERNORATES.values())
    assert len(codes) == 11
    assert {c for c, a in registry.by_code.items() if a.level == "governorate"} == codes


@pytest.mark.parametrize(
    ("ar", "en", "gov", "code"),
    [
        ("بخاء", "Bukha", "OM-MU", "OM-MU-02"),  # final hamza
        ("بهلاء", "Bahla", "OM-DA", "OM-DA-04"),
        ("إبراء", "Ibra", "OM-SS", "OM-SS-01"),
        ("دماء والطائيين", "Dima Wa At Taiyyin", "OM-SS", "OM-SS-05"),  # hamza and doubled ya
        (
            "لوى",
            "Liwa",
            "OM-BS",
            "OM-BS-04",
        ),  # spelt differently: the English name, same governorate
        ("شليم وجزر الحلانيات", "Shalim & Hallaniyat Islands", "OM-ZU", "OM-ZU-08"),  # word order
        ("مطرح", "Mutrah", "OM-MA", "OM-MA-05"),
    ],
)
def test_wilayat_names_match_the_registry_including_spelling_variants(
    registry: we.Registry, ar: str, en: str, gov: str, code: str
) -> None:
    assert registry.wilayat(ar, gov, en).code == code


def test_a_name_is_never_matched_in_another_governorate(registry: we.Registry) -> None:
    assert registry.wilayat("صحار", "OM-MA", "Sohar") is None  # Sohar is in Al Batinah North
    assert registry.wilayat("لوى", "OM-MA", "Liwa") is None


def _population_row(**over: str) -> dict[str, str]:
    row = {
        "Governorate EN": "Al Batinah North",
        "Wilayat EN": "Sohar",
        "Wilayat AR": "صحار",
        "Population 2024": "245000",
        "Population 2025": "250000",
        "Omani 2025": "150000",
        "Non-Omani 2025": "100000",
        "Population source": we.YEARBOOK,
    }
    return {**row, **over}


def test_population_is_end_of_year_counts_for_the_wilayat_with_its_components(
    registry: we.Registry,
) -> None:
    out = Mapped()
    english = we.population([_population_row()], registry, out)
    assert english == {"Sohar": "OM-BS-01"}
    rows = out.rows[we.YEARBOOK]
    assert [(r["indicator_code"], r["period_start"], r["value"]) for r in rows] == [
        ("POP_TOTAL", "2024-01-01", "245000"),
        ("POP_TOTAL", "2025-01-01", "250000"),
        ("POP_OMANI", "2025-01-01", "150000"),
        ("POP_NON_OMANI", "2025-01-01", "100000"),
    ]
    assert {
        (r["unit_code"], r["frequency"], r["period_complete"], r["area_code"]) for r in rows
    } == {("person", "annual", "true", "OM-BS-01")}
    # Parts that do not make up the total are reported.
    bad = Mapped()
    we.population([_population_row(**{"Omani 2025": "150001"})], registry, bad)
    assert any("differs from the total" in why for _, _, why in bad.skipped)


def _trade_row(
    period: str, measure: str = "NEW_COMMERCIAL_REGISTRATIONS", **over: str
) -> dict[str, str]:
    row = {
        "Governorate": "Al Batinah North",
        "Wilayat": "Sohar",
        "Actual period": period,
        "Indicator / definition": measure,
        "Value": "100",
        "Unit": "registrations",
        "Source ID": "MOC",
        "Official URL": "https://example.invalid/moc",
        "Interpretation note": "Official ministry announcement; "
        "verify definition prior to integration",
    }
    return {**row, **over}


def test_registrations_keep_their_own_measure_and_period(registry: we.Registry) -> None:
    out = Mapped()
    rows = [
        _trade_row("2025"),
        _trade_row("2026-Q1"),
        _trade_row("2026-Q2"),
        _trade_row("2026-Q2-end", "CUMULATIVE_COMMERCIAL_REGISTRATIONS"),
        _trade_row("2026-H1"),
    ]
    we.trade(rows, {"Sohar": "OM-BS-01"}, registry, out)
    got = [
        (
            r["indicator_code"],
            r["period_start"],
            r["period_end"],
            r["frequency"],
            r["period_complete"],
        )
        for r in out.rows["https://example.invalid/moc"]
    ]
    assert got == [
        ("TRADE_NEW_COMMERCIAL_REGISTRATIONS", "2025-01-01", "2025-12-31", "annual", "true"),
        ("TRADE_NEW_COMMERCIAL_REGISTRATIONS", "2026-01-01", "2026-03-31", "quarterly", "true"),
        ("TRADE_NEW_COMMERCIAL_REGISTRATIONS", "2026-04-01", "2026-06-30", "quarterly", "true"),
        # A stock on 30 June: its own indicator, never added to the new registrations.
        ("TRADE_COMMERCIAL_REGISTRATIONS_STOCK", "2026-04-01", "2026-06-30", "quarterly", "true"),
    ]
    assert [item for _, item, _ in out.skipped] == ["Sohar NEW_COMMERCIAL_REGISTRATIONS 2026-H1"]
    # "Verify the definition" in the announcement: a warning for the reviewer, not accepted as is.
    assert {r["quality_status"] for r in out.rows["https://example.invalid/moc"]} == {"warning"}


def test_water_stays_at_governorate_level_and_is_not_called_losses() -> None:
    out = Mapped()
    we.water(
        [
            {
                "Governorate EN": "Muscat",
                "Production 2024 (Mm3)": "233.3",
                "Production 2025 (Mm3)": "202.2",
                "Distribution 2024 (Mm3)": "134.6",
                "Distribution 2025 (Mm3)": "133.4",
                "Geographic coverage": "governorate",
                "Source URL": we.YEARBOOK,
            }
        ],
        out,
    )
    rows = out.rows[we.YEARBOOK]
    assert {r["area_code"] for r in rows} == {"OM-MA"}
    assert sorted((r["indicator_code"], r["period_start"][:4], r["value"]) for r in rows) == [
        ("WATER_DISTRIBUTION", "2024", "134.6"),
        ("WATER_DISTRIBUTION", "2025", "133.4"),
        ("WATER_PRODUCTION", "2024", "233.3"),
        ("WATER_PRODUCTION", "2025", "202.2"),
    ]
    assert all("not reported as losses" in r["note"] for r in rows)


def test_national_figures_without_an_osrip_area_or_indicator_are_listed_with_the_reason() -> None:
    out = Mapped()
    we.national(
        [
            {
                "Indicator": "Electricity distribution",
                "Year": "2021",
                "Value": "35661.1",
                "Coverage": "national",
                "Official / primary URL": "https://data.gov.om/OMELCT2016/electricity",
                "Critical note": "n",
            },
            {
                "Indicator": "Nama Water supply",
                "Year": "2025",
                "Value": "428.8",
                "Coverage": "Nama",
            },
            {
                "Indicator": "Total population",
                "Year": "2025",
                "Value": "5359557",
                "Coverage": "national",
            },
        ],
        out,
    )
    [row] = out.rows["https://data.gov.om/OMELCT2016/electricity"]
    assert (row["indicator_code"], row["area_code"], row["_step"]) == (
        "ELEC_DISTRIBUTION",
        "OM",
        "0.1",
    )
    reasons = {item: why for _, item, why in out.skipped}
    assert "excludes Dhofar" in reasons["Nama Water supply 2025"]
    assert "derived" in reasons["Total population 2025"]


def test_january_to_september_2026_is_a_partial_year_never_the_year() -> None:
    out = Mapped()
    we.interim(
        [
            {
                "Indicator": "New commercial registrations",
                "Actual observation period": "2026-01 through 2026-09",
                "Value": "35907",
                "Geographic level": "national",
                "Source URL": "u",
                "Definition/caveat": "c",
            },
            {
                "Indicator": "Total water production",
                "Actual observation period": "2026-04 through 2026-09",
                "Value": "1",
                "Geographic level": "national",
                "Source URL": "u",
            },
        ],
        out,
    )
    [row] = out.rows["u"]
    assert (
        row["period_start"],
        row["period_end"],
        row["period_complete"],
        row["revision_status"],
    ) == ("2026-01-01", "2026-09-30", "false", "preliminary")
    assert "not the year" in row["note"]
    assert out.skipped and "January" in out.skipped[0][2]


def test_the_rows_pass_the_import_validation() -> None:
    from app.services.imports.validation import (
        AreaRef,
        IndicatorRef,
        Reference,
        UnitRef,
        suggest_mapping,
        validate_rows,
    )

    out = Mapped()
    reg = we.Registry(registry_areas())
    we.population([_population_row()], reg, out)
    we.trade(
        [
            _trade_row(
                "2026-Q2-end",
                "CUMULATIVE_COMMERCIAL_REGISTRATIONS",
                **{"Official URL": we.YEARBOOK},
            )
        ],
        {"Sohar": "OM-BS-01"},
        reg,
        out,
    )
    rows = list(csv.DictReader(io.StringIO(csv_text(out.rows[we.YEARBOOK]))))
    ind = {
        code: IndicatorRef(
            id=code, dimension="count", measure="m", requires_commodity=False, requires_flow=False
        )
        for code in (
            "POP_TOTAL",
            "POP_OMANI",
            "POP_NON_OMANI",
            "TRADE_COMMERCIAL_REGISTRATIONS_STOCK",
        )
    }
    reference = Reference(
        indicators=ind,
        units={
            "person": UnitRef(id="p", dimension="count"),
            "registration": UnitRef(id="r", dimension="count"),
        },
        areas={"OM-BS-01": AreaRef(id="a", valid_from=None, valid_to=None)},
        commodities={},
        partners={},
    )
    results = validate_rows(
        rows, suggest_mapping(list(rows[0])), reference, DataMode.VERIFIED_SOURCE
    )
    assert [r.outcome for r in results if r.outcome is RowOutcome.REJECTED] == []


# ------------------------------------------------------------------ the workbook itself


@pytest.fixture(scope="module")
def workbook_rows(registry: we.Registry):  # noqa: ANN201
    sys.path.insert(0, str(BACKEND / "scripts"))
    from stage_owner_workbooks import sheet_rows

    from app.services.sync.xlsx import Workbook

    book = Workbook(WORKBOOK.read_bytes(), dates=True)
    out = Mapped()
    english = we.population(sheet_rows(book, "Wilayats_63", 3), registry, out)
    we.trade(sheet_rows(book, "Trade_Wilayat_Events", 3), english, registry, out)
    we.water(sheet_rows(book, "Water_Governorates", 3), out)
    we.interim(sheet_rows(book, "2026_Interim", 3), out)
    coverage = we.coverage(sheet_rows(book, "Axis_Coverage_252", 3))
    return english, out, coverage


def test_the_workbook_reconciles_63_wilayats_and_the_2025_total(workbook_rows) -> None:  # noqa: ANN001
    english, out, _ = workbook_rows
    assert len(set(english.values())) == 63
    assert we.national_total(out, "2025") == Decimal(5359557)
    assert not [s for s in out.skipped if s[0] in ("Wilayats_63", "Trade_Wilayat_Events")]


def test_the_workbook_keeps_24_annual_registrations_apart_from_quarters_and_stocks(
    workbook_rows,
) -> None:  # noqa: ANN001
    _, out, _ = workbook_rows
    trade = Counter(
        (r["indicator_code"], r["period_start"], r["frequency"])
        for rows in out.rows.values()
        for r in rows
        if r["indicator_code"].startswith("TRADE_") and r["area_code"] != "OM"
    )
    assert trade == {
        ("TRADE_NEW_COMMERCIAL_REGISTRATIONS", "2025-01-01", "annual"): 24,
        ("TRADE_NEW_COMMERCIAL_REGISTRATIONS", "2026-01-01", "quarterly"): 8,
        ("TRADE_NEW_COMMERCIAL_REGISTRATIONS", "2026-04-01", "quarterly"): 3,
        ("TRADE_COMMERCIAL_REGISTRATIONS_STOCK", "2026-04-01", "quarterly"): 4,
    }
    # Al Batinah North's six wilayats add up to the governorate total the ministry gives (4,271).
    north = sum(
        int(r["value"])
        for rows in out.rows.values()
        for r in rows
        if r["area_code"].startswith("OM-BS-")
        and r["period_start"] == "2025-01-01"
        and r["indicator_code"] == "TRADE_NEW_COMMERCIAL_REGISTRATIONS"
    )
    assert north == 4271


def test_the_workbook_water_is_by_governorate_and_adds_up_to_the_national_figure(
    workbook_rows,
) -> None:  # noqa: ANN001
    _, out, _ = workbook_rows
    water = [
        r
        for rows in out.rows.values()
        for r in rows
        if r["indicator_code"] == "WATER_PRODUCTION" and r["area_code"] != "OM"
    ]
    assert {r["area_code"].count("-") for r in water} == {1}, "governorates only, never wilayats"
    by_year = {
        y: sum(Decimal(r["value"]) for r in water if r["period_start"].startswith(y))
        for y in ("2024", "2025")
    }
    assert by_year["2025"] == Decimal("508.1")  # the national 2025 production
    assert abs(by_year["2024"] - Decimal("520.0")) <= Decimal("0.5")  # 519.7: rounded parts


def test_the_workbook_has_252_coverage_statuses_and_none_is_a_number(workbook_rows) -> None:  # noqa: ANN001
    _, _, coverage = workbook_rows
    assert sum(coverage.values()) == 252
    assert not any(re.fullmatch(r"[\d.,]+", status) for status in coverage)
