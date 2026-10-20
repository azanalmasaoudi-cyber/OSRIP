"""Section calculations (booklet 3.5-3.8, Table 3.1) over published observations.

Each calculation is a transparent record: title, formula, every input with its
provenance, the result (or the reason it is unavailable) and the caveats that
must travel with it. Arithmetic is delegated to ``app.domain.calculations``;
this module only chooses compatible inputs and explains the outcome.

Source rules:
* A change over time compares observations of one dataset version only.
* Food and trade frames may combine components from different sources (e.g.
  production from one publisher, trade from another), but if two published
  sources report the same component the calculation is withheld rather than
  choosing one silently.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domain import calculations as calc
from app.domain.enums import DataMode, Frequency, Section
from app.domain.explanations import explain
from app.domain.results import CalcResult, CalcStatus
from app.services.analysis.evidence import Evidence, evidence_from, index
from app.services.observations import ObservationQuery, query_observations

PERCENT = {"code": "percent", "label_en": "%", "label_ar": "٪"}
FRACTION = {"code": "fraction", "label_en": "(0–1 scale)", "label_ar": "(مقياس 0–1)"}

# Domestic exports only: re-exports are a separate flow (SPEC_CONFLICTS C3).
EXPORT_FLOW = "domestic_export"
PERCENTAGE_POINTS = {
    "code": "percentage_points",
    "label_en": "percentage points",
    "label_ar": "نقطة مئوية",
}
# Booklet indicators with their own frame calculations below; changes are not repeated for them.
FRAME_INDICATORS = {"FOOD_PRODUCTION", "FOOD_STOCK_INCREASE", "TRADE_QUANTITY", "TRADE_VALUE"}
COMPARABLE_KINDS = {"annual", "year_to_date", "quarterly", "monthly"}


@dataclass(frozen=True, slots=True)
class AnalysisFilter:
    data_mode: DataMode
    commodity: str | None = None
    area: str | None = None
    frequency: Frequency | None = None
    period_from: Any = None
    period_to: Any = None
    stock_assumption: calc.StockAssumption = calc.StockAssumption.ASSUMED_ZERO
    dataset_version_id: uuid.UUID | None = None
    period_kind: str | None = None  # annual | year_to_date | quarterly | monthly | statement

    def query(self, section: Section | None = None) -> ObservationQuery:
        return ObservationQuery(
            data_mode=self.data_mode,
            section=section,
            area=self.area,
            commodity=self.commodity,
            frequency=self.frequency,
            period_from=self.period_from,
            period_to=self.period_to,
            dataset_version_id=self.dataset_version_id,
            period_kind=self.period_kind,
        )


def _text(en: str, ar: str) -> dict[str, str]:
    return {"en": en, "ar": ar}


def _value(result: CalcResult) -> str | None:
    return None if result.value is None else format(result.value, "f")


def _unit(e: Evidence) -> dict[str, str]:
    return {k: e.meta["unit"][k] for k in ("code", "label_en", "label_ar")}


def _calc(
    *,
    cid: str,
    kind: str,
    section: Section,
    title: dict[str, str],
    formula: dict[str, str],
    inputs: list[dict[str, Any]],
    result: CalcResult | None,
    unit: dict[str, str] | None,
    reason_code: str | None = None,
    notes: list[dict[str, str]] | None = None,
    breakdown: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = result.status.value if result else "unavailable"
    reason = reason_code or (result.reason.value if result and result.reason else None)
    return {
        "id": cid,
        "kind": kind,
        "section": section.value,
        "title": title,
        "formula": formula,
        "inputs": inputs,
        "result": {"status": status, "value": _value(result) if result else None, "unit": unit},
        "reason": explain(reason) if reason else None,
        "caveats": [explain(c.value) for c in (result.caveats if result else ())],
        "notes": notes or [],
        "breakdown": breakdown or [],
    }


def _period_label(start: str, end: str) -> str:
    return start[:4] if start.endswith("-01-01") and end.endswith("-12-31") else f"{start}–{end}"


# ------------------------------------------------------------------ electricity and water


def _in_focus(e: Evidence, focus_area: str | None, national: set[str] | None = None) -> bool:
    """Without an area filter, an indicator that has a national total is compared at national
    level only, and components (whose parents overlap them) are skipped: regional groups,
    governorates and components are compared once the reader selects that area, so a page is
    not flooded with one card per slice. ``national`` lists indicators with national data."""
    if focus_area:
        return e.area == focus_area
    if e.meta["indicator"].get("parent_code"):
        return False
    if e.meta["area"].get("level", "national") == "national":
        return True
    return national is not None and e.indicator not in national


def _national_indicators(evidence: list[Evidence]) -> set[str]:
    return {e.indicator for e in evidence if e.meta["area"].get("level", "national") == "national"}


def _changes(
    section: Section, evidence: list[Evidence], focus_area: str | None = None
) -> list[dict[str, Any]]:
    """Absolute and percentage change between the latest two periods of each series (one version).

    Only the latest pair inside the selected years is calculated, so a long monthly series does
    not produce one card per month; the period filters select an earlier pair. A pair is
    always of one period kind (a year-to-date total is compared only with the same months of
    the previous year). Dated statements are never compared, a published inequality ("more
    than 95") is not treated as a number, and ratios change by percentage points.
    """
    out: list[dict[str, Any]] = []
    series: dict[tuple[Any, ...], list[Evidence]] = defaultdict(list)
    national = _national_indicators(evidence)
    for e in evidence:
        if e.kind not in COMPARABLE_KINDS or not _in_focus(e, focus_area, national):
            continue
        key = (
            e.version_id,
            e.indicator,
            e.area,
            e.meta["unit"]["code"],
            e.meta["frequency"],
            e.commodity,
            e.partner,
            e.flow,
            e.kind,
            e.meta.get("ytd_end_month"),
        )
        series[key].append(e)
    for key, items in series.items():
        items.sort(key=lambda e: e.period)
        name = items[0].meta["indicator"]
        kind_tag = "" if key[8] == key[4] else f":{key[8]}{key[9] or ''}"
        # Commodity, partner and flow slices (and units) of one indicator are separate series,
        # so they are part of the id: no two series' changes share one.
        slices = "".join(f":{part}" for part in (key[5], key[6], key[7], key[3]) if part)
        base = f"{key[1]}:{key[2]}:{key[4]}{kind_tag}{slices}:{key[0][:8]}"
        ratio = items[0].meta["unit"]["dimension"] == "ratio"
        if len(items) < 2:
            out.append(
                _calc(
                    cid=f"{base}:change",
                    kind="percentage_change",
                    section=section,
                    title=_text(f"Change in {name['name_en']}", f"التغير في {name['name_ar']}"),
                    formula=_text(
                        "100 × (current − previous) ÷ previous",
                        "100 × (الحالية − السابقة) ÷ السابقة",
                    ),
                    inputs=[items[0].as_input("current")],
                    result=None,
                    unit=PERCENT,
                    reason_code="no_comparable_period",
                )
            )
            continue
        pair_notes = [explain("latest_pair_only")] if len(items) > 2 else []
        for previous, current in list(zip(items, items[1:], strict=False))[-1:]:
            span = f"{_period_label(*previous.period)}→{_period_label(*current.period)}"
            inputs = [previous.as_input("previous"), current.as_input("current")]
            if previous.operator or current.operator:
                out.append(
                    _calc(
                        cid=f"{base}:{span}:inequality",
                        kind="not_calculated",
                        section=section,
                        title=_text(
                            f"{name['name_en']}: change {span}", f"{name['name_ar']}: التغير {span}"
                        ),
                        formula=_text("—", "—"),
                        inputs=inputs,
                        result=None,
                        unit=None,
                        reason_code="inequality_not_compared",
                    )
                )
                continue
            if ratio:
                out.append(
                    _calc(
                        cid=f"{base}:{span}:points",
                        kind="percentage_point_change",
                        section=section,
                        title=_text(
                            f"{name['name_en']}: change {span}", f"{name['name_ar']}: التغير {span}"
                        ),
                        formula=_text(
                            "current percentage − previous percentage (percentage points)",
                            "النسبة الحالية − النسبة السابقة (نقاط مئوية)",
                        ),
                        inputs=inputs,
                        result=calc.absolute_change(previous.measurement(), current.measurement()),
                        unit=PERCENTAGE_POINTS,
                        notes=pair_notes,
                    )
                )
                continue
            out.append(
                _calc(
                    cid=f"{base}:{span}:absolute",
                    kind="absolute_change",
                    section=section,
                    title=_text(
                        f"{name['name_en']}: change {span}", f"{name['name_ar']}: التغير {span}"
                    ),
                    formula=_text("current − previous", "الحالية − السابقة"),
                    inputs=inputs,
                    result=calc.absolute_change(previous.measurement(), current.measurement()),
                    unit=_unit(current),
                    notes=pair_notes,
                )
            )
            out.append(
                _calc(
                    cid=f"{base}:{span}:percentage",
                    kind="percentage_change",
                    section=section,
                    title=_text(
                        f"{name['name_en']}: growth {span}", f"{name['name_ar']}: النمو {span}"
                    ),
                    formula=_text(
                        "100 × (current − previous) ÷ previous",
                        "100 × (الحالية − السابقة) ÷ السابقة",
                    ),
                    inputs=inputs,
                    result=calc.percentage_change(previous.measurement(), current.measurement()),
                    unit=PERCENT,
                    notes=pair_notes,
                )
            )
    return out


def _per_subscriber(
    section: Section, evidence: list[Evidence], consumption_code: str, subscribers_code: str
) -> list[dict[str, Any]]:
    """Consumption ÷ subscribers only for the same area and period (compatible coverage)."""
    consumption = [e for e in evidence if e.indicator == consumption_code]
    subscribers: dict[tuple[Any, ...], list[Evidence]] = defaultdict(list)
    for e in evidence:
        if e.indicator == subscribers_code:
            subscribers[(e.area, *e.period)].append(e)
    formula = _text(
        "consumption ÷ subscriber accounts (same area and period)",
        "الاستهلاك ÷ حسابات المشتركين (المنطقة والفترة نفسيهما)",
    )
    title = _text("Use per subscriber", "الاستخدام لكل مشترك")
    if not consumption:
        notes = []
        if section is Section.ELECTRICITY and any(
            e.indicator == "ELEC_GENERATION" for e in evidence
        ):
            notes.append(explain("generation_not_consumption"))
        return [
            _calc(
                cid=f"{consumption_code}:per_subscriber",
                kind="use_per_subscriber",
                section=section,
                title=title,
                formula=formula,
                inputs=[],
                result=None,
                unit=None,
                reason_code="component_not_published",
                notes=notes,
            )
        ]
    out = []
    for e in consumption:
        matches = subscribers.get((e.area, *e.period), [])
        unit = {
            "code": f"{e.meta['unit']['code']}/subscriber",
            "label_en": f"{e.meta['unit']['label_en']} per subscriber",
            "label_ar": f"{e.meta['unit']['label_ar']} لكل مشترك",
        }
        cid = f"{consumption_code}:{e.area}:{_period_label(*e.period)}:{e.version_id[:8]}:per_subscriber"
        if len(matches) != 1:
            out.append(
                _calc(
                    cid=cid,
                    kind="use_per_subscriber",
                    section=section,
                    title=title,
                    formula=formula,
                    inputs=[e.as_input("consumption")]
                    + [m.as_input("subscribers") for m in matches],
                    result=None,
                    unit=unit,
                    reason_code="no_subscriber_series" if not matches else "conflicting_sources",
                )
            )
            continue
        out.append(
            _calc(
                cid=cid,
                kind="use_per_subscriber",
                section=section,
                title=title,
                formula=formula,
                inputs=[e.as_input("consumption"), matches[0].as_input("subscribers")],
                result=calc.use_per_subscriber(e.measurement(), matches[0].measurement()),
                unit=unit,
            )
        )
    return out


def electricity(session: Session, f: AnalysisFilter) -> list[dict[str, Any]]:
    evidence = evidence_from(
        query_observations(session, f.query(Section.ELECTRICITY), allow_mixed=True)
    )
    return _changes(Section.ELECTRICITY, evidence, f.area) + _per_subscriber(
        Section.ELECTRICITY, evidence, "ELEC_CONSUMPTION", "ELEC_SUBSCRIBERS"
    )


def water(session: Session, f: AnalysisFilter) -> list[dict[str, Any]]:
    evidence = evidence_from(query_observations(session, f.query(Section.WATER), allow_mixed=True))
    out = _changes(Section.WATER, evidence, f.area)
    out += _per_subscriber(Section.WATER, evidence, "WATER_CONSUMPTION", "WATER_SUBSCRIBERS")
    both = [e for e in evidence if e.indicator in ("WATER_PRODUCTION", "WATER_CONSUMPTION")]
    out.append(
        _calc(
            cid="WATER:leakage",
            kind="not_calculated",
            section=Section.WATER,
            title=_text("Production minus consumption", "الإنتاج ناقص الاستهلاك"),
            formula=_text("Not calculated as leakage", "لا يُحسب على أنه تسرب"),
            inputs=[e.as_input(e.indicator.lower()) for e in both],
            result=None,
            unit=None,
            reason_code="leakage_not_inferred",
        )
    )
    out.append(
        _calc(
            cid="WATER:source_composition",
            kind="not_calculated",
            section=Section.WATER,
            title=_text("Production by water source", "الإنتاج حسب مصدر المياه"),
            formula=_text(
                "share of each source in total production", "حصة كل مصدر من إجمالي الإنتاج"
            ),
            inputs=[],
            result=None,
            unit=None,
            reason_code="no_source_breakdown",
        )
    )
    return out


# ------------------------------------------------------------------ food and trade


class Frame:
    """Components of one commodity, area and period, refusing silent source choices."""

    def __init__(
        self,
        look: dict[tuple[Any, ...], list[Evidence]],
        commodity: str,
        area: str,
        start: str,
        end: str,
    ) -> None:
        self.look, self.commodity, self.area, self.start, self.end = (
            look,
            commodity,
            area,
            start,
            end,
        )
        self.conflicts: list[str] = []

    def get(
        self, indicator: str, flow: str | None = None, partner: str | None = None, role: str = ""
    ) -> Evidence | None:
        found = self.look.get(
            (indicator, self.area, self.start, self.end, self.commodity, partner, flow), []
        )
        if len(found) > 1:
            self.conflicts.append(role or indicator)
            return None
        return found[0] if found else None

    @property
    def label(self) -> str:
        return _period_label(self.start, self.end)


def _commodity_evidence(session: Session, f: AnalysisFilter) -> list[Evidence]:
    food = query_observations(session, f.query(Section.FOOD_SECURITY), allow_mixed=True)
    trade = query_observations(session, f.query(Section.TRADE), allow_mixed=True)
    seen, unique = set(), []
    for e in evidence_from(food + trade):  # food includes the national trade quantities
        key = (e.version_id, e.indicator, e.area, *e.period, e.commodity, e.partner, e.flow)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def _frames(evidence: list[Evidence], indicators: set[str]) -> list[tuple[str, str, str, str]]:
    return sorted(
        {
            (e.commodity, e.area, *e.period)
            for e in evidence
            if e.indicator in indicators and e.commodity
        }
    )  # type: ignore[misc]


def _fmt(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value.quantize(Decimal('0.0001')).normalize():,f}"


def _conflict_notes(frame: Frame) -> list[dict[str, str]]:
    return [
        _text(
            "Reported by more than one published source: " + ", ".join(frame.conflicts),
            "مُبلّغ عنه في أكثر من مصدر منشور: " + "، ".join(frame.conflicts),
        )
    ]


def _section_changes(
    section: Section, evidence: list[Evidence], f: AnalysisFilter
) -> list[dict[str, Any]]:
    own = [
        e
        for e in evidence
        if e.meta["indicator"]["section"] == section.value and e.indicator not in FRAME_INDICATORS
    ]
    return _changes(section, own, f.area)


def food_security(session: Session, f: AnalysisFilter) -> list[dict[str, Any]]:
    evidence = _commodity_evidence(session, f)
    look = index(evidence)
    out: list[dict[str, Any]] = _section_changes(Section.FOOD_SECURITY, evidence, f)
    for commodity, area, start, end in _frames(evidence, {"FOOD_PRODUCTION"}):
        fr = Frame(look, commodity, area, start, end)
        production = fr.get("FOOD_PRODUCTION", role="production")
        imports = fr.get("TRADE_QUANTITY", "import", role="imports")
        exports = fr.get("TRADE_QUANTITY", EXPORT_FLOW, role="domestic_exports")
        stock = fr.get("FOOD_STOCK_INCREASE", role="stock_increase")
        base = f"FOOD:{commodity}:{area}:{fr.label}"
        parts = [(production, "production"), (imports, "imports"), (exports, "domestic_exports")]
        if f.stock_assumption is calc.StockAssumption.KNOWN:
            parts.append((stock, "stock_increase"))
        inputs = [e.as_input(role) for e, role in parts if e is not None]
        stock_text = {
            calc.StockAssumption.ASSUMED_ZERO: _text(
                "stock change = 0 (declared assumption)", "التغير في المخزون = 0 (افتراض معلن)"
            ),
            calc.StockAssumption.UNKNOWN: _text(
                "stock change unknown (not adjusted)", "التغير في المخزون غير معروف (دون تعديل)"
            ),
            calc.StockAssumption.KNOWN: _text(
                "published stock increase", "الزيادة المنشورة في المخزون"
            ),
        }[f.stock_assumption]
        formula = _text(
            f"production + imports − domestic exports − stock increase; {stock_text['en']}",
            f"الإنتاج + الواردات − الصادرات المحلية − الزيادة في المخزون؛ {stock_text['ar']}",
        )
        title = _text("Apparent availability", "التوافر الظاهري")
        tonnes = _unit(production) if production else None
        missing = [role for e, role in parts if e is None and role not in fr.conflicts]
        if fr.conflicts or missing:
            notes = _conflict_notes(fr) if fr.conflicts else []
            if missing:
                notes.append(
                    _text(
                        "Not published: " + ", ".join(missing), "غير منشور: " + "، ".join(missing)
                    )
                )
            out.append(
                _calc(
                    cid=f"{base}:availability",
                    kind="apparent_availability",
                    section=Section.FOOD_SECURITY,
                    title=title,
                    formula=formula,
                    inputs=inputs,
                    result=None,
                    unit=tonnes,
                    reason_code="conflicting_sources"
                    if fr.conflicts
                    else "component_not_published",
                    notes=notes,
                )
            )
            continue
        assert production and imports and exports
        availability = calc.apparent_availability(
            production.measurement(),
            imports.measurement(),
            exports.measurement(),
            f.stock_assumption,
            stock.measurement()
            if stock and f.stock_assumption is calc.StockAssumption.KNOWN
            else None,
        )
        out.append(
            _calc(
                cid=f"{base}:availability",
                kind="apparent_availability",
                section=Section.FOOD_SECURITY,
                title=title,
                formula=formula,
                inputs=inputs,
                result=availability,
                unit=tonnes,
            )
        )
        local = calc.local_production_contribution(production.measurement(), availability)
        gross = calc.gross_import_contribution(imports.measurement(), availability)
        out.append(
            _calc(
                cid=f"{base}:local_production",
                kind="local_production_contribution",
                section=Section.FOOD_SECURITY,
                title=_text("Local production contribution", "مساهمة الإنتاج المحلي"),
                formula=_text(
                    "100 × production ÷ apparent availability", "100 × الإنتاج ÷ التوافر الظاهري"
                ),
                inputs=inputs,
                result=local,
                unit=PERCENT,
            )
        )
        notes = []
        if local.status is CalcStatus.OK and gross.status is CalcStatus.OK:
            assert local.value is not None and gross.value is not None
            p, i, x = (
                production.measurement().value,
                imports.measurement().value,
                exports.measurement().value,
            )
            assert p is not None and i is not None
            notes.append(
                _text(
                    f"Why the two ratios do not sum to 100%: {_fmt(local.value)}% + {_fmt(gross.value)}% = "
                    f"{_fmt(local.value + gross.value)}%. Both divide by apparent availability "
                    f"({_fmt(availability.value)}), which subtracts domestic exports ({_fmt(x)}). Production plus "
                    f"imports ({_fmt(p + i)}) is larger than availability, and exports are not attributed to either "
                    "ratio.",
                    f"لماذا لا يبلغ مجموع النسبتين 100%: {_fmt(local.value)}% + {_fmt(gross.value)}% = "
                    f"{_fmt(local.value + gross.value)}%. كلتاهما مقسومة على التوافر الظاهري ({_fmt(availability.value)}) "
                    f"الذي تُطرح منه الصادرات المحلية ({_fmt(x)}). مجموع الإنتاج والواردات ({_fmt(p + i)}) أكبر من "
                    "التوافر، ولا تُنسب الصادرات إلى أي من النسبتين.",
                )
            )
        out.append(
            _calc(
                cid=f"{base}:gross_imports",
                kind="gross_import_contribution",
                section=Section.FOOD_SECURITY,
                title=_text("Gross import contribution", "مساهمة الواردات الإجمالية"),
                formula=_text(
                    "100 × imports ÷ apparent availability", "100 × الواردات ÷ التوافر الظاهري"
                ),
                inputs=inputs,
                result=gross,
                unit=PERCENT,
                notes=notes,
            )
        )
    return out


def _derived_merchandise_balance(evidence: list[Evidence]) -> list[dict[str, Any]]:
    """Exports minus recorded imports for the same source, area and period. Calculated by
    OSRIP and labelled as derived; a published balance is a separate indicator."""
    exports = {
        (e.version_id, e.area, e.period): e
        for e in evidence
        if e.indicator == "TRADE_MERCH_EXPORTS" and e.partner is None
    }
    out = []
    for e in evidence:
        if e.indicator != "TRADE_MERCH_IMPORTS" or e.partner is not None:
            continue
        x = exports.get((e.version_id, e.area, e.period))
        if x is None or x.meta["unit"]["code"] != e.meta["unit"]["code"]:
            continue
        label = _period_label(*e.period)
        out.append(
            _calc(
                cid=f"TRADE:derived_balance:{e.area}:{label}:{e.version_id[:8]}",
                kind="derived_balance",
                section=Section.TRADE,
                title=_text(
                    f"Merchandise balance {label} (derived)",
                    f"الميزان السلعي {label} (مشتق)",
                ),
                formula=_text(
                    "merchandise exports − recorded merchandise imports",
                    "الصادرات السلعية − الواردات السلعية المسجلة",
                ),
                inputs=[x.as_input("exports"), e.as_input("imports")],
                result=calc.trade_balance(x.measurement(), e.measurement()),
                unit=_unit(x),
                notes=[explain("derived_not_published")],
            )
        )
    return out


def trade(session: Session, f: AnalysisFilter) -> list[dict[str, Any]]:
    evidence = _commodity_evidence(session, f)
    look = index(evidence)
    out: list[dict[str, Any]] = _section_changes(Section.TRADE, evidence, f)
    national = _national_indicators(evidence)
    out += _derived_merchandise_balance(
        [e for e in evidence if e.kind in COMPARABLE_KINDS and _in_focus(e, f.area, national)]
    )
    for commodity, area, start, end in _frames(evidence, {"TRADE_QUANTITY", "TRADE_VALUE"}):
        fr = Frame(look, commodity, area, start, end)
        base = f"TRADE:{commodity}:{area}:{fr.label}"
        q_imp = fr.get("TRADE_QUANTITY", "import", role="import quantity")
        q_exp = fr.get("TRADE_QUANTITY", EXPORT_FLOW, role="export quantity")
        v_imp = fr.get("TRADE_VALUE", "import", role="import value")
        v_exp = fr.get("TRADE_VALUE", EXPORT_FLOW, role="export value")

        # Partner shares against the stated national total (T09).
        partners = [
            e
            for e in evidence
            if e.indicator == "TRADE_QUANTITY"
            and e.flow == "import"
            and e.partner
            and e.commodity == commodity
            and e.area == area
            and e.period == (start, end)
        ]
        partner_codes = [p.partner for p in partners]
        if partners and q_imp is not None and len(set(partner_codes)) == len(partner_codes):
            conc = calc.partner_concentration(
                {p.partner: p.measurement() for p in partners if p.partner}, q_imp.measurement()
            )
            inputs = [q_imp.as_input("import_total")] + [p.as_input("partner") for p in partners]
            breakdown = [
                {"partner": code, "status": r.status.value, "value": _value(r)}
                for code, r in conc.shares.items()
            ]
            out.append(
                _calc(
                    cid=f"{base}:partner_shares",
                    kind="largest_partner_share",
                    section=Section.TRADE,
                    title=_text(
                        "Largest partner share of import quantity", "حصة أكبر شريك من كمية الواردات"
                    ),
                    formula=_text(
                        "100 × partner quantity ÷ stated import total",
                        "100 × كمية الشريك ÷ إجمالي الواردات المعلن",
                    ),
                    inputs=inputs,
                    result=conc.largest_share,
                    unit=PERCENT,
                    breakdown=breakdown,
                )
            )
            out.append(
                _calc(
                    cid=f"{base}:hhi",
                    kind="sum_of_squared_shares",
                    section=Section.TRADE,
                    title=_text("Sum of squared partner shares", "مجموع مربعات حصص الشركاء"),
                    formula=_text(
                        "Σ (partner quantity ÷ stated total)²", "Σ (كمية الشريك ÷ الإجمالي المعلن)²"
                    ),
                    inputs=inputs,
                    result=conc.sum_of_squared_shares,
                    unit=FRACTION,
                )
            )
        elif partners and len(set(partner_codes)) != len(partner_codes):
            fr.conflicts.append("partner quantities")

        if fr.conflicts:
            out.append(
                _calc(
                    cid=f"{base}:conflict",
                    kind="not_calculated",
                    section=Section.TRADE,
                    title=_text("Trade calculations", "حسابات التجارة"),
                    formula=_text("—", "—"),
                    inputs=[],
                    result=None,
                    unit=None,
                    reason_code="conflicting_sources",
                    notes=_conflict_notes(fr),
                )
            )
        if v_exp is not None and v_imp is not None:
            out.append(
                _calc(
                    cid=f"{base}:balance",
                    kind="trade_balance",
                    section=Section.TRADE,
                    title=_text("Commodity trade balance", "الميزان التجاري للسلعة"),
                    formula=_text(
                        "domestic export value − import value",
                        "قيمة الصادرات المحلية − قيمة الواردات",
                    ),
                    inputs=[v_exp.as_input("export_value"), v_imp.as_input("import_value")],
                    result=calc.trade_balance(v_exp.measurement(), v_imp.measurement()),
                    unit=_unit(v_exp),
                )
            )
        for flow_name, value_e, qty_e, title in (
            ("import", v_imp, q_imp, _text("Mean import unit value", "متوسط قيمة وحدة الواردات")),
            ("export", v_exp, q_exp, _text("Mean export unit value", "متوسط قيمة وحدة الصادرات")),
        ):
            if value_e is None or qty_e is None:
                continue
            unit = {
                "code": f"{value_e.meta['unit']['code']}/{qty_e.meta['unit']['code']}",
                "label_en": f"{value_e.meta['unit']['label_en']} per {qty_e.meta['unit']['label_en']}",
                "label_ar": f"{value_e.meta['unit']['label_ar']} لكل {qty_e.meta['unit']['label_ar']}",
            }
            out.append(
                _calc(
                    cid=f"{base}:{flow_name}_unit_value",
                    kind="unit_value",
                    section=Section.TRADE,
                    title=title,
                    formula=_text("trade value ÷ trade quantity", "قيمة التجارة ÷ كمية التجارة"),
                    inputs=[value_e.as_input("value"), qty_e.as_input("quantity")],
                    result=calc.mean_unit_value(value_e.measurement(), qty_e.measurement()),
                    unit=unit,
                )
            )
    return out


BUILDERS = {
    Section.ELECTRICITY: electricity,
    Section.WATER: water,
    Section.FOOD_SECURITY: food_security,
    Section.TRADE: trade,
}


def analyse(session: Session, section: Section, f: AnalysisFilter) -> list[dict[str, Any]]:
    return BUILDERS[section](session, f)
