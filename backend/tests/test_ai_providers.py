"""The governed AI and research service, without a database or network: the OpenAI (Responses)
and Gemini (Interactions) adapters translate OSRIP's tool loop and their documented response
shapes; timeouts, refusals and limits are recorded; search routes keep provider citations and
Google's search suggestions; Grounding with Google Search stays display-only; the routing policy
puts approved data first; every evidence item states its data status; readiness never shows a
secret. Response payloads below follow the shapes in the providers' official documentation
(checked 10 October 2026); they are not recorded live responses."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.domain.enums import DataMode
from app.services import providers
from app.services.assistant import provider as answer
from app.services.assistant import routing
from app.services.assistant.tools import Ledger, Tools, run_tool
from app.services.research import search
from app.services.research import service as research

TOOLS = [
    {
        "name": "get_observations",
        "description": "Published values.",
        "input_schema": {"type": "object", "properties": {"indicator": {"type": "string"}}},
    },
    {
        "name": "final_answer",
        "description": "Finish.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


@pytest.fixture(autouse=True)
def _memory(monkeypatch):  # noqa: ANN001, ANN202
    meter = providers.MemoryMeter()
    monkeypatch.setattr(providers, "meter", meter)
    s = get_settings()
    for name, value in (
        ("openai_api_key", SecretStr("sk-test-only-not-real-0000")),
        ("openai_model", "configured-openai-model"),
        ("openai_search_model", "configured-openai-search-model"),
        ("gemini_api_key", SecretStr("gm-test-only-not-real-0000")),
        ("gemini_model", "configured-gemini-model"),
        ("gemini_search_model", "configured-gemini-search-model"),
        ("provider_daily_call_limit", 500),
        ("provider_daily_budget_usd", None),
        ("provider_prices", {}),
    ):
        monkeypatch.setattr(s, name, value)
    monkeypatch.setattr(answer, "RETRY_PAUSE_SECONDS", 0)
    return meter


def _transport(monkeypatch, module, handler) -> list[httpx.Request]:  # noqa: ANN001
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


# ------------------------------------------------------------------ OpenAI Responses API


def test_openai_request_uses_function_tools_only_and_replays_its_own_items() -> None:
    p = answer.OpenAIProvider("sk", "configured-openai-model", 5)
    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque"}
    call = {
        "type": "function_call",
        "id": "fc_1",
        "call_id": "call_1",
        "name": "get_observations",
        "arguments": "{}",
    }
    messages = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": [{"type": "text", "text": "What is the latest generation?"}]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "call_1", "name": "get_observations", "input": {}},
            {"type": "provider_state", "provider": "openai", "items": [reasoning, call]},
        ]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "{\"value\": 1}"}]},
    ]  # fmt: skip
    body = p._request("SYSTEM", messages, TOOLS)
    assert body["instructions"] == "SYSTEM" and body["tool_choice"] == "required"
    assert body["store"] is False and body["include"] == ["reasoning.encrypted_content"]
    assert {t["type"] for t in body["tools"]} == {"function"}, (
        "no code interpreter, file or web tool"
    )
    assert body["tools"][0]["parameters"] == TOOLS[0]["input_schema"]
    assert body["input"] == [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "What is the latest generation?"},
        reasoning,  # passed back exactly, with the call it belongs to
        call,
        {"type": "function_call_output", "call_id": "call_1", "output": '{"value": 1}'},
    ]


def test_openai_response_becomes_tool_calls_and_usage_is_recorded(monkeypatch, _memory) -> None:  # noqa: ANN001
    reply = {
        "status": "completed",
        "output": [
            {"type": "reasoning", "id": "rs_2", "encrypted_content": "x"},
            {"type": "function_call", "id": "fc_2", "call_id": "call_2", "name": "final_answer",
             "arguments": "{\"status\": \"answered\", \"text\": \"OK\"}"},
        ],
        "usage": {"input_tokens": 120, "output_tokens": 30},
    }  # fmt: skip
    seen = _transport(monkeypatch, answer, lambda r: httpx.Response(200, json=reply))
    p = answer.OpenAIProvider("sk-test", "configured-openai-model", 5)
    result = p.complete("S", [{"role": "user", "content": "q"}], TOOLS)
    tool = result["content"][0]
    assert tool == {
        "type": "tool_use",
        "id": "call_2",
        "name": "final_answer",
        "input": {"status": "answered", "text": "OK"},
    }
    assert result["content"][-1]["type"] == "provider_state"
    assert seen[0].url == "https://api.openai.com/v1/responses"
    assert seen[0].headers["Authorization"] == "Bearer sk-test"
    row = _memory.rows[-1]
    assert (row["provider"], row["capability"], row["status"], row["input_tokens"], row["output_tokens"]) == (
        "openai", "answer", "ok", 120, 30,
    )  # fmt: skip
    with pytest.raises(answer.ProviderError, match="status_incomplete"):
        answer.OpenAIProvider.parse({"status": "incomplete", "output": []})
    with pytest.raises(answer.ProviderError, match="invalid_arguments"):
        answer.OpenAIProvider.parse(
            {
                "output": [
                    {"type": "function_call", "call_id": "c", "name": "x", "arguments": "{not json"}
                ]
            }
        )


# ------------------------------------------------------------------ Gemini Interactions API


def test_gemini_request_sends_its_steps_back_exactly_and_names_results() -> None:
    p = answer.GeminiProvider("gm", "configured-gemini-model", 5)
    thought = {
        "type": "thought",
        "summary": [{"type": "text", "text": "check data"}],
        "signature": "SIG==",
    }
    call = {
        "type": "function_call",
        "id": "g1",
        "name": "get_observations",
        "arguments": {"indicator": "X"},
    }
    messages = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "g1", "name": "get_observations", "input": {"indicator": "X"}},
            {"type": "provider_state", "provider": "gemini", "items": [thought, call]},
        ]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "g1", "content": "{\"v\": 2}"}]},
    ]  # fmt: skip
    body = p._request("SYSTEM", messages, TOOLS)
    assert body["system_instruction"] == "SYSTEM" and body["tool_choice"] == "any"
    assert body["store"] is False
    assert {t["type"] for t in body["tools"]} == {"function"}, (
        "no code execution, no Google Search here"
    )
    assert body["input"] == [
        {"type": "user_input", "content": [{"type": "text", "text": "question"}]},
        thought,  # with its signature, as received
        call,
        {
            "type": "function_result",
            "call_id": "g1",
            "name": "get_observations",
            "result": '{"v": 2}',
        },
    ]


def test_gemini_response_steps_become_tool_calls_with_thought_tokens_counted(
    monkeypatch, _memory
) -> None:  # noqa: ANN001
    reply = {
        "status": "requires_action",
        "steps": [
            {"type": "thought", "summary": [], "signature": "S2"},
            {
                "type": "function_call",
                "id": "g2",
                "name": "final_answer",
                "arguments": {"status": "answered"},
            },
        ],
        "usage": {"total_input_tokens": 80, "total_output_tokens": 10, "total_thought_tokens": 15},
    }
    seen = _transport(monkeypatch, answer, lambda r: httpx.Response(200, json=reply))
    result = answer.GeminiProvider("gm-test", "configured-gemini-model", 5).complete(
        "S", [{"role": "user", "content": "q"}], TOOLS
    )
    assert result["content"][0] == {
        "type": "tool_use",
        "id": "g2",
        "name": "final_answer",
        "input": {"status": "answered"},
    }
    assert seen[0].url == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert seen[0].headers["x-goog-api-key"] == "gm-test"
    assert (_memory.rows[-1]["input_tokens"], _memory.rows[-1]["output_tokens"]) == (80, 25)


# ------------------------------------------------------------------ failures and limits


def test_timeouts_are_retried_once_then_reported_and_auth_errors_are_not_retried(
    monkeypatch, _memory
) -> None:  # noqa: ANN001
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    seen = _transport(monkeypatch, answer, slow)
    with pytest.raises(answer.ProviderError, match="timeout"):
        answer.OpenAIProvider("sk", "m", 1).complete("S", [{"role": "user", "content": "q"}], TOOLS)
    assert len(seen) == 2 and [r["status"] for r in _memory.rows] == ["timeout", "timeout"]
    seen = _transport(monkeypatch, answer, lambda r: httpx.Response(401, json={"error": {}}))
    with pytest.raises(answer.ProviderError, match="http_401"):
        answer.GeminiProvider("gm", "m", 1).complete("S", [{"role": "user", "content": "q"}], TOOLS)
    assert len(seen) == 1, "a refused key is not retried"


def test_daily_call_limit_and_budget_stop_calls_before_they_are_made(monkeypatch, _memory) -> None:  # noqa: ANN001
    s = get_settings()
    ok = {
        "status": "completed",
        "output": [],
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
    }
    seen = _transport(monkeypatch, answer, lambda r: httpx.Response(200, json=ok))
    monkeypatch.setattr(s, "provider_daily_call_limit", 1)
    p = answer.OpenAIProvider("sk", "m", 1)
    p.complete("S", [{"role": "user", "content": "q"}], TOOLS)
    with pytest.raises(answer.ProviderError, match="daily_limit"):
        p.complete("S", [{"role": "user", "content": "q"}], TOOLS)
    assert len(seen) == 1 and _memory.rows[-1]["status"] == "daily_limit"

    _memory.rows.clear()
    monkeypatch.setattr(s, "provider_daily_call_limit", 100)
    monkeypatch.setattr(
        s, "provider_prices", {"openai": {"input_per_mtok": 2.5, "output_per_mtok": 10}}
    )
    monkeypatch.setattr(s, "provider_daily_budget_usd", 2.0)
    p.complete("S", [{"role": "user", "content": "q"}], TOOLS)  # 1M input tokens = 2.50 USD
    assert _memory.rows[-1]["estimated_cost_usd"] == Decimal("2.500000")
    with pytest.raises(answer.ProviderError, match="budget_exhausted"):
        p.complete("S", [{"role": "user", "content": "q"}], TOOLS)
    assert providers.estimate_cost("gemini", 10, 10, 1) is None, "no prices: no guessed cost"


# ------------------------------------------------------------------ search routes


def test_openai_web_search_keeps_each_citation_with_its_url() -> None:
    text = "Electricity generation reached 41,234 GWh in 2023. A news site reported 40,000 GWh."
    body = {
        "output": [
            {"type": "web_search_call", "id": "ws_1", "status": "completed", "action": {"type": "search"}},
            {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": [
                {"type": "url_citation", "url": "https://www.ncsi.gov.om/bulletin", "title": "Bulletin",
                 "start_index": 0, "end_index": 50},
                {"type": "url_citation", "url": "https://news.example.com/a", "title": "News",
                 "start_index": 51, "end_index": len(text)},
                {"type": "url_citation", "url": "javascript:alert(1)", "title": "x", "start_index": 0, "end_index": 4},
            ]}]},
        ],
        "usage": {"input_tokens": 5, "output_tokens": 6},
    }  # fmt: skip
    results = search.openai_results(body, "configured-openai-search-model")
    assert [r.url for r in results] == [
        "https://www.ncsi.gov.om/bulletin",
        "https://news.example.com/a",
    ]
    assert results[0].snippet == "Electricity generation reached 41,234 GWh in 2023."
    assert results[1].snippet == "A news site reported 40,000 GWh."
    assert {r.kind for r in results} == {"provider_summary"} and results.searches == 1


def test_gemini_grounding_parses_byte_offsets_in_arabic_and_keeps_search_suggestions() -> None:
    first = "بلغ توليد الكهرباء 41,234 جيجاواط ساعة."
    text = first + " ورد ذلك في النشرة."
    end = len(first.encode("utf-8"))
    body = {
        "status": "completed",
        "steps": [
            {"type": "google_search_call", "id": "s1", "arguments": {"queries": ["توليد الكهرباء عمان 2023"]}},
            {"type": "google_search_result", "call_id": "s1", "result": [{"search_suggestions": "<div>chips</div>"}]},
            {"type": "model_output", "content": [{"type": "text", "text": text, "annotations": [
                {"type": "url_citation", "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                 "title": "ncsi.gov.om", "start_index": 0, "end_index": end},
            ]}]},
        ],
    }  # fmt: skip
    grounded = search.gemini_grounded(body, "configured-gemini-search-model")
    assert grounded.citations[0]["segment"] == first
    assert grounded.search_suggestions == ["<div>chips</div>"]
    assert grounded.queries == ["توليد الكهرباء عمان 2023"] and grounded.text == text
    cls = research._classify_citation(grounded.citations[0]["url"], grounded.citations[0]["title"])
    assert cls["source_class"] == "official", "a redirect is classified by the real domain"
    with pytest.raises(search.SearchError, match="status_failed"):
        search.gemini_grounded({"status": "failed"}, "m")


def _ledger(**kw: Any) -> Ledger:
    return Ledger(DataMode.SYNTHETIC, web_enabled=True, **kw)


def _routes(monkeypatch, primary: str, fallback: str = "") -> None:  # noqa: ANN001
    s = get_settings()
    monkeypatch.setattr(s, "research_provider", primary)
    monkeypatch.setattr(s, "research_fallback_provider", fallback)
    monkeypatch.setattr(s, "research_max_searches_per_answer", 6)


def test_google_search_grounding_is_shown_separately_and_never_given_to_the_model(
    monkeypatch,
) -> None:  # noqa: ANN001
    _routes(monkeypatch, "fake-gemini")
    ledger = _ledger()
    result = research.web_search(ledger, "electricity generation 2023", "electricity", None)
    assert result["status"] == "shown_separately" and "cannot see or use" in result["message"]
    assert "41,234" not in json.dumps(result), "no grounded text reaches the model"
    grounded = [i for i in ledger.items if i["kind"] == "grounded_context"]
    assert len(grounded) == 1 and grounded[0]["search_suggestions"] and grounded[0]["display_only"]
    assert grounded[0]["data_status"] == "unreviewed_external"
    assert not [i for i in ledger.items if i["kind"] == "web"]


def test_the_fallback_route_is_used_only_when_the_primary_fails(monkeypatch) -> None:  # noqa: ANN001
    _routes(monkeypatch, "fake", "fake-openai")
    ok = research.web_search(_ledger(), "electricity generation 2023", "electricity", None)
    assert ok["provider"] == "fake-search" and "fallback" not in ok and "cross_check" not in ok
    ledger = _ledger()
    failed_over = research.web_search(ledger, "fail electricity generation", "electricity", None)
    assert failed_over["fallback"] == {
        "from": "fake-search",
        "reason": "simulated_failure",
        "to": "fake-openai",
    }
    roles = [
        (i["provider"], i.get("role"), i["status"]) for i in ledger.items if i["kind"] == "search"
    ]
    assert roles == [("fake-search", "primary", "failed"), ("fake-openai", "fallback", "ok")]


def test_a_cross_check_runs_only_when_asked_and_says_agreement_is_not_independent(
    monkeypatch,
) -> None:  # noqa: ANN001
    _routes(monkeypatch, "fake", "fake-openai")
    ledger = _ledger(cross_check=True)
    result = research.web_search(ledger, "electricity generation 2023", "electricity", None)
    assert result["cross_check"]["status"] == "ok"
    assert "NOT independent confirmation" in result["cross_check"]["note"]
    providers_used = {i["provider"] for i in ledger.items if i["kind"] == "web"}
    assert providers_used == {"fake-search", "fake-openai"}


def test_planted_instructions_in_provider_summaries_stay_untrusted_and_never_reach_the_database(
    monkeypatch,
) -> None:  # noqa: ANN001
    _routes(monkeypatch, "fake-openai")
    ledger = _ledger()
    result = research.web_search(ledger, "inject electricity generation", "electricity", None)
    hit = result["results"][0]
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in hit["untrusted_snippet"]
    assert hit["content_kind"] == "provider_summary" and "untrusted" in result["note"].lower()
    item = ledger.by_id()[hit["evidence_id"]]

    class NoSession:
        def execute(self, *a: Any, **k: Any) -> None:
            raise AssertionError("a provider summary must not be queued")

        def scalar(self, *a: Any, **k: Any) -> None:
            raise AssertionError

    stored = research.queue_candidates(
        NoSession(),  # type: ignore[arg-type]
        [{"evidence_id": item["id"], "value_text": "41,234", "period_end": "2023-12-31"}],
        ledger.items, citations=[item["id"]], message_id=1, proposed_by=None, language="en",
    )  # fmt: skip
    assert stored == 0


# ------------------------------------------------------------------ routing and data status


@pytest.mark.parametrize(
    ("question", "numerical", "recent"),
    [
        ("What was electricity generation in 2023?", True, False),
        ("كم بلغ إنتاج المياه؟", True, False),
        ("What is the latest news about desalination today?", False, True),
        ("ما آخر الأخبار عن الأمن الغذائي اليوم؟", False, True),
        ("What does apparent food availability mean?", False, False),
    ],
)
def test_the_routing_policy_puts_approved_data_first_for_numbers(
    question: str, numerical: bool, recent: bool
) -> None:
    route = routing.classify(question)
    assert (route.numerical, route.recent) == (numerical, recent)
    assert route.web_first == (recent or not numerical)


def test_web_search_waits_for_a_data_lookup_on_numerical_questions() -> None:
    ledger = _ledger(web_first=False)
    tools = Tools(None, ledger)  # type: ignore[arg-type]
    assert tools.web_search("electricity generation 2023")["status"] == "data_first"

    class Probe(Tools):
        def get_observations(self, **kwargs: Any) -> dict[str, Any]:
            return {"series": []}

    run_tool(Probe(None, ledger), "get_observations", {})  # type: ignore[arg-type]
    assert ledger.data_lookups == 1
    assert Probe(None, ledger).web_search("x")["status"] != "data_first"  # type: ignore[arg-type]


def test_every_evidence_item_states_its_data_status() -> None:
    verified = Ledger(DataMode.VERIFIED_SOURCE)
    synthetic = Ledger(DataMode.SYNTHETIC)
    assert verified.add({"kind": "observation"})["data_status"] == "approved_official"
    assert synthetic.add({"kind": "observation"})["data_status"] == "synthetic_demonstration"
    for kind, status in (
        ("web", "unreviewed_external"), ("calculation", "calculated"), ("study", "calculated"),
        ("forecast", "model_forecast"), ("scenario", "assumption_scenario"), ("definition", "reference"),
    ):  # fmt: skip
        assert verified.add({"kind": kind})["data_status"] == status


# ------------------------------------------------------------------ readiness and live tests


def test_readiness_states_without_secrets(monkeypatch, _memory) -> None:  # noqa: ANN001
    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "openai")
    monkeypatch.setattr(s, "research_provider", "gemini")
    monkeypatch.setattr(s, "research_api_key", None)
    monkeypatch.setattr(s, "anthropic_api_key", None)
    states = {p["provider"]: p for p in providers.readiness()["providers"]}
    assert (
        states["openai"]["status"] == "configured" and "answer_primary" in states["openai"]["roles"]
    )
    assert states["anthropic"]["status"] == "unavailable"
    assert states["anthropic"]["capabilities"]["answer"]["missing"] == ["OSRIP_ANTHROPIC_API_KEY"]
    assert states["brave"]["capabilities"]["search"]["missing"] == ["OSRIP_RESEARCH_API_KEY"]
    dumped = json.dumps(providers.readiness())
    assert "sk-test-only" not in dumped and "gm-test-only" not in dumped

    _transport(monkeypatch, answer, lambda r: httpx.Response(200, json={
        "status": "completed",
        "output": [{"type": "function_call", "call_id": "c", "name": "final_answer", "arguments": "{}"}],
    }))  # fmt: skip
    tested = providers.run_test("openai", "answer")
    assert tested["status"] == "ok" and _memory.rows[-1]["capability"] == "test_answer"
    assert providers.state("openai")["status"] == "tested"
    _transport(monkeypatch, answer, lambda r: httpx.Response(503))
    assert providers.run_test("openai", "answer")["status"] == "http_503"
    assert providers.state("openai")["status"] == "failed"
    monkeypatch.setattr(s, "openai_model", None)
    refused = providers.run_test("openai", "answer")
    assert refused == {"provider": "openai", "capability": "answer", "status": "not_configured",
                       "missing": ["OSRIP_OPENAI_MODEL"]}  # fmt: skip


def test_grounded_results_expire_after_the_permitted_storage_period() -> None:
    from datetime import UTC, datetime, timedelta

    from app.services.assistant import service

    now = datetime.now(UTC)
    old = {"text": "old", "stored_at": (now - timedelta(days=800)).isoformat()}
    fresh = {"text": "new", "stored_at": (now - timedelta(days=10)).isoformat()}
    out = service._structured_out({"grounded_context": [old, fresh], "method": {}})
    assert out["grounded_context"] == [fresh]
    assert "grounded_context" not in service._structured_out({"grounded_context": [old]})
