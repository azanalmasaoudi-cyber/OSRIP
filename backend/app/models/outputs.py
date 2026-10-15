"""Derived outputs (booklet 3.11, 3.13): analysis runs, recommendations with
append-only review history, and reports with frozen inputs. The schema is in
place; the endpoints that create these rows arrive with the rule engine and
report generation (see docs/VERIFICATION.md)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import DataMode, Section
from app.models.types import (
    ANALYSIS_KIND,
    ANALYSIS_STATUS,
    DATA_MODE,
    REPORT_VISIBILITY,
    REVIEW_STATUS,
    SECTION,
)

UUID_PK = {"primary_key": True, "server_default": text("gen_random_uuid()")}


class AnalysisRun(Base):
    __tablename__ = "analysis_run"
    __table_args__ = (UniqueConstraint("id", "data_mode", name="uq_analysis_run_id_mode"),)

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    kind: Mapped[str] = mapped_column(ANALYSIS_KIND)
    method_code: Mapped[str] = mapped_column(Text)
    method_version: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(ANALYSIS_STATUS)
    status_reason: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisRunInput(Base):
    __tablename__ = "analysis_run_input"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "data_mode"], ["analysis_run.id", "analysis_run.data_mode"]
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "data_mode"], ["dataset_version.id", "dataset_version.data_mode"]
        ),
    )

    analysis_run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)


class Recommendation(Base):
    __tablename__ = "recommendation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "data_mode"], ["analysis_run.id", "analysis_run.data_mode"]
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    analysis_run_id: Mapped[uuid.UUID]
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    rule_code: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    message_en: Mapped[str] = mapped_column(Text)
    message_ar: Mapped[str] = mapped_column(Text)
    follow_up_en: Mapped[str] = mapped_column(Text)
    follow_up_ar: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationReview(Base):
    """Append-only (database trigger). Current status = latest review."""

    __tablename__ = "recommendation_review"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recommendation.id"))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    status: Mapped[str] = mapped_column(REVIEW_STATUS)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastPrediction(Base):
    """One held-out prediction of a forecast run. Append-only (database trigger)."""

    __tablename__ = "forecast_prediction"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "data_mode"], ["analysis_run.id", "analysis_run.data_mode"]
        ),
    )

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID]
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    model: Mapped[str] = mapped_column(Text)
    fold: Mapped[int]
    horizon_steps: Mapped[int]
    training_start: Mapped[date]
    training_end: Mapped[date]
    training_size: Mapped[int]
    target_period_start: Mapped[date]
    target_period_end: Mapped[date]
    predicted: Mapped[Decimal] = mapped_column(Numeric)
    actual: Mapped[Decimal] = mapped_column(Numeric)
    error: Mapped[Decimal] = mapped_column(Numeric)
    interval_lower: Mapped[Decimal | None] = mapped_column(Numeric)
    interval_upper: Mapped[Decimal | None] = mapped_column(Numeric)


class Report(Base):
    __tablename__ = "report"
    __table_args__ = (UniqueConstraint("id", "data_mode", name="uq_report_id_mode"),)

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    title: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    visibility: Mapped[str] = mapped_column(REPORT_VISIBILITY, server_default=text("'private'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    section: Mapped[Section | None] = mapped_column(SECTION)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    # Frozen at generation (trigger trg_report_frozen): observations, calculations, cards.
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), deferred=True)


class ReportInput(Base):
    __tablename__ = "report_input"
    __table_args__ = (
        ForeignKeyConstraint(["report_id", "data_mode"], ["report.id", "report.data_mode"]),
        ForeignKeyConstraint(
            ["dataset_version_id", "data_mode"], ["dataset_version.id", "dataset_version.data_mode"]
        ),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)


class ForecastOutput(Base):
    """A model estimate beyond the last observation. Append-only (database trigger)."""

    __tablename__ = "forecast_output"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "data_mode"], ["analysis_run.id", "analysis_run.data_mode"]
        ),
    )

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID]
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    model: Mapped[str] = mapped_column(Text)
    step: Mapped[int]
    period_start: Mapped[date]
    period_end: Mapped[date]
    estimate: Mapped[Decimal] = mapped_column(Numeric)
    lower80: Mapped[Decimal | None] = mapped_column(Numeric)
    upper80: Mapped[Decimal | None] = mapped_column(Numeric)
    lower95: Mapped[Decimal | None] = mapped_column(Numeric)
    upper95: Mapped[Decimal | None] = mapped_column(Numeric)
    interval_method: Mapped[str] = mapped_column(Text)
