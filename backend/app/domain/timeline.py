"""Chronological series for tables and charts. Pure: no I/O.

One indicator, one area, one unit and one breakdown become rows in time order, in the
view asked for (monthly, quarterly or annual), under these rules:

* Rows are sorted by period start, never by label.
* Published values are used as they are. A period missing from the source stays a row
  without a value (``missing``); it is never filled with zero or interpolated.
* Annual totals are never divided into quarters or months, and quarters never into months.
* A quarter or year is derived from its months (or a year from its quarters) only by the
  indicator's value type, and only when every component is published:
  - period totals (flows: generation, production, trade values) are summed;
  - end-of-period levels (stocks: capacity, connections, livestock) are never summed: the
    period takes the value at its last month or quarter;
  - maxima (peak demand) take the largest component;
  - averages and ratios are never derived: a weighted average needs weights the source
    does not publish.
  A derived row is labelled ``derived`` with its basis; a published one keeps its own status.
* Year-to-date totals are kept apart from monthly values and from complete years.
* When two publications give the same period, the final figure is preferred to a
  provisional one, then the newer publication; a different value from the other
  publication is kept with the row (``revised``), never dropped silently.
* Changes (previous period; same period a year earlier) are calculated by the platform's
  change functions, only between comparable periods; a zero previous value gives no
  percentage, and a value published as "more than" or "less than" gives no change.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain import calculations as calc
from app.domain.enums import PhysicalDimension
from app.domain.explanations import explain
from app.domain.quantities import Measurement, Period, Unit

VIEWS = ("annual", "quarterly", "monthly")
PROVISIONAL = frozenset({"provisional", "preliminary"})
ESTIMATE = frozenset({"estimate"})

RULES: dict[str, dict[str, str]] = {
    "sorted": {
        "en": "Rows are in time order.",
        "ar": "الصفوف مرتبة زمنياً.",
    },
    "missing_kept": {
        "en": "Periods the source does not publish are shown empty, never as zero.",
        "ar": "الفترات التي لا ينشرها المصدر تظهر فارغة، وليست صفراً.",
    },
    "not_split": {
        "en": "Annual totals are never divided into quarters or months.",
        "ar": "لا تُقسَّم المجاميع السنوية أبداً على الأرباع أو الأشهر.",
    },
    "sum_of_components": {
        "en": "Some periods are sums of their published months or quarters (the indicator is a "
        "period total); every component was published.",
        "ar": "بعض الفترات مجموع أشهرها أو أرباعها المنشورة (المؤشر مجموع للفترة)؛ وكل المكونات "
        "منشورة.",
    },
    "end_of_period": {
        "en": "This indicator is a level at the end of each period, so values are never added: "
        "a quarter or year takes the value at its last published month or quarter.",
        "ar": "هذا المؤشر مستوى في نهاية كل فترة، لذلك لا تُجمع قيمه: يأخذ الربع أو السنة "
        "القيمة في آخر شهر أو ربع منشور.",
    },
    "maximum": {
        "en": "This indicator is a maximum: a quarter or year takes the largest of its "
        "published months, only when every month is published.",
        "ar": "هذا المؤشر قيمة قصوى: يأخذ الربع أو السنة أكبر قيم أشهره المنشورة، وفقط عند "
        "نشر كل الأشهر.",
    },
    "not_derived_rate": {
        "en": "Averages and ratios are not combined across periods: a weighted average needs "
        "weights the source does not publish.",
        "ar": "لا تُجمع المتوسطات والنسب عبر الفترات: يحتاج المتوسط المرجّح إلى أوزان لا ينشرها "
        "المصدر.",
    },
    "year_to_date_apart": {
        "en": "Year-to-date totals are shown apart and compared only with the same months of "
        "the previous year.",
        "ar": "تُعرض المجاميع منذ بداية العام على حدة، ولا تُقارن إلا بالأشهر نفسها من العام السابق.",
    },
    "revised": {
        "en": "Where publications disagree, the final figure is shown (then the newer "
        "publication) and the other value is listed with the row.",
        "ar": "عند اختلاف المنشورات يُعرض الرقم النهائي (ثم الأحدث نشراً) ويُذكر الرقم الآخر مع الصف.",
    },
    "several_sources": {
        "en": "Rows come from more than one publication; each row names its source.",
        "ar": "تأتي الصفوف من أكثر من منشور؛ ويذكر كل صف مصدره.",
    },
    "forecast_apart": {
        "en": "Forecasts are model estimates with intervals, shown after the last observation "
        "and never mixed with published values.",
        "ar": "التوقعات تقديرات نموذج مع فترات ثقة، تُعرض بعد آخر مشاهدة ولا تُخلط بالقيم المنشورة.",
    },
}

INEXACT = {
    "code": "inexact_value",
    "en": "A value published as 'more than' or 'less than' cannot be used in a calculation.",
    "ar": "لا يمكن استخدام قيمة منشورة بصيغة «أكثر من» أو «أقل من» في الحساب.",
}
NO_COMPARISON = {
    "code": "no_comparison_period",
    "en": "The period to compare with is not published.",
    "ar": "الفترة التي تُقارن بها غير منشورة.",
}


@dataclass(frozen=True, slots=True)
class Published:
    """One published observation of the series, with what identifies its publication."""

    start: date
    end: date
    kind: str  # annual | quarterly | monthly | year_to_date
    value: Decimal | None
    operator: str | None
    revision_status: str | None
    source: dict[str, Any]
    version: dict[str, Any]
    record_ref: str | None = None
    locator: str | None = None


@dataclass(slots=True)
class Row:
    start: date
    end: date
    frequency: str
    value: Decimal | None
    operator: str | None = None
    nature: str = "observed"  # observed | provisional | estimate | derived | missing | forecast
    status: str = "published"  # published | missing_in_source | not_published | derived | ...
    basis: str | None = None  # how a derived row was obtained
    revision_status: str | None = None
    source: dict[str, Any] | None = None
    version: dict[str, Any] | None = None
    record_ref: str | None = None
    locator: str | None = None
    components: list[str] = field(default_factory=list)  # derived: component periods
    others: list[dict[str, Any]] = field(default_factory=list)  # other publications' values
    reason: dict[str, str] | None = None  # why a value is not given
    changes: list[dict[str, Any]] = field(default_factory=list)
    interval: dict[str, str | None] | None = None  # forecasts only

    def out(self) -> dict[str, Any]:
        return {
            "period_start": self.start.isoformat(),
            "period_end": self.end.isoformat(),
            "frequency": self.frequency,
            "value": _text(self.value),
            "value_operator": self.operator,
            "nature": self.nature,
            "status": self.status,
            "basis": self.basis,
            "revision_status": self.revision_status,
            "source": self.source,
            "dataset_version": self.version,
            "record_ref": self.record_ref,
            "locator": self.locator,
            "components": self.components,
            "other_publications": self.others,
            "revised": bool(self.others),
            "reason": self.reason,
            "changes": self.changes,
            "interval": self.interval,
        }


def _text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize() if value == value.to_integral() else value, "f")


# ------------------------------------------------------------------ calendar


def month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def quarter_of(d: date) -> int:
    return (d.month - 1) // 3 + 1


def quarter_start(year: int, q: int) -> date:
    return date(year, 3 * (q - 1) + 1, 1)


def grid(view: str, first: date, last: date) -> list[tuple[date, date]]:
    """Every period of the view from the one containing ``first`` to the one containing
    ``last``, in time order."""
    out: list[tuple[date, date]] = []
    if view == "annual":
        for y in range(first.year, last.year + 1):
            out.append((date(y, 1, 1), date(y, 12, 31)))
    elif view == "quarterly":
        y, q = first.year, quarter_of(first)
        while (y, q) <= (last.year, quarter_of(last)):
            start = quarter_start(y, q)
            out.append((start, month_end(y, 3 * q)))
            y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    else:
        y, m = first.year, first.month
        while (y, m) <= (last.year, last.month):
            out.append((date(y, m, 1), month_end(y, m)))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def components_of(view: str, start: date) -> tuple[str, list[tuple[date, date]]]:
    """The finer periods a quarter or year is made of (months of a quarter; months, or
    quarters, of a year)."""
    if view == "quarterly":
        q = quarter_of(start)
        return "monthly", [(date(start.year, m, 1), month_end(start.year, m))
                           for m in range(3 * q - 2, 3 * q + 1)]  # fmt: skip
    return "monthly", [(date(start.year, m, 1), month_end(start.year, m)) for m in range(1, 13)]


def quarters_of_year(year: int) -> list[tuple[date, date]]:
    return [(quarter_start(year, q), month_end(year, 3 * q)) for q in range(1, 5)]


# ------------------------------------------------------------------ choosing publications


def _final(p: Published) -> bool:
    return (p.revision_status or "") not in PROVISIONAL | ESTIMATE


def nature_of(revision_status: str | None) -> str:
    if revision_status in PROVISIONAL:
        return "provisional"
    if revision_status in ESTIMATE:
        return "estimate"
    return "observed"


def choose(candidates: list[Published]) -> tuple[Published, list[dict[str, Any]]]:
    """The figure shown for one period, and the other publications' different values."""
    ordered = sorted(
        candidates,
        key=lambda p: (_final(p), str(p.version.get("published_at") or "")),
        reverse=True,
    )
    chosen = ordered[0]
    others = [
        {
            "value": _text(p.value),
            "value_operator": p.operator,
            "revision_status": p.revision_status,
            "source": p.source,
            "dataset_version": p.version,
        }
        for p in ordered[1:]
        if p.value != chosen.value or p.operator != chosen.operator
    ]
    return chosen, others


