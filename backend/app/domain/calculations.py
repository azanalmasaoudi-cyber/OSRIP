"""Transparent indicator calculations (booklet Table 3.1, Chapter 4).

Rules followed throughout:
* Decimal arithmetic; values are stored unrounded. Rounding is a display concern.
* Missing input -> MISSING, never zero (T02).
* Incomparable units, periods, coverage or commodities -> INCOMPATIBLE (T03).
* Guards from Table 3.1 produce UNDEFINED / NOT_CALCULATED with a reason code.
* Interpretation caveats travel with the result.

These functions do no I/O. They are the single source of truth for arithmetic;
the frontend displays API results and does not re-implement these formulas.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.compatibility import measurements_comparability, units_compatibility
from app.domain.enums import PhysicalDimension
from app.domain.quantities import Measurement
from app.domain.results import CalcResult, CalcStatus, Caveat, ReasonCode

HUNDRED = Decimal(100)
ZERO = Decimal(0)


# --------------------------------------------------------------------------- helpers


def _same_frame(first: Measurement, *others: Measurement) -> ReasonCode | None:
    """Components of one calculation must share period, coverage and commodity."""
    for other in others:
        if other.period != first.period:
            return ReasonCode.PERIOD_NOT_COMPARABLE
        if other.coverage != first.coverage:
            return ReasonCode.COVERAGE_NOT_COMPARABLE
        if other.commodity != first.commodity:
            return ReasonCode.COMMODITY_MISMATCH
    return None


def _same_unit(first: Measurement, *others: Measurement) -> ReasonCode | None:
    for other in others:
        reason = units_compatibility(first.unit, other.unit)
        if reason is not None:
            return reason
    return None


def _any_missing(*measurements: Measurement) -> bool:
    return any(m.value is None for m in measurements)


# --------------------------------------------------------------------------- change


def absolute_change(previous: Measurement, current: Measurement) -> CalcResult:
    reason = measurements_comparability(previous, current)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if previous.value is None or current.value is None:
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    return CalcResult.ok(current.value - previous.value)


def percentage_change(previous: Measurement, current: Measurement) -> CalcResult:
    """100 x (current - previous) / previous. Guard: comparable periods, previous != 0."""
    reason = measurements_comparability(previous, current)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if previous.value is None or current.value is None:
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    if previous.value == ZERO:
        return CalcResult.fail(CalcStatus.UNDEFINED, ReasonCode.PREVIOUS_VALUE_ZERO)
    return CalcResult.ok(HUNDRED * (current.value - previous.value) / previous.value)


def compound_annual_growth(first: Measurement, last: Measurement, years: int) -> CalcResult:
    """100 x ((last / first) ^ (1 / years) - 1): the constant yearly rate that links two
    comparable values ``years`` apart. Guards: comparable periods, units and coverage;
    later period after the earlier one; first value positive; last value not negative."""
    reason = measurements_comparability(first, last)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if years < 1 or last.period.start <= first.period.start:
        return CalcResult.fail(CalcStatus.NOT_CALCULATED, ReasonCode.PERIODS_NOT_IN_ORDER)
    if first.value is None or last.value is None:
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    if first.value <= ZERO or last.value < ZERO:
        return CalcResult.fail(CalcStatus.NOT_CALCULATED, ReasonCode.NON_POSITIVE_START)
    ratio = last.value / first.value
    return CalcResult.ok(HUNDRED * (ratio ** (Decimal(1) / Decimal(years)) - 1))


def share_of_total(part: Measurement, total: Measurement) -> CalcResult:
    """100 x part / total for a published component of a published total. Guards: same
    period, coverage, commodity and unit; positive total; the part may not exceed it."""
    reason = _same_frame(part, total) or _same_unit(part, total)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if part.value is None or total.value is None:
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    if total.value <= ZERO:
        return CalcResult.fail(CalcStatus.NOT_CALCULATED, ReasonCode.NON_POSITIVE_DENOMINATOR)
    if part.value > total.value:
        return CalcResult.fail(CalcStatus.NOT_CALCULATED, ReasonCode.COMPONENT_EXCEEDS_TOTAL)
    return CalcResult.ok(HUNDRED * part.value / total.value)


def use_per_subscriber(consumption: Measurement, subscribers: Measurement) -> CalcResult:
    """Consumption / subscriber count. Guard: same coverage and period."""
    if subscribers.unit.dimension is not PhysicalDimension.COUNT:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, ReasonCode.DIMENSION_MISMATCH)
    reason = _same_frame(consumption, subscribers)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if _any_missing(consumption, subscribers):
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    assert consumption.value is not None and subscribers.value is not None
    if subscribers.value <= ZERO:
        return CalcResult.fail(CalcStatus.NOT_CALCULATED, ReasonCode.NON_POSITIVE_DENOMINATOR)
    return CalcResult.ok(consumption.value / subscribers.value, Caveat.NOT_EFFICIENCY_MEASURE)


# --------------------------------------------------------------------------- food balance


class StockAssumption(StrEnum):
    KNOWN = "known"  # a compatible stock-increase value is supplied
    ASSUMED_ZERO = "assumed_zero"  # declared assumption, travels with result (T12)
    UNKNOWN = "unknown"  # apparent balance without stock adjustment (3.7)


def apparent_availability(
    production: Measurement,
    imports: Measurement,
    exports: Measurement,
    stock_assumption: StockAssumption,
    stock_increase: Measurement | None = None,
) -> CalcResult:
    """Production + imports - exports - stock increase (Table 3.1)."""
    components = [production, imports, exports]
    if stock_assumption is StockAssumption.KNOWN:
        if stock_increase is None:
            return CalcResult.fail(CalcStatus.MISSING, ReasonCode.STOCK_CHANGE_MISSING)
        components.append(stock_increase)

    if production.unit.dimension is not PhysicalDimension.MASS:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, ReasonCode.DIMENSION_MISMATCH)
    reason = _same_unit(*components) or _same_frame(*components)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if _any_missing(*components):
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)

    assert production.value is not None and imports.value is not None and exports.value is not None
    total = production.value + imports.value - exports.value
    if stock_assumption is StockAssumption.KNOWN:
        assert stock_increase is not None and stock_increase.value is not None
        return CalcResult.ok(total - stock_increase.value)
    if stock_assumption is StockAssumption.ASSUMED_ZERO:
        return CalcResult.ok(total, Caveat.STOCK_CHANGE_ASSUMED_ZERO)
    return CalcResult.ok(total, Caveat.STOCK_CHANGE_UNKNOWN_NOT_ADJUSTED)


def _share_of_availability(
    numerator: Measurement, availability: CalcResult, *extra: Caveat
) -> CalcResult:
    if availability.status is not CalcStatus.OK:
        assert availability.reason is not None
        return CalcResult.fail(availability.status, availability.reason, *availability.caveats)
    if numerator.value is None:
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    assert availability.value is not None
    if availability.value <= ZERO:
        return CalcResult.fail(
            CalcStatus.NOT_CALCULATED, ReasonCode.NON_POSITIVE_DENOMINATOR, *availability.caveats
        )
    share = HUNDRED * numerator.value / availability.value
    caveats = [*availability.caveats, *extra]
    if share > HUNDRED:
        caveats.append(Caveat.EXCEEDS_100_PERCENT_NOT_CAPPED)  # never silently capped
    return CalcResult.ok(share, *caveats)


def local_production_contribution(production: Measurement, availability: CalcResult) -> CalcResult:
    """100 x production / apparent availability. Guard: positive denominator."""
    return _share_of_availability(
        production, availability, Caveat.NOT_COMPLETE_FOOD_SECURITY_MEASURE
    )


def gross_import_contribution(imports: Measurement, availability: CalcResult) -> CalcResult:
    """100 x imports / apparent availability. Does not complement the production ratio."""
    return _share_of_availability(
        imports, availability, Caveat.DOES_NOT_COMPLEMENT_PRODUCTION_RATIO
    )


# --------------------------------------------------------------------------- partners


@dataclass(frozen=True, slots=True)
class PartnerConcentration:
    shares: Mapping[str, CalcResult]  # partner code -> percent of stated total
    largest_partner: str | None
    largest_share: CalcResult
    sum_of_squared_shares: CalcResult  # on a 0..1 scale (fractions squared)
    coverage_complete: bool


def partner_concentration(
    partner_quantities: Mapping[str, Measurement], total_imports: Measurement
) -> PartnerConcentration:
    """Partner shares against a stated national total (booklet 3.8, 4.3; T09).

    If the listed partners do not reconcile to the stated total, the results
    carry PARTIAL_PARTNER_COVERAGE and the subtotal is never presented as the total.
    """

    def blocked(status: CalcStatus, reason: ReasonCode) -> PartnerConcentration:
        failed = CalcResult.fail(status, reason)
        return PartnerConcentration({}, None, failed, failed, False)

    if not partner_quantities:
        return blocked(CalcStatus.NOT_CALCULATED, ReasonCode.NO_PARTNER_RECORDS)
    parts = list(partner_quantities.values())
    reason = _same_unit(total_imports, *parts) or _same_frame(total_imports, *parts)
    if reason is not None:
        return blocked(CalcStatus.INCOMPATIBLE, reason)
    if _any_missing(total_imports, *parts):
        return blocked(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    assert total_imports.value is not None
    if total_imports.value <= ZERO:
        return blocked(CalcStatus.NOT_CALCULATED, ReasonCode.NON_POSITIVE_DENOMINATOR)

    partner_sum = sum((m.value for m in parts if m.value is not None), ZERO)
    if partner_sum > total_imports.value:
        return blocked(CalcStatus.NOT_CALCULATED, ReasonCode.PARTNER_SUM_EXCEEDS_TOTAL)
    complete = partner_sum == total_imports.value
    coverage_caveats: tuple[Caveat, ...] = () if complete else (Caveat.PARTIAL_PARTNER_COVERAGE,)

    fractions: dict[str, Decimal] = {}
    shares: dict[str, CalcResult] = {}
    for code, measurement in partner_quantities.items():
        assert measurement.value is not None
        fraction = measurement.value / total_imports.value
        fractions[code] = fraction
        shares[code] = CalcResult.ok(HUNDRED * fraction, *coverage_caveats)

    largest = max(fractions, key=lambda code: fractions[code])
    concentration_caveats = (*coverage_caveats, Caveat.CONCENTRATION_NOT_DISRUPTION_PROBABILITY)
    return PartnerConcentration(
        shares=shares,
        largest_partner=largest,
        largest_share=CalcResult.ok(HUNDRED * fractions[largest], *concentration_caveats),
        sum_of_squared_shares=CalcResult.ok(
            sum((f * f for f in fractions.values()), ZERO), *concentration_caveats
        ),
        coverage_complete=complete,
    )


# --------------------------------------------------------------------------- trade values


def trade_balance(export_value: Measurement, import_value: Measurement) -> CalcResult:
    """Export value - import value. Guard: same currency, product and period."""
    if export_value.unit.dimension is not PhysicalDimension.CURRENCY:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, ReasonCode.DIMENSION_MISMATCH)
    if units_compatibility(export_value.unit, import_value.unit) is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, ReasonCode.CURRENCY_MISMATCH)
    reason = _same_frame(export_value, import_value)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if _any_missing(export_value, import_value):
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    assert export_value.value is not None and import_value.value is not None
    return CalcResult.ok(
        export_value.value - import_value.value, Caveat.NOT_PROFIT_OR_LOSS, Caveat.NOMINAL_VALUE
    )


def mean_unit_value(trade_value: Measurement, quantity: Measurement) -> CalcResult:
    """Trade value / physical quantity. Guard: nonzero compatible quantity."""
    if trade_value.unit.dimension is not PhysicalDimension.CURRENCY:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, ReasonCode.DIMENSION_MISMATCH)
    if quantity.unit.dimension is not PhysicalDimension.MASS:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, ReasonCode.DIMENSION_MISMATCH)
    reason = _same_frame(trade_value, quantity)
    if reason is not None:
        return CalcResult.fail(CalcStatus.INCOMPATIBLE, reason)
    if quantity.value is None or quantity.value == ZERO:
        return CalcResult.fail(CalcStatus.NOT_CALCULATED, ReasonCode.ZERO_OR_MISSING_QUANTITY)
    if trade_value.value is None:
        return CalcResult.fail(CalcStatus.MISSING, ReasonCode.INPUT_MISSING)
    return CalcResult.ok(
        trade_value.value / quantity.value, Caveat.NOT_RETAIL_PRICE, Caveat.NOMINAL_VALUE
    )
