"""Reading a source document for research, and the persistent record of what was read.

Two routes (``OSRIP_RESEARCH_FETCH_PROVIDER``):
* ``direct``: OSRIP's SSRF-safe fetcher (``safe_fetch``), HTML and PDF;
* ``deepseek``: the DeepSeek Fetch API (``POST https://api.deepseek.com/v1/tools/fetch``,
  ``{"url"}`` -> ``{"title", "content"}`` as Markdown; 403 refused by DeepSeek's security policy,
  404 no usable content, 429 rate limit, 504 the target site timed out; checked 2026-10-25),
  with the direct fetcher when it fails. Hosts in ``OSRIP_RESEARCH_FETCH_DIRECT_HOSTS`` are read
  directly first: on 2026-10-25 DeepSeek Fetch timed out on ncsi.gov.om and data.gov.om while
  the direct fetcher read both at once.
Whatever the route, the address is checked by ``safe_fetch.check_url`` first (http(s) on the
default port, no credentials, public addresses only), so a page can never make the server
reach an internal address. DeepSeek's Markdown escapes punctuation ("2020\\,", "4\\.5"); the
escapes are removed so a figure reads as it does on the page.

NCSI's news pages (``ncsi.gov.om/{ar,en}/newsPage/newsDetail?id=N``) are rendered in the
browser from NCSI's own public API, so a read of the page returns an empty shell ("loading").
For those pages the article is read from that API (``GET https://api.ncsi.gov.om/V1/news/view/N``:
English and Arabic title and text and the news date; checked 2026-10-25), and the document keeps
the page's address, which is what a reader opens.

Every read is stored in ``research_document`` (address, final address, publisher, source
class, title, the date the document states, the route, the digest and the bounded text), so a
saved figure can be checked against its document again later. The same address read
successfully within ``OSRIP_RESEARCH_CACHE_HOURS`` is served from that record (and says so).
The text is untrusted evidence: never instructions, and never added to the data here.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select

from app.core.config import get_settings
from app.services import monitoring
from app.services import providers as registry
from app.services.research import crawl, pages, safe_fetch, sources

log = logging.getLogger("osrip.research")

DEEPSEEK_FETCH_URL = "https://api.deepseek.com/v1/tools/fetch"
NCSI_NEWS_PAGE = re.compile(
    r"^https?://(?:www\.)?ncsi\.gov\.om/(?:ar|en)/newsPage/newsDetail\?id=(\d{1,7})$"
)
NCSI_NEWS_API = "https://api.ncsi.gov.om/V1/news/view/{id}"
MAX_TEXT = 300_000
MAX_EXCERPT = 20_000
_ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!,%|<>~\"'&:;=?@^$/])")
# Injectable for tests (httpx.MockTransport).
http_client_factory: Any = lambda timeout: httpx.Client(timeout=timeout)  # noqa: E731
# The record and cache in research_document; unit tests without a database switch it off.
persist = True


@dataclass(slots=True)
class Read:
    status: str  # ok | blocked | failed | pdf_unsupported | pdf_no_text
    url: str
    final_url: str
    title: str = ""
    text: str = ""
    published: str | None = None  # ISO date the document states, when it states one
    content_type: str = ""
    is_pdf: bool = False
    retriever: str = "direct"  # direct | deepseek | fake
    retrieved_at: datetime | None = None
    sha256: str | None = None
    truncated: bool = False
    reason: str | None = None
    cached: bool = False
    document_id: uuid.UUID | None = None


def unescape_markdown(text: str) -> str:
    return _ESCAPED.sub(r"\1", text)


def _direct_first(host: str) -> bool:
    suffixes = [h.strip().lower() for h in get_settings().research_fetch_direct_hosts.split(",")]
    return any(h and (host == h or host.endswith("." + h)) for h in suffixes)


def _deepseek(url: str) -> Read:
    s = get_settings()
    assert s.deepseek_api_key is not None
    try:
        safe_fetch.check_url(url)  # the same address rules as the direct fetcher
    except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed) as exc:
        return Read("blocked", url, url, retriever="deepseek", reason=str(exc))
    if registry.calls_today("deepseek", "retrieve") >= s.research_daily_fetch_limit:
        return Read("failed", url, url, retriever="deepseek", reason="daily_limit")
    try:
        registry.check("deepseek", "retrieve", "fetch-api")
    except registry.LimitReached as exc:
        return Read("failed", url, url, retriever="deepseek", reason=str(exc))
    started = time.monotonic()
    code = "ok"
    try:
        with http_client_factory(s.research_fetch_timeout_seconds) as client:
            response = client.post(
                DEEPSEEK_FETCH_URL,
                json={"url": url},
                headers={
                    "Authorization": f"Bearer {s.deepseek_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code != 200:
            code = f"http_{response.status_code}"
        else:
            body = response.json()
    except httpx.TimeoutException:
        code = "timeout"
    except (httpx.HTTPError, ValueError):
        code = "network"
    if code != "ok":
        monitoring.external_failure("research", code)
        registry.record("deepseek", "retrieve", "fetch-api", code, started)
        return Read("failed", url, url, retriever="deepseek", reason=code)
    content = unescape_markdown(str(body.get("content") or ""))
    ok = bool(content.strip())
    registry.record(
        "deepseek", "retrieve", "fetch-api", "ok" if ok else "empty", started,
        credits=1 if ok else None,
    )  # fmt: skip
    monitoring.external_success("research")
    if not ok:
        return Read("failed", url, url, retriever="deepseek", reason="no_content")
    raw = content.encode("utf-8")
    return Read(
        "ok",
        url,
        url,
        title=unescape_markdown(str(body.get("title") or ""))[:300],
        text=content[:MAX_TEXT],
        published=None,
        content_type="text/markdown",
        retriever="deepseek",
        retrieved_at=datetime.now(UTC),
        sha256=hashlib.sha256(raw).hexdigest(),
        truncated=len(content) > MAX_TEXT,
    )


def _direct(url: str) -> Read:
    s = get_settings()
    try:
        fetched = safe_fetch.fetch(
            url, timeout=s.research_timeout_seconds, max_bytes=s.research_fetch_max_bytes
        )
    except safe_fetch.FetchBlocked as exc:
        return Read("blocked", url, url, reason=str(exc))
    except safe_fetch.FetchFailed as exc:
        return Read("failed", url, url, reason=str(exc))
    retrieved = datetime.now(UTC)
    sha = hashlib.sha256(fetched.raw).hexdigest()
    is_pdf = "pdf" in fetched.content_type or fetched.raw[:5] == b"%PDF-"
    if is_pdf:
        try:
            page = pages.extract_pdf(fetched.raw, max_chars=MAX_TEXT)
        except pages.PdfUnavailable:
            return Read("pdf_unsupported", url, fetched.url, is_pdf=True, reason="pypdf_missing")
        except Exception:  # noqa: BLE001 - a damaged or encrypted PDF
            return Read("failed", url, fetched.url, is_pdf=True, reason="pdf_unreadable")
        if not re.sub(r"\[page \d+\]", "", page.text).strip():
            return Read("pdf_no_text", url, fetched.url, is_pdf=True, reason="no_text_layer")
    elif "html" in fetched.content_type or fetched.text.lstrip().startswith("<"):
        page = pages.extract(fetched.text, max_chars=MAX_TEXT)
    else:
        page = pages.Page(title="", text=fetched.text[:MAX_TEXT])
    return Read(
        "ok",
        url,
        fetched.url,
        title=page.title,
        text=page.text,
        published=page.published,
        content_type=fetched.content_type,
        is_pdf=is_pdf,
        retriever="direct",
        retrieved_at=retrieved,
        sha256=sha,
        truncated=fetched.truncated,
    )


def _ncsi_news(url: str, news_id: str) -> Read:
    """An NCSI news article from NCSI's own API (the page itself only renders it)."""
    import json

    s = get_settings()
    try:
        fetched = safe_fetch.fetch(
            NCSI_NEWS_API.format(id=news_id),
            timeout=s.research_timeout_seconds,
            max_bytes=s.research_fetch_max_bytes,
            types=("application/json",),
        )
        news = (json.loads(fetched.text).get("data") or {}).get("news") or {}
    except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed, ValueError, AttributeError) as exc:
        return Read("failed", url, url, reason=f"ncsi_news_api:{type(exc).__name__}")
    if not isinstance(news, dict) or not (news.get("content_en") or news.get("content_ar")):
        return Read("failed", url, url, reason="ncsi_news_api:no_content")

    def plain(value: object) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        return re.sub(r"[ \t\u00a0]+", " ", text).strip()

    parts = [
        plain(news.get("title_en")),
        plain(news.get("content_en")),
        plain(news.get("title_ar")),
        plain(news.get("content_ar")),
    ]
    text = "\n\n".join(p for p in parts if p)[:MAX_TEXT]
    return Read(
        "ok",
        url,
        url,
        title=plain(news.get("title_en") or news.get("title_ar"))[:300],
        text=text,
        published=pages.first_iso_date(str(news.get("news_date") or "")),
        content_type="application/json",
        retriever="direct",
        retrieved_at=datetime.now(UTC),
        sha256=hashlib.sha256(fetched.raw).hexdigest(),
    )