def _published_row(p: Published, others: list[dict[str, Any]]) -> Row:
    missing = p.value is None
    return Row(
        p.start, p.end, p.kind, p.value, p.operator,
        nature="missing" if missing else nature_of(p.revision_status),
        status="missing_in_source" if missing else "published",
        revision_status=p.revision_status, source=p.source, version=p.version,
        record_ref=p.record_ref, locator=p.locator, others=others,
        reason={"code": "missing_in_source", "en": "The source reports this value as missing.",
                "ar": "يذكر المصدر أن هذه القيمة غير متوفرة."} if missing else None,
    )  # fmt: skip


# ------------------------------------------------------------------ deriving


def derive(
    value_type: str, parts: list[Row | None], expected: int
) -> tuple[Decimal | None, str | None, dict[str, str] | None]:
    """(value, basis, reason) for a period made of ``parts`` (None: not published)."""
    present = [p for p in parts if p is not None and p.value is not None]
    if value_type == "average":
        return None, None, {"code": "rate_not_derived", **_rule("not_derived_rate")}
    if any(p.operator for p in present):
        return None, None, INEXACT
    if value_type in ("end_of_period", "cumulative_to_date"):
        last = parts[-1] if parts else None
        if last is None or last.value is None:
            return None, None, {
                "code": "last_component_missing",
                "en": "The value at the end of the period is not published.",
                "ar": "القيمة في نهاية الفترة غير منشورة.",
            }  # fmt: skip
        return last.value, "end_of_period", None
    if len(present) < expected:
        return None, None, {
            "code": "components_incomplete",
            "en": f"{len(present)} of {expected} component periods are published; the total is "
            "not calculated from an incomplete set.",
            "ar": f"نُشرت {len(present)} من {expected} فترات مكوّنة؛ لا يُحسب المجموع من مجموعة "
            "ناقصة.",
        }  # fmt: skip
    if value_type == "maximum":
        return max(p.value for p in present if p.value is not None), "maximum_of_components", None
    total = sum((p.value for p in present if p.value is not None), Decimal(0))
    return total, "sum_of_components", None


