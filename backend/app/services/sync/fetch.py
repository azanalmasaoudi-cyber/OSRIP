"""HTTPS requests to the official statistics hosts the registry names, and nowhere else.

* only ``https`` to an allowed host; certificates are verified; redirects are followed by
  hand and only to an allowed host;
* responses are size-limited and their content type checked;
* bounded retries with exponential backoff on network errors, 429 and 5xx (a
  ``Retry-After`` the server sends is respected up to a limit); other statuses fail at once;
* every attempt is counted so the synchronisation log can show it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "OSRIP-source-sync/1.0 (academic decision-support prototype; daily check)"
MAX_REDIRECTS = 3
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER = 60.0

# Injectable for tests: a client factory and the sleep used between attempts.
client_factory: Callable[[float], httpx.Client] = lambda timeout: httpx.Client(  # noqa: E731
    timeout=timeout, follow_redirects=False, trust_env=False, verify=True
)
sleep: Callable[[float], None] = time.sleep


class FetchError(Exception):
    """The resource could not be retrieved; ``status`` is the last HTTP status, if any."""

    def __init__(self, reason: str, *, status: int | None = None, attempts: int = 1) -> None:
        super().__init__(reason)
        self.reason, self.status, self.attempts = reason, status, attempts


@dataclass(frozen=True, slots=True)
class Fetched:
    url: str
    status: int
    content_type: str
    body: bytes
    attempts: int


def _allowed(url: str, hosts: frozenset[str]) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise FetchError("https_required")
    if (parts.hostname or "").lower() not in hosts or parts.port not in (None, 443):
        raise FetchError("host_not_allowed")
    if parts.username or parts.password:
        raise FetchError("credentials_in_url")


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return min(MAX_RETRY_AFTER, max(0.0, float(value)))
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError):
            return None
        return min(MAX_RETRY_AFTER, max(0.0, delay))


def get(
    url: str,
    *,
    hosts: frozenset[str],
    accept: tuple[str, ...],
    max_bytes: int,
    timeout: float = 20.0,
    attempts: int = 3,
    backoff: float = 2.0,
) -> Fetched:
    """GET with redirects checked, size and type limits, and bounded retries."""
    last: FetchError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _once(
                url,
                hosts=hosts,
                accept=accept,
                max_bytes=max_bytes,
                timeout=timeout,
                attempt=attempt,
            )
        except FetchError as exc:
            exc.attempts = attempt
            last = exc
            retryable = exc.reason in ("network_error", "timeout") or (exc.status in RETRY_STATUSES)
            if not retryable or attempt == attempts:
                raise
            delay = getattr(exc, "retry_after", None)
            sleep(delay if delay is not None else backoff * (2 ** (attempt - 1)))
    assert last is not None
    raise last


def _once(
    url: str,
    *,
    hosts: frozenset[str],
    accept: tuple[str, ...],
    max_bytes: int,
    timeout: float,
    attempt: int,
) -> Fetched:
    current = url
    with client_factory(timeout) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _allowed(current, hosts)
            try:
                with client.stream(
                    "GET", current, headers={"User-Agent": USER_AGENT, "Accept": ", ".join(accept)}
                ) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        location = r.headers.get("location")
                        if not location:
                            raise FetchError("redirect_without_location", status=r.status_code)
                        current = urljoin(current, location)
                        continue
                    if r.status_code != 200:
                        error = FetchError(f"http_{r.status_code}", status=r.status_code)
                        error.retry_after = _retry_after(r)  # type: ignore[attr-defined]
                        raise error
                    content_type = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    if accept and content_type not in accept:
                        raise FetchError("unexpected_content_type", status=200)
                    chunks, size = [], 0
                    for chunk in r.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise FetchError("too_large", status=200)
                        chunks.append(chunk)
                    return Fetched(current, 200, content_type, b"".join(chunks), attempt)
            except httpx.TimeoutException as exc:
                raise FetchError("timeout") from exc
            except httpx.HTTPError as exc:
                raise FetchError("network_error") from exc
    raise FetchError("too_many_redirects")
