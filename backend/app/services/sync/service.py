"""Checking official feeds for new releases and staging their new figures.

A check (scheduled by the sync worker, or started by an administrator) does this:

1. reads the feed's public list of publications (bounded retries with backoff);
2. records every matching release it has not seen, with the publisher's own dates;
3. for a new release with an official workbook: downloads it, reads the mapped tables, and
   compares every figure with what OSRIP already publishes (same indicator, area, period,
   completeness and unit): figures that are the same (at the precision both publications
   give) are skipped, so a repeated check or a re-sent file adds nothing; new and changed
   figures are staged as one ordinary import, validated by the import workflow;
4. leaves the staged import for a data manager to approve, unless the feed's administrator
   switched on automatic publication (then it is approved and published by the sync
   account, all or nothing).

Nothing published is ever replaced or removed by a check: a failed request, an unreadable
listing or workbook, or a validation error leaves the published data as they were, and is
written to the synchronisation log. A successful check is not a new publication: the time of
the last successful check, the latest release's publication date and the latest observation
period are kept and shown apart.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.domain.enums import DataMode, DatasetVersionStatus, Permission, Role
from app.models import (
    AppUser,
    Area,
    DatasetVersion,
    ImportJob,
    Indicator,
    Observation,
    Source,
    SourceFeed,
    SourceRelease,
    SourceSyncRun,
    Unit,
)
from app.services import accounts
from app.services.imports import workflow
from app.services.principal import Principal
from app.services.sync import fetch, ncsi_listing
from app.services.sync.ncsi_msb import LayoutError, Record
from app.services.sync.registry import FEEDS, LICENCE, FeedSpec, release_label
from app.services.sync.xlsx import WorkbookError

log = logging.getLogger("osrip.sync")

SYNC_EMAIL = "source-sync@osrip.invalid"
SYSTEM = Principal(user_id=None, label="system:source-sync")
XLSX_TYPES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
)
MAX_LISTING_BYTES = 3_000_000
MAX_FILE_BYTES = 30_000_000
MAX_RELEASES_PER_CHECK = 3
CSV_FIELDS = (
    "record_ref",
    "indicator_code",
    "area_code",
    "partner_code",
    "flow",
    "period_start",
    "period_end",
    "period_complete",
    "frequency",
    "statement_date",
    "unit_code",
    "value",
    "value_operator",
    "revision_status",
    "source_locator",
)

# Tests replace these to run without the network (and without waiting between retries).
fetch_attempts = 3
fetch_backoff = 2.0


def now() -> datetime:
    return datetime.now(UTC)


def _short(message: str) -> str:
    return message[:500]


# ------------------------------------------------------------------ comparison


def _decimals(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def same_figure(a: Decimal, b: Decimal) -> bool:
    """Equal at the precision both publications give (427.9 and 427.90 are the same figure;
    5743.9 and 5745.6 are not)."""
    places = min(_decimals(a), _decimals(b))
    quantum = Decimal(1).scaleb(-places)
    return a.quantize(quantum) == b.quantize(quantum)


@dataclass(slots=True)
class Delta:
    new: list[Record] = field(default_factory=list)
    revised: list[Record] = field(default_factory=list)
    unchanged: list[Record] = field(default_factory=list)


def compare(session: Session, records: list[Record]) -> Delta:
    """Each record against the published verified-source figures for the same series and
    period (national, governorate and group areas; no partner, product or flow)."""
    codes = sorted({r.indicator_code for r in records})
    rows = session.execute(
        select(
            Indicator.code,
            Area.code,
            Unit.code,
            Observation.period_start,
            Observation.period_end,
            Observation.period_complete,
            Observation.value,
        )
        .join(Indicator, Indicator.id == Observation.indicator_id)
        .join(Area, Area.id == Observation.area_id)
        .join(Unit, Unit.id == Observation.unit_id)
        .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
        .where(
            Observation.data_mode == DataMode.VERIFIED_SOURCE,
            DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
            Indicator.code.in_(codes),
            Observation.partner_id.is_(None),
            Observation.commodity_id.is_(None),
            Observation.flow.is_(None),
            Observation.value.is_not(None),
        )
    )
    published: dict[tuple[Any, ...], list[Decimal]] = {}
    for ind, area, unit, start, end, complete, value in rows:
        published.setdefault((ind, area, start, end, complete, unit), []).append(value)
    out = Delta()
    for r in records:
        values = published.get(
            (
                r.indicator_code,
                r.area_code,
                r.period_start,
                r.period_end,
                r.period_complete,
                r.unit_code,
            )
        )
        if not values:
            out.new.append(r)
        elif any(same_figure(v, r.value) for v in values):
            out.unchanged.append(r)
        else:
            out.revised.append(r)
    return out


def records_csv(records: list[Record]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for r in records:
        writer.writerow(r.csv_row())
    return buffer.getvalue().encode("utf-8")


# ------------------------------------------------------------------ locking and accounts


@contextmanager
def feed_lock(session: Session, code: str) -> Iterator[bool]:
    """A PostgreSQL advisory lock per feed, held on its own connection for the whole check,
    so two workers (or a worker and a manual check) never process a feed at the same time."""
    bind = session.get_bind()
    with bind.connect() as conn:  # type: ignore[union-attr]
        key = conn.execute(select(func.hashtext(f"osrip.sync.{code}"))).scalar_one()
        got = bool(conn.execute(select(func.pg_try_advisory_lock(key))).scalar_one())
        conn.commit()
        try:
            yield got
        finally:
            if got:
                conn.execute(select(func.pg_advisory_unlock(key)))
                conn.commit()


def sync_principal(session: Session) -> Principal:
    """The service account that stages (and, if allowed, publishes) synced imports."""
    with session.begin():
        user = session.scalar(select(AppUser).where(AppUser.email == SYNC_EMAIL))
        if user is None:
            user = accounts.create_user(
                session,
                SYSTEM,
                email=SYNC_EMAIL,
                display_name="Official statistics sync",
                password=None,
                roles=[Role.DATA_MANAGER],
                service_account=True,
            )
            session.flush()
            for permission in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
                accounts.grant_permission(session, SYSTEM, user.id, permission)
        session.flush()
        return accounts.load_principal(session, user)


# ------------------------------------------------------------------ the check


@dataclass(slots=True)
class Outcome:
    status: str
    message: str | None = None
    http_status: int | None = None
    attempts: int = 1
    releases_seen: int = 0
    release_id: uuid.UUID | None = None


def _finish(session: Session, run_id: uuid.UUID, feed_id: uuid.UUID, outcome: Outcome) -> None:
    at = now()
    with session.begin():
        run = session.get(SourceSyncRun, run_id)
        feed = session.get(SourceFeed, feed_id, with_for_update=True)
        assert run is not None and feed is not None
        run.status, run.finished_at = outcome.status, at
        run.message = _short(outcome.message) if outcome.message else None
        run.http_status, run.attempts = outcome.http_status, min(outcome.attempts, 10)
        run.releases_seen, run.release_id = outcome.releases_seen, outcome.release_id
        feed.last_checked_at, feed.last_status, feed.updated_at = at, outcome.status, at
        interval = timedelta(hours=feed.check_interval_hours)
        if outcome.status == "failed":
            feed.consecutive_failures += 1
            feed.last_error = run.message
            # Back off: 1 h, 2 h, 4 h ... never later than the normal interval.
            feed.next_check_at = at + min(
                interval, timedelta(hours=2 ** (feed.consecutive_failures - 1))
            )
        elif outcome.status == "not_accessible":
            feed.last_error, feed.next_check_at = run.message, None
        else:
            feed.consecutive_failures, feed.last_error = 0, None
            feed.last_success_at, feed.next_check_at = at, at + interval
    log.info(
        "sync %s: %s%s", feed_id, outcome.status, f" ({outcome.message})" if outcome.message else ""
    )


RANK = {
    "no_new_release": 0,
    "new_release": 1,
    "unchanged": 2,
    "staged": 3,
    "published": 4,
    "failed": 5,
    "not_accessible": 6,
}


def run_check(
    session: Session, code: str, *, trigger: str = "schedule", requested_by: uuid.UUID | None = None
) -> dict[str, Any]:
    spec = FEEDS.get(code)
    with session.begin():
        feed = session.scalar(select(SourceFeed).where(SourceFeed.code == code))
        if feed is None or spec is None:
            raise not_found("source feed")
        run = SourceSyncRun(
            feed_id=feed.id, trigger=trigger, status="running", requested_by=requested_by
        )
        session.add(run)
        session.flush()
        run_id, feed_id, access, auto_publish = run.id, feed.id, feed.access, feed.auto_publish
    with feed_lock(session, code) as got:
        if not got:
            outcome = Outcome(
                "failed", "Another check of this feed is running; this one did nothing."
            )
        elif access != "public_listing" or spec.listing_url is None:
            outcome = Outcome("not_accessible", spec.notes_en)
        else:
            outcome = _check(session, spec, feed_id, auto_publish)
    _finish(session, run_id, feed_id, outcome)
    return run_out(session, run_id)


def _check(session: Session, spec: FeedSpec, feed_id: uuid.UUID, auto_publish: bool) -> Outcome:
    assert spec.listing_url is not None
    try:
        page = fetch.get(
            spec.listing_url,
            hosts=spec.listing_hosts,
            accept=("text/html",),
            max_bytes=MAX_LISTING_BYTES,
            attempts=fetch_attempts,
            backoff=fetch_backoff,
        )
        publications = ncsi_listing.parse(page.body)
    except fetch.FetchError as exc:
        return Outcome(
            "failed",
            f"The list of publications could not be read: {exc.reason}.",
            http_status=exc.status,
            attempts=exc.attempts,
        )
    except ncsi_listing.ListingError as exc:
        return Outcome(
            "failed", f"The list of publications changed its layout: {exc}.", http_status=200
        )
    matching = [(p, label) for p in publications if (label := release_label(spec, p.title_en))]
    outcome = Outcome(
        "no_new_release",
        http_status=page.status,
        attempts=page.attempts,
        releases_seen=len(matching),
    )
    with session.begin():
        known = {
            (r.external_id, r.file_url): r.status
            for r in session.scalars(select(SourceRelease).where(SourceRelease.feed_id == feed_id))
        }
    fresh = [
        (p, label)
        for p, label in matching
        if known.get((p.id, p.xls_url)) not in ("unchanged", "staged", "published", "no_file")
    ]
    fresh.sort(key=lambda item: item[0].created_at or datetime.min.replace(tzinfo=UTC))
    for publication, label in fresh[:MAX_RELEASES_PER_CHECK]:
        result = _release(session, spec, feed_id, publication, label, auto_publish)
        outcome.release_id = result.release_id
        # The check reports its most significant result: a failure first, then a publication.
        if RANK[result.status] > RANK[outcome.status]:
            outcome.status, outcome.message = result.status, result.message
            outcome.http_status = result.http_status or outcome.http_status
    return outcome


def _record_release(
    session: Session,
    feed_id: uuid.UUID,
    publication: ncsi_listing.Publication,
    sha: str | None,
    size: int | None,
) -> uuid.UUID:
    with session.begin():
        existing = session.scalar(
            select(SourceRelease).where(
                SourceRelease.feed_id == feed_id,
                SourceRelease.external_id == publication.id,
                SourceRelease.file_sha256.is_(None)
                if sha is None
                else SourceRelease.file_sha256 == sha,
            )
        )
        if existing is None:
            existing = SourceRelease(
                feed_id=feed_id,
                external_id=publication.id,
                title_en=publication.title_en[:300],
                title_ar=(publication.title_ar or None) and publication.title_ar[:300],
                published_at=publication.created_at,
                source_updated_at=publication.updated_at,
                file_url=publication.xls_url,
                file_sha256=sha,
                file_bytes=size,
                status="detected",
            )
            session.add(existing)
            session.flush()
        else:
            existing.source_updated_at = publication.updated_at
        return existing.id


def _set_release(session: Session, release_id: uuid.UUID, **fields: Any) -> None:
    with session.begin():
        release = session.get(SourceRelease, release_id)
        assert release is not None
        for key, value in fields.items():
            setattr(release, key, value)
        release.processed_at = now()


def _release(
    session: Session,
    spec: FeedSpec,
    feed_id: uuid.UUID,
    publication: ncsi_listing.Publication,
    label: str,
    auto_publish: bool,
) -> Outcome:
    if publication.xls_url is None:
        rid = _record_release(session, feed_id, publication, None, None)
        message = (
            "This release has no official workbook (PDF only); its figures can be imported by hand."
        )
        _set_release(session, rid, status="no_file", message=message)
        return Outcome("new_release", message, release_id=rid)
    try:
        got = fetch.get(
            publication.xls_url,
            hosts=spec.file_hosts,
            accept=XLSX_TYPES,
            max_bytes=MAX_FILE_BYTES,
            attempts=fetch_attempts,
            backoff=fetch_backoff,
        )
    except fetch.FetchError as exc:
        rid = _record_release(session, feed_id, publication, None, None)
        message = f"The workbook could not be downloaded: {exc.reason}."
        _set_release(session, rid, status="failed", message=message)
        return Outcome(
            "failed", message, http_status=exc.status, attempts=exc.attempts, release_id=rid
        )
    return process_workbook(session, spec, feed_id, publication, label, got.body, auto_publish)


def process_workbook(
    session: Session,
    spec: FeedSpec,
    feed_id: uuid.UUID,
    publication: ncsi_listing.Publication,
    label: str,
    data: bytes,
    auto_publish: bool,
) -> Outcome:
    """Read, compare and stage one release's workbook (also used for an uploaded file)."""
    sha = hashlib.sha256(data).hexdigest()
    rid = _record_release(session, feed_id, publication, sha, len(data))
    with session.begin():
        release = session.get(SourceRelease, rid)
        assert release is not None
        if release.status in ("unchanged", "staged", "published"):
            return Outcome(
                "unchanged", "This file was processed before; nothing was added.", release_id=rid
            )
    assert spec.parser is not None
    try:
        parsed = spec.parser(data, label)
    except (LayoutError, WorkbookError) as exc:
        message = f"The workbook does not have the verified layout ({exc}); nothing was imported."
        _set_release(session, rid, status="failed", message=_short(message))
        return Outcome("failed", message, release_id=rid)
    with session.begin():
        delta = compare(session, parsed.records)
    counts = {
        "rows_read": len(parsed.records),
        "rows_new": len(delta.new),
        "rows_revised": len(delta.revised),
        "rows_unchanged": len(delta.unchanged),
    }
    checks = f" Consistency notes: {'; '.join(parsed.checks)}." if parsed.checks else ""
    staged = delta.new + delta.revised
    if not staged:
        message = (
            f"All {len(parsed.records)} figures are already published; nothing was added.{checks}"
        )
        _set_release(session, rid, status="unchanged", message=_short(message), **counts)
        return Outcome("unchanged", message, release_id=rid)
    actor = sync_principal(session)
    tables = ", ".join(parsed.tables)
    source = workflow.register_source(
        session,
        actor,
        data_mode=DataMode.VERIFIED_SOURCE,
        dataset_title=f"{publication.title_en} (official workbook, tables {tables})"[:300],
        publisher="National Centre for Statistics and Information (NCSI)",
        url=publication.xls_url,
        locator_kind="direct_file",
        access_date=date.today(),
        publication_date=publication.created_at.date() if publication.created_at else None,
        reference_period=f"{label}; NCSI publication list entry {publication.id}",
        geographic_coverage="Oman (national, governorates and governorate groups as published)",
        definition_note=(
            "Tables " + ", ".join(parsed.tables) + " of the official workbook; figures "
            "as displayed by the publisher. Only figures new or changed since the "
            "previously published releases are in this version."
        ),
        reuse_conditions=LICENCE,
        source_code=label,
        source_role="primary",
    )
    state = workflow.create_import(
        session,
        actor,
        source_id=source.id,
        version_label=f"{label}-{sha[:8]}",
        filename=f"{label}.csv",
        data=records_csv(staged),
    )
    import_id = state.job.id
    state = workflow.validate_import(session, actor, import_id)
    with session.begin():
        job = session.get(ImportJob, import_id)
        assert job is not None
        rejected = job.rejected_row_count or 0
    status = "staged"
    message = (
        f"{len(delta.new)} new and {len(delta.revised)} changed figures staged for approval "
        f"({len(delta.unchanged)} already published).{checks}"
    )
    if rejected:
        message = (
            f"{rejected} figures were rejected by validation; a data manager must review "
            f"the import.{checks}"
        )
    elif auto_publish and state.version.status is DatasetVersionStatus.VALIDATED:
        workflow.approve_import(
            session,
            actor,
            import_id,
            acknowledged_rejected_rows=0,
            note=f"Published automatically by the {spec.code} sync (switched on by an "
            "administrator).",
        )
        workflow.publish_import(session, actor, import_id)
        status = "published"
        message = (
            f"{len(delta.new)} new and {len(delta.revised)} changed figures published "
            f"({len(delta.unchanged)} already published).{checks}"
        )
    _set_release(
        session, rid, status=status, message=_short(message), import_job_id=import_id, **counts
    )
    return Outcome(status, message, release_id=rid)


