# ruff: noqa: E501 - provider payloads are kept as in the official documentation, one object per line
"""Study retrieval without network or database: robots.txt rules, the source scope, unsafe
addresses (SSRF), page, depth, time and credit limits, per-host intervals, cancellation,
reporting periods and the Firecrawl v2 adapter against a mock transport."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import providers
from app.services.research import crawl, firecrawl, robots, safe_fetch

HOSTS = ("ncsi.gov.om", "fao.org")


@pytest.fixture
def dns(monkeypatch):  # noqa: ANN001, ANN201
    table = {
        "www.ncsi.gov.om": ["93.184.216.34"],
        "data.ncsi.gov.om": ["93.184.216.40"],
        "www.fao.org": ["93.184.216.35"],
        "intranet.ncsi.gov.om": ["10.0.0.5"],
        "meta.ncsi.gov.om": ["169.254.169.254"],
        "api.firecrawl.dev": ["93.184.216.50"],
    }
    monkeypatch.setattr(safe_fetch, "resolver", lambda host, port: table.get(host, []))
    return table


@pytest.fixture
def meter(monkeypatch):  # noqa: ANN001, ANN201
    m = providers.MemoryMeter()
    monkeypatch.setattr(providers, "meter", m)
    return m


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.pauses: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.pauses.append(round(seconds, 3))
        self.t += seconds


def allow_all() -> robots.RobotsCache:
    cache = robots.RobotsCache()
    for host in ("www.ncsi.gov.om", "data.ncsi.gov.om", "www.fao.org", "intranet.ncsi.gov.om",
                 "meta.ncsi.gov.om"):  # fmt: skip
        cache.hosts[f"https://{host}"] = robots.Rules("missing")
    return cache


def limits(**kw) -> crawl.Limits:  # noqa: ANN003
    base = dict(max_pages=10, max_depth=0, max_runtime_seconds=60, max_credits=100,
                max_pdf_pages=5, host_interval_seconds=2.0, hosts=HOSTS)  # fmt: skip
    return crawl.Limits(**{**base, **kw})


@pytest.fixture
def pages_served(monkeypatch, dns):  # noqa: ANN001, ANN201
    """Direct retrieval (no Firecrawl key): HTML pages with a figure and links."""
    monkeypatch.setattr(get_settings(), "firecrawl_api_key", None)
    served: list[str] = []

    def fetch(url: str, *, timeout: float, max_bytes: int) -> safe_fetch.Fetched:
        safe_fetch.check_url(url)
        served.append(url)
        html = (
            f"<html><head><title>Statistical Bulletin Q2 2026</title></head><body>"
            f"<p>Electricity generation reached 5,743.9 GWh in August 2026.</p>"
            f'<a href="/more-{len(served)}">more</a><a href="https://elsewhere.example.com/x">x</a>'
            f"</body></html>"
        )
        return safe_fetch.Fetched(url, 200, "text/html; charset=utf-8", html, False, html.encode())

    monkeypatch.setattr(safe_fetch, "fetch", fetch)
    return served


# ------------------------------------------------------------------ robots.txt


def test_robots_rules_disallow_paths_and_give_a_crawl_delay() -> None:
    rules = robots.parse(
        "User-agent: *\nDisallow: /private/\nCrawl-delay: 7\n\n"
        "User-agent: OSRIP-research\nDisallow: /no-osrip/\nCrawl-delay: 5\n"
    )
    assert rules.allows("https://www.ncsi.gov.om/stats") is True
    assert rules.allows("https://www.ncsi.gov.om/no-osrip/a") is False
    assert rules.crawl_delay == 5.0
    assert robots.Rules("missing").allows("https://x.gov.om/anything") is True
    assert robots.Rules("unreachable").allows("https://x.gov.om/") is False


@pytest.mark.parametrize(
    ("code", "status"),
    [("http_404", "missing"), ("http_403", "missing"), ("http_503", "unreachable"),
     ("timeout", "unreachable"), ("unsupported_content_type", "unreachable")],
)  # fmt: skip
def test_robots_txt_failures_follow_rfc_9309(monkeypatch, code: str, status: str) -> None:  # noqa: ANN001
    def fail(url: str, **_: object) -> None:
        raise safe_fetch.FetchFailed(code)

    monkeypatch.setattr(safe_fetch, "fetch", fail)
    assert robots.RobotsCache().rules("https://www.ncsi.gov.om/a").status == status


# ------------------------------------------------------------------ scope, order, periods


def test_scope_hosts_and_limits_are_never_raised(monkeypatch) -> None:  # noqa: ANN001
    assert crawl.scope_hosts("none") == ()
    assert "ncsi.gov.om" in crawl.scope_hosts("official")
    assert "fao.org" not in crawl.scope_hosts("official")
    assert "fao.org" in crawl.scope_hosts("official_international")
    assert crawl.host_allowed("https://www.ncsi.gov.om/x", HOSTS)
    assert not crawl.host_allowed("https://ncsi.gov.om.evil.example/x", HOSTS)
    assert not crawl.host_allowed("https://fakencsi.gov.om/x", HOSTS)
    s = get_settings()
    monkeypatch.setattr(s, "crawl_max_pages", 8)
    assert crawl.limits_for("official", {"max_pages": 500}).max_pages == 8
    assert crawl.limits_for("official", {"max_pages": 3}).max_pages == 3
    assert crawl.limits_for("none", {"max_pages": 3}).max_pages == 0
    monkeypatch.setattr(s, "crawl_allowed_domains", ["data.gov.om"])
    assert crawl.scope_hosts("official_international") == ("data.gov.om",)


def test_official_and_downloadable_sources_come_first() -> None:
    ordered = crawl.order([
        {"url": "https://www.fao.org/report.pdf"},
        {"url": "https://www.ncsi.gov.om/page"},
        {"url": "https://www.ncsi.gov.om/bulletin.pdf"},
        {"url": "https://news.example.com/story"},
    ])  # fmt: skip
    assert [c["url"] for c in ordered] == [
        "https://www.ncsi.gov.om/bulletin.pdf", "https://www.ncsi.gov.om/page",
        "https://www.fao.org/report.pdf", "https://news.example.com/story",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("title", "period"),
    [("Statistical Year Book 2026, Issue 54", "2026"), ("Bulletin Q1 2025", "2025 Q1"),
     ("Water review 2022-2024", "2022–2024"), ("Annual report", None), ("", None)],
)  # fmt: skip
def test_reporting_period_is_taken_from_the_title_or_not_stated(
    title: str, period: str | None
) -> None:
    assert crawl.reporting_period(title) == period


# ------------------------------------------------------------------ the retriever


def test_unsafe_addresses_are_blocked_before_any_request(pages_served, dns) -> None:  # noqa: ANN001
    clock = Clock()
    r = crawl.Retriever(limits(), ["electricity"], clock=clock, sleep=clock.sleep,
                        robots_cache=allow_all())  # fmt: skip
    docs = r.run([
        {"url": "https://intranet.ncsi.gov.om/stats"},
        {"url": "https://meta.ncsi.gov.om/latest"},
        {"url": "ftp://www.ncsi.gov.om/file.csv"},
        {"url": "https://user:pw@www.ncsi.gov.om/"},
        {"url": "https://www.ncsi.gov.om:8443/"},
        {"url": "http://127.0.0.1/admin"},
        {"url": "https://evil.example.com/"},
    ])  # fmt: skip
    status = {d.url: d.status for d in docs}
    assert status["https://intranet.ncsi.gov.om/stats"] == "blocked_private_address"
    assert status["https://meta.ncsi.gov.om/latest"] == "blocked_private_address"
    assert status["ftp://www.ncsi.gov.om/file.csv"] == "blocked_scheme_not_allowed"
    assert status["https://user:pw@www.ncsi.gov.om/"] == "blocked_credentials_in_url"
    assert status["https://www.ncsi.gov.om:8443/"] == "blocked_port_not_allowed"
    assert status["http://127.0.0.1/admin"] == "outside_scope"
    assert status["https://evil.example.com/"] == "outside_scope"
    assert pages_served == []  # nothing was requested


def test_robots_disallow_and_unreachable_robots_stop_retrieval(pages_served) -> None:  # noqa: ANN001
    cache = allow_all()
    cache.hosts["https://www.ncsi.gov.om"] = robots.parse("User-agent: *\nDisallow: /closed/\n")
    cache.hosts["https://www.fao.org"] = robots.Rules("unreachable")
    clock = Clock()
    r = crawl.Retriever(limits(), [], clock=clock, sleep=clock.sleep, robots_cache=cache)
    docs = {d.url: d for d in r.run([
        {"url": "https://www.ncsi.gov.om/closed/table"}, {"url": "https://www.ncsi.gov.om/open"},
        {"url": "https://www.fao.org/x"},
    ])}  # fmt: skip
    assert docs["https://www.ncsi.gov.om/closed/table"].status == "robots_disallowed"
    assert docs["https://www.fao.org/x"].status == "robots_unavailable"
    assert docs["https://www.ncsi.gov.om/open"].status == "ok"
    assert pages_served == ["https://www.ncsi.gov.om/open"]


def test_documents_keep_provenance_digest_and_relevant_excerpt(pages_served) -> None:  # noqa: ANN001
    clock = Clock()
    r = crawl.Retriever(limits(), ["generation"], clock=clock, sleep=clock.sleep,
                        robots_cache=allow_all())  # fmt: skip
    [doc] = r.run([{"url": "https://www.ncsi.gov.om/bulletin"}])
    assert doc.status == "ok" and doc.retriever == "direct"
    assert doc.source_class == "official" and doc.publisher
    assert doc.title == "Statistical Bulletin Q2 2026" and doc.reporting_period == "2026 Q2"
    assert doc.sha256 and len(doc.sha256) == 64
    assert "5,743.9 GWh" in (doc.excerpt or "")
    assert doc.retrieved_at is not None and doc.published is None  # not stated: not guessed


def test_page_runtime_credit_limits_and_host_interval(pages_served) -> None:  # noqa: ANN001
    clock = Clock()
    urls = [{"url": f"https://www.ncsi.gov.om/p{i}"} for i in range(5)]
    r = crawl.Retriever(limits(max_pages=3), [], clock=clock, sleep=clock.sleep,
                        robots_cache=allow_all())  # fmt: skip
    docs = r.run(urls)
    assert sum(d.status == "ok" for d in docs) == 3 and r.stopped == "page_limit"
    # The same host is asked at most once per interval.
    assert clock.pauses and all(p <= 2.0 for p in clock.pauses) and sum(clock.pauses) >= 4.0
    credits = crawl.Retriever(limits(max_credits=2), [], clock=Clock(), sleep=lambda s: None,
                              robots_cache=allow_all())  # fmt: skip
    assert sum(d.status == "ok" for d in credits.run(urls)) == 2
    assert credits.stopped == "credit_limit"
    slow = Clock()
    timed = crawl.Retriever(limits(max_runtime_seconds=3), [], clock=slow, sleep=slow.sleep,
                            robots_cache=allow_all())  # fmt: skip
    timed.run(urls)
    assert timed.stopped == "runtime_limit"


def test_links_are_followed_only_to_the_set_depth_and_scope(pages_served) -> None:  # noqa: ANN001
    clock = Clock()
    flat = crawl.Retriever(limits(), [], clock=clock, sleep=clock.sleep, robots_cache=allow_all())
    assert [d.depth for d in flat.run([{"url": "https://www.ncsi.gov.om/start"}])] == [0]
    deep = crawl.Retriever(limits(max_depth=1), [], clock=Clock(), sleep=lambda s: None,
                           robots_cache=allow_all())  # fmt: skip
    docs = deep.run([{"url": "https://www.ncsi.gov.om/start"}])
    assert [d.depth for d in docs] == [0, 1]
    assert docs[1].url.startswith("https://www.ncsi.gov.om/more-")  # the page's own link
    assert not any("elsewhere.example.com" in d.url for d in docs)


def test_a_stopped_study_ends_after_the_current_document(pages_served) -> None:  # noqa: ANN001
    asked = {"n": 0}

    def cancelled() -> bool:
        asked["n"] += 1
        return asked["n"] > 1

    r = crawl.Retriever(limits(), [], cancelled=cancelled, clock=Clock(), sleep=lambda s: None,
                        robots_cache=allow_all())  # fmt: skip
    docs = r.run([{"url": "https://www.ncsi.gov.om/a"}, {"url": "https://www.ncsi.gov.om/b"}])
    assert len(docs) == 1 and r.stopped == "cancelled"


# ------------------------------------------------------------------ Firecrawl v2


def _firecrawl(monkeypatch, handler) -> list[httpx.Request]:  # noqa: ANN001
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(get_settings(), "firecrawl_api_key", SecretStr("fc-test-only"))
    monkeypatch.setattr(firecrawl, "http_client_factory",
                        lambda timeout: httpx.Client(transport=httpx.MockTransport(record)))  # fmt: skip
    return seen


def test_firecrawl_scrape_request_and_response(monkeypatch, dns, meter) -> None:  # noqa: ANN001
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {
            "markdown": "# Bulletin\nGeneration 5,743.9 GWh (August 2026).",
            "links": ["https://www.ncsi.gov.om/next"],
            "metadata": {"title": "Monthly Bulletin", "sourceURL": "https://www.ncsi.gov.om/b.pdf",
                         "url": "https://www.ncsi.gov.om/b.pdf", "statusCode": 200,
                         "contentType": "application/pdf", "numPages": 4, "totalPages": 40}}})  # fmt: skip

    seen = _firecrawl(monkeypatch, ok)
    page = firecrawl.client().scrape(
        "https://www.ncsi.gov.om/b.pdf", max_pdf_pages=4, with_links=True
    )
    [request] = seen
    body = json.loads(request.content)
    assert str(request.url) == "https://api.firecrawl.dev/v2/scrape"
    assert request.headers["authorization"] == "Bearer fc-test-only"
    assert body["url"] == "https://www.ncsi.gov.om/b.pdf" and body["formats"] == [
        "markdown",
        "links",
    ]
    assert body["parsers"] == [{"type": "pdf", "maxPages": 4}]
    assert body["skipTlsVerification"] is False and body["onlyMainContent"] is True
    assert page.pages == 4 and page.total_pages == 40 and page.credits == 5
    assert page.title == "Monthly Bulletin" and "5,743.9 GWh" in page.markdown
    [call] = meter.rows
    assert call["provider"] == "firecrawl" and call["capability"] == "retrieve"
    assert call["credits"] == 5 and call["status"] == "ok"


@pytest.mark.parametrize(
    ("status", "code"), [(402, "http_402"), (429, "http_429"), (500, "http_500")]
)
def test_firecrawl_errors_are_codes_without_the_key(
    monkeypatch, dns, meter, status: int, code: str
) -> None:  # noqa: ANN001
    _firecrawl(monkeypatch, lambda r: httpx.Response(status, json={"success": False,
                                                                     "error": "fc-test-only rejected"}))  # fmt: skip
    with pytest.raises(firecrawl.FirecrawlError) as exc:
        firecrawl.client().scrape("https://www.ncsi.gov.om/x", max_pdf_pages=1)
    assert str(exc.value) == code and "fc-test-only" not in str(exc.value)
    assert meter.rows[-1]["status"] == code


def test_firecrawl_never_receives_or_returns_private_addresses(monkeypatch, dns, meter) -> None:  # noqa: ANN001
    def redirected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {"markdown": "secret", "metadata": {
            "url": "http://169.254.169.254/latest", "statusCode": 200}}})  # fmt: skip

    seen = _firecrawl(monkeypatch, redirected)
    with pytest.raises(safe_fetch.FetchBlocked):
        firecrawl.client().scrape("https://intranet.ncsi.gov.om/", max_pdf_pages=1)
    assert seen == []  # the private address was never sent
    with pytest.raises(firecrawl.FirecrawlError, match="blocked_redirect"):
        firecrawl.client().scrape("https://www.ncsi.gov.om/", max_pdf_pages=1)


def test_firecrawl_map_lists_addresses(monkeypatch, dns, meter) -> None:  # noqa: ANN001
    seen = _firecrawl(monkeypatch, lambda r: httpx.Response(200, json={"success": True, "links": [
        {"url": "https://www.ncsi.gov.om/a", "title": "A"}, "https://www.ncsi.gov.om/b"]}))  # fmt: skip
    links = firecrawl.client().map("https://www.ncsi.gov.om", search="electricity", limit=5)
    assert [x["url"] for x in links] == ["https://www.ncsi.gov.om/a", "https://www.ncsi.gov.om/b"]
    assert str(seen[0].url) == "https://api.firecrawl.dev/v2/map"
    assert json.loads(seen[0].content)["search"] == "electricity"


def test_without_a_key_firecrawl_is_not_configured(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "firecrawl_api_key", None)
    assert firecrawl.client() is None and firecrawl.configured() is False
    assert providers.missing("firecrawl", "retrieve") == ["OSRIP_FIRECRAWL_API_KEY"]
