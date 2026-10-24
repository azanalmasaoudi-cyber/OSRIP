"""Chronological series of one indicator for tables, charts and downloads.

Reads the published observations (data mode, area and breakdown chosen by the caller),
keeps one unit, and builds the rows with ``app.domain.timeline``: the table, the chart and
the CSV download are all drawn from the same rows, identified by one digest.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.domain import timeline as tl
from app.domain.enums import DataMode, Section
from app.models import Indicator
from app.services.imports.csv_file import safe_cell
from app.services.observations import ObservationQuery, SeriesOut, query_observations

KINDS = ("annual", "quarterly", "monthly", "year_to_date")


def _source(s: SeriesOut) -> dict[str, Any]:
    src = s.meta["source"]
    return {
        k: src.get(k)
        for k in (
            "id",
            "dataset_title",
            "publisher",
            "url",
            "source_code",
            "access_date",
            "reference_period",
        )
    }


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


def _published(
    series: list[SeriesOut],
) -> tuple[str, dict[str, int], dict[str, Any], list[tl.Published]]:
    """One unit per table (the one most observations use; others are named, not mixed in)
    and the published observations in that unit."""
    counts: dict[str, int] = {}
    for s in series:
        counts[s.meta["unit"]["code"]] = counts.get(s.meta["unit"]["code"], 0) + len(s.observations)
    unit_code = max(counts, key=lambda c: (counts[c], c))
    kept = [s for s in series if s.meta["unit"]["code"] == unit_code]
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
        )
        for s in kept
        for o in s.observations
    ]
    return unit_code, counts, kept[0].meta["unit"], published


def _named(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if meta is None:
        return None
    return {"code": meta["code"], "name": {"en": meta["name_en"], "ar": meta["name_ar"]}}


def _has_periods(entry: dict[str, Any]) -> bool:
    return any(entry["views"][v] for v in tl.VIEWS) or bool(entry["year_to_date"])


def availability(session: Session, data_mode: DataMode, section: Section) -> dict[str, Any]:
    """What can be asked of each indicator of a section before anything is shown: for every
    area and breakdown with published data, the periods of each view that have a value
    (published, or derived from complete components by the indicator's value type, exactly
    as the timeline builds them) and the year-to-date periods, which are kept apart. The
    period selectors offer only these periods; nothing here is a statistic to display."""
    series = [
        s
        for s in query_observations(
            session, ObservationQuery(data_mode, section=section), allow_mixed=True
        )
        if s.meta["period_kind"] in KINDS
    ]
    groups: dict[tuple[str, str, str | None, str | None, str | None], list[SeriesOut]] = {}
    for s in series:
        key = (s.meta["indicator"]["code"], s.meta["area"]["code"], *_breakdown(s))
        groups.setdefault(key, []).append(s)
    indicators: dict[str, dict[str, Any]] = {}
    for (code, _area, *_), members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        meta = members[0].meta
        ind = meta["indicator"]
        unit_code, _, unit_meta, published = _published(members)
        unit = tl.unit_of(unit_code, unit_meta["dimension"])
        views: dict[str, list[dict[str, str]]] = {}
        year_to_date: list[dict[str, str]] = []
        for view in tl.VIEWS:
            line = tl.build(published, ind["value_type"], view, unit, meta["area"]["code"])
            views[view] = [
                {"start": r.start.isoformat(), "end": r.end.isoformat()}
                for r in line.rows
                if r.value is not None
            ]
            year_to_date = [
                {"start": r.start.isoformat(), "end": r.end.isoformat()}
                for r in line.year_to_date
                if r.value is not None
            ]
        entry = indicators.setdefault(
            code,
            {
                "code": code,
                "name": {"en": ind["name_en"], "ar": ind["name_ar"]},
                "definition": {"en": ind["definition_en"], "ar": ind["definition_ar"]},
                "value_type": ind["value_type"],
                "series": [],
            },
        )
        entry["series"].append(
            {
                "area": {
                    "code": meta["area"]["code"],
                    "level": meta["area"]["level"],
                    "name": {"en": meta["area"]["name_en"], "ar": meta["area"]["name_ar"]},
                },
                "commodity": _named(meta["commodity"]),
                "partner": _named(meta["partner"]),
                "flow": meta["flow"],
                "unit": {
                    "code": unit_code,
                    "label": {"en": unit_meta["label_en"], "ar": unit_meta["label_ar"]},
                },
                "views": views,
                "year_to_date": year_to_date,
            }
        )
    return {
        "section": section.value,
        "data_mode": data_mode.value,
        "indicators": [i for i in indicators.values() if any(map(_has_periods, i["series"]))],
        "label": "SYNTHETIC DEMONSTRATION DATA - not Omani statistics"
        if data_mode is DataMode.SYNTHETIC
        else None,
    }


def _forecast(
    session: Session, data_mode: DataMode, indicator: str, area: str, view: str, unit: str
) -> tuple[list[tl.Row], dict[str, Any] | None]:
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
            )
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
            ObservationQuery(
                data_mode,
                indicator=indicator,
                area=area,
                flow=flow,
                partner=partner or "total",
                commodity=commodity,
            ),
            allow_mixed=True,
        )
        if s.meta["period_kind"] in KINDS and (commodity or s.meta["commodity"] is None)
    ]
    head = {
        "indicator": {
            "code": ind.code,
            "section": ind.section.value,
            "value_type": ind.value_type.value,
            "name": {"en": ind.name_en, "ar": ind.name_ar},
            "definition": {"en": ind.definition_en, "ar": ind.definition_ar},
            "limitation": {"en": ind.limitation_en, "ar": ind.limitation_ar},
        },
        "sector": ind.section.value,
        "area": area,
        "view": view,
        "data_mode": data_mode.value,
    }
    if not series:
        return {
            **head,
            "status": "no_published_data",
            "rows": [],
            "year_to_date": [],
            "available_views": [],
            "rules": [],
            "sources": [],
        }
    breakdowns = sorted({_breakdown(s) for s in series}, key=str)
    if len(breakdowns) > 1:
        return {
            **head,
            "status": "needs_selection",
            "options": [{"commodity": c, "partner": p, "flow": f} for c, p, f in breakdowns],
            "rows": [],
            "year_to_date": [],
            "available_views": [],
            "rules": [],
            "sources": [],
        }
    unit_code, counts, unit_meta, published = _published(series)
    unit = tl.unit_of(unit_code, unit_meta["dimension"])
    line = tl.build(
        published,
        ind.value_type.value,
        view,
        unit,
        area,
        period_from=period_from,
        period_to=period_to,
    )
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
        },
        "other_units": sorted(c for c in counts if c != unit_code),
        "breakdown": dict(zip(("commodity", "partner", "flow"), breakdowns[0], strict=True)),
        "available_views": line.available_views,
        "rows": [r.out() for r in rows],
        "year_to_date": [r.out() for r in line.year_to_date],
        "forecast": forecast,
        "rules": [{"code": c, **tl.RULES[c]} for c in line.rules],
        "sources": list(sources.values()),
        "summary": tl.summarize(line.rows, ind.value_type.value, unit, area),
        "dataset_id": line.digest(),
        "label": "SYNTHETIC DEMONSTRATION DATA - not Omani statistics"
        if data_mode is DataMode.SYNTHETIC
        else None,
    }


CSV_COLUMNS = [
    "sector",
    "indicator",
    "area",
    "period_start",
    "period_end",
    "frequency",
    "value",
    "value_operator",
    "unit",
    "nature",
    "status",
    "basis",
    "revision_status",
    "previous_period_change",
    "previous_period_change_pct",
    "year_on_year_change",
    "year_on_year_change_pct",
    "source_title",
    "publisher",
    "source_url",
    "source_code",
    "dataset_version",
    "record_ref",
    "other_publications",
    "reason",
]


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
        writer.writerow(
            [
                doc["sector"],
                doc["indicator"]["code"],
                doc["area"],
                r["period_start"],
                r["period_end"],
                "year_to_date" if r in doc.get("year_to_date", []) else r["frequency"],
                r["value"] or "",
                r["value_operator"] or "",
                unit,
                r["nature"],
                r["status"],
                r["basis"] or "",
                r["revision_status"] or "",
                (prev or {}).get("absolute") or "",
                (prev or {}).get("percent") or "",
                (yoy or {}).get("absolute") or "",
                (yoy or {}).get("percent") or "",
                safe_cell(src.get("dataset_title") or ""),
                safe_cell(src.get("publisher") or ""),
                safe_cell(src.get("url") or ""),
                src.get("source_code") or "",
                safe_cell(version.get("label") or ""),
                safe_cell(r.get("record_ref") or ""),
                safe_cell(
                    "; ".join(
                        f"{o['value']} ({(o.get('source') or {}).get('source_code') or ''})"
                        for o in r.get("other_publications") or []
                    )
                ),
                safe_cell((r.get("reason") or {}).get(language, "")),
            ]
        )
    return buffer.getvalue()


# ------------------------------------------------------------------ spoken summary

MONTHS_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
MONTHS_AR = (
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)
QUARTERS_AR = ("الأول", "الثاني", "الثالث", "الرابع")
VIEW_WORDS = {
    "en": {"annual": "annual", "quarterly": "quarterly", "monthly": "monthly"},
    "ar": {"annual": "السنوية", "quarterly": "الربعية", "monthly": "الشهرية"},
}


def _spoken_period(start: str, view: str, language: str) -> str:
    d = date.fromisoformat(start)
    if view == "monthly":
        return f"{(MONTHS_AR if language == 'ar' else MONTHS_EN)[d.month - 1]} {d.year}"
    if view == "quarterly":
        q = (d.month - 1) // 3 + 1
        return (
            f"الربع {QUARTERS_AR[q - 1]} من {d.year}"
            if language == "ar"
            else f"quarter {q} of {d.year}"
        )
    return str(d.year)


def _spoken_number(value: str) -> str:
    """A figure as it is said: one decimal (two below 10), thousands grouped. The table keeps
    the exact published value; this is only the spoken rounding."""
    number = Decimal(value)
    places = Decimal("0.1") if abs(number) >= 10 else Decimal("0.01")
    rounded = number.quantize(places, rounding=ROUND_HALF_UP).normalize()
    if rounded == rounded.to_integral():
        return f"{rounded.quantize(Decimal(1)):,}"
    return f"{rounded:,f}"


def spoken_summary(doc: dict[str, Any], language: str, area_name: str) -> str:
    """A short spoken explanation of a selected range, built only from the timeline's own
    summary (the same figures as the table): the latest value, the change over the range, how
    many periods are missing and, for a flow with every period published, the total. It never
    reads the table row by row. Numbers and units are later put into spoken form by
    app.services.speech.speakable."""
    ar = language == "ar"
    name = doc["indicator"]["name"][language]
    if doc.get("status") != "ok" or not doc.get("summary") or not doc["summary"]["with_value"]:
        return (
            f"لا توجد قيم منشورة لمؤشر {name} في {area_name} للفترة المختارة."
            if ar
            else f"No published values of {name} for {area_name} in the selected period."
        )
    s = doc["summary"]
    view = doc["view"]
    unit = doc["unit"]["label"][language]
    first, last = s["first"], s["last"]
    first_p = _spoken_period(first["period_start"], view, language)
    last_p = _spoken_period(last["period_start"], view, language)
    parts: list[str] = []
    if ar:
        parts.append(
            f"{name} في {area_name}، القيم {VIEW_WORDS['ar'][view]} من {first_p} إلى {last_p}."
        )
        parts.append(f"أحدث قيمة {_spoken_number(last['value'])} {unit} في {last_p}.")
    else:
        parts.append(
            f"{name} for {area_name}, {VIEW_WORDS['en'][view]} figures from {first_p} to {last_p}."
        )
        parts.append(f"The latest value is {_spoken_number(last['value'])} {unit}, for {last_p}.")
    change = s.get("change")
    if change and change.get("absolute") is not None:
        absolute = Decimal(change["absolute"])
        amount = _spoken_number(str(abs(absolute)))
        pct = (
            f"{abs(Decimal(change['percent'])):.1f}" if change.get("percent") is not None else None
        )
        if absolute == 0:
            parts.append(f"لم تتغير منذ {first_p}." if ar else f"It is unchanged from {first_p}.")
        elif ar:
            direction = "ارتفعت" if absolute > 0 else "انخفضت"
            parts.append(
                f"{direction} بمقدار {amount} {unit}"
                + (f"، أي {pct}%" if pct else "")
                + f"، مقارنة بـ {first_p}."
            )
        else:
            direction = "up" if absolute > 0 else "down"
            parts.append(
                f"That is {direction} {amount} {unit}"
                + (f", or {pct}%," if pct else "")
                + f" from {first_p}."
            )
    if s["missing"]:
        parts.append(
            f"{s['missing']} من {s['periods']} فترات غير منشورة."
            if ar
            else f"{s['missing']} of the {s['periods']} periods are not published."
        )
    if s.get("total") is not None:
        parts.append(
            f"المجموع خلال الفترة {_spoken_number(s['total'])} {unit}."
            if ar
            else f"The total over the period is {_spoken_number(s['total'])} {unit}."
        )
    if last.get("nature") in ("provisional", "estimate"):
        parts.append(
            "أحدث رقم أولي وقد يُعدَّل."
            if ar
            else "The latest figure is provisional and may be revised."
        )
    publisher = next(
        (src.get("publisher") for src in doc.get("sources", []) if src.get("publisher")), None
    )
    if publisher:
        parts.append(f"المصدر: {publisher}." if ar else f"Source: {publisher}.")
    return " ".join(parts)
