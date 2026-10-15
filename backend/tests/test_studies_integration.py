"""Deterministic studies over published synthetic observations (booklet 3.25, 3.27, 3.29).

Each builder is checked against hand-calculated values: trend changes against the period
immediately before (never bridged across a gap), compound growth, ranked governorates with
missing kept apart from "no value", seasonal heatmaps, import dependence, partner shares,
data quality, a hypothetical scenario, withheld forecasts and a programme record that does
not claim impact. Runs are stored, exported and reproduced; the assistant's ``run_study``
tool stores the cited study with its message.

The data here uses areas, years and a commodity frame that no other module publishes
(Al Wusta and A'Dhahirah in the 1990s, wheat in 1990), so later modules that compare the
latest governorate year are unaffected.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def setup(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "research_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    ratelimit.reset()


@pytest.fixture(scope="module")
def published(database_url: str) -> None:
    """Publish this module's synthetic observations once."""
    from fastapi.testclient import TestClient

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.principal import Principal

    email, password = f"st-manager-{uuid.uuid4().hex[:6]}@test.invalid", "pw-st-manager-0000"
    with session_factory()() as s, s.begin():
        user = accounts.create_user(
            s, Principal(None, "t"), email=email, display_name="M", password=password,
            roles=[Role.DATA_MANAGER],
        )  # fmt: skip
        s.flush()
        for p in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), user.id, p)
    manager = TestClient(create_app())
    manager.post(f"{API}/auth/login", json={"email": email, "password": password})
    manager.headers["X-CSRF-Token"] = manager.cookies["osrip_csrf"]
    lines = [
        # Al Wusta generation: 1993 is missing in the source.
        "ELEC_GENERATION,OM-WU,1991-01-01,1991-12-31,annual,GWh,100,,,",
        "ELEC_GENERATION,OM-WU,1992-01-01,1992-12-31,annual,GWh,110,,,",
        "ELEC_GENERATION,OM-WU,1993-01-01,1993-12-31,annual,GWh,,,,",
        "ELEC_GENERATION,OM-WU,1994-01-01,1994-12-31,annual,GWh,121,,,",
        # A'Dhahirah generation: 1992 is not published at all.
        "ELEC_GENERATION,OM-ZA,1991-01-01,1991-12-31,annual,GWh,10,,,",
        "ELEC_GENERATION,OM-ZA,1993-01-01,1993-12-31,annual,GWh,12,,,",
        # Water production by governorate in 1990, and Al Wusta by month.
        "WATER_PRODUCTION,OM-WU,1990-01-01,1990-12-31,annual,million_m3,50,,,",
        "WATER_PRODUCTION,OM-ZA,1990-01-01,1990-12-31,annual,million_m3,80,,,",
        "WATER_PRODUCTION,OM-BU,1990-01-01,1990-12-31,annual,million_m3,,,,",
        "WATER_PRODUCTION,OM-WU,1990-01-01,1990-01-31,monthly,million_m3,4,,,",
        "WATER_PRODUCTION,OM-WU,1990-02-01,1990-02-28,monthly,million_m3,5,,,",
        "WATER_PRODUCTION,OM-WU,1990-03-01,1990-03-31,monthly,million_m3,9,,,",
        "WATER_PRODUCTION,OM-WU,1990-04-01,1990-04-30,monthly,million_m3,,,,",
        # Wheat in 1990: production, trade totals and import partners.
        "FOOD_PRODUCTION,OM,1990-01-01,1990-12-31,annual,tonne,100,WHEAT,,",
        "TRADE_QUANTITY,OM,1990-01-01,1990-12-31,annual,tonne,300,WHEAT,,import",
        "TRADE_QUANTITY,OM,1990-01-01,1990-12-31,annual,tonne,20,WHEAT,,domestic_export",
        "TRADE_QUANTITY,OM,1990-01-01,1990-12-31,annual,tonne,150,WHEAT,PARTNER_A,import",
        "TRADE_QUANTITY,OM,1990-01-01,1990-12-31,annual,tonne,100,WHEAT,PARTNER_B,import",
        "TRADE_QUANTITY,OM,1990-01-01,1990-12-31,annual,tonne,50,WHEAT,PARTNER_C,import",
    ]
    source = register_synthetic_source(manager)
    imp = upload_validate_approve(manager, source, csv_bytes(*lines))
    r = manager.post(f"{API}/imports/{imp['id']}/publish")
    assert r.status_code == 200, r.text


def run(client, kind: str, **params: Any) -> dict[str, Any]:  # noqa: ANN001
    r = client.post(
        f"{API}/studies", json={"kind": kind, "data_mode": "synthetic", "params": params}
    )
    assert r.status_code == 201, r.text
    return r.json()


