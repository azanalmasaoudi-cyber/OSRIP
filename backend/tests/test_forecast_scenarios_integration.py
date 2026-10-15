"""Forecast runs with future estimates, the per-indicator overview, hypothetical
scenarios, monitoring, and the assistant explaining a validated forecast.
All series are SYNTHETIC or test placeholders in the throwaway database."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    register_test_verified_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration
VALUES = [100, 104, 103, 110, 112, 115, 113, 120, 126, 125, 131, 138]


@pytest.fixture(scope="module")
def clients(database_url: str) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.principal import Principal

    app = create_app()
    people = {
        "manager": ([Role.DATA_MANAGER], (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH)),
        "analyst": ([Role.ANALYST], ()),
        "admin": ([Role.ADMINISTRATOR], ()),
        "viewer": ([Role.VIEWER], ()),
    }
    out: dict[str, Any] = {"app": app}
    for name, (roles, grants) in people.items():
        email, password = f"fs-{name}@test.invalid", f"pw-fs-{name}-000000"
        with session_factory()() as s, s.begin():
            u = accounts.create_user(
                s,
                Principal(None, "t"),
                email=email,
                display_name=name,
                password=password,
                roles=roles,
            )
            s.flush()
            for g in grants:
                accounts.grant_permission(s, Principal(None, "t"), u.id, g)
        c = TestClient(app)
        assert (
            c.post(f"{API}/auth/login", json={"email": email, "password": password}).status_code
            == 200
        )
        c.headers["X-CSRF-Token"] = c.cookies["osrip_csrf"]
        out[name] = c
    m = out["manager"]
    src = register_synthetic_source(m)
    imp = upload_validate_approve(
        m,
        src,
        csv_bytes(
            *(
                f"ELEC_CONSUMPTION,OM-MU,{2008 + i}-01-01,{2008 + i}-12-31,annual,GWh,{v},,,"
                for i, v in enumerate(VALUES)
            )
        ),
    )
    assert m.post(f"{API}/imports/{imp['id']}/publish").status_code == 200
    out["version"] = imp["version"]["id"]
    vsrc = register_test_verified_source(m)
    months = [
        f"WATER_CONSUMPTION,OM-ZA,{2022 + i // 12}-{i % 12 + 1:02d}-01,{_month_end(2022 + i // 12, i % 12 + 1)},monthly,million_m3,{50 + i % 12 + i // 12},,,"
        for i in range(36)
    ]
    vimp = upload_validate_approve(m, vsrc, csv_bytes(*months))
    assert m.post(f"{API}/imports/{vimp['id']}/publish").status_code == 200
    return out


def _month_end(y: int, mo: int) -> str:
    import calendar

    return f"{y}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"


def overview(client, mode: str) -> dict:  # noqa: ANN001
    r = client.get(f"{API}/forecast/overview", params={"data_mode": mode})
    assert r.status_code == 200, r.text
    return r.json()


def target(payload: dict, indicator: str, flow: str | None = None) -> dict:
    return next(t for t in payload["targets"] if t["indicator"] == indicator and t["flow"] == flow)


def our_series(t: dict, area: str) -> dict:
    return next(s for s in t["series"] if s["area"]["code"] == area)


@pytest.fixture(scope="module")
def run(clients) -> dict:  # noqa: ANN001
    sid = our_series(target(overview(clients["viewer"], "synthetic"), "ELEC_CONSUMPTION"), "OM-MU")[
        "series_id"
    ]
    r = clients["analyst"].post(
        f"{API}/forecast-runs", json={"data_mode": "synthetic", "series_id": sid}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_run_stores_future_estimates_with_intervals_and_provenance(run) -> None:  # noqa: ANN001
    assert run["status"] == "succeeded"
    d = run["definition"]
    assert d["history"] == {
        "first_period": "2008-01-01",
        "training_cutoff": "2019-12-31",
        "observations": 12,
    }
    assert d["future_horizon_steps"] == 3 and d["selected_model"] == run["selected_model"]
    assert d["candidates"] == [
        "baseline_last_value",
        "candidate_linear_trend",
    ]  # annual: no seasonal model
    assert [o["period_start"] for o in run["outputs"]] == ["2020-01-01", "2021-01-01", "2022-01-01"]
    for o in run["outputs"]:
        lo95, lo80, est, hi80, hi95 = (
            Decimal(o[k]) for k in ("lower95", "lower80", "estimate", "upper80", "upper95")
        )
        assert lo95 <= lo80 <= est <= hi80 <= hi95
    assert len(run["history"]) == 12 and run["training_cutoff"] == "2019-12-31"
    assert run["interval_method"]["code"] in ("random_walk_normal", "ols_prediction_interval")
    assert "model estimate, not an official statistic" in run["explanation"]["en"]
    assert "ليس إحصاءً رسمياً" in run["explanation"]["ar"]
    assert run["demonstration_label"]  # synthetic: software demonstration only
    # The selected model is the lowest backtest MAE, or the baseline when nothing beats it.
    maes = {k: Decimal(v["mae"]) for k, v in run["metrics"].items()}
    best = min(maes, key=lambda k: (maes[k], k != "baseline_last_value"))
    assert run["selected_model"] == (
        best if maes[best] < maes["baseline_last_value"] else "baseline_last_value"
    )


def test_outputs_are_append_only(db) -> None:  # noqa: ANN001
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="append-only"), db.begin():
        db.execute(text("UPDATE forecast_output SET estimate = 0"))


def test_overview_reports_available_and_insufficient_indicators(clients, run) -> None:  # noqa: ANN001
    payload = overview(clients["viewer"], "synthetic")
    elec = target(payload, "ELEC_CONSUMPTION")
    assert elec["status"] == "available" and our_series(elec, "OM-MU")["latest_run_id"] == run["id"]
    food = target(payload, "FOOD_PRODUCTION")
    assert food["status"] == "insufficient_data"
    assert (
        payload["insufficient_label"]["en"]
        == "Insufficient comparable historical data for a reliable forecast."
    )
    assert {t["indicator"] for t in payload["targets"]} >= {
        "ELEC_CONSUMPTION",
        "ELEC_GENERATION",
        "WATER_CONSUMPTION",
        "WATER_PRODUCTION",
        "FOOD_PRODUCTION",
        "TRADE_QUANTITY",
        "TRADE_VALUE",
    }


def test_verified_monthly_series_from_2022_is_eligible_with_seasonal_candidate(clients) -> None:  # noqa: ANN001
    water = target(overview(clients["viewer"], "verified_source"), "WATER_CONSUMPTION")
    series = our_series(water, "OM-ZA")
    assert series["eligible"] and series["first_period"] >= "2022-01-01"
    r = clients["analyst"].post(
        f"{API}/forecast-runs",
        json={"data_mode": "verified_source", "series_id": series["series_id"]},
    )
    body = r.json()
    assert (
        body["status"] == "succeeded"
        and "candidate_seasonal_naive" in body["definition"]["candidates"]
    )
    assert (
        body["selected_model"] == "candidate_seasonal_naive"
    )  # the season dominates this test series
    assert body["demonstration_label"] is None and len(body["outputs"]) == 9


def test_scenarios_are_hypothetical_and_computed_from_the_latest_published_value(clients) -> None:  # noqa: ANN001
    v = clients["viewer"]
    listed = v.get(f"{API}/scenarios/series", params={"data_mode": "synthetic"}).json()
    ours = next(
        s
        for s in listed
        if s["area"]["code"] == "OM-MU" and s["indicator"]["code"] == "ELEC_CONSUMPTION"
    )
    assert ours["base"]["value"] == "138"
    r = v.get(
        f"{API}/scenarios/projection",
        params={
            "data_mode": "synthetic",
            "series_id": ours["series_id"],
            "growth_pct": "5",
            "years": 3,
        },
    )
    body = r.json()
    assert body["kind"] == "hypothetical_scenario" and "not a forecast" in body["label"]["en"]
    assert [Decimal(p["value"]) for p in body["points"]] == [
        Decimal("144.9"),
        Decimal("152.145"),
        Decimal("159.75225"),
    ]
    assert [p["year"] for p in body["points"]] == [2020, 2021, 2022]
    assert body["base"]["period_start"] == "2019-01-01" and body["base"]["dataset_version"]
    bad = v.get(
        f"{API}/scenarios/projection",
        params={"data_mode": "synthetic", "series_id": ours["series_id"], "growth_pct": "60"},
    )
    assert bad.status_code == 422
    unknown = v.get(
        f"{API}/scenarios/projection", params={"data_mode": "synthetic", "series_id": "nope"}
    )
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unknown_series"


# ------------------------------------------------------------------ monitoring


def test_browser_errors_are_stored_scrubbed_and_limited(clients, db, monkeypatch) -> None:  # noqa: ANN001
    from sqlalchemy import select

    from app.api.routes import monitoring as routes
    from app.core import ratelimit
    from app.models import AppError

    ratelimit.reset()
    monkeypatch.setattr(routes, "CLIENT_ERRORS_PER_HOUR", 2)
    anon = clients["viewer"]
    r = anon.post(
        f"{API}/telemetry/client-errors",
        json={
            "kind": "TypeError",
            "message": "x is undefined for someone@example.org token AAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "location": "http://localhost:5173/geography?area=OM-MA&token=secret",
        },
    )
    assert r.status_code == 204
    with db.begin():
        row = db.scalars(
            select(AppError).where(AppError.source == "client").order_by(AppError.id.desc())
        ).first()
    assert row.location == "http://localhost:5173/geography"
    assert (
        "someone@example.org" not in row.message
        and "[email]" in row.message
        and "[redacted]" in row.message
    )
    anon.post(f"{API}/telemetry/client-errors", json={"kind": "E", "message": "m"})
    assert (
        anon.post(f"{API}/telemetry/client-errors", json={"kind": "E", "message": "m"}).status_code
        == 429
    )


def test_unhandled_server_errors_get_a_request_id_and_are_recorded(clients, db) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.main import create_app
    from app.models import AppError

    app = create_app()

    def boom() -> None:
        raise RuntimeError("database password is hunter2hunter2hunter2hunter2")

    app.add_api_route(f"{API}/__boom", boom)
    r = TestClient(app).get(f"{API}/__boom?secret=1")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    request_id = r.json()["error"]["details"]["request_id"]
    assert r.headers["X-Request-ID"] == request_id and "hunter2" not in r.text
    with db.begin():
        row = db.scalars(select(AppError).where(AppError.request_id == request_id)).one()
    assert (
        row.kind == "RuntimeError"
        and row.location == f"{API}/__boom"
        and "hunter2hunter2" not in row.message
    )


def _alembic_head() -> str:
    import os

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head() or ""


def test_readiness_and_monitoring_view(clients) -> None:  # noqa: ANN001
    ready = clients["viewer"].get(f"{API}/health/ready").json()
    assert ready["ready"] is True and ready["checks"]["migration"] == _alembic_head()
    assert ready["integrations"]["google"]["status"] == "not_configured"
    assert "secret" not in json.dumps(ready).lower()
    assert clients["viewer"].get(f"{API}/admin/monitoring").status_code == 403
    view = clients["admin"].get(f"{API}/admin/monitoring").json()
    assert "errors" in view and view["ready"] is True


# ------------------------------------------------------------------ assistant explains a validated forecast


def _anthropic(monkeypatch, handler) -> None:  # noqa: ANN001
    from app.core.config import get_settings
    from app.services.assistant import provider

    monkeypatch.setattr(get_settings(), "assistant_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("test-key"))
    monkeypatch.setattr(provider, "RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(
        provider,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout),
    )


@pytest.mark.parametrize("invent", [False, True])
def test_assistant_explains_only_validated_forecast_numbers(
    clients, run, monkeypatch, invent: bool
) -> None:  # noqa: ANN001
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "a",
                            "name": "get_forecast",
                            "input": {"indicator": "ELEC_CONSUMPTION", "area": "OM-MU"},
                        }
                    ]
                },
            )
        result = json.loads(body["messages"][-1]["content"][0]["content"])
        first = result["outputs"][0]
        estimate = "999999" if invent else first["estimate"]
        text = (
            f"The model estimate for 2020 is {estimate} GWh (80% interval {first['lower80']} to {first['upper80']}), "
            f"trained on data to {result['training_cutoff']} [{result['evidence_id']}]. It is not an official statistic."
        )
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "tool_use",
                        "id": "b",
                        "name": "final_answer",
                        "input": {
                            "status": "answered",
                            "text": text,
                            "citations": [result["evidence_id"]],
                        },
                    }
                ]
            },
        )

    _anthropic(monkeypatch, handler)
    a = clients["analyst"]
    conv = a.post(
        f"{API}/assistant/conversations", json={"language": "en", "data_mode": "synthetic"}
    ).json()["id"]
    reply = a.post(
        f"{API}/assistant/conversations/{conv}/messages",
        json={"content": "Forecast Musandam electricity consumption"},
    ).json()
    if invent:
        assert reply["status"] == "unverified" and "999999" not in reply["content"]
    else:
        assert reply["status"] == "answered", reply
        assert any(e["kind"] == "forecast" for e in reply["evidence"])


def test_assistant_retries_once_on_a_transient_failure(clients, monkeypatch) -> None:  # noqa: ANN001
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "overloaded"})
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "tool_use",
                        "id": "b",
                        "name": "final_answer",
                        "input": {
                            "status": "clarification",
                            "text": "Which area do you mean?",
                            "citations": [],
                        },
                    }
                ]
            },
        )

    _anthropic(monkeypatch, handler)
    a = clients["analyst"]
    conv = a.post(f"{API}/assistant/conversations", json={"language": "en"}).json()["id"]
    reply = a.post(
        f"{API}/assistant/conversations/{conv}/messages", json={"content": "forecast?"}
    ).json()
    assert reply["status"] == "clarification" and len(calls) == 2
