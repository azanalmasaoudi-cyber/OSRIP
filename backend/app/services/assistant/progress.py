"""Visible progress and cancellation of one assistant request (migration 0016).

While an answer is prepared, each stage actually reached is appended to the request's
``progress`` list in its own short transaction, so the person asking can poll it from a
second request and see what is happening ("checking published data", "searching the web",
"reading sources", ...). Only real steps are recorded: a stage appears when the model calls
a tool of that kind, never on a timer.

Stopping a question sets ``cancel_requested_at``; the answer loop checks it before every
model call and every tool call and ends with a 'cancelled' reply, which is never charged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, select, update
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import session_factory
from app.models import AssistantRequest

STAGES: dict[str, dict[str, str]] = {
    "received": {"en": "Question received", "ar": "استُلم السؤال"},
    "published_data": {
        "en": "Checking OSRIP's published data",
        "ar": "مراجعة بيانات OSRIP المنشورة",
    },
    "calculating": {"en": "Calculating with OSRIP's functions", "ar": "الحساب بدوال OSRIP"},
    "validating_data": {
        "en": "Validating tables (units, periods, values)",
        "ar": "التحقق من الجداول (الوحدات والفترات والقيم)",
    },
    "web_search": {
        "en": "Searching the web in Arabic and English",
        "ar": "البحث في الإنترنت بالعربية والإنجليزية",
    },
    "reading": {"en": "Reading sources", "ar": "قراءة المصادر"},
    "checking": {"en": "Checking numbers and citations", "ar": "التحقق من الأرقام والاستشهادات"},
    "done": {"en": "Answer ready", "ar": "الإجابة جاهزة"},
    "cancelled": {"en": "Stopped at your request", "ar": "أُوقف بناءً على طلبك"},
}

TOOL_STAGE = {
    "web_search": "web_search",
    "read_web_page": "reading",
    "compare_periods": "calculating",
    "growth_rate": "calculating",
    "share_of_total": "calculating",
    "compare_areas": "calculating",
    "run_study": "calculating",
    "scenario_projection": "calculating",
    "explain_calculation": "calculating",
}


class Cancelled(Exception):
    """The person stopped the question."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class Tracker:
    """Records stages for one stored request; a no-op without one (no request id). With a
    ``stream`` the same steps (and the sources, datasets and end of the study) are also
    written as live study events (``study_events``)."""

    request_pk: int | None
    reached: list[str] = field(default_factory=list)
    stream: Any = None  # study_events.StudyStream

    def stage(self, name: str, detail: str | None = None) -> None:
        if name not in STAGES or (self.reached and self.reached[-1] == name):
            return
        self.reached.append(name)
        if self.stream is not None:
            self.stream.stage(name, STAGES[name])
        if self.request_pk is None:
            return
        entry: dict[str, Any] = {"stage": name, "at": _now()}
        if detail:
            entry["detail"] = detail[:120]
        # Appended in its own short transaction so a second request can read it at once.
        with session_factory()() as s, s.begin():
            s.execute(
                update(AssistantRequest)
                .where(AssistantRequest.id == self.request_pk)
                .values(
                    progress=AssistantRequest.progress.op("||")(
                        bindparam("entry", [entry], type_=JSONB)
                    )
                )
            )

    def tool(self, name: str) -> None:
        self.stage(TOOL_STAGE.get(name, "published_data"))

    def start(self, *, attempt: int, mode: str) -> None:
        """The live study begins (one 'received' stage, like the stored progress)."""
        if self.stream is not None:
            self.stream.started(attempt=attempt, mode=mode)
            self.stream.stage("received", STAGES["received"])

    def finish(self, reply: Any, message_id: int | None) -> None:
        """The live study ends with the stored reply: completed, cancelled or failed."""
        if self.stream is not None:
            try:
                self.stream.finish(reply, message_id)
            except Exception:  # noqa: BLE001 - the reply is stored; a failed event must not undo it
                import logging

                logging.getLogger("osrip.study_events").exception("study completion event failed")

    def check(self) -> None:
        """Raise ``Cancelled`` when the person has stopped the question."""
        if self.request_pk is None:
            return
        with session_factory()() as s, s.begin():
            stopped = s.scalar(
                select(AssistantRequest.cancel_requested_at).where(
                    AssistantRequest.id == self.request_pk
                )
            )
        if stopped is not None:
            raise Cancelled


def view(row: AssistantRequest) -> dict[str, Any]:
    """The request's state and stages with bilingual labels (no question text)."""
    return {
        "state": row.state,
        "cancel_requested": row.cancel_requested_at is not None,
        "stages": [
            {**e, "label": STAGES.get(str(e.get("stage")), {"en": "", "ar": ""})}
            for e in (row.progress or [])
            if isinstance(e, dict)
        ],
    }
