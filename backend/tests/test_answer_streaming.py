"""Streamed answers without a database: the answer text decoded from partial tool-call JSON, the
checked sentences released in order (never laxer than the final check), the sink's events, and
the providers' streams (DeepSeek's server-sent chunks, its fallback to a plain request, OpenAI's
argument deltas)."""

from __future__ import annotations

import json
import random
import re
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.domain.enums import DataMode
from app.services.assistant import grounding, provider, streaming
from app.services.assistant.tools import Ledger


def _ledger() -> Ledger:
    ledger = Ledger(DataMode.SYNTHETIC)
    ledger.add({"kind": "observation", "value": "41234", "period_start": "2023-01-01",
                "period_end": "2023-12-31", "unit": "GWh"})  # fmt: skip
    return ledger


def _pieces(text: str, seed: int) -> list[str]:
    rng = random.Random(seed)  # noqa: S311 - reproducible splits, not security
    out, i = [], 0
    while i < len(text):
        n = rng.randint(1, 7)
        out.append(text[i : i + n])
        i += n
    return out


# ------------------------------------------------------------------ the text field


@pytest.mark.parametrize("seed", range(6))
def test_the_text_field_is_decoded_from_any_split(seed: int) -> None:
    text = 'Line "one".\nسطر ٢ — émoji 😀 \\ tab\there / end'
    arguments = json.dumps(
        {"status": "text", "meta": {"text": "not this"}, "text": text, "citations": ["E1"]}
    )
    for ascii_only in (True, False):
        raw = arguments if ascii_only else json.dumps(json.loads(arguments), ensure_ascii=False)
        field = streaming.JsonTextField()
        decoded = "".join(field.feed(piece) for piece in _pieces(raw, seed))
        assert decoded == text and field.done


def test_no_text_field_decodes_nothing() -> None:
    field = streaming.JsonTextField()
    assert field.feed(json.dumps({"status": "no_evidence", "citations": []})) == ""
    assert not field.done


# ------------------------------------------------------------------ checked sentences


def _write(text: str, ledger: Ledger, seed: int = 0) -> tuple[list[str], streaming.VerifiedWriter]:
    sent: list[str] = []
    writer = streaming.VerifiedWriter(lambda: list(ledger.items), sent.append)
    for piece in _pieces(text, seed):
        writer.feed(piece)
    writer.finish()
    return sent, writer


def _norm(text: str) -> str:
    return re.sub(r"\n{2,}", "\n\n", text).strip()


ANSWERS = [
    # Supported, invented and figure-free sentences in one paragraph.
    "Generation reached 41,234 GWh in 2023 [E1]. It rose steadily. "
    "Another source gave 99,999 GWh [E1].",
    # A sentence without its own marker is covered by its paragraph's marker.
    "## Summary\n\n- Generation was 41,234 GWh. The official figure is cited here [E1].\n"
    "- 77,777 GWh is not in the evidence.",
    # A table: the supported row stays, the invented one goes.
    "| Year | GWh |\n|---|---|\n| 2023 | 41,234 [E1] |\n| 2024 | 55,555 [E1] |\n\nThe end.",
]


@pytest.mark.parametrize("text", ANSWERS)
@pytest.mark.parametrize("seed", range(4))
def test_streamed_sentences_are_exactly_what_the_final_check_keeps(text: str, seed: int) -> None:
    ledger = _ledger()
    sent, writer = _write(text, ledger, seed)
    kept = grounding.keep_supported(text, [], list(ledger.items))
    assert _norm("".join(sent)) == _norm(kept.text)
    assert writer.held_back == kept.omitted
    for invented in ("99,999", "77,777", "55,555"):
        assert invented not in "".join(sent)


def test_a_checked_sentence_goes_out_before_its_line_ends() -> None:
    ledger = _ledger()
    sent: list[str] = []
    writer = streaming.VerifiedWriter(lambda: list(ledger.items), sent.append)
    writer.feed("Generation reached 41,234 GWh in 2023 [E1]. It ")
    assert sent == ["Generation reached 41,234 GWh in 2023 [E1]. "]
    writer.feed("rose. Then 99,999 GWh [E1]. And more")
    assert sent[-1] == "It rose. "
    writer.feed(" text.\n")
    assert "99,999" not in "".join(sent) and sent[-1] == "\n"


# ------------------------------------------------------------------ the sink


class _Stream:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def emit(self, kind: str, payload: dict[str, Any], **_: Any) -> None:
        self.events.append((kind, payload))


class _Tracker:
    def __init__(self) -> None:
        self.stream = _Stream()
        self.stages: list[str] = []

    def stage(self, name: str) -> None:
        self.stages.append(name)


def test_the_sink_sends_only_final_answer_text_and_restarts_for_a_new_attempt() -> None:
    tracker = _Tracker()
    sink = streaming.AnswerSink(_ledger(), tracker)
    sink.start("c1", "web_search")
    sink.arguments("c1", '{"query": "text 1"}')  # another tool: nothing is shown
    assert tracker.stream.events == []
    sink.start("c2", "final_answer")
    for piece in _pieces(json.dumps({"status": "answered", "text": "First try. Cut"}), 1):
        sink.arguments("c2", piece)
    sink.start("c3", "final_answer")
    sink.arguments("c3", json.dumps({"status": "answered", "text": "Second try."}))
    kinds = [k for k, _ in tracker.stream.events]
    assert kinds[0] == "answer.segment" and "answer.reset" in kinds
    after = kinds.index("answer.reset")
    segments = [p for k, p in tracker.stream.events[after:] if k == "answer.segment"]
    assert [p["index"] for p in segments] == list(range(len(segments)))
    assert "".join(p["text"] for p in segments) == "Second try."
    assert tracker.stages[0] == "writing"
    # A provider that does not stream: the finished text, once (not again for a streamed call).
    quiet = _Tracker()
    other = streaming.AnswerSink(_ledger(), quiet)
    other.whole("x", {"status": "answered", "text": "Done."})
    other.whole("x", {"status": "answered", "text": "Done."})
    assert [p["text"] for _, p in quiet.stream.events] == ["Done."]


