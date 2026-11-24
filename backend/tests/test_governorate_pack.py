"""The owner's governorate evidence pack of November 2026 as import rows
(imports/governorate_pack.py), read from the workbook in docs/data-imports/2026-11-governorates:

* every sum of the staged areas matches the NCSI publication's own total (within rounding);
* all 63 wilayats sit in the governorate the registry gives them, and none receives a figure;
* full-year 2025 and the 2026 years to date are separate periods, and 2026 is never a year;
* grouped regions stay groups (never shared out among governorates), and the count of
  enterprises of all economic activities is not imported as trade.
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.imports import governorate_pack as gp
from app.services.imports.owner_workbooks import Mapped
from tests.test_wilayat_evidence import registry_areas

BACKEND = Path(__file__).resolve().parents[1]
PACK = BACKEND.parent / "docs" / "data-imports" / "2026-11-governorates"
WORKBOOK = PACK / "OSRIP_Oman_11_Governorates_63_Wilayats_Official_Data_2026.xlsx"
RECORDS = PACK / "moc-active-commercial-records-2025.xlsx"
WILAYAT = re.compile(r"^OM-[A-Z]{2}-\d\d$")


@pytest.fixture(scope="module")
def mapped() -> tuple[Mapped, gp.Checks]:
    import sys

    sys.path.insert(0, str(BACKEND / "scripts"))
    import stage_owner_workbooks as sow

    from app.services.sync.xlsx import Workbook

    book = Workbook(WORKBOOK.read_bytes(), dates=True)
    out, checks = Mapped(), gp.Checks()
    gp.annual_2025(sow.sheet_rows(book, "Governorates 2025", 3), out, checks)
    gp.fishery_2025(sow.sheet_rows(book, "Fishery 2025", 3), out, checks)
    gp.latest_2026(sow.sheet_rows(book, "Latest 2026", 3), out, checks)
    gp.wilayats_63(sow.sheet_rows(book, "Wilayats 63", 3), registry_areas(), checks)
    moc = Workbook(RECORDS.read_bytes(), dates=True)
    checks.records = gp.commercial_records(
        sow.sheet_rows(moc, moc.sheet_names[0], 1), registry_areas(), out
    )
    return out, checks


def rows(mapped_: tuple[Mapped, gp.Checks]) -> list[dict[str, str]]:
    return [r for url_rows in mapped_[0].rows.values() for r in url_rows]


def test_every_sum_matches_the_publications_own_total(mapped) -> None:  # noqa: ANN001
    checks = mapped[1].reconciliation()
    assert {what for what, *_ in checks} == {f"{k[0]} {k[1]}" for k in gp.PUBLISHED_TOTALS}
    for what, total, published, tolerance, agrees, _ in checks:
        assert agrees, f"{what}: {total} against {published} (±{tolerance})"
        assert tolerance < Decimal(6), f"{what}: the rounding allowed stays small ({tolerance})"


def test_all_63_wilayats_are_in_the_registrys_governorate_and_none_gets_a_figure(mapped) -> None:  # noqa: ANN001
    assert mapped[1].wilayats_matched == 63 and mapped[1].wilayat_problems == []
    # The only wilayat figures are the ministry's commercial records (published by wilayat).
    at_wilayats = {r["indicator_code"] for r in rows(mapped) if WILAYAT.match(r["area_code"])}
    assert at_wilayats == {"TRADE_COMMERCIAL_REGISTRATIONS_STOCK"}


def test_full_year_2025_by_governorate_with_provenance(mapped) -> None:  # noqa: ANN001
    annual = [
        r
        for r in rows(mapped)
        if r["period_start"] == "2025-01-01"
        and r["period_end"] == "2025-12-31"
        # The ministry's commercial records are tested on their own below.
        and r["indicator_code"] != "TRADE_COMMERCIAL_REGISTRATIONS_STOCK"
    ]
    by_indicator = Counter(r["indicator_code"] for r in annual)
    # Eleven governorates for each yearbook indicator; "Other" electricity; six fishing regions
    # and the national total.
    assert by_indicator == {
        "ELEC_GROSS_GENERATION": 12, "ELEC_DISTRIBUTION": 11, "WATER_PRODUCTION": 11,
        "WATER_DISTRIBUTION": 11, "AGRI_PROD_DATES": 11, "AGRI_PROD_HONEY": 11,
        "FISH_LANDINGS_TRADITIONAL": 7,
    }  # fmt: skip
    assert all(
        r["period_complete"] == "true"
        and r["source_locator"].startswith("Statistical Year Book 2026")
        for r in annual
    )
    honey = {r["area_code"]: r for r in annual if r["indicator_code"] == "AGRI_PROD_HONEY"}
    assert honey["OM-MA"]["value"] == "13264" and honey["OM-MA"]["unit_code"] == "kg"
    dates = [r for r in annual if r["indicator_code"] == "AGRI_PROD_DATES"]
    assert {r["revision_status"] for r in dates} == {"estimate"}, (
        "the yearbook says dates are estimated"
    )
    # A published zero stays a zero (Al Buraimi has no generating plant), never missing.
    zero = next(
        r
        for r in annual
        if r["indicator_code"] == "ELEC_GROSS_GENERATION" and r["area_code"] == "OM-BU"
    )
    assert zero["value"] == "0"
    other = next(r for r in annual if r["area_code"] == "OM-GRP-OTHER-ELEC")
    assert other["value"] == "480.2" and "never assigned" in other["note"]


def test_grouped_regions_are_never_shared_out(mapped) -> None:  # noqa: ANN001
    fishing = {
        r["area_code"]: r["value"]
        for r in rows(mapped)
        if r["indicator_code"] == "FISH_LANDINGS_TRADITIONAL"
    }
    assert fishing["OM-GRP-BATINAH"] == "84883"
    assert "OM-BS" not in fishing and "OM-BJ" not in fishing, "Al Batinah is one published figure"
    ytd = [r for r in rows(mapped) if r["period_start"] == "2026-01-01"]
    grouped = {r["area_code"] for r in ytd if r["area_code"].startswith("OM-GRP-")}
    assert grouped == {
        "OM-GRP-BATINAH-DHAHIRAH",
        "OM-GRP-SHARQIYAH",
        "OM-GRP-OTHER-ELEC",
        "OM-GRP-OTHER-WATER",
    }
    governorates_2026 = {r["area_code"] for r in ytd if re.match(r"^OM-[A-Z]{2}$", r["area_code"])}
    assert governorates_2026 == {"OM-MA", "OM-ZU", "OM-MU", "OM-DA", "OM-WU"}, (
        "only those the bulletin names"
    )


def test_2026_is_a_year_to_date_never_a_full_year(mapped) -> None:  # noqa: ANN001
    partial = [r for r in rows(mapped) if r["period_complete"] == "false"]
    assert {(r["period_start"][:4], r["period_end"]) for r in partial} == {
        ("2026", "2026-10-31"), ("2025", "2025-10-31"), ("2026", "2026-09-30"),
    }  # fmt: skip
    assert not [
        r
        for r in rows(mapped)
        if r["period_start"] == "2026-01-01" and r["period_end"] == "2026-12-31"
    ]
    exports = next(r for r in partial if r["indicator_code"] == "TRADE_MERCH_EXPORTS")
    assert (
        exports["value"] == "20889"
        and exports["unit_code"] == "million_OMR"
        and exports["area_code"] == "OM"
    )
    current = [r for r in partial if r["period_start"] == "2026-01-01"]
    assert {r["revision_status"] for r in current} == {"preliminary"}
    assert all("not the year" in r["note"] for r in current)
    water = next(
        r for r in current if r["indicator_code"] == "WATER_PRODUCTION" and r["area_code"] == "OM"
    )
    assert water["unit_code"] == "thousand_m3" and water["value"] == "417201.4"


def test_enterprises_are_business_context_not_trade(mapped) -> None:  # noqa: ANN001
    skipped = [s for s in mapped[0].skipped if "enterprises" in s[1].lower()]
    assert len(skipped) == 11 and all("not trade" in why for _, _, why in skipped)
    assert not [r for r in rows(mapped) if "ENTERPRISE" in r["indicator_code"]]


def test_the_committed_import_files_are_this_mapping(mapped) -> None:  # noqa: ANN001
    """The files in docs/data-imports/2026-11-governorates are rows of this mapping (those not
    already published or waiting for review when they were generated)."""
    import csv

    mapped_rows = {
        (r["indicator_code"], r["area_code"], r["period_start"], r["period_end"]): r["value"]
        for r in rows(mapped)
    }
    files = sorted(PACK.glob("*.csv"))
    assert [f.name for f in files] == [
        "moc-active-commercial-records-2025.csv",
        "ncsi-msb-2026-11-ytd.csv",
        "ncsi-yearbook-2026-governorates-2025.csv",
    ]
    staged = [r for f in files for r in csv.DictReader(f.read_text(encoding="utf-8").splitlines())]
    assert staged
    for r in staged:
        key = (r["indicator_code"], r["area_code"], r["period_start"], r["period_end"])
        assert mapped_rows.get(key) == r["value"], key


def test_the_ministrys_active_records_by_wilayat_are_registrations_not_trade(mapped) -> None:  # noqa: ANN001
    records = mapped[1].records
    assert records.problems == [] and len(records.matched) == 63
    assert records.total == 446189, "every active record in the ministry's file"
    assert records.by_governorate["OM-MA"] == 196056 and records.by_governorate["OM-MU"] == 3024
    stock = [
        r for r in rows(mapped) if r["indicator_code"] == "TRADE_COMMERCIAL_REGISTRATIONS_STOCK"
    ]
    assert len(stock) == 63 and all(WILAYAT.match(r["area_code"]) for r in stock), "wilayats only"
    assert {(r["period_start"], r["period_end"], r["unit_code"]) for r in stock} == {
        ("2025-01-01", "2025-12-31", "registration")
    }
    assert sum(int(r["value"]) for r in stock) == 446189
    # Two spellings the registry writes differently, matched inside their own governorate.
    codes = {r["area_code"] for r in stock}
    assert {"OM-MU-03", "OM-BS-04"} <= codes
    assert all("not trade values, not enterprises" in r["note"] for r in stock)
