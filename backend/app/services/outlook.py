# ruff: noqa: E501 - bilingual labels are kept on one line each, as in services/studies.py
"""The official outlook for electricity and water: what official statements forecast, target,
plan or are considering, kept apart from observed statistics.

Each item keeps its evidence class (observed, estimate, forecast, policy_target, planned,
under_consideration), its source (title, publisher, address, page, file hash, retrieval date, the
year the statement was issued) and a review status. Items are staged as pending and are shown only
once a person with the import approval permission approves them; every staging and decision is
audited. The database refuses an observation or estimate dated in or after the statement's year, so
a 2032 figure can never be an observed one. Outlook items are never written into the observation
tables, the timelines or the comparisons.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.domain.enums import Section
from app.services import audit
from app.services.principal import Principal

CLASSES = ("observed", "estimate", "forecast", "policy_target", "planned", "under_consideration")
# Classes that describe the future or an intention: never presented as achieved.
NOT_ACHIEVED = frozenset({"forecast", "policy_target", "planned", "under_consideration"})
UNITS = ("MW", "percent", "m3_per_day", "thousand_m3_per_day", "event")

CLASS_LABELS: dict[str, dict[str, str]] = {
    "observed": {"en": "Observed (as stated in the outlook)", "ar": "مُسجَّل (كما ورد في البيان)"},
    "estimate": {"en": "Estimate", "ar": "تقدير"},
    "forecast": {"en": "Forecast (not observed)", "ar": "توقع (غير مُسجَّل)"},
    "policy_target": {"en": "Policy target (not achieved)", "ar": "هدف وطني (لم يتحقق بعد)"},
    "planned": {"en": "Planned (not in operation)", "ar": "مخطط (ليس قيد التشغيل)"},
    "under_consideration": {"en": "Under consideration", "ar": "قيد الدراسة"},
}
UNIT_LABELS: dict[str, dict[str, str]] = {
    "MW": {"en": "MW", "ar": "ميجاواط"},
    "percent": {"en": "%", "ar": "٪"},
    "m3_per_day": {"en": "m³/day", "ar": "م³/يوم"},
    "thousand_m3_per_day": {"en": "thousand m³/day", "ar": "ألف م³/يوم"},
    "event": {"en": "", "ar": ""},
}

# One fixed query (bound parameters only): every item, or the approved ones, or one item.
_SELECT = (
    "SELECT id, section, metric_code, metric_en, metric_ar, year, value, unit, scope_en, scope_ar, evidence_class, "
    "status_note_en, status_note_ar, source_title, source_publisher, source_url, source_locator, source_sha256, "
    "retrieved_on, issue_year, batch_label, review_status, reviewed_at, review_note FROM outlook_item "
    "WHERE (CAST(:section AS text) IS NULL OR section = CAST(:section AS section_code)) "
    "AND (NOT :approved_only OR review_status = 'approved') "
    "AND (CAST(:id AS uuid) IS NULL OR id = CAST(:id AS uuid)) "
    "ORDER BY section, metric_code, year, scope_en"
)


def check(item: dict[str, Any]) -> list[str]:
    """What is wrong with an item before it is staged (the database enforces the same rules)."""
    problems = []
    if item.get("evidence_class") not in CLASSES:
        problems.append(f"unknown evidence class {item.get('evidence_class')!r}")
    if item.get("unit") not in UNITS:
        problems.append(f"unknown unit {item.get('unit')!r}")
    if item.get("value") is None and item.get("unit") != "event":
        problems.append("no value (only an event, such as an operation year, may have none)")
    if item.get("evidence_class") in ("observed", "estimate") and int(item["year"]) >= int(
        item["issue_year"]
    ):
        problems.append(
            f"{item['year']} is not before the statement's year {item['issue_year']}: it cannot be observed"
        )
    if not str(item.get("source_url", "")).startswith("https://"):
        problems.append("the source address is not https://")
    return problems


def _out(row: Any, *, review: bool = False) -> dict[str, Any]:
    """One item. With ``review``, also the decision's date and note (reviewers only, never public)."""
    m = row._mapping
    cls = m["evidence_class"]
    item = {
        "id": str(m["id"]),
        "section": m["section"],
        "metric": {"code": m["metric_code"], "en": m["metric_en"], "ar": m["metric_ar"]},
        "year": m["year"],
        "value": None if m["value"] is None else format(Decimal(m["value"]).normalize(), "f"),
        "unit": {"code": m["unit"], **UNIT_LABELS[m["unit"]]},
        "scope": {"en": m["scope_en"], "ar": m["scope_ar"]},
        "evidence_class": cls,
        "class_label": CLASS_LABELS[cls],
        "achieved": cls not in NOT_ACHIEVED,
        "status_note": {"en": m["status_note_en"], "ar": m["status_note_ar"]} if m["status_note_en"] else None,
        "source": {
            "title": m["source_title"], "publisher": m["source_publisher"], "url": m["source_url"],
            "locator": m["source_locator"], "sha256": m["source_sha256"],
            "retrieved_on": m["retrieved_on"].isoformat(), "issue_year": m["issue_year"],
        },
        "batch": m["batch_label"],
        "review_status": m["review_status"],
    }  # fmt: skip
    if review:
        item["reviewed_at"] = m["reviewed_at"].isoformat() if m["reviewed_at"] else None
        item["review_note"] = m["review_note"]
    return item