def _rule(code: str) -> dict[str, str]:
    return {"en": RULES[code]["en"], "ar": RULES[code]["ar"]}


def _derived_row(
    start: date, end: date, view: str, value_type: str, parts: list[Row | None],
    labels: list[str],
) -> Row:  # fmt: skip
    value, basis, reason = derive(value_type, parts, len(parts))
    present = [p for p in parts if p is not None]
    if value is None:
        return Row(start, end, view, None, nature="missing", status="not_published",
                   reason=reason)  # fmt: skip
    statuses = {p.nature for p in present if p.value is not None}
    sources = {json.dumps(p.source, sort_keys=True, default=str) for p in present if p.source}
    return Row(
        start, end, view, value, nature="derived", status="derived", basis=basis,
        revision_status="provisional" if statuses & {"provisional", "estimate"} else None,
        source=present[-1].source if len(sources) == 1 else None,
        version=present[-1].version if len(sources) == 1 else None,
        components=labels,
    )  # fmt: skip


# ------------------------------------------------------------------ building


@dataclass
class Timeline:
    view: str
    rows: list[Row]
    year_to_date: list[Row]
    rules: list[str]
    available_views: list[str]

    def digest(self) -> str:
        """Identifies the dataset both the table and the chart are drawn from."""
        body = json.dumps(
            [r.out() for r in self.rows] + [r.out() for r in self.year_to_date],
            sort_keys=True, default=str,
        )  # fmt: skip
        return hashlib.sha256(body.encode()).hexdigest()[:16]


