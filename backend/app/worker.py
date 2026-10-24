"""The sync worker: runs the official-statistics checks that are due, outside the web server.

    python -m app.worker                                # every minute, the feeds that are due
    python -m app.worker --once                         # one pass (cron, Windows Task Scheduler)
    python -m app.worker --check ncsi-monthly-bulletin  # one feed now, whatever its schedule

It uses OSRIP_DATABASE_URL; for the local development cluster run
``python scripts/sync_worker_dev.py`` instead (same options). The database it connects to is
logged first, without the password.

A feed is due when an administrator switched it on and its next check time has passed (a
daily check by default). Several workers can run: each feed is checked under a PostgreSQL
advisory lock, so no feed is processed twice at the same time. A failure is logged and
retried later with backoff; it never removes or replaces published data.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.session import session_factory
from app.services.sync import service

log = logging.getLogger("osrip.worker")


def run_due() -> int:
    session = session_factory()()
    try:
        codes = service.due_feeds(session)
        for code in codes:
            try:
                result = service.run_check(session, code, trigger="schedule")
                log.info("%s: %s %s", code, result["status"], result.get("message") or "")
            except Exception:  # noqa: BLE001 - one feed's failure must not stop the others
                log.exception("%s: the check failed", code)
        return len(codes)
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.worker", description=__doc__.split("\n")[0]
    )
    parser.add_argument("--once", action="store_true", help="run the due checks once and exit")
    parser.add_argument("--check", metavar="FEED", help="check one feed now and print the result")
    parser.add_argument("--interval", type=float, default=60.0, help="seconds between passes")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    database = make_url(get_settings().database_url)
    log.info("database %s:%s/%s", database.host, database.port, database.database)
    if args.check:
        session = session_factory()()
        try:
            print(json.dumps(service.run_check(session, args.check, trigger="manual"), indent=2))
        finally:
            session.close()
        return 0
    if args.once:
        log.info("checked %d due feed(s)", run_due())
        return 0
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log.info("sync worker started; checking due feeds every %.0f s", args.interval)
    while not stop.is_set():
        try:
            run_due()
        except Exception:  # noqa: BLE001 - e.g. the database is restarting; try again next pass
            log.exception("the pass failed")
        stop.wait(args.interval)
    log.info("sync worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
