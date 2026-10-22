"""Chronological series of one indicator: the rows a table and a chart are both drawn from,
and the same rows as a CSV download."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DbSession
from app.domain.enums import DataMode
from app.services import timeline

router = APIRouter(prefix="/series", tags=["series"])

View = Annotated[str, Query(pattern="^(annual|quarterly|monthly)$")]
Code = Annotated[str | None, Query(max_length=64)]


def _build(
    session: DbSession,
    data_mode: DataMode,
    indicator: str,
    area: str,
    view: str,
    commodity: str | None,
    partner: str | None,
    flow: str | None,
    period_from: date | None,
    period_to: date | None,
    include_forecast: bool,
) -> dict[str, Any]:
    with session.begin():
        return timeline.build(
            session, data_mode, indicator, area=area, view=view, commodity=commodity,
            partner=partner, flow=flow, period_from=period_from, period_to=period_to,
            include_forecast=include_forecast,
        )  # fmt: skip


@router.get("/timeline")
def series_timeline(
    session: DbSession,
    data_mode: DataMode,
    indicator: Annotated[str, Query(max_length=64)],
    area: Annotated[str, Query(max_length=64)] = "OM",
    view: View = "annual",
    commodity: Code = None,
    partner: Code = None,
    flow: Code = None,
    period_from: date | None = None,
    period_to: date | None = None,
    include_forecast: bool = False,
) -> dict[str, Any]:
    """Rows in time order for the view (monthly, quarterly or annual): published values,
    periods derived from complete published components by the indicator's value type, and
    missing periods left empty; year-to-date totals apart; changes from the previous period
    and the same period a year earlier; every row with its source."""
    return _build(session, data_mode, indicator, area, view, commodity, partner, flow,
                  period_from, period_to, include_forecast)  # fmt: skip


@router.get("/timeline.csv")
def series_timeline_csv(
    session: DbSession,
    data_mode: DataMode,
    indicator: Annotated[str, Query(max_length=64)],
    area: Annotated[str, Query(max_length=64)] = "OM",
    view: View = "annual",
    commodity: Code = None,
    partner: Code = None,
    flow: Code = None,
    period_from: date | None = None,
    period_to: date | None = None,
    language: Annotated[str, Query(pattern="^(en|ar)$")] = "en",
) -> Response:
    """The same rows as the table and the chart, with provenance, as CSV."""
    doc = _build(session, data_mode, indicator, area, view, commodity, partner, flow,
                 period_from, period_to, False)  # fmt: skip
    name = f"osrip-{indicator.lower()}-{area.lower()}-{view}-{data_mode.value}.csv"
    return Response(
        "﻿" + timeline.to_csv(doc, language),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
