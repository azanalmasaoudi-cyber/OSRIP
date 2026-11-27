#!/usr/bin/env python3
"""Compare a restored database's row counts with its backup's manifest (read only).

On the server, after restoring a backup made by tools/Backup-OSRIP-Local.ps1:

    docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec -T db \\
        psql -U osrip -d osrip -tA -c "$(python3 tools/compare_restore_counts.py --sql)" \\
        > counts.txt
    python3 tools/compare_restore_counts.py osrip_dev-YYYYMMDD-HHMMSS.backup.json counts.txt

counts.txt holds one "table|rows" line per table (the --sql query prints exactly that, plus the
migration version as "alembic_version_num|<version>"). Exit 0 only when every table, every count
and the migration version match the manifest. Standard library only; no database access.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

COUNT_SQL = (
    "SELECT table_name || '|' || (xpath('/row/c/text()', query_to_xml(format("
    "'SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text "
    "FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
    "UNION ALL SELECT 'alembic_version_num|' || version_num FROM alembic_version"
)


def read_counts(text: str) -> tuple[dict[str, int], str | None]:
    counts: dict[str, int] = {}
    migration = None
    for line in text.splitlines():
        name, _, value = line.strip().partition("|")
        if not name or not value:
            continue
        if name == "alembic_version_num":
            migration = value
        elif value.isdigit():
            counts[name] = int(value)
    return counts, migration


def compare(manifest: dict, counts: dict[str, int], migration: str | None) -> list[str]:
    expected = {k: int(v) for k, v in manifest["rows"].items()}
    problems = [
        f"{t}: backup {expected[t]}, restored {counts.get(t)}"
        for t in sorted(expected)
        if counts.get(t) != expected[t]
    ]
    problems += [f"{t}: not in the backup" for t in sorted(set(counts) - set(expected))]
    if migration != manifest.get("migration"):
        problems.append(f"migration: backup {manifest.get('migration')}, restored {migration}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("manifest", nargs="?", help="the backup's .backup.json manifest")
    parser.add_argument("counts", nargs="?", help="psql output of the --sql query")
    parser.add_argument("--sql", action="store_true", help="print the counting query and exit")
    args = parser.parse_args(argv)
    if args.sql:
        print(COUNT_SQL)
        return 0
    if not (args.manifest and args.counts):
        parser.error("give the manifest and the counts file (or --sql)")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
    counts, migration = read_counts(Path(args.counts).read_text(encoding="utf-8-sig"))
    problems = compare(manifest, counts, migration)
    for p in problems:
        print("DIFFERENT", p)
    if problems:
        print(f"The restored database does not match the backup ({len(problems)} differences).")
        return 1
    total = sum(counts.values())
    print(f"Match: {len(counts)} tables, {total} rows, migration {migration}, as in the backup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
