"""Chronological series of one indicator: the rows a table and a chart are both drawn from,
and the same rows as a CSV download."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DbSession
from app.domain.enums import DataMode, Section
from app.services import annual_table, timeline

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


@router.get("/availability")
def series_availability(
    session: DbSession, data_mode: DataMode, section: Section
) -> dict[str, Any]:
    """For each indicator of the section, the areas and breakdowns with published data and
    the periods of each view (monthly, quarterly, annual) that have a value, plus the
    year-to-date periods. Selectors offer only these; nothing here is shown as a result."""
    with session.begin():
        return timeline.availability(session, data_mode, section)


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


@router.get("/annual-table")
def series_annual_table(
    session: DbSession,
    data_mode: DataMode,
    section: Section,
    year_from: Annotated[int, Query(ge=1900, le=2100)] = 2022,
    year_to: Annotated[int, Query(ge=1900, le=2100)] = 2025,
) -> dict[str, Any]:
    """Public: the section's annual indicators side by side for full years (electricity and
    water): each a separate published series, with its unit, provisional marks and the
    platform's year-on-year change. Missing years stay empty."""
    with session.begin():
        return annual_table.table(session, section, data_mode, year_from, year_to)


@router.get("/annual-table.csv")
def series_annual_table_csv(
    session: DbSession,
    data_mode: DataMode,
    section: Section,
    year_from: Annotated[int, Query(ge=1900, le=2100)] = 2022,
    year_to: Annotated[int, Query(ge=1900, le=2100)] = 2025,
    language: Annotated[str, Query(pattern="^(en|ar)$")] = "en",
) -> Response:
    """The same cells as the annual table, with provenance, as CSV."""
    with session.begin():
        doc = annual_table.table(session, section, data_mode, year_from, year_to)
    name = f"osrip-{section.value}-annual-{year_from}-{year_to}-{data_mode.value}.csv"
    return Response(
        "\ufeff" + annual_table.to_csv(doc, language),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
