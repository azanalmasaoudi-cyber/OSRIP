"""Data updates: background research runs that look for the latest official statistics of a
sector, read the original documents and save the figures backend validation can check.

A data update is a ``research_job`` of kind ``data_update``. It is queued by an administrator's
schedule (``report_schedule.kind = 'data_update'``: frequency, pages and credits per run, a
monthly cap; nothing runs until the schedule is enabled, paid use is allowed and the server
switch OSRIP_SCHEDULED_REPORTS_ENABLED is on) or by "Run now", and the research worker runs
it independently of any browser.

The run is the assistant's research workflow without a person: the configured answering
model with the research tools (web_search, read_web_page, the platform look-ups and
submit_observations), as the research service account, within the research limits (searches
and pages per answer, model rounds, time, the daily paid search and fetch calls). One run per
sector at a time (an advisory lock); a cancelled job stops before its next model round.
Figures go through ``saving.submit``: duplicates are skipped, conflicts and uncertain figures
wait for a reviewer, and only checked figures from official documents are published. A
failed search, page or model call saves nothing and changes no published data, so the last
valid data stay as they were. The job's result records what happened: the documents read,
the figures saved with their observation ids, duplicates, conflicts, pending figures and the
latest verified period.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import session_factory
from app.domain.enums import DataMode
from app.models import ResearchDocument, ResearchJob, ResearchSearch
from app.services.assistant.progress import Cancelled, Tracker

log = logging.getLogger("osrip.research")

QUESTIONS: dict[str, tuple[str, str]] = {
    "electricity": (
        "Find the latest published official electricity statistics for Oman (gross and net "
        "generation, consumption, peak demand) from 2022 onward. Read the original NCSI or "
        "sector publications and submit every figure you read for validation and saving.",
        "ابحث عن أحدث إحصاءات الكهرباء الرسمية المنشورة لسلطنة عُمان منذ 2022، واقرأ المنشورات "
        "الأصلية للمركز الوطني للإحصاء والمعلومات أو القطاع، وقدّم كل رقم تقرؤه للتحقق والحفظ.",
    ),
    "water": (
        "Find the latest published official water statistics for Oman (production, "
        "consumption) from 2022 onward. Read the original NCSI or sector publications and "
        "submit every figure you read for validation and saving.",
        "ابحث عن أحدث إحصاءات المياه الرسمية المنشورة لسلطنة عُمان منذ 2022، واقرأ المنشورات "
        "الأصلية، وقدّم كل رقم تقرؤه للتحقق والحفظ.",
    ),
    "food_security": (
        "Find the latest published official food security statistics for Oman (production, "
        "self-sufficiency) from 2022 onward. Read the original publications and submit every "
        "figure you read for validation and saving.",
        "ابحث عن أحدث إحصاءات الأمن الغذائي الرسمية المنشورة لسلطنة عُمان منذ 2022، واقرأ "
        "المنشورات الأصلية، وقدّم كل رقم تقرؤه للتحقق والحفظ.",
    ),
    "trade": (
        "Find the latest published official foreign trade statistics for Oman (merchandise "
        "exports, imports, re-exports) from 2022 onward. Read the original publications and "
        "submit every figure you read for validation and saving.",
        "ابحث عن أحدث إحصاءات التجارة الخارجية الرسمية المنشورة لسلطنة عُمان منذ 2022، واقرأ "
        "المنشورات الأصلية، وقدّم كل رقم تقرؤه للتحقق والحفظ.",
    ),
}
STEP = "research_and_save"


class JobTracker(Tracker):
    """Stops a data update before its next model round once cancellation was requested."""

    def __init__(self, job_id: uuid.UUID) -> None:
        super().__init__(None)
        self.job_id = job_id

    def check(self) -> None:
        with session_factory()() as s, s.begin():
            stopped = s.scalar(
                select(ResearchJob.cancel_requested_at).where(ResearchJob.id == self.job_id)
            )
        if stopped is not None:
            raise Cancelled


def default_question(sector: str, language: str) -> str:
    en, ar = QUESTIONS[sector]
    return ar if language == "ar" else en


def create(
    session: Session,
    sector: str,
    *,
    user_id: uuid.UUID | None,
    schedule_id: uuid.UUID | None = None,
    question: str | None = None,
    language: str = "en",
    max_pages: int = 5,
    max_credits: int = 25,
) -> ResearchJob:
    """Queue one data update (the caller's transaction)."""
    if sector not in QUESTIONS:
        raise ValueError(f"unknown sector {sector!r}")
    text = (question or default_question(sector, language)).strip()[:1000]
    key = hashlib.sha256(
        f"data_update|{sector}|{language}|{text}|{uuid.uuid4()}".encode()
    ).hexdigest()
    job = ResearchJob(
        kind="data_update",
        user_id=user_id,
        schedule_id=schedule_id,
        sector=sector,
        area="OM",
        question=text,
        language=language,
        data_mode=DataMode.VERIFIED_SOURCE.value,
        source_scope="official",
        limits={"max_pages": max_pages, "max_credits": max_credits},
        steps=[{"stage": STEP, "state": "pending"}],
        cache_key=key,
        period_from=date(2022, 1, 1),
    )
    session.add(job)
    session.flush()
    return job


def _now() -> datetime:
    return datetime.now(UTC)


def _save(job_id: uuid.UUID, **values: Any) -> None:
    with session_factory()() as s, s.begin():
        job = s.get(ResearchJob, job_id, with_for_update=True)
        if job is not None:
            for key, value in values.items():
                setattr(job, key, value)
            job.heartbeat_at = _now()


def _lock(session: Session, sector: str) -> Any:
    from app.services.sync.service import feed_lock

    return feed_lock(session, f"research-update-{sector}")


def run(job_id: uuid.UUID) -> None:
    """Run one claimed data update to its end (succeeded, partial, failed or cancelled)."""
    from app.services.assistant import service
    from app.services.research import saving

    with session_factory()() as s, s.begin():
        job = s.get(ResearchJob, job_id)
        assert job is not None
        sector, question, language = job.sector, job.question, job.language
    started = _now()
    _save(
        job_id,
        stage=STEP,
        steps=[{"stage": STEP, "state": "running", "started_at": started.isoformat()}],
    )
    with session_factory()() as lock_session, _lock(lock_session, sector) as got:
        if not got:
            _finish(
                job_id,
                "failed",
                "already_running",
                {"reason": "another update of this sector is running"},
                started,
            )
            return
        tracker = JobTracker(job_id)
        try:
            tracker.check()
            with session_factory()() as s:
                principal = saving.research_principal(s)
            reply = service.generate_reply(
                question,
                [],
                language,
                DataMode.VERIFIED_SOURCE,
                web=True,
                mode="research",
                tracker=tracker,
                submitter=principal,
                job_id=job_id,
            )
        except Cancelled:
            _finish(job_id, "cancelled", None, {}, started)
            return
        except Exception:  # noqa: BLE001 - recorded; nothing was saved by a failed run
            log.exception("data update %s failed", job_id)
            _finish(job_id, "failed", "internal_error", {}, started)
            return
    if reply.status == "cancelled":
        _finish(job_id, "cancelled", None, {}, started)
        return
    research = (reply.structured or {}).get("research") or {}
    result = {
        "answer_status": reply.status,
        "answer": reply.content[:4000],
        "summary": research,
        "method": (reply.structured or {}).get("method"),
    }
    if reply.status in ("unavailable", "data_report") and not research.get("submitted"):
        _finish(job_id, "failed", "answer_service_failed", result, started)
        return
    saved = len(research.get("saved") or [])
    state = "succeeded" if research.get("sources_read") else "partial"
    _finish(
        job_id,
        state,
        None if state == "succeeded" else "no_document_read",
        result,
        started,
        saved=saved,
    )


def _finish(
    job_id: uuid.UUID,
    state: str,
    code: str | None,
    result: dict[str, Any],
    started: datetime,
    *,
    saved: int = 0,
) -> None:
    with session_factory()() as s, s.begin():
        searches = s.scalar(select(func.count()).where(ResearchSearch.job_id == job_id)) or 0
        documents = s.scalar(select(func.count()).where(ResearchDocument.job_id == job_id)) or 0
    step = {
        "stage": STEP,
        "state": {"succeeded": "done", "partial": "done"}.get(state, state),
        "started_at": started.isoformat(),
        "finished_at": _now().isoformat(),
        "outcome": {"searches": searches, "documents_read": documents, "saved": saved},
    }
    _save(
        job_id,
        state=state,
        stage=None,
        steps=[step],
        result={**result, "searches": searches, "documents_read": documents},
        error_code=code,
        finished_at=_now(),
        credits_used=int(searches) + int(documents),
    )
