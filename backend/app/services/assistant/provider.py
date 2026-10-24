"""Answering models for the assistant, each through its official API.

All of them speak OSRIP's internal format (Anthropic-style content blocks: ``text``,
``tool_use``, ``tool_result``) to the tool loop, so the loop, the deterministic tools and the
evidence check are the same whichever provider answers:

* ``AnthropicProvider``: Claude, Messages API (``OSRIP_ANTHROPIC_API_KEY``).
* ``OpenAIProvider``: Responses API with function tools (``OSRIP_OPENAI_API_KEY``,
  ``OSRIP_OPENAI_MODEL``); stateless (``store: false``): the output items of each turn
  (reasoning items included) are passed back with the tool results, as the function-calling
  guide requires. No built-in tool (code interpreter, file search, web search) is enabled here.
* ``GeminiProvider``: Interactions API with function tools (``OSRIP_GEMINI_API_KEY``,
  ``OSRIP_GEMINI_MODEL``); stateless: the model's steps (thoughts with their signatures,
  function calls) are sent back exactly as received. No code execution is enabled.
* ``DeepSeekProvider``: Chat Completions API (OpenAI-compatible) with function tools
  (``OSRIP_DEEPSEEK_API_KEY``, ``OSRIP_DEEPSEEK_MODEL``). Usage-billed per token from a
  topped-up balance, so it is built only when ``OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED=true``
  as well: a key alone never starts billing, as primary or as fallback. Thinking mode is
  switched off, because a required tool call is refused in thinking mode.
* ``FakeProvider``: a scripted test double; refused in production.

Keys stay on the server and are never sent to browsers. Model ids are configured, never
assumed. Each call is checked against the daily limits and recorded (``app.services.
providers``); provider-specific state travels in a ``provider_state`` block that only the
same provider reads.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.services import monitoring
from app.services import providers as registry

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
RETRY_PAUSE_SECONDS = 1.0
# A rate-limited call is retried once after the service's Retry-After, when it asks for at
# most this long; a longer wait fails at once (and the fallback provider, if any, answers).
MAX_RETRY_AFTER_SECONDS = 10.0
MAX_OUTPUT_TOKENS = 4096  # room for a final answer with cards, drivers and conflicts


class ProviderError(Exception):
    """The model service failed, timed out or returned something unusable.

    ``str(error)`` is the short code (``http_401``, ``timeout`` ...). ``detail`` is the
    service's own error type when it sent one (``authentication_error``, ``not_found_error``,
    ``UNAUTHENTICATED`` ...), reduced to a safe token: never a message, URL or key.
    """

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.detail = detail
        # Seconds the service asked us to wait (Retry-After on 429/503), when it said.
        self.retry_after: float | None = None
        # Set by the answer loop: who failed, and the evidence gathered before the failure.
        self.provider: str | None = None
        self.model: str | None = None
        self.ledger: Any = None


_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,40}")


def error_type(response_body: Any) -> str | None:
    """The provider's error type from a JSON error body (Anthropic ``error.type``, OpenAI
    ``error.code``/``error.type``, Gemini ``error.status``), or None. Only a short token of
    letters, digits and ``_.-`` is kept, so nothing the service echoes back (such as part of
    a key) can reach the logs."""
    error = response_body.get("error") if isinstance(response_body, dict) else None
    if not isinstance(error, dict):
        return None
    for key in ("type", "code", "status"):
        value = error.get(key)
        if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
            return value
    return None


def failure_category(code: str, detail: str | None = None) -> str:
    """One word for what went wrong, shown to users and administrators."""
    detail = (detail or "").lower()
    if code == "not_configured":
        return "not_configured"
    if code in ("http_401", "http_403") or "auth" in detail or "permission" in detail:
        return "authentication"
    if code == "http_404" or "not_found" in detail or "model" in detail:
        return "model_unavailable"
    if code == "http_429" or "rate_limit" in detail or "overloaded" in detail:
        return "rate_limited"
    if code in ("timeout",):
        return "timeout"
    if code in ("network", "dns_failed"):
        return "network"
    if code.startswith("http_5"):
        return "server_error"
    if code in ("daily_limit", "budget_exhausted", "http_402") or code.startswith("limit"):
        return "budget"  # 402: a usage-billed provider's balance is used up (DeepSeek)
    if code in ("invalid_json", "no_tool_call", "invalid_arguments", "too_many_rounds") or (
        code.startswith("status_")
    ):
        return "invalid_response"
    return "other"


class Provider(Protocol):
    name: str
    vendor: str

    def complete(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]: ...


# Injectable for tests (httpx.MockTransport, no waiting).
http_client_factory: Callable[[float], httpx.Client] = lambda timeout: httpx.Client(timeout=timeout)  # noqa: E731
sleep: Callable[[float], None] = time.sleep


def retry_after(response: httpx.Response) -> float | None:
    """Seconds from a Retry-After header in its delay form (an HTTP date is not trusted)."""
    value = response.headers.get("retry-after", "").strip()
    try:
        return max(0.0, float(value)) if value else None
    except ValueError:
        return None


def transient(code: str) -> bool:
    """Failures worth a retry, or a fallback provider: not configuration or request errors."""
    return code in ("timeout", "network", "http_429") or code.startswith("http_5")


def _post_json(
    url: str, body: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    try:
        with http_client_factory(timeout) as client:
            response = client.post(url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderError("timeout") from exc
    except httpx.HTTPError as exc:
        raise ProviderError("network") from exc
    if response.status_code != 200:
        try:
            detail = error_type(response.json())
        except ValueError:
            detail = None
        error = ProviderError(f"http_{response.status_code}", detail)
        error.retry_after = retry_after(response)
        raise error
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError("invalid_json") from exc


class _HttpProvider:
    """Retry once on transient failures; check limits first; record every call."""

    vendor = ""
    name = ""

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _parse(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        raise NotImplementedError

    def _request(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        raise NotImplementedError

    def complete(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
        capability: str = "answer",
    ) -> dict[str, Any]:  # fmt: skip
        try:
            registry.check(self.vendor, capability, self.name)
        except registry.LimitReached as exc:
            raise ProviderError(str(exc)) from exc
        body = self._request(system, messages, tools)
        for attempt in (1, 2):
            started = time.monotonic()
            try:
                result, usage = self._parse(self._call(body))
            except ProviderError as exc:
                code = str(exc)
                monitoring.external_failure("assistant", code)
                registry.record(self.vendor, capability, self.name, code, started)
                wait = exc.retry_after if exc.retry_after is not None else RETRY_PAUSE_SECONDS
                if attempt == 1 and transient(code) and wait <= MAX_RETRY_AFTER_SECONDS:
                    sleep(wait)
                    continue
                raise
            monitoring.external_success("assistant")
            registry.record(self.vendor, capability, self.name, "ok", started, **usage)
            return result
        raise ProviderError("unreachable")  # pragma: no cover


class AnthropicProvider(_HttpProvider):
    vendor = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.name = model
        self._key = api_key
        self._timeout = timeout

    def _request(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "model": self.name,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            # Provider state of other vendors never reaches Anthropic.
            "messages": [_without_state(m) for m in messages],
            "tools": tools,
            "tool_choice": {"type": "any"},  # every turn is a tool call; the last is final_answer
            "temperature": 0,
        }

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        return _post_json(
            ANTHROPIC_URL,
            body,
            {
                "x-api-key": self._key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            self._timeout,
        )

    def _parse(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        usage = body.get("usage") or {}
        return body, {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }


def _without_state(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, list):
        return {**message, "content": [b for b in content if b.get("type") != "provider_state"]}
    return message


def _state(message: dict[str, Any], vendor: str) -> list[dict[str, Any]] | None:
    content = message.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if block.get("type") == "provider_state" and block.get("provider") == vendor:
            return list(block.get("items") or [])
    return None


def _result_text(content: Any) -> str:
    return (
        content
        if isinstance(content, str)
        else json.dumps(content, ensure_ascii=False, default=str)
    )


class OpenAIProvider(_HttpProvider):
    """Responses API (POST /v1/responses) with function tools only."""

    vendor = "openai"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.name = model
        self._key = api_key
        self._timeout = timeout

    @staticmethod
    def input_items(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                items.append({"role": m["role"], "content": content})
                continue
            replay = _state(m, "openai") if m["role"] == "assistant" else None
            if replay is not None:
                items.extend(replay)  # the model's own output items, reasoning included
                continue
            for b in content:
                kind = b.get("type")
                if kind == "text":
                    items.append({"role": m["role"], "content": b.get("text", "")})
                elif kind == "tool_result":
                    items.append(
                        {
                            "type": "function_call_output",
                            "call_id": b["tool_use_id"],
                            "output": _result_text(b.get("content")),
                        }
                    )
                elif kind == "tool_use":
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": b["id"],
                            "name": b["name"],
                            "arguments": json.dumps(b.get("input") or {}),
                        }
                    )
        return items

    def _request(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "model": self.name,
            "instructions": system,
            "input": self.input_items(messages),
            "tools": [
                {
                    "type": "function",
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                    "strict": False,
                }
                for t in tools
            ],  # fmt: skip
            "tool_choice": "required",  # every turn is a tool call; the last is final_answer
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            # Nothing is kept by the provider for later turns; reasoning comes back encrypted
            # so it can be passed back with the tool results.
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        return _post_json(
            OPENAI_RESPONSES_URL,
            body,
            {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            self._timeout,
        )

    @staticmethod
    def parse(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        if body.get("status") not in (None, "completed"):
            raise ProviderError(f"status_{body.get('status')}"[:40])
        output = [i for i in body.get("output") or [] if isinstance(i, dict)]
        blocks: list[dict[str, Any]] = []
        for item in output:
            if item.get("type") == "function_call":
                try:
                    arguments = json.loads(item.get("arguments") or "{}")
                except ValueError as exc:
                    raise ProviderError("invalid_arguments") from exc
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(item.get("call_id")),
                        "name": str(item.get("name")),
                        "input": arguments,
                    }
                )
            elif item.get("type") == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "output_text":
                        blocks.append({"type": "text", "text": str(part.get("text", ""))})
        blocks.append({"type": "provider_state", "provider": "openai", "items": output})
        usage = body.get("usage") or {}
        return {"content": blocks}, {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }

    def _parse(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        return self.parse(body)


GEMINI_MODEL_STEPS = (
    "thought",
    "function_call",
    "model_output",
    "google_search_call",
    "google_search_result",
)


class GeminiProvider(_HttpProvider):
    """Interactions API (POST /v1beta/interactions) with function tools only."""

    vendor = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.name = model
        self._key = api_key
        self._timeout = timeout

    @staticmethod
    def input_steps(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        names: dict[str, str] = {}
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                kind = "user_input" if m["role"] == "user" else "model_output"
                steps.append({"type": kind, "content": [{"type": "text", "text": content}]})
                continue
            replay = _state(m, "gemini") if m["role"] == "assistant" else None
            if replay is not None:
                for step in replay:
                    if step.get("type") == "function_call":
                        names[str(step.get("id"))] = str(step.get("name"))
                steps.extend(replay)  # exactly as received (thought signatures included)
                continue
            for b in content:
                kind = b.get("type")
                if kind == "text":
                    step_type = "user_input" if m["role"] == "user" else "model_output"
                    steps.append(
                        {
                            "type": step_type,
                            "content": [{"type": "text", "text": b.get("text", "")}],
                        }
                    )
                elif kind == "tool_use":
                    names[b["id"]] = b["name"]
                    steps.append(
                        {
                            "type": "function_call",
                            "id": b["id"],
                            "name": b["name"],
                            "arguments": b.get("input") or {},
                        }
                    )
                elif kind == "tool_result":
                    steps.append(
                        {"type": "function_result", "call_id": b["tool_use_id"], "name": names.get(b["tool_use_id"], ""),
                         "result": _result_text(b.get("content"))}
                    )  # fmt: skip
        return steps

    def _request(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "model": self.name,
            "system_instruction": system,
            "input": self.input_steps(messages),
            "tools": [
                {
                    "type": "function",
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                }
                for t in tools
            ],
            "tool_choice": "any",  # always a function call; the last is final_answer
            "generation_config": {"max_output_tokens": MAX_OUTPUT_TOKENS},
            "store": False,
        }

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        return _post_json(
            GEMINI_INTERACTIONS_URL,
            body,
            {"x-goog-api-key": self._key, "Content-Type": "application/json"},
            self._timeout,
        )

    @staticmethod
    def parse(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        if body.get("status") in ("failed", "cancelled", "incomplete"):
            raise ProviderError(f"status_{body.get('status')}")
        steps = [
            s
            for s in body.get("steps") or []
            if isinstance(s, dict) and s.get("type") in GEMINI_MODEL_STEPS
        ]
        blocks: list[dict[str, Any]] = []
        for step in steps:
            if step.get("type") == "function_call":
                arguments = step.get("arguments") or {}
                if not isinstance(arguments, dict):
                    raise ProviderError("invalid_arguments")
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(step.get("id")),
                        "name": str(step.get("name")),
                        "input": arguments,
                    }
                )
            elif step.get("type") == "model_output":
                for part in step.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "text":
                        blocks.append({"type": "text", "text": str(part.get("text", ""))})
        blocks.append({"type": "provider_state", "provider": "gemini", "items": steps})
        usage = body.get("usage") or {}
        output = (usage.get("total_output_tokens") or 0) + (usage.get("total_thought_tokens") or 0)
        return {"content": blocks}, {
            "input_tokens": usage.get("total_input_tokens"),
            "output_tokens": output or None,
        }

    def _parse(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        return self.parse(body)


class DeepSeekProvider(_HttpProvider):
    """Chat Completions (POST https://api.deepseek.com/chat/completions) with function tools.

    Stateless: the conversation is sent as chat messages each turn (assistant tool calls,
    then one ``tool`` message per result, as the tool-calls guide requires). Thinking is
    switched off (``thinking: {"type": "disabled"}``): ``tool_choice: required`` is refused
    in thinking mode, and every turn must be a tool call (the last is final_answer)."""

    vendor = "deepseek"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.name = model
        self._key = api_key
        self._timeout = timeout

    @staticmethod
    def chat_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                out.append({"role": m["role"], "content": content})
                continue
            if m["role"] == "assistant":
                text = "".join(str(b.get("text", "")) for b in content if b.get("type") == "text")
                calls = [
                    {
                        "id": str(b["id"]),
                        "type": "function",
                        "function": {
                            "name": str(b["name"]),
                            "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False),
                        },
                    }
                    for b in content
                    if b.get("type") == "tool_use"
                ]
                message: dict[str, Any] = {"role": "assistant", "content": text or None}
                if calls:
                    message["tool_calls"] = calls
                out.append(message)
                continue
            texts: list[str] = []
            for b in content:  # tool results first (they answer the previous tool calls)
                if b.get("type") == "tool_result":
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": str(b["tool_use_id"]),
                            "content": _result_text(b.get("content")),
                        }
                    )
                elif b.get("type") == "text":
                    texts.append(str(b.get("text", "")))
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
        return out

    def _request(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "model": self.name,
            "messages": self.chat_messages(system, messages),
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ],
            "tool_choice": "required",  # every turn is a tool call; the last is final_answer
            "thinking": {"type": "disabled"},
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0,
            "stream": False,
        }

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        return _post_json(
            DEEPSEEK_CHAT_URL,
            body,
            {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            self._timeout,
        )

    @staticmethod
    def parse(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError("invalid_json")
        finish = choices[0].get("finish_reason")
        if finish in ("content_filter", "insufficient_system_resource", "aborted"):
            raise ProviderError(f"status_{finish}"[:40])
        message = choices[0].get("message") or {}
        blocks: list[dict[str, Any]] = []
        if isinstance(message.get("content"), str) and message["content"]:
            blocks.append({"type": "text", "text": message["content"]})
        for call in message.get("tool_calls") or []:
            function = (call or {}).get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except ValueError as exc:
                raise ProviderError("invalid_arguments") from exc
            if not isinstance(arguments, dict):
                raise ProviderError("invalid_arguments")
            blocks.append(
                {
                    "type": "tool_use",
                    "id": str(call.get("id")),
                    "name": str(function.get("name")),
                    "input": arguments,
                }
            )
        usage = body.get("usage") or {}
        return {"content": blocks}, {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }

    def _parse(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
        return self.parse(body)


class FakeProvider:
    """Deterministic stand-in used by tests: picks tools by keywords and answers only
    from their results. Never used in production (startup refuses it)."""

    name = "fake-test-provider"
    vendor = "fake"
    KEYWORDS = {
        # The verified reference pack's indicator (checked first: it also says "generation").
        "gross generation": "ELEC_GROSS_GENERATION",
        "generation": "ELEC_GENERATION",
        "توليد": "ELEC_GENERATION",
        "consumption": "ELEC_CONSUMPTION",
        "water": "WATER_PRODUCTION",
        "مياه": "WATER_PRODUCTION",
    }
    # The rule service.selection_rule adds when the question comes from a sector page.
    SELECTION = re.compile(
        r"applied selection: sector [a-z_]+; indicator (?P<indicator>[A-Z0-9_]+); "
        r"area (?P<area>[A-Z0-9-]+); (?P<view>[a-z_]+) periods from "
        r"(?P<start>\d{4}-\d{2}-\d{2}) to (?P<end>\d{4}-\d{2}-\d{2})"
    )

    def complete(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        question = ""
        for m in reversed(messages):
            if m["role"] == "user" and isinstance(m["content"], list):
                texts = [
                    b["text"]
                    for b in m["content"]
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                if texts:
                    # Only the newest question (earlier unanswered turns are merged above it).
                    question = texts[-1].splitlines()[-1].lower()
                    break
        arabic = bool(re.search(r"[؀-ۿ]", question))
        tool_results = [
            b
            for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
            for b in m["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
        ]
        names = {t.get("name") for t in tools}
        # Scripted research-assistant behaviours (each exercises one backend safeguard).
        if ("conflict" in question or "تعارض" in question) and "web_search" in names:
            return self._conflict(question, tool_results, arabic)
        if ("study" in question or "دراسة" in question) and "run_study" in names:
            return self._study(tool_results, arabic)
        chosen = self.SELECTION.search(system)
        if chosen and question.startswith(("analyse", "حلّل", "حلل")):
            return self._selection(chosen, tool_results, arabic)
        if "history" in question or "تاريخ" in question:
            return self._history(question, tool_results, arabic)
        if "growth" in question or "نمو" in question:
            return self._growth(tool_results, arabic)
        if "governorate" in question or "محافظ" in question:
            return self._areas(tool_results, arabic)
        if "double" in question or "تضاعف" in question:
            return self._premise(tool_results, arabic)
        if ("recommend" in question or "توصي" in question) and "Mode: Analyze" in system:
            return self._recommend(tool_results, arabic)
        # Web questions ("fail" there makes the search, not the model, fail).
        if ("web" in question or "إنترنت" in question) and "web_search" in names:
            return self._web(question, tool_results, arabic)
        if "fail" in question:
            raise ProviderError("simulated_failure")
        indicator = next((code for k, code in self.KEYWORDS.items() if k in question), None)
        if indicator is None:
            return self._final(
                "clarification",
                "أي مؤشر تقصد؟ مثلاً توليد الكهرباء أو إنتاج المياه."
                if arabic
                else "Which indicator do you mean, for example electricity generation or water production?",
                [],
            )
        if not tool_results:
            return {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "latest_period",
                        "input": {"indicator": indicator},
                    }
                ],
            }
        result = json.loads(tool_results[-1]["content"])
        if result.get("status") != "ok":
            return self._final(
                "no_evidence",
                "لا توجد بيانات منشورة لهذا المؤشر، لذا لا أستطيع الإجابة."
                if arabic
                else "There is no published data for this indicator, so I cannot answer.",
                [],
            )
        latest = result["latest_by_series"][0]
        value = latest["value"]
        if "invent" in question:
            value = "123456789"  # deliberately unsupported, to exercise the evidence check
        text = (
            f"آخر قيمة منشورة هي {value} {latest['unit']} للفترة التي تبدأ في {latest['period_start']} [{latest['id']}]."
            if arabic
            else f"The latest published value is {value} {latest['unit']} for the period starting {latest['period_start']} [{latest['id']}]."
        )
        return self._final("answered", text, [latest["id"]])

    def _web(
        self, question: str, tool_results: list[dict[str, Any]], arabic: bool
    ) -> dict[str, Any]:
        """Search once, then report the first result, or say the search failed."""
        step = self._data_first(
            tool_results,
            self._call("web_search", {"query": question[:200], "domain": "electricity"}),
        )
        if step is not None:
            return step
        result = json.loads(tool_results[-1]["content"])
        if result.get("status") == "shown_separately":
            # Grounding with Google Search: the results are shown to the person, not to us.
            return self._final(
                "no_evidence",
                "نتائج بحث Google معروضة أسفل الإجابة كما هي، وهي غير مُراجَعة." if arabic
                else "Unreviewed web context from Google Search is shown below the answer.",
                [],
            )  # fmt: skip
        if result.get("status") != "ok":
            return self._final(
                "no_evidence",
                "فشل البحث على الإنترنت، لذلك لا توجد نتائج لعرضها."
                if arabic
                else "The web search failed, so there are no web findings to report.",
                [],
            )
        first = result["results"][0]
        match = re.search(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", first["untrusted_snippet"])
        number = match.group(0) if match else None
        text = (
            f"يذكر {first['publisher']} ({first['source_class']}) القيمة {number} [{first['evidence_id']}]."
            if arabic
            else f"{first['publisher']} ({first['source_class']}) reports {number} [{first['evidence_id']}]."
        )
        final = self._final("answered", text, [first["evidence_id"]])
        if number:
            final["content"][0]["input"]["web_records"] = [
                {
                    "evidence_id": first["evidence_id"],
                    "domain": "electricity",
                    "indicator": "Electricity generated",
                    "value_text": number,
                    "unit": "GWh",
                    "geography": "Oman",
                    "period_label": "2023",
                    "period_start": "2023-01-01",
                    "period_end": "2023-12-31",
                }
            ]
        return final

    @staticmethod
    def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": f"t-{name}", "name": name, "input": arguments}],
        }

    def _data_first(
        self, tool_results: list[dict[str, Any]], search: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Follow the routing policy as a real model would: search; after a data_first
        refusal look up the platform's data, then search again. None: results are in."""
        if not tool_results:
            return search
        last = self._last(tool_results)
        if last.get("status") == "data_first":
            return self._call("list_indicators", {})
        if "indicators" in last:
            return search
        return None

    @staticmethod
    def _last(tool_results: list[dict[str, Any]]) -> dict[str, Any]:
        return json.loads(tool_results[-1]["content"])

    def _history(
        self, question: str, tool_results: list[dict[str, Any]], arabic: bool
    ) -> dict[str, Any]:
        """The published annual values of one indicator, one sentence (and citation) per year,
        so a narration segment points at exactly one table row and chart point."""
        indicator = next(
            (code for k, code in self.KEYWORDS.items() if k in question), "ELEC_GENERATION"
        )
        if not tool_results:
            return self._call("get_observations", {"indicator": indicator, "frequency": "annual"})
        result = self._last(tool_results)
        rows = [o for o in result.get("observations", []) if o.get("value") is not None][-4:]
        if result.get("status") != "ok" or not rows:
            return self._no_data(arabic)
        sentences = [
            f"في {o['period_start'][:4]} كانت القيمة المنشورة {o['value']} {o['unit']} [{o['id']}]."
            if arabic
            else f"In {o['period_start'][:4]} the published value was {o['value']} {o['unit']} [{o['id']}]."
            for o in rows
        ]
        return self._final("answered", " ".join(sentences), [o["id"] for o in rows])

    def _selection(
        self, chosen: re.Match[str], tool_results: list[dict[str, Any]], arabic: bool
    ) -> dict[str, Any]:
        """Request analysis from a sector page: look up exactly the applied indicator, area,
        frequency and years, keep the periods inside the range, cite each one."""
        start, end = chosen["start"], chosen["end"]
        if not tool_results:
            return self._call(
                "get_observations",
                {
                    "indicator": chosen["indicator"],
                    "area": chosen["area"],
                    "frequency": chosen["view"],
                    "year_from": int(start[:4]),
                    "year_to": int(end[:4]),
                },
            )
        result = self._last(tool_results)
        inside = [
            o
            for o in result.get("observations", [])
            if start <= o["period_start"] <= end and o.get("value") is not None
        ][-6:]
        if result.get("status") != "ok" or not inside:
            return self._no_data(arabic)
        sentences = [
            f"للفترة التي تبدأ في {o['period_start']} كانت القيمة المنشورة {o['value']} {o['unit']} [{o['id']}]."
            if arabic
            else f"For the period starting {o['period_start']} the published value was {o['value']} {o['unit']} [{o['id']}]."
            for o in inside
        ]
        return self._final("answered", " ".join(sentences), [o["id"] for o in inside])

    def _no_data(self, arabic: bool) -> dict[str, Any]:
        return self._final(
            "no_evidence",
            "لا توجد بيانات منشورة كافية للإجابة."
            if arabic
            else "There is not enough published data to answer.",
            [],
        )

    def _study(self, tool_results: list[dict[str, Any]], arabic: bool) -> dict[str, Any]:
        """Run the trend study of electricity generation and report its first finding."""
        if not tool_results:
            return self._call(
                "run_study",
                {"kind": "trend", "params": {"indicator": "ELEC_GENERATION", "area": "OM"}},
            )
        result = self._last(tool_results)
        if result.get("status") != "ok" or not result.get("findings"):
            return self._no_data(arabic)
        eid = result["evidence_id"]
        findings = result["findings_ar"] if arabic else result["findings"]
        text = f"{findings[0]} [{eid}]"
        if len(findings) > 1:
            text += f" {findings[1]} [{eid}]"
        return self._final("answered", text, [eid])

    def _growth(self, tool_results: list[dict[str, Any]], arabic: bool) -> dict[str, Any]:
        if not tool_results:
            return self._call(
                "growth_rate", {"indicator": "ELEC_GENERATION", "from_year": 2001, "to_year": 2002}
            )
        result = self._last(tool_results)
        if result.get("status") != "ok" or result["result"]["value"] is None:
            return self._no_data(arabic)
        r = result["result"]
        value = f"{float(r['value']):.2f}"
        text = (
            f"نما توليد الكهرباء بمعدل سنوي مركب قدره {value} في المئة بين 2001 و2002 [{r['id']}]."
            if arabic
            else f"Electricity generation grew at a compound annual rate of {value} percent between 2001 and 2002 [{r['id']}]."
        )
        return self._final("answered", text, [r["id"]])

    def _areas(self, tool_results: list[dict[str, Any]], arabic: bool) -> dict[str, Any]:
        if not tool_results:
            return self._call("compare_areas", {"indicator": "ELEC_GENERATION"})
        result = self._last(tool_results)
        rows = [r for r in result.get("rows", []) if r.get("evidence_id")]
        if result.get("status") not in ("ok", "not_comparable") or not rows:
            return self._no_data(arabic)
        lines = []
        for r in result["rows"]:
            name = r["name"]["ar" if arabic else "en"]
            if r.get("evidence_id") and r.get("value") is not None:
                lines.append(f"{name}: {r['value']} [{r['evidence_id']}]")
            elif r["status"] != "no_published_value":
                lines.append(
                    f"{name}: " + ("قيمة مفقودة في المصدر" if arabic else "missing in the source")
                )
        if result.get("areas_without_value", 0):
            lines.append(
                "لا توجد قيمة منشورة لبقية المحافظات."
                if arabic
                else "The other governorates have no published value."
            )
        return self._final("answered", "\n".join(lines), [r["evidence_id"] for r in rows])

    def _premise(self, tool_results: list[dict[str, Any]], arabic: bool) -> dict[str, Any]:
        if not tool_results:
            return self._call(
                "compare_periods",
                {
                    "indicator": "ELEC_GENERATION",
                    "period_a_start": "2001-01-01",
                    "period_b_start": "2002-01-01",
                },
            )
        result = self._last(tool_results)
        if result.get("status") != "ok":
            return self._no_data(arabic)
        pct = next(r for r in result["results"] if r["calculation"] == "percentage_change")
        value = f"{float(pct['value']):.2f}"
        text = (
            f"المقدمة غير صحيحة: لم يتضاعف توليد الكهرباء. تغيّر بنسبة {value} في المئة بين 2001 و2002 [{pct['id']}]."
            if arabic
            else f"The premise is not supported: electricity generation did not double. It changed by {value} percent between 2001 and 2002 [{pct['id']}]."
        )
        return self._final("answered", text, [pct["id"]])

    def _recommend(self, tool_results: list[dict[str, Any]], arabic: bool) -> dict[str, Any]:
        if not tool_results:
            return self._call("latest_period", {"indicator": "ELEC_GENERATION"})
        result = self._last(tool_results)
        if result.get("status") != "ok":
            return self._no_data(arabic)
        latest = result["latest_by_series"][0]
        eid, value = latest["id"], latest["value"]
        final = self._final(
            "answered",
            f"The latest published generation is {value} GWh [{eid}].",
            [eid],
        )
        final["content"][0]["input"].update(
            {
                "recommendations": [
                    {
                        "finding": f"Generation reached {value} GWh in the latest published year.",
                        "evidence": f"Published value {value} GWh [{eid}].",
                        "action": "Review peak-season capacity planning against this level.",
                        "expected_benefit": "Earlier identification of capacity gaps (not quantified).",
                        "prerequisites": "A published peak-demand series for the same years.",
                        "uncertainty": "One year of data; no trend can be inferred.",
                        "citations": [eid],
                    },
                    {  # an invented saving: must be withheld by the evidence check
                        "finding": "Efficiency programmes are needed.",
                        "evidence": f"Published value {value} GWh.",
                        "action": "Launch an efficiency programme.",
                        "expected_benefit": "Could save 25% of fuel costs.",
                        "prerequisites": "Budget approval.",
                        "uncertainty": "Low.",
                        "citations": [eid],
                    },
                ],
                "drivers": [
                    {
                        "driver": "population",
                        "basis": "hypothesis",
                        "relation": "Population growth may raise electricity demand; the platform's data do not show this.",
                    },
                    {
                        "driver": "weather",
                        "basis": "evidence",
                        "relation": "Hot summers raise cooling load.",
                    },
                ],
                "evidence_points": [
                    {
                        "statement": f"Generation was {value} GWh in the latest published year.",
                        "citations": [eid],
                    }
                ],
                "hypotheses": [
                    {"statement": "Cooling demand may explain part of the level (not tested)."}
                ],
                "assumptions": [
                    {"statement": "The indicator definition is unchanged between years."}
                ],
            }
        )
        return final

    def _conflict(
        self, question: str, tool_results: list[dict[str, Any]], arabic: bool
    ) -> dict[str, Any]:
        step = self._data_first(
            tool_results,
            self._call(
                "web_search",
                {
                    "query": "electricity generated 2023",
                    "query_other_language": "الكهرباء المولدة 2023",
                    "domain": "electricity",
                },
            ),
        )
        if step is not None:
            return step
        result = self._last(tool_results)
        if result.get("status") != "ok" or len(result.get("results", [])) < 2:
            return self._final(
                "no_evidence",
                "فشل البحث على الإنترنت."
                if arabic
                else "The web search failed, so there are no web findings to report.",
                [],
            )
        official, other = result["results"][0], result["results"][1]

        def number(snippet: str) -> str:
            m = re.search(r"\d{1,3}(?:,\d{3})+", snippet)
            return m.group(0) if m else ""

        a, b = number(official["untrusted_snippet"]), number(other["untrusted_snippet"])
        text = (
            f"{official['publisher']} ({official['source_class']}) reports {a} GWh for 2023 [{official['evidence_id']}]. "
            f"A secondary source reports {b} GWh [{other['evidence_id']}]. The official figure is the first."
        )
        final = self._final("answered", text, [official["evidence_id"], other["evidence_id"]])
        final["content"][0]["input"]["conflicts"] = [
            {
                "topic": "Electricity generated in 2023",
                "values": [
                    {"evidence_id": official["evidence_id"], "value_text": a},
                    {"evidence_id": other["evidence_id"], "value_text": b},
                ],
                "note": "Official statistics and a news report differ.",
            }
        ]
        return final

    @staticmethod
    def _final(status: str, text: str, citations: list[str]) -> dict[str, Any]:
        return {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "final",
                    "name": "final_answer",
                    "input": {
                        "status": status,
                        "text": text,
                        "citations": citations,
                        "suggested_questions": [],
                    },
                }
            ],
        }


