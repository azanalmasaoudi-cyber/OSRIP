"""Tables and charts in the conversation, built by the backend from published observations.

The model never writes a table's figures or a chart's code: it names the series (indicator,
area, kind of period, years) and this module reads the approved, published observations,
keeps a missing value missing, sorts by period, and returns one validated table per unit
(``app.domain.study.Table``: a unit on every numeric column, decimal strings or None). A chart
is a validated specification over the very same rows (``app.domain.study.Chart``), drawn by
the page's own chart components; it is built only when the person asked for one, and only
from compatible rows: one unit, one kind of period, at least two values. A line chart shows
a time trend of one or more series; a bar chart compares areas (or indicators) for one
period; grouped bars compare compatible series period by period. Monthly values are never
made from annual ones, and a year-to-date total is never put beside full years.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.domain.study import Chart, ChartSeries, Column, Table, Text, Unit, check_table_and_charts

MAX_ROWS = 60
KINDS = ("monthly", "quarterly", "annual", "year_to_date")
KIND_TEXT = {
    "monthly": ("monthly", "شهري"),
    "quarterly": ("quarterly", "ربع سنوي"),
    "annual": ("full year", "سنة كاملة"),
    "year_to_date": ("year to date (partial year)", "منذ بداية السنة (سنة غير مكتملة)"),
}
COLUMNS_LONG = (
    ("period", "Period", "الفترة", "period"),
    ("indicator", "Indicator", "المؤشر", "text"),
    ("value", "Value", "القيمة", "number"),
    ("unit", "Unit", "الوحدة", "text"),
    ("geography", "Geography", "النطاق الجغرافي", "text"),
    ("source", "Source", "المصدر", "text"),
)


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def period_text(start: str, end: str, kind: str | None) -> str:
    """The period as studies label it: 2024, 2024-08, 2024 Q3, 2026 Jan–Aug."""
    if kind == "annual":
        return start[:4]
    if kind == "monthly":
        return start[:7]
    if kind == "quarterly":
        return f"{start[:4]} Q{(int(start[5:7]) - 1) // 3 + 1}"
    if kind == "year_to_date":
        return f"{start[:4]} Jan–{MONTHS[int(end[5:7]) - 1]}"
    return f"{start}–{end}"


def row_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """A table row (with its evidence id and labels) from a ledger observation item."""
    kind = item.get("period_kind") or item.get("frequency")
    return {
        "evidence_id": item["id"],
        "indicator_code": item["indicator"],
        "indicator_name": item["indicator_name"],
        "area": item["area"],
        "area_name": item["area_name"],
        "period_kind": kind,
        "period_start": item["period_start"],
        "period_end": item["period_end"],
        "period_complete": item.get("period_complete"),
        "value": item.get("value"),
        "value_operator": item.get("value_operator"),
        "unit": item["unit"],
        "unit_label": item["unit_label"],
        "revision_status": item.get("revision_status"),
        "source": {
            "title": item["source"]["title"],
            "publisher": item["source"].get("publisher"),
            "url": item["source"].get("url"),
            "dataset_version": item.get("dataset_version"),
        },
    }


def _unit(row: dict[str, Any]) -> Unit:
    label = row["unit_label"] or {}
    return Unit(
        code=row["unit"],
        label_en=label.get("en") or row["unit"],
        label_ar=label.get("ar") or row["unit"],
    )


def build_tables(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One validated long-format table per unit: Period | Indicator | Value | Unit | Geography |
    Source, in period order. Rows keep their evidence ids for citations and CSV."""
    ordered = sorted(
        rows[:MAX_ROWS],
        key=lambda r: (r["period_start"], r["period_end"], r["indicator_code"], r["area"]),
    )
    by_unit: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for r in ordered:
        by_unit.setdefault(r["unit"], []).append(r)
    out = []
    for unit_code, group in by_unit.items():
        unit = _unit(group[0])
        columns = [
            Column(
                key=k, label=Text(en=en, ar=ar), kind=kind, unit=unit if kind == "number" else None
            )  # type: ignore[arg-type]
            for k, en, ar, kind in COLUMNS_LONG
        ]
        table_rows = [
            {
                "period": period_text(r["period_start"], r["period_end"], r["period_kind"]),
                "indicator": r["indicator_code"],
                "value": None if r["value"] is None else str(r["value"]),
                "unit": unit_code,
                "geography": r["area"],
                "source": r["source"]["title"],
            }
            for r in group
        ]
        table = Table(columns=columns, rows=table_rows)
        check_table_and_charts(table, [])
        out.append(
            {
                "unit": unit.model_dump(),
                "table": table.model_dump(mode="json"),
                "rows": group,
                "kinds": sorted({str(r["period_kind"]) for r in group}),
            }
        )
    return out


