"""Streamed answer text: what the model writes appears while it writes, one checked sentence at a
time (``answer.segment`` study events, read by the conversation over server-sent events).

* Genuine: providers that stream (DeepSeek, OpenAI, the scripted stand-in) hand over the
  ``final_answer`` call's arguments as they arrive; ``JsonTextField`` decodes the ``text`` field
  from that partial JSON. Nothing is written in advance or replayed slowly. Providers that do not
  stream hand over the finished text at once.
* Checked: a sentence is sent only when it passes the same evidence check as the final answer
  (``grounding.validate``, with its own markers). A sentence that does not pass yet (it may rely
  on a marker later in its paragraph) is held, with what follows it in that line, until the line
  is complete; then the line is checked as ``grounding.keep_supported`` checks it. Streamed text
  is never laxer than the final check, so a figure shown while writing is never withdrawn later.
* Only the answer: no tool arguments, no reasoning, no text outside ``final_answer``.

The stored reply (checked again as a whole, with its structured parts) replaces the streamed text
when the answer is complete.
"""

from __future__ import annotations

import contextvars
import json
import logging
from collections.abc import Callable
from typing import Any

from app.services.assistant import grounding

log = logging.getLogger("osrip.assistant")

MAX_SEGMENT = 4000

# Set by the answer loop for the question being answered; providers that stream call it.
answer_sink: contextvars.ContextVar[AnswerSink | None] = contextvars.ContextVar(
    "answer_sink", default=None
)


class JsonTextField:
    """Decodes one top-level string field (``text``) of a JSON object from its pieces as they
    arrive, returning each newly decoded part. Escapes split across pieces are handled; nested
    objects and other fields are skipped."""

    def __init__(self, field: str = "text") -> None:
        self._field = field
        self._depth = 0
        self._in_string = False
        self._escape = ""  # the escape being read ("\\", "\\u12", ...)
        self._key: list[str] | None = None  # the top-level key being read
        self._last_key = ""
        self._expect_value = False
        self._capturing = False
        self._pending_high: int | None = None  # a UTF-16 high surrogate awaiting its pair
        self.done = False

    def feed(self, piece: str) -> str:
        out: list[str] = []
        for ch in piece:
            if self._in_string:
                self._string_char(ch, out)
                continue
            if ch == '"':
                self._in_string = True
                if self._depth == 1 and self._expect_value and self._last_key == self._field:
                    self._capturing = True
                elif self._depth == 1 and not self._expect_value:
                    self._key = []
            elif ch in "{[":
                self._depth += 1
            elif ch in "}]":
                self._depth -= 1
            elif ch == ":" and self._depth == 1:
                self._expect_value = True
            elif ch == "," and self._depth == 1:
                self._expect_value = False
        return "".join(out)

    def _string_char(self, ch: str, out: list[str]) -> None:
        if self._escape:
            self._escape += ch
            if self._escape[1] != "u" or len(self._escape) == 6:
                self._emit(self._decode_escape(self._escape), out)
                self._escape = ""
            return
        if ch == "\\":
            self._escape = ch
            return
        if ch == '"':
            self._in_string = False
            if self._capturing:
                self._capturing = False
                self.done = True
            elif self._key is not None:
                self._last_key = "".join(self._key)
                self._key = None
            return
        self._emit(ch, out)

    def _emit(self, text: str, out: list[str]) -> None:
        if self._capturing:
            out.append(text)
        elif self._key is not None:
            self._key.append(text)

    def _decode_escape(self, escape: str) -> str:
        simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r",
                  "t": "\t"}  # fmt: skip
        if escape[1] != "u":
            return simple.get(escape[1], escape[1])
        try:
            code = int(escape[2:], 16)
        except ValueError:
            return ""
        if 0xD800 <= code <= 0xDBFF:
            self._pending_high = code
            return ""
        if 0xDC00 <= code <= 0xDFFF and self._pending_high is not None:
            high, self._pending_high = self._pending_high, None
            return chr(0x10000 + ((high - 0xD800) << 10) + (code - 0xDC00))
        self._pending_high = None
        return chr(code)


