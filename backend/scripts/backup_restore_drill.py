"""Controlled backup-and-restore exercise (booklet 3.15).

1. Fingerprints the source database: migration version, row count of every table,
   an MD5 of each published dataset version's observations (ordered by natural
   key) and the stored file checksums.
2. Backs it up with pg_dump (custom format) outside the repository.
3. Restores the backup into a separate, newly created database with pg_restore.
4. Fingerprints the restored database and compares; reads the known booklet
   fixture version through the application's own query service; checks that the
   immutability trigger still refuses a change to published observations.
5. Drops the restored database and writes the record to docs/backup/.

Usage (from backend/, with the dev cluster running):
    python scripts/backup_restore_drill.py [source_database]   # default osrip_dev
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from devdb import HOME, PORT, PWFILE, admin_url, exe  # noqa: E402

RESTORE_DB = "osrip_restore_drill"


def plain(database: str) -> str:
    return admin_url(database).replace("postgresql+psycopg://", "postgresql://")


def fingerprint(database: str) -> dict[str, object]:
    with psycopg.connect(plain(database)) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
        ]
        # Table names come from pg_tables, not from user input.
        counts = {
            t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]  # noqa: S608
            for t in tables
        }
        versions = {
            str(vid): {"label": label, "checksum": checksum, "observations_md5": md5}
            for vid, label, checksum, md5 in conn.execute(
                """
                SELECT v.id, v.version_label, v.checksum_sha256,
                       md5(coalesce(string_agg(
                           concat_ws('|', o.indicator_id, o.area_id, o.period_start, o.period_end,
                                     o.commodity_id, o.partner_id, o.flow, o.value::text,
                                     o.unit_id, o.quality_status, o.source_row),
                           ';' ORDER BY o.indicator_id, o.area_id, o.period_start,
                                        o.commodity_id, o.partner_id, o.flow), ''))
                FROM dataset_version v LEFT JOIN observation o ON o.dataset_version_id = v.id
                WHERE v.status IN ('published', 'superseded')
                GROUP BY v.id, v.version_label, v.checksum_sha256 ORDER BY v.id
                """
            )
        }
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    return {"alembic_revision": revision, "row_counts": counts, "published_versions": versions}


def run(cmd: list[str]) -> float:
    env = {**os.environ, "PGPASSWORD": PWFILE.read_text(encoding="utf-8").strip()}
    t = time.perf_counter()
    subprocess.run(cmd, check=True, env=env, capture_output=True)  # noqa: S603 - fixed tools
    return round(time.perf_counter() - t, 2)


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else "osrip_dev"
    backups = HOME / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dump = backups / f"{source}-{stamp}.dump"
    common = ["-h", "localhost", "-p", str(PORT), "-U", "postgres"]

    before = fingerprint(source)
    backup_s = run([exe("pg_dump"), *common, "-Fc", "-f", str(dump), source])
    digest = hashlib.sha256(dump.read_bytes()).hexdigest()

    with psycopg.connect(plain("postgres"), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{RESTORE_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{RESTORE_DB}"')
    checks: dict[str, object] = {}
    try:
        restore_s = run(
            [
                exe("pg_restore"),
                *common,
                "--exit-on-error",
                "--no-owner",
                "-d",
                RESTORE_DB,
                str(dump),
            ]
        )
        after = fingerprint(RESTORE_DB)
        checks["fingerprints_identical"] = before == after
        checks["differences"] = [
            k
            for k in ("alembic_revision", "row_counts", "published_versions")
            if before[k] != after[k]
        ]

        # Read the known booklet fixture through the application's own service.
        os.environ["OSRIP_DATABASE_URL"] = admin_url(RESTORE_DB)
        from app.db.session import get_engine, session_factory
        from app.domain.enums import DataMode, Section
        from app.services.observations import ObservationQuery, query_observations

        with session_factory()() as session, session.begin():
            series = query_observations(
                session,
                ObservationQuery(
                    DataMode.SYNTHETIC,
                    Section.ELECTRICITY,
                    indicator="ELEC_GENERATION",
                    area="OM",
                    frequency=None,
                ),
                allow_mixed=True,
            )
            fixture = [
                [o["value"] for o in s.observations]
                for s in series
                if s.meta["dataset_version"]["label"] == "fixtures-v1"
            ]
        checks["fixture_values_read_by_app"] = fixture
        checks["fixture_values_expected"] = [["48000", "50100"]]
        get_engine().dispose()

        # Integrity rules survive the restore: published observations stay immutable.
        with psycopg.connect(plain(RESTORE_DB)) as conn:
            try:
                conn.execute(
                    "UPDATE observation SET value = 0 WHERE dataset_version_id IN "
                    "(SELECT id FROM dataset_version WHERE status = 'published')"
                )
                checks["immutability_trigger_active"] = False
            except psycopg.errors.CheckViolation:
                checks["immutability_trigger_active"] = True
            conn.rollback()
    finally:
        with psycopg.connect(plain("postgres"), autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{RESTORE_DB}" WITH (FORCE)')

    passed = (
        checks.get("fingerprints_identical") is True
        and checks.get("fixture_values_read_by_app") == checks["fixture_values_expected"]
        and checks.get("immutability_trigger_active") is True
    )
    record = {
        "performed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_database": source,
        "restored_into": f"{RESTORE_DB} (created for the exercise, dropped afterwards)",
        "backup_file": str(dump),
        "backup_bytes": dump.stat().st_size,
        "backup_sha256": digest,
        "backup_seconds": backup_s,
        "restore_seconds": restore_s,
        "alembic_revision": before["alembic_revision"],
        "tables": len(before["row_counts"]),
        "rows_total": sum(before["row_counts"].values()),
        "published_versions": len(before["published_versions"]),
        "checks": checks,
        "result": "PASS" if passed else "FAIL",
    }
    out = ROOT / "docs" / "backup"
    out.mkdir(exist_ok=True)
    (out / f"backup-drill-{stamp[:8]}.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(record, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