def build_chart(rows: list[dict[str, Any]], title: dict[str, str]) -> dict[str, Any]:
    """A chart specification over these rows, or the reason none can be drawn."""
    values = [r for r in rows if r["value"] is not None and not r.get("value_operator")]
    units = {r["unit"] for r in values}
    kinds = {r["period_kind"] for r in values}
    if len(units) > 1:
        return {"status": "not_comparable", "reason": "different_units", "units": sorted(units)}
    if len(kinds) > 1:
        return {
            "status": "not_comparable",
            "reason": "different_kinds_of_period",
            "kinds": sorted(map(str, kinds)),
        }
    if len(values) < 2:
        return {
            "status": "insufficient_points",
            "reason": "fewer_than_two_values",
            "points": len(values),
        }
    series_keys = list(OrderedDict.fromkeys((r["indicator_code"], r["area"]) for r in values))
    periods = list(
        OrderedDict.fromkeys(
            (r["period_start"], r["period_end"])
            for r in sorted(values, key=lambda r: r["period_start"])
        )
    )
    unit = _unit(values[0])
    if len(periods) == 1 and len(series_keys) > 1:
        # One period, several areas or indicators: a bar per category.
        columns = [
            Column(key="category", label=Text(en="Category", ar="الفئة"), kind="text"),
            Column(key="value", label=Text(en="Value", ar="القيمة"), kind="number", unit=unit),
        ]
        wide_rows = [
            {"category": f"{r['indicator_code']} · {r['area']}", "value": str(r["value"])}
            for r in values
        ]
        chart = Chart(
            type="bar", title=Text(**title), x="category", unit=unit,
            series=[ChartSeries(column="value", label=Text(en="Value", ar="القيمة"), nature="observed")],
        )  # fmt: skip
        kind = "bar"
    else:
        columns = [Column(key="period", label=Text(en="Period", ar="الفترة"), kind="period")]
        series = []
        for i, (ind, area) in enumerate(series_keys):
            first = next(r for r in values if (r["indicator_code"], r["area"]) == (ind, area))
            key = f"s{i}"
            name = first["indicator_name"] or {}
            area_name = first["area_name"] or {}
            label = Text(
                en=f"{name.get('en', ind)} · {area_name.get('en', area)}",
                ar=f"{name.get('ar', ind)} · {area_name.get('ar', area)}",
            )
            columns.append(Column(key=key, label=label, kind="number", unit=unit))
            series.append(ChartSeries(column=key, label=label, nature="observed"))
        wide_rows = []
        for start, end in periods:
            row: dict[str, str | None] = {"period": period_text(start, end, next(iter(kinds)))}
            for i, (ind, area) in enumerate(series_keys):
                match = [
                    r for r in values
                    if (r["indicator_code"], r["area"], r["period_start"], r["period_end"]) == (ind, area, start, end)
                ]  # fmt: skip
                # Two publications for the same period are not merged: the first in source order.
                row[f"s{i}"] = str(match[0]["value"]) if match else None
            wide_rows.append(row)
        kind = "line" if len(periods) >= 3 or len(series_keys) == 1 else "bar"
        chart = Chart(type=kind, title=Text(**title), x="period", unit=unit, series=series)  # type: ignore[arg-type]
    table = Table(columns=columns, rows=wide_rows)
    check_table_and_charts(table, [chart])
    return {
        "status": "ok",
        "chart": chart.model_dump(mode="json"),
        "table": table.model_dump(mode="json"),
        "type": kind,
        "points": len(values),
        "evidence_ids": [r["evidence_id"] for r in values],
        "sources": sorted({r["source"]["title"] for r in values}),
        "period_kind": next(iter(kinds)),
    }
