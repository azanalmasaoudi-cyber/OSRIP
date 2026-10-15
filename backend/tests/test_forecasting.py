"""Forecast eligibility and chronological evaluation (pure; booklet 2.4, 4.6, T10).

Expected numbers are worked by hand in the comments, not recomputed with the
implementation's formulas.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext

from app.domain import forecasting as fc
from app.domain.enums import DataMode, Frequency

VALUES = [100, 104, 103, 110, 112, 115, 113, 120, 126, 125, 131, 138]


def annual(values: list[int | None], first_year: int = 2008) -> list[fc.Point]:
    return [
        fc.Point(
            date(first_year + i, 1, 1),
            date(first_year + i, 12, 31),
            None if v is None else Decimal(v),
        )
        for i, v in enumerate(values)
    ]


def codes(e: fc.Eligibility) -> set[str]:
    return {r.code for r in e.reasons}


# ------------------------------------------------------------------ eligibility


def test_two_points_are_insufficient_history_and_withheld() -> None:
    e = fc.check_eligibility(annual([48000, 50100]), Frequency.ANNUAL, DataMode.VERIFIED_SOURCE)
    assert not e.eligible
    assert codes(e) == {"insufficient_history"}
    assert "needs at least 12" in e.reasons[0].en


def test_twelve_complete_consecutive_annual_values_are_eligible() -> None:
    e = fc.check_eligibility(annual(VALUES), Frequency.ANNUAL, DataMode.VERIFIED_SOURCE)
    assert e.eligible and e.reasons == [] and not e.demonstration_only
    assert len(e.points) == 12


def test_missing_values_are_not_imputed() -> None:
    values: list[int | None] = list(VALUES)
    values[5] = None
    e = fc.check_eligibility(annual(values), Frequency.ANNUAL, DataMode.VERIFIED_SOURCE)
    assert codes(e) == {"missing_values"}


def test_withheld_values_count_as_missing() -> None:
    points = annual(VALUES)
    points[3] = replace(points[3], quality_status="withheld")
    assert codes(fc.check_eligibility(points, Frequency.ANNUAL, DataMode.VERIFIED_SOURCE)) == {
        "missing_values"
    }


def test_gaps_make_a_series_ineligible() -> None:
    points = annual(VALUES + [140])
    del points[4]  # 2012 missing: 12 points but not consecutive
    e = fc.check_eligibility(points, Frequency.ANNUAL, DataMode.VERIFIED_SOURCE)
    assert codes(e) == {"irregular_periods"}


def test_trailing_year_to_date_period_is_dropped_with_a_note() -> None:
    points = annual(VALUES + [70])
    points[-1] = replace(points[-1], period_complete=False)
    e = fc.check_eligibility(points, Frequency.ANNUAL, DataMode.VERIFIED_SOURCE)
    assert e.eligible
    assert len(e.points) == 12 and e.points[-1].period_start == date(2019, 1, 1)
    assert [n.code for n in e.notes] == ["trailing_incomplete_dropped"]


def test_incomplete_period_inside_the_series_is_ineligible() -> None:
    points = annual(VALUES)
    points[6] = replace(points[6], period_complete=False)
    assert "incomplete_periods" in codes(
        fc.check_eligibility(points, Frequency.ANNUAL, DataMode.VERIFIED_SOURCE)
    )


def test_synthetic_series_is_marked_demonstration_only() -> None:
    e = fc.check_eligibility(annual(VALUES), Frequency.ANNUAL, DataMode.SYNTHETIC)
    assert e.eligible and e.demonstration_only
    assert "synthetic_demonstration_only" in {n.code for n in e.notes}


def test_monthly_needs_three_years() -> None:
    policy = fc.POLICIES[Frequency.MONTHLY]
    assert policy.minimum_length == 36 and policy.test_size == 12


# ------------------------------------------------------------------ evaluation


def test_baseline_and_candidate_forecast_identical_held_out_dates() -> None:
    preds = fc.evaluate(annual(VALUES), fc.POLICIES[Frequency.ANNUAL])
    assert len(preds) == 8
    assert fc.same_dates(preds)
    targets = sorted({p.target_period_start.year for p in preds})
    assert targets == [2016, 2017, 2018, 2019]
    for p in preds:
        assert p.training_end < p.target_period_start  # chronology
        assert p.training_start == date(2008, 1, 1)  # expanding window
        assert p.training_size == p.target_period_start.year - 2008
        assert p.horizon_steps == 1
        assert p.error == p.actual - p.predicted


def test_baseline_repeats_the_last_training_value() -> None:
    preds = fc.evaluate(annual(VALUES), fc.POLICIES[Frequency.ANNUAL])
    base = [p for p in preds if p.model == fc.BASELINE]
    assert [p.predicted for p in base] == [Decimal(v) for v in (120, 126, 125, 131)]
    assert [p.error for p in base] == [Decimal(v) for v in (6, -1, 6, 7)]
    m = fc.metrics(preds)[fc.BASELINE]
    # |6| + |-1| + |6| + |7| = 20 over 4 -> 5;  (36 + 1 + 36 + 49) / 4 = 30.5 -> sqrt(30.5)
    assert m.n == 4 and m.mae == Decimal(5)
    assert m.rmse == Decimal("30.5").sqrt()


def test_candidate_first_fold_matches_hand_computed_least_squares() -> None:
    # Training 2008-2015: y = 100,104,103,110,112,115,113,120; x centred at 3.5.
    # Sxy = 111.5, Sxx = 42, mean = 109.625; forecast at x = 8: 109.625 + 4.5 * 111.5 / 42 = 851/7.
    preds = fc.evaluate(annual(VALUES), fc.POLICIES[Frequency.ANNUAL])
    first = next(p for p in preds if p.model == fc.CANDIDATE and p.fold == 1)
    assert abs(first.predicted - Decimal(851) / Decimal(7)) < Decimal("1e-24")


def test_linear_series_is_forecast_exactly_by_the_trend_and_off_by_the_step_by_the_baseline() -> (
    None
):
    points = annual([10 + 2 * i for i in range(12)])
    m = fc.metrics(fc.evaluate(points, fc.POLICIES[Frequency.ANNUAL]))
    assert m[fc.CANDIDATE].mae == 0 and m[fc.CANDIDATE].rmse == 0
    assert m[fc.BASELINE].mae == 2 and m[fc.BASELINE].rmse == 2


def test_later_values_never_change_earlier_forecasts() -> None:
    """Transformations are fitted inside each training window: no look-ahead."""
    policy = fc.POLICIES[Frequency.ANNUAL]
    original = fc.evaluate(annual(VALUES), policy)
    changed = fc.evaluate(annual(VALUES[:-1] + [10_000]), policy)
    for a, b in zip(original, changed, strict=True):
        if a.target_period_start.year < 2019:
            assert a.predicted == b.predicted
    last = [p for p in changed if p.target_period_start.year == 2019]
    assert all(p.actual == 10_000 for p in last)


def test_metrics_use_literal_errors() -> None:
    def pred(error: str) -> fc.Prediction:
        d = date(2020, 1, 1)
        return fc.Prediction(
            fc.BASELINE, 1, 1, d, d, 1, d, d, Decimal(0), Decimal(error), Decimal(error)
        )

    m = fc.metrics([pred("1"), pred("-3")])[fc.BASELINE]
    assert m.mae == 2 and m.rmse == Decimal(5).sqrt()


def test_stored_error_is_exact_for_long_decimals() -> None:
    values = [Decimal("123456789.123456789") + Decimal(i) / 3 for i in range(12)]
    points = [
        fc.Point(date(2000 + i, 1, 1), date(2000 + i, 12, 31), v) for i, v in enumerate(values)
    ]
    for p in fc.evaluate(points, fc.POLICIES[Frequency.ANNUAL]):
        with localcontext() as ctx:
            ctx.prec = 200
            assert p.error + p.predicted == p.actual