def run_upload(
    session: Session,
    code: str,
    data: bytes,
    *,
    title_en: str,
    file_url: str,
    published_on: date | None,
    requested_by: uuid.UUID | None,
) -> dict[str, Any]:
    """An official workbook a data manager downloaded by hand, processed exactly like a
    downloaded one (same layout checks, comparison and staging). ``file_url`` is the
    official address of the file, kept as its provenance."""
    spec = FEEDS.get(code)
    label = release_label(spec, title_en) if spec else None
    with session.begin():
        feed = session.scalar(select(SourceFeed).where(SourceFeed.code == code))
        if feed is None or spec is None or spec.parser is None:
            raise not_found("source feed")
        run = SourceSyncRun(
            feed_id=feed.id, trigger="upload", status="running", requested_by=requested_by
        )
        session.add(run)
        session.flush()
        run_id, feed_id = run.id, feed.id
    if label is None:
        outcome = Outcome(
            "failed",
            "The title must be the publication's own title, e.g. "
            "'Monthly Statistical Bulletin :October 2026'.",
        )
    else:
        sha = hashlib.sha256(data).hexdigest()
        published = (
            datetime(published_on.year, published_on.month, published_on.day, tzinfo=UTC)
            if published_on
            else None
        )
        publication = ncsi_listing.Publication(
            f"upload-{sha[:12]}", title_en.strip(), None, published, None, file_url, None
        )
        with feed_lock(session, code) as got:
            outcome = (
                process_workbook(session, spec, feed_id, publication, label, data, False)
                if got
                else Outcome("failed", "Another check of this feed is running; try again.")
            )
    _finish(session, run_id, feed_id, outcome)
    return run_out(session, run_id)


