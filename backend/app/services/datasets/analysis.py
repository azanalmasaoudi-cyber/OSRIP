"""Deterministic analysis of an uploaded dataset: what each column holds, statistics, trends,
unusual values, comparisons between groups, correlations, and the tables and charts that
show them.

Everything here is computed by code from the file's own values; no model is involved and
nothing is estimated or filled in. A missing or unreadable value is counted and left out of
every calculation, never treated as zero. Exact arithmetic (``Decimal``) is used for sums,
means, medians and changes; only the standard deviation, compound growth and correlation use
floating point, rounded when shown.

Column kinds:

* ``number``: at least 95% of the filled cells are numbers (``1,234.5``, ``-3``, ``12%``,
  Arabic-Indic digits). The other cells are reported as unreadable (with their rows).
* ``period``: every filled cell is a year (in a column named like a year), a quarter
  (``2024 Q3``), a month (``2024-07``, ``Jul 2024``) or a date (``2024-07-31``,
  ``31/07/2024``: day first unless a value can only be month first).
* ``text``: everything else; a text column with a few repeated values is a category.

Trends need one value per period: either the rows have distinct periods, or a category column
splits them into series that do. Otherwise no trend is computed and the reason is given:
values are never summed or averaged over repeated periods behind the reader's back. Charts
are chosen from what the data allows (a line over periods, bars or a pie of shares across
categories, a scatter of two measures, a histogram), with the other types that remain valid
for the same table listed as alternatives.
"""

from __future__ import annotations

import math
import re
from collections import Counter, OrderedDict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.domain.study import Chart, ChartSeries, Column, Table, Text, Unit, check_table_and_charts

ANALYSIS_VERSION = 1
NUMBER_SHARE = Decimal("0.95")
MAX_SERIES = 6  # series in one time chart
MAX_CATEGORIES_CHART = 12
MAX_PIE_SLICES = 8
MAX_GROUPS = 30  # a category column with more values is not compared
MAX_TRENDS = 20
MAX_ANOMALIES = 10
MAX_NUMERIC = 8  # numeric columns compared and correlated
MAX_SCATTER_POINTS = 1000
MIN_ANOMALY_VALUES = 8
MIN_CORRELATION_PAIRS = 5
MIN_JUMP_POINTS = 5

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
MISSING = {
    "na", "n/a", "n.a.", "nan", "null", "none", "-", "--", "—", "–", "..", "...", "?",
    "غير متوفر", "غير متاح", "لا يوجد",
}  # fmt: skip
_PLAIN = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d{1,3})?$")
_GROUPED = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_UNIT_IN_NAME = re.compile(r"[(\[]\s*([^()\[\]]{1,24}?)\s*[)\]]\s*$")
_YEAR_NAME = re.compile(r"(?i)\b(year|yr|fy)\b|سنة|السنة|عام|العام")
_YEAR = re.compile(r"^(1[89]\d\d|20\d\d)$")
_QUARTER = re.compile(r"(?i)^(?:(\d{4})\s*[-/ ]?\s*q([1-4])|q([1-4])\s*[-/ ]?\s*(\d{4}))$")
_YEAR_MONTH = re.compile(r"^(\d{4})[-/.](\d{1,2})$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?$")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january", "يناير"), ("feb", "february", "فبراير"), ("mar", "march", "مارس"),
            ("apr", "april", "أبريل", "ابريل"), ("may", "مايو"), ("jun", "june", "يونيو"),
            ("jul", "july", "يوليو"), ("aug", "august", "أغسطس", "اغسطس"),
            ("sep", "sept", "september", "سبتمبر"), ("oct", "october", "أكتوبر", "اكتوبر"),
            ("nov", "november", "نوفمبر"), ("dec", "december", "ديسمبر"),
        ],
        start=1,
    )
    for m in names
}  # fmt: skip
_MONTH_YEAR = re.compile(r"^([^\d\s]+)\.?\s*[-/ ]?\s*(\d{4})$|^(\d{4})\s*[-/ ]?\s*([^\d\s]+)\.?$")


# ------------------------------------------------------------------ values


def number(text: str) -> tuple[Decimal | None, bool]:
    """(value, written as a percentage) or (None, False) when the text is not a number."""
    t = text.translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", ",")
    t = t.replace(" ", "").replace(" ", "").replace(" ", "")
    percent = t.endswith("%")
    if percent:
        t = t[:-1]
    if _GROUPED.match(t):
        t = t.replace(",", "")
    if not _PLAIN.match(t):
        return None, False
    try:
        value = Decimal(t)
    except InvalidOperation:
        return None, False
    return (value if value.is_finite() else None), percent


def is_missing(text: str | None) -> bool:
    return text is None or text.strip().lower() in MISSING


