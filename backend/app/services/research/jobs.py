"""Studies run as background jobs ("Create study"): a person chooses a sector, an area, a
period and a research question; the study then runs step by step without holding any HTTP
request open, and its status can be read, stopped, resumed or retried at any time.

Steps, each recorded with its state, time and outcome as it happens:

1. discover   - OSRIP's published sources for the sector; with a web scope, official pages
                found by the configured search route (and Firecrawl's site map when set up);
2. retrieve   - those documents, within the limits (``crawl.py``: scope, SSRF, robots.txt,
                rate, pages, depth, time, credits);
3. extract    - the passages of each document that mention the study's terms (untrusted
                excerpts for review; never added to the data);
4. validate   - the sector's headline series: units, periods, gaps, revisions, sources;
5. calculate  - the shortage and surplus analysis (deterministic, stored as a study run);
6. build      - the tables and charts: the series and the analysis's balance tables;
7. conclude   - main findings, evidence limitations, immediate actions, medium-term options;
8. next_steps - the questions and data the next study needs.

Steps 1-3 are optional (no web scope, nothing configured, or a failure leaves the study
"partial" with the reason); steps 4-8 are required. A transient failure is retried once per
step; a job interrupted by a restart resumes from its last completed step (its heartbeat is
older than ``research_job_stale_minutes``) up to ``max_attempts`` times. A study with the same
parameters on the same published data is served from cache for ``research_job_cache_hours``
unless a refresh is asked for. Nothing here writes to the published data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.db.session import session_factory
from app.domain.enums import DataMode, DatasetVersionStatus
from app.models import DatasetVersion, ResearchDocument, ResearchJob

log = logging.getLogger("osrip.research_jobs")

STAGES = ("discover", "retrieve", "extract", "validate", "calculate", "build", "conclude",
          "next_steps")  # fmt: skip
OPTIONAL = frozenset({"discover", "retrieve", "extract"})
LABELS = {
    "discover": {"en": "Discover sources", "ar": "اكتشاف المصادر"},
    "retrieve": {"en": "Retrieve documents", "ar": "استرجاع الوثائق"},
    "extract": {"en": "Extract evidence", "ar": "استخراج الأدلة"},
    "validate": {"en": "Validate data", "ar": "التحقق من البيانات"},
    "calculate": {"en": "Calculate", "ar": "الحساب"},
    "build": {"en": "Build tables and charts", "ar": "بناء الجداول والرسوم"},
    "conclude": {"en": "Write conclusions", "ar": "كتابة الاستنتاجات"},
    "next_steps": {"en": "Recommend next steps", "ar": "اقتراح الخطوات التالية"},
}
FINISHED = ("succeeded", "partial", "failed", "cancelled")
SECTOR_TERMS = {
    "electricity": ["electricity", "power", "generation", "consumption", "capacity", "GWh", "MW",
                    "كهرباء", "توليد", "استهلاك"],
    "water": ["water", "desalination", "production", "consumption", "m3", "مياه", "تحلية"],
    "food_security": ["food", "production", "self-sufficiency", "fish", "tonnes", "غذاء",
                      "اكتفاء", "إنتاج"],
    "trade": ["trade", "exports", "imports", "re-exports", "OMR", "تجارة", "صادرات", "واردات"],
}  # fmt: skip


class JobParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector: Literal["electricity", "water", "food_security", "trade"]
    area: str = Field(default="OM", pattern=r"^[A-Z]{2}(-[A-Z0-9]{2,3}){0,2}$")
    period_from: date | None = None
    period_to: date | None = None
    question: str = Field(min_length=3, max_length=1000)
    language: Literal["en", "ar"] = "en"
    data_mode: DataMode = DataMode.VERIFIED_SOURCE
    source_scope: Literal["none", "official", "official_international"] = "none"
    max_pages: int | None = Field(default=None, ge=0, le=50)
    max_depth: int | None = Field(default=None, ge=0, le=3)
    max_credits: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def _period(self) -> JobParams:
        if self.period_from and self.period_to and self.period_from > self.period_to:
            raise ValueError("period_from is after period_to")
        self.question = " ".join(self.question.split())
        return self


def now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------ creating and reading


def cache_key(p: JobParams, versions: list[str]) -> str:
    body = json.dumps(
        {**p.model_dump(mode="json"), "question": p.question.lower(), "versions": versions},
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def published_versions(session: Session, data_mode: DataMode) -> list[str]:
    rows = session.scalars(
        select(DatasetVersion.id).where(
            DatasetVersion.data_mode == data_mode,
            DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
        )
    )
    return sorted(str(r) for r in rows)


def _steps(state: str = "pending") -> list[dict[str, Any]]:
    return [{"stage": s, "state": state, "label": LABELS[s], "attempts": 0} for s in STAGES]


def create(
    session: Session,
    params: dict[str, Any],
    *,
    user_id: uuid.UUID | None,
    refresh: bool = False,
    schedule_id: uuid.UUID | None = None,
) -> ResearchJob:
    """Queue a study (the caller's transaction), or serve an identical recent one from cache."""
    try:
        p = JobParams.model_validate(params)
    except ValueError as exc:
        raise ApiError(422, "invalid_study_parameters", "The study parameters are not valid.",
                       {"errors": str(exc)[:500]}) from exc  # fmt: skip
    s = get_settings()
    from app.services.research import crawl

    limits = crawl.limits_for(p.source_scope, p.model_dump(include={"max_pages", "max_depth",
                                                                   "max_credits"}))  # fmt: skip
    key = cache_key(p, published_versions(session, p.data_mode))
    job = ResearchJob(
        user_id=user_id, schedule_id=schedule_id, sector=p.sector, area=p.area,
        period_from=p.period_from, period_to=p.period_to, question=p.question,
        language=p.language, data_mode=p.data_mode.value, source_scope=p.source_scope,
        limits=limits.as_dict(), state="queued", steps=_steps(), cache_key=key,
        max_attempts=max(1, min(s.research_job_max_attempts, 5)), result={},
    )  # fmt: skip
    if not refresh:
        cached = session.scalar(
            select(ResearchJob)
            .where(
                ResearchJob.cache_key == key,
                ResearchJob.state == "succeeded",
                ResearchJob.finished_at >= now() - timedelta(hours=s.research_job_cache_hours),
            )
            .order_by(ResearchJob.finished_at.desc())
            .limit(1)
        )
        if cached is not None:
            job.state, job.stage = "succeeded", None
            job.cached_from, job.analysis_id = cached.id, cached.analysis_id
            job.result = {**cached.result, "cached": True}
            job.steps = [{**st, "cached": True} for st in cached.steps]
            job.started_at = job.finished_at = now()
    session.add(job)
    session.flush()
    return job


def own(session: Session, job_id: uuid.UUID, user_id: uuid.UUID | None, *, admin: bool = False,
        lock: bool = False) -> ResearchJob:  # fmt: skip
    stmt = select(ResearchJob).where(ResearchJob.id == job_id)
    if not admin:
        stmt = stmt.where(ResearchJob.user_id == user_id)
    job = session.scalar(stmt.with_for_update() if lock else stmt)
    if job is None:
        raise not_found("study")
    return job


def view(job: ResearchJob) -> dict[str, Any]:
    done = sum(1 for s in job.steps if s.get("state") in ("done", "skipped", "failed"))
    return {
        "id": str(job.id),
        "sector": job.sector,
        "area": job.area,
        "period_from": job.period_from.isoformat() if job.period_from else None,
        "period_to": job.period_to.isoformat() if job.period_to else None,
        "question": job.question,
        "language": job.language,
        "data_mode": job.data_mode,
        "source_scope": job.source_scope,
        "limits": job.limits,
        "state": job.state,
        "stage": job.stage,
        "progress": round(100 * done / len(STAGES)),
        "steps": job.steps,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "cancel_requested": job.cancel_requested_at is not None,
        "error_code": job.error_code,
        "cached": job.cached_from is not None,
        "analysis_id": str(job.analysis_id) if job.analysis_id else None,
        "result": job.result,
        "credits_used": job.credits_used,
        "schedule_id": str(job.schedule_id) if job.schedule_id else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def list_mine(session: Session, user_id: uuid.UUID, limit: int = 30) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ResearchJob)
        .where(ResearchJob.user_id == user_id)
        .order_by(ResearchJob.created_at.desc())
        .limit(limit)
    )
    return [{k: v for k, v in view(j).items() if k != "result"} for j in rows]


