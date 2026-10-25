"""The search log and cache (``research_search``).

Every search through a real route is stored with the results it returned. The same query on
the same route within ``OSRIP_RESEARCH_CACHE_HOURS`` is answered from the log (the results keep
their original retrieval time and are marked as cached). When a search fails, the last
successful results for that query, of any age, can be shown with their own date, never as
newly retrieved. Scripted test routes are not logged. Without the database nothing is cached
and searches go to the route as before.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.services.research.search import SearchResult

log = logging.getLogger("osrip.research")
# Unit tests without a database switch the log and cache off.
enabled = True


def _rows(results: list[SearchResult]) -> list[dict[str, Any]]:
    return [{**asdict(r), "extra": list(r.extra)} for r in results]


def _results(rows: list[dict[str, Any]]) -> list[SearchResult]:
    out = []
    for r in rows:
        try:
            out.append(SearchResult(**{**r, "extra": tuple(r.get("extra") or ())}))
        except TypeError:
            continue
    return out


def lookup(
    provider: str, query: str, language: str, *, max_age_hours: float | None
) -> tuple[list[SearchResult], datetime] | None:
    """Stored results for this exact query: recent ones (``max_age_hours``), or the last
    successful ones of any age (``None``)."""
    from app.db.session import session_factory
    from app.models import ResearchSearch

    stmt = (
        select(ResearchSearch)
        .where(
            ResearchSearch.provider == provider,
            ResearchSearch.language == language,
            ResearchSearch.query == query[:300],
            ResearchSearch.status.in_(("ok", "no_results")),
        )
        .order_by(ResearchSearch.retrieved_at.desc())
        .limit(1)
    )
    if not enabled:
        return None
    if max_age_hours is not None:
        stmt = stmt.where(
            ResearchSearch.retrieved_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)
        )
    try:
        with session_factory()() as s, s.begin():
            row = s.scalar(stmt)
            if row is None:
                return None
            return _results(row.results), row.retrieved_at
    except Exception:  # noqa: BLE001 - no cache without the database
        return None


def store(
    provider: str,
    query: str,
    language: str,
    *,
    results: list[SearchResult] | None = None,
    error: str | None = None,
    job_id: uuid.UUID | None = None,
) -> None:
    from app.db.session import session_factory
    from app.models import ResearchSearch

    if not enabled:
        return
    rows = _rows(results or [])
    status = "failed" if error else ("ok" if rows else "no_results")
    try:
        with session_factory()() as s, s.begin():
            s.add(
                ResearchSearch(
                    provider=provider[:40],
                    query=query[:300],
                    language=language if language in ("en", "ar") else "en",
                    status=status,
                    error=(error or None) and error[:200],
                    results=rows,
                    result_count=len(rows),
                    job_id=job_id,
                )
            )
    except Exception:  # noqa: BLE001 - the log must never stop a search
        log.exception("could not record a research search")


def cache_hours() -> float:
    return float(get_settings().research_cache_hours)
