"""Public reads of published data (booklet Table 3.5: GET /observations)."""

import csv
import io
import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbSession
from app.domain.enums import DataMode, Frequency, Section
from app.models import Commodity
from app.services.imports.csv_file import safe_cell
from app.services.observations import ObservationQuery, query_observations

router = APIRouter(tags=["observations"])

SYNTHETIC_LABEL = "SYNTHETIC DEMONSTRATION DATA - declared test inputs; not Omani statistics"


def observation_query(
    data_mode: DataMode,
    section: Section | None = None,
    indicator: Annotated[str | None, Query(max_length=64)] = None,
    area: Annotated[str | None, Query(max_length=64)] = None,
    commodity: Annotated[str | None, Query(max_length=64)] = None,
    partner: Annotated[
        str | None, Query(max_length=64, description="Partner code, or 'total'")
    ] = None,
    flow: Annotated[str | None, Query(max_length=32)] = None,
    frequency: Frequency | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    dataset_version_id: uuid.UUID | None = None,
    period_kind: Annotated[
        str | None,
        Query(
            pattern="^(annual|year_to_date|quarterly|monthly|statement)$",
            description="Complete years, year-to-date totals, quarters, months or dated statements",
        ),
    ] = None,
) -> ObservationQuery:
    return ObservationQuery(
        data_mode,
        section,
        indicator,
        area,
        commodity,
        partner,
        flow,
        frequency,
        period_from,
        period_to,
        dataset_version_id,
        period_kind,
    )


Q = Annotated[ObservationQuery, Depends(observation_query)]


@router.get("/observations")
def observations(q: Q, session: DbSession) -> dict[str, Any]:
    """Observations with unit, period, geography, data mode and source version.

    ``data_mode`` is required. Without ``dataset_version_id`` each source
    contributes its one published snapshot.
    """
    with session.begin():
        series = query_observations(session, q)
    if not series:
        return {"status": "no_published_data", "data_mode": q.data_mode.value, "series": []}
    return {
        "status": "ok",
        "data_mode": q.data_mode.value,
        "label": SYNTHETIC_LABEL if q.data_mode is DataMode.SYNTHETIC else None,
        "series": [{**s.meta, "observations": s.observations} for s in series],
    }


@router.get("/observations/export.csv")
def export(q: Q, session: DbSession) -> StreamingResponse:
    """CSV export with provenance, and the mode in the metadata lines and the file name.

    Missing values stay empty cells.
    """
    with session.begin():
        series = query_observations(session, q)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    heading = (
        SYNTHETIC_LABEL
        if q.data_mode is DataMode.SYNTHETIC
        else "Verified-source data (published snapshots)"
    )
    writer.writerow([f"# OSRIP export - {heading}"])
    writer.writerow([f"# data_mode={q.data_mode.value}"])
    writer.writerow(["# Missing values are empty cells, never zero. Values are unrounded."])
    writer.writerow(
        [
            "data_mode",
            "indicator",
            "area",
            "period_start",
            "period_end",
            "period_complete",
            "frequency",
            "period_kind",
            "value",
            "unit",
            "value_operator",
            "original_value",
            "original_unit",
            "commodity",
            "partner",
            "flow",
            "quality_status",
            "dataset_title",
            "publisher",
            "source_url",
            "dataset_version",
            "source_row",
            "record_ref",
            "source_code",
            "source_locator",
            "revision_status",
            "statement_date",
        ]
    )
    for s in series:
        m = s.meta
        for o in s.observations:
            writer.writerow(
                [
                    m["data_mode"],
                    m["indicator"]["code"],
                    m["area"]["code"],
                    o["period_start"],
                    o["period_end"],
                    o["period_complete"],
                    m["frequency"],
                    m["period_kind"],
                    "" if o["value"] is None else o["value"],
                    m["unit"]["code"],
                    o["value_operator"] or "",
                    o["original_value"] or "",
                    o["original_unit"] or "",
                    m["commodity"]["code"] if m["commodity"] else "",
                    m["partner"]["code"] if m["partner"] else "",
                    m["flow"] or "",
                    o["quality_status"],
                    safe_cell(m["source"]["dataset_title"]),
                    safe_cell(m["source"]["publisher"] or ""),
                    safe_cell(m["source"]["url"] or ""),
                    safe_cell(m["dataset_version"]["label"]),
                    safe_cell(o["source_row"]),
                    o["record_ref"] or "",
                    m["source"]["source_code"] or "",
                    safe_cell(o["source_locator"] or ""),
                    o["revision_status"] or "",
                    o["statement_date"] or "",
                ]
            )
    filename = f"osrip-observations-{q.data_mode.value}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/commodities")
def commodities(data_mode: DataMode, session: DbSession) -> list[dict[str, Any]]:
    """The shared registry. Synthetic-only commodities appear in synthetic mode only."""
    with session.begin():
        stmt = select(Commodity).order_by(Commodity.synthetic_only, Commodity.code)
        if data_mode is DataMode.VERIFIED_SOURCE:
            stmt = stmt.where(Commodity.synthetic_only.is_(False))
        return [
            {
                "code": c.code,
                "name_en": c.name_en,
                "name_ar": c.name_ar,
                "product_form": c.product_form,
                "mapping_status": c.mapping_status,
                "synthetic_only": c.synthetic_only,
            }
            for c in session.scalars(stmt)
        ]