def label(view: str, start: date) -> str:
    if view == "annual":
        return str(start.year)
    if view == "quarterly":
        return f"{start.year}-Q{quarter_of(start)}"
    return f"{start.year}-{start.month:02d}"


def _view_rows(
    view: str,
    chosen: dict[str, dict[tuple[date, date], Row]],
    value_type: str,
    period_from: date | None,
    period_to: date | None,
) -> list[Row]:
    monthly = chosen.get("monthly", {})
    quarterly = chosen.get("quarterly", {})
    annual = chosen.get("annual", {})
    own = {"annual": annual, "quarterly": quarterly, "monthly": monthly}[view]
    starts = [k[0] for k in own]
    if view in ("annual", "quarterly"):
        starts += [k[0] for k in monthly]
    if view == "annual":
        starts += [k[0] for k in quarterly]
    rows: list[Row] = []
    if starts:
        first = max(min(starts), period_from) if period_from else min(starts)
        last_starts = [s for s in starts if not period_to or s <= period_to]
        last = max(last_starts) if last_starts else first
        for start, end in grid(view, first, last):
            if (start, end) in own:
                rows.append(own[(start, end)])
                continue
            if view == "monthly":
                rows.append(Row(start, end, "monthly", None, nature="missing",
                                status="not_published", reason=NO_PUBLISHED))  # fmt: skip
                continue
            _, parts = components_of(view, start)
            months = [monthly.get(p) for p in parts]
            if view == "annual" and not any(months) and quarterly:
                quarters = [quarterly.get(p) for p in quarters_of_year(start.year)]
                if any(quarters):
                    labels = [label("quarterly", p[0]) for p in quarters_of_year(start.year)]
                    rows.append(_derived_row(start, end, view, value_type, quarters, labels))
                    continue
            if any(months):
                labels = [label("monthly", p[0]) for p in parts]
                rows.append(_derived_row(start, end, view, value_type, months, labels))
                continue
            rows.append(Row(start, end, view, None, nature="missing", status="not_published",
                            reason=NO_PUBLISHED))  # fmt: skip
    return [
        r for r in rows
        if (not period_from or r.end >= period_from) and (not period_to or r.start <= period_to)
    ]  # fmt: skip