def rows_by(study: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {r[key]: r for r in study["table"]["rows"]}


# ------------------------------------------------------------------ builders


def test_trend_compares_only_with_the_period_immediately_before(anonymous, published) -> None:  # noqa: ANN001
    body = run(anonymous, "trend", indicator="ELEC_GENERATION", area="OM-WU")
    study = body["study"]
    assert study["status"] == "ok" and study["schema"] == "osrip.study/1"
    rows = rows_by(study, "period")
    assert rows["1991"]["change_pct"] is None
    assert Decimal(rows["1992"]["change_pct"]) == Decimal("10")
    assert rows["1993"]["value"] is None and rows["1993"]["status"] == "missing_in_source"
    # 1994 is not compared with 1992 across the missing year.
    assert rows["1994"]["change_pct"] is None
    assert rows["1994"]["note"] == "previous_period_missing"
    labels = [c["label"]["en"] for c in study["cards"]]
    assert labels == ["Latest published value"] and study["cards"][0]["value"] == "121"
    assert study["charts"][0]["series"][0]["nature"] == "observed"
    assert all(e["id"].startswith("S") and e["dataset_version"] for e in study["evidence"])
    assert len(body["sha256"]) == 64

    gap = run(anonymous, "trend", indicator="ELEC_GENERATION", area="OM-ZA")["study"]
    rows = rows_by(gap, "period")
    assert rows["1993"]["change_pct"] is None
    assert rows["1993"]["note"] == "previous_period_not_published"


def test_growth_is_the_compound_rate_between_two_complete_years(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "growth", indicator="ELEC_GENERATION", area="OM-WU",
                from_year=1991, to_year=1994)["study"]  # fmt: skip
    assert study["status"] == "ok"
    value = Decimal(study["cards"][0]["value"])
    assert abs(value - Decimal("6.560")) < Decimal("0.001")  # (121/100)^(1/3) − 1
    assert study["cards"][0]["nature"] == "calculated"
    assert "6.56" in study["findings"][0]["text"]["en"]
    assert "6.56" in study["findings"][0]["text"]["ar"]

    missing = run(anonymous, "growth", indicator="ELEC_GENERATION", area="OM-WU",
                  from_year=1991, to_year=1993)["study"]  # fmt: skip
    assert missing["status"] == "not_available" and missing["cards"] == []

    backwards = run(anonymous, "growth", indicator="ELEC_GENERATION", area="OM-WU",
                    from_year=1994, to_year=1991)["study"]  # fmt: skip
    assert backwards["status"] == "not_available"


def test_regions_are_ranked_and_missing_is_kept_apart_from_no_value(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "compare_regions", indicator="WATER_PRODUCTION",
                period_start="1990-01-01")["study"]  # fmt: skip
    assert study["status"] == "ok"
    rows = study["table"]["rows"]
    assert [r["value"] for r in rows[:2]] == ["80", "50"]  # ranked, highest first
    by_area = rows_by(study, "area")
    assert by_area["Al Buraimi"]["status"] == "missing_in_source"
    assert by_area["Al Buraimi"]["value"] is None
    assert by_area["Musandam"]["status"] == "no_published_value"
    assert by_area["Musandam"]["value"] is None
    assert "A'Dhahirah" in study["findings"][0]["text"]["en"]
    assert "الظاهرة" in study["findings"][0]["text"]["ar"]
    assert any("not zero" in x["en"] for x in study["limitations"])


def test_seasonal_profile_is_a_monthly_heatmap_or_not_available(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "seasonal_profile", indicator="WATER_PRODUCTION", area="OM-WU")["study"]
    assert study["status"] == "ok"
    chart = study["charts"][0]
    assert chart["type"] == "heatmap" and (chart["x"], chart["y"]) == ("month", "year")
    assert rows_by(study, "month")["Apr"]["value"] is None  # missing month stays empty
    assert "Mar 1990" in study["findings"][0]["text"]["en"]
    assert "مارس" in study["findings"][0]["text"]["ar"]

    annual_only = run(anonymous, "seasonal_profile", indicator="ELEC_GENERATION", area="OM-WU")
    assert annual_only["study"]["status"] == "not_available"
    assert "annual totals" in annual_only["study"]["reason"]["en"]


def test_import_dependence_uses_apparent_availability(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "import_dependence", commodity="WHEAT", year=1990)["study"]
    assert study["status"] == "ok", study.get("reason")
    rows = rows_by(study, "component")
    assert Decimal(rows["apparent_availability"]["quantity"]) == Decimal("380")  # 100 + 300 − 20
    shares = {c["label"]["en"]: Decimal(c["value"]) for c in study["cards"]}
    assert any(abs(v - Decimal("78.947")) < Decimal("0.01") for v in shares.values())  # 300/380
    assert any(abs(v - Decimal("26.316")) < Decimal("0.01") for v in shares.values())  # 100/380
    assert any("not household food security" in x["en"] for x in study["limitations"])

    none = run(anonymous, "import_dependence", commodity="WHEAT", year=1991)["study"]
    assert none["status"] == "not_available"


def test_partner_concentration_shares(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "partner_concentration", commodity="WHEAT", year=1990)["study"]
    assert study["status"] == "ok", study.get("reason")
    rows = study["table"]["rows"]
    assert rows[0]["partner"] == "PARTNER_A" and Decimal(rows[0]["share_pct"]) == Decimal("50")
    assert [r["quantity"] for r in rows] == ["150", "100", "50"]
    assert Decimal(study["cards"][0]["value"]) == Decimal("50")
    hhi = Decimal(study["cards"][1]["value"])
    assert abs(hhi - Decimal("0.3889")) < Decimal("0.001")
    assert any("fictional" in x["en"] for x in study["limitations"])
    assert any("probability" in x["en"] for x in study["limitations"])


def test_data_quality_counts_published_and_missing(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "data_quality", indicator="WATER_PRODUCTION")["study"]
    assert study["status"] == "ok"
    wusta = [r for r in study["table"]["rows"] if r["area"] == "Al Wusta"]
    monthly = next(r for r in wusta if r["period_kind"] == "monthly")
    assert (monthly["published"], monthly["missing"]) == ("3", "1")


def test_scenario_is_labelled_hypothetical(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "scenario", indicator="ELEC_GENERATION", area="OM-WU",
                growth_pct="10", years=2)["study"]  # fmt: skip
    assert study["status"] == "ok"
    rows = study["table"]["rows"]
    assert rows[0] == {"year": "1994", "observed": "121", "scenario": None}
    assert Decimal(rows[-1]["scenario"]) == Decimal("146.41")  # 121 × 1.1²
    assert all(r["observed"] is None for r in rows[1:])
    natures = {s["column"]: s["nature"] for s in study["charts"][0]["series"]}
    assert natures == {"observed": "observed", "scenario": "scenario"}
    assert study["cards"][1]["nature"] == "scenario"
    assert "not a forecast" in study["findings"][0]["text"]["en"]


def test_short_series_forecast_is_withheld(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "forecast_eligibility", indicator="ELEC_GENERATION", area="OM-WU")[
        "study"
    ]
    assert study["status"] == "ok"
    assert study["table"]["rows"][0]["eligible"] == "withheld"
    assert study["findings"][0]["text"]["en"].startswith("Forecast withheld")


def test_programme_assessment_records_a_gap_without_claiming_impact(anonymous, published) -> None:  # noqa: ANN001
    study = run(anonymous, "programme_assessment", indicator="ELEC_GENERATION", area="OM-WU",
                objective="Raise generation in Al Wusta", baseline_year=1991,
                target_value="150", target_year=2000)["study"]  # fmt: skip
    assert study["status"] == "ok"
    rows = rows_by(study, "role")
    assert rows["latest"]["value"] == "121" and rows["target"]["nature"] == "stated target"
    assert Decimal(rows["gap_to_target"]["value"]) == Decimal("29")
    assert any("does not establish programme impact" in x["en"] for x in study["limitations"])
    text = " ".join(f["text"]["en"] for f in study["findings"]).lower()
    assert "does not show the programme's effect" in text
    for claim in ("caused", "because of the programme", "led to", "resulted in"):
        assert claim not in text

    passed = run(anonymous, "programme_assessment", indicator="ELEC_GENERATION", area="OM-WU",
                 objective="Raise generation", baseline_year=1991, target_value="150",
                 target_year=1993)["study"]  # fmt: skip
    assert rows_by(passed, "role")["gap_to_target"]["value"] is None
    assert any("not after the latest published year" in f["text"]["en"] for f in passed["findings"])
    early = run(anonymous, "programme_assessment", indicator="ELEC_GENERATION", area="OM-WU",
                objective="Raise generation", baseline_year=1992, target_value="150",
                target_year=1991)["study"]  # fmt: skip
    assert early["status"] == "not_available"


def test_unknown_codes_and_parameters_are_refused(anonymous, published) -> None:  # noqa: ANN001
    r = anonymous.post(f"{API}/studies", json={"kind": "trend", "data_mode": "synthetic",
                                               "params": {"indicator": "NOPE"}})  # fmt: skip
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_indicator"
    r = anonymous.post(f"{API}/studies", json={"kind": "trend", "data_mode": "synthetic",
                                               "params": {"indicator": "X; DROP TABLE area"}})  # fmt: skip
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_study_parameters"
    r = anonymous.post(f"{API}/studies", json={"kind": "python", "data_mode": "synthetic"})
    assert r.status_code == 422


# ------------------------------------------------------------------ storage, export, reproduce


def test_export_matches_the_table_and_reproduce_is_identical(anonymous, published) -> None:  # noqa: ANN001
    body = run(anonymous, "trend", indicator="ELEC_GENERATION", area="OM-WU")
    sid = body["id"]
    got = anonymous.get(f"{API}/studies/{sid}")
    assert got.status_code == 200 and got.json()["sha256"] == body["sha256"]

    r = anonymous.get(f"{API}/studies/{sid}/export.csv", params={"language": "en"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith("﻿".encode())  # spreadsheet programs read Arabic correctly
    data = [line for line in r.text.lstrip("﻿").splitlines() if not line.startswith("#")]
    table = list(csv.reader(io.StringIO("\n".join(data))))
    keys = [c["key"] for c in body["study"]["table"]["columns"]]
    expected = [["" if row.get(k) is None else row[k] for k in keys]
                for row in body["study"]["table"]["rows"]]  # fmt: skip
    assert table[1:] == expected
    assert table[0][1] == "Electricity generation (gigawatt-hours)" or "(" in table[0][1]

    ar = anonymous.get(f"{API}/studies/{sid}/export.csv", params={"language": "ar"})
    assert "الفترة" in ar.text

    j = anonymous.get(f"{API}/studies/{sid}/export.json")
    assert j.status_code == 200 and j.json()["study"] == body["study"]

    again = anonymous.get(f"{API}/studies/{sid}/reproduce").json()
    assert again["identical"] is True
    assert again["stored_versions"] == again["current_versions"]


def test_signed_in_runs_are_listed_and_deleted_by_their_owner(app, make_user, login) -> None:  # noqa: ANN001
    owner = login(make_user())
    other = login(make_user())
    sid = run(owner, "data_quality", indicator="ELEC_GENERATION")["id"]
    assert sid in {s["id"] for s in owner.get(f"{API}/studies").json()}
    assert sid not in {s["id"] for s in other.get(f"{API}/studies").json()}
    assert other.delete(f"{API}/studies/{sid}").status_code == 404
    assert owner.delete(f"{API}/studies/{sid}").status_code == 204
    assert owner.get(f"{API}/studies/{sid}").status_code == 404


def test_a_signed_in_run_needs_the_csrf_token(app, make_user, login) -> None:  # noqa: ANN001
    client = login(make_user())
    del client.headers["X-CSRF-Token"]
    r = client.post(f"{API}/studies", json={"kind": "data_quality", "data_mode": "synthetic",
                                            "params": {"indicator": "ELEC_GENERATION"}})  # fmt: skip
    assert r.status_code == 403


# ------------------------------------------------------------------ the assistant's study tool


@pytest.fixture
def study_in_wusta(monkeypatch):  # noqa: ANN001, ANN201
    """Point the scripted model's study call at Al Wusta (one series, known values)."""
    from app.services.assistant import provider

    original = provider.FakeProvider.complete

    def patched(self, system, messages, tools):  # noqa: ANN001, ANN202
        reply = original(self, system, messages, tools)
        for block in reply["content"]:
            if block.get("name") == "run_study":
                block["input"]["params"]["area"] = "OM-WU"
        return reply

    monkeypatch.setattr(provider.FakeProvider, "complete", patched)


@pytest.mark.parametrize("language", ["en", "ar"])
def test_assistant_study_is_cited_and_stored_with_the_message(
    app, db, published, study_in_wusta, language: str
) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models import StudyRun

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    question = (
        "Run a study of electricity generation" if language == "en" else "أجرِ دراسة لتوليد الكهرباء"
    )
    r = client.post(
        f"{API}/assistant/guest/messages",
        json={"content": question, "language": language, "request_id": str(uuid.uuid4()),
              "data_mode": "synthetic", "mode": "ask"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    message = r.json()["message"]
    assert message["status"] == "answered", message["content"]
    assert "121" in message["content"]
    if language == "ar":
        assert "آخر قيمة منشورة" in message["content"]
    refs = message["structured"]["studies"]
    assert len(refs) == 1 and refs[0]["kind"] == "trend"
    cited = [e for e in message["evidence"] if e["kind"] == "study"]
    assert cited and "study" not in cited[0]  # the full table is not repeated in the evidence
    row = db.scalar(select(StudyRun).where(StudyRun.id == uuid.UUID(refs[0]["id"])))
    assert row is not None and row.message_id is not None and row.guest_session_id is not None
    assert row.result["kind"] == "trend" and len(row.result_sha256) == 64
    stored = client.get(f"{API}/studies/{refs[0]['id']}").json()
    assert stored["study"]["table"]["rows"][-1]["value"] == "121"
