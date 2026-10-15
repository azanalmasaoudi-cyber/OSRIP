"""Booklet Table 4.2 expected outputs and guard cases (T01, T02, T03, T09, T12).

Expected values are written as independently derived literals from the booklet,
not recomputed with the implementation's own formula (booklet 4.7, internal validity).
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.domain import calculations as calc
from app.domain.quantities import MW, SUBSCRIBERS, Period
from app.domain.results import CalcStatus, Caveat, ReasonCode
from tests import booklet_fixtures as fx


def q(value: str) -> Decimal:
    return Decimal(value)


# --------------------------------------------------------------- Table 4.2


def test_electricity_growth_is_4_375_percent_before_rounding() -> None:
    result = calc.percentage_change(fx.ELECTRICITY_GENERATION_Y1, fx.ELECTRICITY_GENERATION_Y2)
    assert result.status is CalcStatus.OK
    assert result.value == q("4.375")
    assert round(result.value, 2) == q("4.38")  # display rounding only


def test_electricity_absolute_increase_is_2100_gwh() -> None:
    result = calc.absolute_change(fx.ELECTRICITY_GENERATION_Y1, fx.ELECTRICITY_GENERATION_Y2)
    assert result.value == q("2100")


def test_water_growth_is_3_9393_percent() -> None:
    result = calc.percentage_change(fx.WATER_CONSUMPTION_Y1, fx.WATER_CONSUMPTION_Y2)
    assert result.status is CalcStatus.OK
    assert result.value is not None
    assert result.value.quantize(q("0.000001")) == q("3.939394")
    assert calc.absolute_change(fx.WATER_CONSUMPTION_Y1, fx.WATER_CONSUMPTION_Y2).value == q("13")


def test_food_apparent_availability_is_160000_with_zero_stock_assumption() -> None:
    result = calc.apparent_availability(
        fx.PRODUCTION, fx.IMPORTS, fx.EXPORTS, calc.StockAssumption.ASSUMED_ZERO
    )
    assert result.value == q("160000")
    assert Caveat.STOCK_CHANGE_ASSUMED_ZERO in result.caveats  # T12: assumption travels


def test_production_contribution_is_62_5_percent() -> None:
    availability = calc.apparent_availability(
        fx.PRODUCTION, fx.IMPORTS, fx.EXPORTS, calc.StockAssumption.ASSUMED_ZERO
    )
    result = calc.local_production_contribution(fx.PRODUCTION, availability)
    assert result.value == q("62.5")
    assert Caveat.STOCK_CHANGE_ASSUMED_ZERO in result.caveats
    assert Caveat.NOT_COMPLETE_FOOD_SECURITY_MEASURE in result.caveats


def test_gross_import_contribution_is_50_percent() -> None:
    availability = calc.apparent_availability(
        fx.PRODUCTION, fx.IMPORTS, fx.EXPORTS, calc.StockAssumption.ASSUMED_ZERO
    )
    result = calc.gross_import_contribution(fx.IMPORTS, availability)
    assert result.value == q("50")
    assert Caveat.DOES_NOT_COMPLEMENT_PRODUCTION_RATIO in result.caveats


def test_largest_partner_share_is_60_percent_partner_a() -> None:
    result = calc.partner_concentration(fx.PARTNER_IMPORTS, fx.IMPORTS)
    assert result.coverage_complete is True
    assert result.largest_partner == "PARTNER_A"
    assert result.largest_share.value == q("60")
    assert result.shares["PARTNER_B"].value == q("25")
    assert result.shares["PARTNER_C"].value == q("15")
    # 0.6^2 + 0.25^2 + 0.15^2
    assert result.sum_of_squared_shares.value == q("0.445")


def test_commodity_trade_balance_is_minus_28_million_omr() -> None:
    result = calc.trade_balance(fx.EXPORT_VALUE, fx.IMPORT_VALUE)
    assert result.value == q("-28000000")
    assert Caveat.NOT_PROFIT_OR_LOSS in result.caveats


def test_import_and_export_unit_values() -> None:
    assert calc.mean_unit_value(fx.IMPORT_VALUE, fx.IMPORTS).value == q("500")
    export_uv = calc.mean_unit_value(fx.EXPORT_VALUE, fx.EXPORTS)
    assert export_uv.value == q("600")
    assert Caveat.NOT_RETAIL_PRICE in export_uv.caveats


# --------------------------------------------------------------- guards


def test_t01_previous_zero_is_undefined_not_infinite() -> None:
    previous = replace(fx.ELECTRICITY_GENERATION_Y1, value=q("0"))
    result = calc.percentage_change(previous, fx.ELECTRICITY_GENERATION_Y2)
    assert result.status is CalcStatus.UNDEFINED
    assert result.reason is ReasonCode.PREVIOUS_VALUE_ZERO
    assert result.value is None


def test_t02_missing_previous_is_missing_not_zero_growth() -> None:
    previous = replace(fx.WATER_CONSUMPTION_Y1, value=None)
    result = calc.percentage_change(previous, fx.WATER_CONSUMPTION_Y2)
    assert result.status is CalcStatus.MISSING
    assert result.value is None


def test_t03_gwh_compared_with_mw_is_rejected() -> None:
    capacity = replace(fx.ELECTRICITY_GENERATION_Y2, unit=MW)
    result = calc.percentage_change(fx.ELECTRICITY_GENERATION_Y1, capacity)
    assert result.status is CalcStatus.INCOMPATIBLE
    assert result.reason is ReasonCode.DIMENSION_MISMATCH


def test_year_to_date_is_not_compared_with_complete_year() -> None:
    ytd = replace(
        fx.ELECTRICITY_GENERATION_Y2,
        period=Period(date(2002, 1, 1), date(2002, 6, 30), is_complete=False),
    )
    result = calc.percentage_change(fx.ELECTRICITY_GENERATION_Y1, ytd)
    assert result.status is CalcStatus.INCOMPATIBLE
    assert result.reason is ReasonCode.PERIOD_NOT_COMPARABLE


def test_matching_year_to_date_periods_are_comparable() -> None:
    prev = replace(
        fx.ELECTRICITY_GENERATION_Y1,
        period=Period(date(2001, 1, 1), date(2001, 6, 30), is_complete=False),
    )
    cur = replace(
        fx.ELECTRICITY_GENERATION_Y2,
        period=Period(date(2002, 1, 1), date(2002, 6, 30), is_complete=False),
    )
    assert calc.percentage_change(prev, cur).status is CalcStatus.OK


def test_zero_or_negative_availability_blocks_ratio() -> None:
    exports = replace(fx.EXPORTS, value=q("180000"))
    availability = calc.apparent_availability(
        fx.PRODUCTION, fx.IMPORTS, exports, calc.StockAssumption.ASSUMED_ZERO
    )
    assert availability.value == q("0")
    result = calc.local_production_contribution(fx.PRODUCTION, availability)
    assert result.status is CalcStatus.NOT_CALCULATED
    assert result.reason is ReasonCode.NON_POSITIVE_DENOMINATOR


def test_contribution_above_100_percent_is_not_capped() -> None:
    exports = replace(fx.EXPORTS, value=q("120000"))  # availability 60,000
    availability = calc.apparent_availability(
        fx.PRODUCTION, fx.IMPORTS, exports, calc.StockAssumption.ASSUMED_ZERO
    )
    result = calc.local_production_contribution(fx.PRODUCTION, availability)
    assert result.value is not None and result.value > q("100")
    assert Caveat.EXCEEDS_100_PERCENT_NOT_CAPPED in result.caveats


def test_unknown_stock_is_labelled_not_adjusted() -> None:
    result = calc.apparent_availability(
        fx.PRODUCTION, fx.IMPORTS, fx.EXPORTS, calc.StockAssumption.UNKNOWN
    )
    assert Caveat.STOCK_CHANGE_UNKNOWN_NOT_ADJUSTED in result.caveats


def test_known_stock_without_value_is_missing_not_zero() -> None:
    result = calc.apparent_availability(
        fx.PRODUCTION, fx.IMPORTS, fx.EXPORTS, calc.StockAssumption.KNOWN, stock_increase=None
    )
    assert result.status is CalcStatus.MISSING


def test_different_commodities_are_not_combined() -> None:
    other = replace(fx.IMPORTS, commodity="OTHER")
    result = calc.apparent_availability(
        fx.PRODUCTION, other, fx.EXPORTS, calc.StockAssumption.ASSUMED_ZERO
    )
    assert result.status is CalcStatus.INCOMPATIBLE
    assert result.reason is ReasonCode.COMMODITY_MISMATCH


def test_t09_partner_subtotal_is_labelled_partial() -> None:
    subset = {k: v for k, v in fx.PARTNER_IMPORTS.items() if k != "PARTNER_C"}
    result = calc.partner_concentration(subset, fx.IMPORTS)
    assert result.coverage_complete is False
    assert result.largest_share.value == q("60")  # denominator stays the stated total
    assert Caveat.PARTIAL_PARTNER_COVERAGE in result.largest_share.caveats


def test_partner_sum_above_total_fails_reconciliation() -> None:
    total = replace(fx.IMPORTS, value=q("70000"))
    result = calc.partner_concentration(fx.PARTNER_IMPORTS, total)
    assert result.largest_share.reason is ReasonCode.PARTNER_SUM_EXCEEDS_TOTAL


def test_unit_value_with_zero_quantity_is_not_calculated() -> None:
    result = calc.mean_unit_value(fx.IMPORT_VALUE, replace(fx.IMPORTS, value=q("0")))
    assert result.status is CalcStatus.NOT_CALCULATED
    assert result.reason is ReasonCode.ZERO_OR_MISSING_QUANTITY


def test_per_subscriber_requires_count_denominator_and_carries_caveat() -> None:
    subs = replace(fx.WATER_CONSUMPTION_Y2, value=q("1000"), unit=SUBSCRIBERS)
    result = calc.use_per_subscriber(fx.WATER_CONSUMPTION_Y2, subs)
    assert result.value == q("0.343")
    assert Caveat.NOT_EFFICIENCY_MEASURE in result.caveats
