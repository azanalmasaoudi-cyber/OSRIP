"""Decision brief for one economic axis, built only from published observations of one data
mode and OSRIP's own transparent calculations (``sections.analyse``, ``rules.evaluate``).

Nothing here is estimated or invented: every figure is a published value or a stated
arithmetic step over published values of the same indicator family, unit, period and dataset
version. Where the data cannot answer a part of the brief, the brief says so and lists the gap.
Judgements (strength, weakness, surplus, shortage, concentration) follow the fixed rules
below, which are project assumptions shown with each finding, not official standards.
Recommendations are suggested next steps for review; none states a cause.

Sources stay out of the findings: each finding carries reference ids (E1, E2, ...) into
``provenance``, which the page shows in a separate, collapsed panel.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import DataMode, Section
from app.models import Indicator
from app.services import scenarios
from app.services.analysis import rules
from app.services.analysis.sections import AnalysisFilter, analyse
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.observations import ObservationQuery, SeriesOut, query_observations

BRIEF_VERSION = "2026.11-1"
# Measures whose growth adds supply or output. Demand measures are compared against them.
SUPPLY = frozenset(
    {
        "gross_generation",
        "net_generation",
        "generation",
        "installed_capacity",
        "production",
        "crop_production",
        "fish_landings",
        "livestock",
        "cultivated_area",
        "fish_value",
        "merchandise_exports",
    }
)
# Demand against supply over the same two periods.
PAIRS: dict[Section, tuple[tuple[str, str], ...]] = {
    Section.ELECTRICITY: (("ELEC_CONSUMPTION", "ELEC_GROSS_GENERATION"),),
    Section.WATER: (("WATER_CONSUMPTION", "WATER_PRODUCTION"),),
    Section.TRADE: (("TRADE_MERCH_IMPORTS", "TRADE_MERCH_EXPORTS"),),
}
# Product groups published both as non-oil (domestic) exports and as imports of the same
# scope. Mineral products are left out: that export series excludes oil, the import one not.
TRADE_GROUPS = (
    ("TRADE_NONOIL_BASE_METALS_EXPORTS", "TRADE_IMPORTS_BASE_METALS"),
    ("TRADE_NONOIL_PRECIOUS_EXPORTS", "TRADE_IMPORTS_PRECIOUS"),
)
SHARE_THRESHOLD = Decimal(50)  # concentration above this share is flagged for review
STALE_AFTER = timedelta(days=730)
GOVERNORATES = 11
KIND_ORDER = {"annual": 0, "year_to_date": 1, "quarterly": 2, "monthly": 3, "statement": 4}
SUBNATIONAL = ("governorate", "reporting_group")
MONTHS = (
    ("Jan", "يناير"),
    ("Feb", "فبراير"),
    ("Mar", "مارس"),
    ("Apr", "أبريل"),
    ("May", "مايو"),
    ("Jun", "يونيو"),
    ("Jul", "يوليو"),
    ("Aug", "أغسطس"),
    ("Sep", "سبتمبر"),
    ("Oct", "أكتوبر"),
    ("Nov", "نوفمبر"),
    ("Dec", "ديسمبر"),
)


def _t(en: str, ar: str) -> dict[str, str]:
    return {"en": en, "ar": ar}


def _n(value: Decimal | str, places: int = 1) -> str:
    """A figure for a sentence: grouped thousands, at most ``places`` decimals."""
    d = Decimal(value).quantize(Decimal(1).scaleb(-places))
    text = f"{d:,f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _period(start: str, end: str, kind: str | None) -> dict[str, str]:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if kind == "annual" or (s.month, s.day, e.month, e.day) == (1, 1, 12, 31):
        return _t(str(e.year), str(e.year))
    if kind == "year_to_date":
        return _t(
            f"{MONTHS[s.month - 1][0]}–{MONTHS[e.month - 1][0]} {e.year}",
            f"{MONTHS[s.month - 1][1]}–{MONTHS[e.month - 1][1]} {e.year}",
        )
    if kind == "monthly":
        return _t(f"{MONTHS[e.month - 1][0]} {e.year}", f"{MONTHS[e.month - 1][1]} {e.year}")
    return _t(e.isoformat(), e.isoformat())


class Refs:
    """Provenance entries (E1, E2, ...) for every published value the brief uses."""

    def __init__(self) -> None:
        self.entries: dict[tuple[Any, ...], dict[str, Any]] = {}
        # Dataset version id -> publication time, for inputs that carry only id and label.
        self.published: dict[str, str | None] = {}

    def add(self, entry: dict[str, Any]) -> str:
        key = (entry["record_ref"], entry["source_row"], entry["period_end"], entry["indicator"])
        if key not in self.entries:
            self.entries[key] = {"ref": f"E{len(self.entries) + 1}", **entry}
        return self.entries[key]["ref"]

    def from_input(self, i: dict[str, Any]) -> str:
        """A calculation input (``sections`` evidence shape)."""
        return self.add(
            {
                "indicator": i["indicator"]["code"],
                "indicator_name": _t(i["indicator"]["name_en"], i["indicator"]["name_ar"]),
                "area": i["area"]["code"],
                "period_start": i["period_start"],
                "period_end": i["period_end"],
                "value": i["value"],
                "unit": _t(i["unit"]["label_en"], i["unit"]["label_ar"]) if i["unit"] else None,
                "source_title": i["source_title"],
                "source_url": i.get("source_url"),
                "source_locator": i.get("source_locator"),
                "source_row": i.get("source_row"),
                "record_ref": i.get("record_ref"),
                "dataset_version": i["dataset_version"]["label"],
                "published_at": self.published.get(str(i["dataset_version"]["id"])),
                "quality_status": i.get("quality_status"),
                "revision_status": i.get("revision_status"),
            }
        )

    def from_obs(self, s: SeriesOut, o: dict[str, Any]) -> str:
        m = s.meta
        return self.add(
            {
                "indicator": m["indicator"]["code"],
                "indicator_name": _t(m["indicator"]["name_en"], m["indicator"]["name_ar"]),
                "area": m["area"]["code"],
                "period_start": o["period_start"],
                "period_end": o["period_end"],
                "value": o["value"],
                "unit": _t(m["unit"]["label_en"], m["unit"]["label_ar"]),
                "source_title": m["source"]["dataset_title"],
                "source_url": m["source"].get("url"),
                "source_locator": o.get("source_locator"),
                "source_row": o.get("source_row"),
                "record_ref": o.get("record_ref"),
                "dataset_version": m["dataset_version"]["label"],
                "published_at": m["dataset_version"].get("published_at"),
                "quality_status": o.get("quality_status"),
                "revision_status": o.get("revision_status"),
            }
        )

    def out(self) -> list[dict[str, Any]]:
        return list(self.entries.values())


def _name(meta_indicator: dict[str, Any]) -> dict[str, str]:
    return _t(meta_indicator["name_en"], meta_indicator["name_ar"])


def _unit(u: dict[str, Any] | None) -> dict[str, str]:
    return _t(u["label_en"], u["label_ar"]) if u else _t("", "")


# ------------------------------------------------------------------ current performance


def _performance(calcs: list[dict[str, Any]], refs: Refs) -> list[dict[str, Any]]:
    """Per national indicator: the latest complete-year change, and the latest within-year
    change when it is more recent. Monthly changes only when nothing else is published."""
    by_indicator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in calcs:
        if c["kind"] != "percentage_change" or c["result"]["status"] != "ok":
            continue
        roles = {i.get("role"): i for i in c["inputs"]}
        cur, prev = roles.get("current"), roles.get("previous")
        if not cur or not prev or cur["area"]["code"] != "OM":
            continue
        if cur.get("commodity") or cur.get("partner"):
            continue
        change = Decimal(c["result"]["value"])
        kind = cur.get("period_kind") or "annual"
        by_indicator[cur["indicator"]["code"]].append(
            {
                "id": c["id"],
                "indicator": {"code": cur["indicator"]["code"], "name": _name(cur["indicator"])},
                "measure": None,
                "kind": kind,
                "unit": _unit(cur["unit"]),
                "current": {
                    "value": cur["value"],
                    "period": _period(cur["period_start"], cur["period_end"], kind),
                    "end": cur["period_end"],
                },
                "previous": {
                    "value": prev["value"],
                    "period": _period(prev["period_start"], prev["period_end"], kind),
                    "end": prev["period_end"],
                },
                "change_pct": str(change),
                "direction": "flat"
                if _n(change) in ("0", "-0")
                else "up"
                if change > 0
                else "down",
                "refs": [refs.from_input(prev), refs.from_input(cur)],
            }
        )
    out = []
    for items in by_indicator.values():
        items.sort(key=lambda x: (KIND_ORDER.get(x["kind"], 9), x["current"]["end"]))
        complete = [x for x in items if x["kind"] == "annual"]
        within = [x for x in items if x["kind"] in ("year_to_date", "quarterly")]
        chosen = complete[-1:] if complete else []
        if within and (not chosen or within[-1]["current"]["end"] > chosen[0]["current"]["end"]):
            chosen.append(within[-1])
        if not chosen:
            chosen = [max(items, key=lambda x: x["current"]["end"])]
        out.extend(chosen)
    return sorted(out, key=lambda x: (x["indicator"]["code"], KIND_ORDER.get(x["kind"], 9)))


# ------------------------------------------------------------------ helpers over series


def _latest_by(series: list[SeriesOut], pick: Any) -> dict[tuple[Any, ...], tuple[SeriesOut, dict]]:
    """For each key ``pick(series)`` (or skip on None), the latest complete observation."""
    out: dict[tuple[Any, ...], tuple[SeriesOut, dict[str, Any]]] = {}
    for s in series:
        key = pick(s)
        if key is None:
            continue
        for o in s.observations:
            if o["value"] is None or not o["period_complete"]:
                continue
            best = out.get(key)
            if best is None or o["period_end"] > best[1]["period_end"]:
                out[key] = (s, o)
    return out


def _frame(s: SeriesOut) -> tuple[Any, ...]:
    """Values are comparable only within one unit, period kind, dataset version and flow."""
    m = s.meta
    return (
        m["unit"]["code"],
        m["period_kind"],
        m["ytd_end_month"],
        m["dataset_version"]["id"],
        m["flow"],
    )


def _values_at(series: list[SeriesOut], code: str, area: str = "OM") -> dict[tuple, tuple]:
    """(frame, period_start, period_end) -> (series, observation) for one indicator and area."""
    out = {}
    for s in series:
        m = s.meta
        if m["indicator"]["code"] != code or m["area"]["code"] != area or m["commodity"]:
            continue
        if m["partner"]:
            continue
        for o in s.observations:
            if o["value"] is not None and o["period_complete"]:
                out[(_frame(s), o["period_start"], o["period_end"])] = (s, o)
    return out


# ------------------------------------------------------------------ the brief


def brief(
    session: Session,
    section: Section,
    data_mode: DataMode,
    dataset_version_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """The brief over every published version of ``data_mode``, or over one version."""
    refs = Refs()
    calcs = analyse(
        session, section, AnalysisFilter(data_mode, dataset_version_id=dataset_version_id)
    )
    floor = STATISTICAL_SCOPE_START if data_mode is DataMode.VERIFIED_SOURCE else None
    series = query_observations(
        session,
        ObservationQuery(
            data_mode, section=section, period_from=floor, dataset_version_id=dataset_version_id
        ),
        allow_mixed=True,
    )
    refs.published = {
        str(x.meta["dataset_version"]["id"]): x.meta["dataset_version"].get("published_at")
        for x in series
    }
    registry = list(
        session.scalars(
            select(Indicator).where(Indicator.section == section).order_by(Indicator.code)
        )
    )
    measures = {i.code: i.measure for i in registry}
    names = {i.code: _t(i.name_en, i.name_ar) for i in registry}

    performance = _performance(calcs, refs)
    for p in performance:
        p["measure"] = measures.get(p["indicator"]["code"])

    strengths: list[dict[str, Any]] = []
    weaknesses: list[dict[str, Any]] = []
    surplus: list[dict[str, Any]] = []
    shortage: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []

    def finding(
        target: list, kind: str, text: dict[str, str], rule: dict[str, str], used: list[str]
    ) -> str:
        fid = f"{kind}-{len(target) + 1}"
        target.append({"id": fid, "kind": kind, "text": text, "rule": rule, "refs": used})
        return fid

    # Supply indicators that grew or fell over their latest comparison.
    supply_rule = _t(
        "An output or supply indicator that rose counts as a strength, one that fell as a weakness.",
        "مؤشر الإنتاج أو الإمداد الذي ارتفع يُعدّ نقطة قوة، والذي انخفض نقطة ضعف.",
    )
    for p in performance:
        if p["measure"] not in SUPPLY or p["direction"] == "flat":
            continue
        name, pct = p["indicator"]["name"], _n(abs(Decimal(p["change_pct"])))
        span = _t(
            f"{p['previous']['period']['en']} to {p['current']['period']['en']}",
            f"من {p['previous']['period']['ar']} إلى {p['current']['period']['ar']}",
        )
        if p["direction"] == "up":
            finding(
                strengths,
                "supply_up",
                _t(
                    f"{name['en']} rose {pct}% ({span['en']}).",
                    f"ارتفع مؤشر {name['ar']} بنسبة {pct}% ({span['ar']}).",
                ),
                supply_rule,
                p["refs"],
            )
        else:
            finding(
                weaknesses,
                "supply_down",
                _t(
                    f"{name['en']} fell {pct}% ({span['en']}).",
                    f"انخفض مؤشر {name['ar']} بنسبة {pct}% ({span['ar']}).",
                ),
                supply_rule,
                p["refs"],
            )

    # Demand against supply over the same two periods.
    pace_rule = _t(
        "Demand growing faster than supply over the same periods is a weakness; slower, a strength.",
        "نمو الطلب أسرع من الإمداد في الفترات نفسها نقطة ضعف، وأبطأ منه نقطة قوة.",
    )
    by_pair = {
        (p["indicator"]["code"], p["kind"], p["previous"]["end"], p["current"]["end"]): p
        for p in performance
    }
    for demand_code, supply_code in PAIRS.get(section, ()):
        for (code, kind, prev_end, cur_end), d in by_pair.items():
            sup = by_pair.get((supply_code, kind, prev_end, cur_end))
            if code != demand_code or sup is None:
                continue
            dg, sg = Decimal(d["change_pct"]), Decimal(sup["change_pct"])
            dn, sn, per = d["indicator"]["name"], sup["indicator"]["name"], d["current"]["period"]
            text = _t(
                f"{dn['en']} changed {_n(dg)}% while {sn['en']} changed {_n(sg)}% ({per['en']}).",
                f"تغيّر مؤشر {dn['ar']} بنسبة {_n(dg)}% بينما تغيّر مؤشر {sn['ar']} بنسبة {_n(sg)}% ({per['ar']}).",
            )
            if dg > sg:
                fid = finding(
                    weaknesses, "demand_outpaces_supply", text, pace_rule, d["refs"] + sup["refs"]
                )
                if section is Section.TRADE:
                    advice = _t(
                        f"Review the import bill: {dn['en']} grew faster than {sn['en']} ({per['en']}). "
                        "Identify the import groups that rose and the scope for export growth or "
                        "import substitution.",
                        f"راجع فاتورة الاستيراد: نما مؤشر {dn['ar']} أسرع من مؤشر {sn['ar']} ({per['ar']}). "
                        "حدّد مجموعات الواردات التي ارتفعت وفرص نمو الصادرات أو إحلال الواردات.",
                    )
                else:
                    advice = _t(
                        f"Review supply plans: {dn['en']} grew faster than {sn['en']} ({per['en']}). "
                        "Check planned capacity, efficiency and demand management.",
                        f"راجع خطط الإمداد: نما مؤشر {dn['ar']} أسرع من مؤشر {sn['ar']} ({per['ar']}). "
                        "تحقق من القدرات المخطط لها والكفاءة وإدارة الطلب.",
                    )
                recommendations.append(
                    {"kind": "demand_pressure", "based_on": [fid], "text": advice}
                )
            else:
                finding(strengths, "supply_keeps_pace", text, pace_rule, d["refs"] + sup["refs"])

    # Self-sufficiency ratios (food): surplus at or above 100%, shortage below.
    ratio_rule = _t(
        "A published self-sufficiency ratio of 100% or more is a surplus; below 100% a shortage.",
        "نسبة الاكتفاء الذاتي المنشورة 100% أو أكثر فائض، وأقل من 100% عجز.",
    )
    latest_ratio = _latest_by(
        series,
        lambda s: (
            (s.meta["indicator"]["code"],)
            if measures.get(s.meta["indicator"]["code"]) == "self_sufficiency"
            and s.meta["area"]["code"] == "OM"
            else None
        ),
    )
    for (code,), (s, o) in sorted(latest_ratio.items()):
        value, name = Decimal(o["value"]), _name(s.meta["indicator"])
        ref = refs.from_obs(s, o)
        per = _period(o["period_start"], o["period_end"], s.meta["period_kind"])
        item = {
            "indicator": {"code": code, "name": name},
            "value": o["value"],
            "unit": _unit(s.meta["unit"]),
            "period": per,
            "refs": [ref],
        }
        if value >= 100:
            item["gap"] = str(value - 100)
            surplus.append(item)
            fid = finding(
                strengths,
                "self_sufficient",
                _t(
                    f"{name['en']}: {_n(value)}% ({per['en']}).",
                    f"{name['ar']}: {_n(value)}% ({per['ar']}).",
                ),
                ratio_rule,
                [ref],
            )
            recommendations.append(
                {
                    "kind": "use_surplus",
                    "based_on": [fid],
                    "text": _t(
                        f"{name['en']} is at or above 100%: assess export markets, processing and strategic storage.",
                        f"{name['ar']} عند 100% أو أعلى: قيّم أسواق التصدير والتصنيع والتخزين الاستراتيجي.",
                    ),
                }
            )
        else:
            item["gap"] = str(100 - value)
            shortage.append(item)
            fid = finding(
                weaknesses,
                "import_dependent",
                _t(
                    f"{name['en']}: {_n(value)}% ({per['en']}), {_n(100 - value)} percentage point{'' if 100 - value == 1 else 's'} below 100%.",
                    f"{name['ar']}: {_n(value)}% ({per['ar']})، أي أقل من 100% بفارق {_n(100 - value)} نقطة مئوية.",
                ),
                ratio_rule,
                [ref],
            )
            recommendations.append(
                {
                    "kind": "mitigate_shortage",
                    "based_on": [fid],
                    "text": _t(
                        f"Narrow the {name['en']} gap: diversify import sources, review strategic stocks and "
                        "assess the scope for domestic production.",
                        f"قلّص فجوة {name['ar']}: نوّع مصادر الاستيراد، وراجع المخزون الاستراتيجي، "
                        "وقيّم إمكانات الإنتاج المحلي.",
                    ),
                }
            )

    # Trade: the derived balance and product groups with both directions published.
    trade = []
    balances = sorted(
        (c for c in calcs if c["kind"] == "derived_balance" and c["result"]["status"] == "ok"),
        key=lambda c: c["inputs"][0]["period_end"] if c["inputs"] else "",
    )
    annual_balances = [
        c for c in balances if c["inputs"] and c["inputs"][0].get("period_kind") == "annual"
    ]
    if annual_balances:
        last = annual_balances[-1]
        i0 = last["inputs"][0]
        value, unit = Decimal(last["result"]["value"]), _unit(last["result"]["unit"])
        per = _period(i0["period_start"], i0["period_end"], "annual")
        used = [refs.from_input(i) for i in last["inputs"]]
        trade.append(
            {
                "kind": "balance",
                "value": last["result"]["value"],
                "unit": unit,
                "period": per,
                "refs": used,
            }
        )
        balance_rule = _t(
            "Exports minus imports, as published for the same period.",
            "الصادرات ناقص الواردات، كما نُشرت للفترة نفسها.",
        )
        target = strengths if value >= 0 else weaknesses
        word = _t("surplus", "فائض") if value >= 0 else _t("deficit", "عجز")
        finding(
            target,
            "trade_balance",
            _t(
                f"Merchandise trade {word['en']} of {_n(abs(value), 0)} {unit['en']} ({per['en']}).",
                f"{word['ar']} في تجارة السلع قدره {_n(abs(value), 0)} {unit['ar']} ({per['ar']}).",
            ),
            balance_rule,
            used,
        )
        if len(annual_balances) > 1:
            before = Decimal(annual_balances[-2]["result"]["value"])
            pb = _period(
                annual_balances[-2]["inputs"][0]["period_start"],
                annual_balances[-2]["inputs"][0]["period_end"],
                "annual",
            )
            if before > 0 and 0 <= value < before:
                used2 = used + [refs.from_input(i) for i in annual_balances[-2]["inputs"]]
                fid = finding(
                    weaknesses,
                    "surplus_narrowed",
                    _t(
                        f"The trade surplus narrowed from {_n(before, 0)} to {_n(value, 0)} {unit['en']} "
                        f"({pb['en']} to {per['en']}).",
                        f"تراجع الفائض التجاري من {_n(before, 0)} إلى {_n(value, 0)} {unit['ar']} "
                        f"(من {pb['ar']} إلى {per['ar']}).",
                    ),
                    balance_rule,
                    used2,
                )
                recommendations.append(
                    {
                        "kind": "trade_development",
                        "based_on": [fid],
                        "text": _t(
                            "Review which export groups and import groups drove the narrower surplus before "
                            "setting trade-development priorities.",
                            "راجع مجموعات الصادرات والواردات التي أدت إلى تراجع الفائض قبل تحديد أولويات "
                            "تنمية التجارة.",
                        ),
                    }
                )
    for export_code, import_code in TRADE_GROUPS if section is Section.TRADE else ():
        # The two directions differ in flow by definition; everything else must match.
        exports, imports = (
            {(k[0][:-1], k[1], k[2]): v for k, v in _values_at(series, code).items()}
            for code in (export_code, import_code)
        )
        common = sorted(set(exports) & set(imports), key=lambda k: k[2])
        if not common:
            continue
        key = common[-1]
        (se, oe), (si, oi) = exports[key], imports[key]
        net = Decimal(oe["value"]) - Decimal(oi["value"])
        per = _period(oe["period_start"], oe["period_end"], se.meta["period_kind"])
        used = [refs.from_obs(se, oe), refs.from_obs(si, oi)]
        item = {
            "kind": "group",
            "exports": {
                "code": export_code,
                "name": _name(se.meta["indicator"]),
                "value": oe["value"],
            },
            "imports": {
                "code": import_code,
                "name": _name(si.meta["indicator"]),
                "value": oi["value"],
            },
            "net": str(net),
            "unit": _unit(se.meta["unit"]),
            "period": per,
            "refs": used,
        }
        trade.append(item)
        target = surplus if net >= 0 else shortage
        target.append(
            {
                "indicator": {"code": export_code, "name": _name(se.meta["indicator"])},
                "value": str(net),
                "unit": _unit(se.meta["unit"]),
                "period": per,
                "refs": used,
                "gap": str(abs(net)),
            }
        )

    # Composition: published parts of a registry parent, same unit, period and version.
    composition = []
    children: dict[str, list[str]] = defaultdict(list)
    for i in registry:
        if i.parent_code:
            children[i.parent_code].append(i.code)
    for parent, parts in sorted(children.items()):
        totals = _values_at(series, parent)
        values = {code: _values_at(series, code) for code in parts}
        keys = [k for k in totals if any(k in v for v in values.values())]
        if not keys:
            continue
        key = max(keys, key=lambda k: (k[2], -KIND_ORDER.get(k[0][1], 9)))
        st, ot = totals[key]
        total = Decimal(ot["value"])
        if total <= 0:
            continue
        rows, used = [], [refs.from_obs(st, ot)]
        for code in parts:
            if key not in values[code]:
                continue
            sp, op = values[code][key]
            share = Decimal(op["value"]) * 100 / total
            used.append(refs.from_obs(sp, op))
            rows.append(
                {
                    "indicator": {"code": code, "name": _name(sp.meta["indicator"])},
                    "value": op["value"],
                    "share_pct": str(share),
                    "ref": used[-1],
                }
            )
        rows.sort(key=lambda r: Decimal(r["share_pct"]), reverse=True)
        per = _period(ot["period_start"], ot["period_end"], st.meta["period_kind"])
        composition.append(
            {
                "parent": {"code": parent, "name": _name(st.meta["indicator"])},
                "total": ot["value"],
                "unit": _unit(st.meta["unit"]),
                "period": per,
                "parts": rows,
                "refs": used,
            }
        )
        top = rows[0] if rows else None
        if top and Decimal(top["share_pct"]) > SHARE_THRESHOLD:
            tn, pn = top["indicator"]["name"], _name(st.meta["indicator"])
            fid = finding(
                risks,
                "concentration",
                _t(
                    f"Share of {tn['en']} in {pn['en']}: {_n(top['share_pct'])}% ({per['en']}).",
                    f"حصة {tn['ar']} من {pn['ar']}: {_n(top['share_pct'])}% ({per['ar']}).",
                ),
                _t(
                    f"A single part above {SHARE_THRESHOLD}% of its total is flagged as concentration "
                    "(a project assumption, not an official standard).",
                    f"يُعدّ الجزء الواحد الذي يتجاوز {SHARE_THRESHOLD}% من إجماليه تركّزاً "
                    "(افتراض للمشروع، وليس معياراً رسمياً).",
                ),
                [used[0], top["ref"]],
            )
            recommendations.append(
                {
                    "kind": "diversify",
                    "based_on": [fid],
                    "text": _t(
                        f"Most of {pn['en']} depends on {tn['en']}: check how exposed it is to changes there "
                        "and whether diversification is a policy goal.",
                        f"يعتمد معظم {pn['ar']} على {tn['ar']}: تحقق من مدى تأثره بالتغيرات فيه "
                        "وما إذا كان التنويع هدفاً للسياسات.",
                    ),
                }
            )

    # Regional distribution: sub-national values against the national total of the same frame.
    regional, covered = [], set()
    by_indicator: dict[str, list[SeriesOut]] = defaultdict(list)
    for s in series:
        if s.meta["area"]["level"] == "governorate":
            covered.add(s.meta["area"]["code"])
        if s.meta["area"]["level"] in SUBNATIONAL and not (
            s.meta["commodity"] or s.meta["partner"]
        ):
            by_indicator[s.meta["indicator"]["code"]].append(s)
    for code, subs in sorted(by_indicator.items()):
        latest: dict[tuple, list[tuple[SeriesOut, dict]]] = defaultdict(list)
        for s in subs:
            for o in s.observations:
                if o["value"] is not None and o["period_complete"]:
                    latest[(_frame(s), o["period_start"], o["period_end"])].append((s, o))
        candidates = [k for k, v in latest.items() if len(v) >= 2]
        if not candidates:
            continue
        key = max(candidates, key=lambda k: (-KIND_ORDER.get(k[0][1], 9), k[2]))
        national = _values_at(series, code).get(key)
        total = Decimal(national[1]["value"]) if national else None
        rows = []
        for s, o in sorted(latest[key], key=lambda x: Decimal(x[1]["value"]), reverse=True):
            share = Decimal(o["value"]) * 100 / total if total else None
            rows.append(
                {
                    "area": {
                        "code": s.meta["area"]["code"],
                        "level": s.meta["area"]["level"],
                        "name": _t(s.meta["area"]["name_en"], s.meta["area"]["name_ar"]),
                    },
                    "value": o["value"],
                    "share_pct": None if share is None else str(share),
                    "ref": refs.from_obs(s, o),
                }
            )
        s0, o0 = latest[key][0]
        per = _period(o0["period_start"], o0["period_end"], s0.meta["period_kind"])
        regional.append(
            {
                "indicator": {"code": code, "name": _name(s0.meta["indicator"])},
                "unit": _unit(s0.meta["unit"]),
                "period": per,
                "national": national[1]["value"] if national else None,
                "national_ref": refs.from_obs(*national) if national else None,
                "areas": rows,
            }
        )
    if regional:
        recommendations.append(
            {
                "kind": "regional_screening",
                "based_on": [],
                "text": _t(
                    "Use the regional distribution to shortlist governorates for investment screening; any "
                    "investment decision needs a feasibility study beyond these figures.",
                    "استخدم التوزيع الإقليمي لاختيار محافظات مرشحة لفحص فرص الاستثمار؛ أي قرار استثماري "
                    "يحتاج إلى دراسة جدوى تتجاوز هذه الأرقام.",
                ),
            }
        )

    # Data gaps and coverage.
    today = datetime.now(UTC).date()
    published: dict[str, list[tuple[SeriesOut, dict]]] = defaultdict(list)
    for s in series:
        for o in s.observations:
            if o["value"] is not None:
                published[s.meta["indicator"]["code"]].append((s, o))
    gaps = []
    for i in registry:
        rows = published.get(i.code, [])
        if not rows:
            gaps.append(
                {"kind": "not_published", "indicator": {"code": i.code, "name": names[i.code]}}
            )
            continue
        last_end = max(date.fromisoformat(o["period_end"]) for _, o in rows)
        if today - last_end > STALE_AFTER:
            gaps.append(
                {
                    "kind": "stale",
                    "indicator": {"code": i.code, "name": names[i.code]},
                    "latest": last_end.isoformat(),
                }
            )
        if all(s.meta["period_kind"] == "statement" for s, _ in rows):
            gaps.append(
                {"kind": "statement_only", "indicator": {"code": i.code, "name": names[i.code]}}
            )
    regional_axis = section is not Section.TRADE  # trade figures are national by nature
    if regional_axis and len(covered) < GOVERNORATES:
        gaps.append({"kind": "regional", "covered": len(covered), "of": GOVERNORATES})
    missing = [g for g in gaps if g["kind"] == "not_published"]
    if missing:
        listed_en = ", ".join(g["indicator"]["name"]["en"] for g in missing[:4])
        listed_ar = "، ".join(g["indicator"]["name"]["ar"] for g in missing[:4])
        recommendations.append(
            {
                "kind": "fill_gaps",
                "based_on": [],
                "text": _t(
                    f"Request or import the unpublished series ({listed_en}{', …' if len(missing) > 4 else ''}) "
                    "from the official publisher before relying on this axis's balance.",
                    f"اطلب السلاسل غير المنشورة أو استوردها ({listed_ar}{'، …' if len(missing) > 4 else ''}) "
                    "من الجهة الرسمية قبل الاعتماد على ميزان هذا المحور.",
                ),
            }
        )
    if regional_axis and len(covered) < GOVERNORATES:
        recommendations.append(
            {
                "kind": "regional_coverage",
                "based_on": [],
                "text": _t(
                    f"Only {len(covered)} of {GOVERNORATES} governorates have published figures for this axis: "
                    "obtain governorate-level series to compare regions fairly.",
                    f"لا تتوفر أرقام منشورة لهذا المحور إلا في {len(covered)} من {GOVERNORATES} محافظة: "
                    "احصل على سلاسل على مستوى المحافظات لمقارنة المناطق بإنصاف.",
                ),
            }
        )

    # Review rules R01-R04 (thresholds are project assumptions shown with each card).
    for card in rules.evaluate(calcs, rules.RuleParameters()):
        used = [
            refs.from_input(i) for i in card.evidence.get("inputs", []) if i.get("source_title")
        ]
        rule = card.evidence.get("rule", {})
        risks.append(
            {
                "id": f"{card.rule_code}-{len(risks) + 1}",
                "kind": card.rule_code,
                "text": card.observation,
                "rule": rule.get("name", _t("", "")),
                "refs": used,
            }
        )
        recommendations.append(
            {"kind": "investigate", "based_on": [risks[-1]["id"]], "text": card.next_steps}
        )

    # Scenarios: series that can start a growth scenario, with their base values.
    scenario_series = [
        {
            "series_id": x["series_id"],
            "indicator": {
                "code": x["indicator"]["code"],
                "name": _t(x["indicator"]["name_en"], x["indicator"]["name_ar"]),
            },
            "area": _t(x["area"]["name_en"], x["area"]["name_ar"]),
            "unit": _unit(x["unit"]),
            "base": {
                "value": x["base"]["value"],
                "period": _period(x["base"]["period_start"], x["base"]["period_end"], "annual"),
            },
        }
        for x in scenarios.series(session, data_mode)
        if x["indicator"]["code"] in measures
    ]

    return {
        "section": section.value,
        "data_mode": data_mode.value,
        "version": BRIEF_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "performance": performance,
        "movers": [
            p["id"]
            for p in sorted(performance, key=lambda p: abs(Decimal(p["change_pct"])), reverse=True)[
                :3
            ]
        ],
        "composition": composition,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "balance": {
            "surplus": surplus,
            "shortage": shortage,
            # Electricity and water have no published demand-supply balance (peak demand and
            # reserve margins are not in the data); say so instead of guessing one.
            "assessable": bool(surplus or shortage),
        },
        "trade": trade,
        "regional": regional,
        "coverage": {"governorates": sorted(covered), "of": GOVERNORATES},
        "gaps": gaps,
        "risks": risks,
        "scenarios": scenario_series,
        "recommendations": recommendations,
        "provenance": refs.out(),
    }
