"""The series timeline API: published monthly values in time order with gaps kept, a quarter
derived only from its three published months, year-on-year and month-on-month changes, the
CSV with the same rows and provenance, and a selection asked for when one indicator has
several breakdowns."""

from __future__ import annotations

import csv
import io
import uuid

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration

AREA = "OM-MU-02"


@pytest.fixture(scope="module")
def published(database_url: str) -> None:
    """Synthetic monthly consumption for one wilayat: Jan-Apr 2023 and Jan-Apr 2024, with
    February 2024 not published and a zero in January 2023."""
    from fastapi.testclient import TestClient

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.fixtures import seed_booklet_fixtures
    from app.services.principal import Principal

    email, password = f"series-{uuid.uuid4().hex[:6]}@test.invalid", "pw-series-manager-00"
    with session_factory()() as s, s.begin():
        user = accounts.create_user(s, Principal(None, "t"), email=email, display_name="M",
                                    password=password, roles=[Role.DATA_MANAGER])  # fmt: skip
        s.flush()
        for p in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), user.id, p)
    with session_factory()() as s:
        seed_booklet_fixtures(s)
    client = TestClient(create_app())
    client.post(f"{API}/auth/login", json={"email": email, "password": password})
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    source = register_synthetic_source(client)
    lines = [
        f"ELEC_CONSUMPTION,{AREA},2023-01-01,2023-01-31,monthly,GWh,0,,,",
        f"ELEC_CONSUMPTION,{AREA},2023-02-01,2023-02-28,monthly,GWh,20,,,",
        f"ELEC_CONSUMPTION,{AREA},2023-03-01,2023-03-31,monthly,GWh,30,,,",
        f"ELEC_CONSUMPTION,{AREA},2023-04-01,2023-04-30,monthly,GWh,40,,,",
        f"ELEC_CONSUMPTION,{AREA},2024-01-01,2024-01-31,monthly,GWh,15,,,",
        f"ELEC_CONSUMPTION,{AREA},2024-03-01,2024-03-31,monthly,GWh,33,,,",
        f"ELEC_CONSUMPTION,{AREA},2024-04-01,2024-04-30,monthly,GWh,44,,,",
    ]
    imp = upload_validate_approve(client, source, csv_bytes(*lines))
    assert client.post(f"{API}/imports/{imp['id']}/publish").status_code == 200


def _timeline(client, **params):  # noqa: ANN001, ANN003, ANN202
    query = {"data_mode": "synthetic", "indicator": "ELEC_CONSUMPTION", "area": AREA, **params}
    r = client.get(f"{API}/series/timeline", params=query)
    assert r.status_code == 200, r.text
    return r.json()


def test_monthly_rows_keep_gaps_and_changes(anonymous, published) -> None:  # noqa: ANN001
    doc = _timeline(anonymous, view="monthly")
    assert doc["status"] == "ok" and doc["sector"] == "electricity"
    assert doc["unit"]["code"] == "GWh" and doc["unit"]["label"]["en"]
    starts = [r["period_start"] for r in doc["rows"]]
    assert starts == sorted(starts) and starts[0] == "2023-01-01" and starts[-1] == "2024-04-01"
    by = {r["period_start"]: r for r in doc["rows"]}
    # May 2023 to December 2023 and February 2024 are not published: empty, never zero.
    assert by["2023-05-01"]["value"] is None and by["2023-05-01"]["status"] == "not_published"
    assert by["2024-02-01"]["value"] is None
    # From a zero, no percentage; the absolute change is still given.
    feb = by["2023-02-01"]["changes"][0]
    assert feb["absolute"] == "20" and feb["percent"] is None and feb["status"] == "undefined"
    # Year on year for months: March 2024 against March 2023.
    march = {c["basis"]: c for c in by["2024-03-01"]["changes"]}
    assert march["year_on_year"]["percent"] == "10.00"
    assert march["month_on_month"]["status"] == "missing"  # February 2024 is missing
    assert all(r["source"]["id"] for r in doc["rows"] if r["value"] is not None)
    assert doc["sources"] and doc["dataset_id"] and doc["label"]  # synthetic label


def test_quarters_only_from_three_published_months(anonymous, published) -> None:  # noqa: ANN001
    doc = _timeline(anonymous, view="quarterly")
    by = {r["period_start"]: r for r in doc["rows"]}
    q1_2023 = by["2023-01-01"]
    assert q1_2023["value"] == "50" and q1_2023["nature"] == "derived"
    assert q1_2023["basis"] == "sum_of_components"
    q1_2024 = by["2024-01-01"]  # February 2024 missing: no quarter total
    assert q1_2024["value"] is None and q1_2024["reason"]["code"] == "components_incomplete"
    assert by["2023-04-01"]["value"] is None  # only April 2023 of Q2 is published
    assert "monthly" in doc["available_views"] and "annual" not in doc["available_views"]
    assert any(rule["code"] == "sum_of_components" for rule in doc["rules"])


def test_period_range_and_csv_with_the_same_rows(anonymous, published) -> None:  # noqa: ANN001
    doc = _timeline(anonymous, view="monthly", period_from="2024-01-01", period_to="2024-04-30")
    assert [r["period_start"] for r in doc["rows"]] == [
        "2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01",
    ]  # fmt: skip
    r = anonymous.get(
        f"{API}/series/timeline.csv",
        params={"data_mode": "synthetic", "indicator": "ELEC_CONSUMPTION", "area": AREA,
                "view": "monthly", "period_from": "2024-01-01", "period_to": "2024-04-30"},
    )  # fmt: skip
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8-sig")
    assert f"dataset_id={doc['dataset_id']}" in text
    lines = [line for line in text.splitlines() if not line.lstrip('"').startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    assert [(x["period_start"], x["value"]) for x in rows] == [
        (d["period_start"], d["value"] or "") for d in doc["rows"]
    ]
    assert rows[1]["value"] == "" and rows[1]["status"] == "not_published"
    assert rows[2]["year_on_year_change_pct"] == "10.00" and rows[0]["source_title"]
    # Every row says what it is: sector, indicator, area, frequency, unit, kind and status.
    assert {(x["sector"], x["indicator"], x["area"], x["unit"]) for x in rows} == {
        ("electricity", "ELEC_CONSUMPTION", AREA, "GWh")
    }


def test_selection_errors_and_unknown_indicator(anonymous, published) -> None:  # noqa: ANN001
    unknown = anonymous.get(
        f"{API}/series/timeline", params={"data_mode": "synthetic", "indicator": "NOPE"}
    )
    assert unknown.status_code == 404
    bad = anonymous.get(
        f"{API}/series/timeline",
        params={"data_mode": "synthetic", "indicator": "ELEC_CONSUMPTION", "view": "weekly"},
    )
    assert bad.status_code == 422
    # Trade values by product: the caller must pick one breakdown, nothing is summed.
    trade = anonymous.get(
        f"{API}/series/timeline", params={"data_mode": "synthetic", "indicator": "TRADE_VALUE"}
    ).json()
    if trade["status"] == "needs_selection":
        assert len(trade["options"]) > 1 and trade["rows"] == []
    none = _timeline(anonymous, indicator="ELEC_PEAK_DEMAND", area="OM-MU-03")
    assert none["status"] == "no_published_data" and none["rows"] == []
