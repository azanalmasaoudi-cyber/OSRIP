"""Comparability guards (booklet 3.3, 3.5, Table 3.1; tests T03)."""

from __future__ import annotations

import calendar

from app.domain.quantities import Measurement, Period, Unit
from app.domain.results import ReasonCode


def _is_whole_months(period: Period) -> bool:
    last_day = calendar.monthrange(period.end.year, period.end.month)[1]
    return period.start.day == 1 and period.end.day == last_day


def _month_span(period: Period) -> int:
    return (period.end.year - period.start.year) * 12 + period.end.month - period.start.month + 1


def units_compatibility(a: Unit, b: Unit) -> ReasonCode | None:
    """Return ``None`` when directly comparable, else the blocking reason.

    The foundation performs no unit conversion: identical unit codes are
    required. Different codes in the same dimension (e.g. GWh vs MWh) are
    rejected until an explicit, tested conversion factor is registered.
    """
    if a.dimension is not b.dimension:
        return ReasonCode.DIMENSION_MISMATCH
    if a.code != b.code:
        return ReasonCode.UNIT_MISMATCH
    return None


def periods_comparability(previous: Period, current: Period) -> ReasonCode | None:
    """Comparable periods: same completeness, same length, no overlap.

    Complete years compare with complete years; year-to-date periods compare
    only with year-to-date periods covering the same months.
    """
    if previous.end >= current.start:
        return ReasonCode.PERIOD_NOT_COMPARABLE
    if previous.is_complete != current.is_complete:
        return ReasonCode.PERIOD_NOT_COMPARABLE
    if _is_whole_months(previous) and _is_whole_months(current):
        if _month_span(previous) != _month_span(current):
            return ReasonCode.PERIOD_NOT_COMPARABLE
        if not previous.is_complete and (
            previous.start.month != current.start.month or previous.end.month != current.end.month
        ):
            return ReasonCode.PERIOD_NOT_COMPARABLE
        return None
    if previous.length_days != current.length_days:
        return ReasonCode.PERIOD_NOT_COMPARABLE
    return None


def measurements_comparability(previous: Measurement, current: Measurement) -> ReasonCode | None:
    reason = units_compatibility(previous.unit, current.unit)
    if reason is not None:
        return reason
    if previous.coverage != current.coverage:
        return ReasonCode.COVERAGE_NOT_COMPARABLE
    return periods_comparability(previous.period, current.period)
