"""Independent web steps of one model turn, fetched at the same time.

When the model asks for several web searches or several page reads in the same step, their
network work runs concurrently here (at most ``research_parallel_fetches`` at once), before the
tools themselves run one by one as before. The tools then take the prefetched result instead
of fetching again, so the evidence ledger, the search log, the budgets (searches and pages per
answer), the rate limit and the daily limits are applied exactly as for a single call; only
the waiting overlaps. Addresses are deduplicated first, nothing beyond the step's budget is
fetched, cached results are used without a new call (for a question about the latest figures
only while recent), and a stopped question stops waiting at once (calls already in flight end
by their own timeouts; their results are discarded).
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any

from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import ApiError
from app.services.research import fetching, search_log
from app.services.research.search import (
    SearchError,
    get_fallback_search_provider,
    get_search_provider,
)

log = logging.getLogger("osrip.research")


def _run_all(jobs: dict[Any, Callable[[], Any]], check: Callable[[], None]) -> dict[Any, Any]:
    """Run the jobs with bounded concurrency; a job's exception is returned as its result."""
    workers = max(1, min(get_settings().research_parallel_fetches, len(jobs)))
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="research")

    def guarded(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - handed to the tool that asked for it
            return exc

    # Each job runs in a copy of the caller's context (request accounting, stop checks).
    futures = {
        pool.submit(contextvars.copy_context().run, guarded, fn): key for key, fn in jobs.items()
    }
    results: dict[Any, Any] = {}
    try:
        pending = set(futures)
        while pending:
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            for future in done:
                results[futures[future]] = future.result()
            check()  # the person stopped the question: stop waiting now
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def prefetch_reads(ledger: Any, calls: list[dict[str, Any]], check: Callable[[], None]) -> int:
    """Read the pages of this step's read_web_page calls concurrently. Returns how many."""
    s = get_settings()
    by_id = ledger.by_id()
    limit = getattr(ledger, "max_pages", None) or s.research_max_pages_per_answer
    room = max(0, limit - ledger.pages)
    urls: list[str] = []
    for call in calls:
        found = by_id.get(str((call.get("input") or {}).get("evidence_id")))
        url = found.get("url") if found and found.get("kind") == "web" else None
        if url and url not in urls and url not in ledger.reads and url not in ledger.prefetched:
            urls.append(url)
    urls = urls[:room]
    if len(urls) < 2:
        return 0  # one page gains nothing from running beside nothing
    fresh = search_log.cache_hours(ledger.fresh_hours)
    results = _run_all(
        {
            url: (lambda u=url: fetching.read(u, job_id=ledger.job_id, max_age_hours=fresh))
            for url in urls
        },
        check,
    )
    for url, read in results.items():
        if isinstance(read, fetching.Read):
            ledger.prefetched[url] = read
    return len(results)


def _planned_queries(
    call_input: dict[str, Any], language: str
) -> tuple[str, list[tuple[str, str]]]:
    """The normalized query and the (query, language) pairs web_search will search for."""
    from app.services.research import service

    query = " ".join(str(call_input.get("query") or "").split())[:300]
    primary = service._language_of(query) if query else language
    queries = [(service._with_oman(query, primary), primary)]
    other_input = call_input.get("query_other_language")
    if other_input:
        other = " ".join(str(other_input).split())[:300]
        other_lang = service._language_of(other)
        if other and other_lang != primary:
            queries.append((service._with_oman(other, other_lang), other_lang))
    return query, queries


def prefetch_searches(ledger: Any, calls: list[dict[str, Any]], check: Callable[[], None]) -> int:
    """Run the searches of this step's web_search calls concurrently. Returns how many."""
    s = get_settings()
    provider = get_search_provider() or get_fallback_search_provider()
    if provider is None or getattr(provider, "display_only", False):
        return 0
    if not ledger.web_first and ledger.data_lookups == 0:
        return 0  # these calls will be refused (platform data first): nothing to fetch
    limit = getattr(ledger, "max_searches", None) or s.research_max_searches_per_answer
    room = max(0, limit - ledger.searches)
    cacheable = getattr(provider, "cacheable", False)
    max_age = search_log.cache_hours(ledger.fresh_hours)
    planned: list[tuple[str, str]] = []
    prechecked: list[str] = []
    for call in calls:
        query, queries = _planned_queries(call.get("input") or {}, ledger.language)
        wanted = [
            pair
            for pair in queries
            if (provider.name, *pair) not in ledger.search_memo
            and pair not in planned
            and not (
                cacheable
                and max_age > 0
                and search_log.lookup(provider.name, *pair, max_age_hours=max_age)
            )
        ]
        if not wanted or len(planned) + len(wanted) > room:
            continue
        if ledger.client_key:
            # The per-client research limit, counted once for this call (web_search skips it).
            try:
                ratelimit.check(f"research:{ledger.client_key}", s.research_per_client_hour, 3600)
            except ApiError:
                continue
            prechecked.append(query)
        planned += wanted
    ledger.search_prechecked.update(prechecked)
    if len(planned) < 2:
        return 0
    results = _run_all(
        {pair: (lambda p=pair: provider.search(p[0], language=p[1], count=10)) for pair in planned},
        check,
    )
    for (q, lang), found in results.items():
        if isinstance(found, (list, SearchError)):
            ledger.search_memo[(provider.name, q, lang)] = found
        else:
            log.warning("prefetched search failed: %s", type(found).__name__)
    return len(results)