def build_provider(name: str) -> Provider | None:
    """The answering provider called ``name`` when it is fully configured, else None."""
    s = get_settings()
    timeout = s.assistant_timeout_seconds
    if name == "fake" and s.environment != "production":
        return FakeProvider()
    if registry.missing(name, "answer"):
        return None
    if name == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider(s.anthropic_api_key.get_secret_value(), s.assistant_model, timeout)
    if name == "openai" and s.openai_api_key and s.openai_model:
        return OpenAIProvider(s.openai_api_key.get_secret_value(), s.openai_model, timeout)
    if name == "gemini" and s.gemini_api_key and s.gemini_model:
        return GeminiProvider(s.gemini_api_key.get_secret_value(), s.gemini_model, timeout)
    if (
        name == "deepseek"
        and s.deepseek_api_key
        and s.deepseek_model
        and s.deepseek_billing_acknowledged
    ):
        return DeepSeekProvider(s.deepseek_api_key.get_secret_value(), s.deepseek_model, timeout)
    return None


def get_provider() -> Provider | None:
    """The primary answering provider (one per question)."""
    return build_provider(get_settings().assistant_provider)


def answering_available() -> bool:
    """An answering provider (primary or fallback) is configured."""
    return get_provider() is not None or get_fallback_provider() is not None


def get_fallback_provider() -> Provider | None:
    """Used only when the primary fails before answering; never alongside it."""
    s = get_settings()
    if not s.assistant_fallback_provider or s.assistant_fallback_provider == s.assistant_provider:
        return None
    return build_provider(s.assistant_fallback_provider)