def documents(session: Session, job: ResearchJob) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ResearchDocument)
        .where(ResearchDocument.job_id == job.id)
        .order_by(ResearchDocument.retrieved_at)
    )
    return [
        {
            "id": str(d.id), "url": d.url, "final_url": d.final_url, "host": d.host,
            "source_class": d.source_class, "publisher": d.publisher, "title": d.title,
            "retrieved_at": d.retrieved_at.isoformat() if d.retrieved_at else None,
            "published": d.published.isoformat() if d.published else None,
            "reporting_period": d.reporting_period, "content_type": d.content_type,
            "retriever": d.retriever, "status": d.status, "depth": d.depth, "pages": d.pages,
            "credits": d.credits, "sha256": d.sha256,
            "duplicate_of": str(d.duplicate_of) if d.duplicate_of else None,
            "revision_of": str(d.revision_of) if d.revision_of else None,
            "excerpt": d.excerpt, "untrusted": True,
        }
        for d in rows
    ]  # fmt: skip


def cancel(session: Session, job: ResearchJob) -> None:
    """A queued study stops at once; a running one at its next step or document."""
    if job.state == "queued":
        job.state, job.finished_at, job.cancel_requested_at = "cancelled", now(), now()
        job.steps = [{**s, "state": "cancelled"} if s["state"] == "pending" else s
                     for s in job.steps]  # fmt: skip
    elif job.state == "running" and job.cancel_requested_at is None:
        job.cancel_requested_at = now()


