"""Audit events (booklet 3.11, 3.15): actor, action, entity, time and safe metadata.

``record`` adds the event to the caller's transaction, so it commits or rolls
back with the action it describes. ``record_separately`` commits on its own
connection; it is used for denied or failed actions whose own transaction is
rolled back, so the attempt is still recorded.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.session import session_factory
from app.models import AuditEvent
from app.services.principal import Principal

# Keys that must never reach the audit log, whatever a caller passes.
_FORBIDDEN_KEYS = {"password", "token", "csrf_token", "session", "cookie", "password_hash"}


def _safe(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (metadata or {}).items() if k.lower() not in _FORBIDDEN_KEYS}


def record(
    session: Session,
    actor: Principal,
    action: str,
    outcome: str = "success",
    *,
    entity_type: str | None = None,
    entity_id: object | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor.user_id,
            actor_label=actor.label,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            outcome=outcome,
            metadata_=_safe(metadata),
        )
    )


def record_separately(actor: Principal, action: str, outcome: str, **kwargs: Any) -> None:
    with session_factory()() as session, session.begin():
        record(session, actor, action, outcome, **kwargs)
