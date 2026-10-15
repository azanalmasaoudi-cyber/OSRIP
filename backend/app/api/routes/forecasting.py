"""Forecast eligibility and recorded forecast experiments (booklet 2.4, 4.6, FR07, T10)."""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import DbSession, require
from app.domain.enums import DataMode, Permission
from app.services import conditions, forecasting, scenarios
from app.services.principal import Principal

router = APIRouter(tags=["forecasting"])


@router.get("/forecast/eligibility")
def eligibility(data_mode: DataMode, session: DbSession) -> dict[str, Any]:
    """Public: which published series could support the experiment, and why not."""
    with session.begin():
        return forecasting.eligibility(session, data_mode)


class ForecastRunIn(BaseModel):
    data_mode: DataMode
    series_id: str = Field(min_length=1, max_length=512)


@router.post("/forecast-runs", status_code=201)
def run(
    body: ForecastRunIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.ANALYSIS_RUN))],
) -> dict[str, Any]:
    """Record an experiment. An ineligible series is recorded as withheld, with its reasons."""
    run_id = forecasting.run_experiment(session, actor, body.data_mode, body.series_id)
    with session.begin():
        return forecasting.run_detail(session, run_id)


@router.get("/forecast-runs")
def runs(data_mode: DataMode, session: DbSession) -> list[dict[str, Any]]:
    with session.begin():
        return forecasting.list_runs(session, data_mode)


@router.get("/forecast-runs/{run_id}")
def run_detail(run_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    with session.begin():
        return forecasting.run_detail(session, run_id)


@router.get("/forecast/overview")
def forecast_overview(data_mode: DataMode, session: DbSession) -> dict[str, Any]:
    """Public: each target indicator with its series, eligibility and latest forecast run."""
    with session.begin():
        return forecasting.overview(session, data_mode)


@router.get("/forecast/conditions")
def forecast_conditions(data_mode: DataMode, session: DbSession) -> dict[str, Any]:
    """Public: candidate development conditions per domain, each marked measured (a published
    compatible series exists) or a scenario assumption, with the evidence still needed."""
    with session.begin():
        return conditions.conditions(session, data_mode)


@router.get("/scenarios/series")
def scenario_series(data_mode: DataMode, session: DbSession) -> list[dict[str, Any]]:
    """Public: series with a complete published value that a scenario can start from."""
    with session.begin():
        return scenarios.series(session, data_mode)


@router.get("/scenarios/projection")
def scenario_projection(
    data_mode: DataMode,
    series_id: Annotated[str, Query(min_length=1, max_length=512)],
    session: DbSession,
    growth_pct: Annotated[Decimal, Query(ge=-50, le=50)] = Decimal(0),
    years: Annotated[int, Query(ge=1, le=10)] = 5,
    one_off_pct: Annotated[Decimal, Query(ge=-100, le=200)] = Decimal(0),
) -> dict[str, Any]:
    """Public: a hypothetical scenario (not a forecast) from the latest published value."""
    with session.begin():
        return scenarios.projection(session, data_mode, series_id, growth_pct, years, one_off_pct)
