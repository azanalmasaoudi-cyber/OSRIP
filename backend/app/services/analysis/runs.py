"""Analysis runs, review cards and analyst review history (booklet 3.11, 3.13).

A run evaluates the rules over the published snapshot of one data mode and
records its input versions, rule version and parameters. Cards are immutable;
reviews are appended (database trigger) and a card's status is its latest review.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import not_found, unprocessable
from app.domain.calculations import StockAssumption
from app.domain.enums import DataMode, Section
from app.models import AnalysisRun, AnalysisRunInput, AppUser, Recommendation, RecommendationReview
from app.services import audit
from app.services.analysis.rules import RULES_VERSION, RuleParameters, evaluate
from app.services.analysis.sections import AnalysisFilter, analyse
from app.services.principal import Principal

REVIEW_STATUSES = ("under_review", "explained", "dismissed")
METHOD_CODE = "RULES_R01_R04"


def _version_ids(calcs: list[dict[str, Any]]) -> set[uuid.UUID]:
    return {uuid.UUID(i["dataset_version"]["id"]) for c in calcs for i in c["inputs"]}


def run_rules(
    session: Session, actor: Principal, data_mode: DataMode, params: RuleParameters
) -> AnalysisRun:
    with session.begin():
        f = AnalysisFilter(data_mode=data_mode, stock_assumption=StockAssumption.ASSUMED_ZERO)
        calcs = [c for section in Section for c in analyse(session, section, f)]
        versions = _version_ids(calcs)
        cards = evaluate(calcs, params)
        now = datetime.now(UTC)
        run = AnalysisRun(
            data_mode=data_mode,
            kind="rule",
            method_code=METHOD_CODE,
            method_version=RULES_VERSION,
            parameters={**params.as_dict(), "stock_assumption": f.stock_assumption.value},
            status="succeeded" if versions else "withheld",
            status_reason=None if versions else "No published observations in this data mode.",
            requested_by=actor.user_id,
            finished_at=now,
        )
        session.add(run)
        session.flush()
        session.add_all(
            AnalysisRunInput(analysis_run_id=run.id, dataset_version_id=v, data_mode=data_mode)
            for v in versions
        )
        session.add_all(
            Recommendation(
                analysis_run_id=run.id,
                data_mode=data_mode,
                rule_code=card.rule_code,
                evidence={**card.evidence, "section": card.section},
                message_en=card.observation["en"],
                message_ar=card.observation["ar"],
                follow_up_en=card.next_steps["en"],
                follow_up_ar=card.next_steps["ar"],
            )
            for card in cards
        )
        session.flush()
        audit.record(
            session,
            actor,
            "analysis.run",
            entity_type="analysis_run",
            entity_id=run.id,
            metadata={
                "data_mode": data_mode.value,
                "cards": len(cards),
                "input_versions": sorted(str(v) for v in versions),
            },
        )
        return run


def _latest_run(session: Session, data_mode: DataMode) -> AnalysisRun | None:
    return session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.data_mode == data_mode, AnalysisRun.method_code == METHOD_CODE)
        .order_by(AnalysisRun.started_at.desc(), AnalysisRun.id.desc())
        .limit(1)
    )


def card_out(
    rec: Recommendation, run: AnalysisRun, latest: RecommendationReview | None, review_count: int
) -> dict[str, Any]:
    return {
        "id": str(rec.id),
        "rule_code": rec.rule_code,
        "section": rec.evidence.get("section"),
        "data_mode": rec.data_mode.value,
        "observation": {"en": rec.message_en, "ar": rec.message_ar},
        "next_steps": {"en": rec.follow_up_en, "ar": rec.follow_up_ar},
        "evidence": rec.evidence,
        "status": latest.status if latest else "open",
        "review_count": review_count,
        "run": {
            "id": str(run.id),
            "method_version": run.method_version,
            "parameters": run.parameters,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "created_at": rec.created_at.isoformat(),
    }


def latest_cards(
    session: Session, data_mode: DataMode, section: Section | None = None
) -> dict[str, Any]:
    run = _latest_run(session, data_mode)
    if run is None:
        return {"run": None, "cards": []}
    recs = session.scalars(
        select(Recommendation)
        .where(Recommendation.analysis_run_id == run.id)
        .order_by(Recommendation.rule_code, Recommendation.created_at)
    ).all()
    cards = []
    for rec in recs:
        if section and rec.evidence.get("section") != section.value:
            continue
        latest = session.scalar(
            select(RecommendationReview)
            .where(RecommendationReview.recommendation_id == rec.id)
            .order_by(RecommendationReview.id.desc())
            .limit(1)
        )
        count = (
            session.scalar(
                select(func.count())
                .select_from(RecommendationReview)
                .where(RecommendationReview.recommendation_id == rec.id)
            )
            or 0
        )
        cards.append(card_out(rec, run, latest, count))
    return {
        "run": {
            "id": str(run.id),
            "status": run.status,
            "status_reason": run.status_reason,
            "method_version": run.method_version,
            "parameters": run.parameters,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "cards": cards,
    }


def add_review(
    session: Session, actor: Principal, recommendation_id: uuid.UUID, status: str, reason: str
) -> None:
    if status not in REVIEW_STATUSES:
        raise unprocessable(
            "invalid_review_status", "Status must be under_review, explained or dismissed."
        )
    if not reason.strip():
        raise unprocessable("reason_required", "Give a reason for this review.")
    with session.begin():
        rec = session.get(Recommendation, recommendation_id)
        if rec is None:
            raise not_found("recommendation")
        session.add(
            RecommendationReview(
                recommendation_id=rec.id,
                reviewer_id=actor.user_id,
                status=status,
                reason=reason.strip(),
            )
        )
        audit.record(
            session,
            actor,
            "recommendation.review",
            entity_type="recommendation",
            entity_id=rec.id,
            metadata={"status": status},
        )


def review_history(session: Session, recommendation_id: uuid.UUID) -> list[dict[str, Any]]:
    if session.get(Recommendation, recommendation_id) is None:
        raise not_found("recommendation")
    rows = session.execute(
        select(RecommendationReview, AppUser.display_name)
        .join(AppUser, AppUser.id == RecommendationReview.reviewer_id)
        .where(RecommendationReview.recommendation_id == recommendation_id)
        .order_by(RecommendationReview.id)
    ).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "reason": r.reason,
            "reviewer": name,
            "created_at": r.created_at.isoformat(),
        }
        for r, name in rows
    ]
