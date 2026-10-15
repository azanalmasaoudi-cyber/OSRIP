"""Review cards, analyst review history and frozen reports.

Booklet 3.9, 3.12 and 3.13; acceptance evidence FR05, FR06, T07 and T12.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.domain.enums import Permission, Role
from tests.workflow_helpers import API, csv_bytes, upload_validate_approve

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fixture_version(database_url: str) -> str:
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    with session_factory()() as session:
        return seed_booklet_fixtures(session).dataset_version_id


@pytest.fixture
def analyst(make_user, login):  # noqa: ANN001, ANN201
    return login(make_user(Role.ANALYST))


def run_rules(client) -> dict:  # noqa: ANN001
    response = client.post(f"{API}/analysis-runs", json={"data_mode": "synthetic"})
    assert response.status_code == 201, response.text
    return response.json()


def fixture_cards(payload: dict, version: str) -> dict[str, dict]:
    """Cards whose inputs all come from the booklet fixture version, keyed by rule and section."""
    out = {}
    for card in payload["cards"]:
        if all(i["dataset_version"]["id"] == version for i in card["evidence"]["inputs"]):
            out[f"{card['rule_code']}:{card['section']}"] = card
    return out


# ------------------------------------------------------------------ rules


def test_rules_produce_transparent_cards_for_the_fixture(analyst, fixture_version) -> None:  # noqa: ANN001
    cards = fixture_cards(run_rules(analyst), fixture_version)
    assert {"R01:electricity", "R01:water", "R02:trade", "R03:trade"} <= set(cards)
    assert "R04:trade" not in cards  # the fixture partners reconcile exactly

    growth = cards["R01:electricity"]
    assert "4.38%" in growth["observation"]["en"] and "3%" in growth["observation"]["en"]
    assert (
        growth["evidence"]["rule"]["code"] == "R01"
        and growth["evidence"]["rule"]["threshold"] == "3%"
    )
    assert "not an official standard" in growth["evidence"]["rule"]["threshold_note"]["en"]
    assert [i["value"] for i in growth["evidence"]["inputs"]] == ["48000", "50100"]
    assert any(lim["code"] == "generation_not_demand" for lim in growth["evidence"]["limitations"])
    assert growth["next_steps"]["en"] and growth["status"] == "open"

    water = cards["R01:water"]
    assert any(lim["code"] == "no_leak_claim" for lim in water["evidence"]["limitations"])
    assert "leak" not in water["observation"]["en"].lower()

    concentration = cards["R02:trade"]
    assert "PARTNER_A supplies 60%" in concentration["observation"]["en"]
    assert "not a probability" in concentration["next_steps"]["en"]

    unit_values = cards["R03:trade"]
    assert "600" in unit_values["observation"]["en"] and "500" in unit_values["observation"]["en"]
    assert any(lim["code"] == "not_a_margin" for lim in unit_values["evidence"]["limitations"])


def test_thresholds_are_parameters_recorded_with_the_run(analyst, fixture_version) -> None:  # noqa: ANN001
    response = analyst.post(
        f"{API}/analysis-runs",
        json={
            "data_mode": "synthetic",
            "growth_threshold_pct": "5",
            "share_threshold_pct": "70",
            "unit_value_gap_pct": "25",
        },
    )
    payload = response.json()
    assert payload["run"]["parameters"]["growth_threshold_pct"] == "5"
    cards = fixture_cards(payload, fixture_version)
    assert not {"R01:electricity", "R01:water", "R02:trade", "R03:trade"} & set(cards)
    run_rules(analyst)  # restore default thresholds for later tests


def test_rules_need_the_analysis_permission(make_user, login, anonymous) -> None:  # noqa: ANN001
    assert (
        anonymous.post(f"{API}/analysis-runs", json={"data_mode": "synthetic"}).status_code == 401
    )
    viewer = login(make_user(Role.VIEWER))
    assert viewer.post(f"{API}/analysis-runs", json={"data_mode": "synthetic"}).status_code == 403


def test_data_quality_card_for_a_missing_input(analyst, make_user, login) -> None:  # noqa: ANN001
    manager = login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )
    from tests.workflow_helpers import register_synthetic_source

    source = register_synthetic_source(manager)
    imp = upload_validate_approve(
        manager,
        source,
        csv_bytes(
            "ELEC_PEAK_DEMAND,OM,2040-01-01,2040-12-31,annual,MW,,,,",
            "ELEC_PEAK_DEMAND,OM,2041-01-01,2041-12-31,annual,MW,5000,,,",
        ),
    )
    manager.post(f"{API}/imports/{imp['id']}/publish")
    cards = fixture_cards(run_rules(analyst), imp["version"]["id"])
    r04 = cards["R04:electricity"]
    assert "missing" in r04["observation"]["en"].lower()
    assert "Withhold the affected comparison" in r04["next_steps"]["en"]


# ------------------------------------------------------------------ review history


def test_analyst_reviews_are_appended_and_the_latest_is_the_status(
    analyst, anonymous, make_user, login, fixture_version
) -> None:  # noqa: ANN001
    card = fixture_cards(run_rules(analyst), fixture_version)["R02:trade"]
    first = analyst.post(
        f"{API}/recommendations/{card['id']}/reviews",
        json={"status": "under_review", "reason": "Checking contract context."},
    )
    assert first.status_code == 201
    second = analyst.post(
        f"{API}/recommendations/{card['id']}/reviews",
        json={"status": "explained", "reason": "Fictional partners; demonstration only."},
    )
    history = second.json()
    assert [h["status"] for h in history] == ["under_review", "explained"]
    assert history[0]["reason"] == "Checking contract context."

    public = anonymous.get(
        f"{API}/recommendations", params={"data_mode": "synthetic", "section": "trade"}
    ).json()
    listed = next(c for c in public["cards"] if c["id"] == card["id"])
    assert listed["status"] == "explained" and listed["review_count"] == 2
    # Review notes are protected; the calculation behind the card is unchanged.
    assert anonymous.get(f"{API}/recommendations/{card['id']}/reviews").status_code == 401
    viewer = login(make_user(Role.VIEWER))
    assert viewer.get(f"{API}/recommendations/{card['id']}/reviews").status_code == 403
    assert (
        viewer.post(
            f"{API}/recommendations/{card['id']}/reviews",
            json={"status": "dismissed", "reason": "x"},
        ).status_code
        == 403
    )
    assert Decimal(listed["evidence"]["result"]["value"]) == Decimal("60")


def test_review_needs_a_valid_status_and_reason(analyst, fixture_version) -> None:  # noqa: ANN001
    card = fixture_cards(run_rules(analyst), fixture_version)["R01:water"]
    bad = analyst.post(
        f"{API}/recommendations/{card['id']}/reviews", json={"status": "open", "reason": "x"}
    )
    assert bad.status_code == 422
    blank = analyst.post(
        f"{API}/recommendations/{card['id']}/reviews", json={"status": "dismissed", "reason": " "}
    )
    assert blank.json()["error"]["code"] == "reason_required"


# ------------------------------------------------------------------ reports


def create_report(client, fixture_version: str, **extra) -> dict:  # noqa: ANN001, ANN003
    body = {
        "title": "Food balance - synthetic fixture",
        "data_mode": "synthetic",
        "section": "food_security",
        "filters": {"commodity": "SYNTH_COMMODITY", "dataset_version_id": fixture_version},
        **extra,
    }
    response = client.post(f"{API}/reports", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_report_freezes_inputs_and_survives_a_later_publication(
    analyst, make_user, login, db, fixture_version
) -> None:  # noqa: ANN001
    report = create_report(analyst, fixture_version)
    content = analyst.get(f"{API}/reports/{report['id']}").json()["content"]
    availability = next(c for c in content["calculations"] if c["kind"] == "apparent_availability")
    assert availability["result"]["value"] == "160000"
    assert content["assumptions"] == {"stock_assumption": "assumed_zero"}
    assert content["filters"] == {
        "commodity": "SYNTH_COMMODITY",
        "dataset_version_id": fixture_version,
    }
    assert content["label"].startswith("SYNTHETIC DEMONSTRATION DATA")
    assert [s["id"] for s in content["sources"]] == [fixture_version]
    indicators = {s["indicator"]["code"] for s in content["series"]}
    assert indicators == {
        "FOOD_PRODUCTION",
        "TRADE_QUANTITY",
    }  # the report shows every input it used

    # The database refuses to alter a generated report.
    with pytest.raises(DBAPIError, match="frozen"), db.begin():
        db.execute(
            text("UPDATE report SET content = '{}'::jsonb WHERE id = :id"), {"id": report["id"]}
        )


def test_report_keeps_its_snapshot_after_a_revision_is_published(
    analyst, make_user, login, anonymous
) -> None:  # noqa: ANN001
    from tests.workflow_helpers import register_synthetic_source

    manager = login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )
    source = register_synthetic_source(manager)
    rows = [
        "TRADE_QUANTITY,OM,2050-01-01,2050-12-31,annual,tonne,10,WHEAT,,import",
        "TRADE_QUANTITY,OM,2050-01-01,2050-12-31,annual,tonne,5,WHEAT,,domestic_export",
    ]
    v1 = upload_validate_approve(
        manager,
        source,
        csv_bytes("FOOD_PRODUCTION,OM,2050-01-01,2050-12-31,annual,tonne,100,WHEAT,,", *rows),
        "v1",
    )
    manager.post(f"{API}/imports/{v1['id']}/publish")
    filters = {"commodity": "WHEAT", "period_from": "2050-01-01", "period_to": "2050-12-31"}
    report = analyst.post(
        f"{API}/reports",
        json={
            "title": "Wheat 2050",
            "data_mode": "synthetic",
            "section": "food_security",
            "filters": filters,
        },
    ).json()

    v2 = upload_validate_approve(
        manager,
        source,
        csv_bytes("FOOD_PRODUCTION,OM,2050-01-01,2050-12-31,annual,tonne,200,WHEAT,,", *rows),
        "v2",
    )
    manager.post(f"{API}/imports/{v2['id']}/publish")

    live = anonymous.get(
        f"{API}/analysis/food_security", params={"data_mode": "synthetic", **filters}
    ).json()
    live_value = next(c for c in live["calculations"] if c["kind"] == "apparent_availability")[
        "result"
    ]["value"]
    frozen = analyst.get(f"{API}/reports/{report['id']}").json()["content"]
    frozen_value = next(c for c in frozen["calculations"] if c["kind"] == "apparent_availability")[
        "result"
    ]["value"]
    assert (frozen_value, live_value) == ("105", "205")  # 100 + 10 - 5 then; 200 + 10 - 5 now
    assert [s["id"] for s in frozen["sources"]] == [v1["version"]["id"]]


def test_report_export_keeps_label_filters_assumptions_and_versions(
    analyst, fixture_version
) -> None:  # noqa: ANN001
    report = create_report(analyst, fixture_version, stock_assumption="unknown")
    response = analyst.get(f"{API}/reports/{report['id']}/export.csv")
    assert response.status_code == 200
    assert "-synthetic.csv" in response.headers["content-disposition"]
    text_ = response.text
    assert text_.startswith("# OSRIP report - SYNTHETIC DEMONSTRATION DATA")
    assert "assumptions=stock_assumption=unknown" in text_
    assert "commodity=SYNTH_COMMODITY" in text_ and "version fixtures-v1" in text_
    assert ",160000," in text_ and "not adjusted for stocks" in text_


def test_private_reports_are_hidden_and_published_ones_are_shared(
    analyst, anonymous, make_user, login, fixture_version
) -> None:  # noqa: ANN001
    report = create_report(analyst, fixture_version)
    other = login(make_user(Role.ANALYST))
    assert anonymous.get(f"{API}/reports/{report['id']}").status_code == 404
    assert other.get(f"{API}/reports/{report['id']}").status_code == 404
    assert (
        other.put(
            f"{API}/reports/{report['id']}/visibility", json={"visibility": "published"}
        ).status_code
        == 404
    )  # only the owner
    assert (
        analyst.put(
            f"{API}/reports/{report['id']}/visibility", json={"visibility": "published"}
        ).status_code
        == 200
    )
    shared = anonymous.get(f"{API}/reports/{report['id']}")
    assert shared.status_code == 200 and shared.json()["owned"] is False
    assert any(r["id"] == report["id"] for r in anonymous.get(f"{API}/reports").json())


def test_report_creation_needs_permission_and_known_filters(
    make_user, login, analyst, fixture_version
) -> None:  # noqa: ANN001
    viewer = login(make_user(Role.VIEWER))
    assert (
        viewer.post(
            f"{API}/reports", json={"title": "x" * 5, "data_mode": "synthetic", "section": "trade"}
        ).status_code
        == 403
    )
    bad = analyst.post(
        f"{API}/reports",
        json={
            "title": "Bad filter",
            "data_mode": "synthetic",
            "section": "trade",
            "filters": {"colour": "red"},
        },
    )
    assert bad.json()["error"]["code"] == "unknown_filter"
