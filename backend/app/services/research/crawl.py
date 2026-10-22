"""Targeted retrieval of documents for a study, within configured limits.

For each discovered address, in order (Omani official sources first, then international
statistical organisations; downloadable files such as PDF, CSV and spreadsheets before
ordinary pages):

1. it must be on a host of the study's source scope (the official registry in
   ``sources.py``, or ``OSRIP_CRAWL_ALLOWED_DOMAINS``);
2. it must pass the SSRF check: http(s) on the default port, no credentials, every address
   public (``safe_fetch.check_url``); a redirect to anything else is discarded;
3. robots.txt must allow it (``robots.py``, agent ``OSRIP-research``);
4. each host is asked at most once per interval (the configured interval, or the site's
   Crawl-delay if longer);
5. the study's page, depth, run-time and credit limits must still allow it;
6. it is retrieved through Firecrawl when configured, otherwise directly (SSRF-safe, HTML and
   PDF), with one retry after a transient failure.

What is kept: provenance (address, final address, publisher, title, retrieval time,
publication date when the page states one, the reporting period named in the title),
the content digest, and a bounded excerpt of the passages that mention the study's terms.
The text is untrusted: it is never treated as instructions or added to the data.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from app.core.config import get_settings
from app.services.research import firecrawl, pages, robots, safe_fetch
from app.services.research.sources import INTERNATIONAL, OFFICIAL, classify, rank

DOWNLOADABLE = (".pdf", ".csv", ".xlsx", ".xls", ".json")
TRANSIENT = ("timeout", "network", "http_429", "http_500", "http_502", "http_503", "http_504")
EXCERPT_CHARS = 6000


@dataclass(frozen=True)
class Limits:
    max_pages: int
    max_depth: int
    max_runtime_seconds: int
    max_credits: int
    max_pdf_pages: int
    host_interval_seconds: float
    hosts: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_pages": self.max_pages, "max_depth": self.max_depth,
            "max_runtime_seconds": self.max_runtime_seconds, "max_credits": self.max_credits,
            "max_pdf_pages": self.max_pdf_pages, "host_interval_seconds": self.host_interval_seconds,
            "hosts": list(self.hosts),
        }  # fmt: skip


def scope_hosts(scope: str) -> tuple[str, ...]:
    """Hosts a study may read: the configured list, or the official registry for the scope."""
    configured = tuple(h.lower().strip(".") for h in get_settings().crawl_allowed_domains if h)
    if scope == "none":
        return ()
    if configured:
        return configured
    hosts = list(OFFICIAL)
    if scope == "official_international":
        hosts += list(INTERNATIONAL)
    return tuple(hosts)


def limits_for(scope: str, overrides: dict[str, Any] | None = None) -> Limits:
    """The server's limits, lowered (never raised) by a study's or a schedule's own."""
    s = get_settings()
    o = overrides or {}

    def lower(key: str, default: int) -> int:
        value = o.get(key)
        return max(0, min(int(value), default)) if isinstance(value, int) else default

    return Limits(
        max_pages=0 if scope == "none" else lower("max_pages", s.crawl_max_pages),
        max_depth=lower("max_depth", min(s.crawl_max_depth, 3)),
        max_runtime_seconds=lower("max_runtime_seconds", s.crawl_max_runtime_seconds),
        max_credits=lower("max_credits", s.crawl_max_credits),
        max_pdf_pages=max(1, lower("max_pdf_pages", s.crawl_max_pdf_pages)),
        host_interval_seconds=max(0.0, s.crawl_host_interval_seconds),
        hosts=scope_hosts(scope),
    )


def host_allowed(url: str, hosts: tuple[str, ...]) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return bool(host) and any(host == h or host.endswith("." + h) for h in hosts)


