"""Run the OSRIP command line against the local development database.

    backend\\.venv\\Scripts\\python.exe scripts\\dev_cli.py ensure-admin --username Azzan
    backend\\.venv\\Scripts\\python.exe scripts\\dev_cli.py ensure-user --username someone

The same as ``python -m app.cli ...``, but pointed at ``osrip_dev`` on the cluster managed by
scripts/devdb.py, as scripts/serve_dev.py and tools/start_osrip.py do (the default database
setting is for a server install). An OSRIP_DATABASE_URL already set is kept. The dev cluster must
be running (start it with tools/start_osrip.py or ``scripts/devdb.py start``). Passwords are
typed at a hidden prompt by the commands themselves; nothing is printed or stored here.
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

from app.cli import main  # noqa: E402

if __name__ == "__main__":
    main(sys.argv[1:])
