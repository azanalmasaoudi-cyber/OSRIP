"""Manage a local, portable PostgreSQL cluster for development and integration tests.

Usage (from backend/):  python scripts/devdb.py init|start|stop|status|url [db]|createdb [db]

The cluster lives outside the repository (and outside OneDrive) under
OSRIP_DEV_HOME (default %LOCALAPPDATA%/OSRIP-dev on Windows, ~/.osrip-dev elsewhere).
It listens on localhost only, uses SCRAM-SHA-256 password authentication, and the
generated superuser password is stored in that folder, never in the repo.
Binaries: OSRIP_PG_BIN, default <OSRIP_DEV_HOME>/pgsql/bin (official EDB zip).
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

PORT = int(os.environ.get("OSRIP_DEV_PG_PORT", "55432"))


def dev_home() -> Path:
    if os.environ.get("OSRIP_DEV_HOME"):
        return Path(os.environ["OSRIP_DEV_HOME"])
    if os.name == "nt":
        default = Path(os.environ["LOCALAPPDATA"]) / "OSRIP-dev"
        if (default / "pgdata").exists():
            return default
        # A cluster created by a packaged (MSIX) app lives in that app's virtualised
        # AppData (for example %LOCALAPPDATA%\Packages\<app>\LocalCache\Local\OSRIP-dev)
        # and is invisible to ordinary programs at the default path. Use it if it is the
        # only one, so existing data is found instead of a second cluster being created.
        found = sorted(
            Path(os.environ["LOCALAPPDATA"]).glob("Packages/*/LocalCache/Local/OSRIP-dev/pgdata")
        )
        if len(found) == 1:
            return found[0].parent
        return default
    return Path.home() / ".osrip-dev"


HOME = dev_home()
BIN = Path(os.environ.get("OSRIP_PG_BIN", HOME / "pgsql" / "bin"))
DATA = HOME / "pgdata"
PWFILE = HOME / "superuser-password.txt"
LOG = HOME / "postgres.log"


def exe(name: str) -> str:
    return str(BIN / (f"{name}.exe" if os.name == "nt" else name))


def admin_url(database: str = "postgres") -> str:
    password = PWFILE.read_text(encoding="utf-8").strip()
    return f"postgresql+psycopg://postgres:{password}@localhost:{PORT}/{database}"


def init() -> None:
    if DATA.exists():
        print(f"Cluster already initialised at {DATA}")
        return
    HOME.mkdir(parents=True, exist_ok=True)
    PWFILE.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    subprocess.run(
        [
            exe("initdb"),
            "-D",
            str(DATA),
            "-U",
            "postgres",
            "--auth=scram-sha-256",
            f"--pwfile={PWFILE}",
            "--encoding=UTF8",
            "--locale=C",
        ],
        check=True,
    )
    with (DATA / "postgresql.conf").open("a", encoding="utf-8") as conf:
        conf.write(f"\nlisten_addresses = 'localhost'\nport = {PORT}\n")
    print(f"Initialised {DATA}")


def start() -> None:
    subprocess.run([exe("pg_ctl"), "-D", str(DATA), "-l", str(LOG), "-w", "start"], check=True)


def stop() -> None:
    subprocess.run([exe("pg_ctl"), "-D", str(DATA), "-w", "stop"], check=True)


def createdb(name: str) -> None:
    env = {**os.environ, "PGPASSWORD": PWFILE.read_text(encoding="utf-8").strip()}
    subprocess.run(
        [exe("createdb"), "-h", "localhost", "-p", str(PORT), "-U", "postgres", name],
        check=True,
        env=env,
    )
    print(f"Created database {name}")


def status() -> None:
    subprocess.run([exe("pg_ctl"), "-D", str(DATA), "status"], check=False)


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "init":
        init()
    elif command == "start":
        start()
    elif command == "stop":
        stop()
    elif command == "status":
        status()
    elif command == "createdb":
        createdb(sys.argv[2] if len(sys.argv) > 2 else "osrip_dev")
    elif command == "url":
        print(admin_url(sys.argv[2] if len(sys.argv) > 2 else "postgres"))
    else:
        raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    main()
