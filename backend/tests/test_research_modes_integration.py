"""The internet modes through the API and the database, with the scripted stand-ins (no request
leaves the machine): a Deep research report (plan, parallel searches, a calculation, a table, a
chart, a diagram and the report's sections) in English and Arabic, a Quick answer, what happens
without web search or when the answering service fails (no answer from OSRIP's own records
instead, never charged), the real progress stages, and illustrations made only for a signed-in
person and served only to them."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.domain.enums import Role
from app.services.assistant import provider as answer
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration

# What an internet answer may rest on: web results and searches, and calculations on them.
WEB_KINDS = {"web", "search"}


@pytest.fixture(autouse=True)
def _setup(request, monkeypatch):  # noqa: ANN001, ANN202
    from app.core import ratelimit
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    request.getfixturevalue("database_url")
    with session_factory()() as session:
        seed_booklet_fixtures(session)
    s = get_settings()
    for name, value in (
        ("assistant_provider", "fake"),
        ("assistant_fallback_provider", ""),
        ("research_provider", "fake"),
        ("research_fallback_provider", ""),
        ("images_provider", "fake"),
        ("guest_asks_per_minute", 1000),
        ("guest_asks_per_client_hour", 1000),
        ("assistant_max_per_minute", 1000),
        ("assistant_max_per_hour", 1000),
        ("research_per_client_hour", 1000),
        ("provider_daily_call_limit", 500),
    ):
        monkeypatch.setattr(s, name, value)
    monkeypatch.setattr(answer, "RETRY_PAUSE_SECONDS", 0)
    ratelimit.reset()


_ASKED: list[int] = []


@pytest.fixture(autouse=True)
def _forget_queued_figures(db):  # noqa: ANN001, ANN202
    """A scripted web answer queues its figure for review; remove what these tests queued so later
    modules find their own candidate (candidates are de-duplicated by source)."""
    yield
    if _ASKED:
        db.rollback()  # a test may have read through the same session
        with db.begin():
            db.execute(
                text("DELETE FROM research_candidate WHERE message_id = ANY(:m)"), {"m": _ASKED}
            )
        _ASKED.clear()


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _ask(client, content: str, mode: str, language: str = "en", **extra: Any) -> dict[str, Any]:  # noqa: ANN001
    response = client.post(
        f"{API}/assistant/guest/messages",
        json={"content": content, "language": language, "request_id": str(extra.pop("rid", uuid.uuid4())),
              "data_mode": "synthetic", "mode": mode, **extra},
    )  # fmt: skip
    assert response.status_code == 201, response.text
    _ASKED.append(response.json()["message"]["id"])
    return response.json()


def test_a_deep_research_report_is_planned_calculated_and_tabulated(app) -> None:  # noqa: ANN001
    client = _guest(app)
    rid = uuid.uuid4()
    msg = _ask(client, "Write a report on electricity generation in 2023", "research", rid=rid)[
        "message"
    ]
    assert msg["status"] == "answered", msg["content"]
    structured = msg["structured"]
    # Planned first; the sections of a research report.
    assert structured["plan"] == [
        "How much electricity did Oman generate in 2023?",
        "Do the sources agree?",
    ]
    for heading in ("## Summary", "## Findings", "## Opportunities and risks", "## Recommendations",
                    "## Evidence and assumptions", "## Limitations and missing information"):  # fmt: skip
        assert heading in msg["content"]
    # Only the web: no OSRIP records, and the route says the web came first.
    assert {e["kind"] for e in msg["evidence"]} <= WEB_KINDS
    assert structured["method"]["route"]["web_first"] is True
    assert structured["method"]["searches"] >= 2, "two searches in one step"
    # The difference was calculated by the backend from the two cited figures.
    [calc] = [c for c in msg["calculations"] if c["kind"] == "calculation"]
    assert calc["value"] == "1234" and calc["basis"] == "web" and len(calc["inputs"]) == 2
    # The table's rows, each with its source; the chart drawn from them; the diagram.
    [table] = structured["research_tables"]
    assert [r["cells"][1] for r in table["rows"]] == ["41,234", "40,000"]
    assert all(r["citations"] for r in table["rows"])
    shown = {e["id"] for e in msg["evidence"]}
    assert all(c in shown for r in table["rows"] for c in r["citations"])
    [chart] = structured["research_charts"]
    assert chart["table_id"] == table["id"] and chart["series"][0]["values"] == [41234, 40000]
    [diagram] = structured["diagrams"]
    assert [n["label"] for n in diagram["nodes"]][0] == "Generation" and diagram["edges"]
    # The two sources disagree, and both are reported.
    assert [v["value_text"] for v in structured["conflicts"][0]["values"]] == ["41,234", "40,000"]
    # No illustration: the person did not ask for one (and guests cannot have one).
    assert "images" not in structured
    seen = [s["stage"] for s in client.get(f"{API}/assistant/guest/requests/{rid}/progress").json()["stages"]]
    for stage in ("planning", "web_search", "computing", "visuals", "checking", "done"):
        assert stage in seen, seen
    assert "published_data" not in seen


def test_the_report_in_arabic(app) -> None:  # noqa: ANN001
    msg = _ask(_guest(app), "اكتب تقريرا عن توليد الكهرباء في 2023", "research", "ar")["message"]
    assert msg["status"] == "answered", msg["content"]
    assert "## الملخص" in msg["content"] and "## التوصيات" in msg["content"]
    [table] = msg["structured"]["research_tables"]
    assert table["columns"] == ["المصدر", "التوليد (غيغاواط ساعة)"]
    assert msg["structured"]["diagrams"][0]["nodes"][0]["label"] == "التوليد"


def test_a_quick_answer_searches_once_and_answers(app) -> None:  # noqa: ANN001
    msg = _ask(_guest(app), "web electricity generation 2023", "quick")["message"]
    assert msg["status"] == "answered", msg["content"]
    assert msg["mode"] == "quick"
    assert {e["kind"] for e in msg["evidence"]} <= WEB_KINDS
    method = msg["structured"]["method"]
    assert method["route"]["web_first"] is True and 1 <= method["searches"] <= 2
    assert "plan" not in msg["structured"]


def test_without_web_search_internet_modes_say_so_and_are_not_charged(app, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "research_provider", "")
    client = _guest(app)
    for mode in ("research", "quick"):
        body = _ask(client, "web electricity generation 2023", mode)
        msg = body["message"]
        assert msg["status"] == "unavailable"
        assert "no web search service is configured" in msg["content"]
        assert msg["evidence"] == [], "nothing from OSRIP's records instead"
        assert body["allowance"]["used"] == 0


def test_a_failed_answer_service_is_reported_without_a_data_fallback(app) -> None:  # noqa: ANN001
    body = _ask(_guest(app), "please fail now", "research")
    msg = body["message"]
    assert msg["status"] == "unavailable"
    assert "could not be completed" in msg["content"]
    assert msg["evidence"] == [] and body["allowance"]["used"] == 0


def test_illustrations_for_the_signed_in_owner_only(app, make_user, login, db) -> None:  # noqa: ANN001
    owner = login(make_user(Role.VIEWER))
    conv = owner.post(
        f"{API}/assistant/conversations", json={"language": "en", "data_mode": "synthetic"}
    ).json()["id"]
    r = owner.post(
        f"{API}/assistant/conversations/{conv}/messages",
        json={"content": "Write a report on electricity generation with an illustration",
              "language": "en", "mode": "research"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    message = r.json()
    _ASKED.append(message["id"])
    assert message["status"] == "answered", message["content"]
    [image] = message["structured"]["images"]
    assert image["purpose"] == "illustration" and image["model"] == "gpt-image-2.5-flare"
    picture = owner.get(f"{API}/assistant/images/{image['id']}")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert picture.content.startswith(b"\x89PNG")
    # Another person, and a guest, cannot see it.
    other = login(make_user(Role.VIEWER))
    assert other.get(f"{API}/assistant/images/{image['id']}").status_code == 404
    assert _guest(app).get(f"{API}/assistant/images/{image['id']}").status_code in (401, 403)
    # The call was metered as an image call of the stand-in.
    count = db.execute(
        text("SELECT count(*) FROM provider_call WHERE capability = 'image' AND provider = 'fake'")
    ).scalar()
    assert count >= 1


def test_a_guest_asking_for_an_illustration_gets_none(app) -> None:  # noqa: ANN001
    msg = _ask(_guest(app), "Write a report on electricity generation with an illustration", "research")[
        "message"
    ]
    assert msg["status"] == "answered" and "images" not in msg["structured"]
