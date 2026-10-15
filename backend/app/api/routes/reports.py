"""Reports with frozen inputs (booklet 3.12; Table 3.5: POST /reports, GET /reports/{id})."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, DbSession, require
from app.domain.calculations import StockAssumption
from app.domain.enums import DataMode, Permission, Section
from app.models import Report
from app.services import reports
from app.services.principal import Principal

router = APIRouter(tags=["reports"])


class ReportIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    data_mode: DataMode
    section: Section
    filters: dict[str, str | None] = {}
    stock_assumption: StockAssumption = StockAssumption.ASSUMED_ZERO
    visibility: Literal["private", "published"] = "private"


class VisibilityIn(BaseModel):
    visibility: Literal["private", "published"]


def _summary(r: Report, principal: Principal) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "title": r.title,
        "data_mode": r.data_mode.value,
        "section": r.section.value if r.section else None,
        "visibility": r.visibility,
        "filters": r.filters,
        "assumptions": r.assumptions,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        "owned": r.owner_id == principal.user_id,
    }


@router.post("/reports", status_code=201)
def create(
    body: ReportIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.REPORT_CREATE))],
) -> dict[str, Any]:
    report = reports.create_report(
        session,
        actor,
        title=body.title,
        data_mode=body.data_mode,
        section=body.section,
        filters=body.filters,
        stock_assumption=body.stock_assumption,
        visibility=body.visibility,
    )
    return _summary(report, actor)


@router.get("/reports")
def list_reports(session: DbSession, principal: CurrentPrincipal) -> list[dict[str, Any]]:
    """Published reports for everyone, plus the signed-in user's own private reports."""
    with session.begin():
        return [_summary(r, principal) for r in reports.list_reports(session, principal)]


@router.get("/reports/{report_id}")
def get(report_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal) -> dict[str, Any]:
    with session.begin():
        report = reports.get_report(session, principal, report_id)
        return {**_summary(report, principal), "content": report.content}


@router.get("/reports/{report_id}/export.csv")
def export(report_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal) -> Response:
    with session.begin():
        report = reports.get_report(session, principal, report_id)
        text = reports.report_csv(report)
    filename = f"osrip-report-{report.id}-{report.data_mode.value}.csv"
    return Response(
        text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/reports/{report_id}/visibility")
def visibility(
    report_id: uuid.UUID,
    body: VisibilityIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.REPORT_CREATE))],
) -> dict[str, Any]:
    report = reports.set_visibility(session, actor, report_id, body.visibility)
    return _summary(report, actor)
