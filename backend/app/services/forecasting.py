"""Forecast eligibility over published series, and recorded forecast experiments.

* Eligibility is evaluated for every published series of one data mode (one
  dataset version, indicator, area, unit, frequency, commodity, partner, flow).
  Series are never summed or combined to manufacture a longer history.
* A run first records the experiment definition (``analysis_run.parameters``),
  then its predictions in the same transaction. An ineligible series is recorded
  as a withheld run with its reasons (booklet T10) and produces no predictions.
* Metrics are recomputed from the stored predictions, so an examiner can
  reproduce them from the individual errors.
* Synthetic runs are software demonstrations only, never forecasts for Oman.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found, unprocessable
from app.domain import forecasting as fc
from app.domain.enums import DataMode, Frequency
from app.models import AnalysisRun, AnalysisRunInput, ForecastOutput, ForecastPrediction
from app.services import audit
from app.services.exports import mode_label
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.observations import ObservationQuery, SeriesOut, query_observations
from app.services.principal import Principal

DEMONSTRATION_LABEL = {
    "en": "Software demonstration on synthetic data. Not a validated forecast for Oman.",
    "ar": "عرض لسلوك البرنامج على بيانات اصطناعية. ليس تنبؤاً موثقاً لعُمان.",
}


def _series_id(s: SeriesOut) -> str:
    return ":".join("-" if part is None else str(part) for part in s.key)


def _points(s: SeriesOut) -> list[fc.Point]:
    return [
        fc.Point(
            date.fromisoformat(o["period_start"]),
            date.fromisoformat(o["period_end"]),
            None if o["value"] is None else Decimal(o["value"]),
            o["period_complete"],
            o["quality_status"],
        )
        for o in s.observations
    ]


def _describe(s: SeriesOut) -> dict[str, Any]:
    m = s.meta
    return {
        "series_id": _series_id(s),
        "indicator": {k: m["indicator"][k] for k in ("code", "name_en", "name_ar")},
        "unit": m["unit"],
        "frequency": m["frequency"],
        "area": m["area"],
        "commodity": m["commodity"]["code"] if m["commodity"] else None,
        "partner": m["partner"]["code"] if m["partner"] else None,
        "flow": m["flow"],
        "dataset_version": {
            "id": m["dataset_version"]["id"],
            "label": m["dataset_version"]["label"],
        },
        "source_title": m["source"]["dataset_title"],
    }


def _evaluated(session: Session, data_mode: DataMode) -> list[tuple[SeriesOut, fc.Eligibility]]:
    # Verified-source forecasting uses January 2022 onward only (platform scope).
    floor = STATISTICAL_SCOPE_START if data_mode is DataMode.VERIFIED_SOURCE else None
    series = query_observations(
        session, ObservationQuery(data_mode, period_from=floor), allow_mixed=True
    )
    # Only regular periods form a time series: dated statements and year-to-date totals
    # (overlapping cumulative figures) are never treated as independent observations.
    return [
        (s, fc.check_eligibility(_points(s), Frequency(s.meta["frequency"]), data_mode))
        for s in series
        if s.meta.get("period_kind") in ("annual", "quarterly", "monthly")
    ]


def _policies() -> dict[str, Any]:
    return {
        f.value: {"min_training": p.min_training, "test_size": p.test_size, "horizon": p.horizon}
        for f, p in fc.POLICIES.items()
    }


def eligibility(session: Session, data_mode: DataMode) -> dict[str, Any]:
    evaluated = _evaluated(session, data_mode)
    rows = []
    for s, e in evaluated:
        first, last = (e.points[0], e.points[-1]) if e.points else (None, None)
        rows.append(
            {
                **_describe(s),
                "usable_observations": len(e.points),
                "first_period": first.period_start.isoformat() if first else None,
                "last_period": last.period_end.isoformat() if last else None,
                "eligible": e.eligible,
                "reasons": [r.as_dict() for r in e.reasons],
                "notes": [n.as_dict() for n in e.notes],
            }
        )
    eligible = [r for r in rows if r["eligible"]]
    if not rows:
        summary = {
            "code": "no_published_series",
            "en": "No series is published in this data mode, so there is nothing to evaluate.",
            "ar": "لا توجد سلاسل منشورة في وضع البيانات هذا، فلا يوجد ما يُقيَّم.",
        }
    elif not eligible:
        summary = {
            "code": "no_eligible_series",
            "en": f"None of the {len(rows)} published series meets the history and quality "
            "requirements, so no forecast is produced.",
            "ar": f"لا تستوفي أي من السلاسل المنشورة ({len(rows)}) متطلبات الطول والجودة، "
            "لذا لا يُنتَج أي تنبؤ.",
        }
    else:
        summary = None
    return {
        "data_mode": data_mode.value,
        "label": mode_label(data_mode),
        "status": "available" if eligible else "unavailable",
        "summary": summary,
        "demonstration_only": data_mode is DataMode.SYNTHETIC,
        "demonstration_label": DEMONSTRATION_LABEL if data_mode is DataMode.SYNTHETIC else None,
        "method": _method(),
        "series": rows,
    }


def _method() -> dict[str, Any]:
    return {
        "code": fc.METHOD_CODE,
        "version": fc.METHOD_VERSION,
        "policies": _policies(),
        "baseline": {
            "code": fc.BASELINE,
            "en": "Repeats the most recent observation of the training window.",
            "ar": "يكرر آخر مشاهدة في نافذة التدريب.",
        },
        "candidate": {
            "code": fc.CANDIDATE,
            "en": "Least-squares linear trend on the time index, fitted on the training window "
            "only (the index is centred on the training mean).",
            "ar": "اتجاه خطي بطريقة المربعات الصغرى على مؤشر الزمن، يُقدَّر من نافذة التدريب فقط "
            "(مع توسيط المؤشر على متوسط التدريب).",
        },
        "splits": {
            "en": "Rolling origin: for each of the final held-out periods, both models are fitted "
            "on every earlier observation and forecast that period one step ahead.",
            "ar": "أصل متدحرج: لكل فترة من فترات الاختبار الأخيرة يُقدَّر النموذجان من جميع "
            "المشاهدات السابقة ويتنبآن بتلك الفترة بخطوة واحدة.",
        },
        "interval": {
            "code": "per_model",
            "en": "Backtest predictions are point estimates. Future estimates carry 80% and 95% prediction intervals from the selected method (naive, seasonal naive or least-squares formula); each forecast states its method and assumptions.",
            "ar": "تنبؤات الاختبار الرجعي تقديرات نقطية. تحمل التقديرات المستقبلية فترات تنبؤ 80% و95% وفق الطريقة المختارة (الساذجة أو الموسمية الساذجة أو صيغة المربعات الصغرى)؛ ويذكر كل تنبؤ طريقته وافتراضاته.",
        },
        "metrics": {
            "en": "MAE is the mean absolute error and RMSE the root mean squared error, both in "
            "the indicator's unit. RMSE weighs large errors more. Neither is an accuracy "
            "percentage, and a few held-out periods cannot show stability.",
            "ar": "متوسط الخطأ المطلق (MAE) وجذر متوسط مربع الخطأ (RMSE) بوحدة المؤشر نفسها. "
            "يعطي RMSE وزناً أكبر للأخطاء الكبيرة. لا يمثل أي منهما نسبة دقة، وقلة فترات "
            "الاختبار لا تُظهر الاستقرار.",
        },
    }


def run_experiment(
    session: Session, actor: Principal, data_mode: DataMode, series_id: str
) -> uuid.UUID:
    with session.begin():
        match = next(
            (x for x in _evaluated(session, data_mode) if _series_id(x[0]) == series_id), None
        )
        if match is None:
            raise unprocessable("unknown_series", "That series is not published in this data mode.")
        s, e = match
        frequency = Frequency(s.meta["frequency"])
        policy = fc.POLICIES[frequency]
        # The definition is fixed from the series and the policy, before any fitting.
        definition = {
            "series": _describe(s),
            "target": {
                "indicator": s.meta["indicator"]["code"],
                "unit": s.meta["unit"]["code"],
                "frequency": frequency.value,
            },
            "horizon_steps": policy.horizon,
            "min_training": policy.min_training,
            "test_size": policy.test_size,
            "splits": "rolling_origin_expanding_window",
            "baseline": fc.BASELINE,
            "candidate": fc.CANDIDATE,
            "candidates": [fc.BASELINE, fc.CANDIDATE]
            + ([fc.SEASONAL] if fc.SEASON_LENGTH.get(frequency) else []),
            "selection_rule": "lowest MAE on the same held-out dates; the baseline unless a "
            "candidate is strictly better",
            "interval_method": fc.INTERVAL_METHOD["code"],
            "missing_values": "not_imputed",
            "demonstration_only": e.demonstration_only,
            "eligibility": {
                "eligible": e.eligible,
                "reasons": [r.as_dict() for r in e.reasons],
                "notes": [n.as_dict() for n in e.notes],
            },
        }
        if e.eligible:
            held_out = e.points[-policy.test_size :]
            definition["held_out_periods"] = [p.period_start.isoformat() for p in held_out]
            definition["history"] = {
                "first_period": e.points[0].period_start.isoformat(),
                "training_cutoff": e.points[-1].period_end.isoformat(),
                "observations": len(e.points),
            }
            definition["future_horizon_steps"] = fc.horizon_for(frequency, len(e.points), policy)
        run = AnalysisRun(
            data_mode=data_mode,
            kind="forecast",
            method_code=fc.METHOD_CODE,
            method_version=fc.METHOD_VERSION,
            parameters=definition,
            status="succeeded" if e.eligible else "withheld",
            status_reason=None if e.eligible else " ".join(r.en for r in e.reasons),
            requested_by=actor.user_id,
        )
        session.add(run)
        session.flush()
        session.add(
            AnalysisRunInput(
                analysis_run_id=run.id,
                dataset_version_id=uuid.UUID(s.meta["dataset_version"]["id"]),
                data_mode=data_mode,
            )
        )
        season = fc.SEASON_LENGTH.get(frequency)
        predictions = fc.evaluate(e.points, policy, season) if e.eligible else []
        session.add_all(
            ForecastPrediction(
                analysis_run_id=run.id,
                data_mode=data_mode,
                model=p.model,
                fold=p.fold,
                horizon_steps=p.horizon_steps,
                training_start=p.training_start,
                training_end=p.training_end,
                training_size=p.training_size,
                target_period_start=p.target_period_start,
                target_period_end=p.target_period_end,
                predicted=p.predicted,
                actual=p.actual,
                error=p.error,
            )
            for p in predictions
        )
        if predictions:
            chosen = fc.select_model(fc.metrics(predictions))
            horizon = definition["future_horizon_steps"]
            estimates = fc.forecast_future(e.points, frequency, chosen, horizon)
            # A new dict (not an in-place change) so the update is detected and written.
            run.parameters = {**definition, "selected_model": chosen}
            session.add_all(
                ForecastOutput(
                    analysis_run_id=run.id,
                    data_mode=data_mode,
                    model=chosen,
                    step=est.step,
                    period_start=est.period_start,
                    period_end=est.period_end,
                    estimate=est.estimate,
                    lower80=est.lower80,
                    upper80=est.upper80,
                    lower95=est.lower95,
                    upper95=est.upper95,
                    interval_method=fc.INTERVAL_METHODS[chosen]["code"],
                )
                for est in estimates
            )
        run.finished_at = datetime.now(UTC)
        session.flush()
        audit.record(
            session,
            actor,
            "forecast.run",
            entity_type="analysis_run",
            entity_id=run.id,
            metadata={
                "data_mode": data_mode.value,
                "series_id": series_id,
                "status": run.status,
                "predictions": len(predictions),
            },
        )
        return run.id


def _run_summary(run: AnalysisRun) -> dict[str, Any]:
    p = run.parameters
    return {
        "id": str(run.id),
        "data_mode": run.data_mode.value,
        "status": run.status,
        "status_reason": run.status_reason,
        "method_code": run.method_code,
        "method_version": run.method_version,
        "series": p.get("series"),
        "demonstration_only": bool(p.get("demonstration_only")),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def list_runs(session: Session, data_mode: DataMode, limit: int = 20) -> list[dict[str, Any]]:
    runs = session.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.data_mode == data_mode, AnalysisRun.kind == "forecast")
        .order_by(AnalysisRun.started_at.desc(), AnalysisRun.id.desc())
        .limit(limit)
    )
    return [_run_summary(r) for r in runs]


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def run_detail(session: Session, run_id: uuid.UUID) -> dict[str, Any]:
    run = session.get(AnalysisRun, run_id)
    if run is None or run.kind != "forecast":
        raise not_found("forecast run")
    rows = session.scalars(
        select(ForecastPrediction)
        .where(ForecastPrediction.analysis_run_id == run.id)
        .order_by(ForecastPrediction.target_period_start, ForecastPrediction.model)
    ).all()
    predictions = [
        fc.Prediction(
            r.model,
            r.fold,
            r.horizon_steps,
            r.training_start,
            r.training_end,
            r.training_size,
            r.target_period_start,
            r.target_period_end,
            r.predicted,
            r.actual,
            r.error,
        )
        for r in rows
    ]
    m = fc.metrics(predictions) if predictions else {}
    base, cand = m.get(fc.BASELINE), m.get(fc.CANDIDATE)
    comparison = None
    if base and cand:
        improves = cand.mae < base.mae
        comparison = {
            "same_dates": fc.same_dates(predictions),
            "n": base.n,
            "candidate_improves_mae": improves,
            "en": (
                f"On the same {base.n} held-out periods the candidate's MAE is "
                + ("lower than" if improves else "not lower than")
                + " the baseline's. "
                + (
                    ""
                    if improves
                    else "The simpler baseline remains the preferred choice for this series. "
                )
                + "A few periods cannot show that either model will keep this ranking."
            ),
            "ar": (
                f"على فترات الاختبار نفسها ({base.n}) متوسط الخطأ المطلق للنموذج المرشح "
                + ("أقل من" if improves else "ليس أقل من")
                + " خط الأساس. "
                + ("" if improves else "يبقى خط الأساس الأبسط الخيار المفضل لهذه السلسلة. ")
                + "لا تُثبت فترات قليلة أن أياً من النموذجين سيحافظ على هذا الترتيب."
            ),
        }
    return {
        **_run_summary(run),
        "label": mode_label(run.data_mode),
        "demonstration_label": DEMONSTRATION_LABEL
        if bool(run.parameters.get("demonstration_only"))
        else None,
        "definition": run.parameters,
        "method": _method(),
        "predictions": [
            {
                "model": r.model,
                "fold": r.fold,
                "horizon_steps": r.horizon_steps,
                "training_start": r.training_start.isoformat(),
                "training_end": r.training_end.isoformat(),
                "training_size": r.training_size,
                "target_period_start": r.target_period_start.isoformat(),
                "target_period_end": r.target_period_end.isoformat(),
                "predicted": _decimal(r.predicted),
                "actual": _decimal(r.actual),
                "error": _decimal(r.error),
                "interval_lower": _decimal(r.interval_lower),
                "interval_upper": _decimal(r.interval_upper),
            }
            for r in rows
        ],
        "metrics": {
            k: {"n": v.n, "mae": _decimal(v.mae), "rmse": _decimal(v.rmse)} for k, v in m.items()
        },
        "comparison": comparison,
        **_future(session, run, m),
    }


MODEL_NAMES = {
    fc.BASELINE: {"en": "last-value baseline", "ar": "خط أساس القيمة الأخيرة"},
    fc.CANDIDATE: {"en": "linear trend", "ar": "الاتجاه الخطي"},
    fc.SEASONAL: {"en": "seasonal naive", "ar": "النموذج الموسمي الساذج"},
}

ASSUMPTIONS = {
    "en": [
        "The estimate continues the pattern of the published history; it cannot anticipate events, policy changes or data revisions.",
        "Prediction intervals hold only if the method's statistical assumptions hold; they are not guarantees.",
        "Errors were measured on a few held-out periods, which cannot prove future accuracy.",
        "Model estimates are not official statistics and do not predict crises or disruptions.",
    ],
    "ar": [
        "يستمر التقدير على نمط السلسلة المنشورة؛ ولا يمكنه توقع الأحداث أو تغيّر السياسات أو تعديل البيانات.",
        "لا تصح فترات التنبؤ إلا إذا تحققت افتراضات الطريقة الإحصائية؛ وهي ليست ضمانات.",
        "قيست الأخطاء على فترات اختبار قليلة لا تثبت الدقة المستقبلية.",
        "تقديرات النموذج ليست إحصاءات رسمية ولا تتنبأ بالأزمات أو الاضطرابات.",
    ],
}


def _history(session: Session, run: AnalysisRun) -> list[dict[str, Any]]:
    series = run.parameters.get("series") or {}
    wanted = series.get("series_id")
    if not wanted:
        return []
    for s in query_observations(
        session,
        ObservationQuery(
            run.data_mode, dataset_version_id=uuid.UUID(series["dataset_version"]["id"])
        ),
        allow_mixed=True,
    ):
        if _series_id(s) == wanted:
            first = (run.parameters.get("history") or {}).get("first_period")
            return [
                {
                    "period_start": o["period_start"],
                    "period_end": o["period_end"],
                    "value": o["value"],
                }
                for o in s.observations
                if not first or o["period_start"] >= first
            ]
    return []


def _future(session: Session, run: AnalysisRun, m: dict[str, fc.Metrics]) -> dict[str, Any]:
    rows = session.scalars(
        select(ForecastOutput)
        .where(ForecastOutput.analysis_run_id == run.id)
        .order_by(ForecastOutput.step)
    ).all()
    chosen = run.parameters.get("selected_model")
    outputs = [
        {
            "step": r.step,
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
            "estimate": _decimal(r.estimate),
            "lower80": _decimal(r.lower80),
            "upper80": _decimal(r.upper80),
            "lower95": _decimal(r.lower95),
            "upper95": _decimal(r.upper95),
        }
        for r in rows
    ]
    explanation = None
    if chosen and rows and chosen in m and fc.BASELINE in m:
        unit = (run.parameters.get("series") or {}).get("unit") or {}
        first = rows[0]
        n = m[chosen].n
        cutoff = (run.parameters.get("history") or {}).get("training_cutoff", "")
        interval_en = (
            f" If the method's assumptions hold, 80% of such outcomes would fall between {_decimal(first.lower80)} and {_decimal(first.upper80)}."
            if first.lower80 is not None
            else " No interval is given: the history has no variation to estimate uncertainty from, which does not make the estimate certain."
        )
        interval_ar = (
            f" إذا تحققت افتراضات الطريقة فإن 80% من هذه النتائج تقع بين {_decimal(first.lower80)} و{_decimal(first.upper80)}."
            if first.lower80 is not None
            else " لا تُعطى فترة: لا يوجد تباين في البيانات التاريخية لتقدير عدم اليقين، وهذا لا يجعل التقدير مؤكداً."
        )
        better_en = (
            f"The {MODEL_NAMES[chosen]['en']} had a lower average error (MAE {_decimal(m[chosen].mae)}) than the baseline (MAE {_decimal(m[fc.BASELINE].mae)}), so it is used."
            if chosen != fc.BASELINE
            else f"No candidate beat the simple baseline (MAE {_decimal(m[fc.BASELINE].mae)}), so the baseline is used."
        )
        better_ar = (
            f"كان متوسط خطأ {MODEL_NAMES[chosen]['ar']} (MAE {_decimal(m[chosen].mae)}) أقل من خط الأساس (MAE {_decimal(m[fc.BASELINE].mae)})، لذا اعتُمد."
            if chosen != fc.BASELINE
            else f"لم يتفوق أي نموذج على خط الأساس البسيط (MAE {_decimal(m[fc.BASELINE].mae)})، لذا اعتُمد خط الأساس."
        )
        explanation = {
            "en": (
                f"OSRIP tested each method on the last {n} periods up to {cutoff}, using only earlier data each time. {better_en} "
                f"The model estimate for the period starting {first.period_start.isoformat()} is {_decimal(first.estimate)} {unit.get('label_en', '')}.{interval_en} "
                "This is a model estimate, not an official statistic."
            ),
            "ar": (
                f"اختبرت OSRIP كل طريقة على آخر {n} فترات حتى {cutoff} باستخدام البيانات السابقة فقط في كل مرة. {better_ar} "
                f"تقدير النموذج للفترة التي تبدأ في {first.period_start.isoformat()} هو {_decimal(first.estimate)} {unit.get('label_ar', '')}.{interval_ar} "
                "هذا تقدير نموذج وليس إحصاءً رسمياً."
            ),
        }
    return {
        "selected_model": chosen,
        "model_names": MODEL_NAMES,
        "outputs": outputs,
        "interval_method": fc.INTERVAL_METHODS.get(chosen) if chosen else None,
        "history": _history(session, run) if rows else [],
        "training_cutoff": (run.parameters.get("history") or {}).get("training_cutoff"),
        "explanation": explanation,
        "assumptions": ASSUMPTIONS,
        "estimate_label": {
            "en": "Model estimate — not an official observation.",
            "ar": "تقدير نموذج — ليس مشاهدة رسمية.",
        },
    }


# ------------------------------------------------------------------ overview by indicator

INSUFFICIENT_LABEL = {
    "en": "Insufficient comparable historical data for a reliable forecast.",
    "ar": "لا تتوفر بيانات تاريخية قابلة للمقارنة كافية لتوقع موثوق.",
}

TARGETS: list[dict[str, Any]] = [
    {"group": "electricity", "indicator": "ELEC_CONSUMPTION", "flow": None},
    {"group": "electricity", "indicator": "ELEC_GENERATION", "flow": None},
    {"group": "water", "indicator": "WATER_CONSUMPTION", "flow": None},
    {"group": "water", "indicator": "WATER_PRODUCTION", "flow": None},
    {"group": "food_security", "indicator": "FOOD_PRODUCTION", "flow": None},
    {"group": "trade", "indicator": "TRADE_QUANTITY", "flow": "import"},
    {"group": "trade", "indicator": "TRADE_QUANTITY", "flow": "domestic_export"},
    {"group": "trade", "indicator": "TRADE_VALUE", "flow": "import"},
    {"group": "trade", "indicator": "TRADE_VALUE", "flow": "domestic_export"},
    # Reference-pack indicators (migration 0009). Their annual history starts in 2022, and
    # year-to-date totals and statements are never used as training points.
    {"group": "electricity", "indicator": "ELEC_GROSS_GENERATION", "flow": None},
    {"group": "electricity", "indicator": "ELEC_NET_GENERATION", "flow": None},
    {"group": "food_security", "indicator": "AGRI_CROP_PRODUCTION", "flow": None},
    {"group": "food_security", "indicator": "FISH_CAPTURE_LANDINGS", "flow": None},
    {"group": "trade", "indicator": "TRADE_MERCH_EXPORTS", "flow": None},
    {"group": "trade", "indicator": "TRADE_MERCH_IMPORTS", "flow": None},
]


def overview(session: Session, data_mode: DataMode) -> dict[str, Any]:
    """Every target indicator with its published series, eligibility and latest run.

    Apparent food availability is a derived balance, not a published series; it is not
    forecast directly (its components would need compatible forecasts of their own)."""
    evaluated = _evaluated(session, data_mode)
    runs = session.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.data_mode == data_mode,
            AnalysisRun.kind == "forecast",
            AnalysisRun.status == "succeeded",
        )
        .order_by(AnalysisRun.started_at.desc())
        .limit(500)
    ).all()
    latest_run: dict[str, str] = {}
    for r in runs:
        sid = (r.parameters.get("series") or {}).get("series_id")
        if sid and sid not in latest_run:
            latest_run[sid] = str(r.id)
    targets = []
    for t in TARGETS:
        matching = [
            (s, e)
            for s, e in evaluated
            if s.meta["indicator"]["code"] == t["indicator"]
            and (t["flow"] is None or s.meta["flow"] == t["flow"])
            and s.meta["partner"] is None
        ]
        series = [
            {
                **_describe(s),
                "usable_observations": len(e.points),
                "first_period": e.points[0].period_start.isoformat() if e.points else None,
                "last_period": e.points[-1].period_end.isoformat() if e.points else None,
                "eligible": e.eligible,
                "reasons": [r.as_dict() for r in e.reasons],
                "latest_run_id": latest_run.get(_series_id(s)),
            }
            for s, e in matching
        ]
        targets.append(
            {
                **t,
                "series": series,
                "status": "available"
                if any(x["eligible"] for x in series)
                else "insufficient_data",
            }
        )
    return {
        "data_mode": data_mode.value,
        "label": mode_label(data_mode),
        "demonstration_label": DEMONSTRATION_LABEL if data_mode is DataMode.SYNTHETIC else None,
        "targets": targets,
        "method": _method(),
        "insufficient_label": INSUFFICIENT_LABEL,
    }