class VerifiedWriter:
    """Turns the answer text, as it is decoded, into checked segments in reading order."""

    def __init__(self, items: Callable[[], list[dict[str, Any]]], send: Callable[[str], None]):
        self._items = items
        self._send = send
        self._line = ""  # the current (incomplete) line
        self._done = 0  # characters of the current line already handled
        self._held = False  # a sentence of this line failed: wait for the line's end
        self._prefix_sent = False
        self._sent_any_in_line = False
        self._in_table = False
        self.sent = 0  # segments sent
        self.held_back = 0  # sentences or rows not sent (they failed the check)

    def feed(self, text: str) -> None:
        for ch in text:
            if ch == "\n":
                self._end_line()
            else:
                self._line += ch
        self._progress()

    def finish(self) -> None:
        if self._line:
            self._end_line(final=True)

    # -------------------------------------------------------------- checks
    def _visible(self) -> list[dict[str, Any]]:
        return [i for i in self._items() if i.get("kind") != "grounded_context"]

    def _ok(self, sentence: str, paragraph_ids: list[str]) -> bool:
        items = self._visible()
        known = {i["id"] for i in items}
        own = grounding.inline_markers(sentence)
        ids = [i for i in (own or paragraph_ids) if i in known]
        probe = sentence if own or not paragraph_ids else sentence + "".join(f" [{i}]" for i in ids)
        return grounding.validate(probe, ids, items).ok

    # -------------------------------------------------------------- lines
    def _progress(self) -> None:
        """Sends the complete sentences of the current line that pass on their own."""
        line = self._line
        if self._held or grounding._TABLE_ROW.match(line) or line.lstrip().startswith("|"):
            return
        prefix_match = grounding._LINE_PREFIX.match(line)
        start = max(self._done, len(prefix_match.group(1)) if prefix_match else 0)
        body = line[start:]
        parts = grounding._SENTENCE_GAP.split(body)
        # Complete sentences only: the last part may still be growing.
        complete = list(zip(parts[0::2], parts[1::2], strict=False))
        for sentence, gap in complete:
            if not self._ok(sentence, []):
                self._held = True
                return
            self._emit_sentence(line, sentence + gap)
            self._done = start + len(sentence) + len(gap)
            start = self._done

    def _end_line(self, *, final: bool = False) -> None:
        line, self._line = self._line, ""
        newline = "" if final else "\n"
        try:
            if not line.strip():
                if self._in_table:
                    self._in_table = False
                self._send(newline)
                return
            if grounding._TABLE_RULE.match(line):
                if self._in_table:
                    self._send(line + newline)
                return
            paragraph_ids = grounding.inline_markers(line)
            if grounding._TABLE_ROW.match(line):
                if self._ok(line, paragraph_ids):
                    self._in_table = True
                    self._send(line + newline)
                else:
                    self.held_back += 1
                return
            self._in_table = False
            prefix_match = grounding._LINE_PREFIX.match(line)
            prefix = prefix_match.group(1) if prefix_match else ""
            start = max(self._done, len(prefix))
            parts = grounding._SENTENCE_GAP.split(line[start:])
            for sentence, gap in zip(parts[0::2], [*parts[1::2], ""], strict=True):
                if not sentence:
                    continue
                if self._ok(sentence, paragraph_ids):
                    self._emit_sentence(line, sentence + gap)
                else:
                    self.held_back += 1
            if self._sent_any_in_line:
                self._send(newline)
        finally:
            self._done, self._held = 0, False
            self._prefix_sent = self._sent_any_in_line = False

    def _emit_sentence(self, line: str, text: str) -> None:
        if not self._prefix_sent:
            match = grounding._LINE_PREFIX.match(line)
            text = (match.group(1) if match else "") + text
            self._prefix_sent = True
        self._sent_any_in_line = True
        self._send(text)


class AnswerSink:
    """For one question: receives the model's tool-call arguments as they stream and sends the
    checked answer text as ``answer.segment`` events (and a ``writing`` stage)."""

    def __init__(self, ledger: Any, tracker: Any) -> None:
        self._ledger = ledger
        self._tracker = tracker
        self._calls: dict[str, tuple[str, JsonTextField, VerifiedWriter]] = {}
        self._index = 0
        self._buffer = ""
        self.streamed: set[str] = set()  # final_answer calls that streamed their text

    def _send(self, text: str) -> None:
        # Each checked sentence (or table row, or paragraph break) goes out as it is ready.
        self._buffer += text
        self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        stream = getattr(self._tracker, "stream", None)
        if self._index == 0:
            self._tracker.stage("writing")
        while self._buffer:
            piece, self._buffer = self._buffer[:MAX_SEGMENT], self._buffer[MAX_SEGMENT:]
            if stream is not None:
                stream.emit("answer.segment", {"index": self._index, "text": piece})
            self._index += 1

    def start(self, call_id: str, name: str) -> None:
        if name != "final_answer" or call_id in self._calls:
            return
        if self._index:
            # A new answer replaces one that was cut off or refused: start the text again.
            stream = getattr(self._tracker, "stream", None)
            if stream is not None:
                stream.emit("answer.reset", {"reason": "new_attempt"})
            self._index = 0
        writer = VerifiedWriter(lambda: list(self._ledger.items), self._send)
        self._calls[call_id] = (name, JsonTextField(), writer)

    def arguments(self, call_id: str, piece: str) -> None:
        call = self._calls.get(call_id)
        if call is None:
            return
        _name, decoder, writer = call
        try:
            text = decoder.feed(piece)
            if text:
                self.streamed.add(call_id)
                writer.feed(text)
            if decoder.done:
                writer.finish()
                self._flush()
        except Exception:  # noqa: BLE001 - streaming is a view; the stored reply is what counts
            log.exception("answer streaming failed; the reply is shown when complete")
            self._calls.pop(call_id, None)

    def whole(self, call_id: str, arguments: dict[str, Any]) -> None:
        """A provider that does not stream: the finished answer, sent as checked segments."""
        if call_id in self._calls:  # already streamed (or being streamed) by the provider
            return
        self.start(call_id, "final_answer")
        self.arguments(call_id, json.dumps(arguments, ensure_ascii=False))
