"""Forecast eligibility and chronological evaluation (booklet 2.4, 4.6, T10). Pure.

The experiment is defined before anything is fitted: one named series, its unit,
a one-step horizon, rolling-origin splits over the final ``test_size`` periods, a
last-value baseline and a candidate linear trend. For every held-out period both
models are fitted on the observations strictly before it (expanding window), so
they forecast exactly the same dates and nothing after the forecast origin is
used. The only transformation (centring the time index) is computed from the
training window of each fold. No interval is produced (see ``INTERVAL_METHOD``).

Missing values are never imputed; a series with gaps, missing values or
incomplete periods (other than a trailing year-to-date period, which is dropped)
is ineligible and the forecast is withheld with the reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, localcontext

from app.domain.enums import DataMode, Frequency

METHOD_CODE = "FORECAST_LAST_VALUE_VS_LINEAR_TREND"
METHOD_VERSION = "forecast-2.0"
BASELINE = "baseline_last_value"
CANDIDATE = "candidate_linear_trend"
SEASONAL = "candidate_seasonal_naive"
SEASON_LENGTH = {Frequency.MONTHLY: 12, Frequency.QUARTERLY: 4}
INTERVAL_METHOD = {
    "code": "none",
    "en": "No prediction interval is produced. With the few held-out errors available, an "
    "empirical or model-based interval would not be supported by the data.",
    "ar": "لا تُنتَج فترة تنبؤ. مع قلة أخطاء فترات الاختبار المتاحة لن تكون فترة تجريبية أو "
    "مبنية على نموذج مدعومة بالبيانات.",
}


@dataclass(frozen=True, slots=True)
class Policy:
    """Project assumptions (not booklet values; see docs/SPEC_CONFLICTS.md C10)."""

    min_training: int
    test_size: int
    horizon: int = 1

    @property
    def minimum_length(self) -> int:
        return self.min_training + self.test_size


POLICIES: dict[Frequency, Policy] = {
    Frequency.ANNUAL: Policy(min_training=8, test_size=4),
    Frequency.QUARTERLY: Policy(min_training=12, test_size=4),
    Frequency.MONTHLY: Policy(min_training=24, test_size=12),
}


@dataclass(frozen=True, slots=True)
class Point:
    period_start: date
    period_end: date
    value: Decimal | None
    period_complete: bool = True
    quality_status: str = "accepted"


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    en: str
    ar: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "en": self.en, "ar": self.ar}


@dataclass(slots=True)
class Eligibility:
    eligible: bool
    reasons: list[Reason]
    points: list[Point]  # the observations the experiment would use
    notes: list[Reason] = field(default_factory=list)
    demonstration_only: bool = False


def _reason(code: str, en: str, ar: str) -> Reason:
    return Reason(code, en, ar)


def check_eligibility(
    points: list[Point], frequency: Frequency, data_mode: DataMode
) -> Eligibility:
    """Decide whether a series supports the experiment, with every failing reason."""
    ordered = sorted(points, key=lambda p: p.period_start)
    reasons: list[Reason] = []
    notes: list[Reason] = []

    policy = POLICIES.get(frequency)
    if policy is None:  # pragma: no cover - every Frequency has a policy
        reasons.append(
            _reason("unsupported_frequency", "Unsupported frequency.", "تكرار غير مدعوم.")
        )
        return Eligibility(False, reasons, [])

    if ordered and not ordered[-1].period_complete:
        ordered = ordered[:-1]
        notes.append(
            _reason(
                "trailing_incomplete_dropped",
                "The latest period is incomplete (year-to-date) and is not used.",
                "الفترة الأخيرة غير مكتملة (منذ بداية السنة) ولا تُستخدم.",
            )
        )
    if any(not p.period_complete for p in ordered):
        reasons.append(
            _reason(
                "incomplete_periods",
                "The series contains incomplete periods before its latest period.",
                "تحتوي السلسلة على فترات غير مكتملة قبل فترتها الأخيرة.",
            )
        )
    if any(p.value is None or p.quality_status == "withheld" for p in ordered):
        reasons.append(
            _reason(
                "missing_values",
                "The series has missing or withheld values. They are not imputed, so the series "
                "cannot be used.",
                "في السلسلة قيم مفقودة أو محجوبة. لا تُقدَّر هذه القيم، لذا لا يمكن استخدام السلسلة.",
            )
        )
    pairs = zip(ordered, ordered[1:], strict=False)
    if any(b.period_start != a.period_end + timedelta(days=1) for a, b in pairs):
        reasons.append(
            _reason(
                "irregular_periods",
                "The periods are not consecutive (there are gaps or overlaps).",
                "الفترات غير متتالية (توجد فجوات أو تداخلات).",
            )
        )
    if len(ordered) < policy.minimum_length:
        reasons.append(
            _reason(
                "insufficient_history",
                f"{len(ordered)} usable {frequency.value} observations; the experiment needs "
                f"at least {policy.minimum_length} ({policy.min_training} for the first training "
                "window and "
                f"{policy.test_size} held out).",
                f"{len(ordered)} مشاهدة صالحة ({frequency.value})؛ تحتاج التجربة إلى "
                f"{policy.minimum_length} على الأقل ({policy.min_training} لأول نافذة تدريب و"
                f"{policy.test_size} للاختبار).",
            )
        )
    demo = data_mode is DataMode.SYNTHETIC
    if demo:
        notes.append(
            _reason(
                "synthetic_demonstration_only",
                "Synthetic data: any output demonstrates software behaviour only and is not a "
                "forecast for Oman.",
                "بيانات اصطناعية: أي ناتج يوضح سلوك البرنامج فقط وليس تنبؤاً لعُمان.",
            )
        )
    return Eligibility(not reasons, reasons, ordered, notes, demo)


@dataclass(frozen=True, slots=True)
class Prediction:
    model: str
    fold: int
    horizon_steps: int
    training_start: date
    training_end: date
    training_size: int
    target_period_start: date
    target_period_end: date
    predicted: Decimal
    actual: Decimal
    error: Decimal  # actual - predicted


def _baseline(train: list[Decimal]) -> Decimal:
    return train[-1]


def _linear_trend(train: list[Decimal], steps_ahead: int) -> Decimal:
    """OLS on the time index, centred on the training mean (fitted on training only)."""
    m = len(train)
    if m < 2:
        return train[-1]
    x_mean = Decimal(m - 1) / 2
    y_mean = sum(train, Decimal(0)) / m
    xs = [Decimal(i) - x_mean for i in range(m)]
    sxx = sum((x * x for x in xs), Decimal(0))
    sxy = sum((x * (y - y_mean) for x, y in zip(xs, train, strict=True)), Decimal(0))
    slope = sxy / sxx
    return y_mean + slope * (Decimal(m - 1 + steps_ahead) - x_mean)


def _seasonal_naive(train: list[Decimal], steps_ahead: int, season: int) -> Decimal:
    """Repeat the value from the same season of the last complete year in the training data."""
    k = (steps_ahead - 1) // season + 1
    return train[len(train) - season * k + steps_ahead - 1]


def evaluate(points: list[Point], policy: Policy, season: int | None = None) -> list[Prediction]:
    """Rolling-origin evaluation over the final ``policy.test_size`` periods.

    ``season`` (12 for monthly, 4 for quarterly data) adds the seasonal-naive
    candidate when every training window holds at least two complete seasons.
    Callers must pass an eligible series (see ``check_eligibility``)."""
    if len(points) < policy.minimum_length or any(p.value is None for p in points):
        raise ValueError("series is not eligible for evaluation")
    out: list[Prediction] = []
    first_target = len(points) - policy.test_size
    h = policy.horizon
    for fold, t in enumerate(range(first_target, len(points)), start=1):
        train_points = points[: t - h + 1]
        train = [p.value for p in train_points]  # type: ignore[misc]
        target = points[t]
        actual = target.value
        assert actual is not None
        candidates = [(BASELINE, _baseline(train)), (CANDIDATE, _linear_trend(train, h))]
        if season and len(train) >= 2 * season:
            candidates.append((SEASONAL, _seasonal_naive(train, h, season)))
        for model, predicted in candidates:
            with localcontext() as ctx:
                ctx.prec = 100  # exact difference, so the stored error equals actual - predicted
                error = actual - predicted
            out.append(
                Prediction(
                    model,
                    fold,
                    h,
                    train_points[0].period_start,
                    train_points[-1].period_end,
                    len(train_points),
                    target.period_start,
                    target.period_end,
                    predicted,
                    actual,
                    error,
                )
            )
    return out


@dataclass(frozen=True, slots=True)
class Metrics:
    model: str
    n: int
    mae: Decimal
    rmse: Decimal


def metrics(predictions: list[Prediction]) -> dict[str, Metrics]:
    """MAE and RMSE per model, in the indicator's unit. Not an accuracy percentage."""
    by_model: dict[str, list[Decimal]] = {}
    for p in predictions:
        by_model.setdefault(p.model, []).append(p.error)
    out = {}
    for model, errors in by_model.items():
        n = len(errors)
        mae = sum((abs(e) for e in errors), Decimal(0)) / n
        rmse = (sum((e * e for e in errors), Decimal(0)) / n).sqrt()
        out[model] = Metrics(model, n, mae, rmse)
    return out


