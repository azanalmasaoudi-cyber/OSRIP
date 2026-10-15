"""Fetching public web pages for the assistant without exposing the server's network.

Retrieved content is untrusted. This module only protects the network side:

* only ``http``/``https`` on the default ports, no credentials in the URL;
* the host name is resolved here and **every** address must be public (no loopback,
  private, link-local, carrier-grade NAT, multicast, reserved or unspecified ranges,
  IPv4 or IPv6, including IPv4-mapped IPv6);
* the connection goes to the checked address itself (the URL host is kept for the
  ``Host`` header and for TLS server-name verification), so a second DNS answer cannot
  redirect the request to an internal address (DNS rebinding);
* redirects are followed by hand, at most ``MAX_REDIRECTS``, each target checked the
  same way, and never from https down to http;
* response size, time and content type are limited; nothing is executed.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 3
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/pdf")
USER_AGENT = "OSRIP-research/1.0 (academic research prototype)"


class FetchBlocked(Exception):
    """The URL or one of its redirects is not allowed (reported to the model as such)."""


class FetchFailed(Exception):
    """The page could not be retrieved (network, status, type or size)."""


# Injectable for tests: (host, port) -> list of IP address strings.
def _system_resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


resolver: Callable[[str, int], list[str]] = _system_resolve
transport_factory: Callable[[], httpx.BaseTransport | None] = lambda: None  # noqa: E731


def address_is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


@dataclass(frozen=True, slots=True)
class CheckedTarget:
    url: str
    scheme: str
    host: str
    port: int
    path: str  # path plus query
    address: str


def check_url(url: str) -> CheckedTarget:
    """Validate a URL and resolve it to one public address, or raise FetchBlocked."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise FetchBlocked("invalid_url") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchBlocked("scheme_not_allowed")
    if parts.username or parts.password:
        raise FetchBlocked("credentials_in_url")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise FetchBlocked("no_host")
    default_port = 443 if scheme == "https" else 80
    try:
        port = parts.port or default_port
    except ValueError as exc:
        raise FetchBlocked("invalid_port") from exc
    if port != default_port:
        raise FetchBlocked("port_not_allowed")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")):
        raise FetchBlocked("private_host")
    try:
        addresses = [host] if _is_ip_literal(host) else resolver(host, port)
    except OSError as exc:
        raise FetchFailed("dns_failed") from exc
    if not addresses:
        raise FetchFailed("dns_failed")
    if not all(address_is_public(a) for a in addresses):
        raise FetchBlocked("private_address")
    path = parts.path or "/"
    if parts.query:
        path += f"?{parts.query}"
    return CheckedTarget(url, scheme, host, port, path, addresses[0])


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class Fetched:
    url: str  # final URL after redirects
    status: int
    content_type: str
    text: str
    truncated: bool
    raw: bytes = b""  # the body as received (PDF text is extracted from it)


def fetch(url: str, *, timeout: float, max_bytes: int) -> Fetched:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        target = check_url(current)
        response = _request(target, timeout=timeout, max_bytes=max_bytes)
        if response[0] in (301, 302, 303, 307, 308):
            location = response[3]
            if not location:
                raise FetchFailed("redirect_without_location")
            nxt = urljoin(current, location)
            if target.scheme == "https" and urlsplit(nxt).scheme.lower() == "http":
                raise FetchBlocked("https_downgrade")
            current = nxt
            continue
        status, content_type, body, _, truncated = response
        if status != 200:
            raise FetchFailed(f"http_{status}")
        charset = "utf-8"
        if "charset=" in content_type:
            charset = content_type.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            text = body.decode(charset, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        return Fetched(current, status, content_type, text, truncated, body)
    raise FetchBlocked("too_many_redirects")


def _request(
    target: CheckedTarget, *, timeout: float, max_bytes: int
) -> tuple[int, str, bytes, str | None, bool]:
    address = f"[{target.address}]" if ":" in target.address else target.address
    pinned = f"{target.scheme}://{address}{target.path}"
    host_header = target.host if target.port in (80, 443) else f"{target.host}:{target.port}"
    extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
    transport = transport_factory()
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=False, transport=transport, trust_env=False
        ) as client:
            with client.stream(
                "GET",
                pinned,
                headers={
                    "Host": host_header,
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,application/pdf;q=0.7",
                    "Accept-Language": "en,ar;q=0.8",
                },
                extensions=extensions,
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    return response.status_code, "", b"", response.headers.get("location"), False
                content_type = response.headers.get("content-type", "").lower()
                if response.status_code == 200 and not content_type.startswith(ALLOWED_TYPES):
                    raise FetchFailed("unsupported_content_type")
                chunks: list[bytes] = []
                size, truncated = 0, False
                for chunk in response.iter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= max_bytes:
                        truncated = True
                        break
                return (
                    response.status_code,
                    content_type,
                    b"".join(chunks)[:max_bytes],
                    None,
                    truncated,
                )
    except httpx.TimeoutException as exc:
        raise FetchFailed("timeout") from exc
    except httpx.HTTPError as exc:
        raise FetchFailed("network") from exc
