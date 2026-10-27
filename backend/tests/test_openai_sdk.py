"""OpenAI through the official SDK (``app.services.openai_api``), without network: requests
follow the Responses API documentation (checked 2026-10-26 on developers.openai.com), streamed
calls end when the person stops the question, structured replies are refused when the model
refuses or stops early, quota errors are not retried, and no error message (which could echo
part of a key) is kept. Response payloads are written from the documented shapes; they are not
recorded live responses, and nothing here shows that a live OpenAI call works."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import openai_api, providers
from app.services.assistant import provider as answer
from app.services.assistant.progress import Cancelled
from app.services.research import search

ONE_TOOL = [
    {
        "name": "final_answer",
        "description": "Finish.",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
    }
]
TWO_TOOLS = [
    {"name": "get_observations", "description": "Data.", "input_schema": {"type": "object"}},
    *ONE_TOOL,
]
CALL = {
    "type": "function_call",
    "id": "fc_1",
    "call_id": "call_1",
    "name": "final_answer",
    "arguments": '{"text": "done"}',
}


@pytest.fixture(autouse=True)
def _memory(monkeypatch):  # noqa: ANN001, ANN202
    meter = providers.MemoryMeter()
    monkeypatch.setattr(providers, "meter", meter)
    s = get_settings()
    for name, value in (
        ("openai_api_key", SecretStr("sk-test-only-not-real-0000")),
        ("openai_model", "configured-openai-model"),
        ("openai_search_model", "configured-openai-search-model"),
        ("provider_daily_call_limit", 500),
        ("provider_daily_budget_usd", None),
        ("provider_prices", {}),
    ):
        monkeypatch.setattr(s, name, value)
    monkeypatch.setattr(answer, "RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(answer, "sleep", lambda seconds: None)
    return meter


def _serve(monkeypatch, module, handler) -> list[httpx.Request]:  # noqa: ANN001
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        module,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(wrapped)),
    )
    return seen


def _sse(*events: dict[str, Any]) -> httpx.Response:
    raw = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=raw.encode())


STARTED = {"id": "resp_1", "status": "in_progress", "output": []}


def _completed(output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "status": "completed",
        "output": output,
        "usage": {"input_tokens": 50, "output_tokens": 7},
    }


# ------------------------------------------------------------------ requests


def test_one_offered_tool_is_named_and_reasoning_effort_is_sent_when_configured() -> None:
    p = answer.OpenAIProvider("sk", "configured-openai-model", 5, "low")
    body = p._request("S", [{"role": "user", "content": "q"}], ONE_TOOL)
    assert body["tool_choice"] == {"type": "function", "name": "final_answer"}
    assert body["reasoning"] == {"effort": "low"}
    body = answer.OpenAIProvider("sk", "m", 5)._request(
        "S", [{"role": "user", "content": "q"}], TWO_TOOLS
    )
    assert body["tool_choice"] == "required" and "reasoning" not in body


def test_calls_go_through_the_sdk_to_the_responses_endpoint_with_the_server_key(
    monkeypatch, _memory
) -> None:  # noqa: ANN001
    seen = _serve(monkeypatch, answer, lambda r: httpx.Response(200, json=_completed([CALL])))
    reply = answer.OpenAIProvider("sk-test", "configured-openai-model", 5).complete(
        "S", [{"role": "user", "content": "q"}], TWO_TOOLS
    )
    assert reply["content"][0]["input"] == {"text": "done"}
    request = seen[0]
    assert (request.method, str(request.url)) == ("POST", "https://api.openai.com/v1/responses")
    assert request.headers["authorization"] == "Bearer sk-test"
    sent = json.loads(request.content)
    assert sent["store"] is False and "stream" not in sent, "not streamed without a stop check"
    assert _memory.rows[-1]["status"] == "ok"


# ------------------------------------------------------------------ streaming and stopping


def test_a_streamed_call_returns_the_same_reply_as_an_unstreamed_one(monkeypatch, _memory) -> None:  # noqa: ANN001
    events = (
        {"type": "response.created", "sequence_number": 0, "response": STARTED},
        {"type": "response.function_call_arguments.delta", "sequence_number": 1,
         "item_id": "fc_1", "output_index": 0, "delta": "{"},
        {"type": "response.completed", "sequence_number": 2, "response": _completed([CALL])},
    )  # fmt: skip
    seen = _serve(monkeypatch, answer, lambda r: _sse(*events))
    checks: list[int] = []
    token = answer.stop_check.set(lambda: checks.append(1))
    try:
        reply = answer.OpenAIProvider("sk", "m", 5).complete(
            "S", [{"role": "user", "content": "q"}], TWO_TOOLS
        )
    finally:
        answer.stop_check.reset(token)
    assert json.loads(seen[0].content)["stream"] is True
    assert reply["content"][0] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "final_answer",
        "input": {"text": "done"},
    }
    assert reply["content"][-1]["items"] == [CALL], "the output items are kept for the next turn"
    row = _memory.rows[-1]
    assert (row["status"], row["input_tokens"], row["output_tokens"]) == ("ok", 50, 7)


def test_stopping_the_question_ends_a_streamed_call_and_is_recorded_without_retry(
    monkeypatch, _memory
) -> None:  # noqa: ANN001
    events = (
        {"type": "response.created", "sequence_number": 0, "response": STARTED},
        {"type": "response.completed", "sequence_number": 1, "response": _completed([CALL])},
    )  # fmt: skip
    seen = _serve(monkeypatch, answer, lambda r: _sse(*events))
    monkeypatch.setattr(openai_api, "STOP_CHECK_SECONDS", 0)

    def stopped() -> None:
        raise Cancelled

    token = answer.stop_check.set(stopped)
    try:
        with pytest.raises(Cancelled):
            answer.OpenAIProvider("sk", "m", 5).complete(
                "S", [{"role": "user", "content": "q"}], TWO_TOOLS
            )
    finally:
        answer.stop_check.reset(token)
    assert len(seen) == 1, "a stopped call is not retried"
    assert [r["status"] for r in _memory.rows] == ["cancelled"]


def test_a_stream_error_event_is_a_provider_error(monkeypatch) -> None:  # noqa: ANN001
    _serve(
        monkeypatch,
        answer,
        lambda r: _sse(
            {
                "type": "error",
                "sequence_number": 0,
                "code": "server_error",
                "message": "x",
                "param": None,
            }
        ),
    )
    token = answer.stop_check.set(lambda: None)
    try:
        with pytest.raises(answer.ProviderError, match="stream_error") as caught:
            answer.OpenAIProvider("sk", "m", 5).complete(
                "S", [{"role": "user", "content": "q"}], TWO_TOOLS
            )
    finally:
        answer.stop_check.reset(token)
    assert caught.value.detail == "server_error"


# ------------------------------------------------------------------ errors


def test_used_up_quota_is_not_retried_and_is_reported_as_balance_not_rate_limit(
    monkeypatch, _memory
) -> None:  # noqa: ANN001
    body = {
        "error": {
            "message": "You exceeded your current quota sk-abc...",
            "type": "insufficient_quota",
            "code": "credit_balance_exhausted",
        }
    }
    seen = _serve(monkeypatch, answer, lambda r: httpx.Response(429, json=body))
    with pytest.raises(answer.ProviderError) as caught:
        answer.OpenAIProvider("sk", "m", 5).complete(
            "S", [{"role": "user", "content": "q"}], TWO_TOOLS
        )
    assert (str(caught.value), caught.value.detail) == ("http_429", "insufficient_quota")
    assert len(seen) == 1, "retrying cannot restore a used-up quota"
    assert answer.failure_category("http_429", caught.value.detail) == "insufficient_balance"
    assert "sk-abc" not in repr(caught.value.__dict__), "the service's message is never kept"


def test_a_rate_limit_is_retried_once_after_retry_after(monkeypatch, _memory) -> None:  # noqa: ANN001
    waits: list[float] = []
    monkeypatch.setattr(answer, "sleep", waits.append)
    replies = iter(
        [
            httpx.Response(
                429,
                headers={"retry-after": "2"},
                json={
                    "error": {
                        "type": "requests",
                        "code": "rate_limit_exceeded",
                        "message": "slow down",
                    }
                },
            ),
            httpx.Response(200, json=_completed([CALL])),
        ]
    )
    seen = _serve(monkeypatch, answer, lambda r: next(replies))
    answer.OpenAIProvider("sk", "m", 5).complete("S", [{"role": "user", "content": "q"}], TWO_TOOLS)
    assert len(seen) == 2 and waits == [2.0]
    assert [r["status"] for r in _memory.rows] == ["http_429", "ok"]


def test_model_not_found_and_refused_key_are_safe_tokens(monkeypatch) -> None:  # noqa: ANN001
    _serve(
        monkeypatch,
        answer,
        lambda r: httpx.Response(
            404,
            json={
                "error": {
                    "message": "The model `x` does not exist",
                    "type": "invalid_request_error",
                    "code": "model_not_found",
                }
            },  # fmt: skip
        ),
    )
    with pytest.raises(answer.ProviderError) as caught:
        answer.OpenAIProvider("sk", "m", 5).complete(
            "S", [{"role": "user", "content": "q"}], TWO_TOOLS
        )
    assert (str(caught.value), caught.value.detail) == ("http_404", "model_not_found")
    assert answer.failure_category("http_404", "model_not_found") == "model_unavailable"


# ------------------------------------------------------------------ structured outputs

SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


def _message(part: dict[str, Any], status: str = "completed") -> dict[str, Any]:
    return {
        "status": status,
        "output": [{"type": "message", "role": "assistant", "content": [part]}],
        "usage": {"input_tokens": 9, "output_tokens": 3},
    }


def test_structured_reply_uses_a_strict_json_schema_and_is_metered(monkeypatch, _memory) -> None:  # noqa: ANN001
    seen = _serve(
        monkeypatch,
        answer,
        lambda r: httpx.Response(
            200,
            json=_message({"type": "output_text", "text": '{"summary": "ok"}', "annotations": []}),
        ),
    )
    value = answer.OpenAIProvider("sk", "m", 5).structured("S", "data", SCHEMA, "dataset_summary")
    assert value == {"summary": "ok"}
    sent = json.loads(seen[0].content)
    assert sent["text"] == {
        "format": {
            "type": "json_schema",
            "name": "dataset_summary",
            "schema": SCHEMA,
            "strict": True,
        }
    }
    assert "tools" not in sent and sent["store"] is False
    assert (_memory.rows[-1]["status"], _memory.rows[-1]["input_tokens"]) == ("ok", 9)


@pytest.mark.parametrize(
    ("reply", "code"),
    [
        (_message({"type": "refusal", "refusal": "I can't help with that."}), "refused"),
        (_message({"type": "output_text", "text": '{"summ', "annotations": []}, "incomplete"),
         "status_incomplete"),
        (_message({"type": "output_text", "text": "[1, 2]", "annotations": []}), "invalid_json"),
    ],
)  # fmt: skip
def test_a_refused_cut_or_non_object_structured_reply_is_never_data(
    monkeypatch, reply: dict[str, Any], code: str
) -> None:  # noqa: ANN001
    _serve(monkeypatch, answer, lambda r: httpx.Response(200, json=reply))
    with pytest.raises(answer.ProviderError, match=code):
        answer.OpenAIProvider("sk", "m", 5).structured("S", "data", SCHEMA, "dataset_summary")


def test_background_responses_can_be_cancelled(monkeypatch) -> None:  # noqa: ANN001
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"id": "resp_9", "object": "response", "status": "cancelled"}
        )

    factory = lambda timeout: httpx.Client(transport=httpx.MockTransport(handler))  # noqa: E731
    assert openai_api.cancel("sk", "resp_9", 5, factory) == "cancelled"
    assert str(seen[0].url) == "https://api.openai.com/v1/responses/resp_9/cancel"


# ------------------------------------------------------------------ web search route


def test_web_search_request_follows_the_documented_tool_options(monkeypatch) -> None:  # noqa: ANN001
    route = search.OpenAIWebSearch(
        "sk", "configured-openai-search-model", 30, context_size="high",
        allowed_domains=["https://ncsi.gov.om/", "data.gov.om"],
    )  # fmt: skip
    body = route.request("Oman electricity generation 2025", "ar")
    tool = body["tools"][0]
    assert tool["type"] == "web_search", "not the legacy web_search_preview"
    assert tool["user_location"]["country"] == "OM" and tool["search_context_size"] == "high"
    assert tool["filters"] == {"allowed_domains": ["ncsi.gov.om", "data.gov.om"]}
    assert body["tool_choice"] == "required" and body["store"] is False
    assert body["include"] == ["web_search_call.action.sources"]
    assert "Arabic" in body["instructions"]
    assert "filters" not in search.OpenAIWebSearch("sk", "m", 30).request("q", "en")["tools"][0]


def test_web_search_keeps_citations_first_then_consulted_sources_without_text(
    monkeypatch, _memory
) -> None:  # noqa: ANN001
    text = "Gross generation was 31,732.5 GWh in January to July 2026."
    reply = {
        "status": "completed",
        "output": [
            {"type": "web_search_call", "id": "ws_1", "status": "completed",
             "action": {"type": "search", "query": "Oman electricity", "sources": [
                 {"type": "url", "url": "https://www.ncsi.gov.om/news/366"},
                 {"type": "url", "url": "https://www.opwp.co.om/statement"},
                 {"type": "api", "name": "oai-finance"},
             ]}},
            {"type": "web_search_call", "id": "ws_2", "status": "completed",
             "action": {"type": "open_page", "url": "https://www.ncsi.gov.om/news/366"}},
            {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": [
                {"type": "url_citation", "url": "https://www.ncsi.gov.om/news/366", "title": "NCSI",
                 "start_index": 0, "end_index": len(text)},
            ]}]},
        ],
        "usage": {"input_tokens": 400, "output_tokens": 60},
    }  # fmt: skip
    seen = _serve(monkeypatch, search, lambda r: httpx.Response(200, json=reply))
    results = search.OpenAIWebSearch("sk", "configured-openai-search-model", 30).search(
        "Oman electricity", language="en", count=5
    )
    assert [(r.url, r.kind) for r in results] == [
        ("https://www.ncsi.gov.om/news/366", "provider_summary"),
        ("https://www.opwp.co.om/statement", "provider_source"),
    ]
    assert results[1].snippet == "", "nothing is said about a source until it is read"
    assert seen[0].headers["authorization"] == "Bearer sk"
    row = _memory.rows[-1]
    assert (row["provider"], row["capability"], row["status"]) == ("openai", "search", "ok")
    assert row["searches"] == 1, "only search actions are billed, not opening a page"


def test_a_failed_web_search_reports_its_code(monkeypatch) -> None:  # noqa: ANN001
    _serve(
        monkeypatch,
        search,
        lambda r: httpx.Response(401, json={"error": {"code": "invalid_api_key"}}),
    )
    with pytest.raises(search.SearchError, match="http_401"):
        search.OpenAIWebSearch("sk", "m", 30).search("q", language="en", count=3)
