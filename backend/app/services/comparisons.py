"""Comparable views across areas for one indicator, period and unit.

Rules (booklet 3.20, the research brief):
* Only published values recorded for each exact area are shown. An area with no value is
  "no published value" (or "missing in the source" when the source lists it without a
  value); it is never zero.
* Nothing is inferred downwards: no governorate figure is split among its wilayats and no
  wilayat is given a share of a governorate or national total.
* Reporting groups (a source's combined figure for several governorates) are listed apart
  with their members and never divided.
* Values are compared only for the same period (same start and end) and the same unit.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import DataMode
from app.models import Area
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.observations import ObservationQuery, SeriesOut, query_observations

LEVELS = ("governorate", "wilayat")
NOTES = {
    "en": "Each value is published for that exact area. 'No published value' is not zero. No "
    "national or governorate total is divided among areas, and reporting groups are shown "
    "separately, undivided.",
    "ar": "كل قيمة منشورة لتلك المنطقة بعينها. «لا توجد قيمة منشورة» ليست صفراً. لا يُقسَّم أي "
    "مجموع وطني أو مجموع محافظة على المناطق، وتُعرض مجموعات الإبلاغ منفصلة دون تقسيم.",
}


def _series(
    session: Session, data_mode: DataMode, indicator: str, period_kind: str, flow: str | None
) -> list[SeriesOut]:
    floor = STATISTICAL_SCOPE_START if data_mode is DataMode.VERIFIED_SOURCE else None
    return [
        s
        for s in query_observations(
            session,
            ObservationQuery(
                data_mode,
                indicator=indicator,
                period_kind=period_kind,
                flow=flow,
                period_from=floor,
            ),
            allow_mixed=True,
        )
        if s.meta["partner"] is None and s.meta["commodity"] is None
    ]


def compare_areas(
    session: Session,
    data_mode: DataMode,
    indicator: str,
    period_kind: str = "annual",
    period_start: date | None = None,
    level: str = "governorate",
    flow: str | None = None,
) -> dict[str, Any]:
    """A comparison table, plus ``entries`` (series, observation) for evidence ledgers."""
    level = level if level in LEVELS else "governorate"
    series = _series(session, data_mode, indicator, period_kind, flow)
    flows = sorted({s.meta["flow"] for s in series if s.meta["flow"]})
    if flow is None and len(flows) > 1:
        return {"status": "choose_flow", "flows": flows, "entries": []}
    at_level = [s for s in series if s.meta["area"]["level"] == level]
    starts = Counter(
        o["period_start"] for s in at_level for o in s.observations if o["value"] is not None
    )
    periods = sorted(starts, reverse=True)
    if period_start is None:
        # The latest period that at least two areas report, so a comparison is possible.
        chosen = next((p for p in periods if starts[p] >= 2), periods[0] if periods else None)
    else:
        chosen = period_start.isoformat()
    if chosen is None:
        return {
            "status": "no_data",
            "indicator": indicator,
            "level": level,
            "available_periods": [],
            "notes": NOTES,
            "entries": [],
        }

    def pick(s: SeriesOut) -> dict[str, Any] | None:
        return next((o for o in s.observations if o["period_start"] == chosen), None)

    entries: list[tuple[SeriesOut, dict[str, Any]]] = []
    by_area: dict[str, tuple[SeriesOut, dict[str, Any]]] = {}
    for s in series:
        o = pick(s)
        if o is not None:
            by_area[s.meta["area"]["code"]] = (s, o)
    period_ends = {o["period_end"] for _, o in by_area.values()}
    units = {s.meta["unit"]["code"] for s, o in by_area.values() if o["value"] is not None}

    def row(code: str, name_en: str, name_ar: str) -> dict[str, Any]:
        found = by_area.get(code)
        if found is None:
            return {
                "area": code,
                "name": {"en": name_en, "ar": name_ar},
                "status": "no_published_value",
                "value": None,
            }
        s, o = found
        entries.append((s, o))
        return {
            "area": code,
            "name": {"en": name_en, "ar": name_ar},
            "status": "published" if o["value"] is not None else "missing_in_source",
            "value": o["value"],
            "value_operator": o.get("value_operator"),
            "period_end": o["period_end"],
            "record_ref": o.get("record_ref"),
            "revision_status": o.get("revision_status"),
            "source": s.meta["source"]["dataset_title"],
            "source_url": s.meta["source"]["url"],
        }

    areas = session.execute(
        select(Area.code, Area.name_en, Area.name_ar).where(Area.level == level).order_by(Area.code)
    ).all()
    rows = [row(code, en, ar) for code, en, ar in areas]
    if level == "wilayat":
        # 63 wilayats: list only those with their own published value, and count the rest.
        without = sum(1 for r in rows if r["status"] == "no_published_value")
        rows = [r for r in rows if r["status"] != "no_published_value"]
    else:
        without = sum(1 for r in rows if r["status"] == "no_published_value")
    national = None
    if "OM" in by_area:
        national = row(
            "OM", by_area["OM"][0].meta["area"]["name_en"], by_area["OM"][0].meta["area"]["name_ar"]
        )
    groups = []
    for code, (s, o) in by_area.items():
        if s.meta["area"]["level"] == "reporting_group":
            entries.append((s, o))
            groups.append(
                {
                    "area": code,
                    "name": {"en": s.meta["area"]["name_en"], "ar": s.meta["area"]["name_ar"]},
                    "value": o["value"],
                    "period_end": o["period_end"],
                    "record_ref": o.get("record_ref"),
                    "note": {
                        "en": "Combined figure published for several governorates; not divided.",
                        "ar": "رقم مجمّع منشور لعدة محافظات؛ لا يُقسَّم.",
                    },
                }
            )
    any_series = next(iter(by_area.values()), (series[0], None) if series else (None, None))[0]
    comparable = len(units) <= 1 and len(period_ends) <= 1
    return {
        "status": "ok" if comparable else "not_comparable",
        "reason": None
        if comparable
        else ("different_units" if len(units) > 1 else "different_period_lengths"),
        "indicator": indicator,
        "indicator_name": {
            "en": any_series.meta["indicator"]["name_en"],
            "ar": any_series.meta["indicator"]["name_ar"],
        }
        if any_series
        else None,
        "unit": any_series.meta["unit"] if any_series else None,
        "period_kind": period_kind,
        "period_start": chosen,
        "period_end": next(iter(period_ends)) if len(period_ends) == 1 else None,
        "level": level,
        "flow": flow or (flows[0] if flows else None),
        "rows": rows,
        "areas_without_value": without,
        "national": national,
        "reporting_groups": groups,
        "available_periods": periods,
        "notes": NOTES,
        "entries": entries,
    }


def public(result: dict[str, Any]) -> dict[str, Any]:
    """The comparison without the internal evidence entries."""
    return {k: v for k, v in result.items() if k != "entries"}
