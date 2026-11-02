"""Built-in error monitoring and service health (no third-party account needed).

* Unhandled server exceptions and browser errors are stored in ``app_error`` with
  a fingerprint for grouping. Stored: error type, a truncated message, the path
  without its query string, a request id and the release. Never stored: request
  bodies, cookies, headers, query strings or user identifiers.
* External services (model API, OpenID providers, SMTP) report their latest
  failure here, in memory, so the health page can show degraded integrations
  without calling them on every health check.
* Request timings (route pattern, status, milliseconds to the response headers) are
  kept in memory for the last requests of this process only; nothing about the
  person or the request content.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import session_factory
from app.models import AppError, ProviderCall, SourceFeed, SourceRelease

logger = logging.getLogger("osrip.monitoring")
RELEASE = "0.8.0"

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_TOKENISH = re.compile(r"[A-Za-z0-9_\-]{24,}")
_lock = threading.Lock()
_external: dict[str, dict[str, Any]] = {}
TIMING_WINDOW = 2000
_timings: deque[tuple[str, int, float]] = deque(maxlen=TIMING_WINDOW)
_started = time.time()
# Refused before any call was made (OSRIP's own limits), so neither a call nor a failure.
REFUSED = ("budget_exhausted", "daily_limit")


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


def record_request(route: str, status: int, duration_ms: float) -> None:
    """One finished request: its route pattern (never the concrete path), status and time."""
    with _lock:
        _timings.append((route, status, duration_ms))


def _percentile(values: list[float], share: float) -> float:
    """Nearest-rank percentile of sorted values."""
    return values[max(1, math.ceil(len(values) * share)) - 1]


def performance() -> dict[str, Any]:
    """Response times of this process's latest requests (up to ``TIMING_WINDOW``)."""
    with _lock:
        rows = list(_timings)
    out: dict[str, Any] = {
        "window": TIMING_WINDOW,
        "requests": len(rows),
        "uptime_seconds": int(time.time() - _started),
    }
    if not rows:
        return {
            **out,
            "p50_ms": None,
            "p95_ms": None,
            "max_ms": None,
            "server_errors": 0,
            "slowest": [],
        }
    durations = sorted(d for _, _, d in rows)
    by_route: dict[str, list[float]] = {}
    for route, _, d in rows:
        by_route.setdefault(route, []).append(d)
    slowest = sorted(
        (
            {"route": route, "requests": len(ds), "p95_ms": round(_percentile(sorted(ds), 0.95), 1)}
            for route, ds in by_route.items()
        ),
        key=lambda r: r["p95_ms"],
        reverse=True,
    )[:5]
    return {
        **out,
        "p50_ms": round(_percentile(durations, 0.5), 1),
        "p95_ms": round(_percentile(durations, 0.95), 1),
        "max_ms": round(durations[-1], 1),
        "server_errors": sum(1 for _, status, _ in rows if status >= 500),
        "slowest": slowest,
    }


def provider_usage(session: Session) -> dict[str, Any]:
    """Calls, failures, tokens and estimated cost per provider over the last 24 hours and
    30 days, from ``provider_call`` (outcomes and counts only; no prompts or answers)."""
    prices = get_settings().provider_prices
    now = datetime.now(UTC)
    windows: dict[str, list[dict[str, Any]]] = {}
    for key, since in (("day", now - timedelta(hours=24)), ("month", now - timedelta(days=30))):
        made = ProviderCall.status.not_in(REFUSED)
        rows = session.execute(
            select(
                ProviderCall.provider,
                func.count().filter(made),
                func.count().filter(made, ProviderCall.status != "ok"),
                func.count().filter(ProviderCall.status.in_(REFUSED)),
                func.coalesce(func.sum(ProviderCall.input_tokens), 0),
                func.coalesce(func.sum(ProviderCall.output_tokens), 0),
                func.coalesce(func.sum(ProviderCall.estimated_cost_usd), 0),
                func.avg(ProviderCall.duration_ms).filter(made),
            )
            .where(ProviderCall.created_at >= since)
            .group_by(ProviderCall.provider)
            .order_by(ProviderCall.provider)
        ).all()
        windows[key] = [
            {
                "provider": provider,
                "calls": calls,
                "failures": failures,
                "refused": refused,
                "input_tokens": int(tokens_in),
                "output_tokens": int(tokens_out),
                # Estimated from the configured prices; unknown when none are set.
                "estimated_cost_usd": float(cost) if prices.get(provider) else None,
                "average_ms": None if avg is None else round(float(avg)),
            }
            for provider, calls, failures, refused, tokens_in, tokens_out, cost, avg in rows
        ]
    return {"windows": windows, "priced": sorted(prices)}


def sync_summary(session: Session) -> list[dict[str, Any]]:
    """Each official-statistics feed: schedule, last check and releases awaiting approval."""
    staged = dict(
        session.execute(
            select(SourceRelease.feed_id, func.count())
            .where(SourceRelease.status == "staged")
            .group_by(SourceRelease.feed_id)
        ).all()
    )
    feeds = session.scalars(select(SourceFeed).order_by(SourceFeed.code))

    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    return [
        {
            "code": f.code,
            "title": {"en": f.title_en, "ar": f.title_ar},
            "access": f.access,
            "enabled": f.enabled,
            "auto_publish": f.auto_publish,
            "last_checked_at": iso(f.last_checked_at),
            "last_success_at": iso(f.last_success_at),
            "next_check_at": iso(f.next_check_at),
            "last_status": f.last_status,
            "consecutive_failures": f.consecutive_failures,
            "awaiting_approval": int(staged.get(f.id, 0)),
        }
        for f in feeds
    ]
