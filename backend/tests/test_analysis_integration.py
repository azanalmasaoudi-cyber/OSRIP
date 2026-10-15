"""Section calculations over published data (booklet 3.5-3.8, Table 4.2; T01, T02, T09, T12).

Expected numbers are literals taken from the booklet, not recomputed with the
implementation's own formulas (booklet 4.7: independent worked fixtures).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fixture_version(database_url: str) -> str:
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    with session_factory()() as session:
        return seed_booklet_fixtures(session).dataset_version_id


def analysis(client, section: str, **params: str) -> dict:  # noqa: ANN001
    response = client.get(f"{API}/analysis/{section}", params={"data_mode": "synthetic", **params})
    assert response.status_code == 200, response.text
    return response.json()


def by_kind(payload: dict, kind: str) -> list[dict]:
    return [c for c in payload["calculations"] if c["kind"] == kind]


def one(payload: dict, kind: str) -> dict:
    [calc] = by_kind(payload, kind)
    return calc


def caveats(calc: dict) -> set[str]:
    return {c["code"] for c in calc["caveats"]}


# ------------------------------------------------------------------ Table 4.2 fixtures


def test_electricity_generation_growth_is_4_375_percent(anonymous, fixture_version) -> None:  # noqa: ANN001
    payload = analysis(anonymous, "electricity", dataset_version_id=fixture_version)
    assert one(payload, "absolute_change")["result"]["value"] == "2100"
    pct = one(payload, "percentage_change")
    assert Decimal(pct["result"]["value"]) == Decimal("4.375")  # stored unrounded
    assert pct["result"]["unit"]["code"] == "percent"
    assert [i["value"] for i in pct["inputs"]] == ["48000", "50100"]
    assert {i["unit"]["code"] for i in pct["inputs"]} == {"GWh"}
    assert all(i["indicator"]["code"] == "ELEC_GENERATION" for i in pct["inputs"])
    # Generation is never divided by subscribers as if it were consumption.
    per_sub = one(payload, "use_per_subscriber")
    assert per_sub["result"]["status"] == "unavailable"
    assert per_sub["reason"]["code"] == "component_not_published"
    assert [n["code"] for n in per_sub["notes"]] == ["generation_not_consumption"]


def test_water_consumption_growth_is_about_3_94_percent(anonymous, fixture_version) -> None:  # noqa: ANN001
    payload = analysis(anonymous, "water", dataset_version_id=fixture_version)
    assert one(payload, "absolute_change")["result"]["value"] == "13"
    pct = Decimal(one(payload, "percentage_change")["result"]["value"])
    assert pct.quantize(Decimal("0.000001")) == Decimal("3.939394")
    assert round(pct, 2) == Decimal("3.94")


def test_water_does_not_infer_leakage_source_mix_or_per_subscriber_use(
    anonymous, fixture_version
) -> None:  # noqa: ANN001
    payload = analysis(anonymous, "water", dataset_version_id=fixture_version)
    reasons = {
        c["id"]: c["reason"]["code"]
        for c in payload["calculations"]
        if c["result"]["status"] == "unavailable"
    }
    assert reasons["WATER:leakage"] == "leakage_not_inferred"
    assert reasons["WATER:source_composition"] == "no_source_breakdown"
    assert {c["reason"]["code"] for c in by_kind(payload, "use_per_subscriber")} == {
        "no_subscriber_series"
    }
    leakage = next(c for c in payload["calculations"] if c["id"] == "WATER:leakage")
    assert leakage["result"]["value"] is None
    assert leakage["reason"]["en"].startswith(
        "Production minus consumption is not calculated as leakage"
    )
    # Both series are shown as inputs so the reader sees what is being declined.
    assert {i["indicator"]["code"] for i in leakage["inputs"]} == {"WATER_CONSUMPTION"}


def test_food_balance_with_explicit_zero_stock_assumption(anonymous, fixture_version) -> None:  # noqa: ANN001
    payload = analysis(anonymous, "food_security", dataset_version_id=fixture_version)
    assert payload["assumptions"] == {"stock_assumption": "assumed_zero"}
    availability = one(payload, "apparent_availability")
    assert availability["result"]["value"] == "160000"
    assert availability["result"]["unit"]["code"] == "tonne"
    assert "stock_change_assumed_zero" in caveats(availability)
    roles = {i["role"]: i["value"] for i in availability["inputs"]}
    assert roles == {"production": "100000", "imports": "80000", "domestic_exports": "20000"}
    assert "stock change = 0 (declared assumption)" in availability["formula"]["en"]

    local = one(payload, "local_production_contribution")
    assert Decimal(local["result"]["value"]) == Decimal("62.5")
    assert "not_complete_food_security_measure" in caveats(local)

    gross = one(payload, "gross_import_contribution")
    assert Decimal(gross["result"]["value"]) == Decimal("50")
    assert "does_not_complement_production_ratio" in caveats(gross)
    [note] = gross["notes"]
    assert "62.5% + 50% = 112.5%" in note["en"] and "domestic exports (20,000)" in note["en"]


def test_unknown_stock_keeps_the_balance_but_labels_it_unadjusted(
    anonymous, fixture_version
) -> None:  # noqa: ANN001
    payload = analysis(
        anonymous, "food_security", dataset_version_id=fixture_version, stock_assumption="unknown"
    )
    availability = one(payload, "apparent_availability")
    assert availability["result"]["value"] == "160000"
    assert "stock_change_unknown_not_adjusted" in caveats(availability)


def test_known_stock_without_a_published_stock_change_is_unavailable(
    anonymous, fixture_version
) -> None:  # noqa: ANN001
    payload = analysis(
        anonymous, "food_security", dataset_version_id=fixture_version, stock_assumption="known"
    )
    availability = one(payload, "apparent_availability")
    assert availability["result"]["status"] == "unavailable"
    assert availability["result"]["value"] is None
    assert "stock_increase" in availability["notes"][0]["en"]
    assert by_kind(payload, "local_production_contribution") == []


def test_trade_partner_shares_balance_and_unit_values(anonymous, fixture_version) -> None:  # noqa: ANN001
    payload = analysis(anonymous, "trade", dataset_version_id=fixture_version)
    shares = one(payload, "largest_partner_share")
    assert Decimal(shares["result"]["value"]) == Decimal("60")
    assert {b["partner"]: Decimal(b["value"]) for b in shares["breakdown"]} == {
        "PARTNER_A": Decimal("60"),
        "PARTNER_B": Decimal("25"),
        "PARTNER_C": Decimal("15"),
    }
    partner_inputs = sorted(i["value"] for i in shares["inputs"] if i["role"] == "partner")
    assert partner_inputs == ["12000", "20000", "48000"]
    assert "concentration_not_disruption_probability" in caveats(shares)
    assert Decimal(one(payload, "sum_of_squared_shares")["result"]["value"]) == Decimal("0.445")

    balance = one(payload, "trade_balance")
    assert balance["result"]["value"] == "-28000000"
    assert {i["role"]: i["value"] for i in balance["inputs"]} == {
        "export_value": "12000000",
        "import_value": "40000000",
    }
    assert {"not_profit_or_loss", "nominal_value"} <= caveats(balance)
    assert "profit" not in balance["title"]["en"].lower()

    unit_values = {c["id"].rsplit(":", 1)[1]: c for c in by_kind(payload, "unit_value")}
    assert unit_values["import_unit_value"]["result"]["value"] == "500"
    assert unit_values["export_unit_value"]["result"]["value"] == "600"
    assert all("not_retail_price" in caveats(c) for c in unit_values.values())
    assert unit_values["import_unit_value"]["result"]["unit"]["code"] == "OMR/tonne"


# ------------------------------------------------------------------ guards on published data


@pytest.fixture
def manager(make_user, login):  # noqa: ANN001, ANN201
    return login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )


def publish(manager, *lines: str) -> str:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload_validate_approve(manager, source_id, csv_bytes(*lines))
    assert manager.post(f"{API}/imports/{imp['id']}/publish").status_code == 200
    return imp["version"]["id"]


def test_missing_previous_value_gives_a_missing_result_not_zero_growth(manager, anonymous) -> None:  # noqa: ANN001
    version = publish(
        manager,
        "WATER_PRODUCTION,OM,2020-01-01,2020-12-31,annual,million_m3,,,,",
        "WATER_PRODUCTION,OM,2021-01-01,2021-12-31,annual,million_m3,400,,,",
    )
    pct = one(analysis(anonymous, "water", dataset_version_id=version), "percentage_change")
    assert pct["result"] == {"status": "missing", "value": None, "unit": pct["result"]["unit"]}
    assert pct["reason"]["code"] == "input_missing"
    assert pct["inputs"][0]["value"] is None


def test_zero_previous_value_is_undefined_and_explained(manager, anonymous) -> None:  # noqa: ANN001
    version = publish(
        manager,
        "ELEC_CONSUMPTION,OM,2020-01-01,2020-12-31,annual,GWh,0,,,",
        "ELEC_CONSUMPTION,OM,2021-01-01,2021-12-31,annual,GWh,10,,,",
    )
    pct = one(analysis(anonymous, "electricity", dataset_version_id=version), "percentage_change")
    assert pct["result"]["status"] == "undefined" and pct["result"]["value"] is None
    assert pct["reason"]["code"] == "previous_value_zero"
    assert "undefined" in pct["reason"]["en"]


def test_non_positive_availability_blocks_the_ratios(manager, anonymous) -> None:  # noqa: ANN001
    version = publish(
        manager,
        "FOOD_PRODUCTION,OM,2030-01-01,2030-12-31,annual,tonne,100,RICE,,",
        "TRADE_QUANTITY,OM,2030-01-01,2030-12-31,annual,tonne,50,RICE,,import",
        "TRADE_QUANTITY,OM,2030-01-01,2030-12-31,annual,tonne,150,RICE,,domestic_export",
    )
    payload = analysis(anonymous, "food_security", dataset_version_id=version)
    assert one(payload, "apparent_availability")["result"]["value"] == "0"
    local = one(payload, "local_production_contribution")
    assert local["result"]["status"] == "not_calculated"
    assert local["reason"]["code"] == "non_positive_denominator"


def test_use_per_subscriber_needs_matching_coverage_and_period(manager, anonymous) -> None:  # noqa: ANN001
    version = publish(
        manager,
        "WATER_CONSUMPTION,OM,2022-01-01,2022-12-31,annual,million_m3,300,,,",
        "WATER_SUBSCRIBERS,OM,2022-01-01,2022-12-31,annual,subscriber,1000000,,,",
        "WATER_CONSUMPTION,OM,2023-01-01,2023-12-31,annual,million_m3,310,,,",
    )
    per_sub = {
        c["inputs"][0]["period_start"][:4]: c
        for c in by_kind(
            analysis(anonymous, "water", dataset_version_id=version), "use_per_subscriber"
        )
    }
    assert Decimal(per_sub["2022"]["result"]["value"]) == Decimal("0.0003")
    assert "not_efficiency_measure" in caveats(per_sub["2022"])
    assert per_sub["2023"]["reason"]["code"] == "no_subscriber_series"


def test_two_sources_for_the_same_component_are_not_merged_silently(manager, anonymous) -> None:  # noqa: ANN001
    line = "FOOD_PRODUCTION,OM,2031-01-01,2031-12-31,annual,tonne,{},TOMATOES,,"
    trade = [
        "TRADE_QUANTITY,OM,2031-01-01,2031-12-31,annual,tonne,10,TOMATOES,,import",
        "TRADE_QUANTITY,OM,2031-01-01,2031-12-31,annual,tonne,5,TOMATOES,,domestic_export",
    ]
    publish(manager, line.format(100), *trade)
    publish(manager, line.format(120))
    payload = analysis(
        anonymous,
        "food_security",
        commodity="TOMATOES",
        period_from="2031-01-01",
        period_to="2031-12-31",
    )
    availability = one(payload, "apparent_availability")
    assert availability["result"]["status"] == "unavailable"
    assert availability["reason"]["code"] == "conflicting_sources"


def test_annual_and_monthly_series_are_never_compared(manager, anonymous) -> None:  # noqa: ANN001
    version = publish(
        manager,
        "ELEC_PEAK_DEMAND,OM,2060-01-01,2060-12-31,annual,MW,5000,,,",
        "ELEC_PEAK_DEMAND,OM,2061-01-01,2061-12-31,annual,MW,5200,,,",
        "ELEC_PEAK_DEMAND,OM,2061-07-01,2061-07-31,monthly,MW,5100,,,",
    )
    payload = analysis(anonymous, "electricity", dataset_version_id=version)
    pct = by_kind(payload, "percentage_change")
    frequencies = sorted(sorted({i["frequency"] for i in c["inputs"]}) for c in pct)
    assert frequencies == [["annual"], ["monthly"]]  # one series each, never mixed
    annual = next(c for c in pct if c["inputs"][0]["frequency"] == "annual")
    assert Decimal(annual["result"]["value"]) == Decimal("4")
    monthly = next(c for c in pct if c["inputs"][0]["frequency"] == "monthly")
    assert monthly["reason"]["code"] == "no_comparable_period"


# ------------------------------------------------------------------ filters and exports


def test_filters_apply_to_calculations(anonymous, fixture_version) -> None:  # noqa: ANN001
    wheat = analysis(anonymous, "trade", dataset_version_id=fixture_version, commodity="WHEAT")
    assert wheat["calculations"] == [] and wheat["filters"]["commodity"] == "WHEAT"
    later = analysis(
        anonymous, "electricity", dataset_version_id=fixture_version, period_from="2002-01-01"
    )
    assert one(later, "percentage_change")["reason"]["code"] == "no_comparable_period"


def test_calculation_export_keeps_mode_assumption_and_values(anonymous, fixture_version) -> None:  # noqa: ANN001
    response = anonymous.get(
        f"{API}/analysis/food_security/export.csv",
        params={"data_mode": "synthetic", "dataset_version_id": fixture_version},
    )
    assert response.status_code == 200
    assert (
        "osrip-calculations-food_security-synthetic.csv" in response.headers["content-disposition"]
    )
    text = response.text
    assert text.startswith("# OSRIP calculations - SYNTHETIC DEMONSTRATION DATA")
    assert "assumptions=stock_assumption=assumed_zero" in text
    assert ",160000," in text and "Assumption: stock change is zero" in text  # T12


def test_verified_mode_never_reuses_synthetic_calculations(anonymous, fixture_version) -> None:  # noqa: ANN001
    response = anonymous.get(
        f"{API}/analysis/trade",
        params={"data_mode": "verified_source", "dataset_version_id": fixture_version},
    )
    assert response.json()["error"]["code"] == "data_mode_mismatch"
