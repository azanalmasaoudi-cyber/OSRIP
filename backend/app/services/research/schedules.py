"""Scheduled reports: an administrator's recurring studies (weekly, monthly or quarterly).

Nothing recurring runs by default: schedules run only when the server switches them on
(``OSRIP_SCHEDULED_REPORTS_ENABLED``), each schedule is created disabled, and a schedule whose
source scope calls external services (``official`` or ``official_international``) can be
enabled only with ``allow_paid`` (the database refuses it otherwise). Each run is limited by
the schedule's pages and credits per run, and skipped when its credits this month would pass
the monthly cap.
"""

from __future__ import annotations

import calendar
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.db.session import session_factory
from app.domain.enums import DataMode
from app.models import ReportSchedule, ResearchJob

log = logging.getLogger("osrip.schedules")


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    sector: Literal["electricity", "water", "food_security", "trade"]
    area: str = Field(default="OM", pattern=r"^[A-Z]{2}(-[A-Z0-9]{2,3}){0,2}$")
    data_mode: DataMode = DataMode.VERIFIED_SOURCE
    question: str = Field(min_length=3, max_length=1000)
    language: Literal["en", "ar"] = "en"
    frequency: Literal["weekly", "monthly", "quarterly"] = "monthly"
    source_scope: Literal["none", "official", "official_international"] = "none"
    max_pages: int = Field(default=5, ge=0, le=50)
    max_credits_per_run: int = Field(default=25, ge=0, le=1000)
    max_credits_per_month: int = Field(default=100, ge=0, le=10000)
    allow_paid: bool = False
    enabled: bool = False
    # study: a recurring study; data_update: research that reads official documents and saves
    # the figures validation can check (research/data_update.py).
    kind: Literal["study", "data_update"] = "study"

    @model_validator(mode="after")
    def _paid(self) -> ScheduleIn:
        if self.kind == "data_update" and self.source_scope == "none":
            raise ValueError("a data update searches official sources: source_scope official")
        if self.enabled and self.source_scope != "none" and not self.allow_paid:
            raise ValueError("a schedule that calls external services needs allow_paid to run")
        if self.max_credits_per_run > self.max_credits_per_month:
            raise ValueError("the credits per run exceed the monthly cap")
        return self


def now() -> datetime:
    return datetime.now(UTC)


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def next_after(frequency: str, moment: datetime) -> datetime:
    if frequency == "weekly":
        return moment + timedelta(days=7)
    return add_months(moment, 1 if frequency == "monthly" else 3)


def out(row: ReportSchedule, credits_this_month: int | None = None) -> dict[str, Any]:
    return {
        "id": str(row.id), "name": row.name, "sector": row.sector, "area": row.area,
        "data_mode": row.data_mode, "question": row.question, "language": row.language,
        "frequency": row.frequency, "source_scope": row.source_scope, "max_pages": row.max_pages,
        "max_credits_per_run": row.max_credits_per_run,
        "max_credits_per_month": row.max_credits_per_month, "allow_paid": row.allow_paid,
        "enabled": row.enabled, "paid": row.source_scope != "none", "kind": row.kind,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "credits_this_month": credits_this_month,
    }  # fmt: skip


def credits_this_month(session: Session, schedule_id: uuid.UUID) -> int:
    start = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(session.scalar(
        select(func.coalesce(func.sum(ResearchJob.credits_used), 0))
        .where(ResearchJob.schedule_id == schedule_id, ResearchJob.created_at >= start)
    ) or 0)  # fmt: skip


def status() -> dict[str, Any]:
    """What would run (no secret values): the server switch, and what is configured."""
    from app.services.research import firecrawl
    from app.services.research.search import get_search_provider

    s = get_settings()
    route = get_search_provider()
    return {
        "scheduler_enabled": s.scheduled_reports_enabled,
        "retrieval": {
            "firecrawl": "configured" if firecrawl.configured() else "not_configured",
            "search_route": getattr(route, "name", None) if route else None,
            "direct_fetch": True,
        },
        "limits": {
            "max_pages": s.crawl_max_pages, "max_depth": s.crawl_max_depth,
            "max_runtime_seconds": s.crawl_max_runtime_seconds, "max_credits": s.crawl_max_credits,
            "max_pdf_pages": s.crawl_max_pdf_pages,
            "host_interval_seconds": s.crawl_host_interval_seconds,
            "allowed_domains": list(s.crawl_allowed_domains),
        },
        "cache_hours": s.research_job_cache_hours,
    }  # fmt: skip


