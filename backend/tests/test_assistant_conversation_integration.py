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


def test_a_model_that_keeps_looking_up_must_answer_in_the_last_round(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seen live with DeepSeek: the evidence was there by the third round, but the model kept
    # looking the same figures up until the rounds ran out, and the answer was lost.
    from app.services.assistant import provider, service

    offered: list[list[str]] = []
    notes: list[list[str]] = []

    def keeps_looking(self, system, messages, tools):  # noqa: ANN001, ANN202
        offered.append([t["name"] for t in tools])
        last = messages[-1]["content"]
        notes.append([b["text"] for b in last if isinstance(last, list) and b["type"] == "text"])
        if len(tools) > 1:
            return {"content": [{
                "type": "tool_use", "id": f"t{len(offered)}", "name": "latest_period",
                "input": {"indicator": "ELEC_GENERATION"},
            }]}  # fmt: skip
        return provider.FakeProvider._final(
            "answered", "The latest value is published [E1].", ["E1"]
        )

    monkeypatch.setattr(provider.FakeProvider, "complete", keeps_looking)
    message = _ask(client, "What is the latest electricity generation?", None)["message"]
    assert message["status"] == "answered"
    assert len(offered) == service.MAX_ROUNDS
    assert all("latest_period" in names for names in offered[:-1])
    assert offered[-1] == ["final_answer"]
    assert notes[-1] == [service.LAST_ROUND] and not any(notes[1:-1])  # said in words too


def test_after_an_unanswered_question_the_next_one_is_asked_on_its_own(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seen live: an unrelated question was joined to the unanswered one before it, and the
    # model tried to answer both.
    from app.services.assistant import provider, service

    first = _ask(client, "What is the latest electricity generation?", None)
    conversation = first["conversation_id"]
    original = provider.FakeProvider.complete

    def unavailable(self, system, messages, tools):  # noqa: ANN001, ANN202
        raise provider.ProviderError("http_503")

    monkeypatch.setattr(provider.FakeProvider, "complete", unavailable)
    assert (
        _ask(client, "Compare it with the previous year.", conversation)["message"]["status"]
        == "data_report"
    )
    seen: list[list[dict[str, Any]]] = []

    def recording(self, system, messages, tools):  # noqa: ANN001, ANN202
        seen.append(list(messages))  # the list grows with later rounds
        return original(self, system, messages, tools)

    monkeypatch.setattr(provider.FakeProvider, "complete", recording)
    _ask(client, "What is the latest water production?", conversation)
    turns = [
        (m["role"], m["content"] if isinstance(m["content"], str) else m["content"][0]["text"])
        for m in seen[0]
    ]
    assert turns[-3:] == [
        ("user", "Compare it with the previous year."),
        ("assistant", service.UNANSWERED),
        ("user", "What is the latest water production?"),
    ]


def test_a_tool_call_with_broken_arguments_goes_back_to_the_model(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seen live with DeepSeek: one call's arguments were not JSON, and the whole answer failed.
    import json

    from app.services.assistant import provider, service

    sent: list[dict[str, Any]] = []

    def broken_once(self, system, messages, tools):  # noqa: ANN001, ANN202
        if (
            not sent
            and messages[-1]["role"] == "user"
            and isinstance(messages[-1]["content"], list)
        ):
            last = messages[-1]["content"]
            if last and last[0].get("type") == "tool_result":
                sent.append(json.loads(last[0]["content"]))
                return provider.FakeProvider._final(
                    "no_evidence", "The published data does not answer this.", []
                )
        return {"content": [{
            "type": "tool_use", "id": "t1", "name": "latest_period", "input": {},
            "invalid_arguments": True,
        }]}  # fmt: skip

    monkeypatch.setattr(provider.FakeProvider, "complete", broken_once)
    message = _ask(client, "What is the latest electricity generation?", None)["message"]
    assert sent == [{"error": "invalid_arguments", "message": service.INVALID_ARGUMENTS}]
    assert message["status"] == "no_evidence"  # an answer, not a failure
