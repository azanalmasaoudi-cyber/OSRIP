"""The evidence-grounded assistant: grounding, citations, missing data, permissions,
limits, deletion, read-only tools and model-service failures.

The model is replaced by (a) the scripted FakeProvider, which only repeats tool
results unless asked to invent, and (b) the real AnthropicProvider talking to an
httpx MockTransport, to test the HTTP contract and failure handling. No request
reaches a real model service.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_test_verified_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def verified_generation(database_url: str) -> None:
    """Two verified-source test values (placeholder source, test database only)."""
    from fastapi.testclient import TestClient

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.principal import Principal

    email, password = "assistant-manager@test.invalid", "pw-assistant-manager-000"
    with session_factory()() as s, s.begin():
        user = accounts.create_user(
            s,
            Principal(None, "t"),
            email=email,
            display_name="M",
            password=password,
            roles=[Role.DATA_MANAGER],
        )
        s.flush()
        for p in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), user.id, p)
    client = TestClient(create_app())
    client.post(f"{API}/auth/login", json={"email": email, "password": password})
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    source = register_test_verified_source(client)
    imp = upload_validate_approve(
        client,
        source,
        csv_bytes(
            "ELEC_GENERATION,OM-ZU,2022-01-01,2022-12-31,annual,GWh,4100.25,,,",
            "ELEC_GENERATION,OM-ZU,2023-01-01,2023-12-31,annual,GWh,4305.5,,,",
        ),
    )
    assert client.post(f"{API}/imports/{imp['id']}/publish").status_code == 200


@pytest.fixture
def fake(monkeypatch):  # noqa: ANN001, ANN201
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "assistant_provider", "fake")


@pytest.fixture
def dhofar(monkeypatch):  # noqa: ANN001, ANN201
    """Point the fake model's latest_period call at the Dhofar test series."""
    from app.services.assistant import provider

    original = provider.FakeProvider.complete

    def patched(self, system, messages, tools):  # noqa: ANN001, ANN202
        reply = original(self, system, messages, tools)
        for block in reply["content"]:
            if block.get("name") == "latest_period":
                block["input"]["area"] = "OM-ZU"
        return reply

    monkeypatch.setattr(provider.FakeProvider, "complete", patched)


@pytest.fixture
def user(make_user, login):  # noqa: ANN001, ANN201
    return login(make_user(Role.VIEWER))


