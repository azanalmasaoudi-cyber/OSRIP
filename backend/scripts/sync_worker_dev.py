"""Run the official-statistics sync worker for local development (the portable dev cluster).

    python scripts/sync_worker_dev.py            # every minute, the feeds that are due
    python scripts/sync_worker_dev.py --once     # one pass

Uses the database ``osrip_dev`` managed by scripts/devdb.py unless OSRIP_DATABASE_URL is set.
A feed is checked only after an administrator switches its schedule on (Data Management).
In production run ``python -m app.worker`` as its own service, next to the API.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
os.chdir(BACKEND)

from devdb import admin_url  # noqa: E402

os.environ.setdefault("OSRIP_DATABASE_URL", admin_url("osrip_dev"))

from app.worker import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