def _cached(url: str) -> Read | None:
    from app.db.session import session_factory
    from app.models import ResearchDocument

    since = datetime.now(UTC) - timedelta(hours=get_settings().research_cache_hours)
    try:
        with session_factory()() as s, s.begin():
            row = s.scalar(
                select(ResearchDocument)
                .where(
                    ResearchDocument.url == url[:2048],
                    ResearchDocument.status == "ok",
                    ResearchDocument.text_content.is_not(None),
                    # A near-empty read (a page drawn by scripts) is not worth reusing.
                    func.length(ResearchDocument.text_content) >= 400,
                    ResearchDocument.retrieved_at >= since,
                )
                .order_by(ResearchDocument.retrieved_at.desc())
                .limit(1)
            )
            if row is None:
                return None
            return Read(
                "ok",
                row.url,
                row.final_url or row.url,
                title=row.title or "",
                text=row.text_content or "",
                published=row.published.isoformat() if row.published else None,
                content_type=row.content_type or "",
                is_pdf="pdf" in (row.content_type or ""),
                retriever=row.retriever,
                retrieved_at=row.retrieved_at,
                sha256=row.sha256,
                cached=True,
                document_id=row.id,
            )
    except Exception:  # noqa: BLE001 - without the database there is no cache
        return None


def _store(result: Read, job_id: uuid.UUID | None) -> uuid.UUID | None:
    from app.db.session import session_factory
    from app.models import ResearchDocument

    cls = sources.classify(result.final_url or result.url)
    published = None
    if result.published:
        try:
            published = date.fromisoformat(result.published)
        except ValueError:
            published = None
    try:
        with session_factory()() as s, s.begin():
            row = ResearchDocument(
                job_id=job_id,
                url=result.url[:2048],
                final_url=(result.final_url or None) and result.final_url[:2048],
                host=str(cls["host"])[:255],
                source_class=str(cls["source_class"]),
                publisher=(cls["publisher"] or {}).get("en") if cls["publisher"] else None,
                title=result.title or None,
                retrieved_at=result.retrieved_at or datetime.now(UTC),
                published=published,
                reporting_period=crawl.reporting_period(result.title or ""),
                content_type=(result.content_type or None) and result.content_type[:120],
                retriever=result.retriever,
                status=re.sub(r"[^a-z0-9_]", "_", result.status)[:40],
                sha256=result.sha256,
                excerpt=(result.text[:MAX_EXCERPT] or None) if result.status == "ok" else None,
                text_content=(result.text or None) if result.status == "ok" else None,
            )
            s.add(row)
            s.flush()
            return row.id
    except Exception:  # noqa: BLE001 - the record must never stop the reading
        log.exception("could not record a research document")
        return None


