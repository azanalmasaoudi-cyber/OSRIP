"""Administrative registry, statistical coverage by area and recorded forecast runs.

Registry expectations are literals from the cited references (Ministry of Finance
listing: 11 governorates, 61 wilayats; Ministry of Interior / Oman News Agency 2022:
Al Jabal Al Akhdar and Sinaw, total 63), not read back from the migration.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    observations,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration

ISO_CODES = {
    "OM-DA", "OM-BU", "OM-WU", "OM-ZA", "OM-BJ", "OM-SJ",
    "OM-MA", "OM-MU", "OM-BS", "OM-SS", "OM-ZU",
}  # fmt: skip
WILAYATS_PER_GOVERNORATE = {
    "OM-MU": 4, "OM-BU": 3, "OM-BS": 6, "OM-BJ": 6, "OM-MA": 6, "OM-ZA": 3,
    "OM-DA": 9, "OM-SS": 7, "OM-SJ": 5, "OM-WU": 4, "OM-ZU": 10,
}  # fmt: skip


@pytest.fixture(scope="module")
def registry(database_url: str) -> dict:
    from fastapi.testclient import TestClient

    from app.main import create_app

    response = TestClient(create_app()).get(f"{API}/areas")
    assert response.status_code == 200, response.text
    return response.json()


def by_level(registry: dict, level: str) -> list[dict]:
    return [a for a in registry["areas"] if a["level"] == level]


# ------------------------------------------------------------------ registry


def test_registry_has_11_governorates_and_63_wilayats(registry: dict) -> None:
    governorates = by_level(registry, "governorate")
    wilayats = by_level(registry, "wilayat")
    assert len(governorates) == 11 and len(wilayats) == 63
    assert {g["code"] for g in governorates} == ISO_CODES
    assert all(g["iso_3166_2"] == g["code"] and g["parent_code"] == "OM" for g in governorates)
    counts: dict[str, int] = {}
    for w in wilayats:
        counts[w["parent_code"]] = counts.get(w["parent_code"], 0) + 1
    assert counts == WILAYATS_PER_GOVERNORATE
    v = registry["verification"]
    assert v["complete"] is True
    assert (v["expected_governorates"], v["expected_wilayats"]) == (11, 63)
    assert (v["found_governorates"], v["found_wilayats"]) == (11, 63)


def test_2022_wilayats_have_their_governorates_and_sources(registry: dict) -> None:
    areas = {a["code"]: a for a in registry["areas"]}
    akhdar, sinaw = areas["OM-DA-09"], areas["OM-SS-07"]
    assert (akhdar["name_en"], akhdar["name_ar"], akhdar["parent_code"]) == (
        "Al Jabal Al Akhdar",
        "الجبل الأخضر",
        "OM-DA",
    )
    assert (sinaw["name_en"], sinaw["name_ar"], sinaw["parent_code"]) == ("Sinaw", "سناو", "OM-SS")
    for area in (akhdar, sinaw):
        assert {r["code"] for r in area["references"]} == {
            "MOI_2022_NEW_WILAYATS",
            "ONA_2022_NEW_WILAYATS",
        }
        assert "2022" in area["note_en"]


def test_every_entry_is_sourced_for_existence_names_and_parent(registry: dict) -> None:
    refs = {r["code"] for r in registry["references"]}
    for area in by_level(registry, "governorate") + by_level(registry, "wilayat"):
        supported = {s for r in area["references"] for s in r["supports"]}
        assert {"existence", "name_en", "name_ar", "parent"} <= supported, area["code"]
        assert {r["code"] for r in area["references"]} <= refs
        assert area["verified_on"] == "2026-09-25"
        assert area["name_en"].strip() and area["name_ar"].strip()
    for r in registry["references"]:
        assert r["url"].startswith("https://") and r["accessed_on"] == "2026-09-25"


def test_codes_are_unique_and_osrip_codes_are_labelled(registry: dict) -> None:
    codes = [a["code"] for a in registry["areas"]]
    assert len(codes) == len(set(codes))
    for w in by_level(registry, "wilayat"):
        assert w["code_authority"] == "osrip" and w["iso_3166_2"] is None
        assert w["code"].startswith(w["parent_code"] + "-")


def test_registry_carries_no_coordinates_or_geometry(registry: dict) -> None:
    assert registry["geometry"]["available"] is False
    forbidden = {"lat", "lon", "lng", "latitude", "longitude", "centroid", "geometry", "bbox"}
    for area in registry["areas"]:
        assert not forbidden & set(area)


def test_hierarchy_is_enforced_by_the_database(db) -> None:  # noqa: ANN001
    with pytest.raises(DBAPIError, match="has a parent of level national"), db.begin():
        db.execute(
            text(
                "INSERT INTO area (code, level, parent_id, name_en, name_ar, verified_on) "
                "SELECT 'TEST-W', 'wilayat', id, 'x', 'x', DATE '2026-09-25' FROM area "
                "WHERE code = 'OM'"
            )
        )
    with pytest.raises(DBAPIError, match="ck_area_admin_level_is_verified"), db.begin():
        db.execute(
            text(
                "INSERT INTO area (code, level, parent_id, name_en, name_ar) "
                "SELECT 'TEST-G', 'governorate', id, 'x', 'x' FROM area WHERE code = 'OM'"
            )
        )
    with pytest.raises(DBAPIError, match="append-only"), db.begin():
        db.execute(text("UPDATE area_registry_verification SET expected_wilayats = 61"))


# ------------------------------------------------------------------ statistical coverage


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


def test_coverage_counts_only_the_exact_area_and_missing_is_not_zero(manager, anonymous) -> None:  # noqa: ANN001
    version = publish(
        manager,
        "WATER_PRODUCTION,OM-MA,2020-01-01,2020-12-31,annual,million_m3,,,,",
        "WATER_PRODUCTION,OM-MA,2021-01-01,2021-12-31,annual,million_m3,40,,,",
    )
    response = anonymous.get(f"{API}/areas/coverage", params={"data_mode": "synthetic"})
    assert response.status_code == 200
    cov = response.json()["areas"]
    muscat = cov["OM-MA"]
    water = next(i for i in muscat["indicators"] if i["code"] == "WATER_PRODUCTION")
    assert water["observations"] >= 2 and water["values"] >= 1
    assert muscat["missing"] >= 1
    # Nothing is inherited downwards or from the national total.
    assert "OM-MA-01" not in cov and "OM-ZU" not in cov
    # The verified mode never shows synthetic coverage.
    verified = anonymous.get(f"{API}/areas/coverage", params={"data_mode": "verified_source"})
    assert "OM-MA" not in verified.json()["areas"] or all(
        i["code"] != "WATER_PRODUCTION" or i["observations"] == 0
        for i in verified.json()["areas"]["OM-MA"]["indicators"]
    )
    payload = observations(
        anonymous, data_mode="synthetic", area="OM-MA", dataset_version_id=version
    )
    assert {s["area"]["code"] for s in payload["series"]} == {"OM-MA"}
    assert [o["value"] for s in payload["series"] for o in s["observations"]] == [None, "40"]


# ------------------------------------------------------------------ forecasting

ELIGIBLE_VALUES = [100, 104, 103, 110, 112, 115, 113, 120, 126, 125, 131, 138]


@pytest.fixture
def analyst(make_user, login):  # noqa: ANN001, ANN201
    return login(make_user(Role.ANALYST))


def eligibility(client) -> dict:  # noqa: ANN001
    response = client.get(f"{API}/forecast/eligibility", params={"data_mode": "synthetic"})
    assert response.status_code == 200, response.text
    return response.json()


def series_for(payload: dict, version: str) -> dict:
    [row] = [s for s in payload["series"] if s["dataset_version"]["id"] == version]
    return row


def test_booklet_fixture_series_are_ineligible_and_the_run_is_withheld(analyst, anonymous) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    with session_factory()() as session:
        version = seed_booklet_fixtures(session).dataset_version_id
    payload = eligibility(anonymous)
    assert payload["demonstration_only"] is True
    rows = [s for s in payload["series"] if s["dataset_version"]["id"] == version]
    assert rows and all(not r["eligible"] for r in rows)
    assert all("insufficient_history" in {x["code"] for x in r["reasons"]} for r in rows)

    target = next(r for r in rows if r["indicator"]["code"] == "ELEC_GENERATION")
    response = analyst.post(
        f"{API}/forecast-runs", json={"data_mode": "synthetic", "series_id": target["series_id"]}
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "withheld"
    assert "needs at least 12" in run["status_reason"]
    assert run["predictions"] == [] and run["metrics"] == {} and run["comparison"] is None
    listed = anonymous.get(f"{API}/forecast-runs", params={"data_mode": "synthetic"}).json()
    assert run["id"] in {r["id"] for r in listed}


def test_eligible_synthetic_series_records_predictions_errors_and_metrics(
    manager, analyst, anonymous
) -> None:  # noqa: ANN001
    version = publish(
        manager,
        *(
            f"ELEC_GENERATION,OM-BS,{2008 + i}-01-01,{2008 + i}-12-31,annual,GWh,{v},,,"
            for i, v in enumerate(ELIGIBLE_VALUES)
        ),
    )
    row = series_for(eligibility(anonymous), version)
    assert row["eligible"] and row["usable_observations"] == 12
    assert row["area"]["code"] == "OM-BS"

    response = analyst.post(
        f"{API}/forecast-runs", json={"data_mode": "synthetic", "series_id": row["series_id"]}
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "succeeded"
    assert run["demonstration_only"] is True
    assert "Not a validated forecast for Oman" in run["demonstration_label"]["en"]
    d = run["definition"]
    assert (d["horizon_steps"], d["test_size"], d["min_training"]) == (1, 4, 8)
    assert d["held_out_periods"] == ["2016-01-01", "2017-01-01", "2018-01-01", "2019-01-01"]
    assert d["interval_method"] == "none"

    preds = run["predictions"]
    assert len(preds) == 8
    base = [p for p in preds if p["model"] == "baseline_last_value"]
    cand = [p for p in preds if p["model"] == "candidate_linear_trend"]
    assert [p["target_period_start"] for p in base] == [p["target_period_start"] for p in cand]
    assert [p["predicted"] for p in base] == ["120", "126", "125", "131"]
    assert [p["error"] for p in base] == ["6", "-1", "6", "7"]
    for p in preds:
        assert p["training_end"] < p["target_period_start"]
        assert Decimal(p["actual"]) - Decimal(p["predicted"]) == Decimal(p["error"])
        assert p["interval_lower"] is None and p["interval_upper"] is None
    assert abs(Decimal(cand[0]["predicted"]) - Decimal(851) / Decimal(7)) < Decimal("1e-20")

    m = run["metrics"]["baseline_last_value"]
    assert m["n"] == 4 and Decimal(m["mae"]) == 5
    assert Decimal(m["rmse"]) == Decimal("30.5").sqrt()
    assert run["comparison"]["same_dates"] is True and run["comparison"]["n"] == 4

    again = anonymous.get(f"{API}/forecast-runs/{run['id']}").json()
    assert again["predictions"] == preds and again["metrics"] == run["metrics"]


def test_predictions_are_append_only(db) -> None:  # noqa: ANN001
    with pytest.raises(DBAPIError, match="append-only"), db.begin():
        db.execute(text("DELETE FROM forecast_prediction"))


def test_running_a_forecast_needs_the_analysis_permission(make_user, login, anonymous) -> None:  # noqa: ANN001
    body = {"data_mode": "synthetic", "series_id": "x"}
    assert anonymous.post(f"{API}/forecast-runs", json=body).status_code in (401, 403)
    viewer = login(make_user(Role.VIEWER))
    assert viewer.post(f"{API}/forecast-runs", json=body).status_code == 403


def test_unknown_series_is_refused(analyst) -> None:  # noqa: ANN001
    response = analyst.post(
        f"{API}/forecast-runs", json={"data_mode": "synthetic", "series_id": "nope"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_series"


def test_no_published_series_gives_forecast_unavailable(db, monkeypatch) -> None:  # noqa: ANN001
    from app.domain.enums import DataMode
    from app.services import forecasting

    monkeypatch.setattr(forecasting, "_evaluated", lambda session, mode: [])
    with db.begin():
        payload = forecasting.eligibility(db, DataMode.VERIFIED_SOURCE)
    assert payload["status"] == "unavailable"
    assert payload["summary"]["code"] == "no_published_series"
    assert payload["demonstration_only"] is False