def list_all(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(select(ReportSchedule).order_by(ReportSchedule.created_at))
    return [out(r, credits_this_month(session, r.id)) for r in rows]


def _get(session: Session, schedule_id: uuid.UUID) -> ReportSchedule:
    row = session.get(ReportSchedule, schedule_id, with_for_update=True)
    if row is None:
        raise not_found("schedule")
    return row


def _validated(body: dict[str, Any]) -> ScheduleIn:
    try:
        return ScheduleIn.model_validate(body)
    except ValueError as exc:
        raise ApiError(422, "invalid_schedule", "The schedule is not valid.",
                       {"errors": str(exc)[:500]}) from exc  # fmt: skip


def create(session: Session, body: dict[str, Any], user_id: uuid.UUID | None) -> dict[str, Any]:
    v = _validated(body)
    row = ReportSchedule(**{**v.model_dump(), "data_mode": v.data_mode.value}, created_by=user_id)
    row.next_run_at = next_after(v.frequency, now()) if v.enabled else None
    session.add(row)
    session.flush()
    return out(row, 0)


def update(session: Session, schedule_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    row = _get(session, schedule_id)
    current = {k: v for k, v in out(row).items() if k in ScheduleIn.model_fields}
    v = _validated({**current, **body})
    was_enabled = row.enabled
    for key, value in {**v.model_dump(), "data_mode": v.data_mode.value}.items():
        setattr(row, key, value)
    if v.enabled and (not was_enabled or row.next_run_at is None):
        row.next_run_at = next_after(v.frequency, now())
    if not v.enabled:
        row.next_run_at = None
    row.updated_at = now()
    session.flush()
    return out(row, credits_this_month(session, row.id))


def delete(session: Session, schedule_id: uuid.UUID) -> None:
    session.delete(_get(session, schedule_id))


def start_run(session: Session, row: ReportSchedule) -> ResearchJob | None:
    """Queue one run of the schedule within its limits, or None when this month's credits
    would pass the cap."""
    from app.services.research import jobs

    if row.source_scope != "none" and not row.allow_paid:
        raise ApiError(409, "paid_not_allowed",
                       "This schedule calls external services; allow paid runs first.")  # fmt: skip
    if credits_this_month(session, row.id) + row.max_credits_per_run > row.max_credits_per_month:
        return None
    if row.kind == "data_update":
        from app.services.research import data_update

        running = session.scalar(
            select(ResearchJob.id).where(
                ResearchJob.schedule_id == row.id, ResearchJob.state.in_(("queued", "running"))
            )
        )
        if running is not None:
            return None  # never two runs of one schedule at a time
        return data_update.create(
            session, row.sector, user_id=row.created_by, schedule_id=row.id,
            question=row.question, language=row.language, max_pages=row.max_pages,
            max_credits=row.max_credits_per_run,
        )  # fmt: skip
    return jobs.create(
        session,
        {"sector": row.sector, "area": row.area, "question": row.question,
         "language": row.language, "data_mode": row.data_mode,
         "source_scope": row.source_scope, "max_pages": row.max_pages,
         "max_credits": row.max_credits_per_run},
        user_id=row.created_by, schedule_id=row.id, refresh=True,
    )  # fmt: skip


def run_now(session: Session, schedule_id: uuid.UUID) -> dict[str, Any]:
    from app.services.research import jobs

    row = _get(session, schedule_id)
    job = start_run(session, row)
    if job is None:
        raise ApiError(
            409, "monthly_cap_reached", "This schedule's credits for this month are used up."
        )
    row.last_run_at = now()
    return jobs.view(job)


def tick() -> int:
    """Queue the schedules that are due (only when the server switch is on)."""
    if not get_settings().scheduled_reports_enabled:
        return 0
    started = 0
    with session_factory()() as session, session.begin():
        due = session.scalars(
            select(ReportSchedule)
            .where(ReportSchedule.enabled.is_(True), ReportSchedule.next_run_at <= now())
            .with_for_update(skip_locked=True)
        ).all()
        for row in due:
            try:
                job = start_run(session, row)
            except ApiError:
                job = None
            if job is None:
                log.warning(
                    "schedule %s skipped: monthly credit cap or paid runs not allowed", row.id
                )
            else:
                started += 1
                row.last_run_at = now()
            row.next_run_at = next_after(row.frequency, now())
    if started:
        from app.services.research import jobs

        jobs.kick()
    return started


_timer: threading.Thread | None = None
_stop = threading.Event()


def start_scheduler(interval_seconds: float = 60.0) -> None:
    """Check for due schedules every minute (a daemon thread; nothing if switched off)."""
    global _timer
    if not get_settings().scheduled_reports_enabled or (_timer is not None and _timer.is_alive()):
        return

    def loop() -> None:
        while not _stop.wait(interval_seconds):
            try:
                tick()
            except Exception:  # noqa: BLE001 - the next tick tries again
                log.exception("scheduled reports tick failed")

    _stop.clear()
    _timer = threading.Thread(target=loop, name="osrip-schedules", daemon=True)
    _timer.start()


def stop_scheduler() -> None:
    _stop.set()
