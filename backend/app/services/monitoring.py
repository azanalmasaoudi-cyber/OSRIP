"""Built-in error monitoring and service health (no third-party account needed).

* Unhandled server exceptions and browser errors are stored in ``app_error`` with
  a fingerprint for grouping. Stored: error type, a truncated message, the path
  without its query string, a request id and the release. Never stored: request
  bodies, cookies, headers, query strings or user identifiers.
* External services (model API, OpenID providers, SMTP) report their latest
  failure here, in memory, so the health page can show degraded integrations
  without calling them on every health check.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import session_factory
from app.models import AppError

logger = logging.getLogger("osrip.monitoring")
RELEASE = "0.8.0"

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_TOKENISH = re.compile(r"[A-Za-z0-9_\-]{24,}")
_lock = threading.Lock()
_external: dict[str, dict[str, Any]] = {}


def scrub(text_: str, limit: int = 500) -> str:
    """Remove e-mail addresses and long token-like strings; truncate."""
    cleaned = _TOKENISH.sub("[redacted]", _EMAIL.sub("[email]", text_ or ""))
    return cleaned[:limit]


def strip_query(location: str | None) -> str | None:
    if not location:
        return None
    return location.split("?", 1)[0].split("#", 1)[0][:300]


def record_error(
    source: str, kind: str, message: str, location: str | None, request_id: str | None
) -> None:
    """Store one error on its own connection; never raises."""
    kind, message, location = scrub(kind, 120), scrub(message), strip_query(location)
    fingerprint = hashlib.sha256(f"{source}|{kind}|{message[:120]}|{location}".encode()).hexdigest()
    try:
        with session_factory()() as s, s.begin():
            s.add(
                AppError(
                    source=source,
                    kind=kind,
                    message=message,
                    location=location,
                    request_id=request_id,
                    fingerprint=fingerprint,
                    release=RELEASE,
                )
            )
    except Exception:  # noqa: BLE001 - monitoring must not break the request
        logger.exception("could not store application error")


def external_failure(service: str, code: str) -> None:
    with _lock:
        entry = _external.setdefault(service, {"failures": 0})
        entry.update(last_failure_code=code, last_failure_at=time.time())
        entry["failures"] += 1


def external_success(service: str) -> None:
    with _lock:
        _external.setdefault(service, {"failures": 0})["last_success_at"] = time.time()


def integrations() -> dict[str, Any]:
    """Configuration state of each integration (never secrets) plus recent failures."""
    from app.services import mail, oidc, sms, speech
    from app.services.assistant.provider import answering_available
    from app.services.research.service import available as research_available

    s = get_settings()
    now = time.time()
    with _lock:
        external = {k: dict(v) for k, v in _external.items()}

    def state(name: str, configured: bool) -> dict[str, Any]:
        e = external.get(name, {})
        recent = (
            e.get("last_failure_at")
            and now - e["last_failure_at"] < 900
            and (e.get("last_success_at", 0) < e["last_failure_at"])
        )
        return {
            "configured": configured,
            "status": "not_configured" if not configured else ("degraded" if recent else "ok"),
            "last_failure_code": e.get("last_failure_code"),
            "failures_since_start": e.get("failures", 0),
        }

    providers = oidc.configured()
    return {
        "email": {
            **state("smtp", mail.delivery_mode() != "disabled"),
            "mode": mail.delivery_mode(),
        },
        "assistant": {
            **state("assistant", answering_available()),
            "provider": s.assistant_provider,
        },
        "sms": {
            **state("sms", sms.get_provider() is not None),
            "mode": sms.status()["status"],
            "provider": s.sms_provider or None,
        },
        "web_research": {
            **state("research", research_available()),
            "provider": s.research_provider or None,
        },
        "speech": {
            **state("speech", speech.configured()),
            "provider": s.speech_provider or None,
        },
        "google": state("oidc_google", providers["google"]),
        "microsoft": state("oidc_microsoft", providers["microsoft"]),
        "official_statistics": {
            "configured": True,
            "status": "file_import",
            "note": "NCSI data are imported as reviewed files (no public download API).",
        },
    }


def readiness(session: Session) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
        checks["migration"] = session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:  # noqa: BLE001
        checks["database"] = "unavailable"
    return {
        "ready": checks.get("database") == "ok",
        "release": RELEASE,
        "checks": checks,
        "integrations": integrations(),
    }


def recent_errors(session: Session, limit: int = 50) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            AppError.fingerprint,
            AppError.source,
            AppError.kind,
            AppError.message,
            AppError.location,
            func.count(),
            func.max(AppError.occurred_at),
            func.max(AppError.request_id),
        )
        .group_by(
            AppError.fingerprint,
            AppError.source,
            AppError.kind,
            AppError.message,
            AppError.location,
        )
        .order_by(func.max(AppError.occurred_at).desc())
        .limit(limit)
    ).all()
    return [
        {
            "fingerprint": f,
            "source": src,
            "kind": k,
            "message": m,
            "location": loc,
            "count": n,
            "last_seen": last.isoformat(),
            "last_request_id": rid,
        }
        for f, src, k, m, loc, n, last, rid in rows
    ]
