"""When the answer service fails, the question gets a data-based report without AI
interpretation: published records and OSRIP calculations with their evidence, a sanitized
server log line with the request id, no guest charge, and a retry that can still be
answered by the model. No request reaches a real model service."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.domain.enums import Role
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration

SECRET = "sk-ant-test-only-not-a-real-key"  # noqa: S105 - a fake value for the test


@pytest.fixture(autouse=True)
def synthetic(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    s = get_settings()
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    ratelimit.reset()
    with session_factory()() as session:
        seed_booklet_fixtures(session)  # idempotent: synthetic national series


@pytest.fixture
def user(make_user, login):  # noqa: ANN001, ANN201
    return login(make_user(Role.VIEWER))


def _conversation(client: Any, mode: str = "synthetic") -> str:
    r = client.post(f"{API}/assistant/conversations", json={"language": "en", "data_mode": mode})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ask(client: Any, conv: str, content: str, language: str = "en") -> dict[str, Any]:
    r = client.post(
        f"{API}/assistant/conversations/{conv}/messages",
        json={"content": content, "language": language, "request_id": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _anthropic_rejects_the_key(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    from app.core.config import get_settings
    from app.services.assistant import provider

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "anthropic")
    monkeypatch.setattr(s, "assistant_fallback_provider", None)
    monkeypatch.setattr(s, "anthropic_api_key", SecretStr(SECRET))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        # The service echoes part of the key in its message: it must never reach the log.
        return httpx.Response(
            401,
            json={
                "type": "error",
                "error": {"type": "authentication_error", "message": f"invalid x-api-key {SECRET}"},
            },
        )

    monkeypatch.setattr(
        provider,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout),
    )
    return seen


def test_an_invalid_key_gives_a_data_report_and_a_sanitized_log(user, monkeypatch, caplog) -> None:  # noqa: ANN001
    seen = _anthropic_rejects_the_key(monkeypatch)
    caplog.set_level(logging.WARNING, logger="osrip.assistant")
    reply = _ask(user, _conversation(user), "What is the latest electricity generation?")

    assert seen, "the configured service was really called"
    assert reply["status"] == "data_report" and reply["ai_generated"] is False
    assert reply["model"] is None
    report = reply["structured"]["data_report"]
    assert report["category"] == "authentication" and report["sufficient"] is True
    assert report["label"]["en"] == "Data-based report without AI interpretation"
    assert report["web_search"] == "not_attempted"
    assert report["data_last_updated"]  # when the reported data were published
    assert "data-based report without AI interpretation" in reply["content"]

    # Every figure in the text is a published value or an OSRIP calculation it cites.
    observations = {e["id"]: e for e in reply["evidence"] if e["kind"] == "observation"}
    assert observations and set(reply["citations"]) <= set(observations) | {
        c["id"] for c in reply["calculations"]
    }
    # The question names generation: it is reported first (other topics' series may follow).
    generation = [e for e in observations.values() if e["indicator"] == "ELEC_GENERATION"]
    assert generation, "the indicator the question names is reported"
    latest = max(generation, key=lambda e: e["period_start"])
    assert f"{Decimal(latest['value']):,f}".rstrip("0").rstrip(".") in reply["content"]
    # Each change is paired with its percentage over the same two published values.
    changes = [c for c in reply["calculations"] if c["calculation"] == "absolute_change"]
    percents = [c for c in reply["calculations"] if c["calculation"] == "percentage_change"]
    assert changes and all(c["status"] == "ok" and len(c["inputs"]) == 2 for c in changes)
    assert {tuple(c["inputs"]) for c in percents} <= {tuple(c["inputs"]) for c in changes}

    # One warning line with the request id and the service's error type, never the key.
    lines = [
        r.getMessage() for r in caplog.records if "assistant provider failed" in r.getMessage()
    ]
    assert len(lines) == 1
    assert "category=authentication" in lines[0] and "detail=authentication_error" in lines[0]
    assert "code=http_401" in lines[0] and f"request_id={report['incident']}" in lines[0]
    assert SECRET not in caplog.text and "x-api-key" not in caplog.text


def test_a_shortage_question_adds_the_balance_analysis(user, monkeypatch) -> None:  # noqa: ANN001
    _anthropic_rejects_the_key(monkeypatch)
    reply = _ask(user, _conversation(user), "Is there a water shortage?")
    assert reply["status"] == "data_report"
    studies = reply["structured"].get("studies") or []
    assert [s["kind"] for s in studies] == ["supply_balance"]
    assert reply["structured"]["data_report"]["domains"] == ["water"]


def test_arabic_report_and_missing_topic(user, monkeypatch) -> None:  # noqa: ANN001
    _anthropic_rejects_the_key(monkeypatch)
    conv = _conversation(user)
    arabic = _ask(user, conv, "ما آخر قيمة لتوليد الكهرباء؟", language="ar")
    assert arabic["status"] == "data_report"
    assert "دون تفسير بالذكاء الاصطناعي" in arabic["content"]
    # Nothing to report: no figures at all, only what is missing and what to do next.
    vague = _ask(user, conv, "How is it going?")
    report = vague["structured"]["data_report"]
    assert vague["status"] == "data_report" and report["sufficient"] is False
    assert vague["evidence"] == [] and vague["calculations"] == []
    assert not any(ch.isdigit() for ch in vague["content"])
    assert any("electricity" in m["en"] for m in report["missing"])
    assert any("administrator" in s["en"] for s in report["next_steps"])


def test_guests_are_not_charged_and_the_same_request_can_be_retried(app, monkeypatch) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "assistant_provider", "fake")
    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    key = str(uuid.uuid4())

    def ask(content: str) -> dict[str, Any]:
        r = client.post(
            f"{API}/assistant/guest/messages",
            json={"content": content, "language": "en", "request_id": key,
                  "data_mode": "synthetic"},
        )  # fmt: skip
        assert r.status_code == 201, r.text
        return r.json()

    failed = ask("please fail: electricity generation")
    assert failed["message"]["status"] == "data_report"
    assert failed["message"]["structured"]["data_report"]["sufficient"] is True
    assert failed["allowance"]["used"] == 0
    # The model works again: the same request is answered (released, not replayed).
    from app.services.assistant import provider

    original = provider.FakeProvider.complete

    def healthy(self, system, messages, tools):  # noqa: ANN001, ANN202
        for m in messages:
            for b in m["content"] if isinstance(m["content"], list) else []:
                if b.get("type") == "text":
                    b["text"] = b["text"].replace("please fail: ", "")
        return original(self, system, messages, tools)

    monkeypatch.setattr(provider.FakeProvider, "complete", healthy)
    again = ask("please fail: electricity generation")
    assert again["message"]["status"] == "answered" and again["allowance"]["used"] == 1
