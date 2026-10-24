"""Official statistics feeds: public status (last successful check, latest release and latest
observation kept apart), and for administrators the schedule, a manual check, an upload of a
workbook downloaded by hand, the release list and the synchronisation log.

Scheduled checks are never run here: they run in the sync worker (``python -m app.worker``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession, require, require_any
from app.core.errors import not_found, unprocessable
from app.domain.enums import Permission
from app.models import SourceFeed, SourceRelease, SourceSyncRun
from app.services import audit
from app.services.principal import Principal
from app.services.sync import service
from app.services.sync.registry import FEEDS

router = APIRouter(tags=["source sync"])

Admin = Annotated[Principal, Depends(require(Permission.USER_MANAGE))]
# Data managers and administrators see the feeds' state, releases and log.
Manager = Annotated[Principal, Depends(require_any(Permission.IMPORT_READ, Permission.USER_MANAGE))]
MAX_UPLOAD_BYTES = 30_000_000


class FeedSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    check_interval_hours: int | None = Field(default=None, ge=6, le=720)
    auto_publish: bool | None = None


def _public(status: dict[str, Any]) -> dict[str, Any]:
    """What anyone may see: no error text, no file digests."""
    return {k: v for k, v in status.items() if k not in ("last_error", "auto_publish")}


@router.get("/source-feeds")
def public_feeds(session: DbSession) -> list[dict[str, Any]]:
    return [_public(s) for s in service.statuses(session)]


@router.get("/admin/source-feeds")
def admin_feeds(session: DbSession, _: Manager) -> list[dict[str, Any]]:
    return service.statuses(session)


def _feed(session: DbSession, code: str) -> SourceFeed:
    feed = session.scalar(select(SourceFeed).where(SourceFeed.code == code))
    if feed is None:
        raise not_found("source feed")
    return feed


@router.patch("/admin/source-feeds/{code}")
def update_feed(
    code: str, body: FeedSettings, session: DbSession, principal: Admin
) -> dict[str, Any]:
    with session.begin():
        feed = _feed(session, code)
        changes = body.model_dump(exclude_none=True)
        if changes.get("enabled") and feed.access != "public_listing":
            raise unprocessable(
                "feed_not_accessible",
                "This feed needs access OSRIP does not have; it cannot be switched on.",
            )
        for key, value in changes.items():
            setattr(feed, key, value)
        if changes.get("enabled") or "check_interval_hours" in changes:
            # A new or changed schedule starts with a check soon, then every interval.
            feed.next_check_at = datetime.now(UTC) + timedelta(minutes=1)
        feed.updated_by, feed.updated_at = principal.user_id, datetime.now(UTC)
        audit.record(
            session,
            principal,
            "source_feed.update",
            entity_type="source_feed",
            entity_id=feed.id,
            metadata=changes,
        )
        return service.feed_status(session, feed)


@router.post("/admin/source-feeds/{code}/check")
def check_now(code: str, session: DbSession, principal: Admin) -> dict[str, Any]:
    """A manual check, run now (whether or not the schedule is switched on)."""
    with session.begin():
        feed = _feed(session, code)
        audit.record(
            session, principal, "source_feed.check", entity_type="source_feed", entity_id=feed.id
        )
    return service.run_check(session, code, trigger="manual", requested_by=principal.user_id)


@router.post("/admin/source-feeds/{code}/upload")
async def upload_workbook(
    code: str,
    session: DbSession,
    principal: Admin,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=3, max_length=200)],
    file_url: Annotated[str, Form(pattern=r"^https://api\.ncsi\.gov\.om/uploads/", max_length=500)],
    published_on: Annotated[date | None, Form()] = None,
) -> dict[str, Any]:
    """An official workbook downloaded by hand; processed like a downloaded one."""
    if code not in FEEDS or FEEDS[code].parser is None:
        raise not_found("source feed")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise unprocessable("file_too_large", "The workbook is larger than 30 MB.")
    with session.begin():
        feed = _feed(session, code)
        audit.record(
            session,
            principal,
            "source_feed.upload",
            entity_type="source_feed",
            entity_id=feed.id,
            metadata={"title": title, "file_url": file_url},
        )
    return service.run_upload(
        session,
        code,
        data,
        title_en=title,
        file_url=file_url,
        published_on=published_on,
        requested_by=principal.user_id,
    )


@router.get("/admin/source-feeds/{code}/runs")
def feed_runs(code: str, session: DbSession, _: Manager, limit: int = 20) -> list[dict[str, Any]]:
    with session.begin():
        feed = _feed(session, code)
        ids = list(
            session.scalars(
                select(SourceSyncRun.id)
                .where(SourceSyncRun.feed_id == feed.id)
                .order_by(SourceSyncRun.started_at.desc())
                .limit(max(1, min(limit, 100)))
            )
        )
    return [service.run_out(session, i) for i in ids]


@router.get("/admin/source-feeds/{code}/releases")
def feed_releases(code: str, session: DbSession, _: Manager) -> list[dict[str, Any]]:
    with session.begin():
        feed = _feed(session, code)
        rows = session.scalars(
            select(SourceRelease)
            .where(SourceRelease.feed_id == feed.id)
            .order_by(
                SourceRelease.published_at.desc().nulls_last(), SourceRelease.detected_at.desc()
            )
            .limit(50)
        )
        return [service.release_out(r) for r in rows]
