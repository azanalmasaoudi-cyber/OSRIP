"""The governed AI and research service through the API and the database: the routing policy
(approved data first for numbers), a fallback answering provider only after the primary fails,
the daily limit refusing calls (never charged), Google Search grounded context shown apart
from the answer, a cross-check only when asked for, an unsupported answer withheld, the
provider readiness view and live test (administrators only), and expiry of grounded results."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import get_settings
from app.services.assistant import provider as answer
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


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
        ("research_max_searches_per_answer", 6),
        ("guest_asks_per_minute", 1000),
        ("assistant_max_per_minute", 1000),
        ("provider_daily_call_limit", 500),
    ):
        monkeypatch.setattr(s, name, value)
    monkeypatch.setattr(answer, "RETRY_PAUSE_SECONDS", 0)
    ratelimit.reset()


_ASKED: list[int] = []


@pytest.fixture(autouse=True)
def _forget_queued_figures(db):  # noqa: ANN001, ANN202
    """The scripted web figure goes to the review queue; remove what these tests queued so the
    module that checks that queue later finds its own candidate (candidates are de-duplicated
    by source)."""
    from sqlalchemy import text

    yield
    if _ASKED:
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


def _ask(client, content: str, **extra: Any) -> dict[str, Any]:  # noqa: ANN001
    response = client.post(
        f"{API}/assistant/guest/messages",
        json={"content": content, "language": "en", "request_id": str(uuid.uuid4()),
              "data_mode": "synthetic", **extra},
    )  # fmt: skip
    assert response.status_code == 201, response.text
    _ASKED.append(response.json()["message"]["id"])
    return response.json()


def _number(evidence_id: str) -> int:
    return int(evidence_id[1:])


def test_numbers_start_with_approved_data_and_recent_questions_may_search_first(app) -> None:  # noqa: ANN001
    client = _guest(app)
    numeric = _ask(client, "web electricity generation 2023")["message"]
    method = numeric["structured"]["method"]
    assert method["route"] == {"numerical": True, "recent": False, "web_first": False}
    search = next(e for e in numeric["evidence"] if e["kind"] == "search")
    assert _number(search["id"]) > 1, "the platform's data were looked up before the web"
    recent = _ask(client, "web news about electricity today")["message"]
    assert recent["structured"]["method"]["route"]["web_first"] is True
    first_search = next(e for e in recent["evidence"] if e["kind"] == "search")
    assert first_search["id"] == "E1", "a question about recent events may search first"
    assert all(e.get("data_status") for e in numeric["evidence"]), "every item states its status"


def test_the_fallback_answers_only_after_the_primary_fails_and_calls_are_recorded(
    app, db, monkeypatch
) -> None:  # noqa: ANN001
    from app.models import ProviderCall

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "openai")
    monkeypatch.setattr(s, "openai_api_key", SecretStr("sk-integration-test-only"))
    monkeypatch.setattr(s, "openai_model", "configured-model")
    monkeypatch.setattr(s, "assistant_fallback_provider", "fake")

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no answer", request=request)

    monkeypatch.setattr(
        answer,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(slow)),
    )
    client = _guest(app)
    body = _ask(client, "What is the latest electricity generation?")
    method = body["message"]["structured"]["method"]
    assert body["message"]["status"] == "answered" and method["answer_provider"] == "fake"
    assert method["answer_fallback"] == {"from": "openai", "to": "fake", "reason": "timeout"}
    assert body["allowance"]["used"] == 1
    with db.begin():
        rows = db.scalars(select(ProviderCall).where(ProviderCall.provider == "openai")).all()
    assert [r.status for r in rows][-2:] == ["timeout", "timeout"]  # one retry, then the fallback
    assert all(r.capability == "answer" and r.input_tokens is None for r in rows[-2:])


def test_the_daily_limit_refuses_the_call_and_the_guest_is_not_charged(app, monkeypatch) -> None:  # noqa: ANN001
    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "openai")
    monkeypatch.setattr(s, "openai_api_key", SecretStr("sk-integration-test-only"))
    monkeypatch.setattr(s, "openai_model", "configured-model")
    monkeypatch.setattr(s, "provider_daily_call_limit", 0)

    def never(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent over the limit")

    monkeypatch.setattr(
        answer,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(never)),
    )
    body = _ask(_guest(app), "What is the latest electricity generation?")
    assert body["message"]["status"] == "unavailable" and body["allowance"]["used"] == 0


def test_google_search_grounding_is_shown_apart_and_never_used_as_evidence(
    app, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "research_provider", "fake-gemini")
    client = _guest(app)
    body = _ask(client, "web electricity generation 2023")
    message = body["message"]
    grounded = message["structured"]["grounded_context"][0]
    assert grounded["attribution"] == "Grounding with Google Search"
    assert grounded["search_suggestions"] and "41,234" in grounded["text"]
    assert grounded["citations"][0]["source_class"] == "official"
    assert not [e for e in message["evidence"] if e["kind"] == "web"]
    assert "41,234" not in message["content"], "the answer does not use the grounded text"
    assert "shown below the answer" in message["content"]
    again = client.get(f"{API}/assistant/guest/conversations/{body['conversation_id']}").json()
    assert again["messages"][-1]["structured"]["grounded_context"][0]["text"] == grounded["text"]


def test_a_cross_check_uses_the_second_route_only_when_asked(app, monkeypatch) -> None:  # noqa: ANN001
    s = get_settings()
    monkeypatch.setattr(s, "research_fallback_provider", "fake-openai")
    client = _guest(app)
    plain = _ask(client, "web electricity generation 2023", mode="research")["message"]
    assert {e["provider"] for e in plain["evidence"] if e["kind"] == "web"} == {"fake-search"}
    checked = _ask(client, "web electricity generation 2023", mode="research", cross_check=True)[
        "message"
    ]
    roles = {(r["provider"], r["role"]) for r in checked["structured"]["method"]["search_routes"]}
    assert ("fake-openai", "cross_check") in roles and ("fake-search", "primary") in roles
    status = client.get(f"{API}/assistant/status").json()
    assert status["cross_check_available"] is True


def test_conflicting_sources_across_routes_are_each_reported_and_labelled(app, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "research_fallback_provider", "fake-openai")
    msg = _ask(
        _guest(app), "Is there a conflict in electricity generation figures?",
        mode="research", cross_check=True,
    )["message"]  # fmt: skip
    assert msg["status"] == "answered", msg["content"]
    # Both values are reported, each with its own source; neither is presented as approved data.
    [conflict] = msg["structured"]["conflicts"]
    assert [v["value_text"] for v in conflict["values"]] == ["41,234", "40,000"]
    web = {e["id"]: e for e in msg["evidence"] if e["kind"] == "web"}
    for v in conflict["values"]:
        assert web[v["evidence_id"]]["data_status"] == "unreviewed_external"
    assert {web[v["evidence_id"]]["source_class"] for v in conflict["values"]} == {
        "official", "secondary",
    }  # fmt: skip
    # The cross-check route ran and is labelled; its provider summary (agreeing with one of
    # the values) was seen but is not cited as confirming it.
    method = msg["structured"]["method"]
    assert ("fake-openai", "cross_check") in {
        (r["provider"], r["role"]) for r in method["search_routes"]
    }
    assert method["provider_summaries"] == 1
    assert not [e for e in msg["evidence"] if e.get("content_kind") == "provider_summary"]


def test_an_unsupported_figure_is_withheld_not_shown(app) -> None:  # noqa: ANN001
    body = _ask(_guest(app), "invent the latest electricity generation")
    assert (
        body["message"]["status"] == "unverified" and "123456789" not in body["message"]["content"]
    )
    assert body["allowance"]["used"] == 0


def test_provider_readiness_and_live_test_are_for_administrators_only(
    app, make_user, login, monkeypatch
) -> None:  # noqa: ANN001
    from app.domain.enums import Role

    s = get_settings()
    monkeypatch.setattr(s, "openai_api_key", SecretStr("sk-integration-test-only"))
    monkeypatch.setattr(s, "openai_model", "configured-model")
    reply = {"status": "completed", "output": [
        {"type": "function_call", "call_id": "c1", "name": "final_answer", "arguments": "{\"status\": \"answered\"}"},
    ], "usage": {"input_tokens": 12, "output_tokens": 3}}  # fmt: skip
    monkeypatch.setattr(
        answer,
        "http_client_factory",
        lambda timeout: httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply))
        ),
    )
    from app.domain.enums import Permission

    viewer = login(make_user(Role.VIEWER))
    assert viewer.get(f"{API}/admin/providers").status_code == 403
    assert viewer.post(f"{API}/admin/providers/openai/test").status_code == 403
    # Reading the view is not enough to make a live (billable) call: that needs an administrator.
    auditor = login(make_user(Role.VIEWER, grants=(Permission.AUDIT_READ,)))
    assert auditor.get(f"{API}/admin/providers").status_code == 200
    assert auditor.post(f"{API}/admin/providers/openai/test").status_code == 403
    admin = login(make_user(Role.ADMINISTRATOR))
    view = admin.get(f"{API}/admin/providers").json()
    assert [p["provider"] for p in view["providers"]] == ["anthropic", "openai", "gemini", "brave"]
    assert view["routing"]["answer"]["primary"] == "fake"
    assert "sk-integration" not in str(view)
    tested = admin.post(f"{API}/admin/providers/openai/test?capability=answer").json()
    assert tested["status"] == "ok" and tested["readiness"]["status"] == "tested"
    assert tested["readiness"]["last_test"]["capability"] == "test_answer"
    unsupported = admin.post(f"{API}/admin/providers/brave/test?capability=answer").json()
    assert unsupported["status"] == "unsupported"


def test_expired_grounded_results_are_purged_from_stored_replies(db, make_user) -> None:  # noqa: ANN001
    from app.domain.enums import Role
    from app.models import AssistantConversation, AssistantMessage
    from app.services.assistant import service

    owner = make_user(Role.VIEWER)
    old = (datetime.now(UTC) - timedelta(days=800)).isoformat()
    with db.begin():
        conv = AssistantConversation(
            title="t", language="en", data_mode="synthetic", user_id=owner.id
        )
        db.add(conv)
        db.flush()
        msg = AssistantMessage(
            conversation_id=conv.id, role="assistant", content="answer", status="answered",
            structured={"grounded_context": [{"text": "old", "stored_at": old}], "method": {}},
        )  # fmt: skip
        db.add(msg)
    with db.begin():
        assert service.purge_grounded(db) >= 1
    with db.begin():
        stored = db.get(AssistantMessage, msg.id)
        assert "grounded_context" not in stored.structured and stored.content == "answer"