def list_items(
    session: Session, section: Section | None = None, *, approved_only: bool = True
) -> dict[str, Any]:
    """Outlook items, by section, year and metric. The public sees approved items only."""
    rows = session.execute(
        text(_SELECT),
        {"section": section.value if section else None, "approved_only": approved_only, "id": None},
    )
    items = [_out(r, review=not approved_only) for r in rows]
    return {
        "items": items,
        "classes": [
            {"code": c, "label": CLASS_LABELS[c], "achieved": c not in NOT_ACHIEVED}
            for c in CLASSES
        ],
        "note": {
            "en": "Official statements of what is forecast, targeted, planned or considered. Not observed statistics: kept apart from the published series.",
            "ar": "بيانات رسمية لما هو متوقع أو مستهدف أو مخطط أو قيد الدراسة. ليست إحصاءات مُسجَّلة: تُعرض منفصلة عن السلاسل المنشورة.",
        },
    }


def stage(
    session: Session, actor: Principal, items: list[dict[str, Any]], batch_label: str
) -> dict[str, int]:
    """Stage items as pending review; an item already staged (same source, metric, year and scope)
    is left as it is, so staging twice changes nothing. Refused as a whole if any item is wrong."""
    problems = [f"{i.get('metric_code')} {i.get('year')}: {p}" for i in items for p in check(i)]
    if problems:
        raise ApiError(422, "outlook_invalid", "Some outlook items are not valid.", problems)
    inserted = 0
    for i in items:
        result = session.execute(
            text(
                "INSERT INTO outlook_item (section, metric_code, metric_en, metric_ar, year, value, unit, scope_en, scope_ar, "
                "evidence_class, status_note_en, status_note_ar, source_title, source_publisher, source_url, source_locator, "
                "source_sha256, retrieved_on, issue_year, batch_label, created_by) VALUES (CAST(:section AS section_code), "
                ":metric_code, :metric_en, :metric_ar, :year, :value, :unit, :scope_en, :scope_ar, CAST(:evidence_class AS outlook_class), "
                ":status_note_en, :status_note_ar, :source_title, :source_publisher, :source_url, :source_locator, :source_sha256, "
                ":retrieved_on, :issue_year, :batch_label, :created_by) "
                "ON CONFLICT ON CONSTRAINT outlook_item_once DO NOTHING"
            ),
            {**i, "batch_label": batch_label, "created_by": actor.user_id},
        )
        inserted += result.rowcount
    audit.record(session, actor, "outlook.stage", entity_type="outlook_batch", entity_id=batch_label,
                 metadata={"items": len(items), "inserted": inserted})  # fmt: skip
    return {"items": len(items), "inserted": inserted, "already_staged": len(items) - inserted}


def review(
    session: Session, actor: Principal, item_id: uuid.UUID, decision: str, note: str = ""
) -> dict[str, Any]:
    """Approve or reject a pending item (audited). A decided item is not decided again."""
    if decision not in ("approved", "rejected"):
        raise ApiError(422, "invalid_decision", "The decision is 'approved' or 'rejected'.")
    row = session.execute(
        text("SELECT review_status FROM outlook_item WHERE id = :id FOR UPDATE"), {"id": item_id}
    ).first()
    if row is None:
        raise not_found("outlook item")
    if row[0] != "pending":
        raise ApiError(409, "already_reviewed", "This outlook item has already been reviewed.")
    session.execute(
        text(
            "UPDATE outlook_item SET review_status = CAST(:d AS outlook_review), reviewed_by = :by, reviewed_at = now(), "
            "review_note = :note WHERE id = :id"
        ),
        {"d": decision, "by": actor.user_id, "note": note[:500] or None, "id": item_id},
    )
    audit.record(session, actor, f"outlook.{decision}", entity_type="outlook_item", entity_id=item_id,
                 metadata={"note": note[:200]})  # fmt: skip
    updated = session.execute(
        text(_SELECT), {"section": None, "approved_only": False, "id": str(item_id)}
    ).first()
    return _out(updated, review=True)
