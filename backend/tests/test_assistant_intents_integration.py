"""A sentence to Al Mulhim runs OSRIP's real study, forecast and scenario tools, and the reply
carries their results (tables and charts are drawn from them), against the database.

The scripted test provider stands in for the model: it calls the tools the request names, as the
service's rules ask, and writes only what the tools returned. The series here are SYNTHETIC, for
Al Batinah South (OM-BJ) in 1960-1971, which no other module publishes; they are superseded when
the module ends, so nothing is left published for later modules.

- Electricity consumption, 12 years: enough history, so the forecasting engine estimates.
- Electricity generation, 4 years: not enough, so the forecast is withheld with its reasons.
- Water production, 12 years: the base of a hypothetical scenario.
"""

from __future__ import annotations

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

AREA = "OM-BJ"
CONSUMPTION = [100, 104, 103, 110, 112, 115, 113, 120, 126, 125, 131, 138]
WATER = [50, 52, 51, 55, 56, 58, 57, 60, 63, 62, 65, 69]
GENERATION = [200, 210, 205, 220]


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
    monkeypatch.setattr(s, "guest_answer_limit", 1000, raising=False)
    ratelimit.reset()


@pytest.fixture(scope="module")
def published(database_url: str):  # noqa: ANN201
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.principal import Principal

    username, password = f"in{uuid.uuid4().hex[:8]}", "pw-intents-manager-0000"
    with session_factory()() as s, s.begin():
        u = accounts.create_user(
            s, Principal(None, "t"), username=username, display_name="intents manager",
            password=password, roles=[Role.DATA_MANAGER],
        )  # fmt: skip
        s.flush()
        for g in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), u.id, g)
    client = TestClient(create_app())
    login = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]

    def rows(indicator: str, unit: str, values: list[int]) -> list[str]:
        return [
            f"{indicator},{AREA},{1960 + i}-01-01,{1960 + i}-12-31,annual,{unit},{v},,,"
            for i, v in enumerate(values)
        ]

    imp = upload_validate_approve(
        client,
        register_synthetic_source(client),
        csv_bytes(
            *rows("ELEC_CONSUMPTION", "GWh", CONSUMPTION),
            *rows("ELEC_GENERATION", "GWh", GENERATION),
            *rows("WATER_PRODUCTION", "million_m3", WATER),
        ),
    )
    assert client.post(f"{API}/imports/{imp['id']}/publish").status_code == 200
    yield imp["version"]["id"]
    with session_factory()() as s, s.begin():
        s.execute(
            text(
                "UPDATE dataset_version SET status = 'superseded', superseded_at = now() "
                "WHERE id = :id"
            ),
            {"id": imp["version"]["id"]},
        )


