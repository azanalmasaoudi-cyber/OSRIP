"""Official statistics feeds, the releases found in them and the log of each check
(migration 0022). Checks run in the separate sync worker (``python -m app.worker``)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

NOW = {"server_default": func.now()}


class SourceFeed(Base):
    """An official publication series OSRIP follows, how it is reached and its schedule."""

    __tablename__ = "source_feed"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(Text, unique=True)
    publisher: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str] = mapped_column(Text)
    title_ar: Mapped[str] = mapped_column(Text)
    access: Mapped[str] = mapped_column(Text)  # public_listing | requires_access
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    check_interval_hours: Mapped[int] = mapped_column(server_default=text("24"))
    auto_publish: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(server_default=text("0"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class SourceRelease(Base):
    """A publication found in a feed, with the publisher's own dates and what became of it."""

    __tablename__ = "source_release"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_feed.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str] = mapped_column(Text)
    title_ar: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_url: Mapped[str | None] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(Text)
    file_bytes: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(Text)
    rows_read: Mapped[int] = mapped_column(server_default=text("0"))
    rows_new: Mapped[int] = mapped_column(server_default=text("0"))
    rows_revised: Mapped[int] = mapped_column(server_default=text("0"))
    rows_unchanged: Mapped[int] = mapped_column(server_default=text("0"))
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL")
    )
    message: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceSyncRun(Base):
    """One check of a feed, successful or not."""

    __tablename__ = "source_sync_run"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_feed.id", ondelete="CASCADE"))
    trigger: Mapped[str] = mapped_column(Text)  # schedule | manual | upload
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(server_default=text("1"))
    http_status: Mapped[int | None] = mapped_column()
    releases_seen: Mapped[int] = mapped_column(server_default=text("0"))
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_release.id", ondelete="SET NULL")
    )
    message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
