"""A conversation as the conversation page has it, through the real guest endpoint with the
scripted FakeProvider standing in for the model: a greeting is answered without a data lookup
or a charge; a question and then a follow-up that names no indicator ("Compare it with the
previous year") keeps the topic, because the earlier turns reach the model; "auto" is stored
as the inferred mode."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture
def client(app, monkeypatch) -> Any:  # noqa: ANN001
    from fastapi.testclient import TestClient

    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    settings = get_settings()
    monkeypatch.setattr(settings, "assistant_provider", "fake")
    for name in (
        "guest_asks_per_minute",
        "guest_asks_per_client_hour",
        "guest_sessions_per_client_hour",
    ):
        monkeypatch.setattr(settings, name, 1000)
    ratelimit.reset()
    with session_factory()() as s:
        seed_booklet_fixtures(s)
    c = TestClient(app)
    c.get(f"{API}/assistant/guest")
    c.headers["X-Guest-CSRF"] = c.cookies["osrip_guest_csrf"]
    return c


def _ask(client: Any, content: str, conversation: str | None) -> dict[str, Any]:
    response = client.post(f"{API}/assistant/guest/messages", json={
        "content": content, "language": "en", "request_id": str(uuid.uuid4()),
        "data_mode": "synthetic", "mode": "auto", "conversation_id": conversation,
    })  # fmt: skip
    assert response.status_code == 201, response.text
    return response.json()


def test_greeting_question_and_context_dependent_follow_up(client: Any) -> None:
    greeting = _ask(client, "Hello", None)
    assert greeting["message"]["status"] == "profile"
    assert greeting["message"]["evidence"] == []  # no statistical lookup for a greeting
    conversation = greeting["conversation_id"]
    remaining = greeting["allowance"]["remaining"]

    first = _ask(client, "What is the latest electricity generation?", conversation)
    assert first["message"]["status"] == "answered"
    assert first["message"]["mode"] == "ask"
    assert "50100" in first["message"]["content"]
    assert first["allowance"]["remaining"] == remaining - 1

    follow_up = _ask(client, "Compare it with the previous year.", conversation)
    message = follow_up["message"]
    assert message["status"] == "answered"
    assert message["mode"] == "compare"  # inferred from the words, stored as such
    assert [(e["indicator"], e["period_start"], e["value"]) for e in message["evidence"]] == [
        ("ELEC_GENERATION", "2001-01-01", "48000"),
        ("ELEC_GENERATION", "2002-01-01", "50100"),
    ]
    assert "2001" in message["content"] and "2002" in message["content"]


def test_without_the_ai_a_follow_up_keeps_its_topic_in_the_data_based_report(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.assistant import provider

    first = _ask(client, "What is the latest electricity generation?", None)
    assert first["message"]["status"] == "answered"
    remaining = first["allowance"]["remaining"]

    def unavailable(self, system, messages, tools):  # noqa: ANN001, ANN202
        raise provider.ProviderError("http_503")

    monkeypatch.setattr(provider.FakeProvider, "complete", unavailable)
    follow_up = _ask(client, "Compare it with the previous year.", first["conversation_id"])
    message = follow_up["message"]
    assert message["status"] == "data_report"  # labelled, without AI interpretation
    assert follow_up["allowance"]["remaining"] == remaining  # a failed answer is not charged
    # The topic came from the earlier question: electricity figures, not "no topic named".
    assert {
        e.get("indicator", "")[:5] for e in message["evidence"] if e["kind"] == "observation"
    } == {"ELEC_"}