# ------------------------------------------------------------------ schedule and status


def due_feeds(session: Session, at: datetime | None = None) -> list[str]:
    at = at or now()
    with session.begin():
        return list(
            session.scalars(
                select(SourceFeed.code)
                .where(
                    SourceFeed.enabled.is_(True),
                    SourceFeed.access == "public_listing",
                    (SourceFeed.next_check_at.is_(None)) | (SourceFeed.next_check_at <= at),
                )
                .order_by(SourceFeed.code)
            )
        )


def _iso(value: datetime | date | None) -> str | None:
    """Times in UTC (the database may hand them back in its own zone); dates as dates."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value.isoformat() if value is not None else None


def release_out(r: SourceRelease) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "external_id": r.external_id,
        "title_en": r.title_en,
        "title_ar": r.title_ar,
        "published_at": _iso(r.published_at),
        "file_url": r.file_url,
        "file_sha256": r.file_sha256,
        "status": r.status,
        "rows_read": r.rows_read,
        "rows_new": r.rows_new,
        "rows_revised": r.rows_revised,
        "rows_unchanged": r.rows_unchanged,
        "import_id": str(r.import_job_id) if r.import_job_id else None,
        "message": r.message,
        "detected_at": _iso(r.detected_at),
        "processed_at": _iso(r.processed_at),
    }


def run_out(session: Session, run_id: uuid.UUID) -> dict[str, Any]:
    with session.begin():
        r = session.get(SourceSyncRun, run_id)
        assert r is not None
        return {
            "id": str(r.id),
            "trigger": r.trigger,
            "status": r.status,
            "started_at": _iso(r.started_at),
            "finished_at": _iso(r.finished_at),
            "attempts": r.attempts,
            "http_status": r.http_status,
            "releases_seen": r.releases_seen,
            "release_id": str(r.release_id) if r.release_id else None,
            "message": r.message,
        }


def feed_status(session: Session, feed: SourceFeed) -> dict[str, Any]:
    """Last successful check, latest release (the publisher's date) and latest observation
    period, kept apart: a successful check does not mean anything new was published."""
    spec = FEEDS.get(feed.code)
    latest = session.scalar(
        select(SourceRelease)
        .where(SourceRelease.feed_id == feed.id)
        .order_by(SourceRelease.published_at.desc().nulls_last(), SourceRelease.detected_at.desc())
        .limit(1)
    )
    observation = None
    if spec and spec.source_titles:
        conditions = [Source.dataset_title.ilike(f"{t}%") for t in spec.source_titles]
        row = session.execute(
            select(Observation.period_end, Indicator.code)
            .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
            .join(Source, Source.id == DatasetVersion.source_id)
            .join(Indicator, Indicator.id == Observation.indicator_id)
            .where(
                DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
                Observation.data_mode == DataMode.VERIFIED_SOURCE,
                Observation.value.is_not(None),
                or_(*conditions),
            )
            .order_by(Observation.period_end.desc())
            .limit(1)
        ).first()
        if row is not None:
            observation = {"period_end": row[0].isoformat(), "indicator": row[1]}
    return {
        "code": feed.code,
        "publisher": feed.publisher,
        "title": {"en": feed.title_en, "ar": feed.title_ar},
        "access": feed.access,
        "enabled": feed.enabled,
        "check_interval_hours": feed.check_interval_hours,
        "auto_publish": feed.auto_publish,
        "last_checked_at": _iso(feed.last_checked_at),
        "last_success_at": _iso(feed.last_success_at),
        "next_check_at": _iso(feed.next_check_at),
        "last_status": feed.last_status,
        "last_error": feed.last_error,
        "latest_release": None
        if latest is None
        else {
            "title_en": latest.title_en,
            "title_ar": latest.title_ar,
            "published_at": _iso(latest.published_at),
            "status": latest.status,
            "file_url": latest.file_url,
        },
        "latest_observation": observation,
        "indicators": list(spec.indicators) if spec else [],
        "tables": list(spec.tables) if spec else [],
        "notes": {"en": spec.notes_en, "ar": spec.notes_ar} if spec else None,
        "verified": spec.verified if spec else {},
    }


def statuses(session: Session) -> list[dict[str, Any]]:
    with session.begin():
        feeds = list(session.scalars(select(SourceFeed).order_by(SourceFeed.code)))
        return [feed_status(session, f) for f in feeds]
