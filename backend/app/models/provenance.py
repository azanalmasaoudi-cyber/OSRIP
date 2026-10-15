import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    CHAR,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import DataMode, DatasetVersionStatus
from app.models.types import DATA_MODE, DATASET_VERSION_STATUS

UUID_PK = {"primary_key": True, "server_default": text("gen_random_uuid()")}


class Source(Base):
    __tablename__ = "source"
    __table_args__ = (UniqueConstraint("id", "data_mode", name="uq_source_id_mode"),)

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    publisher: Mapped[str | None] = mapped_column(Text)
    dataset_title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    access_date: Mapped[date | None]
    publication_date: Mapped[date | None]
    reference_period: Mapped[str | None] = mapped_column(Text)
    geographic_coverage: Mapped[str] = mapped_column(Text)
    definition_note: Mapped[str | None] = mapped_column(Text)
    reuse_conditions: Mapped[str | None] = mapped_column(Text)
    locator_kind: Mapped[str | None] = mapped_column(Text)
    source_code: Mapped[str | None] = mapped_column(Text)  # S01 ... within a reference pack
    source_role: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetVersion(Base):
    __tablename__ = "dataset_version"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "data_mode"],
            ["source.id", "source.data_mode"],
            name="fk_dataset_version_source_mode",
        ),
        UniqueConstraint("source_id", "version_label", name="uq_dataset_version_label"),
        UniqueConstraint("id", "data_mode", name="uq_dataset_version_id_mode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    source_id: Mapped[uuid.UUID]
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    version_label: Mapped[str] = mapped_column(Text)
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[DatasetVersionStatus] = mapped_column(
        DATASET_VERSION_STATUS, server_default=text("'draft'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferencePack(Base):
    """A curated evidence pack (for example the September 2026 Oman reference pack)."""

    __tablename__ = "reference_pack"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    research_cutoff: Mapped[date]
    record_count: Mapped[int]
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64))
    document: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReferencePackSource(Base):
    """Every reference in a pack, including crosschecks that supply no imported value."""

    __tablename__ = "reference_pack_source"

    pack_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reference_pack.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    publisher: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    publication: Mapped[str] = mapped_column(Text)
    accessed_on: Mapped[date]
    role: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    locations: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source.id"))


class DataQualityNote(Base):
    """A documented conflict, revision or limitation (Q01 ...); shown, never resolved silently."""

    __tablename__ = "data_quality_note"

    pack_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reference_pack.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    title_en: Mapped[str] = mapped_column(Text)
    title_ar: Mapped[str] = mapped_column(Text)
    body_en: Mapped[str] = mapped_column(Text)
    body_ar: Mapped[str] = mapped_column(Text)
    source_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    sections: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