def same_dates(predictions: list[Prediction]) -> bool:
    dates = {
        m: [p.target_period_start for p in predictions if p.model == m]
        for m in (BASELINE, CANDIDATE)
    }
    return dates[BASELINE] == dates[CANDIDATE]


# --------------------------------------------------------------------------- selection


def select_model(m: dict[str, Metrics]) -> str:
    """The baseline unless a candidate has a strictly lower MAE on the same held-out dates
    (booklet 2.4: a simpler baseline remains acceptable if the candidate does not improve it)."""
    best = BASELINE
    for model, metric in m.items():
        if model != BASELINE and metric.mae < m[best].mae:
            best = model
    return best


def horizon_for(frequency: Frequency, n: int, policy: Policy) -> int:
    """Steps ahead: at most the held-out size, a quarter of the history, and one year."""
    cap = {Frequency.ANNUAL: 3, Frequency.QUARTERLY: 4, Frequency.MONTHLY: 12}[frequency]
    return max(1, min(cap, policy.test_size, n // 4))


# --------------------------------------------------------------------------- future estimates

# Two-sided critical values. Student t for the regression interval (df 1-30, then normal).
Z = {80: Decimal("1.2816"), 95: Decimal("1.9600")}
T80 = [
    3.078,
    1.886,
    1.638,
    1.533,
    1.476,
    1.440,
    1.415,
    1.397,
    1.383,
    1.372,
    1.363,
    1.356,
    1.350,
    1.345,
    1.341,
    1.337,
    1.333,
    1.330,
    1.328,
    1.325,
    1.323,
    1.321,
    1.319,
    1.318,
    1.316,
    1.315,
    1.314,
    1.313,
    1.311,
    1.310,
]
T95 = [
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
]


def t_value(level: int, df: int) -> Decimal:
    table = T80 if level == 80 else T95
    return Decimal(str(table[df - 1])) if 1 <= df <= len(table) else Z[level]


INTERVAL_METHODS = {
    BASELINE: {
        "code": "random_walk_normal",
        "en": "Naive (random-walk) interval: estimate ± z × σ × √h, where σ is the standard deviation of the period-to-period changes in the history. Assumes independent, normally distributed changes.",
        "ar": "فترة النموذج الساذج (المسار العشوائي): التقدير ± z × σ × √h، حيث σ الانحراف المعياري للتغيرات بين الفترات في السلسلة. يفترض تغيرات مستقلة وموزعة توزيعاً طبيعياً.",
    },
    SEASONAL: {
        "code": "seasonal_naive_normal",
        "en": "Seasonal-naive interval: estimate ± z × σ × √(k + 1), where σ is the standard deviation of year-on-year changes for the same season and k counts completed years ahead. Assumes independent, normally distributed changes.",
        "ar": "فترة النموذج الموسمي الساذج: التقدير ± z × σ × √(k + 1)، حيث σ الانحراف المعياري للتغيرات السنوية للموسم نفسه وk عدد السنوات الكاملة للأمام. يفترض تغيرات مستقلة وموزعة طبيعياً.",
    },
    CANDIDATE: {
        "code": "ols_prediction_interval",
        "en": "Least-squares prediction interval: estimate ± t × s × √(1 + 1/n + (x − x̄)² / Sxx), with Student t on n − 2 degrees of freedom. Assumes a straight-line trend with independent, normally distributed residuals of constant spread.",
        "ar": "فترة تنبؤ المربعات الصغرى: التقدير ± t × s × √(1 + 1/n + (x − x̄)² / Sxx) مع توزيع t بدرجات حرية n − 2. يفترض اتجاهاً خطياً وبواقي مستقلة موزعة طبيعياً بتشتت ثابت.",
    },
}


@dataclass(frozen=True, slots=True)
class Estimate:
    step: int
    period_start: date
    period_end: date
    estimate: Decimal
    lower80: Decimal | None
    upper80: Decimal | None
    lower95: Decimal | None
    upper95: Decimal | None


def _sd(values: list[Decimal]) -> Decimal | None:
    """Sample standard deviation, or None when it cannot support an interval.

    Zero variation (for example a perfectly regular synthetic series) would give a
    zero-width interval that claims certainty; no interval is given instead.
    """
    if len(values) < 2:
        return None
    mean = sum(values, Decimal(0)) / len(values)
    var = sum(((v - mean) ** 2 for v in values), Decimal(0)) / (len(values) - 1)
    return var.sqrt() if var > 0 else None


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def next_periods(last: Point, frequency: Frequency, horizon: int) -> list[tuple[date, date]]:
    step = {Frequency.ANNUAL: 12, Frequency.QUARTERLY: 3, Frequency.MONTHLY: 1}[frequency]
    out = []
    for h in range(1, horizon + 1):
        start = _add_months(last.period_start, step * h)
        out.append((start, _add_months(start, step) - timedelta(days=1)))
    return out


def forecast_future(
    points: list[Point], frequency: Frequency, model: str, horizon: int
) -> list[Estimate]:
    """Fit the chosen model on the whole eligible history and estimate ``horizon`` periods ahead."""
    y = [p.value for p in points]
    if any(v is None for v in y) or len(y) < 3:
        raise ValueError("series is not eligible for forecasting")
    values: list[Decimal] = y  # type: ignore[assignment]
    n = len(values)
    season = SEASON_LENGTH.get(frequency)
    periods = next_periods(points[-1], frequency, horizon)
    out: list[Estimate] = []
    if model == CANDIDATE:
        x_mean = Decimal(n - 1) / 2
        y_mean = sum(values, Decimal(0)) / n
        xs = [Decimal(i) - x_mean for i in range(n)]
        sxx = sum((x * x for x in xs), Decimal(0))
        slope = sum((x * (v - y_mean) for x, v in zip(xs, values, strict=True)), Decimal(0)) / sxx
        residuals = [v - (y_mean + slope * x) for x, v in zip(xs, values, strict=True)]
        sse = sum((r * r for r in residuals), Decimal(0))
        s = (
            (sse / (n - 2)).sqrt() if n > 2 and sse > 0 else None
        )  # see _sd: no zero-width intervals
    for h, (start, end) in enumerate(periods, start=1):
        if model == BASELINE:
            est = values[-1]
            sd = _sd([b - a for a, b in zip(values, values[1:], strict=False)])
            spread = (
                {lv: Z[lv] * sd * Decimal(h).sqrt() for lv in (80, 95)} if sd is not None else None
            )
        elif model == SEASONAL and season:
            est = _seasonal_naive(values, h, season)
            sd = _sd([values[i] - values[i - season] for i in range(season, n)])
            k = (h - 1) // season
            spread = (
                {lv: Z[lv] * sd * Decimal(k + 1).sqrt() for lv in (80, 95)}
                if sd is not None
                else None
            )
        elif model == CANDIDATE:
            x0 = Decimal(n - 1 + h) - x_mean
            est = y_mean + slope * x0
            if s is None:
                spread = None
            else:
                factor = (Decimal(1) + Decimal(1) / n + x0 * x0 / sxx).sqrt()
                spread = {lv: t_value(lv, n - 2) * s * factor for lv in (80, 95)}
        else:
            raise ValueError(f"unknown model {model}")
        out.append(
            Estimate(
                h,
                start,
                end,
                est,
                est - spread[80] if spread else None,
                est + spread[80] if spread else None,
                est - spread[95] if spread else None,
                est + spread[95] if spread else None,
            )
        )
    return out