def ask(app, question: str, language: str = "en") -> dict[str, Any]:  # noqa: ANN001
    """One visitor question, in Automatic mode (as the conversation page sends it)."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    r = client.post(
        f"{API}/assistant/guest/messages",
        json={"content": question, "language": language, "request_id": str(uuid.uuid4()),
              "data_mode": "synthetic", "mode": "auto"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return {"message": r.json()["message"], "client": client}


def test_a_forecast_request_runs_the_engine_and_returns_its_estimates(app, published) -> None:  # noqa: ANN001
    message = ask(app, "Forecast electricity consumption in Batinah South.")["message"]
    assert message["status"] == "answered", message["content"]
    assert message["mode"] == "analyze"
    structured = message["structured"]
    assert structured["intent"] == "forecast"
    forecast = structured["forecasts"][0]
    assert forecast["status"] == "ok" and forecast["stored"] is False
    assert forecast["indicator"] == "ELEC_CONSUMPTION" and forecast["area"] == AREA
    # Names in the shape every evidence item uses ({en, ar}), here and in the evidence list.
    assert set(forecast["indicator_name"]) == {"en", "ar"} and set(forecast["unit_label"]) == {
        "en",
        "ar",
    }
    cited = next(e for e in message["evidence"] if e["kind"] == "forecast")
    assert set(cited["indicator_name"]) == {"en", "ar"} and set(cited["unit_label"]) == {"en", "ar"}
    assert len(forecast["history"]) == len(CONSUMPTION)
    assert forecast["outputs"] and forecast["outputs"][0]["period_start"] == "1972-01-01"
    assert forecast["selected_model"] in forecast["metrics"]
    # The reply states the engine's estimate, labelled, and nothing else is invented.
    assert forecast["outputs"][0]["estimate"] in message["content"]
    assert "not an official statistic" in message["content"]


def test_a_short_history_is_withheld_with_the_reasons_and_no_value(app, published) -> None:  # noqa: ANN001
    message = ask(app, "Forecast electricity generation in Batinah South.")["message"]
    assert message["status"] == "answered", message["content"]
    forecast = message["structured"]["forecasts"][0]
    assert forecast["status"] == "withheld"
    assert forecast["outputs"] == [] and forecast["reasons"]
    assert forecast["usable_observations"] == len(GENERATION)
    assert forecast["policy"]["minimum_length"] == 12
    assert "No forecast is produced" in message["content"] and "4 usable" in message["content"]


def test_a_forecast_request_in_arabic(app, published) -> None:  # noqa: ANN001
    message = ask(app, "تنبأ بإنتاج المياه في جنوب الباطنة", "ar")["message"]
    assert message["status"] == "answered", message["content"]
    assert message["structured"]["intent"] == "forecast"
    forecast = message["structured"]["forecasts"][0]
    assert forecast["indicator"] == "WATER_PRODUCTION" and forecast["status"] == "ok"
    assert "تقدير نموذج" in message["content"]


def test_a_scenario_request_applies_the_stated_change_and_is_labelled_hypothetical(
    app, published
) -> None:  # noqa: ANN001
    message = ask(
        app, "What happens if water production in Batinah South increases by 15% over five years?"
    )["message"]
    assert message["status"] == "answered", message["content"]
    assert message["mode"] == "scenario" and message["structured"]["intent"] == "scenario"
    scenario = message["structured"]["scenarios"][0]
    assert scenario["indicator"] == "WATER_PRODUCTION" and scenario["area"] == AREA
    assert len(scenario["points"]) == 5
    # The published base (1971) and +15% in total over five years (compounded yearly rate).
    assert Decimal(scenario["base"]["value"]) == WATER[-1]
    assert scenario["base"]["period_start"] == "1971-01-01"
    last = Decimal(scenario["points"][-1]["value"])
    assert abs(last - Decimal(WATER[-1]) * Decimal("1.15")) < Decimal("0.1")
    assert "Hypothetical scenario, not a forecast" in message["content"]


def test_a_scenario_without_a_stated_change_asks_for_it(app, published) -> None:  # noqa: ANN001
    message = ask(app, "Create a scenario for water production in Batinah South.")["message"]
    assert message["status"] == "clarification"
    assert "percentage" in message["content"]
    assert "scenarios" not in message["structured"]


def test_a_study_request_runs_the_study_and_keeps_it_with_the_reply(app, published) -> None:  # noqa: ANN001
    asked = ask(app, "أنشئ دراسة عن توليد الكهرباء في جنوب الباطنة", "ar")
    message = asked["message"]
    assert message["status"] == "answered", message["content"]
    assert message["structured"]["intent"] == "study"
    ref = message["structured"]["studies"][0]
    assert ref["kind"] == "trend"
    # The whole study (title, method, findings, table, limitations) is stored and readable.
    stored = asked["client"].get(f"{API}/studies/{ref['id']}").json()["study"]
    assert stored["params"]["indicator"] == "ELEC_GENERATION" and stored["params"]["area"] == AREA
    assert [r["value"] for r in stored["table"]["rows"]][-1] == str(GENERATION[-1])
    assert stored["method"]["en"] and stored["limitations"] and stored["findings"]
