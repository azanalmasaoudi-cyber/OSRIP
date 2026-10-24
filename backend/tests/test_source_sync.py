"""Official statistics sync (pure parts): the safe workbook reader, the bulletin's verified
layout (tables 21 and 22), the publications list, retries with backoff, and the comparison
that keeps repeated figures out of new imports."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services.sync import fetch, ncsi_listing, ncsi_msb
from app.services.sync.registry import MONTHLY_BULLETIN, release_label
from app.services.sync.service import same_figure
from app.services.sync.xlsx import Workbook, WorkbookError, displayed, format_decimals, number_text
from tests.sync_fixtures import bulletin, listing_page, msb_entry, workbook


def test_numbers_are_read_as_the_publisher_displays_them() -> None:
    assert number_text("4811.0879999999997") == "4811.088"  # as stored in the October workbook
    assert number_text("65") == "65"
    assert displayed("571.3255337683111", 1) == "571.3"
    assert displayed("0.05", 1) == "0.1"  # half up, as a spreadsheet displays it
    assert displayed("571.3255", None) == "571.3255"  # General format: unchanged
    assert [
        format_decimals(f) for f in ("#,##0.0", "0.00", "#,##0", "0%", '"GWh" 0.0', "General")
    ] == [
        1,
        2,
        0,
        None,
        1,
        None,
    ]
    book = Workbook(workbook({"21": {"A1": "x", "B2": 571.3255337683111}}))
    assert book.sheet("21").get(2, 2) == "571.3"


def test_unsafe_or_broken_workbooks_are_refused() -> None:
    with pytest.raises(WorkbookError):
        Workbook(b"not a zip")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(
            "xl/workbook.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><workbook/>'
        )
    with pytest.raises(WorkbookError, match="xml_declarations_not_allowed"):
        Workbook(buffer.getvalue())
    # A damaged archive entry is a workbook error, not a crash.
    damaged = bulletin().replace(b"Gross Production", b"Gross Productiom")
    with pytest.raises(WorkbookError, match="file_damaged"):
        ncsi_msb.parse_workbook(damaged, "MSB-2026-10")


def test_bulletin_tables_become_records_with_periods_status_and_locators() -> None:
    parsed = ncsi_msb.parse_workbook(bulletin(), "MSB-2026-10")
    assert parsed.tables == ["21", "22"] and parsed.checks == []
    # 2 electricity blocks x 9 areas x 6 columns + 1 water block x 4 areas x 6 columns.
    assert len(parsed.records) == 2 * 9 * 6 + 4 * 6
    by = {(r.indicator_code, r.area_code, r.period_start, r.period_end): r for r in parsed.records}
    sep = by[("ELEC_GROSS_GENERATION", "OM-ZU", date(2026, 9, 1), date(2026, 9, 30))]
    assert (
        sep.frequency == "monthly" and sep.period_complete and sep.revision_status == "preliminary"
    )
    assert sep.value == Decimal("22.1") and sep.source_locator == "Table 21, cell H11"
    assert sep.record_ref == "MSB-2026-10/T21/H11"
    ytd = by[("ELEC_GROSS_GENERATION", "OM-MA", date(2025, 1, 1), date(2025, 9, 30))]
    assert (
        ytd.frequency == "annual"
        and not ytd.period_complete
        and ytd.revision_status == "provisional"
    )
    year = by[("ELEC_NET_GENERATION", "OM-GRP-OTHER-ELEC", date(2025, 1, 1), date(2025, 12, 31))]
    assert year.period_complete and year.unit_code == "GWh"
    water = by[("WATER_PRODUCTION", "OM-GRP-OTHER-WATER", date(2026, 7, 1), date(2026, 7, 31))]
    assert water.unit_code == "thousand_m3" and water.value == Decimal("130")
    # The publisher's percentage changes (column C) are not imported.
    assert not any(r.source_locator.endswith(("C10", "C11")) for r in parsed.records)


def test_an_unknown_region_or_unit_stops_the_conversion() -> None:
    from tests import sync_fixtures as f

    original = f.ELEC_REGIONS[:]
    try:
        f.ELEC_REGIONS[1] = "-Dhofar and Al Wusta"
        with pytest.raises(ncsi_msb.LayoutError, match="not in the map"):
            ncsi_msb.parse_workbook(bulletin(), "MSB-2026-10")
    finally:
        f.ELEC_REGIONS[:] = original
    with pytest.raises(ncsi_msb.LayoutError, match="expected unit thousand_m3"):
        ncsi_msb.parse_workbook(bulletin(water_unit="(000)Litres"), "MSB-2026-10")


def test_totals_that_do_not_add_up_are_reported() -> None:
    parsed = ncsi_msb.parse_workbook(bulletin(august_total=1.0), "MSB-2026-10")
    assert any("regions add up to" in c and "column I" in c for c in parsed.checks)


def test_the_publications_list_and_release_labels() -> None:
    pubs = ncsi_listing.parse(listing_page([msb_entry(), msb_entry(1967, xls=None)]))
    assert pubs[0].id == "1968" and pubs[0].xls_url and pubs[0].created_at is not None
    assert pubs[1].xls_url is None
    assert release_label(MONTHLY_BULLETIN, pubs[0].title_en) == "MSB-2026-10"
    assert release_label(MONTHLY_BULLETIN, "Consumer Price Inflation: September 2026") is None
    with pytest.raises(ncsi_listing.ListingError):
        ncsi_listing.parse(b"<html>no data</html>")
    # A file outside the publisher's upload folder is not trusted as the release's file.
    other = msb_entry(xls="https://example.org/msb.xlsx")
    assert ncsi_listing.parse(listing_page([other]))[0].xls_url is None


def _client(responses: list[httpx.Response]):  # noqa: ANN202
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return responses.pop(0)

    def factory(timeout: float) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout)

    return factory, calls


def test_fetch_retries_with_backoff_then_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(fetch, "sleep", waits.append)
    factory, calls = _client([httpx.Response(503), httpx.Response(503), httpx.Response(503)])
    monkeypatch.setattr(fetch, "client_factory", factory)
    with pytest.raises(fetch.FetchError) as err:
        fetch.get(
            "https://www.ncsi.gov.om/en/publications",
            hosts=frozenset({"www.ncsi.gov.om"}),
            accept=("text/html",),
            max_bytes=1000,
            attempts=3,
            backoff=2.0,
        )
    assert err.value.status == 503 and err.value.attempts == 3 and len(calls) == 3
    assert waits == [2.0, 4.0]
    # Retry-After is respected; a 404 is not retried.
    factory, calls = _client(
        [
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok"),
        ]
    )
    monkeypatch.setattr(fetch, "client_factory", factory)
    waits.clear()
    got = fetch.get(
        "https://www.ncsi.gov.om/en/publications",
        hosts=frozenset({"www.ncsi.gov.om"}),
        accept=("text/html",),
        max_bytes=1000,
    )
    assert got.body == b"ok" and got.attempts == 2 and waits == [7.0]
    factory, calls = _client([httpx.Response(404)])
    monkeypatch.setattr(fetch, "client_factory", factory)
    with pytest.raises(fetch.FetchError, match="http_404"):
        fetch.get(
            "https://www.ncsi.gov.om/x",
            hosts=frozenset({"www.ncsi.gov.om"}),
            accept=(),
            max_bytes=10,
        )
    assert len(calls) == 1


def test_fetch_stays_on_allowed_https_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    hosts = frozenset({"www.ncsi.gov.om"})
    with pytest.raises(fetch.FetchError, match="https_required"):
        fetch.get("http://www.ncsi.gov.om/", hosts=hosts, accept=(), max_bytes=10)
    with pytest.raises(fetch.FetchError, match="host_not_allowed"):
        fetch.get("https://example.org/", hosts=hosts, accept=(), max_bytes=10)
    factory, _ = _client([httpx.Response(302, headers={"location": "https://evil.example/x"})])
    monkeypatch.setattr(fetch, "client_factory", factory)
    with pytest.raises(fetch.FetchError, match="host_not_allowed"):
        fetch.get("https://www.ncsi.gov.om/", hosts=hosts, accept=(), max_bytes=10)
    factory, _ = _client(
        [httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 50)]
    )
    monkeypatch.setattr(fetch, "client_factory", factory)
    with pytest.raises(fetch.FetchError, match="too_large"):
        fetch.get("https://www.ncsi.gov.om/", hosts=hosts, accept=("text/html",), max_bytes=10)


def test_same_figure_compares_at_the_precision_both_publications_give() -> None:
    assert same_figure(Decimal("427.9"), Decimal("427.90"))
    assert same_figure(Decimal("5622.4"), Decimal("5622.36"))  # 5622.36 published as 5622.4
    assert not same_figure(Decimal("5743.9"), Decimal("5745.6"))
    assert not same_figure(Decimal("10"), Decimal("11"))
