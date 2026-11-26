"""The official outlook (forecasts, targets, plans), apart from observations: public reading of
approved items; review of pending ones by people allowed to approve imports (audited)."""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import DbSession, require
from app.domain.enums import Permission, Section
from app.services import outlook
from app.services.principal import Principal

router = APIRouter(prefix="/outlook", tags=["outlook"])


@router.get("")
def outlook_items(session: DbSession, section: Section | None = None) -> dict[str, Any]:
    """Public: approved outlook items, each with its evidence class and source."""
    with session.begin():
        return outlook.list_items(session, section)


@router.get("/review")
def outlook_for_review(
    session: DbSession,
    _actor: Annotated[Principal, Depends(require(Permission.IMPORT_APPROVE))],
    section: Section | None = None,
) -> dict[str, Any]:
    """Every item, pending ones included, for the people who approve imports."""
    with session.begin():
        return outlook.list_items(session, section, approved_only=False)


class OutlookItemIn(BaseModel):
    section: Literal["electricity", "water"]
    metric_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9_]+$")
    metric_en: str = Field(min_length=1, max_length=200)
    metric_ar: str = Field(min_length=1, max_length=200)
    year: int = Field(ge=2000, le=2100)
    value: str | None = Field(default=None, max_length=32, pattern=r"^-?\d+(\.\d+)?$")
    unit: Literal["MW", "percent", "m3_per_day", "thousand_m3_per_day", "event"]
    scope_en: str = Field(min_length=1, max_length=200)
    scope_ar: str = Field(min_length=1, max_length=200)
    evidence_class: Literal[
        "observed", "estimate", "forecast", "policy_target", "planned", "under_consideration"
    ]
    status_note_en: str | None = Field(default=None, max_length=500)
    status_note_ar: str | None = Field(default=None, max_length=500)
    source_title: str = Field(min_length=1, max_length=300)
    source_publisher: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=9, max_length=500, pattern=r"^https://")
    source_locator: str = Field(min_length=1, max_length=200)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    retrieved_on: date
    issue_year: int = Field(ge=2000, le=2100)


class BatchIn(BaseModel):
    batch_label: str = Field(min_length=1, max_length=120)
    items: list[OutlookItemIn] = Field(min_length=1, max_length=200)


@router.post("/batches", status_code=201)
def outlook_stage(
    body: BatchIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_CREATE))],
) -> dict[str, Any]:
    """Stage outlook items as pending review (idempotent; audited). Nothing is shown until a
    person allowed to approve imports approves each item."""
    with session.begin():
        return outlook.stage(session, actor, [i.model_dump() for i in body.items], body.batch_label)


class ReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=500)


@router.post("/{item_id}/review")
def outlook_review(
    item_id: uuid.UUID,
    body: ReviewIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_APPROVE))],
) -> dict[str, Any]:
    """Approve or reject one pending item (recorded in the audit log)."""
    with session.begin():
        return outlook.review(session, actor, item_id, body.decision, body.note)
