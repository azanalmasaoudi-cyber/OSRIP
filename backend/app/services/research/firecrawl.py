"""Firecrawl page retrieval for background studies (API v2, from the official reference:
https://docs.firecrawl.dev/api-reference/endpoint/scrape and .../endpoint/map).

* ``POST {base}/v2/scrape`` with ``Authorization: Bearer <key>``: one page as Markdown with
  its metadata (title, the requested ``sourceURL``, the final ``url`` after redirects,
  ``statusCode``, ``contentType``, ``numPages`` and ``totalPages`` for PDFs). PDFs are parsed
  by the ``pdf`` parser with ``maxPages`` (billed per page); image OCR is not requested.
  TLS certificates are verified (``skipTlsVerification: false``); only the main content is
  kept; Firecrawl's own cache may answer for up to a day (``maxAge``).
* ``POST {base}/v2/map``: addresses on one official site, ordered by a search phrase.

The key stays on the server. Before an address is sent, OSRIP checks it (scheme, public
address, robots.txt) itself; after the reply, the final address is checked again, and a page
that ended on a private or non-public address is discarded. Retrieved text is untrusted: it is
returned as data for the study's evidence, never followed as instructions. Every call is
metered (``provider_call``, capability ``retrieve``, with its credits) and stopped by the
daily limits. No live call is made by the tests: they use a mock transport.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings
from app.services import monitoring
from app.services import providers as registry
from app.services.research import safe_fetch

PROVIDER = "firecrawl"


class FirecrawlError(Exception):
    """The retrieval failed; the code (str) is reported: timeout, network, http_402 (no
    credits), http_429 (rate limited), invalid_json, blocked_redirect, daily_limit ..."""


@dataclass(frozen=True)
class Scraped:
    url: str  # the address asked for
    final_url: str  # after redirects
    status_code: int | None
    content_type: str | None
    title: str
    markdown: str
    links: list[str] = field(default_factory=list)
    pages: int | None = None  # PDF pages parsed
    total_pages: int | None = None  # PDF page count (more than ``pages``: truncated)
    credits: int = 1  # estimated from the documented pricing: 1 per page, + 1 per PDF page


# Injectable for tests (httpx.MockTransport).
http_client_factory: Callable[[float], httpx.Client] = lambda timeout: httpx.Client(  # noqa: E731
    timeout=timeout, trust_env=False
)


def configured() -> bool:
    return bool(get_settings().firecrawl_api_key)


class Firecrawl:
    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _post(self, path: str, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        try:
            registry.check(PROVIDER, "retrieve", None)
        except registry.LimitReached as exc:
            raise FirecrawlError(str(exc)) from exc
        started = time.monotonic()
        try:
            with http_client_factory(self._timeout) as client:
                response = client.post(
                    f"{self._base}{path}",
                    json=body,
                    headers={"Authorization": f"Bearer {self._key}",
                             "Content-Type": "application/json"},
                )  # fmt: skip
        except httpx.TimeoutException as exc:
            self._failed("timeout", started)
            raise FirecrawlError("timeout") from exc
        except httpx.HTTPError as exc:
            self._failed("network", started)
            raise FirecrawlError("network") from exc
        if response.status_code != 200:
            code = f"http_{response.status_code}"
            self._failed(code, started)
            raise FirecrawlError(code)
        try:
            data = response.json()
        except ValueError as exc:
            self._failed("invalid_json", started)
            raise FirecrawlError("invalid_json") from exc
        if not isinstance(data, dict) or data.get("success") is False:
            self._failed("invalid_response", started)
            raise FirecrawlError("invalid_response")
        return data, started

    def _failed(self, code: str, started: float) -> None:
        monitoring.external_failure("research", code)
        registry.record(PROVIDER, "retrieve", None, code, started)

    def scrape(self, url: str, *, max_pdf_pages: int, with_links: bool = False) -> Scraped:
        target = safe_fetch.check_url(url)  # never send a private or malformed address
        formats: list[Any] = ["markdown", "links"] if with_links else ["markdown"]
        body = {
            "url": target.url,
            "formats": formats,
            "onlyMainContent": True,
            "parsers": [{"type": "pdf", "maxPages": max(1, min(max_pdf_pages, 10000))}],
            "skipTlsVerification": False,
            "removeBase64Images": True,
            "blockAds": True,
            "maxAge": 86_400_000,  # one day
            "timeout": int(min(self._timeout, 300) * 1000),
        }
        data, started = self._post("/v2/scrape", body)
        page = data.get("data") if isinstance(data.get("data"), dict) else {}
        meta = page.get("metadata") if isinstance(page.get("metadata"), dict) else {}
        final = str(meta.get("url") or meta.get("sourceURL") or target.url)
        pages = _int(meta.get("numPages"))
        credits = 1 + (pages or 0)
        registry.record(PROVIDER, "retrieve", None, "ok", started, credits=credits)
        monitoring.external_success("research")
        try:
            safe_fetch.check_url(final)
        except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed) as exc:
            raise FirecrawlError("blocked_redirect") from exc
        links = [str(x) for x in page.get("links") or [] if isinstance(x, str)]
        return Scraped(
            url=target.url,
            final_url=final,
            status_code=_int(meta.get("statusCode")),
            content_type=str(meta.get("contentType") or "") or None,
            title=str(meta.get("title") or "")[:300],
            markdown=str(page.get("markdown") or ""),
            links=links[:200],
            pages=pages,
            total_pages=_int(meta.get("totalPages")),
            credits=credits,
        )

    def map(self, site: str, *, search: str, limit: int) -> list[dict[str, str]]:
        target = safe_fetch.check_url(site)
        data, started = self._post(
            "/v2/map",
            {"url": target.url, "search": search[:200], "limit": max(1, min(limit, 100)),
             "includeSubdomains": True, "ignoreQueryParameters": True,
             "timeout": int(min(self._timeout, 120) * 1000)},
        )  # fmt: skip
        registry.record(PROVIDER, "retrieve", None, "ok", started, credits=1)
        monitoring.external_success("research")
        out = []
        for link in data.get("links") or []:
            if isinstance(link, dict) and isinstance(link.get("url"), str):
                out.append({"url": link["url"], "title": str(link.get("title") or "")[:300]})
            elif isinstance(link, str):  # older responses list plain addresses
                out.append({"url": link, "title": ""})
        return out[:limit]


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def client() -> Firecrawl | None:
    """The configured client, or None (studies then retrieve pages directly, or not at all)."""
    s = get_settings()
    if not s.firecrawl_api_key:
        return None
    return Firecrawl(
        s.firecrawl_api_key.get_secret_value(), s.firecrawl_base_url, s.firecrawl_timeout_seconds
    )