def build(
    published: list[Published],
    value_type: str,
    view: str,
    unit: Unit,
    coverage: str,
    *,
    period_from: date | None = None,
    period_to: date | None = None,
) -> Timeline:
    """Rows of the view from the published observations of one series."""
    if view not in VIEWS:
        raise ValueError(f"unknown view {view}")
    by_kind: dict[str, dict[tuple[date, date], list[Published]]] = {}
    for p in published:
        by_kind.setdefault(p.kind, {}).setdefault((p.start, p.end), []).append(p)
    rules = ["sorted", "missing_kept", "not_split"]
    chosen: dict[str, dict[tuple[date, date], Row]] = {}
    for kind, periods in by_kind.items():
        chosen[kind] = {}
        for key, candidates in periods.items():
            pick, others = choose(candidates)
            chosen[kind][key] = _published_row(pick, others)
            if others:
                rules.append("revised")
    available = [
        v for v in VIEWS
        if any(r.value is not None for r in _view_rows(v, chosen, value_type, None, None))
    ]  # fmt: skip
    # Changes use the whole series (a year-earlier month may lie before the range shown).
    every = _view_rows(view, chosen, value_type, None, None)
    _changes(every, view, unit, coverage)
    rows = [r for r in every if _within(r, period_from, period_to)]
    if any(r.nature == "derived" for r in rows):
        rules.append({
            "period_total": "sum_of_components", "end_of_period": "end_of_period",
            "cumulative_to_date": "end_of_period", "maximum": "maximum",
        }.get(value_type, "not_derived_rate"))  # fmt: skip
    if value_type == "average" and view != "monthly":
        rules.append("not_derived_rate")
    sources = {json.dumps(r.source, sort_keys=True, default=str) for r in rows if r.source}
    if len(sources) > 1:
        rules.append("several_sources")

    ytd = sorted(chosen.get("year_to_date", {}).values(), key=lambda r: (r.start, r.end))
    _ytd_changes(ytd, unit, coverage)
    ytd = [r for r in ytd if _within(r, period_from, period_to)]
    if ytd:
        rules.append("year_to_date_apart")
    return Timeline(view, rows, ytd, list(dict.fromkeys(rules)), available)


def _within(r: Row, period_from: date | None, period_to: date | None) -> bool:
    return (not period_from or r.end >= period_from) and (not period_to or r.start <= period_to)


NO_PUBLISHED = {
    "code": "not_published",
    "en": "Not published for this period.",
    "ar": "غير منشور لهذه الفترة.",
}


# ------------------------------------------------------------------ changes


def _measure(r: Row, unit: Unit, coverage: str, complete: bool = True) -> Measurement:
    return Measurement(r.value, unit, Period(r.start, r.end, complete), coverage)


def change(previous: Row | None, current: Row, basis: str, unit: Unit, coverage: str,
           complete: bool = True) -> dict[str, Any]:  # fmt: skip
    """Absolute and percentage change from ``previous`` to ``current`` by the platform's
    calculations (comparable periods only; no percentage from a zero)."""
    out: dict[str, Any] = {
        "basis": basis,
        "against": previous.start.isoformat() if previous is not None else None,
        "absolute": None,
        "percent": None,
        "status": "ok",
        "reason": None,
    }
    if previous is None or previous.value is None:
        return {**out, "status": "missing", "reason": NO_COMPARISON}
    if previous.operator or current.operator:
        return {**out, "status": "inexact", "reason": INEXACT}
    a = _measure(previous, unit, coverage, complete)
    b = _measure(current, unit, coverage, complete)
    absolute = calc.absolute_change(a, b)
    percent = calc.percentage_change(a, b)
    if absolute.value is None:
        reason = explain(absolute.reason.value) if absolute.reason else None
        return {**out, "status": absolute.status.value, "reason": reason}
    out["absolute"] = _text(absolute.value)
    if percent.value is not None:
        out["percent"] = format(percent.value.quantize(Decimal("0.01")), "f")
    else:
        out["status"] = percent.status.value
        out["reason"] = explain(percent.reason.value) if percent.reason else None
    return out


