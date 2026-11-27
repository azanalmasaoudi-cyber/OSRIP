#!/usr/bin/env python3
"""Read-only check of a public OSRIP address: is the whole platform really online?

    python tools/check_public_osrip.py https://osrip.example.org

It needs no secrets and changes nothing. PASS needs all of:
  * the interface: HTTPS answers 200 with the OSRIP page;
  * the API: /api/v1/health/ready answers 200 from OSRIP's own API (its X-OSRIP-API header)
    with ready=true, i.e. the database is reachable and the migrations are current;
  * HTTPS hardening: Strict-Transport-Security on the page.
A static host alone (for example the interface on Vercel with no API behind it) fails, and the
report says why. Sign-in, the sectors, the map and Al Mulhim still need testing by hand from two
devices outside the server's network (docs/CENTRAL_HOSTING_EN.md).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlparse

Response = tuple[int, dict[str, str], bytes]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}  # noqa: S104 - hosts refused, not bound


def fetch(url: str) -> Response:
    """GET (urllib follows redirects, e.g. HTTP to HTTPS); an HTTP error is a response too."""
    req = urllib.request.Request(url, headers={"User-Agent": "OSRIP public readiness check/1.1"})  # noqa: S310
    try:
        # Only https:// addresses reach here (base_url).
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read(200_000)
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read(20_000)


def base_url(raw: str) -> str | None:
    """https://host[:port] of a real public address, or None (local, plain HTTP, credentials)."""
    u = urlparse(raw.strip())
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or host in LOCAL_HOSTS or host.endswith(".localhost"):
        return None
    if u.username or u.password:
        return None
    return f"https://{host}" + (f":{u.port}" if u.port else "")


def check(base: str, get: Callable[[str], Response] = fetch) -> tuple[list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []
    try:
        status, headers, body = get(base + "/")
        if status == 200 and b"<title>osrip" in body.lower():
            passed.append("The interface answers over HTTPS with the OSRIP page.")
        else:
            failed.append(f"The interface did not answer with the OSRIP page (HTTP {status}).")
        if "strict-transport-security" in headers:
            passed.append("HSTS is sent.")
        else:
            failed.append("No Strict-Transport-Security header on the page.")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        failed.append(f"The interface is unreachable ({type(exc).__name__}).")
    try:
        status, headers, body = get(base + "/api/v1/health/ready")
        if "x-osrip-api" not in headers:
            server = f" ({headers['server']})" if "server" in headers else ""
            failed.append(
                f"No OSRIP API behind this address: /api/v1/health/ready answered HTTP {status} "
                f"without OSRIP's X-OSRIP-API header{server}."
            )
        else:
            try:
                ready = json.loads(body).get("ready") is True
            except (ValueError, AttributeError):
                ready = False
            if status == 200 and ready:
                passed.append("The API is ready: database reachable and migrations current.")
            else:
                failed.append(f"The OSRIP API answers but is not ready (HTTP {status}).")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        failed.append(f"The API is unreachable ({type(exc).__name__}).")
    return passed, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("url", help="the public HTTPS address, e.g. https://osrip.example.org")
    args = parser.parse_args(argv)
    base = base_url(args.url)
    if base is None:
        print(
            "FAIL: give a real public https:// address (not localhost, no user name or password)."
        )
        return 2
    print(f"Checking {base} (read only) ...")
    passed, failed = check(base)
    for line in passed:
        print("PASS:", line)
    for line in failed:
        print("FAIL:", line)
    if failed:
        print("Not deployed as a whole platform: do not announce this address yet.")
        return 1
    print("Interface and API are online. Test sign-in, sectors, map and Al Mulhim by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
