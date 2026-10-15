import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import DataMode
from app.models.types import DATA_MODE


class ImportJob(Base):
    """Private upload for one dataset version. The version's status is the lifecycle."""

    __tablename__ = "import_job"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_version_id", "data_mode"],
            ["dataset_version.id", "dataset_version.data_mode"],
            name="fk_import_job_version_mode",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    original_filename: Mapped[str] = mapped_column(Text)
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    file_size: Mapped[int] = mapped_column(Integer)
    header: Mapped[list[str]] = mapped_column(ARRAY(Text))
    column_mapping: Mapped[dict[str, str] | None] = mapped_column(JSONB(none_as_null=True))
    row_count: Mapped[int | None]
    valid_row_count: Mapped[int | None]
    warning_row_count: Mapped[int | None]
    rejected_row_count: Mapped[int | None]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    validated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    approval_note: Mapped[str | None] = mapped_column(Text)
    acknowledged_rejected_rows: Mapped[int | None]
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(Base):
    __tablename__ = "import_row"

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_job.id", ondelete="CASCADE"), primary_key=True
    )
    row_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw: Mapped[dict[str, str]] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(Text)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'"))
    # none_as_null: Python None must be SQL NULL (ck_import_row_normalized), not JSON 'null'.
    normalized: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