def conversation(client, language: str = "en", mode: str = "verified_source") -> str:  # noqa: ANN001
    r = client.post(
        f"{API}/assistant/conversations", json={"language": language, "data_mode": mode}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def ask(client, conv: str, content: str, language: str = "en") -> dict[str, Any]:  # noqa: ANN001
    r = client.post(
        f"{API}/assistant/conversations/{conv}/messages",
        json={"content": content, "language": language},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ fake model


def test_answer_cites_published_evidence_with_its_source(
    user, fake, monkeypatch, verified_generation
) -> None:  # noqa: ANN001
    from app.services.assistant import provider

    # Point the fake at the Dhofar test series.
    original = provider.FakeProvider.complete

    def dhofar(self, system, messages, tools):  # noqa: ANN001, ANN202
        reply = original(self, system, messages, tools)
        for block in reply["content"]:
            if block.get("name") == "latest_period":
                block["input"]["area"] = "OM-ZU"
        return reply

    monkeypatch.setattr(provider.FakeProvider, "complete", dhofar)
    conv = conversation(user)
    reply = ask(user, conv, "What is the latest electricity generation?")
    assert reply["status"] == "answered" and reply["ai_generated"] is True
    assert "4305.5" in reply["content"] and reply["citations"]
    [evidence] = reply["evidence"]
    assert evidence["id"] == reply["citations"][0]
    assert evidence["value"] == "4305.5" and evidence["period_start"] == "2023-01-01"
    assert evidence["source"]["url"] == "https://example.invalid/test-table.csv"
    assert evidence["data_mode"] == "verified_source" and evidence["dataset_version"]


def test_arabic_question_gets_an_arabic_answer(
    user, fake, monkeypatch, verified_generation
) -> None:  # noqa: ANN001
    from app.services.assistant import provider

    original = provider.FakeProvider.complete

    def dhofar(self, system, messages, tools):  # noqa: ANN001, ANN202
        reply = original(self, system, messages, tools)
        for block in reply["content"]:
            if block.get("name") == "latest_period":
                block["input"]["area"] = "OM-ZU"
        return reply

    monkeypatch.setattr(provider.FakeProvider, "complete", dhofar)
    reply = ask(user, conversation(user, "ar"), "ما آخر قيمة لتوليد الكهرباء؟", "ar")
    assert reply["status"] == "answered" and "آخر قيمة منشورة" in reply["content"]


def test_an_invented_number_is_withheld_and_the_evidence_shown(
    user, fake, dhofar, verified_generation
) -> None:  # noqa: ANN001
    reply = ask(user, conversation(user), "Invent the latest electricity generation")
    assert reply["status"] == "unverified"
    assert "123456789" not in reply["content"]
    assert reply["evidence"], "the retrieved evidence is shown instead"


def test_missing_evidence_is_explained_not_zero(user, fake) -> None:  # noqa: ANN001
    reply = ask(user, conversation(user), "What is the latest water production?")
    assert reply["status"] == "no_evidence" and "no published data" in reply["content"].lower()
    assert reply["citations"] == [] and "0" not in reply["content"]


def test_ambiguous_questions_get_a_clarifying_question(user, fake) -> None:  # noqa: ANN001
    reply = ask(user, conversation(user), "How did it change?")
    assert reply["status"] == "clarification" and reply["content"].endswith("?")


def test_model_failure_gives_a_retryable_unavailable_reply(user, fake) -> None:  # noqa: ANN001
    reply = ask(user, conversation(user), "please fail")
    assert reply["status"] == "unavailable" and reply["ai_generated"] is False


def test_not_configured_is_reported(user, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "assistant_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    status = user.get(f"{API}/assistant/status").json()
    assert status["configured"] is False and status["fallback"] == "lookup"
    # The labelled non-AI lookup: says it is not an AI answer, and is not AI-generated.
    reply = ask(user, conversation(user), "anything")
    assert reply["status"] == "lookup" and reply["ai_generated"] is False
    assert "No AI answer service is configured" in reply["content"]
    assert reply["evidence"] == []  # no topic named: guidance only, no records
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    with session_factory()() as s:
        seed_booklet_fixtures(s)  # idempotent; synthetic national electricity series
    topic = ask(user, conversation(user, mode="synthetic"), "electricity generation please")
    assert topic["status"] == "lookup" and "was not written by AI" in topic["content"]
    assert topic["evidence"] and topic["citations"] == [e["id"] for e in topic["evidence"]]
    assert all(e["evidence_class"] == "observed" for e in topic["evidence"])
    assert {e["data_mode"] for e in topic["evidence"]} == {"synthetic"}


# ------------------------------------------------------------------ permissions, limits, deletion


def test_conversations_are_private_and_deletable(user, fake, make_user, login, anonymous) -> None:  # noqa: ANN001
    conv = conversation(user)
    ask(user, conv, "How did it change?")
    other = login(make_user(Role.VIEWER))
    assert other.get(f"{API}/assistant/conversations/{conv}").status_code == 404
    assert other.delete(f"{API}/assistant/conversations/{conv}").status_code == 404
    assert anonymous.post(f"{API}/assistant/conversations", json={}).status_code == 401
    assert len(user.get(f"{API}/assistant/conversations/{conv}").json()["messages"]) == 2
    assert user.delete(f"{API}/assistant/conversations/{conv}").status_code == 204
    assert user.get(f"{API}/assistant/conversations/{conv}").status_code == 404
    assert conv not in {c["id"] for c in user.get(f"{API}/assistant/conversations").json()}


def test_accounts_without_the_permission_are_refused(make_user, login) -> None:  # noqa: ANN001
    no_role = login(make_user())
    assert no_role.post(f"{API}/assistant/conversations", json={}).status_code == 403


def test_requests_are_limited_per_user(user, fake, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "assistant_max_per_minute", 2)
    conv = conversation(user)
    ask(user, conv, "How did it change?")
    ask(user, conv, "How did it change?")
    r = user.post(f"{API}/assistant/conversations/{conv}/messages", json={"content": "again"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "assistant_rate_limited"


def test_overlong_messages_are_refused(user, fake) -> None:  # noqa: ANN001
    conv = conversation(user)
    r = user.post(f"{API}/assistant/conversations/{conv}/messages", json={"content": "x" * 1500})
    assert r.status_code == 422


def test_the_assistant_cannot_write(fake, monkeypatch, verified_generation) -> None:  # noqa: ANN001
    """Tool calls run in a READ ONLY transaction: even a tool that tried to write fails."""
    from app.domain.enums import DataMode
    from app.services.assistant import service, tools

    attempts: list[str] = []

    def writing_tool(self, indicator, area="OM"):  # noqa: ANN001, ANN202
        try:
            self.session.execute(text("UPDATE app_user SET display_name = 'hacked'"))
        except Exception as exc:  # noqa: BLE001
            attempts.append(type(exc.__cause__ or exc).__name__)
        return {"status": "no_data", "message": "none"}

    monkeypatch.setattr(tools.Tools, "latest_period", writing_tool)
    final, _, _ = service._run_model(
        "latest electricity generation", [], "en", DataMode.VERIFIED_SOURCE
    )
    assert attempts == ["ReadOnlySqlTransaction"]
    assert final["status"] == "no_evidence"


# ------------------------------------------------------------------ real provider, mocked HTTP


def _anthropic(monkeypatch, handler) -> None:  # noqa: ANN001
    from app.core.config import get_settings
    from app.services.assistant import provider

    monkeypatch.setattr(get_settings(), "assistant_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("test-key"))
    monkeypatch.setattr(
        provider,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout),
    )


def test_anthropic_tool_loop_and_request_contract(user, monkeypatch, verified_generation) -> None:  # noqa: ANN001
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"headers": dict(request.headers), "body": body})
        if len(seen) == 1:
            return httpx.Response(
                200,
                json={
                    "stop_reason": "tool_use",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "a",
                            "name": "compare_periods",
                            "input": {
                                "indicator": "ELEC_GENERATION",
                                "area": "OM-ZU",
                                "period_a_start": "2022-01-01",
                                "period_b_start": "2023-01-01",
                            },
                        }
                    ],
                },
            )
        results = json.loads(body["messages"][-1]["content"][0]["content"])
        pct = next(r for r in results["results"] if r["calculation"] == "percentage_change")
        return httpx.Response(
            200,
            json={
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "b",
                        "name": "final_answer",
                        "input": {
                            "status": "answered",
                            "text": f"Generation rose by {float(pct['value']):.2f}% from 2022 to 2023 [{pct['id']}].",
                            "citations": [pct["id"]],
                        },
                    }
                ],
            },
        )

    _anthropic(monkeypatch, handler)
    reply = ask(user, conversation(user), "Compare Dhofar electricity generation 2022 and 2023")
    assert reply["status"] == "answered", reply
    assert (
        "5.01%" in reply["content"]
    )  # 100 * (4305.5 - 4100.25) / 4100.25 = 20525 / 4100.25 = 5.00579...
    [calc] = [c for c in reply["calculations"] if c["calculation"] == "percentage_change"]
    assert calc["value"].startswith("5.005792") and len(calc["inputs"]) == 2
    assert {e["value"] for e in reply["evidence"]} == {
        "4100.25",
        "4305.5",
    }  # inputs shown for "How calculated"
    first = seen[0]
    assert first["headers"]["x-api-key"] == "test-key" and first["body"]["model"]
    assert first["body"]["tool_choice"] == {"type": "any"}
    assert "Never state a number" in first["body"]["system"]


@pytest.mark.parametrize("failure", ["http_500", "timeout", "not_json"])
def test_model_service_failures_become_unavailable(user, monkeypatch, failure: str) -> None:  # noqa: ANN001
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if failure == "not_json":
            return httpx.Response(200, text="<html>")
        return httpx.Response(500, json={"error": "overloaded"})

    _anthropic(monkeypatch, handler)
    reply = ask(user, conversation(user), "latest electricity generation")
    assert reply["status"] == "unavailable"
    assert "not available" in reply["content"]
