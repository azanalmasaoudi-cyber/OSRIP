"""The curated Oman reference pack: import, provenance and the acceptance checks.

Runs last (file name): it publishes verified-source data, which earlier tests expect
to be absent.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration

DOCX = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "Oman_Statistics_References_and_Images_English.docx"
)


@pytest.fixture(scope="module")
def pack() -> dict[str, Any]:
    from app.services import reference_pack

    return reference_pack.load_pack()


@pytest.fixture(scope="module")
def loaded(database_url: str, pack: dict[str, Any]) -> list[Any]:
    from app.db.session import session_factory
    from app.services import reference_pack

    with session_factory()() as session:
        return reference_pack.import_pack(session, pack, publish=True)


def series(client, **params: str) -> list[dict[str, Any]]:  # noqa: ANN001
    r = client.get(f"{API}/observations", params={"data_mode": "verified_source", **params})
    assert r.status_code == 200, r.text
    return r.json()["series"]


def only(items: list[dict[str, Any]], **meta: Any) -> dict[str, Any]:
    found = [
        s
        for s in items
        if all(
            s.get(k) == v or (isinstance(s.get(k), dict) and s[k].get("code") == v)
            for k, v in meta.items()
        )
    ]
    assert len(found) == 1, [
        (s["indicator"]["code"], s["area"]["code"], s["period_kind"]) for s in items
    ]
    return found[0]


def test_committed_pack_matches_the_reference_document(pack: dict[str, Any]) -> None:
    from app.services import reference_pack

    if not DOCX.exists():
        pytest.skip("reference document not present")
    rebuilt = reference_pack.build_pack(DOCX)
    assert json.dumps(rebuilt, sort_keys=True) == json.dumps(pack, sort_keys=True)
    assert pack["record_count"] == len(pack["records"]) == 346
    assert [s["code"] for s in pack["sources"]] == [f"S0{i}" for i in range(1, 9)]
    assert [n["code"] for n in pack["notes"]] == [f"Q0{i}" for i in range(1, 10)]


def test_import_count_equals_the_pack_and_repeats_add_nothing(loaded, pack, anonymous) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.services import reference_pack

    assert sum(r.rows for r in loaded) == 346 and all(r.rejected == 0 for r in loaded)
    with session_factory()() as s, s.begin():
        before = s.scalar(text("SELECT count(*) FROM observation WHERE record_ref IS NOT NULL"))
    with session_factory()() as session:
        again = reference_pack.import_pack(session, pack, publish=True)
    with session_factory()() as s, s.begin():
        after = s.scalar(text("SELECT count(*) FROM observation WHERE record_ref IS NOT NULL"))
    assert before == after == 346 and [r.status for r in again] == ["published"] * 5
    body = anonymous.get(f"{API}/reference-pack").json()
    assert (
        body["pack"]["published_records"] == 346 and body["pack"]["research_cutoff"] == "2026-09-27"
    )


def test_electricity_and_water_headlines(loaded, anonymous) -> None:  # noqa: ANN001
    gross = only(
        series(anonymous, indicator="ELEC_GROSS_GENERATION", area="OM", period_kind="year_to_date"),
        period_kind="year_to_date",
    )
    latest = gross["observations"][-1]
    assert (latest["period_start"], latest["period_end"], latest["value"]) == (
        "2026-01-01",
        "2026-08-31",
        "37481.8",
    )
    assert (
        gross["unit"]["code"] == "GWh"
        and latest["record_ref"] == "OM-0079"
        and latest["source_locator"] == "p. 24"
    )
    assert latest["revision_status"] == "preliminary" and gross["source"]["source_code"] == "S01"

    water = only(
        series(anonymous, indicator="WATER_PRODUCTION", area="OM", period_kind="year_to_date"),
        period_kind="year_to_date",
    )
    point = water["observations"][-1]
    assert water["unit"]["code"] == "million_m3" and Decimal(point["value"]) == Decimal("330.6493")
    assert (point["original_value"], point["original_unit"], point["conversion_factor"]) == (
        "330649.3",
        "thousand_m3",
        "0.001",
    )


def test_trade_headlines_and_derived_balance(loaded, anonymous) -> None:  # noqa: ANN001
    exports = only(
        series(anonymous, indicator="TRADE_MERCH_EXPORTS", period_kind="year_to_date"),
        period_kind="year_to_date",
    )
    imports = only(
        series(
            anonymous, indicator="TRADE_MERCH_IMPORTS", partner="total", period_kind="year_to_date"
        ),
        period_kind="year_to_date",
    )
    assert (
        exports["observations"][-1]["value"] == "15866"
        and imports["observations"][-1]["value"] == "10409"
    )
    assert exports["observations"][-1]["period_end"] == "2026-07-31"
    calcs = anonymous.get(f"{API}/analysis/trade", params={"data_mode": "verified_source"}).json()[
        "calculations"
    ]
    balance = [c for c in calcs if c["kind"] == "derived_balance" and "2026-01-01" in c["id"]]
    assert len(balance) == 1 and Decimal(balance[0]["result"]["value"]) == 5457
    assert (
        "(derived)" in balance[0]["title"]["en"]
        and "not a published figure" in balance[0]["notes"][0]["en"]
    )
    assert {i["record_ref"] for i in balance[0]["inputs"]} == {"OM-0239", "OM-0260"}


def test_fisheries_and_crops(loaded, anonymous) -> None:  # noqa: ANN001
    capture = only(
        series(anonymous, indicator="FISH_CAPTURE_LANDINGS", period_kind="year_to_date"),
        period_kind="year_to_date",
    )
    assert (
        capture["observations"][-1]["value"] == "468407"
        and capture["observations"][-1]["period_end"] == "2026-06-30"
    )
    value = only(
        series(anonymous, indicator="FISH_VALUE_INCL_AQUACULTURE", period_kind="year_to_date"),
        period_kind="year_to_date",
    )
    assert (
        value["observations"][-1]["value"] == "320795" and value["unit"]["code"] == "thousand_OMR"
    )
    assert "aquaculture" in value["indicator"]["limitation_en"]

    crops = series(anonymous, indicator="AGRI_CROP_PRODUCTION", period_kind="annual")
    points = {o["period_start"][:4]: o for s in crops for o in s["observations"]}
    assert points["2025"]["value"] == "4085864" and points["2025"]["source_locator"] == "p. 87"
    assert (
        points["2022"]["original_unit"] == "thousand_tonnes"
        and Decimal(points["2022"]["value"]) == 3491000
    )
    components = {
        code: next(
            o["value"]
            for s in series(anonymous, indicator=code, period_kind="annual")
            for o in s["observations"]
            if o["period_start"] == "2025-01-01"
        )
        for code in (
            "AGRI_PROD_VEGETABLES",
            "AGRI_PROD_FIELD_CROPS",
            "AGRI_PROD_FODDER",
            "AGRI_PROD_FRUIT",
        )
    }
    assert sum(Decimal(v) for v in components.values()) == Decimal("4085864")  # fodder included


def test_period_kinds_and_groups_are_never_mixed(loaded, anonymous) -> None:  # noqa: ANN001
    mixed = anonymous.get(
        f"{API}/observations",
        params={"data_mode": "verified_source", "indicator": "ELEC_GROSS_GENERATION"},
    )
    assert (
        mixed.status_code == 422
    )  # annual, year to date and monthly are never returned side by side
    calcs = anonymous.get(
        f"{API}/analysis/electricity", params={"data_mode": "verified_source"}
    ).json()["calculations"]
    for c in calcs:
        kinds = {i.get("period_kind") for i in c["inputs"]}
        assert len(kinds) <= 1, c["id"]
        if kinds == {"year_to_date"}:
            periods = {(i["period_end"][5:]) for i in c["inputs"]}
            assert len(periods) == 1, c["id"]  # a year-to-date total: the same months of each year
    ytd = [
        c
        for c in calcs
        if c["kind"] == "percentage_change"
        and "year_to_date" in c["id"]
        and "ELEC_GROSS" in c["id"]
    ]
    assert ytd and Decimal(ytd[0]["result"]["value"]).quantize(Decimal("0.0001")) == Decimal(
        "4.3036"
    )

    statements = series(anonymous, indicator="SELF_SUFFICIENCY_EGGS", period_kind="statement")
    eggs = [o for s in statements for o in s["observations"]]
    assert {(o["statement_date"], o["value_operator"], o["value"]) for o in eggs} == {
        ("2026-04-21", ">", "95"),
        ("2026-05-10", None, "95"),
    }
    annual = anonymous.get(
        f"{API}/observations",
        params={
            "data_mode": "verified_source",
            "indicator": "SELF_SUFFICIENCY_EGGS",
            "period_kind": "annual",
        },
    )
    assert annual.json()["series"] == []  # statements never appear in an annual trend

    registry = anonymous.get(f"{API}/areas").json()
    assert all(a["level"] != "reporting_group" for a in registry["areas"])
    groups = {g["code"]: g for g in registry["reporting_groups"]}
    assert groups["OM-GRP-BATINAH-DHAHIRAH"]["members"] == ["OM-BJ", "OM-BS", "OM-ZA"]
    assert (
        groups["OM-GRP-OTHER-ELEC"]["members_stated"] is False
        and groups["OM-GRP-OTHER-ELEC"]["members"] == []
    )
    grouped = series(
        anonymous,
        indicator="ELEC_GROSS_GENERATION",
        area="OM-GRP-BATINAH-DHAHIRAH",
        period_kind="year_to_date",
    )
    assert grouped[0]["area"]["level"] == "reporting_group"


def test_forecasts_are_withheld_and_conditions_say_what_is_measured(loaded, anonymous) -> None:  # noqa: ANN001
    overview = anonymous.get(
        f"{API}/forecast/overview", params={"data_mode": "verified_source"}
    ).json()
    pack_targets = [
        t
        for t in overview["targets"]
        if t["indicator"]
        in ("ELEC_GROSS_GENERATION", "AGRI_CROP_PRODUCTION", "TRADE_MERCH_EXPORTS")
    ]
    # Four annual values (2022-2025) are far from the twelve a time-ordered evaluation
    # needs; year-to-date totals are never counted as extra training points.
    assert pack_targets and all(t["status"] == "insufficient_data" for t in pack_targets)
    assert all(s["usable_observations"] <= 4 for t in pack_targets for s in t["series"])
    assert overview["insufficient_label"]["en"] == (
        "Insufficient comparable historical data for a reliable forecast."
    )
    body = anonymous.get(
        f"{API}/forecast/conditions", params={"data_mode": "verified_source"}
    ).json()
    assert set(body["domains"]) == {"electricity", "water", "food_security", "trade"}
    factors = {(d, f["code"]): f for d, fs in body["domains"].items() for f in fs}
    capacity = factors[("electricity", "capacity")]
    assert capacity["status"] == "measured"
    assert capacity["measured_by"][0]["indicator"] == "ELEC_INSTALLED_CAPACITY"
    assert factors[("electricity", "population")]["status"] == "scenario_assumption"
    losses = factors[("water", "network_losses")]
    assert losses["status"] == "scenario_assumption" and "Q02" in losses["note"]["en"]
    assert factors[("trade", "partner_concentration")]["status"] == "measured"
    assert factors[("trade", "policy_changes")]["evidence_needed"]["ar"]


def test_conflict_notes_and_every_source_are_visible(loaded, anonymous) -> None:  # noqa: ANN001
    body = anonymous.get(f"{API}/reference-pack").json()
    assert [n["code"] for n in body["notes"]] == [f"Q0{i}" for i in range(1, 10)]
    assert all(n["title"]["ar"] and n["body"]["ar"] for n in body["notes"])
    roles = {s["code"]: (s["role"], s["published_records"]) for s in body["sources"]}
    assert roles["S01"] == ("primary", 216) and roles["S08"] == ("superseded_crosscheck", 0)
    # Q01: the superseded press figures are documented, not imported.
    q01 = next(n for n in body["notes"] if n["code"] == "Q01")
    assert "51612.3" in q01["body"]["en"]
    assert not series(
        anonymous, indicator="ELEC_GROSS_GENERATION", area="OM", period_kind="annual"
    ) or all(
        o["value"] != "51612.3"
        for s in series(
            anonymous, indicator="ELEC_GROSS_GENERATION", area="OM", period_kind="annual"
        )
        for o in s["observations"]
    )
