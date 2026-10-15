"""Calculations, review cards and analyst review history (booklet 3.13, Table 3.5)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, DbSession, require
from app.core.errors import ApiError
from app.domain.calculations import StockAssumption
from app.domain.enums import DataMode, Frequency, Permission, Section
from app.services.analysis import runs
from app.services.analysis.rules import RuleParameters
from app.services.analysis.sections import AnalysisFilter, analyse
from app.services.exports import CALC_HEADER, calculation_rows, mode_label, write_csv
from app.services.principal import Principal

router = APIRouter(tags=["analysis"])


def analysis_filter(
    data_mode: DataMode,
    commodity: Annotated[str | None, Query(max_length=64)] = None,
    area: Annotated[str | None, Query(max_length=64)] = None,
    frequency: Frequency | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    stock_assumption: StockAssumption = StockAssumption.ASSUMED_ZERO,
    dataset_version_id: uuid.UUID | None = None,
    period_kind: Annotated[
        str | None, Query(pattern="^(annual|year_to_date|quarterly|monthly|statement)$")
    ] = None,
) -> AnalysisFilter:
    return AnalysisFilter(
        data_mode,
        commodity,
        area,
        frequency,
        period_from,
        period_to,
        stock_assumption,
        dataset_version_id,
        period_kind,
    )


F = Annotated[AnalysisFilter, Depends(analysis_filter)]


def _payload(section: Section, f: AnalysisFilter, calcs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "section": section.value,
        "data_mode": f.data_mode.value,
        "label": mode_label(f.data_mode),
        "filters": {
            k: str(v)
            for k, v in (
                ("commodity", f.commodity),
                ("area", f.area),
                ("frequency", f.frequency),
                ("period_kind", f.period_kind),
                ("period_from", f.period_from),
                ("period_to", f.period_to),
                ("dataset_version_id", f.dataset_version_id),
            )
            if v
        },
        "assumptions": {"stock_assumption": f.stock_assumption.value},
        "calculations": calcs,
    }


@router.get("/analysis/{section}")
def section_analysis(section: Section, f: F, session: DbSession) -> dict[str, Any]:
    """Public: transparent calculations over the published snapshot of one data mode."""
    with session.begin():
        return _payload(section, f, analyse(session, section, f))


@router.get("/analysis/{section}/export.csv")
def section_analysis_export(section: Section, f: F, session: DbSession) -> Response:
    with session.begin():
        calcs = analyse(session, section, f)
    payload = _payload(section, f, calcs)
    text = write_csv(
        [
            f"OSRIP calculations - {payload['label']}",
            f"data_mode={f.data_mode.value}",
            f"section={section.value}",
            "filters=" + ("; ".join(f"{k}={v}" for k, v in payload["filters"].items()) or "none"),
            f"assumptions=stock_assumption={f.stock_assumption.value}",
            "Missing values stay missing; unavailable results carry their reason. "
            "Values are unrounded.",
        ],
        [(CALC_HEADER, calculation_rows(f.data_mode.value, calcs))],
    )
    filename = f"osrip-calculations-{section.value}-{f.data_mode.value}.csv"
    return Response(
        text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ------------------------------------------------------------------ review cards


class RunIn(BaseModel):
    data_mode: DataMode
    growth_threshold_pct: Decimal = Field(default=Decimal("3"), ge=0, le=1000)
    share_threshold_pct: Decimal = Field(default=Decimal("50"), ge=0, le=100)
    unit_value_gap_pct: Decimal = Field(default=Decimal("10"), ge=0, le=1000)


@router.post("/analysis-runs", status_code=201)
def run_rules(
    body: RunIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.ANALYSIS_RUN))],
) -> dict[str, Any]:
    params = RuleParameters(
        body.growth_threshold_pct, body.share_threshold_pct, body.unit_value_gap_pct
    )
    runs.run_rules(session, actor, body.data_mode, params)
    with session.begin():
        return runs.latest_cards(session, body.data_mode)


@router.get("/recommendations")
def recommendations(
    session: DbSession, data_mode: DataMode, section: Section | None = None
) -> dict[str, Any]:
    """Public: review cards of the latest rule run for the data mode, with their current status."""
    with session.begin():
        return runs.latest_cards(session, data_mode, section)


class ReviewIn(BaseModel):
    status: Literal["under_review", "explained", "dismissed"]
    reason: str = Field(min_length=1, max_length=2000)


def _can_read_reviews(principal: Principal) -> bool:
    return principal.has(Permission.RECOMMENDATION_REVIEW) or principal.has(Permission.ANALYSIS_RUN)


@router.get("/recommendations/{recommendation_id}/reviews")
def reviews(
    recommendation_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> list[dict[str, Any]]:
    """Review notes are protected (booklet 3.15): analysts and reviewers only."""
    if not principal.is_authenticated:
        raise ApiError(401, "authentication_required", "Sign in to continue.")
    if not _can_read_reviews(principal):
        raise ApiError(
            403, "permission_denied", "Your account does not have permission for this action."
        )
    with session.begin():
        return runs.review_history(session, recommendation_id)


@router.post("/recommendations/{recommendation_id}/reviews", status_code=201)
def add_review(
    recommendation_id: uuid.UUID,
    body: ReviewIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.RECOMMENDATION_REVIEW))],
) -> list[dict[str, Any]]:
    runs.add_review(session, actor, recommendation_id, body.status, body.reason)
    with session.begin():
        return runs.review_history(session, recommendation_id)