# ------------------------------------------------------------------ providers


def _sse(*chunks: dict[str, Any]) -> bytes:
    return (
        b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n"
    )


def _deepseek_chunks(text: str) -> bytes:
    arguments = json.dumps({"status": "answered", "text": text, "citations": ["E1"]})
    opened = {"index": 0, "id": "call_1", "type": "function",
              "function": {"name": "final_answer", "arguments": ""}}  # fmt: skip
    first = {"choices": [{"index": 0, "finish_reason": None,
                          "delta": {"role": "assistant", "content": "", "tool_calls": [opened]}}],
             "usage": None}  # fmt: skip
    pieces = [
        {"choices": [{"index": 0, "finish_reason": None,
                      "delta": {"tool_calls": [{"index": 0, "function": {"arguments": p}}]}}],
         "usage": None}
        for p in _pieces(arguments, 3)
    ]  # fmt: skip
    last = {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 40}}  # fmt: skip
    return _sse(first, *pieces, last)


FINAL = [{"name": "final_answer", "input_schema": {"type": "object"}}]


def _transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    monkeypatch.setattr(
        provider,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
def deepseek(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(provider.DeepSeekProvider, "streaming", True)
    monkeypatch.setattr(provider, "RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(provider.registry, "check", lambda *a, **k: None)
    monkeypatch.setattr(provider.registry, "record", lambda *a, **k: None)
    return provider.DeepSeekProvider("test-key", "deepseek-flash", 10)


def test_deepseek_streams_the_answer_and_assembles_the_same_reply(
    deepseek: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = "Generation reached 41,234 GWh in 2023 [E1]. It rose."
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, content=_deepseek_chunks(text), headers={"content-type": "text/event-stream"}
        )

    _transport(monkeypatch, handler)
    tracker = _Tracker()
    token = streaming.answer_sink.set(streaming.AnswerSink(_ledger(), tracker))
    try:
        reply = deepseek.complete("system", [{"role": "user", "content": "q"}],
                                  FINAL)  # fmt: skip
    finally:
        streaming.answer_sink.reset(token)
    assert requests[0]["stream"] is True and requests[0]["stream_options"] == {
        "include_usage": True
    }
    [call] = [b for b in reply["content"] if b["type"] == "tool_use"]
    assert call["name"] == "final_answer" and call["input"]["text"] == text
    segments = [p["text"] for k, p in tracker.stream.events if k == "answer.segment"]
    assert len(segments) == 2 and "".join(segments) == text


def test_deepseek_falls_back_to_a_plain_request_when_streaming_is_refused(
    deepseek: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    bodies: list[dict[str, Any]] = []
    called = {
        "id": "c",
        "type": "function",
        "function": {
            "name": "final_answer",
            "arguments": json.dumps({"status": "answered", "text": "Hi."}),
        },
    }
    plain = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [called]},
                          "finish_reason": "tool_calls"}],
             "usage": {"prompt_tokens": 1, "completion_tokens": 1}}  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("stream"):
            return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
        return httpx.Response(200, json=plain)

    _transport(monkeypatch, handler)
    token = streaming.answer_sink.set(streaming.AnswerSink(_ledger(), _Tracker()))
    try:
        reply = deepseek.complete("s", [{"role": "user", "content": "q"}],
                                  FINAL)  # fmt: skip
    finally:
        streaming.answer_sink.reset(token)
    assert [b.get("stream") for b in bodies] == [True, False]
    assert provider.DeepSeekProvider.streaming is False
    assert reply["content"][0]["input"]["text"] == "Hi."


def test_without_a_question_deepseek_sends_a_plain_request(
    deepseek: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(bool(json.loads(request.content).get("stream")))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        )

    _transport(monkeypatch, handler)
    deepseek.complete("s", [{"role": "user", "content": "q"}], [{"name": "a", "input_schema": {}}])
    assert seen == [False]


def test_openai_argument_deltas_reach_the_sink() -> None:
    tracker = _Tracker()
    sink = streaming.AnswerSink(_ledger(), tracker)
    handle = provider._openai_answer_events(sink)
    item = SimpleNamespace(type="function_call", id="fc_1", call_id="call_9", name="final_answer")
    handle(SimpleNamespace(type="response.output_item.added", item=item))
    arguments = json.dumps({"status": "answered", "text": "One. Two."})
    for piece in _pieces(arguments, 2):
        handle(
            SimpleNamespace(
                type="response.function_call_arguments.delta", item_id="fc_1", delta=piece
            )
        )
    handle(SimpleNamespace(type="response.output_text.delta", delta="ignored"))
    assert (
        "".join(p["text"] for k, p in tracker.stream.events if k == "answer.segment") == "One. Two."
    )
