"""Run the API for local development against the portable dev cluster.

Uses the database `osrip_dev` on the cluster managed by scripts/devdb.py (it
must already be migrated and seeded: `alembic upgrade head`, then
`python -m app.cli seed-synthetic`). Plain-HTTP localhost only, so Secure
cookies are switched off here and nowhere else. Port: PORT or 8010 (the Vite proxy default).
If an OSRIP API already answers on that port, nothing is started; if another program holds
it, the next free port is used.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
os.chdir(BACKEND)

from devdb import admin_url  # noqa: E402

os.environ.setdefault("OSRIP_DATABASE_URL", admin_url("osrip_dev"))
os.environ.setdefault("OSRIP_SESSION_COOKIE_SECURE", "false")
# Development: scripted SMS delivery, labelled "test mode" in the interface; codes are
# shown at /dev/mail. Set OSRIP_SMS_ENABLED=false to see the "unavailable" path.
os.environ.setdefault("OSRIP_SMS_ENABLED", "true")
os.environ.setdefault("OSRIP_SMS_PROVIDER", "test")
# --fake-assistant: the scripted test provider (labelled; refused in production) for
# interface work without a model account. It answers "generation" questions only.
if "--fake-assistant" in sys.argv:
    os.environ.setdefault("OSRIP_ASSISTANT_PROVIDER", "fake")

import uvicorn  # noqa: E402


def port_in_use(port: int) -> bool:
    """Something listens on 127.0.0.1:port, or Windows refuses to bind it."""
    # connect_ex reports a listener without raising, so a debugger set to break on raised
    # exceptions does not stop here whenever the port is busy.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            return True
    # Nobody listens, but the port may be in a reserved range (Hyper-V, WSL). No SO_REUSEADDR:
    # on Windows it lets bind() succeed on a port another program is already listening on.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def osrip_api_on(port: int) -> bool:
    """An OSRIP API answers on localhost:port (the same test as tools/start_osrip.py)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/v1/health/ready", timeout=2) as response:
            text = response.read()
    except urllib.error.HTTPError as error:  # 503 while not ready is still OSRIP
        text = error.read()
    except OSError:
        return False
    try:
        body = json.loads(text)
    except ValueError:
        return False
    return isinstance(body, dict) and "release" in body and "checks" in body


def free_port_after(port: int) -> int:
    for candidate in range(port + 1, port + 100):
        if not port_in_use(candidate):
            return candidate
    raise RuntimeError(f"No free localhost port found in range {port + 1}-{port + 99}")


port = int(os.environ.get("PORT", "8010"))
if port_in_use(port):
    if osrip_api_on(port):
        # A second copy on another port would not be reached by the interface (its /api
        # proxy keeps using this one), so breakpoints set here would never be hit.
        print(
            f"An OSRIP API is already running on http://127.0.0.1:{port}/ "
            "(started by tools/start_osrip.py, Visual Studio or another serve_dev.py).\n"
            "Not starting a second one. To run or debug the API here, stop that one first "
            "(Stop Debugging in Visual Studio, or Ctrl+C in its window), then start this again.",
            file=sys.stderr,
        )
        sys.exit(0)
    busy, port = port, free_port_after(port)
    print(
        f"Port {busy} is used by another program; starting the API on http://127.0.0.1:{port}/.\n"
        f"Point the interface at it before npm run dev: $env:OSRIP_API_ORIGIN='http://127.0.0.1:{port}'",
        file=sys.stderr,
    )
    os.environ["PORT"] = str(port)

uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="info")
