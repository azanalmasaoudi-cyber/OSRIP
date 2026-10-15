"""Documented performance workload (booklet 4.7). Reports measured numbers only.

What it does, in a throwaway database that is dropped afterwards:
  1. Migrates, seeds the booklet's synthetic fixtures and creates test accounts.
  2. Times one import of a generated SYNTHETIC file (63 wilayats x 120 months of
     electricity generation = 7,560 rows) through upload, validate, approve and
     publish, each step separately.
  3. Starts the API as a real HTTP server (uvicorn, one worker, no reload).
  4. Read workload: per endpoint, 5 warm-up requests, then 100 sequential requests.
  5. Concurrent workload: 10 client threads x 50 requests over the same endpoints.
  6. Report generation: 10 reports created and timed separately.
Results go to docs/perf/ as JSON and Markdown. The generated values are synthetic
software-test inputs, never Omani statistics.

Usage (from backend/):
    OSRIP_TEST_ADMIN_URL=$(python scripts/devdb.py url) python scripts/perf_workload.py
"""

from __future__ import annotations

import calendar
import concurrent.futures as cf
import io
import json
import os
import platform
import secrets
import statistics
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import psycopg
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
DB_NAME = "osrip_perf"
PORT = int(os.environ.get("OSRIP_PERF_PORT", "8790"))
BASE = f"http://127.0.0.1:{PORT}/api/v1"

READS = {
    "health": "/health",
    "indicators": "/indicators",
    "observations (electricity, monthly: 63 series)": (
        "/observations?data_mode=synthetic&section=electricity&frequency=monthly"
    ),
    "observations (one wilayat)": "/observations?data_mode=synthetic&area=OM-MA-01",
    "analysis electricity": "/analysis/electricity?data_mode=synthetic",
    "analysis food security": "/analysis/food_security?data_mode=synthetic",
    "areas registry": "/areas",
    "area coverage": "/areas/coverage?data_mode=synthetic",
    "forecast eligibility": "/forecast/eligibility?data_mode=synthetic",
}


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered) + 0.5) - 1))
    return ordered[k]


def summary(ms: list[float], errors: int) -> dict[str, float | int]:
    return {
        "n": len(ms),
        "errors": errors,
        "median_ms": round(statistics.median(ms), 1),
        "p95_ms": round(pct(ms, 95), 1),
        "max_ms": round(max(ms), 1),
    }


def generated_csv() -> tuple[bytes, int]:
    from app.db.session import session_factory
    from app.models import Area

    with session_factory()() as session:
        wilayats = sorted(session.query(Area.code).filter(Area.level == "wilayat").all())
    lines = ["indicator_code,area_code,period_start,period_end,frequency,unit_code,value"]
    for i, (code,) in enumerate(wilayats):
        for m in range(120):
            year, month = 2015 + m // 12, m % 12 + 1
            last = date(year, month, calendar.monthrange(year, month)[1])
            value = 100 + i * 3 + m * 0.5 + (m % 12) * 2  # deterministic synthetic pattern
            lines.append(
                f"ELEC_GENERATION,{code},{year}-{month:02d}-01,{last.isoformat()},monthly,GWh,{value}"
            )
    return ("\n".join(lines) + "\n").encode(), len(lines) - 1