def read(url: str, *, job_id: uuid.UUID | None = None, use_cache: bool = True) -> Read:
    """Read one document by the configured route, record it, and return its text."""
    s = get_settings()
    deepseek_ready = (
        s.research_fetch_provider == "deepseek"
        and s.deepseek_api_key is not None
        and s.deepseek_billing_acknowledged
    )
    host = sources.host_of(url)
    pdf_like = url.lower().split("?", 1)[0].endswith(".pdf")
    news = NCSI_NEWS_PAGE.match(url)
    if news:
        result = _ncsi_news(url, news.group(1))
        result.document_id = _store(result, job_id) if persist else None
        return result
    if use_cache and persist:
        hit = _cached(url)
        if hit is not None:
            return hit
    if deepseek_ready and not _direct_first(host) and not pdf_like:
        order = (_deepseek, _direct)
    elif deepseek_ready:
        order = (_direct, _deepseek)
    else:
        order = (_direct,)
    attempts: list[str] = []
    result = Read("failed", url, url, reason="not_read")
    for route in order:
        result = route(url)
        attempts.append(f"{result.retriever}:{result.reason or result.status}")
        if result.status in ("ok", "blocked", "pdf_unsupported", "pdf_no_text"):
            break
    if result.status != "ok" and len(attempts) > 1:
        result.reason = "; ".join(attempts)[:200]
    result.document_id = _store(result, job_id) if persist else None
    return result