def plain(value: Decimal) -> str:
    """A decimal as plain text without exponent or trailing zeros (table cells)."""
    return "0" if value == 0 else format(value.normalize(), "f")


def rounded(value: Decimal) -> Decimal:
    """A computed value to a sensible precision: 2 decimals from 100 up, 4 below."""
    places = 2 if abs(value) >= 100 else 4
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def computed(value: Decimal) -> str:
    return plain(rounded(value))


def grouped(text: str) -> str:
    """Thousands separators for display in sentences: 31732.5 -> 31,732.5."""
    sign = "-" if text.startswith("-") else ""
    whole, _, frac = text.lstrip("-").partition(".")
    whole = f"{int(whole):,}" if whole.isdigit() else whole
    return sign + whole + (f".{frac}" if frac else "")


def _pct(value: Decimal) -> str:
    return plain(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------ periods


def _period(text: str, year_column: bool, month_first: bool) -> tuple[str, str] | None:
    """(sortable key, kind) of a period cell, or None."""
    t = text.translate(_ARABIC_DIGITS).strip()
    if year_column and _YEAR.match(t.removesuffix(".0")):
        return t[:4], "year"
    m = _QUARTER.match(t)
    if m:
        year, quarter = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        return f"{year}-Q{quarter}", "quarter"
    m = _YEAR_MONTH.match(t)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{int(m.group(2)):02d}", "month"
    m = _MONTH_YEAR.match(t)
    if m:
        name, year = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        month = _MONTHS.get(name.lower().rstrip("."))
        if month:
            return f"{year}-{month:02d}", "month"
    m = _ISO_DATE.match(t)
    if m and _valid_date(int(m.group(1)), int(m.group(2)), int(m.group(3))):
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", "date"
    m = _DAY_MONTH_YEAR.match(t)
    if m:
        first, second, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        day, month = (second, first) if month_first else (first, second)
        if _valid_date(year, month, day):
            return f"{year}-{month:02d}-{day:02d}", "date"
    return None


def _valid_date(year: int, month: int, day: int) -> bool:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    days = [
        31,
        29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    return day <= days[month - 1]


def _month_first(values: list[str]) -> bool:
    """dd/mm/yyyy unless some value can only be mm/dd/yyyy (its second part above 12)."""
    firsts, seconds = [], []
    for v in values:
        m = _DAY_MONTH_YEAR.match(v.translate(_ARABIC_DIGITS).strip())
        if m:
            firsts.append(int(m.group(1)))
            seconds.append(int(m.group(2)))
    return bool(seconds) and max(seconds) > 12 and max(firsts) <= 12


def period_label(key: str) -> str:
    return key.replace("-Q", " Q")


# ------------------------------------------------------------------ columns


def _unit_from_name(name: str, percent: bool) -> Unit:
    if percent:
        return Unit(code="percent", label_en="%", label_ar="%")
    m = _UNIT_IN_NAME.search(name)
    if m and not _YEAR_NAME.search(m.group(1)):
        label = m.group(1).strip()
        return Unit(
            code=re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "unit",
            label_en=label,
            label_ar=label,
        )
    return Unit(code="unspecified", label_en="unit not stated", label_ar="الوحدة غير مذكورة")


def profile_columns(columns: list[str], rows: list[list[str | None]]) -> list[dict[str, Any]]:
    """Kind, unit, counts and examples of every column, with each cell read once."""
    out = []
    for i, name in enumerate(columns):
        cells = [r[i] for r in rows]
        filled = [(n, c) for n, c in enumerate(cells, start=1) if not is_missing(c)]
        missing = len(cells) - len(filled)
        texts = [c for _, c in filled if c is not None]
        numbers: dict[int, Decimal] = {}
        unreadable: list[int] = []
        percents = 0
        for n, c in filled:
            value, percent = number(str(c))
            if value is None:
                unreadable.append(n)
            else:
                numbers[n] = value
                percents += percent
        info: dict[str, Any] = {
            "index": i,
            "name": name,
            "count": len(filled),
            "missing": missing,
            "distinct": len(set(texts)),
            "examples": list(OrderedDict.fromkeys(texts))[:3],
        }
        year_column = bool(_YEAR_NAME.search(name))
        month_first = _month_first(texts)
        periods = {n: _period(str(c), year_column, month_first) for n, c in filled}
        kinds = {p[1] for p in periods.values() if p is not None}
        if filled and all(periods.values()) and len(kinds) == 1:
            info.update(kind="period", period_kind=kinds.pop())
            info["periods"] = {n: p[0] for n, p in periods.items() if p is not None}
            if info["period_kind"] == "date" and any(
                _DAY_MONTH_YEAR.match(t.translate(_ARABIC_DIGITS).strip()) for t in texts
            ):
                info["date_order"] = "month_first" if month_first else "day_first"
        elif numbers and Decimal(len(numbers)) >= NUMBER_SHARE * len(filled):
            info.update(
                kind="number",
                unit=_unit_from_name(name, percents == len(numbers)).model_dump(),
                unreadable=len(unreadable),
                unreadable_rows=unreadable[:5],
            )
            info["values"] = numbers
        else:
            counts = Counter(texts)
            info.update(
                kind="text",
                category=2 <= len(counts) <= MAX_GROUPS and len(counts) < len(texts),
                top=[{"value": v, "count": c} for v, c in counts.most_common(10)],
            )
            info["labels"] = {n: str(c) for n, c in filled}
        out.append(info)
    return out


# ------------------------------------------------------------------ statistics


def _quantile(ordered: list[Decimal], p: Decimal) -> Decimal:
    """Linear interpolation between the closest ranks (inclusive method)."""
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def statistics(col: dict[str, Any]) -> dict[str, Any]:
    values: dict[int, Decimal] = col["values"]
    ordered = sorted(values.values())
    n = len(ordered)
    total = sum(ordered, Decimal(0))
    mean = total / n
    lowest_row = min(values, key=lambda r: values[r])
    highest_row = max(values, key=lambda r: values[r])
    out = {
        "column": col["name"],
        "count": n,
        "sum": plain(total),
        "mean": computed(mean),
        "median": plain(_quantile(ordered, Decimal("0.5"))),
        "min": {"value": plain(values[lowest_row]), "row": lowest_row},
        "max": {"value": plain(values[highest_row]), "row": highest_row},
        "q1": computed(_quantile(ordered, Decimal("0.25"))),
        "q3": computed(_quantile(ordered, Decimal("0.75"))),
        "std": None,
        "all_non_negative": ordered[0] >= 0,
    }
    if n >= 2:
        variance = sum(((v - mean) ** 2 for v in ordered), Decimal(0)) / (n - 1)
        out["std"] = computed(variance.sqrt())
    return out


# ------------------------------------------------------------------ trends


def _series_points(
    period: dict[str, Any], col: dict[str, Any], rows: list[int]
) -> list[tuple[str, Decimal, int]] | None:
    """(period key, value, row) sorted by period, or None when a period repeats."""
    points = [
        (period["periods"][r], col["values"][r], r)
        for r in rows
        if r in period["periods"] and r in col["values"]
    ]
    keys = [p for p, _, _ in points]
    if len(keys) != len(set(keys)):
        return None
    return sorted(points)


def _trend(points: list[tuple[str, Decimal, int]], period_kind: str) -> dict[str, Any]:
    (p1, v1, _), (p2, v2, _) = points[0], points[-1]
    change = v2 - v1
    out: dict[str, Any] = {
        "points": len(points),
        "first": {"period": period_label(p1), "value": plain(v1)},
        "last": {"period": period_label(p2), "value": plain(v2)},
        "change": plain(change),
        "change_pct": _pct(change / abs(v1) * 100) if v1 != 0 else None,
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
        "cagr_pct": None,
    }
    steps = [b[1] - a[1] for a, b in zip(points, points[1:], strict=False)]
    out["steady"] = all(s >= 0 for s in steps) or all(s <= 0 for s in steps)
    peak = max(points, key=lambda p: p[1])
    trough = min(points, key=lambda p: p[1])
    out["peak"] = {"period": period_label(peak[0]), "value": plain(peak[1])}
    out["trough"] = {"period": period_label(trough[0]), "value": plain(trough[1])}
    years = int(p2[:4]) - int(p1[:4])
    if period_kind == "year" and years >= 1 and v1 > 0 and v2 > 0:
        rate = (float(v2) / float(v1)) ** (1 / years) - 1
        out["cagr_pct"] = _pct(Decimal(repr(rate * 100)))
    # Least-squares slope per step between consecutive periods in the file.
    xs = list(range(len(points)))
    ys = [float(v) for _, v, _ in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    out["slope_per_period"] = computed(Decimal(repr(slope)))
    out["jumps"] = _jumps(points)
    return out


def _jumps(points: list[tuple[str, Decimal, int]]) -> list[dict[str, Any]]:
    """Changes between consecutive periods far from the series' usual change (modified
    z-score of the steps above 3.5; at least four steps). A jump may be real or a data error;
    it is reported, never corrected."""
    if len(points) < MIN_JUMP_POINTS:
        return []
    steps = [(a, b, b[1] - a[1]) for a, b in zip(points, points[1:], strict=False)]
    ordered = sorted(d for _, _, d in steps)
    median = _quantile(ordered, Decimal("0.5"))
    mad = _quantile(sorted(abs(d - median) for d in ordered), Decimal("0.5"))
    if mad == 0:
        return []
    out = []
    for a, b, d in steps:
        score = Decimal("0.6745") * (d - median) / mad
        if abs(score) > Decimal("3.5"):
            out.append({
                "from": {"period": period_label(a[0]), "value": plain(a[1])},
                "to": {"period": period_label(b[0]), "value": plain(b[1]), "row": b[2]},
                "change": plain(d),
                "score": _pct(score),
            })  # fmt: skip
    return out


def trends(cols: list[dict[str, Any]], n_rows: int) -> tuple[list[dict[str, Any]], list[str]]:
    period = next((c for c in cols if c["kind"] == "period"), None)
    numeric = [c for c in cols if c["kind"] == "number"][:MAX_NUMERIC]
    if period is None or not numeric:
        return [], ["no_period_column" if period is None else "no_numeric_column"]
    all_rows = list(range(1, n_rows + 1))
    out: list[dict[str, Any]] = []
    notes: list[str] = []
    categories = [c for c in cols if c["kind"] == "text" and c["category"]]
    for col in numeric:
        points = _series_points(period, col, all_rows)
        if points is not None:
            if len(points) >= 2:
                out.append(
                    {
                        "column": col["name"],
                        "period_column": period["name"],
                        "group": None,
                        **_trend(points, period["period_kind"]),
                    }
                )
            continue
        split = None
        for cat in categories:
            groups: dict[str, list[int]] = {}
            for r, label in cat["labels"].items():
                groups.setdefault(label, []).append(r)
            series = {g: _series_points(period, col, rs) for g, rs in groups.items()}
            if all(s is not None for s in series.values()):
                split = (cat, series)
                break
        if split is None:
            notes.append(f"repeated_periods:{col['name']}")
            continue
        cat, series = split
        ranked = sorted(series.items(), key=lambda kv: -len(kv[1] or []))[:MAX_SERIES]
        for group, pts in ranked:
            if pts and len(pts) >= 2:
                out.append(
                    {
                        "column": col["name"],
                        "period_column": period["name"],
                        "group": {"column": cat["name"], "value": group},
                        **_trend(pts, period["period_kind"]),
                    }
                )
    return out[:MAX_TRENDS], notes


# ------------------------------------------------------------------ anomalies


def anomalies(col: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
    """Unusual values by the modified z-score (Iglewicz and Hoaglin: |0.6745 (x - median) /
    MAD| > 3.5), or, when half the values are equal (MAD 0), outside the 1.5 IQR fences."""
    values: dict[int, Decimal] = col["values"]
    if len(values) < MIN_ANOMALY_VALUES:
        return {"column": col["name"], "method": None, "status": "too_few_values", "items": []}
    ordered = sorted(values.values())
    median = _quantile(ordered, Decimal("0.5"))
    mad = _quantile(sorted(abs(v - median) for v in ordered), Decimal("0.5"))
    found: list[dict[str, Any]] = []
    if mad > 0:
        method = "modified_z_score"
        for r, v in values.items():
            score = Decimal("0.6745") * (v - median) / mad
            if abs(score) > Decimal("3.5"):
                found.append({"row": r, "value": plain(v), "score": _pct(score)})
    else:
        q1, q3 = _quantile(ordered, Decimal("0.25")), _quantile(ordered, Decimal("0.75"))
        iqr = q3 - q1
        method = "iqr_fences" if iqr > 0 else None
        if iqr > 0:
            low, high = q1 - Decimal("1.5") * iqr, q3 + Decimal("1.5") * iqr
            found = [
                {"row": r, "value": plain(v), "score": None}
                for r, v in values.items()
                if v < low or v > high
            ]
    found.sort(key=lambda a: -abs(Decimal(a["score"] or 0)))
    for a in found:
        if context is not None and a["row"] in context["map"]:
            a[context["key"]] = context["map"][a["row"]]
    return {
        "column": col["name"],
        "method": method,
        "status": "found" if found else "none",
        "count": len(found),
        "median": plain(median),
        "items": found[:MAX_ANOMALIES],
    }


# ------------------------------------------------------------------ comparisons


def comparisons(cat: dict[str, Any], col: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[Decimal]] = {}
    for r, label in cat["labels"].items():
        if r in col["values"]:
            groups.setdefault(label, []).append(col["values"][r])
    total = sum((sum(v, Decimal(0)) for v in groups.values()), Decimal(0))
    shares = col["stats"]["all_non_negative"] and total > 0 and col["unit"]["code"] != "percent"
    rows = []
    for label, vals in groups.items():
        s = sum(vals, Decimal(0))
        rows.append(
            {
                "group": label,
                "count": len(vals),
                "sum": plain(s),
                "mean": computed(s / len(vals)),
                "min": plain(min(vals)),
                "max": plain(max(vals)),
                "share_pct": _pct(s / total * 100) if shares else None,
            }
        )
    rows.sort(key=lambda g: -Decimal(g["sum"]))
    return {
        "category": cat["name"],
        "column": col["name"],
        "groups": rows,
        "total": plain(total),
        "one_row_per_group": all(g["count"] == 1 for g in rows),
    }


# ------------------------------------------------------------------ correlations


def correlations(numeric: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, a in enumerate(numeric):
        for b in numeric[i + 1 :]:
            rows = sorted(set(a["values"]) & set(b["values"]))
            if len(rows) < MIN_CORRELATION_PAIRS:
                continue
            xs = [float(a["values"][r]) for r in rows]
            ys = [float(b["values"][r]) for r in rows]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            syy = sum((y - my) ** 2 for y in ys)
            if sxx == 0 or syy == 0:
                continue
            r = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / math.sqrt(sxx * syy)
            r = max(-1.0, min(1.0, r))
            strength = "strong" if abs(r) >= 0.7 else "moderate" if abs(r) >= 0.4 else "weak"
            out.append(
                {
                    "x": a["name"],
                    "y": b["name"],
                    "r": f"{r:.3f}",
                    "pairs": len(rows),
                    "strength": strength,
                }
            )
    out.sort(key=lambda c: -abs(float(c["r"])))
    return out[:10]


# ------------------------------------------------------------------ views (tables and charts)


def _view(
    view_id: str,
    title: Text,
    table: Table,
    chart: Chart,
    alternatives: list[str],
    note: Text | None = None,
) -> dict[str, Any]:
    check_table_and_charts(table, [chart])
    return {
        "id": view_id,
        "title": title.model_dump(),
        "table": table.model_dump(mode="json"),
        "chart": chart.model_dump(mode="json"),
        "alternatives": alternatives,
        "note": note.model_dump() if note else None,
    }


def _unit(col: dict[str, Any]) -> Unit:
    return Unit(**col["unit"])


def _time_views(cols: list[dict[str, Any]], n_rows: int) -> list[dict[str, Any]]:
    period = next((c for c in cols if c["kind"] == "period"), None)
    numeric = [c for c in cols if c["kind"] == "number"][:MAX_NUMERIC]
    if period is None:
        return []
    rows = list(range(1, n_rows + 1))
    views = []
    plain_series: dict[str, list[dict[str, Any]]] = {}  # unit code -> columns
    for col in numeric:
        points = _series_points(period, col, rows)
        if points is not None and len(points) >= 2:
            plain_series.setdefault(col["unit"]["code"], []).append(col)
    for unit_code, group in plain_series.items():
        group = group[:MAX_SERIES]
        keys = sorted(
            {period["periods"][r] for c in group for r in c["values"] if r in period["periods"]}
        )
        by_period = {
            c["name"]: {
                period["periods"][r]: v for r, v in c["values"].items() if r in period["periods"]
            }
            for c in group
        }
        columns = [
            Column(key="period", label=Text(en=period["name"], ar=period["name"]), kind="period")
        ]
        series = []
        for j, c in enumerate(group, start=1):
            columns.append(
                Column(
                    key=f"c{j}",
                    label=Text(en=c["name"], ar=c["name"]),
                    kind="number",
                    unit=_unit(c),
                )
            )
            series.append(
                ChartSeries(
                    column=f"c{j}", label=Text(en=c["name"], ar=c["name"]), nature="observed"
                )
            )
        table_rows = [
            {
                "period": period_label(k),
                **{
                    f"c{j}": (plain(by_period[c["name"]][k]) if k in by_period[c["name"]] else None)
                    for j, c in enumerate(group, start=1)
                },
            }
            for k in keys
        ]
        names = ", ".join(c["name"] for c in group)
        title = Text(en=f"{names} over time", ar=f"{names} عبر الزمن")
        chart = Chart(type="line", title=title, x="period", series=series, unit=_unit(group[0]))
        views.append(
            _view(
                f"time_{unit_code}",
                title,
                Table(columns=columns, rows=table_rows),
                chart,
                ["line", "bar"],
            )
        )
    # One measure split by a category into series (e.g. a value per region per year).
    categories = [c for c in cols if c["kind"] == "text" and c["category"]]
    shown = {c["name"] for group in plain_series.values() for c in group}
    for col in numeric:
        if col["name"] in shown:
            continue
        for cat in categories:
            groups: dict[str, list[int]] = {}
            for r, label in cat["labels"].items():
                groups.setdefault(label, []).append(r)
            series_points = {g: _series_points(period, col, rs) for g, rs in groups.items()}
            if not all(s is not None for s in series_points.values()):
                continue
            ranked = sorted(series_points.items(), key=lambda kv: -len(kv[1] or []))[:MAX_SERIES]
            ranked = [(g, pts) for g, pts in ranked if pts]
            if not ranked:
                continue
            keys = sorted({p for _, pts in ranked for p, _, _ in pts or []})
            columns = [
                Column(
                    key="period", label=Text(en=period["name"], ar=period["name"]), kind="period"
                )
            ]
            series = []
            values = []
            for j, (g, pts) in enumerate(ranked, start=1):
                columns.append(
                    Column(key=f"c{j}", label=Text(en=g, ar=g), kind="number", unit=_unit(col))
                )
                series.append(
                    ChartSeries(column=f"c{j}", label=Text(en=g, ar=g), nature="observed")
                )
                values.append({p: v for p, v, _ in pts or []})
            table_rows = [
                {
                    "period": period_label(k),
                    **{
                        f"c{j}": (plain(values[j - 1][k]) if k in values[j - 1] else None)
                        for j in range(1, len(ranked) + 1)
                    },
                }
                for k in keys
            ]
            title = Text(
                en=f"{col['name']} by {cat['name']} over time",
                ar=f"{col['name']} حسب {cat['name']} عبر الزمن",
            )
            chart = Chart(type="line", title=title, x="period", series=series, unit=_unit(col))
            note = None
            if len(groups) > len(ranked):
                note = Text(
                    en=f"The {len(ranked)} groups with the most periods are shown.",
                    ar=f"تُعرض {len(ranked)} مجموعات لديها أكبر عدد من الفترات.",
                )
            views.append(
                _view(
                    f"time_{col['index']}_by_{cat['index']}",
                    title,
                    Table(columns=columns, rows=table_rows),
                    chart,
                    ["line", "bar"],
                    note,
                )
            )
            break
    return views


def _category_views(
    comps: list[dict[str, Any]], cols: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_name = {c["name"]: c for c in cols}
    views = []
    for comp in comps[:3]:
        col, cat = by_name[comp["column"]], by_name[comp["category"]]
        groups = comp["groups"][:MAX_CATEGORIES_CHART]
        percent = col["unit"]["code"] == "percent"
        if comp["one_row_per_group"]:
            measure, key = Text(en=col["name"], ar=col["name"]), "sum"
            title = Text(
                en=f"{col['name']} by {cat['name']}", ar=f"{col['name']} حسب {cat['name']}"
            )
        elif percent:
            measure, key = Text(en=f"Average {col['name']}", ar=f"متوسط {col['name']}"), "mean"
            title = Text(
                en=f"Average {col['name']} by {cat['name']}",
                ar=f"متوسط {col['name']} حسب {cat['name']}",
            )
        else:
            measure, key = Text(en=f"Total {col['name']}", ar=f"مجموع {col['name']}"), "sum"
            title = Text(
                en=f"Total {col['name']} by {cat['name']}",
                ar=f"مجموع {col['name']} حسب {cat['name']}",
            )
        columns = [
            Column(key="category", label=Text(en=cat["name"], ar=cat["name"]), kind="text"),
            Column(key="value", label=measure, kind="number", unit=_unit(col)),
        ]
        rows = [{"category": g["group"], "value": g[key]} for g in groups]
        chart = Chart(
            type="bar",
            title=title,
            x="category",
            unit=_unit(col),
            series=[
                ChartSeries(
                    column="value",
                    label=measure,
                    nature="observed" if comp["one_row_per_group"] else "calculated",
                )
            ],
        )
        pie = (
            key == "sum"
            and comp["groups"][0]["share_pct"] is not None
            and len(comp["groups"]) <= MAX_PIE_SLICES
        )
        note = None
        if len(comp["groups"]) > len(groups):
            note = Text(
                en=f"The {len(groups)} largest of {len(comp['groups'])} groups are shown.",
                ar=f"تُعرض أكبر {len(groups)} مجموعات من {len(comp['groups'])}.",
            )
        views.append(
            _view(
                f"compare_{col['index']}_by_{cat['index']}",
                title,
                Table(columns=columns, rows=rows),
                chart,
                ["bar", "pie"] if pie else ["bar"],
                note,
            )
        )
    return views


def _scatter_view(corr: list[dict[str, Any]], cols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not corr:
        return []
    by_name = {c["name"]: c for c in cols}
    best = corr[0]
    a, b = by_name[best["x"]], by_name[best["y"]]
    rows = sorted(set(a["values"]) & set(b["values"]))[:MAX_SCATTER_POINTS]
    columns = [
        Column(key="x", label=Text(en=a["name"], ar=a["name"]), kind="number", unit=_unit(a)),
        Column(key="y", label=Text(en=b["name"], ar=b["name"]), kind="number", unit=_unit(b)),
    ]
    table_rows = [{"x": plain(a["values"][r]), "y": plain(b["values"][r])} for r in rows]
    title = Text(
        en=f"{b['name']} against {a['name']} (r = {best['r']})",
        ar=f"{b['name']} مقابل {a['name']} (r = {best['r']})",
    )
    chart = Chart(
        type="scatter",
        title=title,
        x="x",
        unit=_unit(b),
        series=[ChartSeries(column="y", label=Text(en=b["name"], ar=b["name"]), nature="observed")],
    )
    note = Text(
        en="A correlation shows that two measures move together, not that one causes the other.",
        ar="يدل الارتباط على أن المقياسين يتغيران معًا، ولا يعني أن أحدهما سبب الآخر.",
    )
    return [
        _view("scatter", title, Table(columns=columns, rows=table_rows), chart, ["scatter"], note)
    ]


def _histogram_view(col: dict[str, Any]) -> list[dict[str, Any]]:
    values = sorted(col["values"].values())
    if len(values) < 10 or values[0] == values[-1]:
        return []
    bins = 10
    low, high = values[0], values[-1]
    width = (high - low) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - low) / width), bins - 1)] += 1
    edges = [low + width * i for i in range(bins + 1)]
    rows = [
        {"bin": f"{computed(edges[i])} – {computed(edges[i + 1])}", "count": str(counts[i])}
        for i in range(bins)
    ]
    rows_unit = Unit(code="rows", label_en="rows", label_ar="صفوف")
    columns = [
        Column(key="bin", label=Text(en=col["name"], ar=col["name"]), kind="text"),
        Column(key="count", label=Text(en="Rows", ar="عدد الصفوف"), kind="number", unit=rows_unit),
    ]
    title = Text(en=f"Distribution of {col['name']}", ar=f"توزيع {col['name']}")
    chart = Chart(
        type="bar",
        title=title,
        x="bin",
        unit=rows_unit,
        series=[
            ChartSeries(column="count", label=Text(en="Rows", ar="عدد الصفوف"), nature="calculated")
        ],
    )
    return [
        _view(f"histogram_{col['index']}", title, Table(columns=columns, rows=rows), chart, ["bar"])
    ]


# ------------------------------------------------------------------ findings


def _signed(pct: str) -> str:
    return pct if pct.startswith("-") else f"+{pct}"


def _finding(kind: str, en: str, ar: str) -> dict[str, Any]:
    return {"kind": kind, "text": {"en": en, "ar": ar}}


def _findings(
    cols: list[dict[str, Any]],
    trend_list: list[dict[str, Any]],
    anomaly_list: list[dict[str, Any]],
    comps: list[dict[str, Any]],
    corr: list[dict[str, Any]],
    n_rows: int,
    duplicates: int,
) -> list[dict[str, Any]]:
    """Short sentences in both languages, each built from computed values only."""
    out: list[dict[str, Any]] = []
    for t in trend_list[:6]:
        name = t["column"] + (f" ({t['group']['value']})" if t["group"] else "")
        first, last = t["first"], t["last"]
        pct = f" ({_signed(t['change_pct'])}%)" if t["change_pct"] else ""
        cagr_en = f"; compound annual growth {t['cagr_pct']}%" if t["cagr_pct"] else ""
        cagr_ar = f"؛ معدل النمو السنوي المركب {t['cagr_pct']}%" if t["cagr_pct"] else ""
        out.append(
            _finding(
                "trend",
                f"{name}: {grouped(first['value'])} in {first['period']} to "
                f"{grouped(last['value'])} in {last['period']}{pct}{cagr_en}.",
                f"{name}: من {grouped(first['value'])} في {first['period']} إلى "
                f"{grouped(last['value'])} في {last['period']}{pct}{cagr_ar}.",
            )
        )
    for comp in comps[:3]:
        if len(comp["groups"]) < 2:
            continue
        top = comp["groups"][0]
        share_en = f", {top['share_pct']}% of the total" if top["share_pct"] else ""
        share_ar = f"، أي {top['share_pct']}% من المجموع" if top["share_pct"] else ""
        if comp["one_row_per_group"]:
            what_en, what_ar = "value", "قيمة"
        else:
            what_en, what_ar = "total over all rows", "مجموع في جميع الصفوف"
        out.append(
            _finding(
                "comparison",
                f"Highest {what_en} of {comp['column']}: {top['group']} "
                f"({grouped(top['sum'])}{share_en}).",
                f"أعلى {what_ar} لـ{comp['column']}: {top['group']} "
                f"({grouped(top['sum'])}{share_ar}).",
            )
        )
    for t in trend_list:
        for j in t["jumps"][:1]:
            name = t["column"] + (f" ({t['group']['value']})" if t["group"] else "")
            frm, to = j["from"], j["to"]
            out.append(
                _finding(
                    "jump",
                    f"Unusual change in {name}: {grouped(frm['value'])} in {frm['period']} to "
                    f"{grouped(to['value'])} in {to['period']} (data row {to['row']}); check "
                    "whether it is real or a data error.",
                    f"تغير غير معتاد في {name}: من {grouped(frm['value'])} في {frm['period']} إلى "
                    f"{grouped(to['value'])} في {to['period']} (صف البيانات {to['row']})؛ "
                    "تحقق مما إذا كان حقيقيًا أم خطأ في البيانات.",
                )
            )
    for a in anomaly_list:
        if a["status"] != "found":
            continue
        top = a["items"][0]
        value, median = grouped(top["value"]), grouped(a["median"])
        out.append(
            _finding(
                "anomaly",
                f"{a['count']} unusual value(s) in {a['column']}; the most extreme is "
                f"{value} in data row {top['row']} (median {median}).",
                f"{a['count']} قيمة غير معتادة في {a['column']}؛ أبعدها {value} "
                f"في صف البيانات {top['row']} (الوسيط {median}).",
            )
        )
    for c in corr[:2]:
        if c["strength"] == "weak":
            continue
        how_en, how_ar = {
            "strong": ("strongly", "بقوة"),
            "moderate": ("moderately", "بدرجة متوسطة"),
        }[c["strength"]]
        positive = float(c["r"]) > 0
        way_en = "together" if positive else "in opposite directions"
        way_ar = "في الاتجاه نفسه" if positive else "في اتجاهين متعاكسين"
        out.append(
            _finding(
                "correlation",
                f"{c['x']} and {c['y']} move {how_en} {way_en} (r = {c['r']}, {c['pairs']} rows).",
                f"يتغير {c['x']} و{c['y']} {how_ar} {way_ar} (r = {c['r']}، {c['pairs']} صفًا).",
            )
        )
    gaps = [c for c in cols if c["missing"]]
    if gaps:
        worst = max(gaps, key=lambda c: c["missing"])
        out.append(
            _finding(
                "quality",
                f"{len(gaps)} column(s) have missing values; {worst['name']} is missing "
                f"{worst['missing']} of {n_rows} rows. Missing values are left out, never counted "
                "as zero.",
                f"في {len(gaps)} عمود قيم مفقودة؛ ينقص {worst['name']} في {worst['missing']} من "
                f"{n_rows} صفًا. تُستبعد القيم المفقودة ولا تُحسب صفرًا.",
            )
        )
    if duplicates:
        out.append(
            _finding(
                "quality",
                f"{duplicates} row(s) repeat an earlier row exactly.",
                f"{duplicates} صفًا يكرر صفًا سابقًا تمامًا.",
            )
        )
    return out


# ------------------------------------------------------------------ the whole analysis


def analyse(columns: list[str], rows: list[list[str | None]]) -> dict[str, Any]:
    cols = profile_columns(columns, rows)
    numeric = [c for c in cols if c["kind"] == "number"]
    stats = []
    for c in numeric:
        c["stats"] = statistics(c)
        stats.append(c["stats"])
    trend_list, trend_notes = trends(cols, len(rows))
    period = next((c for c in cols if c["kind"] == "period"), None)
    context = None
    if period is not None:
        context = {
            "key": "period",
            "map": {r: period_label(p) for r, p in period["periods"].items()},
        }
    anomaly_list = [anomalies(c, context) for c in numeric[:MAX_NUMERIC]]
    categories = [c for c in cols if c["kind"] == "text" and c["category"]]
    comps = [comparisons(cat, col) for cat in categories[:3] for col in numeric[:5]]
    corr = correlations(numeric[:MAX_NUMERIC])
    duplicates = len(rows) - len({tuple(r) for r in rows})
    views = _time_views(cols, len(rows)) + _category_views(comps, cols) + _scatter_view(corr, cols)
    if numeric:
        views += _histogram_view(numeric[0])
    profile = [
        {k: v for k, v in c.items() if k not in ("values", "labels", "periods", "stats")}
        for c in cols
    ]
    return {
        "version": ANALYSIS_VERSION,
        "rows": len(rows),
        "columns": len(columns),
        "duplicate_rows": duplicates,
        "profile": profile,
        "statistics": stats,
        "trends": trend_list,
        "trend_notes": trend_notes,
        "anomalies": anomaly_list,
        "comparisons": [{**c, "groups": c["groups"][:MAX_GROUPS]} for c in comps],
        "correlations": corr,
        "findings": _findings(cols, trend_list, anomaly_list, comps, corr, len(rows), duplicates),
        "views": views,
    }
