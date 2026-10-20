"""Shortage and surplus analysis through the API, on the synthetic booklet fixtures, and the
voice test and voice check endpoints (scripted speech provider; no network)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def setup(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services import speech
    from app.services.fixtures import seed_booklet_fixtures

    s = get_settings()
    monkeypatch.setattr(s, "speech_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    monkeypatch.setitem(speech._VOICES_CACHE, "voices", None)
    ratelimit.reset()
    with session_factory()() as session:
        seed_booklet_fixtures(session)


def _run(client: TestClient, sector: str, mode: str = "synthetic", **extra: object) -> dict:
    r = client.post(
        f"{API}/analysis/balance", json={"data_mode": mode, "params": {"sector": sector, **extra}}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_food_balance_tables_charts_and_exports_agree(app) -> None:  # noqa: ANN001
    client = TestClient(app)
    body = _run(client, "food_security", supply_growth_pct="2", demand_growth_pct="3", years=2)
    a = body["analysis"]
    b = next(x for x in a["balances"] if x["code"].startswith("FOOD_QUANTITY"))
    row = b["table"]["rows"][0]
    # The gap, the table and the chart are one result: gap = production − apparent availability.
    assert Decimal(row["gap"]) == Decimal(row["production"]) - Decimal(row["availability"])
    assert Decimal(b["gap"]) == Decimal(row["gap"])
    assert b["status"] == ("shortfall" if Decimal(b["gap"]) < 0 else "surplus")
    assert {s["column"] for c in b["charts"] for s in c["series"]} <= {
        c["key"] for c in b["table"]["columns"]
    }
    assert all(c.get("unit") for c in b["table"]["columns"] if c["kind"] == "number")
    # Every number rests on cited, published observations with their provenance.
    ids = {s["id"]: s for s in a["sources"]}
    assert b["evidence"] and set(b["evidence"]) <= set(ids)
    assert all(
        ids[i]["dataset_version"] and ids[i]["title"] and ids[i]["period_label"]
        for i in b["evidence"]
    )
    assert all(s["data_status"] == "synthetic_demonstration" for s in a["sources"])
    # The scenario is labelled as stated assumptions, never as observations or a forecast.
    sc = a["scenario"]
    assert sc["status"] == "ok" and [r["basis"] for r in sc["table"]["rows"]] == [
        "base",
        "scenario",
        "scenario",
    ]
    assert "not a forecast" in sc["assumptions"][0]["en"]
    # Recommendations: quantities only from the calculation, costs always unknown.
    rec = next(
        r for r in a["recommendations"] if r["balance"] == b["id"] and r["quantity"] is not None
    )
    assert Decimal(rec["quantity"]) == abs(Decimal(b["gap"]))
    assert all(
        r["cost_known"] is False and r["cost"]["en"].startswith("Unknown")
        for r in a["recommendations"]
    )

    analysis_id = body["id"]
    assert client.get(f"{API}/analysis/balance/{analysis_id}").json()["analysis"] == a
    assert client.get(f"{API}/analysis/balance/{analysis_id}/reproduce").json()["identical"] is True
    csv_ar = client.get(
        f"{API}/analysis/balance/{analysis_id}/export.csv", params={"language": "ar"}
    )
    assert csv_ar.status_code == 200 and csv_ar.headers["content-type"].startswith("text/csv")
    assert csv_ar.text.startswith("﻿") and "الإجراء المقترح" in csv_ar.text
    assert row["gap"] in csv_ar.text, "the CSV holds the same unrounded value as the table"
    report = client.get(
        f"{API}/analysis/balance/{analysis_id}/report.html", params={"language": "ar"}
    )
    assert (
        report.status_code == 200
        and "default-src 'none'" in report.headers["content-security-policy"]
    )
    assert '<html lang="ar" dir="rtl">' in report.text and "<script" not in report.text
    # An analysis is not a study: the study routes do not serve it.
    assert client.get(f"{API}/studies/{analysis_id}").status_code == 404


def test_electricity_without_peak_demand_states_no_shortage(app) -> None:  # noqa: ANN001
    client = TestClient(app)
    a = client.post(f"{API}/analysis/balance/preview",
                    json={"data_mode": "synthetic", "params": {"sector": "electricity"}}).json()["analysis"]  # fmt: skip
    assert a["status"] == "not_available"
    assert all(b["status"] == "not_determinable" and b["gap"] is None for b in a["balances"])
    assert any("peak demand" in g["missing"]["en"].lower() for g in a["data_gaps"])
    first = a["recommendations"][0]
    assert (first["nature"], first["priority"]) == ("data_improvement", "high")
    assert all(r["quantity"] is None for r in a["recommendations"]), (
        "no quantity without a shortfall"
    )
    assert a["scenario"]["status"] == "not_requested"


def test_trade_balance_is_exports_minus_imports(app) -> None:  # noqa: ANN001
    client = TestClient(app)
    a = _run(client, "trade")["analysis"]
    for b in a["balances"]:
        for row in b["table"]["rows"]:
            if row["exports"] is not None and row["imports"] is not None:
                assert Decimal(row["balance"]) == Decimal(row["exports"]) - Decimal(row["imports"])
            else:
                assert row["balance"] is None, "a missing side never becomes zero"


@pytest.mark.parametrize(
    "params",
    [
        {"sector": "fisheries"},
        {"sector": "trade", "years": 3},
        {"sector": "trade", "area": "<script>"},
    ],
)
def test_parameters_outside_the_allowlist_are_refused(app, params: dict) -> None:  # noqa: ANN001
    r = TestClient(app).post(
        f"{API}/analysis/balance", json={"data_mode": "synthetic", "params": params}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_analysis_parameters"


def _guest(app) -> TestClient:  # noqa: ANN001
    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def test_voice_check_and_test_voice_use_each_persona_voice(app) -> None:  # noqa: ANN001
    client = _guest(app)
    voices = client.get(f"{API}/assistant/voice/voices").json()
    assert voices["configured"] is True
    by = {p["code"]: p for p in voices["personas"]}
    assert by["mulhim"]["voices"]["ar"]["name"] == "ar-OM-AbdullahNeural"
    assert by["ilham"]["voices"]["ar"]["name"] == "ar-OM-AyshaNeural"
    assert by["ilham"]["voices"]["en"] == {
        "name": "en-GB-SoniaNeural",
        "verified": True,
        "locale": "en-GB",
        "gender": "Female",
    }
    for persona, language, voice in (("ilham", "ar", "ar-OM-AyshaNeural"), ("mulhim", "ar", "ar-OM-AbdullahNeural"),
                                     ("mulhim", "en", "en-GB-RyanNeural")):  # fmt: skip
        r = client.post(
            f"{API}/assistant/voice/test", json={"persona": persona, "language": language}
        )
        assert r.status_code == 200, r.text
        assert r.headers["x-voice"] == voice and r.content[:4] == b"RIFF"
    no_csrf = TestClient(app)
    no_csrf.get(f"{API}/assistant/guest")
    assert no_csrf.post(f"{API}/assistant/voice/test", json={"language": "ar"}).status_code == 403


def test_an_analysis_is_read_as_a_short_summary_not_cell_by_cell(app) -> None:  # noqa: ANN001
    from app.services.analysis import balance_export

    client = _guest(app)
    body = _run(client, "trade")
    text = balance_export.spoken_summary(body["analysis"], "ar")
    # The summary names each balance's status but not the table cells one by one.
    assert all(b["status_label"]["ar"] in text for b in body["analysis"]["balances"])
    assert len(text) < 3000
    r = client.post(
        f"{API}/assistant/voice/analysis",
        json={"analysis_id": body["id"], "persona": "ilham", "language": "ar"},
    )
    assert r.status_code == 200 and r.headers["x-voice"] == "ar-OM-AyshaNeural"
    missing = client.post(
        f"{API}/assistant/voice/analysis",
        json={"analysis_id": "00000000-0000-4000-8000-000000000000", "language": "en"},
    )
    assert missing.status_code == 404


def test_without_speech_the_voice_test_says_not_configured(app, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "speech_provider", "")
    client = _guest(app)
    voices = client.get(f"{API}/assistant/voice/voices").json()
    assert voices["configured"] is False
    assert {v["verified"] for p in voices["personas"] for v in p["voices"].values()} == {None}
    r = client.post(f"{API}/assistant/voice/test", json={"persona": "ilham", "language": "ar"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "speech_not_configured"
