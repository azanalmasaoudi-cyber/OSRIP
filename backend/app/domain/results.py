"""Result type for transparent calculations.

A calculation never returns a bare number. It returns a status, the exact
(unrounded) value when one exists, a stable reason code when it does not, and
any interpretation caveats that must travel with the value to display and export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class CalcStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"  # an input is absent; never converted to zero (T02)
    UNDEFINED = "undefined"  # arithmetic undefined, e.g. previous value is zero (T01)
    INCOMPATIBLE = "incompatible"  # inputs cannot be compared (T03)
    NOT_CALCULATED = "not_calculated"  # guard failed, e.g. non-positive denominator


class ReasonCode(StrEnum):
    INPUT_MISSING = "input_missing"
    PREVIOUS_VALUE_ZERO = "previous_value_zero"
    DIMENSION_MISMATCH = "dimension_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    PERIOD_NOT_COMPARABLE = "period_not_comparable"
    COVERAGE_NOT_COMPARABLE = "coverage_not_comparable"
    NON_POSITIVE_DENOMINATOR = "non_positive_denominator"
    ZERO_OR_MISSING_QUANTITY = "zero_or_missing_quantity"
    CURRENCY_MISMATCH = "currency_mismatch"
    NO_PARTNER_RECORDS = "no_partner_records"
    COMMODITY_MISMATCH = "commodity_mismatch"
    STOCK_CHANGE_MISSING = "stock_change_missing"
    PARTNER_SUM_EXCEEDS_TOTAL = "partner_sum_exceeds_total"
    NON_POSITIVE_START = "non_positive_start"  # growth needs a positive first value
    PERIODS_NOT_IN_ORDER = "periods_not_in_order"
    COMPONENT_EXCEEDS_TOTAL = "component_exceeds_total"
    NOT_A_RATIO = "not_a_ratio"  # a self-sufficiency gap needs a percent ratio
    NEGATIVE_RATIO = "negative_ratio"


class Caveat(StrEnum):
    """Interpretation limits that must be shown beside the value."""

    STOCK_CHANGE_ASSUMED_ZERO = "stock_change_assumed_zero"
    STOCK_CHANGE_UNKNOWN_NOT_ADJUSTED = "stock_change_unknown_not_adjusted"
    EXCEEDS_100_PERCENT_NOT_CAPPED = "exceeds_100_percent_not_capped"
    NOT_COMPLETE_FOOD_SECURITY_MEASURE = "not_complete_food_security_measure"
    DOES_NOT_COMPLEMENT_PRODUCTION_RATIO = "does_not_complement_production_ratio"
    PARTIAL_PARTNER_COVERAGE = "partial_partner_coverage"
    NOT_RETAIL_PRICE = "not_retail_price"
    NOT_PROFIT_OR_LOSS = "not_profit_or_loss"
    NOMINAL_VALUE = "nominal_value"
    NOT_EFFICIENCY_MEASURE = "not_efficiency_measure"
    CONCENTRATION_NOT_DISRUPTION_PROBABILITY = "concentration_not_disruption_probability"


@dataclass(frozen=True, slots=True)
class CalcResult:
    status: CalcStatus
    value: Decimal | None = None
    reason: ReasonCode | None = None
    caveats: tuple[Caveat, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status is CalcStatus.OK and self.value is None:
            raise ValueError("An OK result must carry a value.")
        if self.status is not CalcStatus.OK and self.value is not None:
            raise ValueError("A non-OK result must not carry a value.")
        if self.status is not CalcStatus.OK and self.reason is None:
            raise ValueError("A non-OK result must carry a reason code.")

    @classmethod
    def ok(cls, value: Decimal, *caveats: Caveat) -> CalcResult:
        return cls(CalcStatus.OK, value, None, tuple(caveats))

    @classmethod
    def fail(cls, status: CalcStatus, reason: ReasonCode, *caveats: Caveat) -> CalcResult:
        return cls(status, None, reason, tuple(caveats))