def order(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Official sources first, then international; downloadable files before pages."""

    def key(c: dict[str, Any]) -> tuple[int, int, int]:
        path = urlsplit(c["url"]).path.lower()
        return (int(c.get("depth", 0)), rank(classify(c["url"])["source_class"]),
                0 if path.endswith(DOWNLOADABLE) else 1)  # fmt: skip

    return sorted(candidates, key=key)


_YEAR = re.compile(r"(?<!\d)(20[0-4]\d|19[89]\d)(?!\d)")
_QUARTER = re.compile(r"\b(Q[1-4])\s*[-/ ]?\s*(20[0-4]\d)\b", re.IGNORECASE)


def reporting_period(title: str) -> str | None:
    """The period a document's title names (a quarter, a year or a range of years); None
    when the title names none (it is then 'not stated', never guessed)."""
    q = _QUARTER.search(title or "")
    if q:
        return f"{q.group(2)} {q.group(1).upper()}"
    years = sorted({int(y) for y in _YEAR.findall(title or "")})
    if not years:
        return None
    return str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"


def digest(text: str) -> str:
    normal = re.sub(r"\s+", " ", text or "").strip()
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()


@dataclass
class Document:
    url: str
    depth: int
    status: str  # ok, or why it was not retrieved
    host: str
    source_class: str
    publisher: str | None
    retriever: str
    final_url: str | None = None
    title: str | None = None
    published: date | None = None
    reporting_period: str | None = None
    content_type: str | None = None
    pages: int | None = None
    credits: int = 0
    sha256: str | None = None
    excerpt: str | None = None
    links: list[str] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class Retriever:
    """Retrieves candidates in order within the limits; ``cancelled`` is asked between
    documents, so a stopped study ends after the current one."""

    def __init__(
        self,
        limits: Limits,
        terms: list[str],
        *,
        cancelled: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        robots_cache: robots.RobotsCache | None = None,
    ) -> None:
        self.limits = limits
        self.terms = terms
        self.cancelled = cancelled
        self.clock = clock
        self.sleep = sleep
        self.robots = robots_cache or robots.RobotsCache(
            timeout=get_settings().research_timeout_seconds
        )
        self.client = firecrawl.client()
        self.last_request: dict[str, float] = {}
        self.credits = 0
        self.stopped: str | None = None  # why retrieval stopped early

    def run(self, candidates: list[dict[str, Any]]) -> list[Document]:
        deadline = self.clock() + self.limits.max_runtime_seconds
        queue = order([{**c, "depth": int(c.get("depth", 0))} for c in candidates])
        seen: set[str] = set()
        out: list[Document] = []
        retrieved = 0
        while queue:
            c = queue.pop(0)
            url = urldefrag(str(c["url"]).strip())[0]
            if url in seen:
                continue
            seen.add(url)
            if self.cancelled():
                self.stopped = "cancelled"
                break
            if retrieved >= self.limits.max_pages:
                self.stopped = "page_limit"
                break
            if self.clock() >= deadline:
                self.stopped = "runtime_limit"
                break
            if self.credits + 1 > self.limits.max_credits:
                self.stopped = "credit_limit"
                break
            doc = self._one(url, c["depth"])
            out.append(doc)
            if doc.status == "ok":
                retrieved += 1
                if c["depth"] < self.limits.max_depth:
                    queue += [{"url": link, "depth": c["depth"] + 1} for link in doc.links
                              if host_allowed(link, self.limits.hosts)]  # fmt: skip
                    queue = order(queue)
        return out

    # -------------------------------------------------------------- one document
    def _base(self, url: str, depth: int, status: str) -> Document:
        info = classify(url)
        return Document(
            url=url, depth=depth, status=status, host=str(info["host"]),
            source_class=str(info["source_class"]), publisher=info["publisher"]["en"],  # type: ignore[index]
            retriever="firecrawl" if self.client else "direct",
        )  # fmt: skip

    def _one(self, url: str, depth: int) -> Document:
        if not host_allowed(url, self.limits.hosts):
            return self._base(url, depth, "outside_scope")
        try:
            safe_fetch.check_url(url)
        except safe_fetch.FetchBlocked as exc:
            return self._base(url, depth, f"blocked_{exc}"[:40])
        except safe_fetch.FetchFailed as exc:
            return self._base(url, depth, str(exc)[:40])
        rules = self.robots.rules(url)
        if not rules.allows(url):
            return self._base(
                url, depth, "robots_disallowed" if rules.status == "ok" else "robots_unavailable"
            )
        self._wait(url, rules.crawl_delay)
        doc = self._retrieve(url, depth)
        if doc.status in TRANSIENT:
            self.sleep(min(5.0, max(1.0, self.limits.host_interval_seconds)))
            self._wait(url, rules.crawl_delay)
            doc = self._retrieve(url, depth)
        return doc

    def _wait(self, url: str, crawl_delay: float | None) -> None:
        host = (urlsplit(url).hostname or "").lower()
        interval = max(self.limits.host_interval_seconds, crawl_delay or 0.0)
        last = self.last_request.get(host)
        if last is not None:
            pause = interval - (self.clock() - last)
            if pause > 0:
                self.sleep(pause)
        self.last_request[host] = self.clock()

    def _retrieve(self, url: str, depth: int) -> Document:
        doc = self._base(url, depth, "ok")
        if self.client is not None:
            try:
                page = self.client.scrape(
                    url, max_pdf_pages=self.limits.max_pdf_pages,
                    with_links=depth < self.limits.max_depth,
                )  # fmt: skip
            except firecrawl.FirecrawlError as exc:
                doc.status = str(exc)[:40]
                return doc
            except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed) as exc:
                doc.status = f"blocked_{exc}"[:40]
                return doc
            self.credits += page.credits
            doc.credits = page.credits
            doc.final_url = page.final_url
            doc.title = page.title or None
            doc.content_type = page.content_type
            doc.pages = page.pages
            text = page.markdown
            doc.links = [urljoin(page.final_url, x) for x in page.links]
        else:
            try:
                fetched = safe_fetch.fetch(
                    url, timeout=get_settings().research_timeout_seconds,
                    max_bytes=get_settings().research_fetch_max_bytes,
                )  # fmt: skip
            except safe_fetch.FetchBlocked as exc:
                doc.status = f"blocked_{exc}"[:40]
                return doc
            except safe_fetch.FetchFailed as exc:
                doc.status = str(exc)[:40]
                return doc
            self.credits += 1  # one request (no paid service is used)
            doc.final_url = fetched.url
            doc.content_type = fetched.content_type.split(";")[0] or None
            if fetched.content_type.startswith("application/pdf"):
                try:
                    page_doc = pages.extract_pdf(fetched.raw, max_pages=self.limits.max_pdf_pages)
                except pages.PdfUnavailable:
                    doc.status = "pdf_reader_missing"
                    return doc
                except Exception:  # noqa: BLE001 - a malformed PDF is reported, not raised
                    doc.status = "pdf_unreadable"
                    return doc
            else:
                page_doc = pages.extract(fetched.text)
                doc.links = [urljoin(fetched.url, h) for h in _hrefs(fetched.text)]
            doc.title = page_doc.title or None
            if page_doc.published:
                doc.published = date.fromisoformat(page_doc.published)
            text = page_doc.text
        if not text.strip():
            doc.status = "empty"
            return doc
        doc.sha256 = digest(text)
        doc.excerpt = pages.relevant_passages(text, self.terms, limit=EXCERPT_CHARS)
        doc.reporting_period = reporting_period(doc.title or "")
        return doc


_HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.IGNORECASE)


def _hrefs(html: str) -> list[str]:
    return [h for h in _HREF.findall(html or "")[:400] if h.lower().startswith(("http", "/"))]
