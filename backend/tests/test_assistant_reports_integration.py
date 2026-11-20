"""A report asked of Al Mulhim in a sentence is built from published data by OSRIP's own report
service and shown in the reply; saving it uses the existing report endpoints and permissions,
and the saved report exports as CSV, PDF and Excel, against the database.

The scripted test provider stands in for the model: it calls build_report (and the forecasting
engine for a forecast report) with the sector, indicator, area and years the request names, and
writes only what the tools returned. The series are SYNTHETIC, for Al Batinah South (OM-BJ) in
1950-1955, which no other module publishes; they are superseded when the module ends.
"""

from __future__ import annotations

import uuid
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
GENERATION = [400, 410, 425, 431, 440, 452]  # 1950-1955


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

    username, password = f"rp{uuid.uuid4().hex[:8]}", f"pw-{uuid.uuid4().hex}"
    with session_factory()() as s, s.begin():
        u = accounts.create_user(
            s, Principal(None, "t"), username=username, display_name="reports manager",
            password=password, roles=[Role.DATA_MANAGER],
        )  # fmt: skip
        s.flush()
        for g in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), u.id, g)
    client = TestClient(create_app())
    login = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    rows = [
        f"ELEC_GENERATION,{AREA},{1950 + i}-01-01,{1950 + i}-12-31,annual,GWh,{v},,,"
        for i, v in enumerate(GENERATION)
    ]
    imp = upload_validate_approve(client, register_synthetic_source(client), csv_bytes(*rows))
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
    return r.json()["message"]


def test_a_report_request_builds_the_report_from_published_data(app, published) -> None:  # noqa: ANN001
    message = ask(
        app, "Create a report on electricity generation in Batinah South for 1950 to 1955."
    )
    assert message["status"] == "answered", message["content"]
    assert message["mode"] == "analyze"
    structured = message["structured"]
    assert structured["intent"] == "report" and structured["report_type"] == "sector"
    report = structured["report"]
    assert report["section"] == "electricity" and report["data_mode"] == "synthetic"
    # The sector, indicator, area and period the request named, as the report's filters.
    assert report["filters"] == {
        "indicator": "ELEC_GENERATION", "area": AREA, "period_kind": "annual",
        "period_from": "1950-01-01", "period_to": "1955-12-31",
    }  # fmt: skip
    series = report["series"][0]
    assert series["indicator"] == "ELEC_GENERATION" and series["area"] == AREA
    assert set(series["indicator_name"]) == {"en", "ar"}
    assert [r["value"] for r in series["rows"]] == [str(v) for v in GENERATION]
    assert report["title"]["en"].startswith("Electricity report: Electricity generation")
    assert "1950–1955" in report["title"]["en"]
    # The reply states only the published figures, and its evidence keeps no copy of the content.
    assert str(GENERATION[-1]) in message["content"]
    cited = next(e for e in message["evidence"] if e["kind"] == "report")
    assert "content" not in cited and cited["id"] == report["evidence_id"]


def test_a_report_request_in_arabic(app, published) -> None:  # noqa: ANN001
    message = ask(app, "أنشئ تقريرًا عن توليد الكهرباء في جنوب الباطنة", "ar")
    assert message["status"] == "answered", message["content"]
    report = message["structured"]["report"]
    assert report["series"][0]["area"] == AREA
    assert report["title"]["ar"].startswith("تقرير الكهرباء")
    assert "يضم التقرير" in message["content"]


def test_a_forecast_report_also_asks_the_forecasting_engine(app, published) -> None:  # noqa: ANN001
    message = ask(app, "Create a forecast report on electricity generation in Batinah South.")
    assert message["status"] == "answered", message["content"]
    structured = message["structured"]
    assert structured["intent"] == "report" and structured["report_type"] == "forecast"
    assert structured["report"]["report_type"] == "forecast"
    # Six annual values: too short for the backtesting policy, so no value is given.
    forecast = structured["forecasts"][0]
    assert forecast["status"] == "withheld" and forecast["outputs"] == []
    assert "No forecast is produced" in message["content"]


def test_nothing_published_means_no_report_and_says_so(app, published) -> None:  # noqa: ANN001
    message = ask(app, "Create a report on trade in Batinah South for 1950.")
    assert "report" not in message["structured"]
    assert "No published data matches this report." in message["content"]


def test_the_report_is_saved_viewed_and_exported_with_the_existing_permissions(
    app, published, make_user, login, anonymous
) -> None:  # noqa: ANN001
    """Saving sends the reply's section and filters to POST /reports (report.create), which
    freezes the same figures; the saved report exports as CSV, PDF and Excel; a private report
    stays its owner's."""
    report = ask(
        app, "Create a report on electricity generation in Batinah South for 1950 to 1955."
    )["structured"]["report"]
    body = {
        "title": report["title"]["en"], "data_mode": report["data_mode"],
        "section": report["section"], "filters": report["filters"],
        "stock_assumption": "assumed_zero", "visibility": "private",
    }  # fmt: skip
    # A viewer cannot create platform reports; an analyst can.
    viewer = login(make_user(Role.VIEWER))
    assert viewer.post(f"{API}/reports", json=body).status_code == 403
    analyst = login(make_user(Role.ANALYST))
    created = analyst.post(f"{API}/reports", json=body)
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    saved = analyst.get(f"{API}/reports/{report_id}").json()
    values = [o["value"] for s in saved["content"]["series"] for o in s["observations"]]
    assert values == [r["value"] for r in report["series"][0]["rows"]]  # the same figures
    csv = analyst.get(f"{API}/reports/{report_id}/export.csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "ELEC_GENERATION" in csv.text and str(GENERATION[0]) in csv.text
    pdf = analyst.get(f"{API}/reports/{report_id}/export.pdf?language=ar")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xlsx = analyst.get(f"{API}/reports/{report_id}/export.xlsx?language=en")
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")

    # Private: the same "not found" for another account and for a visitor.
    assert viewer.get(f"{API}/reports/{report_id}").status_code == 404
    assert anonymous.get(f"{API}/reports/{report_id}").status_code == 404
    assert anonymous.get(f"{API}/reports/{report_id}/export.csv").status_code == 404


def test_a_signed_in_answer_report_keeps_the_report_tables(
    app, published, make_user, login
) -> None:  # noqa: ANN001
    """Any signed-in person can turn the answer into a report (PDF, Excel, CSV); it carries the
    report's tables and sources."""
    user = login(make_user(Role.VIEWER))
    conv = user.post(
        f"{API}/assistant/conversations", json={"language": "en", "data_mode": "synthetic"}
    ).json()["id"]
    reply = user.post(
        f"{API}/assistant/conversations/{conv}/messages",
        json={"content": "Create a report on electricity generation in Batinah South.", "language": "en"},
    )  # fmt: skip
    assert reply.status_code == 201, reply.text
    message = reply.json()["message"] if "message" in reply.json() else reply.json()
    assert message["structured"]["report"]["series"][0]["indicator"] == "ELEC_GENERATION"
    made = user.post(f"{API}/assistant/messages/{message['id']}/report", json={"language": "en"})
    assert made.status_code == 201, made.text
    content = user.get(f"{API}/analysis-reports/{made.json()['id']}").json()["content"]
    headings = [s["heading"] for s in content["sections"]]
    assert any(h.startswith("Electricity report: Electricity generation") for h in headings)
    csv = user.get(f"{API}/analysis-reports/{made.json()['id']}/export.csv")
    assert csv.status_code == 200 and str(GENERATION[-1]) in csv.text
