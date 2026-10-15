"""Hypothetical scenario explorer: assumptions applied to the latest published value.

Kept apart from forecasting on purpose: no error measures, no intervals, and the
label says it is not a forecast (app.domain.scenarios).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import unprocessable
from app.domain import scenarios as sc
from app.domain.enums import DataMode
from app.services.exports import mode_label
from app.services.forecasting import _describe, _series_id
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.observations import ObservationQuery, SeriesOut, query_observations

INDICATORS = {
    "ELEC_CONSUMPTION",
    "ELEC_GENERATION",
    "WATER_CONSUMPTION",
    "WATER_PRODUCTION",
    "FOOD_PRODUCTION",
    "TRADE_QUANTITY",
    "TRADE_VALUE",
    # Reference-pack indicators (migration 0009).
    "ELEC_GROSS_GENERATION",
    "ELEC_NET_GENERATION",
    "ELEC_INSTALLED_CAPACITY",
    "WATER_DISTRIBUTION",
    "AGRI_CROP_PRODUCTION",
    "FISH_CAPTURE_LANDINGS",
    "TRADE_MERCH_EXPORTS",
    "TRADE_MERCH_IMPORTS",
    "TRADE_NON_OIL_EXPORTS",
}


def _series(session: Session, data_mode: DataMode) -> list[SeriesOut]:
    floor = STATISTICAL_SCOPE_START if data_mode is DataMode.VERIFIED_SOURCE else None
    return [
        s
        for s in query_observations(
            session, ObservationQuery(data_mode, period_from=floor), allow_mixed=True
        )
        if s.meta["indicator"]["code"] in INDICATORS
        and s.meta["partner"] is None
        # A scenario starts from a complete year, never a year-to-date total or statement.
        and s.meta.get("period_kind") == "annual"
    ]


def _latest(s: SeriesOut) -> dict[str, Any] | None:
    complete = [o for o in s.observations if o["value"] is not None and o["period_complete"]]
    return complete[-1] if complete else None


def series(session: Session, data_mode: DataMode) -> list[dict[str, Any]]:
    out = []
    for s in _series(session, data_mode):
        latest = _latest(s)
        if latest:
            out.append({**_describe(s), "base": latest})
    return out


def projection(
    session: Session,
    data_mode: DataMode,
    series_id: str,
    growth_pct: Decimal,
    years: int,
    one_off_pct: Decimal,
) -> dict[str, Any]:
    match = next((s for s in _series(session, data_mode) if _series_id(s) == series_id), None)
    if match is None:
        raise unprocessable("unknown_series", "That series is not published in this data mode.")
    latest = _latest(match)
    if latest is None:
        raise unprocessable(
            "no_base_value", "This series has no complete published value to start from."
        )
    try:
        points = sc.project(Decimal(latest["value"]), growth_pct, years, one_off_pct)
    except ValueError as exc:
        raise unprocessable("invalid_assumption", str(exc)) from exc
    base_start = date.fromisoformat(latest["period_start"])
    m = match.meta
    return {
        "kind": "hypothetical_scenario",
        "label": sc.LABEL,
        "data_mode": data_mode.value,
        "mode_label": mode_label(data_mode),
        "series": _describe(match),
        "base": {
            **latest,
            "source": {
                "title": m["source"]["dataset_title"],
                "publisher": m["source"]["publisher"],
                "url": m["source"]["url"],
            },
            "dataset_version": m["dataset_version"]["label"],
        },
        "assumptions": {
            "growth_pct": format(growth_pct, "f"),
            "years": years,
            "one_off_pct": format(one_off_pct, "f"),
        },
        "formula": {
            "en": "value(k) = base × (1 + one-off change) × (1 + annual growth)^k",
            "ar": "القيمة(k) = الأساس × (1 + التغير لمرة واحدة) × (1 + النمو السنوي)^k",
        },
        "points": [
            {"step": p.step, "year": base_start.year + p.step, "value": format(p.value, "f")}
            for p in points
        ],
    }
