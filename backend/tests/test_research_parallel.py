"""Independent web steps of one model turn run at the same time (research/parallel.py), with
the same evidence, budgets and limits as one by one: addresses deduplicated, nothing beyond
the budget fetched, failures reported by the tool that asked, a stopped question stops
waiting, and "latest" questions rely only on recent cached results. Simulated providers;
nothing here reaches the network."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from app.domain.enums import DataMode
from app.services.assistant import routing
from app.services.assistant.progress import Cancelled
from app.services.assistant.tools import Ledger
from app.services.research import fetching, parallel, search_log
from app.services.research import service as research
from app.services.research.search import SearchError, SearchResult


def _never_stopped() -> None:
    return None


def _ledger(pages: int = 6, searches: int = 6) -> Ledger:
    ledger = Ledger(DataMode.SYNTHETIC, web_enabled=True)
    ledger.max_pages, ledger.max_searches = pages, searches
    return ledger


def _slow_reads(monkeypatch, delay: float = 0.4) -> list[str]:  # noqa: ANN001
    seen: list[str] = []
    lock = threading.Lock()

    def read(url: str, **_: Any) -> fetching.Read:
        with lock:
            seen.append(url)
        time.sleep(delay)
        return fetching.Read("ok", url, url, title="Page", text=f"Text of {url} " * 40)

    monkeypatch.setattr(fetching, "read", read)
    return seen


def _read_calls(ledger: Ledger, urls: list[str]) -> list[dict[str, Any]]:
    calls = []
    for url in urls:
        item = ledger.add({"kind": "web", "url": url, "title": "Result", "query": "q"})
        calls.append({"name": "read_web_page", "input": {"evidence_id": item["id"]}})
    return calls


def test_pages_of_one_step_are_read_at_the_same_time_once_each(monkeypatch) -> None:  # noqa: ANN001
    seen = _slow_reads(monkeypatch)
    monkeypatch.setattr(parallel.get_settings(), "research_parallel_fetches", 3)
    ledger = _ledger()
    urls = ["https://ncsi.gov.om/a", "https://ncsi.gov.om/b", "https://ncsi.gov.om/c"]
    calls = _read_calls(ledger, [*urls, urls[0]])  # the same address twice
    t0 = time.perf_counter()
    assert parallel.prefetch_reads(ledger, calls, _never_stopped) == 3
    assert time.perf_counter() - t0 < 0.9, "three 0.4 s reads overlap"
    assert sorted(seen) == sorted(urls), "each address fetched once"
    for call in calls:
        out = research.read_web_page(ledger, call["input"]["evidence_id"])
        assert out["status"] == "ok"
    assert len(seen) == 3, "the tools took the prefetched pages"
    assert ledger.pages == 3, "a page counts once against the budget"


def test_nothing_beyond_the_page_budget_is_fetched(monkeypatch) -> None:  # noqa: ANN001
    seen = _slow_reads(monkeypatch, delay=0.01)
    ledger = _ledger(pages=2)
    calls = _read_calls(ledger, [f"https://mem.gov.om/{i}" for i in range(4)])
    parallel.prefetch_reads(ledger, calls, _never_stopped)
    assert len(seen) == 2
    statuses = [research.read_web_page(ledger, c["input"]["evidence_id"])["status"] for c in calls]
    assert statuses == ["ok", "ok", "limit_reached", "limit_reached"]
    assert len(seen) == 2


def test_a_stopped_question_stops_waiting(monkeypatch) -> None:  # noqa: ANN001
    _slow_reads(monkeypatch, delay=2.0)
    ledger = _ledger()
    calls = _read_calls(ledger, ["https://a.gov.om/x", "https://a.gov.om/y"])
    stopped = threading.Event()

    def check() -> None:
        if stopped.is_set():
            raise Cancelled

    threading.Timer(0.2, stopped.set).start()
    t0 = time.perf_counter()
    with pytest.raises(Cancelled):
        parallel.prefetch_reads(ledger, calls, check)
    assert time.perf_counter() - t0 < 1.5, "no wait for the 2 s reads"
    assert ledger.prefetched == {} and ledger.pages == 0


class _Provider:
    name = "stub-search"
    cacheable = False
    display_only = False

    def __init__(self, fail: set[str] | None = None) -> None:
        self.queries: list[str] = []
        self.fail = fail or set()
        self.lock = threading.Lock()

    def search(self, query: str, *, language: str, count: int) -> list[SearchResult]:
        with self.lock:
            self.queries.append(query)
        time.sleep(0.4)
        if any(word in query for word in self.fail):
            raise SearchError("http_503")
        return [
            SearchResult(
                title=f"About {query}", url=f"https://ncsi.gov.om/{len(query)}", snippet="s"
            )
        ]


def _search_calls(*queries: str) -> list[dict[str, Any]]:
    return [{"name": "web_search", "input": {"query": q, "domain": "water"}} for q in queries]


def test_searches_of_one_step_run_at_the_same_time(monkeypatch) -> None:  # noqa: ANN001
    provider = _Provider(fail={"tariff"})
    monkeypatch.setattr(parallel, "get_search_provider", lambda: provider)
    monkeypatch.setattr(research, "get_search_provider", lambda: provider)
    monkeypatch.setattr(research, "get_fallback_search_provider", lambda: None)
    ledger = _ledger()
    calls = _search_calls("desalination capacity 2025", "water tariff Oman")
    t0 = time.perf_counter()
    assert parallel.prefetch_searches(ledger, calls, _never_stopped) == 2
    assert time.perf_counter() - t0 < 0.75
    ok = research.web_search(ledger, "desalination capacity 2025", "water", None)
    failed = research.web_search(ledger, "water tariff Oman", "water", None)
    assert ok["status"] == "ok" and failed["status"] == "search_failed"
    assert len(provider.queries) == 2, "the tools did not search again"
    assert ledger.searches == 2, "each search counts once"
    assert any(i["kind"] == "search" and i["status"] == "failed" for i in ledger.items)


def test_search_budget_and_rate_limit_are_counted_once(monkeypatch) -> None:  # noqa: ANN001
    from app.core import ratelimit

    ratelimit.reset()
    provider = _Provider()
    monkeypatch.setattr(parallel, "get_search_provider", lambda: provider)
    monkeypatch.setattr(research, "get_search_provider", lambda: provider)
    monkeypatch.setattr(research, "get_fallback_search_provider", lambda: None)
    checks: list[str] = []
    real_check = ratelimit.check
    monkeypatch.setattr(
        ratelimit, "check", lambda key, *a, **k: (checks.append(key), real_check(key, *a, **k))
    )
    ledger = _ledger(searches=2)
    ledger.client_key = "client-digest"
    queries = ("water production 2024", "electricity output 2024", "food imports 2024")
    parallel.prefetch_searches(ledger, _search_calls(*queries), _never_stopped)
    assert len(provider.queries) == 2, "the third search is beyond the budget"
    for q in queries:
        research.web_search(ledger, q, "general", ledger.client_key)
    assert len(provider.queries) == 2 and ledger.searches == 2
    assert len(checks) == 2, "one rate-limit count per search made, not two"
    ratelimit.reset()


def test_latest_questions_rely_only_on_recent_cached_results(monkeypatch) -> None:  # noqa: ANN001
    assert routing.asks_for_latest("What is the latest desalination output?")
    assert routing.asks_for_latest("ما أحدث رقم لإنتاج الكهرباء؟")
    assert not routing.asks_for_latest("Electricity generation in 2023")
    ages: list[float | None] = []
    provider = _Provider()
    provider.cacheable = True
    monkeypatch.setattr(research, "get_search_provider", lambda: provider)
    monkeypatch.setattr(research, "get_fallback_search_provider", lambda: None)
    monkeypatch.setattr(search_log, "lookup", lambda *a, max_age_hours: ages.append(max_age_hours))
    monkeypatch.setattr(search_log, "store", lambda *a, **k: None)
    ledger = _ledger()
    ledger.fresh_hours = 6.0
    research.web_search(ledger, "latest water production", "water", None)
    assert ages and ages[0] == 6.0
    assert fetching._cached("https://ncsi.gov.om/x", max_age_hours=0) is None, "no cache at age 0"


def test_latest_never_lengthens_the_cache_period(monkeypatch) -> None:  # noqa: ANN001
    assert search_log.cache_hours(6.0) == 6.0
    monkeypatch.setattr(search_log.get_settings(), "research_cache_hours", 0)
    assert search_log.cache_hours(6.0) == 0, "with the cache off, latest stays uncached"
    assert search_log.cache_hours(None) == 0
