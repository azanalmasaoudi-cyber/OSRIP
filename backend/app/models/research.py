"""Statistics found by the assistant's web research, queued for review (migration 0011,
never part of the published dataset); saved research, watchlists and alerts (0012); stored
study runs (0015)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Identity, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import DataMode
from app.models.types import DATA_MODE

NOW = {"server_default": func.now()}


class SavedResearch(Base):
    """A user's saved snapshot of an assistant reply (for the library and briefs)."""

    __tablename__ = "saved_research"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_message.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class WatchlistItem(Base):
    __tablename__ = "watchlist_item"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    indicator_code: Mapped[str] = mapped_column(ForeignKey("indicator.code"))
    area_code: Mapped[str] = mapped_column(ForeignKey("area.code"))
    period_kind: Mapped[str] = mapped_column(Text)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class AlertRule(Base):
    __tablename__ = "alert_rule"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    watchlist_item_id: Mapped[int] = mapped_column(
        ForeignKey("watchlist_item.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)  # new_data | above | below
    threshold: Mapped[Decimal | None] = mapped_column(Numeric)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    channel: Mapped[str] = mapped_column(Text, server_default=text("'in_app'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertEvent(Base):
    __tablename__ = "alert_event"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rule.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_version.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(Text)
    indicator_code: Mapped[str] = mapped_column(Text)
    area_code: Mapped[str] = mapped_column(Text)
    value: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(Text)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric)
    message_en: Mapped[str] = mapped_column(Text)
    message_ar: Mapped[str] = mapped_column(Text)
    delivery: Mapped[str] = mapped_column(Text, server_default=text("'in_app'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchCandidate(Base):
    __tablename__ = "research_candidate"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    domain: Mapped[str] = mapped_column(Text)
    indicator: Mapped[str] = mapped_column(Text)
    indicator_code: Mapped[str | None] = mapped_column(ForeignKey("indicator.code"))
    value: Mapped[Decimal] = mapped_column(Numeric)
    value_text: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text)
    geography: Mapped[str] = mapped_column(Text)
    period_label: Mapped[str] = mapped_column(Text)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    publication_date: Mapped[date | None] = mapped_column(Date)
    publisher: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_class: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    search_provider: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_message.id", ondelete="SET NULL")
    )
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    checks: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudyRun(Base):
    """One study: validated parameters and the shared result (migration 0015)."""

    __tablename__ = "study_run"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    data_mode: Mapped[str] = mapped_column(Text)
    dataset_versions: Mapped[list[str]] = mapped_column(ARRAY(Text))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_sha256: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("guest_session.id", ondelete="CASCADE")
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_message.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class ReportSchedule(Base):
    """A scheduled report an administrator configured (migration 0021); off by default, and a
    schedule that calls paid services must be allowed explicitly."""

    __tablename__ = "report_schedule"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text)
    sector: Mapped[str] = mapped_column(Text)
    area: Mapped[str] = mapped_column(Text, server_default=text("'OM'"))
    data_mode: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, server_default=text("'en'"))
    frequency: Mapped[str] = mapped_column(Text)  # weekly | monthly | quarterly
    source_scope: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    max_pages: Mapped[int] = mapped_column(server_default=text("5"))
    max_credits_per_run: Mapped[int] = mapped_column(server_default=text("25"))
    max_credits_per_month: Mapped[int] = mapped_column(server_default=text("100"))
    allow_paid: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class ResearchJob(Base):
    """A study run in the background (migration 0021): its steps, progress, attempts,
    cancellation, cache key and result."""

    __tablename__ = "research_job"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_schedule.id", ondelete="SET NULL")
    )
    sector: Mapped[str] = mapped_column(Text)
    area: Mapped[str] = mapped_column(Text)
    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)
    question: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    data_mode: Mapped[str] = mapped_column(Text)
    source_scope: Mapped[str] = mapped_column(Text)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    state: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    stage: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(server_default=text("3"))
    cache_key: Mapped[str] = mapped_column(Text)
    cached_from: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_job.id", ondelete="SET NULL")
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("study_run.id", ondelete="SET NULL")
    )
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    credits_used: Mapped[int] = mapped_column(server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchDocument(Base):
    """A document a study retrieved, with its provenance (migration 0021). Its text is
    untrusted evidence, kept as a bounded excerpt and never added to the dataset."""

    __tablename__ = "research_document"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_job.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    host: Mapped[str] = mapped_column(Text)
    source_class: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    published: Mapped[date | None] = mapped_column(Date)
    reporting_period: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    retriever: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(server_default=text("0"))
    pages: Mapped[int | None]
    credits: Mapped[int] = mapped_column(server_default=text("0"))
    sha256: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_document.id", ondelete="SET NULL")
    )
    revision_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_document.id", ondelete="SET NULL")
    )
