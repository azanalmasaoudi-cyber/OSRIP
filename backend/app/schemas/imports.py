import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from app.domain.enums import DataMode, DatasetVersionStatus, LocatorKind


class SourceIn(BaseModel):
    """Provenance registered before import (booklet 3.2)."""

    data_mode: DataMode
    dataset_title: str = Field(min_length=3, max_length=500)
    publisher: str | None = Field(default=None, max_length=300)
    url: HttpUrl | None = None
    locator_kind: LocatorKind | None = None
    access_date: date | None = None
    publication_date: date | None = None
    reference_period: str | None = Field(default=None, max_length=200)
    geographic_coverage: str = Field(min_length=1, max_length=300)
    definition_note: str | None = Field(default=None, max_length=4000)
    reuse_conditions: str | None = Field(default=None, max_length=2000)


class VersionOut(BaseModel):
    id: uuid.UUID
    label: str
    status: DatasetVersionStatus
    checksum_sha256: str
    created_at: datetime
    approved_at: datetime | None
    published_at: datetime | None
    superseded_at: datetime | None


class SourceOut(BaseModel):
    id: uuid.UUID
    data_mode: DataMode
    dataset_title: str
    publisher: str | None
    url: str | None
    locator_kind: str | None
    access_date: date | None
    publication_date: date | None
    reference_period: str | None
    geographic_coverage: str
    definition_note: str | None
    reuse_conditions: str | None
    versions: list[VersionOut]
    # A registered source identifies where values came from; it does not by itself
    # verify any particular number.
    verification_note: str


class MappingIn(BaseModel):
    mapping: dict[str, str]


class ApproveIn(BaseModel):
    acknowledged_rejected_rows: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=2000)


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ImportOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    data_mode: DataMode
    version: VersionOut
    original_filename: str
    file_size: int
    header: list[str]
    column_mapping: dict[str, str] | None
    required_fields: list[str]
    optional_fields: list[str]
    row_count: int | None
    valid_row_count: int | None
    warning_row_count: int | None
    rejected_row_count: int | None
    created_at: datetime
    validated_at: datetime | None
    approval_note: str | None
    acknowledged_rejected_rows: int | None
    rejection_reason: str | None
    last_error_code: str | None


class ImportRowOut(BaseModel):
    row_number: int
    outcome: Literal["valid", "warning", "rejected"]
    raw: dict[str, str]
    issues: list[dict[str, Any]]


class ImportRowsOut(BaseModel):
    total: int
    rows: list[ImportRowOut]


class PublishOut(BaseModel):
    import_: ImportOut = Field(alias="import")
    already_published: bool
    observations_inserted: int
    superseded_version_id: uuid.UUID | None

    model_config = {"populate_by_name": True}
