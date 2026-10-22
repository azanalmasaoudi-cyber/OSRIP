"""Shortage and surplus analysis (supply against demand) per sector, from published data only.

Like studies, running an analysis needs no account (it reads only published data); a
signed-in user's runs are kept with their account. The stored document is the single source
for the screen, the CSV export and the printable report.
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DbSession, optional_session
from app.core import ratelimit
from app.domain.enums import DataMode
from app.services.analysis import balance, balance_export
from app.services.principal import Principal

router = APIRouter(prefix="/analysis/balance", tags=["analysis"])


class BalanceIn(BaseModel):
    data_mode: DataMode
    params: dict[str, Any] = Field(default_factory=dict)


def _limit(request: Request, key: str, per_hour: int) -> None:
    client = request.client.host if request.client else "unknown"
    ratelimit.check(f"{key}:{client}", per_hour, 3600)


@router.post("", status_code=201)
def run(
    body: BalanceIn,
    request: Request,
    session: DbSession,
    principal: Annotated[Principal, Depends(optional_session)],
) -> dict[str, Any]:
    """Run and store an analysis for one sector (parameters: sector, area, period_kind, and an
    optional scenario: supply_growth_pct, demand_growth_pct, years)."""
    _limit(request, "balance", 240)
    with session.begin():
        user = principal.user_id if principal and principal.is_authenticated else None
        return balance.run(session, body.params, body.data_mode, user)


@router.post("/preview")
def preview(body: BalanceIn, request: Request, session: DbSession) -> dict[str, Any]:
    """The same validated analysis, computed but not stored."""
    _limit(request, "balance-preview", 600)
    with session.begin():
        return {"analysis": balance.build(session, body.params, body.data_mode)}


@router.get("/{analysis_id}")
def get(analysis_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    with session.begin():
        return balance.out(balance.get(session, analysis_id))


@router.get("/{analysis_id}/spoken")
def spoken(
    analysis_id: uuid.UUID, session: DbSession, language: Literal["en", "ar"] = "en"
) -> dict[str, str]:
    """The exact words the voice reads for this analysis (the transcript shown beside the
    player): its summary and each balance's status, not every table cell."""
    with session.begin():
        row = balance.get(session, analysis_id)
        return {"language": language, "text": balance_export.spoken_summary(row.result, language)}


@router.get("/{analysis_id}/reproduce")
def reproduce(analysis_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    with session.begin():
        return balance.reproduce(session, analysis_id)


def _download(row: Any, analysis_id: uuid.UUID, language: str, extension: str) -> dict[str, str]:
    sector = row.params.get("sector", "sector")
    name = f"osrip-shortage-surplus-{sector}-{language}-{str(analysis_id)[:8]}.{extension}"
    return {
        "Content-Disposition": f'attachment; filename="{name}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


# The report is a static document: nothing in it may run or load from elsewhere.
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


@router.get("/{analysis_id}/export.csv")
def export_csv(
    analysis_id: uuid.UUID, session: DbSession, language: Literal["en", "ar"] = "en"
) -> Response:
    with session.begin():
        row = balance.get(session, analysis_id)
        text = balance_export.export_csv(row.result, language)
    return Response(
        "﻿" + text,  # BOM so spreadsheet programs read Arabic correctly
        media_type="text/csv; charset=utf-8",
        headers=_download(row, analysis_id, language, "csv"),
    )


@router.get("/{analysis_id}/report.html")
def report(
    analysis_id: uuid.UUID, session: DbSession, language: Literal["en", "ar"] = "en"
) -> Response:
    """A readable, printable report of the stored analysis (no scripts; values escaped)."""
    with session.begin():
        row = balance.get(session, analysis_id)
        html = balance_export.export_html(row.result, language)
    return Response(
        html,
        media_type="text/html; charset=utf-8",
        headers={
            **_download(row, analysis_id, language, "html"),
            "Content-Security-Policy": REPORT_CSP,
        },
    )
