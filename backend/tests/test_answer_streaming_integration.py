"""Streamed answers through the API and the database (the scripted model streams its answer in
pieces, as a model does): the checked sentences arrive as ``answer.segment`` events, in order,
after a ``writing`` stage and before the answer is checked and completed; together they are the
stored reply; an invented figure is never streamed."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.core.config import get_settings
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
        ("guest_asks_per_minute", 1000),
        ("guest_asks_per_client_hour", 1000),
        ("assistant_max_per_minute", 1000),
        ("assistant_max_per_hour", 1000),
        ("research_per_client_hour", 1000),
    ):
        monkeypatch.setattr(s, name, value)
    ratelimit.reset()


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _ask(client, content: str, rid: uuid.UUID, mode: str = "ask") -> dict[str, Any]:  # noqa: ANN001
    r = client.post(
        f"{API}/assistant/guest/messages",
        json={"content": content, "language": "en", "request_id": str(rid),
              "data_mode": "synthetic", "mode": mode},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()["message"]


def _events(client, rid: uuid.UUID) -> list[tuple[str, dict[str, Any]]]:  # noqa: ANN001
    out: list[tuple[str, dict[str, Any]]] = []
    with client.stream("GET", f"{API}/assistant/guest/requests/{rid}/events") as r:
        kind = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: ") and kind:
                out.append((kind, json.loads(line[6:])))
                if kind == "end":
                    break
    return out


def _streamed(events: list[tuple[str, dict[str, Any]]]) -> tuple[str, list[str]]:
    segments = [e["payload"] for k, e in events if k == "answer.segment"]
    assert [s["index"] for s in segments] == list(range(len(segments))), "in order"
    order = [k if k != "stage" else f"stage:{e['payload']['stage']}" for k, e in events]
    return "".join(s["text"] for s in segments), order


def test_the_answer_is_streamed_in_checked_sentences_before_it_completes(app) -> None:  # noqa: ANN001
    client = _guest(app)
    rid = uuid.uuid4()
    message = _ask(client, "What is the latest electricity generation?", rid)
    assert message["status"] == "answered"
    text, order = _streamed(_events(client, rid))
    assert text.strip() == message["content"].strip()
    first = order.index("answer.segment")
    assert order.index("stage:writing") < first < order.index("stage:checking")
    assert max(i for i, k in enumerate(order) if k == "answer.segment") < order.index(
        "study.completed"
    )


def test_an_invented_figure_is_never_streamed(app) -> None:  # noqa: ANN001
    client = _guest(app)
    rid = uuid.uuid4()
    message = _ask(client, "partly invent the latest electricity generation", rid)
    assert message["status"] == "answered" and message["structured"]["omitted_claims"] == 1
    text, _ = _streamed(_events(client, rid))
    assert "987654321" not in text and "987654321" not in message["content"]
    assert text.strip() == message["content"].strip()


def test_a_deep_research_report_streams_its_sections(app) -> None:  # noqa: ANN001
    client = _guest(app)
    rid = uuid.uuid4()
    message = _ask(client, "Write a report on electricity generation in 2023", rid, "research")
    assert message["status"] == "answered", message["content"]
    text, order = _streamed(_events(client, rid))
    assert order.count("answer.segment") >= 8, "sentence by sentence, not all at once"
    assert "## Summary" in text and "## Limitations and missing information" in text
    assert text.strip() == message["content"].strip()
