"""The official OpenAI Python SDK (``openai``), on the server only: the Responses API.

Checked against https://developers.openai.com/api/docs on 2026-10-26 (Responses API, streaming,
background mode, structured outputs, the ``web_search`` tool, error codes).

OSRIP keeps its own retry, daily limits and metering (``app.services.providers``), so the SDK's
own retries are off, and each call gets the injected httpx client (tests use
``httpx.MockTransport``; nothing reaches the network). A response comes back as a plain dict,
exactly as the API sent it (``to_dict``), because the output items of a turn are passed back
with its tool results.

* ``create``: one response (``POST /v1/responses``).
* ``create`` with ``stop``: the same call streamed (``stream: true``). Between events (at most
  every ``STOP_CHECK_SECONDS``) ``stop()`` is called; when it raises (the person stopped the
  question), leaving the stream closes the connection, which is how a synchronous response is
  cancelled. The completed response is the same dict as without streaming.
* ``json_format`` / ``output_json``: a JSON reply that follows a schema (``text.format``
  json_schema, strict). A refusal or an incomplete reply is an error, never parsed as data.
* ``cancel``: ``POST /v1/responses/{id}/cancel``, for background responses.

Errors become ``OpenAIFailure``: ``http_401``, ``http_429`` ... with the service's error code
(``insufficient_quota``, ``rate_limit_exceeded``, ``model_not_found`` ...) reduced to a safe
token, ``timeout`` or ``network``, and Retry-After when the service sent it. The SDK's messages
are never kept, so nothing the service echoes back (such as part of a key) reaches the logs.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
import openai

STOP_CHECK_SECONDS = 1.0
# 429 codes that are quota or spending limits, not rate limits: retrying cannot help until
# credits are added or the limit is changed (error-codes guide).
QUOTA_CODES = frozenset(
    {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
        "billing_hard_limit_reached",
    }
)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,40}")

ClientFactory = Callable[[float], httpx.Client]


class OpenAIFailure(Exception):
    """A failed OpenAI call: ``str(error)`` is the short code, ``detail`` the service's code."""

    def __init__(self, code: str, detail: str | None = None, retry_after: float | None = None):
        super().__init__(code)
        self.detail = detail
        self.retry_after = retry_after


def _token(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value) else None


def _retry_after(response: httpx.Response | None) -> float | None:
    """Seconds from a Retry-After header in its delay form (an HTTP date is not trusted)."""
    value = (response.headers.get("retry-after", "") if response is not None else "").strip()
    try:
        return max(0.0, float(value)) if value else None
    except ValueError:
        return None


def _status_failure(exc: openai.APIStatusError) -> OpenAIFailure:
    # The SDK keeps the body's ``error`` object; ``code`` says more than ``type`` (a spending
    # limit has type insufficient_quota and its own code).
    body = exc.body if isinstance(exc.body, dict) else {}
    detail = _token(body.get("code")) or _token(body.get("type"))
    if exc.status_code == 429 and QUOTA_CODES & {detail, _token(body.get("type"))}:
        detail = "insufficient_quota"
    return OpenAIFailure(f"http_{exc.status_code}", detail, _retry_after(exc.response))


def _plain(response: Any) -> dict[str, Any]:
    """The response as the API sent it: fields it did not send are left out (``to_dict``), and
    the SDK's union-type warnings for item shapes it does not model exactly are not raised."""
    return response.to_dict(mode="json", warnings=False)


def client(api_key: str, http: httpx.Client, timeout: float) -> openai.OpenAI:
    return openai.OpenAI(api_key=api_key, http_client=http, timeout=timeout, max_retries=0)


def create(
    api_key: str,
    body: dict[str, Any],
    timeout: float,
    http_client_factory: ClientFactory,
    stop: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """One Responses API call; streamed when ``stop`` is given, so it can be stopped."""
    try:
        with http_client_factory(timeout) as http:
            responses = client(api_key, http, timeout).responses
            if stop is None:
                return _plain(responses.create(**body))
            checked = time.monotonic()
            with responses.create(**body, stream=True) as events:
                for event in events:
                    if time.monotonic() - checked >= STOP_CHECK_SECONDS:
                        stop()  # raises when stopped; leaving the block closes the stream
                        checked = time.monotonic()
                    kind = getattr(event, "type", "")
                    if kind in ("response.completed", "response.incomplete", "response.failed"):
                        return _plain(event.response)
                    if kind == "error":
                        raise OpenAIFailure("stream_error", _token(getattr(event, "code", None)))
            raise OpenAIFailure("stream_ended")
    except openai.APITimeoutError as exc:  # before APIConnectionError, its parent
        raise OpenAIFailure("timeout") from exc
    except openai.APIConnectionError as exc:
        raise OpenAIFailure("network") from exc
    except openai.APIStatusError as exc:
        raise _status_failure(exc) from exc
    except openai.APIResponseValidationError as exc:
        raise OpenAIFailure("invalid_json") from exc


def cancel(
    api_key: str, response_id: str, timeout: float, http_client_factory: ClientFactory
) -> str | None:
    """Cancel a background response; returns its final status (idempotent)."""
    try:
        with http_client_factory(timeout) as http:
            return client(api_key, http, timeout).responses.cancel(response_id).status
    except openai.APITimeoutError as exc:
        raise OpenAIFailure("timeout") from exc
    except openai.APIConnectionError as exc:
        raise OpenAIFailure("network") from exc
    except openai.APIStatusError as exc:
        raise _status_failure(exc) from exc


def json_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """``text.format`` for a reply that must follow ``schema`` (strict structured outputs)."""
    return {"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}}


def output_json(body: dict[str, Any]) -> dict[str, Any]:
    """The JSON object of a structured reply. A refusal, an incomplete reply (for example cut at
    max_output_tokens) or text that is not a JSON object is an error, never data."""
    status = body.get("status")
    if status not in (None, "completed"):
        raise OpenAIFailure(f"status_{status}"[:40])
    text = ""
    for item in body.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise OpenAIFailure("refused")
            if part.get("type") == "output_text":
                text += str(part.get("text", ""))
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise OpenAIFailure("invalid_json") from exc
    if not isinstance(value, dict):
        raise OpenAIFailure("invalid_json")
    return value


def usage(body: dict[str, Any]) -> dict[str, int | None]:
    u = body.get("usage") or {}
    return {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens")}