def environment() -> dict[str, str]:
    info = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
    }
    try:
        cpu = subprocess.run(  # noqa: S603 - fixed command, no user input
            [  # noqa: S607 - Windows PowerShell on PATH; failure is handled
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name;"
                "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout.split()
        info["cpu"] = " ".join(cpu[:-1])
        info["ram_gb"] = cpu[-1]
    except (OSError, IndexError, subprocess.SubprocessError):
        info["cpu"] = platform.processor()
    return info


def login(client: httpx.Client, email: str, password: str) -> None:
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]


def main() -> None:
    admin = make_url(os.environ["OSRIP_TEST_ADMIN_URL"])
    plain = admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DB_NAME}"')
    db_url = admin.set(database=DB_NAME).render_as_string(hide_password=False)
    os.environ["OSRIP_DATABASE_URL"] = db_url
    os.environ["OSRIP_SESSION_COOKIE_SECURE"] = "false"
    password = secrets.token_urlsafe(18)

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")

    from app.db.session import session_factory
    from app.domain.enums import Permission, Role
    from app.services import accounts
    from app.services.fixtures import seed_booklet_fixtures
    from app.services.principal import Principal

    system = Principal(None, "system:perf")
    with session_factory()() as session:
        seed_booklet_fixtures(session)
        with session.begin():
            m = accounts.create_user(
                session,
                system,
                email="manager@perf.invalid",
                display_name="Perf manager",
                password=password,
                roles=[Role.DATA_MANAGER],
            )
            for p in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
                accounts.grant_permission(session, system, m.id, p)
            accounts.create_user(
                session,
                system,
                email="analyst@perf.invalid",
                display_name="Perf analyst",
                password=password,
                roles=[Role.ANALYST],
            )
    data, rows = generated_csv()

    env = {**os.environ, "OSRIP_DATABASE_URL": db_url, "OSRIP_SESSION_COOKIE_SECURE": "false"}
    server = subprocess.Popen(  # noqa: S603 - this interpreter, fixed arguments
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND,
        env=env,
    )
    results: dict[str, object] = {}
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)

        # ---- import, each step timed on its own
        with httpx.Client(base_url=BASE, timeout=300) as mgr:
            login(mgr, "manager@perf.invalid", password)
            src = mgr.post(
                "/sources",
                json={
                    "data_mode": "synthetic",
                    "dataset_title": "Perf synthetic monthly generation",
                    "geographic_coverage": "Wilayats (synthetic)",
                },
            ).json()["id"]
            steps: dict[str, float] = {}
            t = time.perf_counter()
            imp = mgr.post(
                "/imports",
                data={"source_id": src, "version_label": "perf-v1"},
                files={"file": ("perf.csv", io.BytesIO(data), "text/csv")},
            )
            imp.raise_for_status()
            steps["upload_ms"] = (time.perf_counter() - t) * 1000
            iid = imp.json()["id"]
            t = time.perf_counter()
            v = mgr.post(f"/imports/{iid}/validate")
            v.raise_for_status()
            steps["validate_ms"] = (time.perf_counter() - t) * 1000
            t = time.perf_counter()
            a = mgr.post(
                f"/imports/{iid}/approve",
                json={"acknowledged_rejected_rows": v.json()["rejected_row_count"], "note": "perf"},
            )
            a.raise_for_status()
            steps["approve_ms"] = (time.perf_counter() - t) * 1000
            t = time.perf_counter()
            p = mgr.post(f"/imports/{iid}/publish")
            p.raise_for_status()
            steps["publish_ms"] = (time.perf_counter() - t) * 1000
            results["import"] = {
                "rows": rows,
                "file_bytes": len(data),
                "rejected": v.json()["rejected_row_count"],
                **{k: round(val, 1) for k, val in steps.items()},
            }

        perf_db = admin.set(drivername="postgresql", database=DB_NAME)
        with psycopg.connect(perf_db.render_as_string(hide_password=False)) as conn:
            results["dataset"] = {
                "observations": conn.execute("SELECT count(*) FROM observation").fetchone()[0],
                "published_versions": conn.execute(
                    "SELECT count(*) FROM dataset_version WHERE status = 'published'"
                ).fetchone()[0],
                "areas": conn.execute("SELECT count(*) FROM area").fetchone()[0],
            }

        # ---- sequential reads (after warm-up)
        seq: dict[str, object] = {}
        with httpx.Client(base_url=BASE, timeout=60) as c:
            for name, path in READS.items():
                for _ in range(5):
                    c.get(path)
                ms, errors, size = [], 0, 0
                for _ in range(100):
                    t = time.perf_counter()
                    r = c.get(path)
                    ms.append((time.perf_counter() - t) * 1000)
                    errors += r.status_code != 200
                    size = len(r.content)
                seq[name] = {**summary(ms, errors), "response_bytes": size}
        results["sequential_reads"] = seq

        # ---- concurrent mixed reads
        paths = list(READS.values())

        def worker(k: int) -> tuple[list[float], int]:
            ms, errors = [], 0
            with httpx.Client(base_url=BASE, timeout=120) as c:
                for i in range(50):
                    t = time.perf_counter()
                    r = c.get(paths[(k + i) % len(paths)])
                    ms.append((time.perf_counter() - t) * 1000)
                    errors += r.status_code != 200
            return ms, errors

        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(10) as pool:
            parts = list(pool.map(worker, range(10)))
        wall = time.perf_counter() - t0
        all_ms = [x for ms, _ in parts for x in ms]
        results["concurrent_reads"] = {
            "clients": 10,
            "requests_per_client": 50,
            **summary(all_ms, sum(e for _, e in parts)),
            "wall_s": round(wall, 2),
            "throughput_rps": round(len(all_ms) / wall, 1),
        }

        # ---- report generation
        with httpx.Client(base_url=BASE, timeout=120) as an:
            login(an, "analyst@perf.invalid", password)
            ms, errors = [], 0
            for i in range(10):
                t = time.perf_counter()
                r = an.post(
                    "/reports",
                    json={
                        "title": f"Perf report {i}",
                        "data_mode": "synthetic",
                        "section": "electricity",
                        "filters": {"frequency": "monthly"},
                    },
                )
                ms.append((time.perf_counter() - t) * 1000)
                errors += r.status_code != 201
            results["report_generation"] = summary(ms, errors)
    finally:
        server.terminate()
        server.wait(timeout=30)
        from app.db.session import get_engine

        get_engine().dispose()
        with psycopg.connect(plain, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')

    record = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {
            **environment(),
            "server": "uvicorn, 1 worker, no reload, HTTP on 127.0.0.1",
            "database": "PostgreSQL (local portable cluster, same machine)",
            "client": "httpx on the same machine (keep-alive connections)",
            "cache": "no application cache; database buffers warm after warm-up",
        },
        **results,
    }
    out = ROOT / "docs" / "perf"
    out.mkdir(exist_ok=True)
    stamp = record["measured_at"][:10]
    (out / f"perf-{stamp}.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
