"""Chronological series of one indicator for tables, charts and downloads.

Reads the published observations (data mode, area and breakdown chosen by the caller),
keeps one unit, and builds the rows with ``app.domain.timeline``: the table, the chart and
the CSV download are all drawn from the same rows, identified by one digest.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.domain import timeline as tl
from app.domain.enums import DataMode
from app.models import Indicator
from app.services.imports.csv_file import safe_cell
from app.services.observations import ObservationQuery, SeriesOut, query_observations

KINDS = ("annual", "quarterly", "monthly", "year_to_date")


def _source(s: SeriesOut) -> dict[str, Any]:
    src = s.meta["source"]
    return {k: src.get(k) for k in (
        "id", "dataset_title", "publisher", "url", "source_code", "access_date", "reference_period",
    )}  # fmt: skip


def _version(s: SeriesOut) -> dict[str, Any]:
    v = s.meta["dataset_version"]
    return {k: v.get(k) for k in ("id", "label", "status", "published_at")}


def _breakdown(s: SeriesOut) -> tuple[str | None, str | None, str | None]:
    m = s.meta
    return (
        m["commodity"]["code"] if m["commodity"] else None,
        m["partner"]["code"] if m["partner"] else None,
        m["flow"],
    )


def _forecast(session: Session, data_mode: DataMode, indicator: str, area: str, view: str,
              unit: str) -> tuple[list[tl.Row], dict[str, Any] | None]:  # fmt: skip
    """The latest validated forecast of this series in this view, as forecast rows."""
    from app.models import AnalysisRun
    from app.services import forecasting

    runs = session.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.kind == "forecast",
            AnalysisRun.status == "succeeded",
            AnalysisRun.data_mode == data_mode,
        )
        .order_by(AnalysisRun.started_at.desc())
        .limit(200)
    )
    for run in runs:
        series = run.parameters.get("series") or {}
        if (
            (series.get("indicator") or {}).get("code") != indicator
            or (series.get("area") or {}).get("code") != area
            or series.get("frequency") != view
            or (series.get("unit") or {}).get("code") != unit
        ):
            continue
        detail = forecasting.run_detail(session, run.id)
        rows = [
            tl.Row(
                date.fromisoformat(o["period_start"]),
                date.fromisoformat(o["period_end"]),
                view,
                Decimal(o["estimate"]) if o.get("estimate") is not None else None,
                nature="forecast",
                status="model_estimate",
                interval={k: o.get(k) for k in ("lower80", "upper80", "lower95", "upper95")},
            )  # fmt: skip
            for o in detail["outputs"]
        ]
        if rows:
            return rows, {
                "run_id": str(run.id),
                "model": detail["selected_model"],
                "training_cutoff": detail["training_cutoff"],
                "label": detail["estimate_label"],
            }
    return [], None


def build(
    session: Session,
    data_mode: DataMode,
    indicator: str,
    *,
    area: str = "OM",
    view: str = "annual",
    commodity: str | None = None,
    partner: str | None = None,
    flow: str | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    include_forecast: bool = False,
) -> dict[str, Any]:
    ind = session.scalar(select(Indicator).where(Indicator.code == indicator))
    if ind is None:
        raise not_found("indicator")
    series = [
        s
        for s in query_observations(
            session,
            ObservationQuery(data_mode, indicator=indicator, area=area, flow=flow,
                             partner=partner or "total", commodity=commodity),
            allow_mixed=True,
        )
        if s.meta["period_kind"] in KINDS and (commodity or s.meta["commodity"] is None)
    ]  # fmt: skip
    head = {
        "indicator": {
            "code": ind.code, "section": ind.section.value, "value_type": ind.value_type.value,
            "name": {"en": ind.name_en, "ar": ind.name_ar},
            "definition": {"en": ind.definition_en, "ar": ind.definition_ar},
            "limitation": {"en": ind.limitation_en, "ar": ind.limitation_ar},
        },
        "sector": ind.section.value,
        "area": area,
        "view": view,
        "data_mode": data_mode.value,
    }  # fmt: skip
    if not series:
        return {**head, "status": "no_published_data", "rows": [], "year_to_date": [],
                "available_views": [], "rules": [], "sources": []}  # fmt: skip
    breakdowns = sorted({_breakdown(s) for s in series}, key=str)
    if len(breakdowns) > 1:
        return {
            **head,
            "status": "needs_selection",
            "options": [{"commodity": c, "partner": p, "flow": f} for c, p, f in breakdowns],
            "rows": [], "year_to_date": [], "available_views": [], "rules": [], "sources": [],
        }  # fmt: skip
    # One unit per table: the one most observations use; others are named, not mixed in.
    counts: dict[str, int] = {}
    for s in series:
        counts[s.meta["unit"]["code"]] = counts.get(s.meta["unit"]["code"], 0) + len(s.observations)
    unit_code = max(counts, key=lambda c: (counts[c], c))
    kept = [s for s in series if s.meta["unit"]["code"] == unit_code]
    unit_meta = kept[0].meta["unit"]
    published = [
        tl.Published(
            date.fromisoformat(o["period_start"]),
            date.fromisoformat(o["period_end"]),
            s.meta["period_kind"],
            Decimal(o["value"]) if o["value"] is not None else None,
            o.get("value_operator"),
            o.get("revision_status"),
            _source(s),
            _version(s),
            o.get("record_ref"),
            o.get("source_locator"),
        )  # fmt: skip
        for s in kept
        for o in s.observations
    ]
    line = tl.build(
        published, ind.value_type.value, view, tl.unit_of(unit_code, unit_meta["dimension"]),
        area, period_from=period_from, period_to=period_to,
    )  # fmt: skip
    forecast_rows, forecast = ([], None)
    if include_forecast and line.rows:
        forecast_rows, forecast = _forecast(session, data_mode, indicator, area, view, unit_code)
        last = max((r.end for r in line.rows if r.value is not None), default=None)
        forecast_rows = [r for r in forecast_rows if last is None or r.start > last]
        if forecast_rows:
            line.rules.append("forecast_apart")
    rows = line.rows + forecast_rows
    sources: dict[str, dict[str, Any]] = {}
    for r in rows + line.year_to_date:
        if r.source and r.source.get("id"):
            sources.setdefault(str(r.source["id"]), {**r.source, "dataset_version": r.version})
    return {
        **head,
        "status": "ok",
        "unit": {
            "code": unit_code,
            "label": {"en": unit_meta["label_en"], "ar": unit_meta["label_ar"]},
        },  # fmt: skip
        "other_units": sorted(c for c in counts if c != unit_code),
        "breakdown": dict(zip(("commodity", "partner", "flow"), breakdowns[0], strict=True)),
        "available_views": line.available_views,
        "rows": [r.out() for r in rows],
        "year_to_date": [r.out() for r in line.year_to_date],
        "forecast": forecast,
        "rules": [{"code": c, **tl.RULES[c]} for c in line.rules],
        "sources": list(sources.values()),
        "dataset_id": line.digest(),
        "label": "SYNTHETIC DEMONSTRATION DATA - not Omani statistics"
        if data_mode is DataMode.SYNTHETIC
        else None,
    }


CSV_COLUMNS = [
    "sector", "indicator", "area", "period_start", "period_end", "frequency", "value",
    "value_operator", "unit", "nature",
    "status", "basis", "revision_status", "previous_period_change", "previous_period_change_pct",
    "year_on_year_change", "year_on_year_change_pct", "source_title", "publisher", "source_url",
    "source_code", "dataset_version", "record_ref", "other_publications", "reason",
]  # fmt: skip


def to_csv(doc: dict[str, Any], language: str = "en") -> str:
    """The same rows as the table and chart, one line per period (year-to-date totals
    after them), with provenance. Text cells are neutralised against spreadsheet formulas;
    missing values are empty cells, never zero."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    name = doc["indicator"]["name"][language]
    writer.writerow([safe_cell(f"# OSRIP series - {name} - {doc['area']} - {doc['view']}")])
    writer.writerow([f"# data_mode={doc['data_mode']} dataset_id={doc.get('dataset_id', '')}"])
    if doc.get("label"):
        writer.writerow([f"# {doc['label']}"])
    for rule in doc.get("rules", []):
        writer.writerow([safe_cell(f"# {rule[language]}")])
    writer.writerow(CSV_COLUMNS)
    unit = (doc.get("unit") or {}).get("code", "")
    for r in doc.get("rows", []) + doc.get("year_to_date", []):
        prev = next(
            (c for c in r["changes"] if c["basis"] in ("month_on_month", "quarter_on_quarter")),
            None,
        )
        yoy = next((c for c in r["changes"] if c["basis"] == "year_on_year"), None)
        src = r.get("source") or {}
        version = r.get("dataset_version") or {}
        writer.writerow([
            doc["sector"], doc["indicator"]["code"], doc["area"],
            r["period_start"], r["period_end"],
            "year_to_date" if r in doc.get("year_to_date", []) else r["frequency"],
            r["value"] or "", r["value_operator"] or "", unit, r["nature"], r["status"],
            r["basis"] or "", r["revision_status"] or "",
            (prev or {}).get("absolute") or "", (prev or {}).get("percent") or "",
            (yoy or {}).get("absolute") or "", (yoy or {}).get("percent") or "",
            safe_cell(src.get("dataset_title") or ""), safe_cell(src.get("publisher") or ""),
            safe_cell(src.get("url") or ""), src.get("source_code") or "",
            safe_cell(version.get("label") or ""), safe_cell(r.get("record_ref") or ""),
            safe_cell("; ".join(
                f"{o['value']} ({(o.get('source') or {}).get('source_code') or ''})"
                for o in r.get("other_publications") or []
            )),
            safe_cell((r.get("reason") or {}).get(language, "")),
        ])  # fmt: skip
    return buffer.getvalue()
