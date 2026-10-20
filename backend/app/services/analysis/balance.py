# ruff: noqa: E501 - bilingual sentences are kept on one line each, as in services/studies.py
"""Shortage and surplus analysis: supply against demand per sector, from published data only.

A shortage or surplus is stated only when a supply measure and a demand measure with the same
period, geography and unit are published and the source's own definitions allow comparing them.
Otherwise the balance is "not determinable" and the analysis names the missing information.

What each sector can support with the data OSRIP holds:

* Electricity: shortages happen at the hour of peak demand (MW), which is not published; the
  source states that distribution and consumption (GWh) are defined differently, so their
  difference is shown side by side and never called a surplus, a loss or a shortage.
* Water: the source states that production minus distribution or consumption is neither
  leakage nor a shortage; the demand requirement, storage and quality are not published.
* Food security: a published self-sufficiency ratio (production as a percent of domestic
  consumption) gives the production surplus or shortfall in percentage points; with matching
  quantities (synthetic demonstration data), production is compared with apparent
  availability in tonnes.
* Trade: exports minus imports by value (trade surplus or deficit) for the national total and
  for product groups published on both sides.

All arithmetic goes through ``app.domain.calculations``. Missing values stay missing. Two
published sources reporting the same series are never chosen between silently. Costs are
never estimated. Recommendations are generated from fixed, documented rules (decision
support, not guaranteed outcomes) and every number in them comes from the calculation.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import balance as schema
from app.domain import calculations as calc
from app.domain.enums import DataMode, PhysicalDimension
from app.domain.quantities import Measurement, Period
from app.domain.quantities import Unit as QUnit
from app.domain.results import CalcResult, CalcStatus
from app.models import ReferencePackSource
from app.services import forecasting
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.observations import ObservationQuery, SeriesOut, query_observations

CONTEXT_FLOOR = date(2022, 1, 1)  # statistics before this are context only, and labelled
PERCENT = {"code": "percent", "label_en": "percent", "label_ar": "نسبة مئوية"}
POINTS = {"code": "percentage_points", "label_en": "percentage points", "label_ar": "نقطة مئوية"}
HUNDRED = Decimal(100)


def T(en: str, ar: str) -> dict[str, str]:  # noqa: N802 - short bilingual constructor
    return {"en": en, "ar": ar}


SECTOR_NAME = {
    "electricity": T("Electricity", "الكهرباء"),
    "water": T("Water", "المياه"),
    "food_security": T("Food security", "الأمن الغذائي"),
    "trade": T("Trade", "التجارة"),
}


# ------------------------------------------------------------------ parameters (allowlisted)


class BalanceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector: schema.Sector
    area: str = Field(default="OM", pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,8}){0,3}$")
    period_kind: Literal["annual", "year_to_date"] = "annual"
    # A scenario only from assumptions the person states (all three, or none).
    supply_growth_pct: Decimal | None = Field(default=None, ge=Decimal("-50"), le=Decimal("50"))
    demand_growth_pct: Decimal | None = Field(default=None, ge=Decimal("-50"), le=Decimal("50"))
    years: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def _scenario_complete(self) -> BalanceParams:
        given = [
            self.supply_growth_pct is not None,
            self.demand_growth_pct is not None,
            self.years is not None,
        ]
        if any(given) and not all(given):
            raise ValueError("a scenario needs supply_growth_pct, demand_growth_pct and years")
        return self

    @property
    def scenario(self) -> bool:
        return self.years is not None


# ------------------------------------------------------------------ formatting helpers


def _num(value: Decimal | None) -> str | None:
    """Unrounded decimal string (tables and the stored result keep full precision)."""
    return (
        None
        if value is None
        else format(value.normalize() if value == value.to_integral() else value, "f")
    )


def _fmt(value: Decimal, places: int = 1) -> str:
    """For sentences only: rounded, with thousands separators (tables keep the exact value)."""
    q = value.quantize(Decimal(1).scaleb(-places))
    text = f"{q:,.{places}f}"
    return text[:-2] if places == 1 and text.endswith(".0") else text


def _signed(value: Decimal, places: int = 1) -> str:
    return ("+" if value > 0 else "") + _fmt(value, places)


def _unit(meta: dict[str, Any]) -> dict[str, str]:
    return {k: meta["unit"][k] for k in ("code", "label_en", "label_ar")}


def _label(o: dict[str, Any], kind: str) -> str:
    """A period as it appears in tables and on chart axes (language-neutral)."""
    start, end = o["period_start"], o["period_end"]
    if (
        kind == "annual"
        and start.endswith("-01-01")
        and end.endswith("-12-31")
        and start[:4] == end[:4]
    ):
        return start[:4]
    if kind == "year_to_date":
        return f"{start[:7]}–{end[:7]}"
    if kind == "monthly":
        return start[:7]
    if kind == "statement":
        return o.get("statement_date") or end
    return f"{start}–{end}"


def _measurement(meta: dict[str, Any], o: dict[str, Any]) -> Measurement:
    unit = meta["unit"]
    return Measurement(
        None if o["value"] is None else Decimal(o["value"]),
        QUnit(unit["code"], PhysicalDimension(unit["dimension"])),
        Period(
            date.fromisoformat(o["period_start"]),
            date.fromisoformat(o["period_end"]),
            o["period_complete"],
        ),
        meta["area"]["code"],
        meta["commodity"]["code"] if meta.get("commodity") else None,
    )


def _ok(result: CalcResult) -> Decimal | None:
    return result.value if result.status is CalcStatus.OK else None


# ------------------------------------------------------------------ sources


class Sources:
    """Every published observation the analysis uses, numbered S1, S2, ... with its citation."""

    def __init__(self, session: Session, data_mode: DataMode) -> None:
        self.session, self.data_mode = session, data_mode
        self.items: list[dict[str, Any]] = []
        self._ids: dict[tuple[Any, ...], str] = {}
        self._publications: dict[str, str | None] = {}

    def _publication(self, source_id: str | None) -> str | None:
        if not source_id:
            return None
        if source_id not in self._publications:
            row = self.session.scalar(
                select(ReferencePackSource.publication).where(
                    ReferencePackSource.source_id == uuid.UUID(source_id)
                )
            )
            self._publications[source_id] = row
        return self._publications[source_id]

    def add(self, meta: dict[str, Any], o: dict[str, Any]) -> str:
        kind = meta.get("period_kind") or meta["frequency"]
        key = (meta["dataset_version"]["id"], meta["indicator"]["code"], meta["area"]["code"], o["period_start"],
               o["period_end"], meta.get("flow"), (meta.get("partner") or {}).get("code"),
               (meta.get("commodity") or {}).get("code"), o.get("statement_date"))  # fmt: skip
        if key in self._ids:
            return self._ids[key]
        sid = f"S{len(self.items) + 1}"
        self._ids[key] = sid
        src = meta["source"]
        self.items.append({
            "id": sid,
            "indicator": meta["indicator"]["code"],
            "indicator_name": T(meta["indicator"]["name_en"], meta["indicator"]["name_ar"]),
            "area": meta["area"]["code"],
            "area_name": T(meta["area"]["name_en"], meta["area"]["name_ar"]),
            "period_start": o["period_start"],
            "period_end": o["period_end"],
            "period_label": _label(o, kind),
            "period_kind": kind,
            "value": o["value"],
            "value_operator": o.get("value_operator"),
            "unit": _unit(meta),
            "publisher": src.get("publisher"),
            "title": src["dataset_title"],
            "url": src.get("url"),
            "publication": self._publication(src.get("id")),
            "accessed": src.get("access_date"),
            "dataset_version": meta["dataset_version"]["label"],
            "record_ref": o.get("record_ref"),
            "data_status": "approved_official" if self.data_mode is DataMode.VERIFIED_SOURCE else "synthetic_demonstration",
            "older_context": date.fromisoformat(o["period_end"]) < CONTEXT_FLOOR,
        })  # fmt: skip
        return sid

    def add_input(self, inp: dict[str, Any]) -> str:
        """A calculation input from ``services.analysis.sections`` (it carries its provenance)."""
        meta = {
            "indicator": {"code": inp["indicator"]["code"], "name_en": inp["indicator"]["name_en"],
                          "name_ar": inp["indicator"]["name_ar"]},
            "area": inp["area"], "unit": {**inp["unit"], "dimension": "mass"},
            "frequency": inp.get("frequency", "annual"), "period_kind": inp.get("period_kind"),
            "flow": inp.get("flow"), "partner": None,
            "commodity": {"code": inp["commodity"]} if inp.get("commodity") else None,
            "dataset_version": inp["dataset_version"],
            "source": {"dataset_title": inp["source_title"], "url": inp.get("source_url"), "publisher": None,
                       "id": None, "access_date": None},
        }  # fmt: skip
        return self.add(meta, {"period_start": inp["period_start"], "period_end": inp["period_end"],
                               "value": inp["value"], "value_operator": inp.get("value_operator"),
                               "record_ref": inp.get("record_ref")})  # fmt: skip


# ------------------------------------------------------------------ context and data access


@dataclass
class Ctx:
    session: Session
    data_mode: DataMode
    p: BalanceParams
    sources: Sources
    conflicts: list[dict[str, str]] = field(default_factory=list)

    @property
    def floor(self) -> date | None:
        return STATISTICAL_SCOPE_START if self.data_mode is DataMode.VERIFIED_SOURCE else None

    def series(
        self,
        indicator: str,
        *,
        kind: str | None = None,
        flow: str | None = None,
        partners: bool = False,
    ) -> tuple[SeriesOut | None, list[SeriesOut]]:
        """The one published national-total series (or, with ``partners``, the partner series).
        Two sources for the same series: none is returned and the conflict is recorded."""
        found = query_observations(
            self.session,
            ObservationQuery(self.data_mode, indicator=indicator, area=self.p.area,
                             period_kind=kind or self.p.period_kind, flow=flow,
                             partner=None if partners else "total", period_from=self.floor),
            allow_mixed=True,
        )  # fmt: skip
        if partners:
            return None, [s for s in found if s.meta["partner"] is not None]
        totals = [s for s in found if s.meta["partner"] is None and s.meta["commodity"] is None]
        if len(totals) > 1:
            name = totals[0].meta["indicator"]
            self.conflicts.append(T(f"{name['name_en']} is published by more than one source with different values; it is not used, rather than choosing one silently.",
                                    f"يُنشر {name['name_ar']} من أكثر من مصدر بقيم مختلفة؛ ولذلك لا يُستخدم بدلاً من اختيار أحدها بصمت."))  # fmt: skip
            return None, totals
        return (totals[0] if totals else None), totals


# ------------------------------------------------------------------ builders shared by sectors


def _number_col(key: str, label: dict[str, str], unit: dict[str, str]) -> dict[str, Any]:
    return {"key": key, "label": label, "kind": "number", "unit": unit}


PERIOD_COL = {"key": "period", "label": T("Period", "الفترة"), "kind": "period"}
STATUS_COL = {"key": "status", "label": T("Assessment", "التقييم"), "kind": "status"}


def _side_by_side(
    ctx: Ctx, pairs: list[tuple[str, SeriesOut | None, dict[str, str]]]
) -> tuple[dict[str, Any], list[str], dict[str, dict[str, Any]]]:
    """A table of several published series (same unit) by period, with no calculated column."""
    by_period: dict[str, dict[str, Any]] = {}
    evidence: list[str] = []
    unit: dict[str, str] | None = None
    shown: list[tuple[str, dict[str, str]]] = []
    for key, s, label in pairs:
        if s is None:
            continue
        unit = unit or _unit(s.meta)
        shown.append((key, label))
        kind = s.meta.get("period_kind") or s.meta["frequency"]
        for o in s.observations:
            row = by_period.setdefault(o["period_start"], {"period": _label(o, kind)})
            row[key] = o["value"]
            evidence.append(ctx.sources.add(s.meta, o))
    rows = [by_period[k] for k in sorted(by_period)]
    for row in rows:
        for key, _ in shown:
            row.setdefault(key, None)  # not published for this period: empty, never zero
    columns = [PERIOD_COL] + [_number_col(k, lab, unit or PERCENT) for k, lab in shown]
    return {"columns": columns, "rows": rows}, evidence, {k: lab for k, lab in shown}


def _line_chart(title: dict[str, str], keys: dict[str, dict[str, str]], unit: dict[str, str] | None, rows: list[dict[str, Any]],
                nature: str = "observed") -> list[dict[str, Any]]:  # fmt: skip
    usable = sum(1 for r in rows if any(r.get(k) is not None for k in keys))
    if usable < 2 or unit is None:
        return []
    return [{"type": "line", "title": title, "x": "period", "unit": unit,
             "series": [{"column": k, "label": lab, "nature": nature} for k, lab in keys.items()]}]  # fmt: skip


def _bar_chart(title: dict[str, str], key: str, label: dict[str, str], unit: dict[str, str], rows: list[dict[str, Any]],
               nature: str = "calculated") -> list[dict[str, Any]]:  # fmt: skip
    if not any(r.get(key) is not None for r in rows):
        return []
    return [{"type": "bar", "title": title, "x": "period", "unit": unit,
             "series": [{"column": key, "label": label, "nature": nature}]}]  # fmt: skip


def _change(s: SeriesOut | None) -> tuple[Decimal | None, str, str, list[dict[str, Any]]]:
    """Percentage change between the first and the last published values of a series."""
    if s is None:
        return None, "", "", []
    values = [o for o in s.observations if o["value"] is not None and not o.get("value_operator")]
    if len(values) < 2:
        return None, "", "", []
    first, last = values[0], values[-1]
    result = calc.percentage_change(_measurement(s.meta, first), _measurement(s.meta, last))
    return _ok(result), first["period_start"][:4], last["period_start"][:4], [first, last]


@dataclass
class Rec:
    """A recommendation row before numbering."""

    problem: dict[str, str]
    evidence: dict[str, str]
    action: dict[str, str]
    quantity_note: dict[str, str]
    horizon: str
    constraints: dict[str, str]
    outcome: dict[str, str]
    priority: str
    priority_basis: dict[str, str]
    kpi: dict[str, str]
    nature: str
    balance: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    quantity: str | None = None
    quantity_unit: dict[str, str] | None = None


COST_UNKNOWN = T("Unknown: OSRIP holds no cost evidence for this action. Obtain costed options from the responsible authority before deciding.",
                 "غير معروفة: لا تملك OSRIP أي دليل على تكلفة هذا الإجراء. يُطلب من الجهة المسؤولة تقديم خيارات مقدّرة التكلفة قبل اتخاذ القرار.")  # fmt: skip
HORIZON = {
    "short": T("Short term (within 1 year)", "المدى القصير (خلال سنة)"),
    "medium": T("Medium term (1–3 years)", "المدى المتوسط (1–3 سنوات)"),
    "long": T("Long term (more than 3 years)", "المدى الطويل (أكثر من 3 سنوات)"),
}
PRIORITIZATION = T(
    "Priority follows a fixed rule. A data gap that blocks the assessment is high. Otherwise a score starts at 1, adds 1 for a shortfall or deficit, and adds 1 for a gap of at least 10% of the demand measure (2 for at least 50%): 3 or more is high, 2 is medium, 1 is low. Options listed for a shortfall that is not established are conditional and not ranked. Costs are not part of the rule because they are unknown.",
    "تتبع الأولوية قاعدة ثابتة. فجوة البيانات التي تمنع التقييم أولويتها عالية. وفيما عدا ذلك يبدأ المجموع بـ1، ويضاف 1 للعجز، ويضاف 1 لفجوة لا تقل عن 10٪ من مقياس الطلب (و2 إذا بلغت 50٪): 3 فأكثر عالية، و2 متوسطة، و1 منخفضة. أما الخيارات المطروحة لعجز غير مثبت فهي مشروطة ولا تُرتَّب. ولا تدخل التكاليف في القاعدة لأنها غير معروفة.",
)


def _priority(shortfall: bool, magnitude_pct: Decimal | None) -> tuple[str, dict[str, str]]:
    m = abs(magnitude_pct) if magnitude_pct is not None else None
    size = 2 if m is not None and m >= 50 else 1 if m is not None and m >= 10 else 0
    score = 1 + (1 if shortfall else 0) + size
    level = "high" if score >= 3 else "medium" if score == 2 else "low"
    names = {"high": ("high", "عالية"), "medium": ("medium", "متوسطة"), "low": ("low", "منخفضة")}[
        level
    ]
    size_en = "not measured" if m is None else f"{_fmt(m)}%"
    size_ar = "غير مقاس" if m is None else f"{_fmt(m)}٪"
    return level, T(
        f"Score {score}: base 1{', +1 shortfall' if shortfall else ''}, gap size {size_en} (+{size}) → {names[0]}.",
        f"المجموع {score}: الأساس 1{'، +1 للعجز' if shortfall else ''}، حجم الفجوة {size_ar} (+{size}) ← {names[1]}.",
    )


BLOCKING = (
    "high",
    T(
        "A data gap that blocks the assessment comes first.",
        "فجوة البيانات التي تمنع التقييم تأتي أولاً.",
    ),
)
CONDITIONAL = ("conditional", T("Applies only if a shortfall is confirmed; not ranked until then.",
                                "ينطبق فقط إذا ثبت العجز؛ ولا يُرتَّب قبل ذلك."))  # fmt: skip


@dataclass
class SectorOut:
    balances: list[dict[str, Any]] = field(default_factory=list)
    recs: list[Rec] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    summary: list[dict[str, str]] = field(default_factory=list)
    method: dict[str, str] = field(default_factory=lambda: T("", ""))
    assumptions: list[dict[str, str]] = field(default_factory=list)
    limitations: list[dict[str, str]] = field(default_factory=list)
    # For a scenario: (balance id, base period, base supply, base demand, unit, supply label, demand label, ratio?)
    scenario_base: tuple[Any, ...] | None = None
    scenario_reason: dict[str, str] | None = None
    forecast_indicator: str | None = None

    def balance_id(self) -> str:
        return f"B{len(self.balances) + 1}"

    def gap(
        self,
        balance: str | None,
        missing: dict[str, str],
        blocks: dict[str, str],
        where: dict[str, str] | None = None,
    ) -> None:
        self.gaps.append({"balance": balance, "missing": missing, "blocks": blocks, "where": where})


def _conditional_options(options: list[tuple[dict[str, str], str, dict[str, str], dict[str, str]]], balance: str,
                         constraints: dict[str, str]) -> list[Rec]:  # fmt: skip
    """Options for a shortfall that is not established: listed, labelled conditional, unranked."""
    return [
        Rec(problem=T("If a shortfall is confirmed", "إذا ثبت وجود عجز"),
            evidence=T("Not established by the published data (see the balance's reason).", "غير مثبت بالبيانات المنشورة (انظر سبب حالة الميزان)."),
            action=action, quantity_note=T("Not quantified: no shortfall is established.", "غير محدد كمياً: لا يوجد عجز مثبت."),
            horizon=horizon, constraints=constraints, outcome=outcome, priority=CONDITIONAL[0], priority_basis=CONDITIONAL[1],
            kpi=kpi, nature="conditional_option", balance=balance)
        for action, horizon, outcome, kpi in options
    ]  # fmt: skip


# ------------------------------------------------------------------ electricity


ELEC_CONSTRAINTS = T(
    "Peak demand (MW) and when it occurs; grid transmission and distribution capacity; storage; interconnection with the GCC grid.",
    "ذروة الطلب (ميغاواط) ووقت حدوثها؛ وسعة شبكات النقل والتوزيع؛ والتخزين؛ والربط مع شبكة دول مجلس التعاون.",
)


def electricity(ctx: Ctx) -> SectorOut:
    out = SectorOut(forecast_indicator="ELEC_CONSUMPTION")
    dist, _ = ctx.series("ELEC_DISTRIBUTION")
    cons, _ = ctx.series("ELEC_CONSUMPTION")
    cap, _ = ctx.series("ELEC_INSTALLED_CAPACITY")
    b1 = out.balance_id()
    table, evidence, keys = _side_by_side(ctx, [("distribution", dist, T("Distributed (supply side)", "الموزّع (جانب العرض)")),
                                               ("consumption", cons, T("Consumed (recorded use)", "المستهلك (الاستخدام المسجّل)"))])  # fmt: skip
    unit = table["columns"][1]["unit"] if len(table["columns"]) > 1 else None
    out.balances.append({
        "id": b1, "code": "ELEC_ENERGY_SUPPLY_AND_USE",
        "title": T("Electricity supplied and recorded use (energy)", "الكهرباء الموزعة والاستخدام المسجّل (الطاقة)"),
        "status": "not_determinable",
        "status_label": T("Cannot be determined", "لا يمكن تحديده"),
        "reason": T("A shortage of electricity occurs at the hour of peak demand, measured in MW, which is not published. Annual energy totals (GWh) cannot show it, and the source states that distribution and consumption are defined differently, so their difference is not a surplus, a loss or a shortage.",
                    "يحدث عجز الكهرباء في ساعة ذروة الطلب، وتقاس بالميغاواط، وهي غير منشورة. ولا يمكن أن تبيّنه مجاميع الطاقة السنوية (غيغاواط ساعة)، كما يذكر المصدر أن التوزيع والاستهلاك معرّفان بشكل مختلف، فلا يُعد الفرق بينهما فائضاً ولا فاقداً ولا عجزاً."),
        "interpretation": T("Shown side by side for context only; no difference is calculated.", "يُعرضان جنباً إلى جنب للسياق فقط؛ ولا يُحسب أي فرق."),
        "supply_label": T("Distributed energy", "الطاقة الموزعة"), "demand_label": T("Consumed energy", "الطاقة المستهلكة"),
        "table": table, "charts": _line_chart(T("Distributed and consumed electricity", "الكهرباء الموزعة والمستهلكة"), keys, unit, table["rows"]),
        "evidence": evidence, "constraints": [ELEC_CONSTRAINTS],
        "notes": [T(dist.meta["indicator"]["limitation_en"], dist.meta["indicator"]["limitation_ar"])] if dist and dist.meta["indicator"].get("limitation_en") else [],
    })  # fmt: skip
    b2 = out.balance_id()
    ctable, cevidence, ckeys = _side_by_side(
        ctx,
        [
            (
                "installed_capacity",
                cap,
                T("Installed capacity (end of period)", "القدرة المركبة (نهاية الفترة)"),
            )
        ],
    )
    cunit = ctable["columns"][1]["unit"] if len(ctable["columns"]) > 1 else None
    out.balances.append({
        "id": b2, "code": "ELEC_CAPACITY_AT_PEAK",
        "title": T("Generating capacity against peak demand", "قدرة التوليد مقابل ذروة الطلب"),
        "status": "not_determinable", "status_label": T("Cannot be determined", "لا يمكن تحديده"),
        "reason": T("Peak demand (MW) is not published, so installed capacity cannot be compared with it. Installed capacity is also not the capacity available at the peak (outages, maintenance, renewable output).",
                    "ذروة الطلب (ميغاواط) غير منشورة، لذا لا يمكن مقارنة القدرة المركبة بها. كما أن القدرة المركبة ليست القدرة المتاحة وقت الذروة (الأعطال والصيانة وإنتاج الطاقة المتجددة)."),
        "interpretation": T("Capacity is power (MW) and is never compared with energy (GWh).", "القدرة قدرةٌ (ميغاواط) ولا تُقارن أبداً بالطاقة (غيغاواط ساعة)."),
        "table": ctable, "charts": _line_chart(T("Installed generating capacity", "القدرة التوليدية المركبة"), ckeys, cunit, ctable["rows"]),
        "evidence": cevidence, "constraints": [ELEC_CONSTRAINTS],
    })  # fmt: skip

    growth, y0, y1, pair = _change(cons)
    cgrowth, c0, c1, cpair = _change(cap)
    ev = [ctx.sources.add(cons.meta, o) for o in pair] if cons and pair else []
    cev = [ctx.sources.add(cap.meta, o) for o in cpair] if cap and cpair else []
    if growth is not None:
        out.summary.append(T(f"Recorded electricity consumption changed by {_signed(growth)}% between {y0} and {y1} (calculated from published values).",
                             f"تغيّر استهلاك الكهرباء المسجّل بنسبة {_signed(growth)}٪ بين {y0} و{y1} (محسوب من القيم المنشورة)."))  # fmt: skip
    if cgrowth is not None:
        out.summary.append(T(f"Installed generating capacity changed by {_signed(cgrowth)}% between {c0} and {c1}.",
                             f"تغيّرت القدرة التوليدية المركبة بنسبة {_signed(cgrowth)}٪ بين {c0} و{c1}."))  # fmt: skip
    out.summary.append(T("No electricity shortage or surplus is stated: peak demand is not published, and annual energy totals cannot show one.",
                         "لا يُذكر عجز أو فائض في الكهرباء: ذروة الطلب غير منشورة، ومجاميع الطاقة السنوية لا تبيّنه."))  # fmt: skip

    out.gap(b2, T("Annual peak demand (MW) for the same network and years", "ذروة الطلب السنوية (ميغاواط) للشبكة والسنوات نفسها"),
            T("Any statement of a capacity shortage or surplus.", "أي حكم بوجود عجز أو فائض في القدرة."),
            T("The grid operator's or regulator's annual statistics", "الإحصاءات السنوية لمشغّل الشبكة أو الجهة المنظِّمة"))  # fmt: skip
    out.gap(b2, T("Available (firm) capacity at the peak, after outages and maintenance", "القدرة المتاحة (المؤكدة) وقت الذروة بعد الأعطال والصيانة"),
            T("A reserve margin.", "حساب هامش الاحتياطي."))  # fmt: skip
    out.gap(b1, T("Electricity imported or exported through interconnections, and storage", "الكهرباء المستوردة أو المصدّرة عبر الربط، والتخزين"),
            T("A complete supply account.", "حساباً كاملاً للعرض."))  # fmt: skip
    out.gap(b1, T("Distribution and consumption with matching definitions and coverage", "التوزيع والاستهلاك بتعريفات وتغطية متطابقة"),
            T("Separating network losses from unbilled use and definitional differences.", "فصل فاقد الشبكة عن الاستخدام غير المفوتر والفروق في التعريف."))  # fmt: skip

    out.recs.append(Rec(
        problem=T("Peak adequacy cannot be assessed", "لا يمكن تقييم كفاية القدرة وقت الذروة"),
        evidence=T("Peak demand and firm capacity are not among the published series.", "ذروة الطلب والقدرة المؤكدة ليستا ضمن السلاسل المنشورة."),
        action=T("Obtain annual peak demand and firm available capacity for 2022 onward and repeat this analysis.", "الحصول على ذروة الطلب السنوية والقدرة المتاحة المؤكدة منذ 2022 وإعادة هذا التحليل."),
        quantity_note=T("Not applicable (a data request).", "لا ينطبق (طلب بيانات)."), horizon="short", constraints=ELEC_CONSTRAINTS,
        outcome=T("Makes a reserve-margin assessment possible. Assumes the operator publishes or shares these figures.", "يجعل تقييم هامش الاحتياطي ممكناً. ويفترض أن ينشر المشغّل هذه الأرقام أو يتيحها."),
        priority=BLOCKING[0], priority_basis=BLOCKING[1], kpi=T("Reserve margin at the annual peak (%)", "هامش الاحتياطي عند الذروة السنوية (٪)"),
        nature="data_improvement", balance=b2))  # fmt: skip
    if growth is not None and cgrowth is not None:
        faster = growth > cgrowth
        out.recs.append(Rec(
            problem=T("Consumption and capacity grow at different rates", "يختلف معدل نمو الاستهلاك عن نمو القدرة"),
            evidence=T(f"Consumption {_signed(growth)}% ({y0}–{y1}); installed capacity {_signed(cgrowth)}% ({c0}–{c1}).",
                       f"الاستهلاك {_signed(growth)}٪ ({y0}–{y1})؛ والقدرة المركبة {_signed(cgrowth)}٪ ({c0}–{c1})."),
            action=T("Track consumption growth against capacity additions each year, alongside the peak data once available.", "متابعة نمو الاستهلاك مقابل إضافات القدرة سنوياً، مع بيانات الذروة حين تتوفر."),
            quantity_note=T("Not quantified: growth rates are evidence, not a shortfall.", "غير محدد كمياً: معدلات النمو دليل وليست عجزاً."),
            horizon="short", constraints=ELEC_CONSTRAINTS,
            outcome=T("Early warning if consumption keeps outpacing capacity. Assumes the series stay comparable.", "إنذار مبكر إذا استمر الاستهلاك في تجاوز القدرة. ويفترض بقاء السلاسل قابلة للمقارنة."),
            priority="medium" if faster else "low",
            priority_basis=T("Monitoring only: consumption grew faster than capacity." if faster else "Monitoring only: capacity grew at least as fast as consumption.",
                             "متابعة فقط: نما الاستهلاك أسرع من القدرة." if faster else "متابعة فقط: نمت القدرة بمعدل لا يقل عن الاستهلاك."),
            kpi=T("Consumption growth minus capacity growth (percentage points)", "نمو الاستهلاك ناقص نمو القدرة (نقطة مئوية)"),
            nature="recommendation", balance=b2, evidence_ids=ev + cev))  # fmt: skip
    out.recs += _conditional_options([
        (T("Demand management and efficiency at the peak (time-of-use signals, efficient cooling standards)", "إدارة الطلب والكفاءة وقت الذروة (إشارات حسب وقت الاستخدام ومعايير التبريد الكفؤ)"), "short",
         T("Lower peak load; depends on uptake.", "خفض حمل الذروة؛ ويعتمد على مدى الاستجابة."), T("Peak demand (MW)", "ذروة الطلب (ميغاواط)")),
        (T("Reduce network losses, once measured separately from unbilled use", "خفض فاقد الشبكة بعد قياسه منفصلاً عن الاستخدام غير المفوتر"), "medium",
         T("More of the generated energy reaches customers.", "وصول مزيد من الطاقة المولدة إلى المستهلكين."), T("Network losses (% of energy sent out)", "فاقد الشبكة (٪ من الطاقة المرسلة)")),
        (T("Storage to shift supply to the peak hours", "التخزين لنقل العرض إلى ساعات الذروة"), "medium",
         T("Firm capacity at the peak; size depends on the peak profile.", "قدرة مؤكدة وقت الذروة؛ ويعتمد الحجم على منحنى الذروة."), T("Storage capacity (MW, MWh)", "سعة التخزين (ميغاواط، ميغاواط ساعة)")),
        (T("Use interconnection imports at the peak", "الاستفادة من الاستيراد عبر الربط وقت الذروة"), "medium",
         T("Shared reserves; limited by interconnector capacity and neighbours' peaks.", "احتياطيات مشتركة؛ وتحدها سعة الربط وذروات الدول المجاورة."), T("Interconnector imports at the peak (MW)", "الواردات عبر الربط وقت الذروة (ميغاواط)")),
        (T("Add local generating capacity, including renewables", "إضافة قدرة توليد محلية، بما فيها المتجددة"), "long",
         T("Higher firm capacity; renewables need storage or firm backup for the peak.", "زيادة القدرة المؤكدة؛ وتحتاج المتجددة إلى تخزين أو دعم مؤكد للذروة."), T("Firm capacity (MW)", "القدرة المؤكدة (ميغاواط)")),
    ], b2, ELEC_CONSTRAINTS)  # fmt: skip
    out.method = T("Published annual distribution, consumption and installed capacity are retrieved for the selected area and period kind. A shortage or surplus is stated only when peak demand and available capacity are both published; no difference of energy totals is calculated.",
                   "تُسترجع قيم التوزيع والاستهلاك والقدرة المركبة السنوية المنشورة للمنطقة ونوع الفترة المختارين. ولا يُذكر عجز أو فائض إلا عند نشر ذروة الطلب والقدرة المتاحة معاً؛ ولا يُحسب أي فرق بين مجاميع الطاقة.")  # fmt: skip
    out.scenario_reason = T("No electricity balance can be determined, so a scenario would only project two unrelated measures.",
                            "لا يمكن تحديد ميزان الكهرباء، فالسيناريو سيُسقط مقياسين غير مترابطين فقط.")  # fmt: skip
    return out


# ------------------------------------------------------------------ water


WATER_CONSTRAINTS = T(
    "Water quality and treatment; transport and storage between production and use; permitted reuse of treated wastewater only for approved uses.",
    "جودة المياه ومعالجتها؛ والنقل والتخزين بين الإنتاج والاستخدام؛ وإعادة استخدام مياه الصرف المعالجة للاستخدامات المعتمدة فقط.",
)


def water(ctx: Ctx) -> SectorOut:
    out = SectorOut(forecast_indicator="WATER_CONSUMPTION")
    ctx.series("WATER_PRODUCTION")  # recorded as a conflict when two sources publish it
    dist, _ = ctx.series("WATER_DISTRIBUTION")
    cons, _ = ctx.series("WATER_CONSUMPTION")
    b1 = out.balance_id()
    table, evidence, keys = _side_by_side(ctx, [("distribution", dist, T("Distributed (supply side)", "الموزّعة (جانب العرض)")),
                                               ("consumption", cons, T("Consumed (recorded use)", "المستهلكة (الاستخدام المسجّل)"))])  # fmt: skip
    unit = table["columns"][1]["unit"] if len(table["columns"]) > 1 else None
    out.balances.append({
        "id": b1, "code": "WATER_SUPPLY_AND_USE",
        "title": T("Water supplied and recorded use", "المياه الموزعة والاستخدام المسجّل"),
        "status": "not_determinable", "status_label": T("Cannot be determined", "لا يمكن تحديده"),
        "reason": T("The source states that production minus distribution or consumption is neither leakage nor a shortage, because coverage and definitions differ. The water demand requirement, unmet demand and storage levels are not published.",
                    "يذكر المصدر أن الإنتاج ناقص التوزيع أو الاستهلاك ليس تسرباً ولا عجزاً لاختلاف التغطية والتعريفات. كما أن الاحتياج من المياه والطلب غير الملبّى ومستويات التخزين غير منشورة."),
        "interpretation": T("Shown side by side for context only; no difference is calculated.", "تُعرضان جنباً إلى جنب للسياق فقط؛ ولا يُحسب أي فرق."),
        "supply_label": T("Distributed water", "المياه الموزعة"), "demand_label": T("Consumed water", "المياه المستهلكة"),
        "table": table, "charts": _line_chart(T("Distributed and consumed water", "المياه الموزعة والمستهلكة"), keys, unit, table["rows"]),
        "evidence": evidence, "constraints": [WATER_CONSTRAINTS],
        "notes": list(ctx.conflicts),
    })  # fmt: skip
    growth, y0, y1, pair = _change(cons)
    if growth is not None and cons is not None:
        for o in pair:
            ctx.sources.add(cons.meta, o)
        out.summary.append(T(f"Recorded water consumption changed by {_signed(growth)}% between {y0} and {y1} (calculated from published values).",
                             f"تغيّر استهلاك المياه المسجّل بنسبة {_signed(growth)}٪ بين {y0} و{y1} (محسوب من القيم المنشورة)."))  # fmt: skip
    out.summary.append(T("No water shortage or surplus is stated: the demand requirement and storage are not published, and the source rules out reading production minus consumption as a shortage.",
                         "لا يُذكر عجز أو فائض في المياه: الاحتياج والتخزين غير منشورين، والمصدر يستبعد قراءة الإنتاج ناقص الاستهلاك على أنه عجز."))  # fmt: skip
    out.gap(b1, T("Water demand requirement or unmet demand by service area", "الاحتياج من المياه أو الطلب غير الملبّى حسب منطقة الخدمة"),
            T("Any statement of a water shortage or surplus.", "أي حكم بوجود عجز أو فائض في المياه."),
            T("The water utility's or regulator's statistics", "إحصاءات شركة المياه أو الجهة المنظِّمة"))  # fmt: skip
    out.gap(b1, T("Storage and strategic reserve levels", "مستويات التخزين والاحتياطي الاستراتيجي"), T("Days of supply in reserve.", "حساب أيام الإمداد المحتفظ بها."))  # fmt: skip
    out.gap(b1, T("Treatment and desalination capacity, and quality compliance", "سعة المعالجة والتحلية والالتزام بالجودة"), T("Assessing whether supply can grow safely.", "تقييم إمكانية زيادة العرض بأمان."))  # fmt: skip
    out.gap(b1, T("Metered losses (non-revenue water) separated from unbilled use", "الفاقد المقاس (المياه غير المدرّة للإيراد) مفصولاً عن الاستخدام غير المفوتر"),
            T("Any loss-reduction target.", "أي هدف لخفض الفاقد."))  # fmt: skip
    out.recs.append(Rec(
        problem=T("A water shortage cannot be assessed", "لا يمكن تقييم عجز المياه"),
        evidence=T("Demand requirement, unmet demand and storage are not among the published series.", "الاحتياج والطلب غير الملبّى والتخزين ليست ضمن السلاسل المنشورة."),
        action=T("Obtain the demand requirement (or unmet demand) and storage levels by service area for 2022 onward and repeat this analysis.", "الحصول على الاحتياج (أو الطلب غير الملبّى) ومستويات التخزين حسب منطقة الخدمة منذ 2022 وإعادة هذا التحليل."),
        quantity_note=T("Not applicable (a data request).", "لا ينطبق (طلب بيانات)."), horizon="short", constraints=WATER_CONSTRAINTS,
        outcome=T("Makes a supply–demand balance possible. Assumes the utility shares coverage-matched figures.", "يجعل حساب ميزان العرض والطلب ممكناً. ويفترض أن تتيح الشركة أرقاماً متطابقة التغطية."),
        priority=BLOCKING[0], priority_basis=BLOCKING[1], kpi=T("Unmet demand (million m³) and days of storage", "الطلب غير الملبّى (مليون م³) وأيام التخزين"),
        nature="data_improvement", balance=b1))  # fmt: skip
    out.recs += _conditional_options([
        (T("Demand management and efficiency (metering, efficient fittings, awareness)", "إدارة الطلب والكفاءة (العدادات والتجهيزات الموفرة والتوعية)"), "short",
         T("Lower use per connection; depends on uptake.", "خفض الاستخدام لكل توصيلة؛ ويعتمد على الاستجابة."), T("Consumption per connection (m³)", "الاستهلاك لكل توصيلة (م³)")),
        (T("Reduce non-revenue water once losses are metered", "خفض المياه غير المدرّة للإيراد بعد قياس الفاقد"), "medium",
         T("More produced water reaches customers.", "وصول مزيد من المياه المنتجة إلى المستهلكين."), T("Non-revenue water (% of production)", "المياه غير المدرّة للإيراد (٪ من الإنتاج)")),
        (T("Increase storage and strategic reserves", "زيادة التخزين والاحتياطي الاستراتيجي"), "medium",
         T("More days of supply during outages.", "مزيد من أيام الإمداد أثناء الانقطاعات."), T("Days of storage", "أيام التخزين")),
        (T("Use treated wastewater for permitted non-drinking uses", "استخدام مياه الصرف المعالجة للاستخدامات غير الشرب المسموح بها"), "medium",
         T("Frees drinking water for drinking; only within quality rules.", "توفير مياه الشرب للشرب؛ وضمن قواعد الجودة فقط."), T("Treated wastewater reused (million m³)", "مياه الصرف المعالجة المعاد استخدامها (مليون م³)")),
        (T("Improve transport and distribution between production and demand centres", "تحسين النقل والتوزيع بين مراكز الإنتاج والطلب"), "medium",
         T("Supply reaches the areas short of it.", "وصول الإمداد إلى المناطق التي تحتاجه."), T("Supply interruptions (hours per customer)", "انقطاعات الإمداد (ساعات لكل مشترك)")),
        (T("Add desalination or treatment capacity", "إضافة سعة تحلية أو معالجة"), "long",
         T("Higher supply; energy use and brine discharge must be managed.", "زيادة العرض؛ مع ضرورة إدارة استهلاك الطاقة وتصريف المياه المالحة."), T("Production capacity (m³ per day)", "سعة الإنتاج (م³ يومياً)")),
    ], b1, WATER_CONSTRAINTS)  # fmt: skip
    out.method = T("Published annual distribution and consumption are retrieved for the selected area. Production is used only when exactly one source publishes it. A shortage or surplus is stated only against a published demand requirement; no difference of production, distribution and consumption is calculated.",
                   "تُسترجع قيم التوزيع والاستهلاك السنوية المنشورة للمنطقة المختارة. ولا يُستخدم الإنتاج إلا إذا نشره مصدر واحد فقط. ولا يُذكر عجز أو فائض إلا مقابل احتياج منشور؛ ولا يُحسب أي فرق بين الإنتاج والتوزيع والاستهلاك.")  # fmt: skip
    out.scenario_reason = T("No water balance can be determined, so a scenario would only project two unrelated measures.",
                            "لا يمكن تحديد ميزان المياه، فالسيناريو سيُسقط مقياسين غير مترابطين فقط.")  # fmt: skip
    return out


# ------------------------------------------------------------------ food security


FOOD_CONSTRAINTS = T(
    "Shelf life and cold chains; nutritional needs; the water needed to grow more locally; storage capacity.",
    "مدة الصلاحية وسلاسل التبريد؛ والاحتياجات الغذائية؛ والمياه اللازمة لزيادة الإنتاج المحلي؛ وسعة التخزين.",
)
SSR_PREFIX = "SELF_SUFFICIENCY_"


def _ssr_status(gap: Decimal | None, operator: str | None) -> str:
    if gap is None:
        return "not_determinable"
    if operator in (">", ">="):
        return "surplus" if gap > 0 else "not_determinable"
    if operator in ("<", "<="):
        return "shortfall" if gap < 0 else "not_determinable"
    if operator == "~":
        return "not_determinable" if abs(gap) < 5 else ("surplus" if gap > 0 else "shortfall")
    return "surplus" if gap > 0 else "shortfall" if gap < 0 else "balanced"


SSR_LABEL = {
    "surplus": T("Production above domestic consumption", "الإنتاج أعلى من الاستهلاك المحلي"),
    "shortfall": T("Production below domestic consumption", "الإنتاج أدنى من الاستهلاك المحلي"),
    "balanced": T("Production equals domestic consumption", "الإنتاج يساوي الاستهلاك المحلي"),
    "not_determinable": T("Cannot be determined", "لا يمكن تحديده"),
}


def _ssr_codes(ctx: Ctx) -> list[str]:
    from app.models import Indicator

    return list(ctx.session.scalars(
        select(Indicator.code).where(Indicator.code.like(f"{SSR_PREFIX}%")).order_by(Indicator.code)
    ))  # fmt: skip


def _conflict_balance(
    ctx: Ctx, out: SectorOut, code: str, totals: list[SeriesOut], kind: str
) -> None:
    """Two published sources disagree: both values are shown and neither is chosen."""
    name = T(totals[0].meta["indicator"]["name_en"], totals[0].meta["indicator"]["name_ar"])
    rows, evidence = [], []
    for s in totals:
        for o in s.observations:
            evidence.append(ctx.sources.add(s.meta, o))
            rows.append({"period": _label(o, kind), "kind": kind, "qualifier": o.get("value_operator"),
                         "ratio": o["value"], "source": s.meta["source"]["dataset_title"]})  # fmt: skip
    out.balances.append({
        "id": out.balance_id(), "code": f"FOOD_{code}", "title": name, "status": "not_determinable",
        "status_label": SSR_LABEL["not_determinable"],
        "reason": T("More than one published source states this ratio with different values; both are listed and neither is chosen.",
                    "يذكر أكثر من مصدر منشور هذه النسبة بقيم مختلفة؛ فتُدرج القيمتان ولا تُختار إحداهما."),
        "interpretation": T("Resolve which statement applies (and to which period) before classifying the product.",
                            "يلزم تحديد التصريح المعتمد (ولأي فترة) قبل تصنيف المنتج."),
        "table": {"columns": [PERIOD_COL, {"key": "kind", "label": T("Kind of figure", "نوع الرقم"), "kind": "text"},
                              {"key": "qualifier", "label": T("Qualifier", "المؤهِّل"), "kind": "text"},
                              _number_col("ratio", T("Self-sufficiency ratio", "نسبة الاكتفاء الذاتي"), PERCENT),
                              {"key": "source", "label": T("Source", "المصدر"), "kind": "text"}], "rows": rows},
        "evidence": evidence, "constraints": [FOOD_CONSTRAINTS],
    })  # fmt: skip


def food_security(ctx: Ctx) -> SectorOut:
    out = SectorOut()
    for code in _ssr_codes(ctx):
        rows_src: list[tuple[SeriesOut, dict[str, Any], str]] = []
        conflicted: tuple[list[SeriesOut], str] | None = None
        for kind in (
            [ctx.p.period_kind, "statement"]
            if ctx.p.period_kind == "annual"
            else [ctx.p.period_kind]
        ):
            s, totals = ctx.series(code, kind=kind)
            if s is not None:
                rows_src += [(s, o, kind) for o in s.observations]
            elif len(totals) > 1:
                conflicted = (totals, kind)
        if not rows_src:
            if conflicted is not None:
                _conflict_balance(ctx, out, code, *conflicted)
            continue
        s0 = rows_src[0][0]
        name = T(s0.meta["indicator"]["name_en"], s0.meta["indicator"]["name_ar"])
        bid = out.balance_id()
        rows, evidence = [], []
        latest: tuple[str, Decimal | None, str | None, str, dict[str, Any], str] | None = None
        for s, o, kind in sorted(rows_src, key=lambda r: (r[2] != "annual", r[1]["period_start"])):
            gap = _ok(calc.self_sufficiency_gap(_measurement(s.meta, o)))
            operator = o.get("value_operator")
            status = _ssr_status(gap, operator)
            sid = ctx.sources.add(s.meta, o)
            evidence.append(sid)
            # An inequality ("more than 95%") is not an exact value: its row shows no gap.
            rows.append({"period": _label(o, kind), "kind": kind, "qualifier": operator,
                         "ratio": o["value"], "gap": None if operator else _num(gap), "status": status})  # fmt: skip
            # The latest annual figure decides; a dated statement only when no annual figure exists.
            if latest is None or kind == "annual" or latest[3] != "annual":
                latest = (status, gap, operator, kind, o, sid)
        assert latest is not None
        status, gap, operator, kind, o, sid = latest
        if status == "not_determinable":
            gap = None
        bound = T(" The ratio is published as an inequality, so the gap is a bound, not an exact value.",
                  " النسبة منشورة كمتباينة، فالفجوة حدٌّ وليست قيمة دقيقة.") if operator and gap is not None else T("", "")  # fmt: skip
        label = _label(o, kind)
        out.balances.append({
            "id": bid, "code": f"FOOD_{code}",
            "title": name, "status": status, "status_label": SSR_LABEL[status],
            "reason": T(f"Published self-sufficiency ratio {(operator or '')}{o['value']}% for {label}" + (" (a dated statement; the reference period is not stated)." if kind == "statement" else "."),
                        f"نسبة الاكتفاء الذاتي المنشورة {(operator or '')}{o['value']}٪ لـ{label}" + (" (تصريح مؤرخ؛ ولم تُذكر الفترة المرجعية)." if kind == "statement" else ".")) if o["value"] is not None
            else T("The ratio is missing in the source.", "النسبة مفقودة في المصدر."),
            "interpretation": T("A ratio above 100% means domestic production exceeds domestic consumption; below 100%, the rest is met by imports or stocks. It is not a measure of household access, prices or nutrition." + bound["en"],
                                "النسبة فوق 100٪ تعني أن الإنتاج المحلي يتجاوز الاستهلاك المحلي؛ ودون 100٪ يُغطّى الباقي بالواردات أو المخزون. وهي ليست مقياساً لوصول الأسر أو الأسعار أو التغذية." + bound["ar"]),
            "period": label, "period_kind": kind,
            "gap": _num(gap) if status != "not_determinable" else None,
            "gap_unit": POINTS if status != "not_determinable" else None,
            "gap_share": _num(gap) if status != "not_determinable" else None,
            "supply_label": T("Domestic production", "الإنتاج المحلي"), "demand_label": T("Domestic consumption", "الاستهلاك المحلي"),
            "table": {"columns": [
                PERIOD_COL,
                {"key": "kind", "label": T("Kind of figure", "نوع الرقم"), "kind": "text"},
                {"key": "qualifier", "label": T("Qualifier", "المؤهِّل"), "kind": "text"},
                _number_col("ratio", T("Self-sufficiency ratio", "نسبة الاكتفاء الذاتي"), PERCENT),
                _number_col("gap", T("Production minus consumption", "الإنتاج ناقص الاستهلاك"), POINTS),
                STATUS_COL,
            ], "rows": rows},
            "charts": _bar_chart(T(f"{name['en']}: production relative to consumption", f"{name['ar']}: الإنتاج مقارنةً بالاستهلاك"),
                                 "gap", T("Production minus consumption", "الإنتاج ناقص الاستهلاك"), POINTS, rows),
            "evidence": evidence, "constraints": [FOOD_CONSTRAINTS],
            "notes": [T(s0.meta["indicator"]["limitation_en"], s0.meta["indicator"]["limitation_ar"])] if s0.meta["indicator"].get("limitation_en") else [],
        })  # fmt: skip
        _food_recs(out, bid, name, status, gap, label, sid, operator, o)
    # Quantities (tonnes): production against apparent availability, where all components exist.
    _food_quantities(ctx, out)
    if not out.balances:
        bid = out.balance_id()
        out.balances.append({
            "id": bid, "code": "FOOD_NO_DATA", "title": T("Food production against consumption", "الإنتاج الغذائي مقابل الاستهلاك"),
            "status": "not_determinable", "status_label": SSR_LABEL["not_determinable"],
            "reason": T("No self-sufficiency ratio or matching production, import and export quantities are published for this selection.",
                        "لا تُنشر نسبة اكتفاء ذاتي ولا كميات متطابقة للإنتاج والواردات والصادرات لهذا الاختيار."),
            "interpretation": T("Production figures alone cannot show a shortage.", "أرقام الإنتاج وحدها لا تبيّن العجز."),
            "table": {"columns": [PERIOD_COL], "rows": []}, "evidence": [], "constraints": [FOOD_CONSTRAINTS],
        })  # fmt: skip
    out.gap(None, T("Domestic consumption in tonnes for each product", "الاستهلاك المحلي بالطن لكل منتج"),
            T("Expressing each gap as a quantity rather than percentage points.", "التعبير عن كل فجوة كمية بدلاً من النقاط المئوية."))  # fmt: skip
    out.gap(None, T("Strategic stocks and their shelf life", "المخزون الاستراتيجي ومدة صلاحيته"), T("How long reserves cover a shortfall.", "مدة تغطية الاحتياطيات للعجز."))  # fmt: skip
    out.gap(None, T("Water used per tonne produced, by product", "المياه المستخدمة لكل طن منتج حسب المنتج"), T("Weighing local expansion against water scarcity.", "الموازنة بين التوسع المحلي وندرة المياه."))  # fmt: skip
    out.gap(None, T("Nutritional requirement by product group", "الاحتياج الغذائي حسب مجموعة المنتجات"), T("Judging whether supply meets nutritional needs.", "الحكم على كفاية العرض للاحتياجات الغذائية."))  # fmt: skip
    determined = [b for b in out.balances if b["status"] != "not_determinable"]
    if determined:
        out.recs.append(Rec(
            problem=T("Gaps can only be stated in percentage points", "لا يمكن التعبير عن الفجوات إلا بالنقاط المئوية"),
            evidence=T("Consumption quantities, stocks and post-harvest loss rates are not among the published series.",
                       "كميات الاستهلاك والمخزون ومعدلات الفاقد بعد الحصاد ليست ضمن السلاسل المنشورة."),
            action=T("Obtain domestic consumption in tonnes, strategic stocks and post-harvest loss rates for the listed products.",
                     "الحصول على الاستهلاك المحلي بالطن والمخزون الاستراتيجي ومعدلات الفاقد بعد الحصاد للمنتجات المدرجة."),
            quantity_note=T("Not applicable (a data request).", "لا ينطبق (طلب بيانات)."), horizon="short", constraints=FOOD_CONSTRAINTS,
            outcome=T("Gaps in tonnes and a measured basis for loss reduction.", "فجوات بالطن وأساس مقاس لخفض الفاقد."),
            priority="medium", priority_basis=T("Improves the measure; the direction of each gap is already known.", "يحسّن القياس؛ فاتجاه كل فجوة معروف مسبقاً."),
            kpi=T("Products with consumption published in tonnes", "المنتجات التي يُنشر استهلاكها بالطن"), nature="data_improvement"))  # fmt: skip
    shortfalls = [b for b in determined if b["status"] == "shortfall"]
    surpluses = [b for b in determined if b["status"] == "surplus"]
    if determined:
        undetermined = len(out.balances) - len(determined)
        out.summary.insert(0, T(
            f"Products with published data: {len(out.balances)}. Production above domestic consumption: {len(surpluses)}; below it: {len(shortfalls)}; not determinable: {undetermined}.",
            f"المنتجات ذات البيانات المنشورة: {len(out.balances)}. الإنتاج أعلى من الاستهلاك المحلي: {len(surpluses)}؛ وأدنى منه: {len(shortfalls)}؛ وغير قابل للتحديد: {undetermined}."))  # fmt: skip
        for b in shortfalls + surpluses:
            if b["code"].startswith("FOOD_SELF"):
                out.summary.append(T(f"{b['title']['en']}: {_signed(Decimal(b['gap']))} percentage points ({b['period']}).",
                                     f"{b['title']['ar']}: {_signed(Decimal(b['gap']))} نقطة مئوية ({b['period']})."))  # fmt: skip
    out.method = T("Each product's published self-sufficiency ratio minus 100 gives production relative to domestic consumption, in percentage points (the latest annual figure decides; a dated statement only when no annual figure exists). An inequality such as \"more than 95%\" is not treated as an exact value. Where production, imports and exports are published in the same unit and period, production is also compared with apparent availability in tonnes.",
                   "تعطي نسبة الاكتفاء الذاتي المنشورة لكل منتج ناقص 100 الإنتاجَ مقارنةً بالاستهلاك المحلي بالنقاط المئوية (يحسم آخر رقم سنوي؛ ولا يُعتمد التصريح المؤرخ إلا عند غياب الرقم السنوي). ولا تُعامل المتباينة مثل «أكثر من 95٪» قيمةً دقيقة. وحيث تُنشر قيم الإنتاج والواردات والصادرات بالوحدة والفترة نفسيهما، يُقارن الإنتاج أيضاً بالتوافر الظاهري بالطن.")  # fmt: skip
    out.assumptions.append(T("Self-sufficiency ratios are used as published; OSRIP does not recompute them.", "تُستخدم نسب الاكتفاء الذاتي كما نُشرت؛ ولا تعيد OSRIP حسابها."))  # fmt: skip
    first = next((b for b in determined), None)
    if first is not None and first["code"].startswith("FOOD_SELF"):
        ratio_row = next(r for r in reversed(first["table"]["rows"]) if r["ratio"] is not None)
        out.scenario_base = (
            "ratio",
            first["id"],
            first["period"],
            Decimal(ratio_row["ratio"]),
            first["title"],
        )
    elif first is not None and first.get("_scenario"):
        out.scenario_base = first.pop("_scenario")
    for b in out.balances:
        b.pop("_scenario", None)
    out.scenario_reason = T(
        "No product balance can be determined for a scenario.", "لا يمكن تحديد ميزان منتج لسيناريو."
    )
    return out


def _food_recs(out: SectorOut, bid: str, name: dict[str, str], status: str, gap: Decimal | None, label: str, sid: str,
               operator: str | None, o: dict[str, Any]) -> None:  # fmt: skip
    if status == "not_determinable":
        out.recs.append(Rec(
            problem=T(f"{name['en']}: the balance cannot be determined", f"{name['ar']}: لا يمكن تحديد الميزان"),
            evidence=T(f"Published as {(operator or '')}{o['value']}% ({label}).", f"منشورة بقيمة {(operator or '')}{o['value']}٪ ({label})."),
            action=T("Obtain the exact ratio with its reference period from the publishing ministry.", "الحصول على النسبة الدقيقة وفترتها المرجعية من الوزارة الناشرة."),
            quantity_note=T("Not applicable (a data request).", "لا ينطبق (طلب بيانات)."), horizon="short", constraints=FOOD_CONSTRAINTS,
            outcome=T("Allows the product to be classified.", "يتيح تصنيف المنتج."), priority=BLOCKING[0], priority_basis=BLOCKING[1],
            kpi=T("Self-sufficiency ratio (%)", "نسبة الاكتفاء الذاتي (٪)"), nature="data_improvement", balance=bid, evidence_ids=[sid]))  # fmt: skip
        return
    assert gap is not None
    level, basis = _priority(status == "shortfall", gap)
    evidence = T(f"Self-sufficiency {(operator or '')}{o['value']}% ({label}): {_signed(gap)} percentage points.",
                 f"الاكتفاء الذاتي {(operator or '')}{o['value']}٪ ({label}): {_signed(gap)} نقطة مئوية.")  # fmt: skip
    size = abs(gap)
    # One targeted option per product, chosen by the size of the gap (the rule is stated in
    # the action's priority basis); the other options stay in the sector's option list.
    if status == "shortfall" and size >= 50:
        action, horizon, outcome, kpi = (
            T("Expand local production where water and land allow, and diversify import suppliers meanwhile", "توسيع الإنتاج المحلي حيث تسمح المياه والأراضي، وتنويع موردي الاستيراد في الأثناء"), "long",
            T("A higher ratio over time and a steadier supply meanwhile. Assumes irrigation water is available sustainably.", "ارتفاع النسبة بمرور الوقت وإمداد أكثر استقراراً في الأثناء. ويفترض توفر مياه الري بشكل مستدام."),
            T("Self-sufficiency ratio (%)", "نسبة الاكتفاء الذاتي (٪)"))  # fmt: skip
    elif status == "shortfall" and size >= 10:
        action, horizon, outcome, kpi = (
            T("Diversify import suppliers and keep strategic reserves sized to shelf life", "تنويع موردي الاستيراد والاحتفاظ باحتياطي استراتيجي يتناسب مع مدة الصلاحية"), "medium",
            T("Steadier supply during disruptions. Assumes storage and cold-chain capacity exist.", "إمداد أكثر استقراراً أثناء الاضطرابات. ويفترض توفر سعة التخزين وسلاسل التبريد."),
            T("Months of consumption held in reserve", "أشهر الاستهلاك المحتفظ بها احتياطياً"))  # fmt: skip
    elif status == "shortfall":
        action, horizon, outcome, kpi = (
            T("Close the small gap by reducing losses between harvest and sale (handling, cold chain, storage)", "سد الفجوة الصغيرة بخفض الفاقد بين الحصاد والبيع (المناولة وسلاسل التبريد والتخزين)"), "short",
            T("More of local production reaches consumers. Loss rates are not published, so the effect is unmeasured.", "وصول مزيد من الإنتاج المحلي إلى المستهلكين. ومعدلات الفاقد غير منشورة، فالأثر غير مقاس."),
            T("Post-harvest losses (% of production)", "الفاقد بعد الحصاد (٪ من الإنتاج)"))  # fmt: skip
    elif size >= 10:
        action, horizon, outcome, kpi = (
            T("Process and add value to the surplus, and export where markets are accessible and standards are met", "تصنيع الفائض وإضافة القيمة إليه، والتصدير حيث تتاح الأسواق وتُستوفى المعايير"), "medium",
            T("Higher value per tonne and income from the surplus. Depends on market access, standards and logistics.", "قيمة أعلى للطن ودخل من الفائض. ويعتمد على النفاذ إلى الأسواق والمعايير والخدمات اللوجستية."),
            T("Export value of the product (OMR)", "قيمة صادرات المنتج (ريال عماني)"))  # fmt: skip
    else:
        action, horizon, outcome, kpi = (
            T("Store or redistribute the seasonal surplus within shelf life", "تخزين الفائض الموسمي أو إعادة توزيعه ضمن مدة الصلاحية"), "short",
            T("Less waste. Limited by cold-chain and storage capacity.", "هدر أقل. وتحده سعة سلاسل التبريد والتخزين."),
            T("Product wasted (tonnes)", "المنتج المهدر (طن)"))  # fmt: skip
    out.recs.append(Rec(
        problem=T(f"{name['en']}: production {'below' if status == 'shortfall' else 'above'} domestic consumption",
                  f"{name['ar']}: الإنتاج {'أدنى من' if status == 'shortfall' else 'أعلى من'} الاستهلاك المحلي"),
        evidence=evidence, action=action, horizon=horizon, constraints=FOOD_CONSTRAINTS, outcome=outcome,
        priority=level, priority_basis=basis, kpi=kpi, nature="recommendation", balance=bid, evidence_ids=[sid],
        quantity=_num(size), quantity_unit=POINTS,
        quantity_note=T("Gap in percentage points of domestic consumption (tonnes are not published).",
                        "الفجوة بالنقاط المئوية من الاستهلاك المحلي (الكميات بالطن غير منشورة).")))  # fmt: skip


def _commodity_name(ctx: Ctx, code: str) -> dict[str, str]:
    from app.models import Commodity

    row = ctx.session.scalar(select(Commodity).where(Commodity.code == code))
    return T(row.name_en, row.name_ar) if row is not None else T(code, code)


def _food_quantities(ctx: Ctx, out: SectorOut) -> None:
    from app.services.analysis import sections

    calcs = sections.food_security(ctx.session, sections.AnalysisFilter(
        data_mode=ctx.data_mode, area=ctx.p.area, period_kind=ctx.p.period_kind, period_from=ctx.floor))  # fmt: skip
    for c in calcs:
        if c["kind"] != "apparent_availability" or c["result"]["status"] != "ok":
            continue
        production = next((i for i in c["inputs"] if i["role"] == "production"), None)
        if production is None or production["value"] is None:
            continue
        unit = c["result"]["unit"]
        meas = Measurement(Decimal(production["value"]), QUnit(unit["code"], PhysicalDimension.MASS),
                           Period(date.fromisoformat(production["period_start"]), date.fromisoformat(production["period_end"]),
                                  production["period_complete"]), production["area"]["code"], production["commodity"])  # fmt: skip
        avail = Measurement(
            Decimal(c["result"]["value"]), meas.unit, meas.period, meas.coverage, meas.commodity
        )
        result = calc.supply_demand_gap(meas, avail)
        gap = _ok(result)
        share = _ok(calc.gap_share_of_demand(result, avail))
        status = (
            "not_determinable"
            if gap is None
            else "surplus"
            if gap > 0
            else "shortfall"
            if gap < 0
            else "balanced"
        )
        ids = [ctx.sources.add_input(i) for i in c["inputs"]]
        period = production["period_start"][:4]
        bid = out.balance_id()
        commodity = production["commodity"] or ""
        cname = _commodity_name(ctx, commodity)
        rows = [
            {
                "period": period,
                "production": production["value"],
                "availability": c["result"]["value"],
                "gap": _num(gap),
                "status": status,
            }
        ]
        out.balances.append({
            "id": bid, "code": f"FOOD_QUANTITY_{commodity}",
            "title": T(f"{cname['en']}: production against apparent availability", f"{cname['ar']}: الإنتاج مقابل التوافر الظاهري"),
            "status": status, "status_label": SSR_LABEL[status],
            "reason": T(f"Production minus apparent availability (production + imports − exports, stock change as stated) for {period}, calculated by OSRIP.",
                        f"الإنتاج ناقص التوافر الظاهري (الإنتاج + الواردات − الصادرات، مع التغير في المخزون كما هو معلن) لعام {period}، محسوب بواسطة OSRIP."),
            "interpretation": T("Apparent availability stands in for domestic use; it is not household consumption or nutrition.",
                                "يحل التوافر الظاهري محل الاستخدام المحلي؛ وهو ليس استهلاك الأسر ولا التغذية."),
            "period": period, "period_kind": "annual", "gap": _num(gap), "gap_unit": {k: unit[k] for k in ("code", "label_en", "label_ar")} if gap is not None else None,
            "gap_share": _num(share), "supply_label": T("Production", "الإنتاج"), "demand_label": T("Apparent availability", "التوافر الظاهري"),
            "table": {"columns": [PERIOD_COL,
                                  _number_col("production", T("Production", "الإنتاج"), {k: unit[k] for k in ("code", "label_en", "label_ar")}),
                                  _number_col("availability", T("Apparent availability", "التوافر الظاهري"), {k: unit[k] for k in ("code", "label_en", "label_ar")}),
                                  _number_col("gap", T("Production minus availability", "الإنتاج ناقص التوافر"), {k: unit[k] for k in ("code", "label_en", "label_ar")}),
                                  STATUS_COL], "rows": rows},
            "charts": _bar_chart(T("Production minus apparent availability", "الإنتاج ناقص التوافر الظاهري"), "gap",
                                 T("Production minus availability", "الإنتاج ناقص التوافر"), {k: unit[k] for k in ("code", "label_en", "label_ar")}, rows),
            "evidence": ids, "constraints": [FOOD_CONSTRAINTS],
            "notes": [T(x["en"], x["ar"]) for x in c["caveats"]],
            "_scenario": ("pair", bid, period, Decimal(production["value"]), Decimal(c["result"]["value"]),
                          {k: unit[k] for k in ("code", "label_en", "label_ar")}, T("Production", "الإنتاج"), T("Apparent availability", "التوافر الظاهري")),
        })  # fmt: skip
        if gap is not None and gap != 0:
            level, basis = _priority(gap < 0, share)
            out.recs.append(Rec(
                problem=T(f"{cname['en']}: production {'below' if gap < 0 else 'above'} apparent availability", f"{cname['ar']}: الإنتاج {'أدنى من' if gap < 0 else 'أعلى من'} التوافر الظاهري"),
                evidence=T(f"Production {production['value']} vs availability {c['result']['value']} {unit['label_en']} ({period}).",
                           f"الإنتاج {production['value']} مقابل التوافر {c['result']['value']} {unit['label_ar']} ({period})."),
                action=T("Diversify import suppliers and size reserves to shelf life" if gap < 0 else "Process, store or export the surplus where feasible",
                         "تنويع موردي الاستيراد وتحديد حجم الاحتياطي وفق مدة الصلاحية" if gap < 0 else "تصنيع الفائض أو تخزينه أو تصديره حيث أمكن"),
                quantity=_num(abs(gap)), quantity_unit={k: unit[k] for k in ("code", "label_en", "label_ar")},
                quantity_note=T("Size of the gap in the latest period (calculated).", "حجم الفجوة في آخر فترة (محسوب)."),
                horizon="medium", constraints=FOOD_CONSTRAINTS,
                outcome=T("Covers the gap without assuming any price or cost.", "يغطي الفجوة دون افتراض أي سعر أو تكلفة."),
                priority=level, priority_basis=basis, kpi=T("Production minus apparent availability (tonnes)", "الإنتاج ناقص التوافر الظاهري (طن)"),
                nature="recommendation", balance=bid, evidence_ids=ids))  # fmt: skip


# ------------------------------------------------------------------ trade


TRADE_CONSTRAINTS = T(
    "Product-level demand; logistics (ports, transit, storage); concentration of suppliers; access to export markets and their standards.",
    "الطلب على مستوى المنتج؛ والخدمات اللوجستية (الموانئ والعبور والتخزين)؛ وتركّز الموردين؛ والنفاذ إلى أسواق التصدير ومعاييرها.",
)
TRADE_LABEL = {
    "surplus": T("Trade surplus", "فائض تجاري"),
    "shortfall": T("Trade deficit", "عجز تجاري"),
    "balanced": T("Balanced trade", "تجارة متوازنة"),
    "not_determinable": T("Cannot be determined", "لا يمكن تحديده"),
}
GROUP_LABEL = {
    "surplus": T("Net exporter", "مصدّر صافٍ"),
    "shortfall": T("Net importer", "مستورد صافٍ"),
    "balanced": T("Exports equal imports", "الصادرات تساوي الواردات"),
    "not_determinable": T("Cannot be determined", "لا يمكن تحديده"),
}
PRODUCT_GROUPS = (
    (
        "BASE_METALS",
        "TRADE_NONOIL_BASE_METALS_EXPORTS",
        "TRADE_IMPORTS_BASE_METALS",
        T("Base metals and articles", "المعادن الخسيسة ومصنوعاتها"),
    ),
    (
        "PRECIOUS",
        "TRADE_NONOIL_PRECIOUS_EXPORTS",
        "TRADE_IMPORTS_PRECIOUS",
        T("Precious metals and stones", "المعادن الثمينة والأحجار الكريمة"),
    ),
)


def _value_balance(ctx: Ctx, out: SectorOut, code: str, title: dict[str, str], exports: SeriesOut | None, imports: SeriesOut | None,
                   labels: dict[str, dict[str, str]], interpretation: dict[str, str], published: SeriesOut | None = None,
                   note: dict[str, str] | None = None) -> dict[str, Any]:  # fmt: skip
    bid = out.balance_id()
    by: dict[str, dict[str, Any]] = {}
    evidence: list[str] = []
    unit: dict[str, str] | None = None
    latest: tuple[str, Decimal | None, Decimal | None, Decimal, Decimal] | None = None
    exp_obs = {o["period_start"]: o for o in (exports.observations if exports else [])}
    imp_obs = {o["period_start"]: o for o in (imports.observations if imports else [])}
    pub_obs = {o["period_start"]: o for o in (published.observations if published else [])}
    kind = ctx.p.period_kind
    latest_ids: list[str] = []
    for start in sorted(set(exp_obs) | set(imp_obs)):
        e, i = exp_obs.get(start), imp_obs.get(start)
        row = {"period": _label(e or i, kind), "exports": e["value"] if e else None, "imports": i["value"] if i else None,  # type: ignore[arg-type]
               "balance": None, "published": None, "status": "not_determinable"}  # fmt: skip
        ids: list[str] = []
        if e is not None:
            ids.append(ctx.sources.add(exports.meta, e))  # type: ignore[union-attr]
            unit = unit or _unit(exports.meta)  # type: ignore[union-attr]
        if i is not None:
            ids.append(ctx.sources.add(imports.meta, i))  # type: ignore[union-attr]
            unit = unit or _unit(imports.meta)  # type: ignore[union-attr]
        evidence += ids
        if e is not None and i is not None and exports and imports:
            em, im = _measurement(exports.meta, e), _measurement(imports.meta, i)
            balance = _ok(calc.trade_balance(em, im))
            share = _ok(calc.gap_share_of_demand(calc.trade_balance(em, im), im))
            row["balance"] = _num(balance)
            if balance is not None:
                row["status"] = (
                    "surplus" if balance > 0 else "shortfall" if balance < 0 else "balanced"
                )
                latest = (row["period"], balance, share, em.value, im.value)  # type: ignore[assignment]
                latest_ids = ids
        p = pub_obs.get(start)
        if p is not None and published is not None:
            row["published"] = p["value"]
            evidence.append(ctx.sources.add(published.meta, p))
        by[start] = row
    rows = [by[k] for k in sorted(by)]
    unit = unit or {
        "code": "million_OMR",
        "label_en": "million OMR",
        "label_ar": "مليون ريال عماني",
    }
    columns = [PERIOD_COL, _number_col("exports", labels["exports"], unit), _number_col("imports", labels["imports"], unit),
               _number_col("balance", labels["balance"], unit)]  # fmt: skip
    if published is not None:
        columns.append(_number_col("published", T("Published balance", "الميزان المنشور"), unit))
    else:
        for r in rows:
            r.pop("published")
    columns.append(STATUS_COL)
    status = (
        "not_determinable"
        if latest is None
        else ("surplus" if latest[1] > 0 else "shortfall" if latest[1] < 0 else "balanced")
    )  # type: ignore[operator]
    label_map = TRADE_LABEL if code == "TRADE_MERCHANDISE" else GROUP_LABEL
    charts = _line_chart(
        title, {"exports": labels["exports"], "imports": labels["imports"]}, unit, rows
    )
    charts += _bar_chart(labels["balance"], "balance", labels["balance"], unit, rows)
    record = {
        "id": bid, "code": code, "title": title, "status": status, "status_label": label_map[status],
        "reason": T(f"Exports minus imports for {latest[0]}, calculated by OSRIP from published values.", f"الصادرات ناقص الواردات لـ{latest[0]}، محسوبة بواسطة OSRIP من القيم المنشورة.")
        if latest else T("Exports and imports are not both published for the same period.", "لا تُنشر الصادرات والواردات معاً للفترة نفسها."),
        "interpretation": interpretation,
        "period": latest[0] if latest else None, "period_kind": kind,
        "gap": _num(latest[1]) if latest else None, "gap_unit": unit if latest else None,
        "gap_share": _num(latest[2]) if latest else None,
        "supply_label": labels["exports"], "demand_label": labels["imports"],
        "table": {"columns": columns, "rows": rows}, "charts": charts, "evidence": evidence if latest else evidence,
        "constraints": [TRADE_CONSTRAINTS], "notes": [note] if note else [],
    }  # fmt: skip
    out.balances.append(record)
    if latest is not None:
        record["_latest"] = latest
        record["_latest_ids"] = latest_ids
    return record


def trade(ctx: Ctx) -> SectorOut:
    out = SectorOut(forecast_indicator="TRADE_MERCH_IMPORTS")
    exports, _ = ctx.series("TRADE_MERCH_EXPORTS")
    imports, _ = ctx.series("TRADE_MERCH_IMPORTS", flow="import")
    published, _ = ctx.series("TRADE_BALANCE_REPORTED")
    main = _value_balance(
        ctx, out, "TRADE_MERCHANDISE", T("Merchandise trade balance", "الميزان التجاري السلعي"), exports, imports,
        {"exports": T("Merchandise exports", "الصادرات السلعية"), "imports": T("Merchandise imports", "الواردات السلعية"),
         "balance": T("Exports minus imports (calculated)", "الصادرات ناقص الواردات (محسوب)")},
        T("A positive balance is a trade surplus and a negative one a deficit, by value in nominal terms. It is not a profit or loss, and it says nothing about whether particular goods are short.",
          "الميزان الموجب فائض تجاري والسالب عجز، بالقيمة الاسمية. وهو ليس ربحاً ولا خسارة، ولا يبيّن نقص سلع بعينها."),
        published,
        T("The published balance is shown beside the calculated one; where they differ, both are kept.", "يُعرض الميزان المنشور بجانب المحسوب؛ وعند اختلافهما يُحتفظ بالاثنين."),
    )  # fmt: skip
    groups = []
    for code, exp_code, imp_code, name in PRODUCT_GROUPS:
        e, _ = ctx.series(exp_code)
        i, _ = ctx.series(imp_code)
        if e is None and i is None:
            continue
        groups.append(_value_balance(
            ctx, out, f"TRADE_GROUP_{code}", T(f"{name['en']}: net trade", f"{name['ar']}: صافي التجارة"), e, i,
            {"exports": T("Non-oil exports", "الصادرات غير النفطية"), "imports": T("Imports", "الواردات"),
             "balance": T("Exports minus imports (calculated)", "الصادرات ناقص الواردات (محسوب)")},
            T("Domestic non-oil exports minus recorded imports of the product group. Re-exports of the group are not published by group and are not included, so this is not a measure of domestic demand.",
              "الصادرات غير النفطية المحلية ناقص الواردات المسجلة لمجموعة المنتجات. ولا تُنشر إعادة التصدير حسب المجموعة فلا تُدرج، لذا فهذا ليس مقياساً للطلب المحلي."),
        ))  # fmt: skip
    if ctx.data_mode is DataMode.SYNTHETIC:
        groups += _synthetic_commodities(ctx, out)
    # Evidence for the recommendations: the oil and gas share of exports, import concentration.
    oil_share: Decimal | None = None
    oil_ids: list[str] = []
    oil, _ = ctx.series("TRADE_OIL_GAS_EXPORTS")
    if oil and exports:
        common = sorted(
            {o["period_start"] for o in oil.observations}
            & {o["period_start"] for o in exports.observations}
        )
        if common:
            o1 = next(o for o in oil.observations if o["period_start"] == common[-1])
            e1 = next(o for o in exports.observations if o["period_start"] == common[-1])
            oil_share = _ok(
                calc.share_of_total(_measurement(oil.meta, o1), _measurement(exports.meta, e1))
            )
            if oil_share is not None:
                oil_ids = [ctx.sources.add(oil.meta, o1), ctx.sources.add(exports.meta, e1)]
                out.summary.append(T(f"Oil and gas made up {_fmt(oil_share)}% of merchandise exports in {_label(e1, ctx.p.period_kind)} (calculated).",
                                     f"شكّل النفط والغاز {_fmt(oil_share)}٪ من الصادرات السلعية في {_label(e1, ctx.p.period_kind)} (محسوب)."))  # fmt: skip
    largest: tuple[str, dict[str, str], Decimal, bool] | None = None
    conc_ids: list[str] = []
    _, partner_series = ctx.series("TRADE_MERCH_IMPORTS", flow="import", partners=True)
    if partner_series and imports:
        latest_start = max(
            (o["period_start"] for s in partner_series for o in s.observations), default=None
        )
        total_o = next((o for o in imports.observations if o["period_start"] == latest_start), None)
        if latest_start and total_o is not None:
            parts = {}
            names = {}
            for s in partner_series:
                o = next((x for x in s.observations if x["period_start"] == latest_start), None)
                if o is not None:
                    code = s.meta["partner"]["code"]
                    parts[code] = _measurement(s.meta, o)
                    names[code] = T(s.meta["partner"]["name_en"], s.meta["partner"]["name_ar"])
                    conc_ids.append(ctx.sources.add(s.meta, o))
            conc = calc.partner_concentration(parts, _measurement(imports.meta, total_o))
            value = _ok(conc.largest_share)
            if value is not None and conc.largest_partner:
                conc_ids.append(ctx.sources.add(imports.meta, total_o))
                largest = (
                    conc.largest_partner,
                    names[conc.largest_partner],
                    value,
                    conc.coverage_complete,
                )
                out.summary.append(T(f"The largest import partner, {names[conc.largest_partner]['en']}, supplied {_fmt(value)}% of recorded imports in {_label(total_o, ctx.p.period_kind)} (calculated from published partner values).",
                                     f"زوّد أكبر شريك استيراد، {names[conc.largest_partner]['ar']}، {_fmt(value)}٪ من الواردات المسجلة في {_label(total_o, ctx.p.period_kind)} (محسوب من قيم الشركاء المنشورة)."))  # fmt: skip
    latest = main.pop("_latest", None)
    main_ids: list[str] = main.pop("_latest_ids", [])
    if latest is not None:
        period, balance, share, exp_v, imp_v = latest
        word_en, word_ar = (
            ("surplus", "فائض")
            if balance > 0
            else ("deficit", "عجز")
            if balance < 0
            else ("balance", "توازن")
        )
        unit = main["gap_unit"]
        out.summary.insert(0, T(f"Merchandise trade in {period}: {word_en} of {_fmt(abs(balance))} {unit['label_en']} (exports {_fmt(exp_v)} minus imports {_fmt(imp_v)}; calculated by OSRIP from published values).",
                                f"التجارة السلعية في {period}: {word_ar} قدره {_fmt(abs(balance))} {unit['label_ar']} (الصادرات {_fmt(exp_v)} ناقص الواردات {_fmt(imp_v)}؛ محسوب بواسطة OSRIP من القيم المنشورة)."))  # fmt: skip
        out.scenario_base = (
            "pair",
            main["id"],
            period,
            exp_v,
            imp_v,
            unit,
            T("Exports", "الصادرات"),
            T("Imports", "الواردات"),
        )
        level, basis = _priority(balance < 0, share)
        ev = T(f"Exports {_fmt(exp_v)} and imports {_fmt(imp_v)} {unit['label_en']} ({period}); balance {_signed(balance)}.",
               f"الصادرات {_fmt(exp_v)} والواردات {_fmt(imp_v)} {unit['label_ar']} ({period})؛ الميزان {_signed(balance)}.")  # fmt: skip
        if balance < 0:
            out.recs.append(Rec(
                problem=T("Merchandise trade deficit", "عجز في الميزان التجاري السلعي"), evidence=ev,
                action=T("Review the largest import groups for supplier diversification and for local production where demand and capability exist.", "مراجعة أكبر مجموعات الواردات لتنويع الموردين وللإنتاج المحلي حيث يتوفر الطلب والقدرة."),
                quantity=_num(abs(balance)), quantity_unit=unit, quantity_note=T("Size of the deficit in the latest period (calculated).", "حجم العجز في آخر فترة (محسوب)."),
                horizon="medium", constraints=TRADE_CONSTRAINTS,
                outcome=T("A smaller deficit or a more resilient supply. Assumes product-level demand data are obtained first.", "عجز أصغر أو إمداد أكثر مرونة. ويفترض الحصول أولاً على بيانات الطلب على مستوى المنتج."),
                priority=level, priority_basis=basis, kpi=T("Merchandise trade balance (million OMR)", "الميزان التجاري السلعي (مليون ريال عماني)"),
                nature="recommendation", balance=main["id"], evidence_ids=main_ids))  # fmt: skip
        elif balance > 0:
            dependent = oil_share is not None and oil_share >= 50
            out.recs.append(Rec(
                problem=T("A surplus that rests on oil and gas" if dependent else "Merchandise trade surplus", "فائض يعتمد على النفط والغاز" if dependent else "فائض في الميزان التجاري السلعي"),
                evidence=T(ev["en"] + (f" Oil and gas: {_fmt(oil_share)}% of exports." if oil_share is not None else ""),
                           ev["ar"] + (f" النفط والغاز: {_fmt(oil_share)}٪ من الصادرات." if oil_share is not None else "")),
                action=T("Widen non-oil exports: add value to existing non-oil products and widen market access.", "توسيع الصادرات غير النفطية: إضافة القيمة إلى المنتجات غير النفطية القائمة وتوسيع النفاذ إلى الأسواق."),
                quantity_note=T("Not quantified: no target is published.", "غير محدد كمياً: لا يوجد هدف منشور."), horizon="long", constraints=TRADE_CONSTRAINTS,
                outcome=T("A surplus less exposed to oil and gas prices. Assumes markets and standards can be met.", "فائض أقل تعرضاً لأسعار النفط والغاز. ويفترض إمكانية استيفاء متطلبات الأسواق والمعايير."),
                priority="high" if dependent else "low",
                priority_basis=T("High: oil and gas are at least half of exports, so the surplus depends on them." if dependent else "Low: a surplus with no dependence signal.",
                                 "عالية: يشكّل النفط والغاز نصف الصادرات على الأقل، فالفائض يعتمد عليهما." if dependent else "منخفضة: فائض دون مؤشر اعتماد."),
                kpi=T("Non-oil share of merchandise exports (%)", "حصة الصادرات غير النفطية من الصادرات السلعية (٪)"),
                nature="recommendation", balance=main["id"], evidence_ids=list(dict.fromkeys(main_ids + oil_ids))))  # fmt: skip
    if largest is not None:
        code, name, value, complete = largest
        level = "medium" if value >= 25 else "low"
        out.recs.append(Rec(
            problem=T("Import supplier concentration", "تركّز موردي الواردات"),
            evidence=T(f"{name['en']} supplied {_fmt(value)}% of recorded imports" + ("" if complete else " (listed partners do not cover the total)") + ".",
                       f"زوّد {name['ar']} {_fmt(value)}٪ من الواردات المسجلة" + ("" if complete else " (الشركاء المدرجون لا يغطون الإجمالي)") + "."),
            action=T("Diversify suppliers for essential import groups and track the largest partner's share.", "تنويع الموردين لمجموعات الواردات الأساسية ومتابعة حصة أكبر شريك."),
            quantity_note=T("Not quantified: concentration is not a probability of disruption.", "غير محدد كمياً: التركّز ليس احتمالاً للانقطاع."),
            horizon="medium", constraints=TRADE_CONSTRAINTS,
            outcome=T("Less exposure to a single partner. Assumes alternative suppliers exist at acceptable terms.", "تعرّض أقل لشريك واحد. ويفترض وجود موردين بدلاء بشروط مقبولة."),
            priority=level, priority_basis=T(f"Rule: largest partner share {_fmt(value)}% ({'at least' if value >= 25 else 'below'} 25%) → {level}.",
                                             f"القاعدة: حصة أكبر شريك {_fmt(value)}٪ ({'لا تقل عن' if value >= 25 else 'أقل من'} 25٪) ← {'متوسطة' if level == 'medium' else 'منخفضة'}."),
            kpi=T("Largest import partner share (%)", "حصة أكبر شريك استيراد (٪)"), nature="recommendation", balance=main["id"], evidence_ids=conc_ids))  # fmt: skip
    for g in groups:
        g_latest = g.pop("_latest", None)
        g_ids: list[str] = g.pop("_latest_ids", [])
        if g_latest is None:
            continue
        period, balance, share, exp_v, imp_v = g_latest
        if balance == 0:
            continue
        level, basis = _priority(balance < 0, share)
        out.recs.append(Rec(
            problem=T(f"{g['title']['en']}: {'net importer' if balance < 0 else 'net exporter'}", f"{g['title']['ar']}: {'مستورد صافٍ' if balance < 0 else 'مصدّر صافٍ'}"),
            evidence=T(f"Non-oil exports {_fmt(exp_v)}, imports {_fmt(imp_v)} {g['gap_unit']['label_en']} ({period}).",
                       f"الصادرات غير النفطية {_fmt(exp_v)}، والواردات {_fmt(imp_v)} {g['gap_unit']['label_ar']} ({period})."),
            action=T("Assess local processing to replace part of the imports, and diversify suppliers meanwhile." if balance < 0 else "Add value before export and widen market access for the group.",
                     "تقييم التصنيع المحلي ليحل محل جزء من الواردات، وتنويع الموردين في الأثناء." if balance < 0 else "إضافة القيمة قبل التصدير وتوسيع النفاذ إلى الأسواق للمجموعة."),
            quantity=_num(abs(balance)), quantity_unit=g["gap_unit"], quantity_note=T("Net trade of the group in the latest period (calculated).", "صافي تجارة المجموعة في آخر فترة (محسوب)."),
            horizon="long" if balance < 0 else "medium", constraints=TRADE_CONSTRAINTS,
            outcome=T("A smaller net import need, if local processing is viable." if balance < 0 else "Higher export value per unit.",
                      "حاجة أقل إلى صافي الاستيراد إذا كان التصنيع المحلي مجدياً." if balance < 0 else "قيمة تصديرية أعلى للوحدة."),
            priority=level, priority_basis=basis, kpi=T("Net trade of the group (million OMR)", "صافي تجارة المجموعة (مليون ريال عماني)"),
            nature="recommendation", balance=g["id"], evidence_ids=g_ids))  # fmt: skip
    out.gap(main["id"], T("Product-level demand (apparent consumption) in quantities", "الطلب على مستوى المنتج (الاستهلاك الظاهري) بالكميات"),
            T("Saying whether particular goods are short or in surplus.", "تحديد ما إذا كانت سلع بعينها ناقصة أو فائضة."))  # fmt: skip
    out.gap(None, T("Re-exports by product group", "إعادة التصدير حسب مجموعة المنتجات"), T("A complete net trade position per group.", "صافي مركز تجاري كامل لكل مجموعة."))  # fmt: skip
    out.gap(None, T("Logistics indicators (port throughput, clearance and transit times)", "مؤشرات لوجستية (طاقة الموانئ وأزمنة التخليص والعبور)"),
            T("Judging whether logistics constrain supply.", "الحكم على ما إذا كانت الخدمات اللوجستية تقيّد الإمداد."))  # fmt: skip
    out.gap(None, T("Market access conditions for non-oil exports (tariffs, standards)", "شروط النفاذ إلى الأسواق للصادرات غير النفطية (التعريفات والمعايير)"),
            T("Ranking export opportunities.", "ترتيب فرص التصدير."))  # fmt: skip
    out.method = T("Published exports and imports of the national total (and of product groups published on both sides) are compared for each period of the selected kind; the balance is exports minus imports by value, calculated by OSRIP. The published balance is shown beside it. Import partner shares use the stated total.",
                   "تُقارن الصادرات والواردات المنشورة للإجمالي الوطني (ولمجموعات المنتجات المنشورة على الجانبين) لكل فترة من النوع المختار؛ والميزان هو الصادرات ناقص الواردات بالقيمة، وتحسبه OSRIP. ويُعرض الميزان المنشور بجانبه. وتُحسب حصص شركاء الاستيراد من الإجمالي المعلن.")  # fmt: skip
    out.assumptions.append(
        T(
            "Values are nominal Omani rials and are not adjusted for inflation.",
            "القيم بالريال العماني الاسمي وغير معدلة للتضخم.",
        )
    )
    out.scenario_reason = T(
        "No trade balance can be determined for a scenario.", "لا يمكن تحديد ميزان تجاري لسيناريو."
    )
    return out


def _synthetic_commodities(ctx: Ctx, out: SectorOut) -> list[dict[str, Any]]:
    """Synthetic demonstration data: export and import values per commodity."""
    records = []
    found = query_observations(ctx.session, ObservationQuery(ctx.data_mode, indicator="TRADE_VALUE", area=ctx.p.area,
                                                             period_kind=ctx.p.period_kind, partner="total"), allow_mixed=True)  # fmt: skip
    by: dict[str, dict[str, SeriesOut]] = {}
    for s in found:
        if (
            s.meta["partner"] is None
            and s.meta["commodity"] is not None
            and s.meta["flow"] in ("import", "domestic_export")
        ):
            by.setdefault(s.meta["commodity"]["code"], {})[s.meta["flow"]] = s
    for commodity, flows in sorted(by.items()):
        name = flows.get("import") or flows.get("domestic_export")
        assert name is not None
        cname = T(name.meta["commodity"]["name_en"], name.meta["commodity"]["name_ar"])
        records.append(_value_balance(
            ctx, out, f"TRADE_COMMODITY_{commodity}", T(f"{cname['en']}: net trade", f"{cname['ar']}: صافي التجارة"),
            flows.get("domestic_export"), flows.get("import"),
            {"exports": T("Domestic exports", "الصادرات المحلية"), "imports": T("Imports", "الواردات"),
             "balance": T("Exports minus imports (calculated)", "الصادرات ناقص الواردات (محسوب)")},
            T("Exports minus imports of the commodity by value.", "صادرات السلعة ناقص وارداتها بالقيمة.")))  # fmt: skip
    return records


SECTORS: dict[str, Callable[[Ctx], SectorOut]] = {
    "electricity": electricity,
    "water": water,
    "food_security": food_security,
    "trade": trade,
}


# ------------------------------------------------------------------ scenario and forecast


def _scenario(p: BalanceParams, out: SectorOut) -> dict[str, Any]:
    if not p.scenario:
        return {"status": "not_requested", "reason": T("No scenario assumptions were given. Enter supply growth, demand growth and years to project the balance.",
                                                      "لم تُعطَ افتراضات للسيناريو. أدخل نمو العرض ونمو الطلب وعدد السنوات لإسقاط الميزان.")}  # fmt: skip
    if out.scenario_base is None:
        return {
            "status": "not_applicable",
            "reason": out.scenario_reason
            or T("No balance can be determined.", "لا يمكن تحديد ميزان."),
        }
    assert (
        p.supply_growth_pct is not None and p.demand_growth_pct is not None and p.years is not None
    )
    gs, gd, years = p.supply_growth_pct, p.demand_growth_pct, p.years
    assumptions = [
        T(f"Supply grows {_signed(gs)}% a year and demand {_signed(gd)}% a year for {years} years (stated by the user; not a forecast).",
          f"ينمو العرض {_signed(gs)}٪ سنوياً والطلب {_signed(gd)}٪ سنوياً لمدة {years} سنوات (كما ذكرها المستخدم؛ وليس تنبؤاً)."),
        T("Everything else stays as in the base period.", "يبقى كل ما عدا ذلك كما في فترة الأساس."),
    ]  # fmt: skip
    base = out.scenario_base
    basis_col = {"key": "basis", "label": T("Basis", "الأساس"), "kind": "text"}
    year_col = {"key": "period", "label": T("Year", "السنة"), "kind": "period"}
    if base[0] == "ratio":
        _, bid, period, ratio, title = base
        start = int(str(period)[:4]) if str(period)[:4].isdigit() else None
        factor = (Decimal(1) + gs / HUNDRED) / (Decimal(1) + gd / HUNDRED)
        rows = [
            {
                "period": str(period),
                "ratio": _num(ratio),
                "gap": _num(ratio - HUNDRED),
                "basis": "base",
            }
        ]
        value = ratio
        for n in range(1, years + 1):
            value = value * factor
            rows.append({"period": str(start + n) if start else f"+{n}", "ratio": _num(value.quantize(Decimal("0.0001"))),
                         "gap": _num((value - HUNDRED).quantize(Decimal("0.0001"))), "basis": "scenario"})  # fmt: skip
        table = {"columns": [year_col, _number_col("ratio", T("Self-sufficiency ratio (scenario)", "نسبة الاكتفاء الذاتي (سيناريو)"), PERCENT),
                             _number_col("gap", T("Production minus consumption (scenario)", "الإنتاج ناقص الاستهلاك (سيناريو)"), POINTS), basis_col], "rows": rows}  # fmt: skip
        charts = [{"type": "line", "title": T(f"{title['en']}: scenario", f"{title['ar']}: سيناريو"), "x": "period", "unit": POINTS,
                   "series": [{"column": "gap", "label": T("Production minus consumption", "الإنتاج ناقص الاستهلاك"), "nature": "scenario"}]}]  # fmt: skip
        return {
            "status": "ok",
            "assumptions": assumptions,
            "balance": bid,
            "table": table,
            "charts": charts,
        }
    _, bid, period, supply, demand, unit, supply_label, demand_label = base
    start = int(str(period)[:4]) if str(period)[:4].isdigit() else None
    sup = calc.compound_projection(supply, gs, years)
    dem = calc.compound_projection(demand, gd, years)
    q = Decimal("0.0001")
    rows = [
        {
            "period": str(period),
            "supply": _num(supply),
            "demand": _num(demand),
            "gap": _num(supply - demand),
            "basis": "base",
        }
    ]
    for n in range(years):
        rows.append({"period": str(start + n + 1) if start else f"+{n + 1}", "supply": _num(sup[n].quantize(q)),
                     "demand": _num(dem[n].quantize(q)), "gap": _num((sup[n] - dem[n]).quantize(q)), "basis": "scenario"})  # fmt: skip
    table = {"columns": [year_col, _number_col("supply", T(f"{supply_label['en']} (scenario)", f"{supply_label['ar']} (سيناريو)"), unit),
                         _number_col("demand", T(f"{demand_label['en']} (scenario)", f"{demand_label['ar']} (سيناريو)"), unit),
                         _number_col("gap", T("Gap (scenario)", "الفجوة (سيناريو)"), unit), basis_col], "rows": rows}  # fmt: skip
    charts = [
        {"type": "line", "title": T("Supply and demand under the scenario", "العرض والطلب وفق السيناريو"), "x": "period", "unit": unit,
         "series": [{"column": "supply", "label": supply_label, "nature": "scenario"}, {"column": "demand", "label": demand_label, "nature": "scenario"}]},
        {"type": "bar", "title": T("Gap under the scenario", "الفجوة وفق السيناريو"), "x": "period", "unit": unit,
         "series": [{"column": "gap", "label": T("Gap", "الفجوة"), "nature": "scenario"}]},
    ]  # fmt: skip
    return {
        "status": "ok",
        "assumptions": assumptions,
        "balance": bid,
        "table": table,
        "charts": charts,
    }


def _forecast(ctx: Ctx, indicator: str | None) -> dict[str, Any]:
    if indicator is None:
        return {"status": "not_available", "text": T("Self-sufficiency ratios are not forecast; no forecast interval is shown.",
                                                     "لا يُتنبأ بنسب الاكتفاء الذاتي؛ ولا يُعرض أي مجال تنبؤ.")}  # fmt: skip
    report = forecasting.eligibility(ctx.session, ctx.data_mode)
    row = next((r for r in report["series"] if r["indicator"]["code"] == indicator and r["area"]["code"] == ctx.p.area
                and r.get("partner") is None and r.get("commodity") is None and r["frequency"] == "annual"), None)  # fmt: skip
    if row is None:
        return {"status": "not_available", "indicator": indicator,
                "text": T("No regular published series of the demand measure is available to the forecasting method; no forecast interval is shown.",
                          "لا تتوفر سلسلة منشورة منتظمة لمقياس الطلب لطريقة التنبؤ؛ ولا يُعرض أي مجال تنبؤ.")}  # fmt: skip
    if row["eligible"]:
        return {"status": "eligible", "indicator": indicator,
                "text": T("The forecasting method accepts the demand series; its forecast, with 80% and 95% intervals, is on the Forecasts page and is not mixed into this balance.",
                          "تقبل طريقة التنبؤ سلسلة الطلب؛ ويُعرض التنبؤ بها مع مجالي 80٪ و95٪ في صفحة التنبؤات، ولا يُدمج في هذا الميزان.")}  # fmt: skip
    reasons_en = (
        "; ".join(x.get("en", "").rstrip(". ") for x in row["reasons"])
        or "it does not meet the history requirements"
    )
    reasons_ar = (
        "؛ ".join(x.get("ar", "").rstrip(". ") for x in row["reasons"])
        or "لا تستوفي متطلبات طول السلسلة"
    )
    return {"status": "withheld", "indicator": indicator,
            "text": T(f"No forecast interval is shown: the forecasting method withholds the demand series ({reasons_en}).",
                      f"لا يُعرض مجال تنبؤ: تحجب طريقة التنبؤ سلسلة الطلب ({reasons_ar}).")}  # fmt: skip


# ------------------------------------------------------------------ the analysis


COMMON_LIMITATIONS = [
    T(
        "Statistics from 2022 onward are used; any older figure is labelled as context.",
        "تُستخدم الإحصاءات من 2022 فصاعداً؛ وأي رقم أقدم يُوسم بأنه للسياق.",
    ),
    T(
        "Recommendations are decision support from fixed rules, not guaranteed outcomes. Costs are not estimated.",
        "التوصيات دعم للقرار وفق قواعد ثابتة، وليست نتائج مضمونة. ولا تُقدَّر التكاليف.",
    ),
    T(
        "Missing values stay missing; they are never treated as zero.",
        "تبقى القيم المفقودة مفقودة؛ ولا تُعامل صفراً أبداً.",
    ),
]


def build(session: Session, params: dict[str, Any], data_mode: DataMode) -> dict[str, Any]:
    """Validate the parameters, run the sector's analysis and validate the result."""
    from app.core.errors import unprocessable

    try:
        p = BalanceParams.model_validate(params)
    except ValueError as exc:
        raise unprocessable("invalid_analysis_parameters", "The analysis parameters are not valid.",
                            {"errors": str(exc)[:500]}) from exc  # fmt: skip
    ctx = Ctx(session, data_mode, p, Sources(session, data_mode))
    out = SECTORS[p.sector](ctx)
    name = SECTOR_NAME[p.sector]
    determined = [b for b in out.balances if b["status"] != "not_determinable"]
    status = (
        "ok"
        if determined and len(determined) == len(out.balances)
        else "partial"
        if determined
        else "not_available"
    )
    for b in out.balances:
        b.pop("_latest", None)
        b.pop("_latest_ids", None)
    recs = []
    order = {"high": 0, "medium": 1, "low": 2, "conditional": 3}
    for n, r in enumerate(sorted(out.recs, key=lambda r: order[r.priority]), start=1):
        recs.append({
            "id": f"R{n}", "balance": r.balance, "problem": r.problem, "evidence": r.evidence,
            "evidence_ids": list(dict.fromkeys(r.evidence_ids)), "action": r.action, "quantity": r.quantity,
            "quantity_unit": r.quantity_unit, "quantity_note": r.quantity_note, "horizon": r.horizon,
            "constraints": r.constraints, "cost": COST_UNKNOWN, "outcome": r.outcome, "priority": r.priority,
            "priority_basis": r.priority_basis, "kpi": r.kpi, "nature": r.nature,
        })  # fmt: skip
    for b in out.balances:
        b["evidence"] = list(dict.fromkeys(b["evidence"]))
    sources = ctx.sources.items
    doc = {
        "schema": schema.SCHEMA,
        "kind": "supply_balance",
        "sector": p.sector,
        "status": status,
        "title": T(f"Shortage and surplus: {name['en']}", f"العجز والفائض: {name['ar']}"),
        "question": T(f"Where does supply fall short of, or exceed, demand in {name['en'].lower()}, and what can be done?",
                      f"أين يقصر العرض عن الطلب أو يتجاوزه في {name['ar']}، وما الذي يمكن عمله؟"),
        "params": p.model_dump(mode="json"),
        "data_mode": data_mode.value,
        "dataset_versions": sorted({s["dataset_version"] for s in sources}),
        "summary": out.summary + [T("These results are decision support: options to assess, not guaranteed outcomes.",
                                    "هذه النتائج دعم للقرار: خيارات للتقييم وليست نتائج مضمونة.")],
        "balances": out.balances,
        "recommendations": recs,
        "prioritization": PRIORITIZATION,
        "data_gaps": [{"id": f"G{n}", **g} for n, g in enumerate(out.gaps, start=1)],
        "scenario": _scenario(p, out),
        "forecast": _forecast(ctx, out.forecast_indicator),
        "sources": sources,
        "method": out.method,
        "assumptions": out.assumptions,
        "limitations": out.limitations + COMMON_LIMITATIONS,
    }  # fmt: skip
    return schema.validate(doc)


