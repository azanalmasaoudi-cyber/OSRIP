"""robots.txt for study retrieval (RFC 9309), checked by OSRIP itself before any page is
asked for, whether OSRIP fetches it or Firecrawl does (Firecrawl's documentation does not
state its own robots.txt handling, so it is not relied on).

* robots.txt is read through the SSRF-safe fetcher, once per host and study.
* 200: its rules apply to the agent ``OSRIP-research`` (and ``*``); a Crawl-delay is honoured
  as the minimum interval between requests to that host.
* Any other 4xx (including no robots.txt): every path may be read (RFC 9309, 2.3.1.3).
* 5xx, a network failure, an unreadable file or a blocked address: nothing on that host is
  read (RFC 9309, 2.3.1.4: the site is treated as completely disallowed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from app.services.research import safe_fetch

AGENT = "OSRIP-research"
MAX_BYTES = 512 * 1024


@dataclass
class Rules:
    status: str  # ok | missing | unreachable
    parser: RobotFileParser | None = None
    crawl_delay: float | None = None

    def allows(self, url: str) -> bool:
        if self.status == "missing":
            return True
        if self.status != "ok" or self.parser is None:
            return False
        return self.parser.can_fetch(AGENT, url)


def parse(text: str) -> Rules:
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    delay = parser.crawl_delay(AGENT)
    return Rules("ok", parser, float(delay) if delay is not None else None)


@dataclass
class RobotsCache:
    """robots.txt per scheme and host, read at most once per study."""

    timeout: float = 10.0
    hosts: dict[str, Rules] = field(default_factory=dict)

    def rules(self, url: str) -> Rules:
        parts = urlsplit(url)
        key = f"{parts.scheme.lower()}://{(parts.hostname or '').lower()}"
        if key not in self.hosts:
            self.hosts[key] = self._read(f"{key}/robots.txt")
        return self.hosts[key]

    def allows(self, url: str) -> bool:
        return self.rules(url).allows(url)

    def _read(self, robots_url: str) -> Rules:
        try:
            fetched = safe_fetch.fetch(robots_url, timeout=self.timeout, max_bytes=MAX_BYTES)
        except safe_fetch.FetchFailed as exc:
            code = str(exc)
            if code.startswith("http_4"):
                return Rules("missing")
            return Rules("unreachable")
        except safe_fetch.FetchBlocked:
            return Rules("unreachable")
        return parse(fetched.text)