def _changes(rows: list[Row], view: str, unit: Unit, coverage: str) -> None:
    by_start = {r.start: r for r in rows}
    for i, r in enumerate(rows):
        if r.value is None or r.nature == "forecast":
            continue
        previous = rows[i - 1] if i > 0 else None
        basis = {"annual": "year_on_year", "quarterly": "quarter_on_quarter",
                 "monthly": "month_on_month"}[view]  # fmt: skip
        if previous is not None:
            r.changes.append(change(previous, r, basis, unit, coverage))
        if view in ("monthly", "quarterly"):
            year_ago = by_start.get(date(r.start.year - 1, r.start.month, 1))
            if year_ago is not None:
                r.changes.append(change(year_ago, r, "year_on_year", unit, coverage))


def _ytd_changes(rows: list[Row], unit: Unit, coverage: str) -> None:
    for r in rows:
        if r.value is None:
            continue
        match = next(
            (p for p in rows
             if p.start.year == r.start.year - 1 and p.start.month == r.start.month
             and p.end.month == r.end.month),
            None,
        )  # fmt: skip
        if match is not None:
            r.changes.append(change(match, r, "year_on_year", unit, coverage, complete=False))


def unit_of(code: str, dimension: str) -> Unit:
    return Unit(code, PhysicalDimension(dimension))


# ------------------------------------------------------------------ summary

TOTAL_REASONS: dict[str, dict[str, str]] = {
    "not_additive": {
        "en": "Not added up: this indicator is a level, a maximum, an average or a ratio, so "
        "its values over several periods have no meaningful sum.",
        "ar": "لم تُجمع القيم: هذا المؤشر مستوى أو قيمة قصوى أو متوسط أو نسبة، فلا معنى "
        "لمجموع قيمه عبر عدة فترات.",
    },
    "missing_periods": {
        "en": "Not added up: some periods in the range are not published, and a missing "
        "period is never counted as zero.",
        "ar": "لم تُجمع القيم: بعض فترات النطاق غير منشورة، والفترة المفقودة لا تُحسب صفراً أبداً.",
    },
    "inexact_value": {
        "en": "Not added up: a value in the range is published as 'more than' or 'less than'.",
        "ar": "لم تُجمع القيم: إحدى قيم النطاق منشورة بصيغة «أكثر من» أو «أقل من».",
    },
}


def _point(r: Row) -> dict[str, Any]:
    return {
        "period_start": r.start.isoformat(),
        "period_end": r.end.isoformat(),
        "value": _text(r.value),
        "value_operator": r.operator,
        "nature": r.nature,
    }


def summarize(rows: list[Row], value_type: str, unit: Unit, coverage: str) -> dict[str, Any]:
    """The rows of the selected range in a few figures, each taken from those same rows:
    how many periods are shown and how many have a value; the first and last values and the
    change between them (the platform's change functions); the highest and lowest exact
    values; and the total over the range, given only for a period total (a flow) and only
    when every period in the range is published with an exact value. A level, a maximum, an
    average or a ratio is never added up, and a missing period is never counted as zero.
    Forecast rows are left out."""
    shown = [r for r in rows if r.nature != "forecast"]
    valued = [r for r in shown if r.value is not None]
    out: dict[str, Any] = {
        "periods": len(shown),
        "with_value": len(valued),
        "missing": len(shown) - len(valued),
        "first": None,
        "last": None,
        "change": None,
        "highest": None,
        "lowest": None,
        "total": None,
        "total_reason": None,
    }
    if not valued:
        return out
    first, last = valued[0], valued[-1]
    out["first"], out["last"] = _point(first), _point(last)
    if first is not last:
        out["change"] = change(first, last, "first_to_last", unit, coverage)
    exact = [r for r in valued if not r.operator]
    if exact:
        out["highest"] = _point(max(exact, key=lambda r: r.value or Decimal(0)))
        out["lowest"] = _point(min(exact, key=lambda r: r.value or Decimal(0)))
    if value_type != "period_total":
        reason = "not_additive"
    elif out["missing"]:
        reason = "missing_periods"
    elif len(exact) != len(valued):
        reason = "inexact_value"
    else:
        reason = None
        out["total"] = _text(sum((r.value for r in valued if r.value is not None), Decimal(0)))
    out["total_reason"] = {"code": reason, **TOTAL_REASONS[reason]} if reason else None
    return out