# ------------------------------------------------------------------ run, store, read


def run(
    session: Session, params: dict[str, Any], data_mode: DataMode, user_id: uuid.UUID | None
) -> dict[str, Any]:
    """Build and store an analysis (as a study run of kind ``supply_balance``)."""
    from app.services import studies

    document = build(session, params, data_mode)
    return out(studies.store(session, document, user_id=user_id))


def get(session: Session, analysis_id: uuid.UUID) -> Any:
    from app.core.errors import not_found
    from app.models import StudyRun
    from app.services.studies import BALANCE_KIND

    row = session.get(StudyRun, analysis_id)
    if row is None or row.kind != BALANCE_KIND:
        raise not_found("analysis")
    return row


def out(row: Any) -> dict[str, Any]:
    return {"id": str(row.id), "created_at": row.created_at.isoformat() if row.created_at else None,
            "sha256": row.result_sha256, "analysis": row.result}  # fmt: skip


def reproduce(session: Session, analysis_id: uuid.UUID) -> dict[str, Any]:
    """Rebuild from the stored parameters: identical unless newer data were published since."""
    from app.services.studies import checksum

    row = get(session, analysis_id)
    fresh = build(session, row.params, DataMode(row.data_mode))
    return {"id": str(row.id), "identical": checksum(fresh) == row.result_sha256,
            "stored_versions": row.dataset_versions, "current_versions": fresh["dataset_versions"]}  # fmt: skip
