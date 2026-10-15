"""Forecast selection, horizons, future estimates, intervals and scenarios (pure).

Expected values are computed independently with the standard library's
``statistics`` module (floats), not with the implementation's Decimal formulas.
"""

from __future__ import annotations

import statistics
from datetime import date
from decimal import Decimal

import pytest

from app.domain import forecasting as fc
from app.domain import scenarios as sc
from app.domain.enums import Frequency

VALUES = [100, 104, 103, 110, 112, 115, 113, 120, 126, 125, 131, 138]


def annual(values: list[int]) -> list[fc.Point]:
    return [
        fc.Point(date(2008 + i, 1, 1), date(2008 + i, 12, 31), Decimal(v))
        for i, v in enumerate(values)
    ]


def monthly(values: list[float], start_year: int = 2022) -> list[fc.Point]:
    points = []
    for i, v in enumerate(values):
        start = date(start_year + i // 12, i % 12 + 1, 1)
        end = fc._add_months(start, 1).replace(day=1)
        points.append(fc.Point(start, date.fromordinal(end.toordinal() - 1), Decimal(str(v))))
    return points


def close(a: Decimal | None, b: float, tol: float = 1e-9) -> bool:
    return a is not None and abs(float(a) - b) < tol


def test_baseline_interval_uses_the_spread_of_period_changes() -> None:
    [est] = fc.forecast_future(annual(VALUES), Frequency.ANNUAL, fc.BASELINE, 1)
    sd = statistics.stdev([b - a for a, b in zip(VALUES, VALUES[1:], strict=False)])
    assert est.estimate == 138
    assert (est.period_start, est.period_end) == (date(2020, 1, 1), date(2020, 12, 31))
    assert close(est.lower80, 138 - 1.2816 * sd) and close(est.upper95, 138 + 1.96 * sd)


def test_baseline_interval_widens_with_the_square_root_of_the_horizon() -> None:
    ests = fc.forecast_future(annual(VALUES), Frequency.ANNUAL, fc.BASELINE, 3)
    sd = statistics.stdev([b - a for a, b in zip(VALUES, VALUES[1:], strict=False)])
    assert close(ests[2].upper80, 138 + 1.2816 * sd * 3**0.5)
    assert [e.period_start.year for e in ests] == [2020, 2021, 2022]


def test_linear_trend_estimate_and_ols_prediction_interval() -> None:
    xs = list(range(12))
    slope, intercept = statistics.linear_regression(xs, VALUES)
    residuals = [v - (intercept + slope * x) for x, v in zip(xs, VALUES, strict=True)]
    s = (sum(r * r for r in residuals) / 10) ** 0.5
    x_mean = statistics.fmean(xs)
    sxx = sum((x - x_mean) ** 2 for x in xs)
    [est] = fc.forecast_future(annual(VALUES), Frequency.ANNUAL, fc.CANDIDATE, 1)
    expected = intercept + slope * 12
    half80 = 1.372 * s * (1 + 1 / 12 + (12 - x_mean) ** 2 / sxx) ** 0.5  # t(0.90, df=10)
    assert close(est.estimate, expected, 1e-9)
    assert close(est.upper80, expected + half80, 1e-6)


def test_seasonal_naive_repeats_last_year_and_is_selected_when_it_backtests_best() -> None:
    values = [100 + (i % 12) * 5 + (i // 12) * 3 for i in range(36)]  # strong season, small trend
    points = monthly(values)
    preds = fc.evaluate(points, fc.POLICIES[Frequency.MONTHLY], season=12)
    models = {p.model for p in preds}
    assert models == {fc.BASELINE, fc.CANDIDATE, fc.SEASONAL}
    assert fc.same_dates([p for p in preds if p.model != fc.SEASONAL])
    m = fc.metrics(preds)
    assert m[fc.SEASONAL].mae == 3  # every seasonal error is exactly the yearly step
    assert fc.select_model(m) == fc.SEASONAL
    ests = fc.forecast_future(points, Frequency.MONTHLY, fc.SEASONAL, 12)
    assert [float(e.estimate) for e in ests] == [float(v) for v in values[24:36]]
    # Year-on-year changes have zero spread here: no interval rather than a zero-width one.
    assert (ests[0].lower80, ests[0].upper95) == (None, None)
    assert (ests[0].period_start, ests[-1].period_end) == (date(2025, 1, 1), date(2025, 12, 31))


def test_seasonal_interval_uses_the_spread_of_year_on_year_changes() -> None:
    noise = [0, 2, -1, 3, -2, 1, 0, -3, 2, 1, -1, 2]
    values = [100 + (i % 12) * 5 + (i // 12) * 3 + noise[i % 11] for i in range(36)]
    ests = fc.forecast_future(monthly(values), Frequency.MONTHLY, fc.SEASONAL, 12)
    sd = statistics.stdev([values[i] - values[i - 12] for i in range(12, 36)])
    assert close(ests[0].upper80, values[24] + 1.2816 * sd)
    assert close(ests[11].lower95, values[35] - 1.96 * sd)


def test_a_perfect_straight_line_gives_no_interval() -> None:
    [est] = fc.forecast_future(annual([10, 20, 30, 40, 50]), Frequency.ANNUAL, fc.CANDIDATE, 1)
    assert est.estimate == 60
    assert est.lower80 is None and est.upper95 is None


def test_the_baseline_stays_unless_a_candidate_is_strictly_better() -> None:
    m = {
        fc.BASELINE: fc.Metrics(fc.BASELINE, 4, Decimal(5), Decimal(6)),
        fc.CANDIDATE: fc.Metrics(fc.CANDIDATE, 4, Decimal(5), Decimal(4)),
    }
    assert fc.select_model(m) == fc.BASELINE  # equal MAE is not an improvement
    m[fc.CANDIDATE] = fc.Metrics(fc.CANDIDATE, 4, Decimal("4.9"), Decimal(7))
    assert fc.select_model(m) == fc.CANDIDATE


@pytest.mark.parametrize(
    ("frequency", "n", "expected"),
    [
        (Frequency.ANNUAL, 12, 3),
        (Frequency.ANNUAL, 8, 2),
        (Frequency.MONTHLY, 36, 9),
        (Frequency.MONTHLY, 60, 12),
    ],
)
def test_horizon_is_limited_by_history_and_held_out_size(
    frequency: Frequency, n: int, expected: int
) -> None:
    assert fc.horizon_for(frequency, n, fc.POLICIES[frequency]) == expected


def test_scenario_projection_is_plain_compound_arithmetic() -> None:
    points = sc.project(Decimal(100), Decimal(10), 3, Decimal(-50))
    assert [p.value for p in points] == [Decimal("55.0"), Decimal("60.50"), Decimal("66.550")]
    with pytest.raises(ValueError):
        sc.project(Decimal(100), Decimal(60), 3)
    with pytest.raises(ValueError):
        sc.project(Decimal(100), Decimal(1), 11)
    assert "not a forecast" in sc.LABEL["en"]
