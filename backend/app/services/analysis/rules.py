"""Interpretable review rules R01-R04 (booklet 3.13, Table 3.6).

A rule turns calculations into review cards. Each card states the observation,
the rule and its threshold, the exact inputs, the limitations, and a suggested
next investigation. Thresholds are project assumptions awaiting review, not
official standards. Rules never trigger on missing or incompatible inputs, and
cards never state a cause: they request investigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

RULES_VERSION = "2026.09-1"
GROWTH_MEASURES = {"generation", "consumption", "peak_demand", "production"}


@dataclass(frozen=True, slots=True)
class RuleParameters:
    growth_threshold_pct: Decimal = Decimal("3")
    share_threshold_pct: Decimal = Decimal("50")
    unit_value_gap_pct: Decimal = Decimal("10")

    def as_dict(self) -> dict[str, str]:
        return {
            k: str(getattr(self, k))
            for k in ("growth_threshold_pct", "share_threshold_pct", "unit_value_gap_pct")
        }


@dataclass(frozen=True, slots=True)
class Card:
    rule_code: str
    section: str
    observation: dict[str, str]
    next_steps: dict[str, str]
    evidence: dict[str, Any]


def _t(en: str, ar: str) -> dict[str, str]:
    return {"en": en, "ar": ar}


def _pct(value: str | Decimal) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01')).normalize():f}"


def _evidence(
    calc: dict[str, Any], rule: dict[str, Any], limitations: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "calculation_id": calc["id"],
        "calculation_title": calc["title"],
        "formula": calc["formula"],
        "result": calc["result"],
        "inputs": calc["inputs"],
        "rule": rule,
        "limitations": limitations
        + [{"code": c["code"], "en": c["en"], "ar": c["ar"]} for c in calc["caveats"]],
    }


def _measure_of(calc: dict[str, Any]) -> str | None:
    code = calc["inputs"][0]["indicator"]["code"] if calc["inputs"] else ""
    return {
        "ELEC_GENERATION": "generation",
        "ELEC_CONSUMPTION": "consumption",
        "ELEC_PEAK_DEMAND": "peak_demand",
        "WATER_PRODUCTION": "production",
        "WATER_CONSUMPTION": "consumption",
    }.get(code)


def r01_growth(calcs: list[dict[str, Any]], p: RuleParameters) -> list[Card]:
    cards = []
    for c in calcs:
        if c["kind"] != "percentage_change" or c["result"]["status"] != "ok":
            continue
        measure = _measure_of(c)
        inputs = c["inputs"]
        if measure not in GROWTH_MEASURES or not all(i["period_complete"] for i in inputs):
            continue  # eligibility: complete comparable periods only
        value = Decimal(c["result"]["value"])
        if abs(value) <= p.growth_threshold_pct:
            continue
        name_en, name_ar = inputs[1]["indicator"]["name_en"], inputs[1]["indicator"]["name_ar"]
        prev, cur = inputs[0], inputs[1]
        rule = {
            "code": "R01",
            "name": _t("Growth above threshold", "نمو يتجاوز العتبة"),
            "version": RULES_VERSION,
            "threshold": f"{p.growth_threshold_pct}%",
            "eligibility": _t(
                "Comparable complete periods, same unit and coverage",
                "فترات كاملة قابلة للمقارنة بالوحدة والتغطية نفسيهما",
            ),
            "threshold_note": _t(
                "Project assumption awaiting review; not an official standard.",
                "افتراض للمشروع قيد المراجعة؛ ليس معياراً رسمياً.",
            ),
        }
        limitations = []
        steps_en = "Check changes in coverage, subscriber numbers and seasonality before interpreting the change."
        steps_ar = "تحقق من تغيرات التغطية وأعداد المشتركين والموسمية قبل تفسير التغير."
        if measure == "generation":
            limitations.append(
                _t(
                    "Generation growth is not demand or consumption growth.",
                    "نمو التوليد ليس نمواً في الطلب أو الاستهلاك.",
                )
                | {"code": "generation_not_demand"}
            )
            steps_en += " Compare with published consumption before drawing any demand conclusion."
            steps_ar += " قارن بالاستهلاك المنشور قبل استنتاج أي شيء عن الطلب."
        if c["section"] == "water":
            limitations.append(
                _t("This card does not show that a leak exists.", "لا تُظهر هذه البطاقة وجود تسرب.")
                | {"code": "no_leak_claim"}
            )
        cards.append(
            Card(
                "R01",
                c["section"],
                _t(
                    f"{name_en} changed by {_pct(value)}% from {prev['period_start'][:4]} to {cur['period_start'][:4]} "
                    f"({prev['value']} → {cur['value']} {cur['unit']['label_en']}), above the {p.growth_threshold_pct}% "
                    "review threshold.",
                    f"تغيّر {name_ar} بنسبة {_pct(value)}% من {prev['period_start'][:4]} إلى {cur['period_start'][:4]} "
                    f"(من {prev['value']} إلى {cur['value']} {cur['unit']['label_ar']})، أي فوق عتبة المراجعة "
                    f"{p.growth_threshold_pct}%.",
                ),
                _t(steps_en, steps_ar),
                _evidence(c, rule, limitations),
            )
        )
    return cards


def r02_concentration(calcs: list[dict[str, Any]], p: RuleParameters) -> list[Card]:
    cards = []
    for c in calcs:
        if c["kind"] != "largest_partner_share" or c["result"]["status"] != "ok":
            continue
        if any(x["code"] == "partial_partner_coverage" for x in c["caveats"]):
            continue  # eligibility: complete partner quantities
        value = Decimal(c["result"]["value"])
        if value <= p.share_threshold_pct:
            continue
        largest = max(c["breakdown"], key=lambda b: Decimal(b["value"] or 0))
        rule = {
            "code": "R02",
            "name": _t("Supplier concentration", "تركّز الموردين"),
            "version": RULES_VERSION,
            "threshold": f"{p.share_threshold_pct}%",
            "eligibility": _t(
                "Partner quantities that reconcile with the stated import total",
                "كميات شركاء تتطابق مع إجمالي الواردات المعلن",
            ),
            "threshold_note": _t(
                "Project assumption awaiting review; not an official standard.",
                "افتراض للمشروع قيد المراجعة؛ ليس معياراً رسمياً.",
            ),
        }
        commodity = c["inputs"][0]["commodity"]
        cards.append(
            Card(
                "R02",
                c["section"],
                _t(
                    f"{largest['partner']} supplies {_pct(value)}% of {commodity} import quantity, above the "
                    f"{p.share_threshold_pct}% review threshold.",
                    f"يورّد {largest['partner']} نسبة {_pct(value)}% من كمية واردات {commodity}، أي فوق عتبة "
                    f"المراجعة {p.share_threshold_pct}%.",
                ),
                _t(
                    "Investigate alternative supply and the contract context. Concentration is not a probability "
                    "of disruption.",
                    "ابحث في مصادر الإمداد البديلة وسياق العقود. التركّز ليس احتمالاً للانقطاع.",
                ),
                _evidence(c, rule, []),
            )
        )
    return cards


def r03_unit_values(calcs: list[dict[str, Any]], p: RuleParameters) -> list[Card]:
    by_frame: dict[str, dict[str, dict[str, Any]]] = {}
    for c in calcs:
        if c["kind"] == "unit_value" and c["result"]["status"] == "ok":
            frame, flow = c["id"].rsplit(":", 1)
            by_frame.setdefault(frame, {})[flow] = c
    cards = []
    for pair in by_frame.values():
        imp, exp = pair.get("import_unit_value"), pair.get("export_unit_value")
        if not imp or not exp:
            continue
        iv, ev = Decimal(imp["result"]["value"]), Decimal(exp["result"]["value"])
        if iv <= 0:
            continue
        gap = abs(ev - iv) / iv * 100
        if gap <= p.unit_value_gap_pct:
            continue
        unit = imp["result"]["unit"]
        rule = {
            "code": "R03",
            "name": _t("Value and quantity divergence", "تباين القيمة والكمية"),
            "version": RULES_VERSION,
            "threshold": f"{p.unit_value_gap_pct}%",
            "eligibility": _t(
                "Compatible trade values and quantities for the same commodity and period",
                "قيم وكميات تجارية متوافقة للسلعة والفترة نفسيهما",
            ),
            "threshold_note": _t(
                "Project assumption awaiting review; not an official standard.",
                "افتراض للمشروع قيد المراجعة؛ ليس معياراً رسمياً.",
            ),
        }
        evidence = _evidence(imp, rule, [])
        evidence["inputs"] = imp["inputs"] + exp["inputs"]
        evidence["related_calculation"] = {
            "id": exp["id"],
            "title": exp["title"],
            "result": exp["result"],
        }
        evidence["limitations"] += [
            {
                "code": "not_a_margin",
                **_t(
                    "The difference between unit values is not a profit margin.",
                    "الفرق بين قيمتي الوحدة ليس هامش ربح.",
                ),
            }
        ]
        cards.append(
            Card(
                "R03",
                imp["section"],
                _t(
                    f"Mean export unit value ({_pct(ev)} {unit['label_en']}) differs from the mean import unit value "
                    f"({_pct(iv)}) by {_pct(gap)}%, above the {p.unit_value_gap_pct}% review threshold.",
                    f"يختلف متوسط قيمة وحدة الصادرات ({_pct(ev)} {unit['label_ar']}) عن متوسط قيمة وحدة الواردات "
                    f"({_pct(iv)}) بنسبة {_pct(gap)}%، أي فوق عتبة المراجعة {p.unit_value_gap_pct}%.",
                ),
                _t(
                    "Review product composition, quality and valuation basis of both baskets before any commercial "
                    "conclusion. Do not read the gap as a margin.",
                    "راجع تكوين المنتجات وجودتها وأساس التقييم في السلتين قبل أي استنتاج تجاري. لا تقرأ الفرق هامشاً.",
                ),
                evidence,
            )
        )
    return cards


def r04_data_quality(calcs: list[dict[str, Any]], _: RuleParameters) -> list[Card]:
    cards = []
    for c in calcs:
        status = c["result"]["status"]
        partial = any(x["code"] == "partial_partner_coverage" for x in c["caveats"])
        missing_value = any(i["value"] is None for i in c["inputs"])
        if not (status in ("missing", "incompatible") or partial or missing_value):
            continue
        problem = (c["reason"] or {}).get("en") if c["reason"] else None
        problem_ar = (c["reason"] or {}).get("ar") if c["reason"] else None
        if partial:
            problem, problem_ar = (
                "Partner quantities do not cover the stated total.",
                "كميات الشركاء لا تغطي الإجمالي المعلن.",
            )
        rule = {
            "code": "R04",
            "name": _t("Data quality issue", "مشكلة في جودة البيانات"),
            "version": RULES_VERSION,
            "threshold": None,
            "eligibility": _t(
                "Missing period, unit or period conflict, or failed reconciliation",
                "فترة مفقودة أو تعارض في الوحدة أو الفترة أو فشل في المطابقة",
            ),
            "threshold_note": None,
        }
        cards.append(
            Card(
                "R04",
                c["section"],
                _t(
                    f"{c['title']['en']}: {problem or 'an input value is missing.'}",
                    f"{c['title']['ar']}: {problem_ar or 'إحدى القيم المدخلة مفقودة.'}",
                ),
                _t(
                    "Withhold the affected comparison and correct or complete the input before interpreting it.",
                    "احجب المقارنة المتأثرة وصحّح المدخل أو أكمله قبل تفسيرها.",
                ),
                _evidence(c, rule, []),
            )
        )
    return cards


RULES = (r01_growth, r02_concentration, r03_unit_values, r04_data_quality)


def evaluate(calcs: list[dict[str, Any]], params: RuleParameters) -> list[Card]:
    return [card for rule in RULES for card in rule(calcs, params)]