def retry(session: Session, job: ResearchJob) -> None:
    """Queue a failed, partial or cancelled study again; completed steps are kept."""
    if job.state not in ("failed", "partial", "cancelled"):
        raise ApiError(
            409, "study_not_retryable", "Only a failed, partial or stopped study can be retried."
        )
    job.state, job.finished_at, job.error_code, job.cancel_requested_at = "queued", None, None, None
    job.attempts = 0
    job.steps = [
        s if s["state"] == "done" else {**s, "state": "pending", "detail": None} for s in job.steps
    ]


# ------------------------------------------------------------------ the runner


class Cancelled(Exception):
    pass


class StepFailed(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _save(job_id: uuid.UUID, **values: Any) -> None:
    with session_factory()() as s, s.begin():
        s.execute(update(ResearchJob).where(ResearchJob.id == job_id).values(
            heartbeat_at=now(), **values))  # fmt: skip


def _load(job_id: uuid.UUID) -> ResearchJob:
    with session_factory()() as s, s.begin():
        job = s.get(ResearchJob, job_id)
        if job is None:
            raise not_found("study")
        s.expunge(job)
        return job


def _cancel_requested(job_id: uuid.UUID) -> bool:
    with session_factory()() as s, s.begin():
        return (
            s.scalar(select(ResearchJob.cancel_requested_at).where(ResearchJob.id == job_id))
            is not None
        )


def claim_next() -> uuid.UUID | None:
    """The oldest queued study, or a running one whose worker stopped (no heartbeat for
    ``research_job_stale_minutes``), marked running in one short transaction."""
    stale = now() - timedelta(minutes=get_settings().research_job_stale_minutes)
    while True:
        with session_factory()() as s, s.begin():
            job = s.scalar(
                select(ResearchJob)
                .where(or_(ResearchJob.state == "queued",
                           (ResearchJob.state == "running") & (ResearchJob.heartbeat_at < stale)))
                .order_by(ResearchJob.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )  # fmt: skip
            if job is None:
                return None
            job.attempts += 1
            if job.attempts > job.max_attempts:
                # Interrupted too often: stopped for good, with the steps it completed.
                job.state, job.error_code, job.finished_at = "failed", "too_many_attempts", now()
                job.stage = None
                continue
            job.state, job.heartbeat_at = "running", now()
            job.started_at = job.started_at or now()
            return job.id


def run(job_id: uuid.UUID) -> None:
    """Run the remaining steps of one claimed study."""
    job = _load(job_id)
    ctx = Context(job)
    try:
        for stage in STAGES:
            step = ctx.step(stage)
            if step["state"] in ("done", "skipped"):
                continue  # resumed: kept from an earlier attempt
            if _cancel_requested(job_id):
                raise Cancelled
            ctx.begin(stage)
            for attempt in (1, 2):
                try:
                    outcome = STEP_FUNCTIONS[stage](ctx)
                    break
                except Cancelled:
                    raise
                except (OperationalError, StepFailed) as exc:
                    transient = isinstance(exc, OperationalError) or (
                        isinstance(exc, StepFailed) and exc.code in TRANSIENT_CODES
                    )
                    if attempt == 1 and transient:
                        time.sleep(1.0)
                        continue
                    code = exc.code if isinstance(exc, StepFailed) else "database_unavailable"
                    outcome = {"state": "failed", "code": code}
                    break
                except Exception:  # noqa: BLE001 - recorded; a required step ends the study
                    log.exception("study %s step %s failed", job_id, stage)
                    outcome = {"state": "failed", "code": "internal_error"}
                    break
            ctx.end(stage, outcome)
            if outcome.get("state") == "failed" and stage not in OPTIONAL:
                _finish(job_id, ctx, "failed", outcome.get("code"))
                return
        partial = any(s["state"] == "failed" for s in ctx.steps)
        _finish(job_id, ctx, "partial" if partial else "succeeded", None)
    except Cancelled:
        ctx.steps = [{**s, "state": "cancelled"} if s["state"] in ("pending", "running") else s
                     for s in ctx.steps]  # fmt: skip
        _finish(job_id, ctx, "cancelled", None)


TRANSIENT_CODES = frozenset({"timeout", "network", "http_429", "http_500", "http_502",
                             "http_503", "http_504"})  # fmt: skip


def _finish(job_id: uuid.UUID, ctx: Context, state: str, code: str | None) -> None:
    _save(job_id, state=state, stage=None, steps=ctx.steps, result=ctx.result,
          error_code=code, finished_at=now(), credits_used=ctx.credits)  # fmt: skip


class Context:
    """One running study: its parameters, steps and accumulated result, saved after each step."""

    def __init__(self, job: ResearchJob) -> None:
        self.job = job
        self.id = job.id
        self.steps = [dict(s) for s in job.steps] or _steps()
        self.result = dict(job.result or {})
        self.credits = job.credits_used
        self.mode = DataMode(job.data_mode)

    def step(self, stage: str) -> dict[str, Any]:
        return next(s for s in self.steps if s["stage"] == stage)

    def begin(self, stage: str) -> None:
        st = self.step(stage)
        st.update(state="running", started_at=now().isoformat(), attempts=st.get("attempts", 0) + 1)
        _save(self.id, stage=stage, steps=self.steps)

    def end(self, stage: str, outcome: dict[str, Any]) -> None:
        st = self.step(stage)
        st.update(
            state=outcome.get("state", "done"), finished_at=now().isoformat(),
            detail=outcome.get("detail"), count=outcome.get("count"), code=outcome.get("code"),
        )  # fmt: skip
        _save(self.id, steps=self.steps, result=self.result, credits_used=self.credits)

    def cancelled(self) -> bool:
        return _cancel_requested(self.id)

    def terms(self) -> list[str]:
        words = [w for w in re.findall(r"[\w\-]{4,}", self.job.question) if not w.isdigit()]
        return list(dict.fromkeys(words[:8] + SECTOR_TERMS[self.job.sector]))


def T(en: str, ar: str) -> dict[str, str]:  # noqa: N802 - short bilingual constructor
    return {"en": en, "ar": ar}


# ------------------------------------------------------------------ the steps


def step_discover(ctx: Context) -> dict[str, Any]:
    from app.models import Indicator, Observation, Source
    from app.services.research import crawl, firecrawl
    from app.services.research.search import SearchError, get_search_provider
    from app.services.research.sources import PREFERRED_SITES, classify

    job = ctx.job
    with session_factory()() as s, s.begin():
        rows = s.execute(
            select(Source, DatasetVersion)
            .join(DatasetVersion, DatasetVersion.source_id == Source.id)
            .where(DatasetVersion.data_mode == ctx.mode,
                   DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
                   DatasetVersion.id.in_(
                       select(Observation.dataset_version_id)
                       .join(Indicator, Indicator.id == Observation.indicator_id)
                       .where(Indicator.section == job.sector)))
        ).all()  # fmt: skip
    ctx.result["sources"] = [
        {"id": str(src.id), "title": src.dataset_title, "publisher": src.publisher,
         "url": src.url, "source_code": src.source_code,
         "dataset_version": v.version_label,
         "published_at": v.published_at.isoformat() if v.published_at else None}
        for src, v in rows
    ]  # fmt: skip
    found: list[dict[str, Any]] = []
    notes: list[dict[str, str]] = []
    if job.source_scope != "none":
        hosts = tuple(job.limits.get("hosts") or ())
        sites = [
            h
            for h in PREFERRED_SITES.get(job.sector, [])
            if crawl.host_allowed(f"https://{h}/", hosts)
        ]
        route = get_search_provider()
        if route is None:
            notes.append(T("No web search route is configured; no pages were discovered by search.",
                           "لا توجد خدمة بحث مُعدّة؛ لم تُكتشف صفحات بالبحث."))  # fmt: skip
        else:
            for site in sites[:2]:
                try:
                    results = route.search(
                        f"{job.question} site:{site}", language=job.language, count=5
                    )
                except SearchError as exc:
                    notes.append(
                        T(f"The search of {site} failed ({exc}).", f"تعذّر البحث في {site} ({exc}).")
                    )
                    continue
                found += [{"url": r.url, "title": r.title, "via": "search"} for r in results]
        client = firecrawl.client()
        if client is not None and sites:
            try:
                for link in client.map(f"https://{sites[0]}", search=job.question, limit=5):
                    found.append({**link, "via": "firecrawl_map"})
                ctx.credits += 1
            except Exception as exc:  # noqa: BLE001 - reported, the study continues
                notes.append(T(f"Firecrawl could not map {sites[0]} ({str(exc)[:40]}).",
                               f"تعذّر على Firecrawl فهرسة {sites[0]} ({str(exc)[:40]})."))  # fmt: skip
        seen: set[str] = set()
        kept = []
        for f in found:
            if f["url"] in seen or not crawl.host_allowed(f["url"], hosts):
                continue
            seen.add(f["url"])
            info = classify(f["url"])
            kept.append({**f, "host": info["host"], "source_class": info["source_class"],
                         "publisher": info["publisher"]})  # fmt: skip
        found = kept[: max(1, int(job.limits.get("max_pages", 0)) * 2)]
    ctx.result["discovered"] = found
    ctx.result["discovery_notes"] = notes
    detail = T(f"{len(ctx.result['sources'])} published sources; {len(found)} official pages found.",
               f"{len(ctx.result['sources'])} مصدراً منشوراً؛ وعُثر على {len(found)} صفحة رسمية.")  # fmt: skip
    if job.source_scope == "none":
        detail = T(f"{len(ctx.result['sources'])} published sources (web sources not requested).",
                   f"{len(ctx.result['sources'])} مصدراً منشوراً (لم تُطلب مصادر الإنترنت).")  # fmt: skip
    return {"state": "done", "detail": detail, "count": len(found)}


def step_retrieve(ctx: Context) -> dict[str, Any]:
    from app.services.research import crawl

    job = ctx.job
    candidates = ctx.result.get("discovered") or []
    if job.source_scope == "none":
        return {
            "state": "skipped",
            "detail": T("Web sources were not requested.", "لم تُطلب مصادر الإنترنت."),
        }
    if not candidates:
        return {
            "state": "skipped",
            "detail": T("No official pages to retrieve.", "لا توجد صفحات رسمية لاسترجاعها."),
        }
    limits = crawl.Limits(**{k: (tuple(v) if k == "hosts" else v) for k, v in job.limits.items()})
    retriever = crawl.Retriever(limits, ctx.terms(), cancelled=ctx.cancelled)
    docs = retriever.run(candidates)
    ctx.credits += retriever.credits
    stored = _store_documents(job.id, docs)
    ok = sum(1 for d in docs if d.status == "ok")
    ctx.result["documents"] = {"retrieved": ok, "attempted": len(docs), "stored": stored,
                               "stopped": retriever.stopped,
                               "by_status": _count(d.status for d in docs)}  # fmt: skip
    if retriever.stopped == "cancelled":
        raise Cancelled
    detail = T(f"{ok} of {len(docs)} documents retrieved" + (f"; stopped: {retriever.stopped}" if retriever.stopped else "") + ".",
               f"استُرجعت {ok} من {len(docs)} وثيقة" + (f"؛ توقف الاسترجاع: {retriever.stopped}" if retriever.stopped else "") + ".")  # fmt: skip
    if ok == 0 and docs:
        return {"state": "failed", "code": "no_document_retrieved", "detail": detail, "count": 0}
    return {"state": "done", "detail": detail, "count": ok}


def _count(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _store_documents(job_id: uuid.UUID, docs: list[Any]) -> int:
    """Rows with provenance; duplicates (same content) and revisions (same address, new
    content) are linked to the earlier document."""
    with session_factory()() as s, s.begin():
        by_sha: dict[str, uuid.UUID] = {}
        for d in docs:
            row = ResearchDocument(
                job_id=job_id, url=d.url[:2048], final_url=(d.final_url or None) and d.final_url[:2048],
                host=d.host, source_class=d.source_class, publisher=d.publisher, title=d.title,
                retrieved_at=d.retrieved_at, published=d.published, reporting_period=d.reporting_period,
                content_type=d.content_type, retriever=d.retriever,
                status=re.sub(r"[^a-z0-9_]", "_", d.status.lower())[:40] or "failed",
                depth=min(d.depth, 3), pages=d.pages, credits=d.credits, sha256=d.sha256,
                excerpt=(d.excerpt or None) and d.excerpt[:20000],
            )  # fmt: skip
            if d.sha256:
                earlier = s.scalar(
                    select(ResearchDocument)
                    .where(ResearchDocument.url == row.url, ResearchDocument.sha256.is_not(None),
                           ResearchDocument.job_id != job_id)
                    .order_by(ResearchDocument.retrieved_at.desc()).limit(1)
                )  # fmt: skip
                if d.sha256 in by_sha:
                    row.duplicate_of = by_sha[d.sha256]
                elif earlier is not None and earlier.sha256 == d.sha256:
                    row.duplicate_of = earlier.id
                elif earlier is not None:
                    row.revision_of = earlier.id
            s.add(row)
            s.flush()
            if d.sha256 and d.sha256 not in by_sha:
                by_sha[d.sha256] = row.id
        return len(docs)


_FIGURE = re.compile(
    r"\d[\d,.]*\s*(%|٪|GWh|MWh|MW|m3|tonnes?|OMR|million|billion|مليون|طن)", re.IGNORECASE
)


def step_extract(ctx: Context) -> dict[str, Any]:
    job = ctx.job
    if job.source_scope == "none":
        return {"state": "skipped", "detail": T("No documents to read.", "لا توجد وثائق لقراءتها.")}
    with session_factory()() as s, s.begin():
        docs = s.scalars(
            select(ResearchDocument).where(ResearchDocument.job_id == job.id,
                                           ResearchDocument.status == "ok",
                                           ResearchDocument.duplicate_of.is_(None))
        ).all()  # fmt: skip
        excerpts = []
        for d in docs:
            lines = [ln.strip() for ln in (d.excerpt or "").split("\n") if _FIGURE.search(ln)]
            for line in lines[:5]:
                excerpts.append({"document_id": str(d.id), "url": d.final_url or d.url,
                                 "publisher": d.publisher, "source_class": d.source_class,
                                 "title": d.title, "reporting_period": d.reporting_period,
                                 "text": line[:500], "untrusted": True,
                                 "status": "unreviewed"})  # fmt: skip
    ctx.result["excerpts"] = excerpts[:60]
    if not docs:
        return {
            "state": "skipped",
            "detail": T("No document was retrieved.", "لم تُسترجع أي وثيقة."),
        }
    return {"state": "done", "count": len(excerpts),
            "detail": T(f"{len(excerpts)} passages with figures, for review (not added to the data).",
                        f"{len(excerpts)} مقطعاً تتضمن أرقاماً، للمراجعة (لم تُضف إلى البيانات).")}  # fmt: skip


def step_validate(ctx: Context) -> dict[str, Any]:
    from app.services import timeline
    from app.services.assistant.data_report import HEADLINES

    job = ctx.job
    checks = []
    with session_factory()() as s, s.begin():
        s.execute(text("SET TRANSACTION READ ONLY"))
        for code in HEADLINES[job.sector].get(ctx.mode, ()):
            try:
                doc = timeline.build(s, ctx.mode, code, area=job.area, view="annual",
                                     period_from=job.period_from, period_to=job.period_to)  # fmt: skip
            except ApiError:
                continue
            if doc["status"] != "ok":
                checks.append({"indicator": code, "status": doc["status"]})
                continue
            rows = doc["rows"]
            checks.append({
                "indicator": code, "name": doc["indicator"]["name"], "status": "ok",
                "unit": doc["unit"], "available_views": doc["available_views"],
                "dataset_id": doc["dataset_id"], "rows": len(rows),
                "with_value": sum(1 for r in rows if r["value"] is not None),
                "missing": sum(1 for r in rows if r["value"] is None),
                "revised": sum(1 for r in rows if r["revised"]),
                "year_to_date": len(doc["year_to_date"]),
                "rules": [r["code"] for r in doc["rules"]],
                "sources": len(doc["sources"]),
            })  # fmt: skip
    ctx.result["validation"] = checks
    usable = [c for c in checks if c.get("status") == "ok" and c.get("with_value")]
    if not usable:
        return {"state": "done", "count": 0,
                "detail": T("No published series for this sector and area in this period.",
                            "لا توجد سلاسل منشورة لهذا القطاع والمنطقة في هذه الفترة.")}  # fmt: skip
    return {"state": "done", "count": len(usable),
            "detail": T(f"{len(usable)} series checked (units, periods, gaps, revisions).",
                        f"فُحصت {len(usable)} سلسلة (الوحدات والفترات والفجوات والمراجعات).")}  # fmt: skip


def step_calculate(ctx: Context) -> dict[str, Any]:
    from app.services.analysis import balance

    job = ctx.job
    with session_factory()() as s, s.begin():
        stored = balance.run(s, {"sector": job.sector, "area": job.area}, ctx.mode, job.user_id)
    analysis = stored["analysis"]
    ctx.result["analysis"] = {
        "id": stored["id"], "status": analysis["status"], "title": analysis["title"],
        "balances": [{"id": b["id"], "title": b["title"], "status": b["status"],
                      "status_label": b["status_label"]} for b in analysis["balances"]],
        "recommendations": len(analysis["recommendations"]),
    }  # fmt: skip
    _save(ctx.id, analysis_id=uuid.UUID(stored["id"]))
    determined = sum(1 for b in analysis["balances"] if b["status"] != "not_determinable")
    return {"state": "done", "count": determined,
            "detail": T(f"{determined} of {len(analysis['balances'])} balances determined.",
                        f"حُدّد {determined} من {len(analysis['balances'])} موازين.")}  # fmt: skip


def step_build(ctx: Context) -> dict[str, Any]:
    job = ctx.job
    tables = [
        {"indicator": c["indicator"], "name": c["name"], "view": "annual",
         "dataset_id": c["dataset_id"], "unit": c["unit"],
         "params": {"data_mode": job.data_mode, "indicator": c["indicator"], "area": job.area,
                    "view": "annual",
                    "period_from": job.period_from.isoformat() if job.period_from else None,
                    "period_to": job.period_to.isoformat() if job.period_to else None}}
        for c in ctx.result.get("validation", []) if c.get("status") == "ok" and c.get("with_value")
    ]  # fmt: skip
    ctx.result["tables"] = tables
    balances = len((ctx.result.get("analysis") or {}).get("balances") or [])
    return {"state": "done", "count": len(tables) + balances,
            "detail": T(f"{len(tables)} series tables and charts, and {balances} balance tables.",
                        f"{len(tables)} جدولاً ورسماً للسلاسل، و{balances} جدولاً للموازين.")}  # fmt: skip


def step_conclude(ctx: Context) -> dict[str, Any]:
    from app.models import StudyRun

    with session_factory()() as s, s.begin():
        row = s.get(StudyRun, uuid.UUID(ctx.result["analysis"]["id"]))
        doc = row.result if row is not None else {}
    end = doc.get("conclusion") or {}
    recs = {r["id"]: r for r in doc.get("recommendations", [])}
    documents = ctx.result.get("documents") or {}
    web = []
    if ctx.job.source_scope != "none":
        n = int(documents.get("retrieved", 0))
        web.append(T(f"{n} web documents were retrieved; their figures are unreviewed and are not part of these results.",
                     f"استُرجعت {n} وثيقة من الإنترنت؛ أرقامها غير مُراجَعة وليست جزءاً من هذه النتائج."))  # fmt: skip
    ctx.result["conclusion"] = {
        "main_findings": end.get("main_findings", []),
        "evidence_limitations": end.get("evidence_limitations", []) + web,
        "immediate_actions": [{"id": i, "action": recs[i]["action"], "priority": recs[i]["priority"]}
                              for i in end.get("immediate_actions", []) if i in recs],
        "medium_term_options": [{"id": i, "action": recs[i]["action"], "priority": recs[i]["priority"]}
                                for i in end.get("medium_term_options", []) if i in recs],
        "written_by": "rules",  # deterministic, from the analysis (no AI)
    }  # fmt: skip
    return {"state": "done", "count": len(end.get("main_findings", [])),
            "detail": T("Conclusions written from the analysis by fixed rules (no AI).",
                        "كُتبت الاستنتاجات من التحليل بقواعد ثابتة (دون ذكاء اصطناعي).")}  # fmt: skip


def step_next(ctx: Context) -> dict[str, Any]:
    from app.models import StudyRun
    from app.services.research import firecrawl
    from app.services.research.search import get_search_provider

    with session_factory()() as s, s.begin():
        row = s.get(StudyRun, uuid.UUID(ctx.result["analysis"]["id"]))
        doc = row.result if row is not None else {}
    steps = [{"question": n["question"], "data": n["data"], "where": n.get("where")}
             for n in (doc.get("conclusion") or {}).get("next_study", [])]  # fmt: skip
    if ctx.job.source_scope == "none":
        steps.append({"question": T("Do official publications add figures that OSRIP does not hold yet?",
                                    "هل تضيف المنشورات الرسمية أرقاماً لا تملكها OSRIP بعد؟"),
                      "data": T("Run the study again with official web sources.",
                                "أعد تشغيل الدراسة مع مصادر الإنترنت الرسمية."), "where": None})  # fmt: skip
    elif get_search_provider() is None and firecrawl.client() is None:
        steps.append({"question": T("Which official pages should be read?", "ما الصفحات الرسمية التي ينبغي قراءتها؟"),
                      "data": T("Set up a web search route or Firecrawl in Settings › Services.",
                                "إعداد خدمة بحث أو Firecrawl في الإعدادات › الخدمات."), "where": None})  # fmt: skip
    if ctx.result.get("excerpts"):
        steps.append({"question": T("Do the retrieved figures belong in OSRIP's data?",
                                    "هل تنتمي الأرقام المسترجعة إلى بيانات OSRIP؟"),
                      "data": T("A data manager reviews the excerpts against their sources.",
                                "يراجع مدير البيانات المقاطع مقابل مصادرها."), "where": None})  # fmt: skip
    ctx.result["next_steps"] = steps
    return {"state": "done", "count": len(steps),
            "detail": T(f"{len(steps)} questions and data needs for the next study.",
                        f"{len(steps)} أسئلة واحتياجات بيانات للدراسة التالية.")}  # fmt: skip


STEP_FUNCTIONS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "discover": step_discover,
    "retrieve": step_retrieve,
    "extract": step_extract,
    "validate": step_validate,
    "calculate": step_calculate,
    "build": step_build,
    "conclude": step_conclude,
    "next_steps": step_next,
}


# ------------------------------------------------------------------ the worker thread


_lock = threading.Lock()
_worker: threading.Thread | None = None


def drain(limit: int | None = None) -> int:
    """Run queued studies one after another until none is left (or ``limit`` ran)."""
    ran = 0
    while limit is None or ran < limit:
        job_id = claim_next()
        if job_id is None:
            break
        try:
            run(job_id)
        except Exception:  # noqa: BLE001 - one broken study must not stop the others
            log.exception("study %s stopped unexpectedly", job_id)
            _save(
                job_id, state="failed", error_code="internal_error", finished_at=now(), stage=None
            )
        ran += 1
    return ran


def kick() -> None:
    """Start the worker thread if it is not running (it stops when the queue is empty)."""
    global _worker
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=drain, name="osrip-studies", daemon=True)
        _worker.start()


def wait_idle(timeout: float = 30.0) -> bool:
    """For tests and shutdown: wait until the worker thread has finished."""
    worker = _worker
    if worker is None:
        return True
    worker.join(timeout)
    return not worker.is_alive()
