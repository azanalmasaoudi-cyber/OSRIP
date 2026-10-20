# ruff: noqa: E501 - the builders are mostly paired English/Arabic sentences kept on one line each
"""Deterministic studies from approved observations (booklet 3.25, 3.27, 3.29).

Each builder takes typed, allowlisted parameters, reads published observations through the
normal query service (the same data-mode and publication rules as the dashboards), does
all arithmetic with ``app.domain.calculations`` and returns one validated study result
(``app.domain.study``). Nothing here runs model-generated code, SQL or markup. Runs are
stored with their inputs and result checksum so a study can be reproduced and exported.

Guards that hold everywhere: missing values stay missing (never zero); units, period kinds
and coverage must match before a comparison; a partial year is never compared with a full
year; national totals are never divided among areas; before-and-after changes are never
presented as programme impact.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found, unprocessable
from app.domain import calculations as calc
from app.domain import study as schema
from app.domain.enums import DataMode, PhysicalDimension
from app.domain.explanations import explain
from app.domain.quantities import Measurement, Period
from app.domain.quantities import Unit as QUnit
from app.models import Area, DataQualityNote, Indicator, ReferencePack, StudyRun
from app.services import comparisons, forecasting, scenarios
from app.services.analysis import sections
from app.services.imports.csv_file import safe_cell
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.observations import ObservationQuery, SeriesOut, query_observations
from app.services.principal import Principal

PeriodKind = Literal["annual", "year_to_date", "quarterly", "monthly"]
PERCENT = {"code": "percent", "label_en": "percent", "label_ar": "نسبة مئوية"}
FRACTION = {"code": "fraction", "label_en": "fraction (0–1)", "label_ar": "كسر (0–1)"}
MONTHS_EN = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
MONTHS_AR = "يناير فبراير مارس أبريل مايو يونيو يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر".split()


def T(en: str, ar: str) -> dict[str, str]:  # noqa: N802 - short bilingual constructor
    return {"en": en, "ar": ar}


# ------------------------------------------------------------------ parameters (allowlisted)


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


_CODE = r"^[A-Z0-9_]{2,64}$"
_AREA = r"^[A-Z]{2}(-[A-Z0-9]{1,8}){0,3}$"


class TrendParams(_P):
    indicator: str = Field(pattern=_CODE)
    area: str = Field(default="OM", pattern=_AREA)
    period_kind: PeriodKind = "annual"
    flow: Literal["import", "domestic_export", "re_export"] | None = None
    commodity: str | None = Field(default=None, pattern=_CODE)


class GrowthParams(_P):
    indicator: str = Field(pattern=_CODE)
    area: str = Field(default="OM", pattern=_AREA)
    from_year: int = Field(ge=1990, le=2100)
    to_year: int = Field(ge=1990, le=2100)


class CompareParams(_P):
    indicator: str = Field(pattern=_CODE)
    period_kind: PeriodKind = "annual"
    period_start: date | None = None
    level: Literal["governorate", "wilayat"] = "governorate"
    flow: Literal["import", "domestic_export", "re_export"] | None = None


class SeasonalParams(_P):
    indicator: str = Field(pattern=_CODE)
    area: str = Field(default="OM", pattern=_AREA)


class CommodityParams(_P):
    commodity: str = Field(pattern=_CODE)
    year: int | None = Field(default=None, ge=1990, le=2100)


class QualityParams(_P):
    indicator: str = Field(pattern=_CODE)


class ScenarioParams(_P):
    indicator: str = Field(pattern=_CODE)
    area: str = Field(default="OM", pattern=_AREA)
    growth_pct: Decimal = Field(ge=Decimal("-50"), le=Decimal("50"))
    years: int = Field(ge=1, le=10)
    one_off_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("-50"), le=Decimal("50"))


class EligibilityParams(_P):
    indicator: str = Field(pattern=_CODE)
    area: str = Field(default="OM", pattern=_AREA)


class ProgrammeParams(_P):
    indicator: str = Field(pattern=_CODE)
    area: str = Field(default="OM", pattern=_AREA)
    objective: str = Field(min_length=3, max_length=300)
    baseline_year: int = Field(ge=1990, le=2100)
    target_value: Decimal
    target_year: int = Field(ge=1990, le=2100)


PARAMS: dict[str, type[_P]] = {
    "trend": TrendParams,
    "growth": GrowthParams,
    "compare_regions": CompareParams,
    "seasonal_profile": SeasonalParams,
    "import_dependence": CommodityParams,
    "partner_concentration": CommodityParams,
    "data_quality": QualityParams,
    "scenario": ScenarioParams,
    "forecast_eligibility": EligibilityParams,
    "programme_assessment": ProgrammeParams,
}
assert set(PARAMS) == set(schema.STUDY_KINDS)

CATALOG = {
    "trend": T("Indicator over time", "المؤشر عبر الزمن"),
    "growth": T("Compound growth between two years", "النمو المركب بين سنتين"),
    "compare_regions": T("Compare governorates", "مقارنة المحافظات"),
    "seasonal_profile": T("Seasonal profile (monthly)", "النمط الموسمي (شهري)"),
    "import_dependence": T("Commodity import dependence", "اعتماد السلعة على الواردات"),
    "partner_concentration": T("Trade partner concentration", "تركّز الشركاء التجاريين"),
    "data_quality": T("Data quality and coverage", "جودة البيانات وتغطيتها"),
    "scenario": T("What-if scenario", "سيناريو «ماذا لو»"),
    "forecast_eligibility": T("Can this series be forecast?", "هل يمكن التنبؤ بهذه السلسلة؟"),
    "programme_assessment": T("Programme assessment record", "سجل تقييم برنامج"),
}


# ------------------------------------------------------------------ shared helpers


def _floor(data_mode: DataMode) -> date | None:
    return STATISTICAL_SCOPE_START if data_mode is DataMode.VERIFIED_SOURCE else None


def _indicator(session: Session, code: str) -> Indicator:
    ind = session.scalar(select(Indicator).where(Indicator.code == code))
    if ind is None:
        raise unprocessable("unknown_indicator", "That indicator does not exist.")
    return ind


def _area(session: Session, code: str) -> Area:
    area = session.scalar(select(Area).where(Area.code == code))
    if area is None:
        raise unprocessable("unknown_area", "That area does not exist.")
    return area


def _series(
    session: Session,
    data_mode: DataMode,
    indicator: str,
    area: str,
    period_kind: str,
    flow: str | None = None,
    commodity: str | None = None,
) -> tuple[SeriesOut | None, dict[str, str] | None]:
    """Exactly one published series, or a reason (none, or several that must be chosen)."""
    found = [
        s
        for s in query_observations(
            session,
            ObservationQuery(
                data_mode,
                indicator=indicator,
                area=area,
                period_kind=period_kind,
                flow=flow,
                commodity=commodity,
                partner="total",
                period_from=_floor(data_mode),
            ),
            allow_mixed=True,
        )
        if s.meta["partner"] is None
    ]
    if not found:
        return None, T(
            "No published observations match this indicator, area and period kind.",
            "لا توجد مشاهدات منشورة تطابق هذا المؤشر والمنطقة ونوع الفترة.",
        )
    if len(found) > 1:
        return None, T(
            "More than one published series matches (different sources, flows or commodities); "
            "choose one so they are not mixed.",
            "تطابق أكثر من سلسلة منشورة (مصادر أو اتجاهات تجارة أو سلع مختلفة)؛ اختر واحدة كي لا "
            "تُخلط.",
        )
    return found[0], None


def _unit(s: SeriesOut) -> dict[str, str]:
    return {k: s.meta["unit"][k] for k in ("code", "label_en", "label_ar")}


def _measure(s: SeriesOut, o: dict[str, Any]) -> Measurement:
    return Measurement(
        None if o["value"] is None else Decimal(o["value"]),
        QUnit(s.meta["unit"]["code"], PhysicalDimension(s.meta["unit"]["dimension"])),
        Period(
            date.fromisoformat(o["period_start"]),
            date.fromisoformat(o["period_end"]),
            o["period_complete"],
        ),
        s.meta["area"]["code"],
        s.meta["commodity"]["code"] if s.meta["commodity"] else None,
    )


def _label(o: dict[str, Any], kind: str) -> str:
    start, end = o["period_start"], o["period_end"]
    if kind == "annual":
        return start[:4]
    if kind == "monthly":
        return start[:7]
    if kind == "year_to_date":
        return f"{start[:4]} Jan–{MONTHS_EN[int(end[5:7]) - 1]}"
    return f"{start}–{end}"


def _period_key(o: dict[str, Any], kind: str, back: bool = False) -> tuple[int, ...]:
    """A period's position, or (``back``) the position of the period just before it: the
    previous year (the same months for year-to-date), the previous month or quarter."""
    y, m = int(o["period_start"][:4]), int(o["period_start"][5:7])
    if kind in ("annual", "year_to_date"):
        tail = (int(o["period_end"][5:7]),) if kind == "year_to_date" else ()
        return (y - 1 if back else y, *tail)
    if back:
        m -= 1 if kind == "monthly" else 3
        if m < 1:
            y, m = y - 1, m + 12
    return (y, m)


def _ev(s: SeriesOut, o: dict[str, Any], n: int) -> dict[str, Any]:
    m = s.meta
    return {
        "id": f"S{n}",
        "indicator": m["indicator"]["code"],
        "area": m["area"]["code"],
        "period_start": o["period_start"],
        "period_end": o["period_end"],
        "value": o["value"],
        "unit": m["unit"]["code"],
        "source_title": m["source"]["dataset_title"],
        "source_url": m["source"]["url"],
        "dataset_version": m["dataset_version"]["label"],
        "record_ref": o.get("record_ref"),
    }


def _num(v: Decimal | None, places: int | None = None) -> str | None:
    if v is None:
        return None
    if places is not None:
        v = v.quantize(Decimal(1).scaleb(-places))
    return format(v.normalize() if places is None else v, "f")


def _name(s: SeriesOut) -> dict[str, str]:
    return T(s.meta["indicator"]["name_en"], s.meta["indicator"]["name_ar"])


def _area_name(s: SeriesOut) -> dict[str, str]:
    return T(s.meta["area"]["name_en"], s.meta["area"]["name_ar"])


def _limitation(s: SeriesOut) -> list[dict[str, str]]:
    lim = s.meta["indicator"]
    return [T(lim["limitation_en"], lim["limitation_ar"])] if lim.get("limitation_en") else []


def _base(
    kind: str, params: _P, data_mode: DataMode, title: dict[str, str], question: dict[str, str]
) -> dict[str, Any]:
    return {
        "schema": schema.SCHEMA,
        "kind": kind,
        "status": "ok",
        "title": title,
        "question": question,
        "params": params.model_dump(mode="json"),
        "data_mode": data_mode.value,
        "dataset_versions": [],
        "periods": {"from": None, "to": None, "kind": None},
        "method": T("", ""),
        "table": {"columns": [], "rows": []},
    }


def _unavailable(
    doc: dict[str, Any], reason: dict[str, str], method: dict[str, str]
) -> dict[str, Any]:
    return {**doc, "status": "not_available", "reason": reason, "method": method}


# ------------------------------------------------------------------ builders


def trend(session: Session, data_mode: DataMode, p: TrendParams) -> dict[str, Any]:
    ind, area = _indicator(session, p.indicator), _area(session, p.area)
    doc = _base(
        "trend", p, data_mode,
        T(f"{ind.name_en}: {area.name_en}", f"{ind.name_ar}: {area.name_ar}"),
        T(f"How has {ind.name_en.lower()} changed over time in {area.name_en}?",
          f"كيف تغيّر {ind.name_ar} عبر الزمن في {area.name_ar}؟"),
    )  # fmt: skip
    method = T(
        "Published observations of one series in order. Each change compares a period with the "
        "period immediately before it (the previous year, the same months of the previous year "
        "for year-to-date totals, or the previous month or quarter) using OSRIP's "
        "percentage-change function. When that period is missing, no change is shown: a gap is "
        "never bridged to an older value.",
        "مشاهدات منشورة لسلسلة واحدة مرتبة زمنياً. يقارن كل تغيّر فترةً بالفترة التي تسبقها مباشرة "
        "(السنة السابقة، أو الأشهر نفسها من السنة السابقة للمجاميع منذ بداية العام، أو الشهر أو الربع "
        "السابق) بدالة نسبة التغيّر في OSRIP. وإذا كانت تلك الفترة مفقودة لا يُعرض تغيّر، ولا تُوصل "
        "الفجوة بقيمة أقدم.",
    )
    s, reason = _series(session, data_mode, p.indicator, p.area, p.period_kind, p.flow, p.commodity)
    if s is None:
        return _unavailable(doc, reason, method)
    unit = _unit(s)
    rows, evidence, findings = [], [], []
    by_key = {_period_key(o, p.period_kind): o for o in s.observations}
    for n, o in enumerate(s.observations, start=1):
        evidence.append(_ev(s, o, n))
        change = None
        note = None
        previous = by_key.get(_period_key(o, p.period_kind, back=True))
        if n > 1 and previous is None:
            note = "previous_period_not_published"
        elif previous is not None and previous["value"] is None:
            note = "previous_period_missing"
        elif previous is not None and o["value"] is not None:
            r = calc.percentage_change(_measure(s, previous), _measure(s, o))
            change = _num(r.value, 3)
            if r.value is None and r.reason:
                note = r.reason.value
        rows.append(
            {
                "period": _label(o, p.period_kind),
                "value": o["value"],
                "status": "published" if o["value"] is not None else "missing_in_source",
                "change_pct": change,
                "note": note,
                "evidence": f"S{n}",
            }
        )
    with_values = [r for r in rows if r["value"] is not None]
    if not with_values:
        return _unavailable(
            doc,
            T("Every period of this series is missing in the source.",
              "جميع فترات هذه السلسلة مفقودة في المصدر."),
            method,
        )  # fmt: skip
    latest = with_values[-1]
    cards = [{"label": T("Latest published value", "آخر قيمة منشورة"), "value": latest["value"],
              "unit": unit, "period": latest["period"]}]  # fmt: skip
    findings.append(
        {
            "text": T(
                f"Latest published value: {latest['value']} {unit['label_en']} ({latest['period']}).",
                f"آخر قيمة منشورة: {latest['value']} {unit['label_ar']} ({latest['period']}).",
            ),
            "evidence": [latest["evidence"]],
        }
    )
    if latest["change_pct"] is not None:
        cards.append({"label": T("Change from the previous comparable period",
                                 "التغير عن الفترة السابقة المماثلة"),
                      "value": latest["change_pct"], "unit": PERCENT, "period": latest["period"],
                      "nature": "calculated"})  # fmt: skip
        findings.append(
            {
                "text": T(
                    f"Change from the previous comparable period: {latest['change_pct']}% (calculated).",
                    f"التغير عن الفترة السابقة المماثلة: {latest['change_pct']}٪ (محسوب).",
                ),
                "evidence": [latest["evidence"]],
            }
        )
    first, last = s.observations[0], s.observations[-1]
    return {
        **doc,
        "dataset_versions": [s.meta["dataset_version"]["label"]],
        "periods": {"from": first["period_start"], "to": last["period_end"], "kind": p.period_kind},
        "findings": findings,
        "cards": cards,
        "table": {
            "columns": [
                {"key": "period", "label": T("Period", "الفترة"), "kind": "period"},
                {"key": "value", "label": _name(s), "kind": "number", "unit": unit},
                {"key": "status", "label": T("Status", "الحالة"), "kind": "status"},
                {
                    "key": "change_pct",
                    "label": T("Change", "التغير"),
                    "kind": "number",
                    "unit": PERCENT,
                },
                {"key": "note", "label": T("Note", "ملاحظة"), "kind": "status"},
                {"key": "evidence", "label": T("Record", "السجل"), "kind": "text"},
            ],
            "rows": rows,
        },
        "charts": [
            {
                "type": "line",
                "title": _name(s),
                "x": "period",
                "series": [{"column": "value", "label": _name(s), "nature": "observed"}],
                "unit": unit,
            }
        ],
        "evidence": evidence,
        "method": method,
        "limitations": _limitation(s)
        + [
            T(
                "A change between periods does not show its cause.",
                "التغير بين فترتين لا يبيّن سببه.",
            )
        ],  # fmt: skip
        "next_questions": [
            T(
                "Did coverage, subscribers or definitions change between these periods?",
                "هل تغيّرت التغطية أو أعداد المشتركين أو التعريفات بين هذه الفترات؟",
            ),
        ],  # fmt: skip
    }


def growth(session: Session, data_mode: DataMode, p: GrowthParams) -> dict[str, Any]:
    ind, area = _indicator(session, p.indicator), _area(session, p.area)
    doc = _base(
        "growth", p, data_mode,
        T(f"Compound growth of {ind.name_en}, {p.from_year}–{p.to_year}",
          f"النمو المركب لـ{ind.name_ar}، {p.from_year}–{p.to_year}"),
        T(f"At what yearly rate did {ind.name_en.lower()} in {area.name_en} grow between "
          f"{p.from_year} and {p.to_year}?",
          f"بأي معدل سنوي نما {ind.name_ar} في {area.name_ar} بين {p.from_year} و{p.to_year}؟"),
    )  # fmt: skip
    method = T(
        "Compound annual growth = 100 × ((last ÷ first)^(1 ÷ years) − 1) between two complete "
        "years of the same series (OSRIP's function, which checks units, coverage and order).",
        "النمو السنوي المركب = 100 × ((الأخيرة ÷ الأولى)^(1 ÷ عدد السنوات) − 1) بين سنتين كاملتين "
        "من السلسلة نفسها (دالة OSRIP التي تتحقق من الوحدات والتغطية والترتيب).",
    )
    if p.to_year <= p.from_year:
        return _unavailable(doc, T("The end year must come after the start year.",
                                   "يجب أن تأتي سنة النهاية بعد سنة البداية."), method)  # fmt: skip
    s, reason = _series(session, data_mode, p.indicator, p.area, "annual")
    if s is None:
        return _unavailable(doc, reason, method)
    by_year = {int(o["period_start"][:4]): o for o in s.observations}
    a, b = by_year.get(p.from_year), by_year.get(p.to_year)
    if a is None or b is None:
        return _unavailable(
            doc,
            T(f"No complete published year for {p.from_year if a is None else p.to_year}.",
              f"لا توجد سنة كاملة منشورة لعام {p.from_year if a is None else p.to_year}."),
            method,
        )  # fmt: skip
    r = calc.compound_annual_growth(_measure(s, a), _measure(s, b), p.to_year - p.from_year)
    unit = _unit(s)
    rows = [
        {"period": str(p.from_year), "value": a["value"], "evidence": "S1"},
        {"period": str(p.to_year), "value": b["value"], "evidence": "S2"},
    ]
    if r.value is None:
        why = explain(r.reason.value) if r.reason else T("Not calculated.", "لم يُحسب.")
        return {
            **_unavailable(doc, T(why["en"], why["ar"]), method),
            "table": {"columns": [
                {"key": "period", "label": T("Year", "السنة"), "kind": "period"},
                {"key": "value", "label": _name(s), "kind": "number", "unit": unit},
                {"key": "evidence", "label": T("Record", "السجل"), "kind": "text"},
            ], "rows": rows},
            "evidence": [_ev(s, a, 1), _ev(s, b, 2)],
        }  # fmt: skip
    value = _num(r.value, 3)
    return {
        **doc,
        "dataset_versions": [s.meta["dataset_version"]["label"]],
        "periods": {"from": a["period_start"], "to": b["period_end"], "kind": "annual"},
        "cards": [{"label": T("Compound annual growth", "النمو السنوي المركب"), "value": value,
                   "unit": PERCENT, "period": f"{p.from_year}–{p.to_year}", "nature": "calculated"}],
        "findings": [{"text": T(
            f"{ind.name_en} grew at a compound {value}% a year from {p.from_year} to {p.to_year} (calculated).",
            f"نما {ind.name_ar} بمعدل مركب قدره {value}٪ سنوياً من {p.from_year} إلى {p.to_year} (محسوب)."),
            "evidence": ["S1", "S2"]}],
        "table": {"columns": [
            {"key": "period", "label": T("Year", "السنة"), "kind": "period"},
            {"key": "value", "label": _name(s), "kind": "number", "unit": unit},
            {"key": "evidence", "label": T("Record", "السجل"), "kind": "text"},
        ], "rows": rows},
        "charts": [{"type": "bar", "title": _name(s), "x": "period",
                    "series": [{"column": "value", "label": _name(s), "nature": "observed"}],
                    "unit": unit}],
        "evidence": [_ev(s, a, 1), _ev(s, b, 2)],
        "method": method,
        "limitations": _limitation(s) + [T(
            "A constant yearly rate summarises two points only; it hides year-to-year variation.",
            "المعدل السنوي الثابت يلخّص نقطتين فقط ويخفي التفاوت من سنة لأخرى.")],
    }  # fmt: skip


def compare_regions(session: Session, data_mode: DataMode, p: CompareParams) -> dict[str, Any]:
    ind = _indicator(session, p.indicator)
    doc = _base(
        "compare_regions", p, data_mode,
        T(f"{ind.name_en} by {p.level}", f"{ind.name_ar} حسب {'المحافظة' if p.level == 'governorate' else 'الولاية'}"),
        T(f"How does {ind.name_en.lower()} compare across {p.level}s?",
          f"كيف يقارَن {ind.name_ar} بين {'المحافظات' if p.level == 'governorate' else 'الولايات'}؟"),
    )  # fmt: skip
    method = T(
        "Each area's own published value for the same indicator, unit and period, ranked. Areas "
        "without a value are listed as such. National totals and combined reporting groups are "
        "shown apart and never divided among areas.",
        "القيمة المنشورة لكل منطقة للمؤشر والوحدة والفترة نفسها، مرتبةً. وتُذكر المناطق التي لا "
        "قيمة لها، ويُعرض المجموع الوطني والمجموعات المجمّعة منفصلةً دون تقسيم على المناطق.",
    )
    result = comparisons.compare_areas(
        session, data_mode, p.indicator, p.period_kind, p.period_start, p.level, p.flow
    )
    if result["status"] in ("no_data", "choose_flow"):
        reason = (
            T("No area at this level has a published value for this indicator.",
              "لا توجد قيمة منشورة لأي منطقة في هذا المستوى لهذا المؤشر.")
            if result["status"] == "no_data"
            else T("Choose a trade flow (import, domestic export or re-export).",
                   "اختر اتجاه التجارة (واردات أو صادرات محلية أو إعادة تصدير).")
        )  # fmt: skip
        return _unavailable(doc, reason, method)
    unit = result["unit"]
    unit = {k: unit[k] for k in ("code", "label_en", "label_ar")} if unit else None
    rows, evidence = [], []
    by_area = {s.meta["area"]["code"]: (s, o) for s, o in result["entries"]}
    n = 0
    ranked = sorted(
        result["rows"],
        key=lambda r: (r["value"] is None, -(Decimal(r["value"]) if r["value"] is not None else 0)),
    )
    for r in ranked:
        ref = None
        if r["area"] in by_area:
            n += 1
            evidence.append(_ev(*by_area[r["area"]], n))
            ref = f"S{n}"
        rows.append({"area": r["name"]["en"], "area_ar": r["name"]["ar"], "value": r["value"],
                     "status": r["status"], "evidence": ref})  # fmt: skip
    published = [r for r in rows if r["value"] is not None]
    cards, findings = [], []
    if published:
        top = published[0]
        findings.append({"text": T(f"Highest published value: {top['area']} ({top['value']} {unit['label_en'] if unit else ''}).",
                                   f"أعلى قيمة منشورة: {top['area_ar']} ({top['value']} {unit['label_ar'] if unit else ''})."),
                         "evidence": [top["evidence"]] if top["evidence"] else []})  # fmt: skip
    without = result.get("areas_without_value", 0)
    if without:
        findings.append({"text": T(f"{without} areas have no published value for this period.",
                                   f"{without} منطقة بلا قيمة منشورة لهذه الفترة.")})  # fmt: skip
    if result.get("national"):
        nat = result["national"]
        if "OM" in by_area:
            n += 1
            evidence.append(_ev(*by_area["OM"], n))
        cards.append({"label": T("National total (not divided)", "المجموع الوطني (غير مُقسَّم)"),
                      "value": nat["value"], "unit": unit,
                      "period": result.get("period_start")})  # fmt: skip
    limitations = [T("Areas without a value are not zero: they have no published figure.",
                     "المناطق التي بلا قيمة ليست صفراً: لا يوجد لها رقم منشور.")]  # fmt: skip
    for g in result.get("reporting_groups", []):
        limitations.append(T(f"{g['name']['en']}: {g['value']} (combined figure, not divided).",
                             f"{g['name']['ar']}: {g['value']} (رقم مجمّع، غير مُقسَّم)."))  # fmt: skip
    status = "ok" if result["status"] == "ok" else "not_comparable"
    return {
        **doc,
        "status": status if rows else "not_available",
        "reason": None if status == "ok" else T(
            "These values differ in unit or period length and cannot be compared directly.",
            "تختلف هذه القيم في الوحدة أو طول الفترة ولا يمكن مقارنتها مباشرة."),
        "dataset_versions": sorted({e["dataset_version"] for e in evidence}),
        "periods": {"from": result.get("period_start"), "to": result.get("period_end"), "kind": p.period_kind},
        "cards": cards,
        "findings": findings,
        "table": {"columns": [
            {"key": "area", "label": T("Area", "المنطقة"), "kind": "text"},
            {"key": "area_ar", "label": T("Area (Arabic)", "المنطقة"), "kind": "text"},
            {"key": "value", "label": T(ind.name_en, ind.name_ar), "kind": "number",
             "unit": unit or {"code": "-", "label_en": "-", "label_ar": "-"}},
            {"key": "status", "label": T("Status", "الحالة"), "kind": "status"},
            {"key": "evidence", "label": T("Record", "السجل"), "kind": "text"},
        ], "rows": rows},
        "charts": [{"type": "bar", "title": T(ind.name_en, ind.name_ar), "x": "area",
                    "series": [{"column": "value", "label": T(ind.name_en, ind.name_ar), "nature": "observed"}],
                    "unit": unit}] if published and status == "ok" else [],
        "evidence": evidence,
        "method": method,
        "limitations": limitations,
    }  # fmt: skip


def seasonal_profile(session: Session, data_mode: DataMode, p: SeasonalParams) -> dict[str, Any]:
    ind, area = _indicator(session, p.indicator), _area(session, p.area)
    doc = _base(
        "seasonal_profile", p, data_mode,
        T(f"Seasonal profile: {ind.name_en}", f"النمط الموسمي: {ind.name_ar}"),
        T(f"Which months have the highest {ind.name_en.lower()} in {area.name_en}?",
          f"ما الأشهر التي يكون فيها {ind.name_ar} أعلى في {area.name_ar}؟"),
    )  # fmt: skip
    method = T(
        "Published monthly observations arranged by year and month; no smoothing or estimation. "
        "Missing months stay empty.",
        "مشاهدات شهرية منشورة مرتبة حسب السنة والشهر، دون تنعيم أو تقدير. وتبقى الأشهر المفقودة فارغة.",
    )
    s, reason = _series(session, data_mode, p.indicator, p.area, "monthly")
    if s is None:
        return _unavailable(doc, T(
            "No monthly series is published for this indicator and area, so a seasonal profile "
            "cannot be shown (annual totals do not reveal seasons).",
            "لا توجد سلسلة شهرية منشورة لهذا المؤشر والمنطقة، لذا لا يمكن عرض النمط الموسمي "
            "(المجاميع السنوية لا تكشف المواسم)."), method)  # fmt: skip
    unit = _unit(s)
    rows, evidence = [], []
    for n, o in enumerate(s.observations, start=1):
        evidence.append(_ev(s, o, n))
        month = int(o["period_start"][5:7])
        rows.append({"year": o["period_start"][:4], "month": MONTHS_EN[month - 1],
                     "month_ar": MONTHS_AR[month - 1], "value": o["value"], "evidence": f"S{n}"})  # fmt: skip
    peak = max(
        (r for r in rows if r["value"] is not None), key=lambda r: Decimal(r["value"]), default=None
    )
    findings = []
    if peak:
        findings.append({"text": T(f"Highest published month: {peak['month']} {peak['year']} ({peak['value']} {unit['label_en']}).",
                                   f"أعلى شهر منشور: {peak['month_ar']} {peak['year']} ({peak['value']} {unit['label_ar']})."),
                         "evidence": [peak["evidence"]]})  # fmt: skip
    return {
        **doc,
        "dataset_versions": [s.meta["dataset_version"]["label"]],
        "periods": {"from": s.observations[0]["period_start"], "to": s.observations[-1]["period_end"], "kind": "monthly"},
        "findings": findings,
        "table": {"columns": [
            {"key": "year", "label": T("Year", "السنة"), "kind": "period"},
            {"key": "month", "label": T("Month", "الشهر"), "kind": "period"},
            {"key": "month_ar", "label": T("Month (Arabic)", "الشهر"), "kind": "text"},
            {"key": "value", "label": _name(s), "kind": "number", "unit": unit},
            {"key": "evidence", "label": T("Record", "السجل"), "kind": "text"},
        ], "rows": rows},
        "charts": [{"type": "heatmap", "title": _name(s), "x": "month", "y": "year", "value": "value", "unit": unit}],
        "evidence": evidence,
        "method": method,
        "limitations": _limitation(s) + [T(
            "Seasonal differences do not show causes such as weather or demand without matching evidence.",
            "الفروق الموسمية لا تبيّن أسباباً كالطقس أو الطلب دون أدلة مطابقة.")],
    }  # fmt: skip


def _frame_calcs(
    session: Session, data_mode: DataMode, p: CommodityParams, section: str
) -> list[dict[str, Any]]:
    f = sections.AnalysisFilter(
        data_mode=data_mode,
        commodity=p.commodity,
        period_from=date(p.year, 1, 1) if p.year else _floor(data_mode),
        period_to=date(p.year, 12, 31) if p.year else None,
        period_kind="annual",
    )
    builder = sections.food_security if section == "food" else sections.trade
    return builder(session, f)


def _latest_frame(calcs: list[dict[str, Any]], kinds: set[str]) -> list[dict[str, Any]]:
    """Calculations of the latest period frame that has any of ``kinds``."""
    matching = [c for c in calcs if c["kind"] in kinds]
    if not matching:
        return []
    frames = sorted({c["id"].split(":")[3] for c in matching if c["id"].count(":") >= 4})
    if not frames:
        return matching
    latest = frames[-1]
    return [c for c in calcs if c["id"].count(":") >= 4 and c["id"].split(":")[3] == latest]


def _inputs_evidence(c: dict[str, Any], start: int) -> list[dict[str, Any]]:
    out = []
    for i, inp in enumerate(c["inputs"], start=start):
        out.append({
            "id": f"S{i}", "indicator": inp["indicator"]["code"], "area": inp["area"]["code"],
            "period_start": inp["period_start"], "period_end": inp["period_end"], "value": inp["value"],
            "unit": inp["unit"]["code"], "source_title": inp["source_title"], "source_url": None,
            "dataset_version": inp["dataset_version"]["label"], "record_ref": inp.get("record_ref"),
        })  # fmt: skip
    return out


def import_dependence(session: Session, data_mode: DataMode, p: CommodityParams) -> dict[str, Any]:
    doc = _base(
        "import_dependence", p, data_mode,
        T(f"Import dependence: {p.commodity}", f"الاعتماد على الواردات: {p.commodity}"),
        T(f"How much of the apparent supply of {p.commodity} comes from imports?",
          f"ما نسبة المعروض الظاهري من {p.commodity} التي تأتي من الواردات؟"),
    )  # fmt: skip
    method = T(
        "Apparent availability = production + imports − exports − stock increase (stated "
        "assumption), for the same commodity, year and quantity unit; the contributions divide "
        "production and gross imports by it. OSRIP's functions refuse mixed units or periods.",
        "التوفر الظاهري = الإنتاج + الواردات − الصادرات − زيادة المخزون (افتراض معلن)، للسلعة والسنة "
        "ووحدة الكمية نفسها؛ وتُقسم عليه حصتا الإنتاج والواردات الإجمالية. ترفض دوال OSRIP خلط "
        "الوحدات أو الفترات.",
    )
    calcs = _latest_frame(
        _frame_calcs(session, data_mode, p, "food"),
        {"apparent_availability", "local_production_contribution", "gross_import_contribution"},
    )
    avail = next((c for c in calcs if c["kind"] == "apparent_availability"), None)
    if avail is None:
        return _unavailable(doc, T(
            "Matching production, import and export quantities are not all published for this "
            "commodity and year, so apparent availability cannot be calculated.",
            "لا تتوفر كميات الإنتاج والواردات والصادرات المتطابقة كلها لهذه السلعة والسنة، لذا لا "
            "يمكن حساب التوفر الظاهري."), method)  # fmt: skip
    unit = avail["result"]["unit"] or {"code": "-", "label_en": "-", "label_ar": "-"}
    unit = {k: unit[k] for k in ("code", "label_en", "label_ar")}
    rows = [{"component": i["role"], "quantity": i["value"], "period": i["period_start"][:4]}
            for i in avail["inputs"]]  # fmt: skip
    rows.append({"component": "apparent_availability", "quantity": avail["result"]["value"],
                 "period": avail["inputs"][0]["period_start"][:4] if avail["inputs"] else None})  # fmt: skip
    cards, findings = [], []
    for c in calcs:
        if c["kind"] in ("local_production_contribution", "gross_import_contribution"):
            cards.append({"label": c["title"], "value": c["result"]["value"], "unit": PERCENT,
                          "period": rows[-1]["period"], "nature": "calculated"})  # fmt: skip
            if c["result"]["value"] is not None:
                findings.append({"text": T(f"{c['title']['en']}: {_num(Decimal(c['result']['value']), 1)}% (calculated).",
                                           f"{c['title']['ar']}: {_num(Decimal(c['result']['value']), 1)}٪ (محسوب)."),
                                 "evidence": ["S1"]})  # fmt: skip
    evidence = _inputs_evidence(avail, 1)
    notes = [
        T(n["en"], n["ar"]) for n in avail.get("notes", []) if isinstance(n, dict) and "en" in n
    ]
    return {
        **doc,
        "dataset_versions": sorted({e["dataset_version"] for e in evidence}),
        "periods": {"from": rows[-1]["period"], "to": rows[-1]["period"], "kind": "annual"},
        "cards": cards,
        "findings": findings,
        "table": {"columns": [
            {"key": "component", "label": T("Component", "المكوّن"), "kind": "text"},
            {"key": "quantity", "label": T("Quantity", "الكمية"), "kind": "number", "unit": unit},
            {"key": "period", "label": T("Year", "السنة"), "kind": "period"},
        ], "rows": rows},
        "charts": [{"type": "bar", "title": T("Supply components", "مكوّنات المعروض"), "x": "component",
                    "series": [{"column": "quantity", "label": T("Quantity", "الكمية"), "nature": "observed"}],
                    "unit": unit}],
        "evidence": evidence,
        "method": method,
        "assumptions": notes or [T("Stock change is assumed to be zero unless a published stock change exists.",
                                   "يُفترض أن تغير المخزون صفر ما لم يُنشر تغير المخزون.")],
        "limitations": [T("Apparent availability is not household food security: it says nothing about access, "
                          "affordability or nutrition, and the two contributions do not add to 100%.",
                          "التوفر الظاهري ليس أمناً غذائياً للأسر: لا يقول شيئاً عن الوصول أو القدرة على الشراء "
                          "أو التغذية، ولا تجتمع الحصتان إلى 100٪.")],
    }  # fmt: skip


def partner_concentration(
    session: Session, data_mode: DataMode, p: CommodityParams
) -> dict[str, Any]:
    doc = _base(
        "partner_concentration", p, data_mode,
        T(f"Import partner concentration: {p.commodity}", f"تركّز شركاء الاستيراد: {p.commodity}"),
        T(f"How concentrated are the import partners for {p.commodity}?",
          f"ما مدى تركّز شركاء استيراد {p.commodity}؟"),
    )  # fmt: skip
    method = T(
        "Each partner's import quantity divided by the stated national import total (complete "
        "partner coverage required), the largest share, and the sum of squared shares.",
        "كمية واردات كل شريك مقسومة على إجمالي الواردات الوطني المعلن (مع اشتراط اكتمال تغطية "
        "الشركاء)، وأكبر حصة، ومجموع مربعات الحصص.",
    )
    calcs = _latest_frame(_frame_calcs(session, data_mode, p, "trade"), {"largest_partner_share"})
    share = next((c for c in calcs if c["kind"] == "largest_partner_share"), None)
    hhi = next((c for c in calcs if c["kind"] == "sum_of_squared_shares"), None)
    if share is None:
        return _unavailable(doc, T(
            "Partner import quantities with a stated national total are not published for this "
            "commodity and year.",
            "لا تُنشر كميات الواردات حسب الشريك مع إجمالي وطني معلن لهذه السلعة والسنة."), method)  # fmt: skip
    qty_unit = share["inputs"][0]["unit"]
    qty_unit = {k: qty_unit[k] for k in ("code", "label_en", "label_ar")}
    quantities = {i["partner"]: i["value"] for i in share["inputs"] if i["role"] == "partner"}
    rows = sorted(
        ({"partner": b["partner"], "quantity": quantities.get(b["partner"]), "share_pct": b["value"]}
         for b in share["breakdown"]),
        key=lambda r: -(Decimal(r["share_pct"]) if r["share_pct"] is not None else Decimal(-1)),
    )  # fmt: skip
    cards = [
        {
            "label": share["title"],
            "value": share["result"]["value"],
            "unit": PERCENT,
            "nature": "calculated",
        }
    ]
    if hhi:
        cards.append(
            {
                "label": hhi["title"],
                "value": hhi["result"]["value"],
                "unit": FRACTION,
                "nature": "calculated",
            }
        )
    findings = []
    if share["result"]["value"] is not None and rows:
        findings.append({"text": T(
            f"The largest partner ({rows[0]['partner']}) supplies {_num(Decimal(share['result']['value']), 1)}% of import quantity (calculated).",
            f"يورّد أكبر شريك ({rows[0]['partner']}) {_num(Decimal(share['result']['value']), 1)}٪ من كمية الواردات (محسوب)."),
            "evidence": ["S1"]})  # fmt: skip
    evidence = _inputs_evidence(share, 1)
    synthetic = data_mode is DataMode.SYNTHETIC
    return {
        **doc,
        "dataset_versions": sorted({e["dataset_version"] for e in evidence}),
        "periods": {"from": share["inputs"][0]["period_start"], "to": share["inputs"][0]["period_end"], "kind": "annual"},
        "cards": cards,
        "findings": findings,
        "table": {"columns": [
            {"key": "partner", "label": T("Partner", "الشريك"), "kind": "text"},
            {"key": "quantity", "label": T("Import quantity", "كمية الواردات"), "kind": "number", "unit": qty_unit},
            {"key": "share_pct", "label": T("Share of total", "الحصة من الإجمالي"), "kind": "number", "unit": PERCENT},
        ], "rows": rows},
        "charts": [{"type": "bar", "title": T("Share of import quantity", "الحصة من كمية الواردات"), "x": "partner",
                    "series": [{"column": "share_pct", "label": T("Share", "الحصة"), "nature": "calculated"}],
                    "unit": PERCENT}],
        "evidence": evidence,
        "method": method,
        "limitations": [T("Concentration identifies an exposure to review; it does not estimate the probability "
                          "of a supply interruption.",
                          "التركّز يبيّن تعرّضاً يستحق المراجعة، ولا يقدّر احتمال انقطاع الإمداد.")]
        + ([T("Partner names are fictional demonstration codes, not real countries.",
              "أسماء الشركاء رموز تجريبية خيالية وليست دولاً حقيقية.")] if synthetic else []),
    }  # fmt: skip


def data_quality(session: Session, data_mode: DataMode, p: QualityParams) -> dict[str, Any]:
    ind = _indicator(session, p.indicator)
    doc = _base(
        "data_quality", p, data_mode,
        T(f"Data quality: {ind.name_en}", f"جودة البيانات: {ind.name_ar}"),
        T(f"How complete and consistent are the published records for {ind.name_en.lower()}?",
          f"ما مدى اكتمال واتساق السجلات المنشورة لـ{ind.name_ar}؟"),
    )  # fmt: skip
    method = T(
        "Counts of published and missing values per published series (area, period kind, flow), "
        "first and last periods, revision labels, and documented data-quality notes.",
        "أعداد القيم المنشورة والمفقودة لكل سلسلة منشورة (المنطقة ونوع الفترة واتجاه التجارة)، "
        "وأول وآخر فترة، ووسوم المراجعة، وملاحظات جودة البيانات الموثقة.",
    )
    series = query_observations(
        session, ObservationQuery(data_mode, indicator=p.indicator, period_from=_floor(data_mode)),
        allow_mixed=True,
    )  # fmt: skip
    rows = []
    for s in series:
        obs = s.observations
        rows.append({
            "area": s.meta["area"]["name_en"],
            "period_kind": s.meta.get("period_kind", s.meta["frequency"]),
            "flow": s.meta["flow"],
            "partner": s.meta["partner"]["code"] if s.meta["partner"] else None,
            "first": obs[0]["period_start"] if obs else None,
            "last": obs[-1]["period_end"] if obs else None,
            "published": str(sum(1 for o in obs if o["value"] is not None)),
            "missing": str(sum(1 for o in obs if o["value"] is None)),
            "revised": str(sum(1 for o in obs if o.get("revision_status"))),
            "source": s.meta["source"]["dataset_title"],
        })  # fmt: skip
    if not rows:
        return _unavailable(doc, T("No published series for this indicator in this data mode.",
                                   "لا توجد سلاسل منشورة لهذا المؤشر في وضع البيانات هذا."), method)  # fmt: skip
    count = {"code": "count", "label_en": "count", "label_ar": "عدد"}
    pack = session.scalar(select(ReferencePack).order_by(ReferencePack.research_cutoff.desc()))
    notes = []
    if pack is not None and data_mode is DataMode.VERIFIED_SOURCE:
        for n in session.scalars(select(DataQualityNote).where(DataQualityNote.pack_id == pack.id)):
            if ind.section.value in (n.sections or []):
                notes.append(T(f"{n.title_en}: {n.body_en}", f"{n.title_ar}: {n.body_ar}"))
    missing = sum(int(r["missing"]) for r in rows)
    return {
        **doc,
        "periods": {"from": min((r["first"] for r in rows if r["first"]), default=None),
                    "to": max((r["last"] for r in rows if r["last"]), default=None), "kind": None},
        "cards": [{"label": T("Published series", "السلاسل المنشورة"), "value": str(len(rows)), "unit": count},
                  {"label": T("Missing values", "القيم المفقودة"), "value": str(missing), "unit": count}],
        "findings": [{"text": T(f"{len(rows)} published series; {missing} values are missing in the source (kept as missing).",
                                f"{len(rows)} سلسلة منشورة؛ و{missing} قيمة مفقودة في المصدر (تبقى مفقودة).")}],
        "table": {"columns": [
            {"key": "area", "label": T("Area", "المنطقة"), "kind": "text"},
            {"key": "period_kind", "label": T("Period kind", "نوع الفترة"), "kind": "text"},
            {"key": "flow", "label": T("Flow", "الاتجاه"), "kind": "text"},
            {"key": "partner", "label": T("Partner", "الشريك"), "kind": "text"},
            {"key": "first", "label": T("First period", "أول فترة"), "kind": "period"},
            {"key": "last", "label": T("Last period", "آخر فترة"), "kind": "period"},
            {"key": "published", "label": T("Published values", "قيم منشورة"), "kind": "number", "unit": count},
            {"key": "missing", "label": T("Missing values", "قيم مفقودة"), "kind": "number", "unit": count},
            {"key": "revised", "label": T("Revised or provisional", "منقحة أو أولية"), "kind": "number", "unit": count},
            {"key": "source", "label": T("Source", "المصدر"), "kind": "text"},
        ], "rows": rows},
        "method": method,
        "limitations": notes or [T("No documented data-quality note for this section.",
                                   "لا توجد ملاحظة موثقة عن جودة البيانات لهذا القسم.")],
    }  # fmt: skip


def scenario(session: Session, data_mode: DataMode, p: ScenarioParams) -> dict[str, Any]:
    ind = _indicator(session, p.indicator)
    _area(session, p.area)  # refuses an unknown area code
    doc = _base(
        "scenario", p, data_mode,
        T(f"Scenario: {ind.name_en} at {p.growth_pct}% a year", f"سيناريو: {ind.name_ar} بمعدل {p.growth_pct}٪ سنوياً"),
        T(f"What would {ind.name_en.lower()} be if it changed by {p.growth_pct}% a year for {p.years} years?",
          f"كم سيكون {ind.name_ar} لو تغيّر بنسبة {p.growth_pct}٪ سنوياً لمدة {p.years} سنوات؟"),
    )  # fmt: skip
    method = T(
        "Hypothetical arithmetic from the latest complete published year: value(k) = base × "
        "(1 + one-off change) × (1 + yearly change)^k. Not a forecast: no model, no error measure.",
        "حساب افتراضي من آخر سنة كاملة منشورة: القيمة(k) = الأساس × (1 + التغير لمرة واحدة) × "
        "(1 + التغير السنوي)^k. ليس تنبؤاً: لا نموذج ولا مقياس خطأ.",
    )
    match = next(
        (s for s in scenarios.series(session, data_mode)
         if s["indicator"]["code"] == p.indicator and s["area"]["code"] == p.area
         and s["partner"] is None and s["commodity"] is None),
        None,
    )  # fmt: skip
    if match is None:
        return _unavailable(doc, T("No complete published year is available to start this scenario from.",
                                   "لا توجد سنة كاملة منشورة يبدأ منها هذا السيناريو."), method)  # fmt: skip
    proj = scenarios.projection(
        session, data_mode, match["series_id"], p.growth_pct, p.years, p.one_off_pct
    )
    unit = {k: proj["series"]["unit"][k] for k in ("code", "label_en", "label_ar")}
    base = proj["base"]
    rows = [{"year": base["period_start"][:4], "observed": base["value"], "scenario": None}]
    rows += [
        {"year": str(pt["year"]), "observed": None, "scenario": pt["value"]}
        for pt in proj["points"]
    ]
    ev = {"id": "S1", "indicator": p.indicator, "area": p.area, "period_start": base["period_start"],
          "period_end": base["period_end"], "value": base["value"], "unit": unit["code"],
          "source_title": base["source"]["title"], "source_url": base["source"]["url"],
          "dataset_version": base["dataset_version"], "record_ref": base.get("record_ref")}  # fmt: skip
    last = proj["points"][-1]
    return {
        **doc,
        "dataset_versions": [base["dataset_version"]],
        "periods": {"from": base["period_start"], "to": f"{last['year']}-12-31", "kind": "annual"},
        "cards": [{"label": T("Published base", "الأساس المنشور"), "value": base["value"], "unit": unit,
                   "period": base["period_start"][:4]},
                  {"label": T("Scenario result (hypothetical)", "نتيجة السيناريو (افتراضية)"),
                   "value": last["value"], "unit": unit, "period": str(last["year"]), "nature": "scenario"}],
        "findings": [{"text": T(f"Under the stated assumption, the value would be {last['value']} {unit['label_en']} in {last['year']}. This is hypothetical, not a forecast.",
                                f"وفق الافتراض المعلن ستكون القيمة {last['value']} {unit['label_ar']} في {last['year']}. هذا افتراضي وليس تنبؤاً."),
                      "evidence": ["S1"]}],
        "table": {"columns": [
            {"key": "year", "label": T("Year", "السنة"), "kind": "period"},
            {"key": "observed", "label": T("Published (observed)", "منشور (مرصود)"), "kind": "number", "unit": unit},
            {"key": "scenario", "label": T("Scenario (hypothetical)", "سيناريو (افتراضي)"), "kind": "number", "unit": unit},
        ], "rows": rows},
        "charts": [{"type": "line", "title": T(ind.name_en, ind.name_ar), "x": "year", "unit": unit, "series": [
            {"column": "observed", "label": T("Published", "منشور"), "nature": "observed"},
            {"column": "scenario", "label": T("Scenario", "سيناريو"), "nature": "scenario"}]}],
        "evidence": [ev],
        "method": method,
        "assumptions": [T(f"Yearly change {p.growth_pct}% for {p.years} years; one-off change {p.one_off_pct}%.",
                          f"تغير سنوي {p.growth_pct}٪ لمدة {p.years} سنوات؛ وتغير لمرة واحدة {p.one_off_pct}٪.")],
        "limitations": [T("A scenario shows the arithmetic of an assumption, not what will happen or why.",
                          "السيناريو يبيّن حساب افتراضٍ ما، لا ما سيحدث ولا سببه.")],
    }  # fmt: skip


def forecast_eligibility(
    session: Session, data_mode: DataMode, p: EligibilityParams
) -> dict[str, Any]:
    ind, area = _indicator(session, p.indicator), _area(session, p.area)
    doc = _base(
        "forecast_eligibility", p, data_mode,
        T(f"Forecast eligibility: {ind.name_en}", f"أهلية التنبؤ: {ind.name_ar}"),
        T(f"Is there enough history to forecast {ind.name_en.lower()} in {area.name_en}?",
          f"هل يوجد تاريخ كافٍ للتنبؤ بـ{ind.name_ar} في {area.name_ar}؟"),
    )  # fmt: skip
    report = forecasting.eligibility(session, data_mode)
    method = T(
        report["method"]["splits"]["en"] + " " + report["method"]["metrics"]["en"],
        report["method"]["splits"]["ar"] + " " + report["method"]["metrics"]["ar"],
    )
    rows_src = [r for r in report["series"] if r["indicator"]["code"] == p.indicator
                and r["area"]["code"] == p.area and r["partner"] is None and r["commodity"] is None]  # fmt: skip
    if not rows_src:
        return _unavailable(doc, T("No regular (annual, quarterly or monthly) published series matches.",
                                   "لا تطابق أي سلسلة منشورة منتظمة (سنوية أو ربعية أو شهرية)."), method)  # fmt: skip
    count = {"code": "count", "label_en": "count", "label_ar": "عدد"}
    rows, findings = [], []
    for r in rows_src:
        reasons = (
            "; ".join(x.get("en", "") for x in r["reasons"])
            or "Meets the history and quality requirements."
        )
        rows.append({"frequency": r["frequency"], "usable": str(r["usable_observations"]),
                     "first": r["first_period"], "last": r["last_period"],
                     "eligible": "eligible" if r["eligible"] else "withheld", "reason": reasons})  # fmt: skip
        findings.append({"text": T(
            ("Eligible for evaluation against the baseline." if r["eligible"] else
             f"Forecast withheld: {reasons}"),
            ("مؤهلة للتقييم مقابل النموذج الأساسي." if r["eligible"] else
             "يُحجب التنبؤ: " + ("؛ ".join(x.get("ar", "") for x in r["reasons"]) or "")))})  # fmt: skip
    return {
        **doc,
        "periods": {"from": rows[0]["first"], "to": rows[0]["last"], "kind": rows[0]["frequency"]},
        "findings": findings,
        "table": {"columns": [
            {"key": "frequency", "label": T("Frequency", "التكرار"), "kind": "text"},
            {"key": "usable", "label": T("Usable observations", "مشاهدات صالحة"), "kind": "number", "unit": count},
            {"key": "first", "label": T("First period", "أول فترة"), "kind": "period"},
            {"key": "last", "label": T("Last period", "آخر فترة"), "kind": "period"},
            {"key": "eligible", "label": T("Decision", "القرار"), "kind": "status"},
            {"key": "reason", "label": T("Reason", "السبب"), "kind": "text"},
        ], "rows": rows},
        "method": method,
        "limitations": [T("Four or five annual observations do not support a complex model; a forecast is shown only "
                          "when it beats a simple baseline on held-out periods.",
                          "أربع أو خمس مشاهدات سنوية لا تكفي لنموذج معقد؛ ولا يُعرض التنبؤ إلا إذا تفوّق على "
                          "نموذج أساسي بسيط في الفترات المحجوزة للاختبار.")],
        "forecast_evaluation": {"policies": report["method"]["policies"], "method_version": report["method"]["version"]},
    }  # fmt: skip


def programme_assessment(
    session: Session, data_mode: DataMode, p: ProgrammeParams
) -> dict[str, Any]:
    ind = _indicator(session, p.indicator)
    _area(session, p.area)  # refuses an unknown area code
    doc = _base(
        "programme_assessment", p, data_mode,
        T(f"Programme record: {p.objective}", f"سجل برنامج: {p.objective}"),
        T(f"Where does {ind.name_en.lower()} stand against the programme target?",
          f"أين يقف {ind.name_ar} مقارنةً بهدف البرنامج؟"),
    )  # fmt: skip
    method = T(
        "Records the stated objective, the published baseline year, the latest published value and "
        "the stated target, with the remaining gap (target − latest, calculated). It does not "
        "estimate the programme's effect.",
        "يسجّل الهدف المعلن وسنة الأساس المنشورة وآخر قيمة منشورة والهدف المعلن، مع الفجوة المتبقية "
        "(الهدف − الأحدث، محسوبة). ولا يقدّر أثر البرنامج.",
    )
    s, reason = _series(session, data_mode, p.indicator, p.area, "annual")
    if s is None:
        return _unavailable(doc, reason, method)
    by_year = {int(o["period_start"][:4]): o for o in s.observations if o["value"] is not None}
    base_o = by_year.get(p.baseline_year)
    if base_o is None:
        return _unavailable(doc, T(f"No published value for the baseline year {p.baseline_year}.",
                                   f"لا توجد قيمة منشورة لسنة الأساس {p.baseline_year}."), method)  # fmt: skip
    if p.target_year <= p.baseline_year:
        return _unavailable(doc, T("The target year must come after the baseline year.",
                                   "يجب أن تأتي سنة الهدف بعد سنة الأساس."), method)  # fmt: skip
    latest_o = by_year[max(by_year)]
    unit = _unit(s)
    latest_m = _measure(s, latest_o)
    target = Measurement(
        p.target_value,
        latest_m.unit,
        Period(date(p.target_year, 1, 1), date(p.target_year, 12, 31), True),
        latest_m.coverage,
    )
    # The gap is only meaningful while the target year is still ahead of the latest value.
    gap = calc.absolute_change(latest_m, target)
    change = (
        calc.percentage_change(_measure(s, base_o), _measure(s, latest_o))
        if latest_o is not base_o
        else None
    )
    rows = [
        {"role": "baseline", "period": str(p.baseline_year), "value": base_o["value"], "nature": "observed"},
        {"role": "latest", "period": latest_o["period_start"][:4], "value": latest_o["value"], "nature": "observed"},
        {"role": "target", "period": str(p.target_year), "value": _num(p.target_value), "nature": "stated target"},
        {"role": "gap_to_target", "period": f"{latest_o['period_start'][:4]}→{p.target_year}",
         "value": _num(gap.value), "nature": "calculated"},
    ]  # fmt: skip
    findings = [{"text": T(f"Latest published value {latest_o['value']} {unit['label_en']}; stated target {_num(p.target_value)} by {p.target_year}.",
                           f"آخر قيمة منشورة {latest_o['value']} {unit['label_ar']}؛ والهدف المعلن {_num(p.target_value)} بحلول {p.target_year}."),
                 "evidence": ["S2"]}]  # fmt: skip
    if gap.value is None:
        findings.append({"text": T(
            f"The target year {p.target_year} is not after the latest published year, so no remaining gap is "
            f"calculated; compare the published value for {p.target_year} with the target instead.",
            f"سنة الهدف {p.target_year} ليست بعد آخر سنة منشورة، لذا لا تُحسب فجوة متبقية؛ قارن القيمة المنشورة "
            f"لعام {p.target_year} بالهدف بدلاً من ذلك.")})  # fmt: skip
    if change is not None and change.value is not None:
        findings.append({"text": T(f"Change since the baseline: {_num(change.value, 2)}% (calculated). This alone does not show the programme's effect.",
                                   f"التغير منذ سنة الأساس: {_num(change.value, 2)}٪ (محسوب). وهذا وحده لا يبيّن أثر البرنامج."),
                         "evidence": ["S1", "S2"]})  # fmt: skip
    return {
        **doc,
        "dataset_versions": [s.meta["dataset_version"]["label"]],
        "periods": {"from": base_o["period_start"], "to": latest_o["period_end"], "kind": "annual"},
        "findings": findings,
        "cards": [{"label": T("Gap to target", "الفجوة عن الهدف"), "value": _num(gap.value), "unit": unit,
                   "nature": "calculated"}],
        "table": {"columns": [
            {"key": "role", "label": T("Item", "البند"), "kind": "text"},
            {"key": "period", "label": T("Period", "الفترة"), "kind": "period"},
            {"key": "value", "label": _name(s), "kind": "number", "unit": unit},
            {"key": "nature", "label": T("Kind", "النوع"), "kind": "status"},
        ], "rows": rows},
        "evidence": [_ev(s, base_o, 1), _ev(s, latest_o, 2)],
        "method": method,
        "assumptions": [T(f"Objective as stated by the user: {p.objective}", f"الهدف كما ذكره المستخدم: {p.objective}"),
                        T(f"Target {_num(p.target_value)} {unit['label_en']} by {p.target_year} (stated, not published).",
                          f"الهدف {_num(p.target_value)} {unit['label_ar']} بحلول {p.target_year} (معلن، غير منشور).")],
        "limitations": [T("Before-and-after comparison does not establish programme impact: other factors, coverage "
                          "changes and revisions may explain the change.",
                          "المقارنة قبل وبعد لا تثبت أثر البرنامج: قد تفسّر التغيرَ عواملُ أخرى أو تغيّرات في التغطية "
                          "أو مراجعات للبيانات.")],
        "next_questions": [T("What did the programme deliver (activities, spending, dates), and what would have "
                             "happened without it?",
                             "ما الذي نفّذه البرنامج (أنشطة وإنفاق وتواريخ)، وماذا كان سيحدث بدونه؟"),
                           T("Is there a comparison area or group not covered by the programme?",
                             "هل توجد منطقة أو فئة للمقارنة لم يشملها البرنامج؟")],
    }  # fmt: skip


BUILDERS = {
    "trend": trend,
    "growth": growth,
    "compare_regions": compare_regions,
    "seasonal_profile": seasonal_profile,
    "import_dependence": import_dependence,
    "partner_concentration": partner_concentration,
    "data_quality": data_quality,
    "scenario": scenario,
    "forecast_eligibility": forecast_eligibility,
    "programme_assessment": programme_assessment,
}


# ------------------------------------------------------------------ run, store, read, export


def build(
    session: Session, kind: str, params: dict[str, Any], data_mode: DataMode
) -> dict[str, Any]:
    """Validate the parameters, run the builder and validate the result (no storage)."""
    if kind not in BUILDERS:
        raise unprocessable("unknown_study", f"Choose one of: {', '.join(BUILDERS)}.")
    try:
        typed = PARAMS[kind].model_validate(params)
    except ValueError as exc:
        raise unprocessable("invalid_study_parameters", "The study parameters are not valid.",
                            {"errors": str(exc)[:500]}) from exc  # fmt: skip
    doc = BUILDERS[kind](session, data_mode, typed)  # type: ignore[operator]
    return schema.validate(doc)


def checksum(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def store(
    session: Session,
    document: dict[str, Any],
    *,
    study_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    guest_session_id: uuid.UUID | None = None,
    message_id: int | None = None,
) -> StudyRun:
    row = StudyRun(
        id=study_id or uuid.uuid4(),
        kind=document["kind"],
        schema_version=document["schema"],
        params=document["params"],
        data_mode=document["data_mode"],
        dataset_versions=document["dataset_versions"],
        result=document,
        result_sha256=checksum(document),
        user_id=user_id,
        guest_session_id=guest_session_id,
        message_id=message_id,
    )
    session.add(row)
    session.flush()
    return row


def run(
    session: Session,
    kind: str,
    params: dict[str, Any],
    data_mode: DataMode,
    principal: Principal | None,
) -> dict[str, Any]:
    document = build(session, kind, params, data_mode)
    row = store(
        session,
        document,
        user_id=principal.user_id if principal and principal.is_authenticated else None,
    )
    return out(row)


def out(row: StudyRun) -> dict[str, Any]:
    return {"id": str(row.id), "created_at": row.created_at.isoformat() if row.created_at else None,
            "sha256": row.result_sha256, "study": row.result}  # fmt: skip


BALANCE_KIND = "supply_balance"  # stored shortage and surplus analyses (osrip.balance/1)


def get(session: Session, study_id: uuid.UUID) -> StudyRun:
    row = session.get(StudyRun, study_id)
    # A shortage and surplus analysis has its own document and routes (/analysis/balance).
    if row is None or row.kind == BALANCE_KIND:
        raise not_found("study")
    return row


def list_mine(session: Session, principal: Principal) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(StudyRun)
        .where(StudyRun.user_id == principal.user_id, StudyRun.kind != BALANCE_KIND)
        .order_by(StudyRun.created_at.desc())
        .limit(100)
    )
    return [{"id": str(r.id), "kind": r.kind, "title": r.result["title"], "status": r.result["status"],
             "data_mode": r.data_mode, "created_at": r.created_at.isoformat()} for r in rows]  # fmt: skip


def delete(session: Session, principal: Principal, study_id: uuid.UUID) -> None:
    row = get(session, study_id)
    if row.user_id is None or row.user_id != principal.user_id:
        raise not_found("study")
    session.delete(row)


def reproduce(session: Session, study_id: uuid.UUID) -> dict[str, Any]:
    """Rebuild a stored study from its parameters and say whether the result is identical
    (it differs when a newer dataset version has been published since)."""
    row = get(session, study_id)
    fresh = build(session, row.kind, row.params, DataMode(row.data_mode))
    return {"id": str(row.id), "identical": checksum(fresh) == row.result_sha256,
            "stored_versions": row.dataset_versions, "current_versions": fresh["dataset_versions"]}  # fmt: skip


def export_csv(document: dict[str, Any], language: str) -> str:
    """The study table exactly as shown, with its provenance as comment lines."""
    lang = "ar" if language == "ar" else "en"
    buf = io.StringIO()
    buf.write(f"# {document['title'][lang]}\n")
    buf.write(
        f"# data_mode={document['data_mode']} dataset_versions={'|'.join(document['dataset_versions'])}\n"
    )
    buf.write(f"# method: {document['method'][lang]}\n")
    if document["data_mode"] == "synthetic":
        buf.write("# SYNTHETIC demonstration data: not Omani statistics\n")
    for a in document.get("assumptions", []):
        buf.write(f"# assumption: {a[lang]}\n")
    writer = csv.writer(buf, lineterminator="\n")
    cols = document["table"]["columns"]
    writer.writerow(
        [
            safe_cell(
                c["label"][lang] + (f" ({c['unit'][f'label_{lang}']})" if c.get("unit") else "")
            )
            for c in cols
        ]
    )
    for row in document["table"]["rows"]:
        # Numeric cells hold validated decimal strings (negative values stay numbers); text
        # cells are neutralised against spreadsheet formula injection.
        writer.writerow(
            [
                ""
                if row.get(c["key"]) is None
                else row[c["key"]]
                if c["kind"] == "number"
                else safe_cell(str(row[c["key"]]))
                for c in cols
            ]
        )
    return buf.getvalue()
