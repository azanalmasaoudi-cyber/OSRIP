"""Datasets people upload to analyse, and research and dataset reports (migration 0024).

An uploaded dataset is private to its owner and never part of the published statistics."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

UUID_PK = {"primary_key": True, "server_default": text("gen_random_uuid()")}
NOW = {"server_default": func.now()}


class AnalysisDataset(Base):
    __tablename__ = "analysis_dataset"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(Text)  # csv | xlsx | json
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(Text)
    sheet: Mapped[str | None] = mapped_column(Text)
    columns: Mapped[list[str]] = mapped_column(JSONB)
    # The values as the file holds them (text or None); loaded only when asked for.
    rows: Mapped[list[list[str | None]]] = mapped_column(JSONB, deferred=True)
    row_count: Mapped[int] = mapped_column(Integer)
    notes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONB, deferred=True)
    # AI summaries of the analysis by language ({"en": {...}, "ar": {...}}).
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class AnalysisReport(Base):
    """Frozen at creation (trigger trg_analysis_report_frozen)."""

    __tablename__ = "analysis_report"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)  # research | dataset
    title: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_dataset.id", ondelete="SET NULL")
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_message.id", ondelete="SET NULL")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
