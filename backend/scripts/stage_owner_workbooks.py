"""Stage the owner's November 2026 statistics workbooks through the controlled import.

    backend\\.venv\\Scripts\\python.exe scripts\\stage_owner_workbooks.py ANNUAL.xlsx LATEST.xlsx
    backend\\.venv\\Scripts\\python.exe scripts\\stage_owner_workbooks.py ANNUAL.xlsx LATEST.xlsx \\
        --stage --as Azzan

Reads the two workbooks (app/services/imports/owner_workbooks.py maps them), compares every
candidate row with the figures already published (same indicator, area and exact period, in
any unit of the same measure) and writes, to docs/data-imports/2026-11/:

* one import CSV per publication (only rows not already published with the same value; a row
  whose value differs from a published one says so in its note), and
* README.md: what is staged, what is already published, and what is not imported and why.

With ``--stage`` it then registers each publication as a verified source (once) and creates its
import, attributed to the account given with ``--as``, and validates it. Nothing is approved or
published: a data manager reviews each import in Data Management and approves or rejects it.
Uses ``osrip_dev`` on the dev cluster unless OSRIP_DATABASE_URL is set (as dev_cli.py does).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
OUT = BACKEND.parent / "docs" / "data-imports" / "2026-11"
ACCESSED = date(2026, 11, 8)
VERSION_LABEL = "2026-11 owner workbook, corrected"

YEARBOOK = (
    "https://api.ncsi.gov.om/uploads/pdfs/statistical_year_book_2026___issue_54_1777963604.pdf"
)
# Each publication the staged rows come from (verified sources need these fields).
SOURCES = {
    YEARBOOK: {
        "slug": "ncsi-yearbook-2026-baseline",
        "publisher": "NCSI",
        "dataset_title": "Statistical Year Book 2026, Issue 54: 2021 baseline and fishing by "
        "method (owner's workbook, November 2026)",
        "locator_kind": "direct_file",
        "publication_date": None,
        "reference_period": "2021-2025 complete calendar years (2025 provisional)",
        "geographic_coverage": "Oman (national)",
        "reuse_conditions": "Official statistics of the National Centre for Statistics and "
        "Information; reuse with attribution.",
    },
    "https://www.omandaily.om/article/1214358": {
        "slug": "electricity-water-jan-sep-2026",
        "publisher": "Oman Daily (reporting NCSI preliminary statistics)",
        "dataset_title": "Electricity and water production, January-September 2026",
        "locator_kind": "web_page",
        "publication_date": date(2026, 11, 7),
        "reference_period": "January-September 2026 and the matching 2025 period",
        "geographic_coverage": "Oman (national); Muscat and Dhofar (water)",
        "reuse_conditions": "News report of NCSI preliminary statistics; check against the NCSI "
        "release before approval.",
    },
    "https://www.omandaily.om/article/1213974": {
        "slug": "electricity-by-governorate-jan-sep-2026",
        "publisher": "Oman Daily (reporting NCSI preliminary statistics)",
        "dataset_title": "Electricity production by governorate, January-September 2026",
        "locator_kind": "web_page",
        "publication_date": None,
        "reference_period": "January-September 2026 and the matching 2025 period",
        "geographic_coverage": "Muscat, Ad Dakhiliyah, Dhofar, Al Wusta, Musandam (combined "
        "reporting areas not imported)",
        "reuse_conditions": "News report of NCSI preliminary statistics; check against the NCSI "
        "release before approval.",
    },
    "https://shabiba.com/article/213087-": {
        "slug": "musandam-artisanal-fish-jan-jun-2026",
        "publisher": "Shabiba (reporting fisheries statistics for Musandam)",
        "dataset_title": "Artisanal fish landings in Musandam, January-June 2026",
        "locator_kind": "web_page",
        "publication_date": None,
        "reference_period": "January-June 2026 and the matching 2025 period",
        "geographic_coverage": "Musandam (governorate)",
        "reuse_conditions": "News report of fisheries statistics; check against the official "
        "release before approval.",
    },
    "https://www.ncsi.gov.om/ar/newsPage/newsDetail?id=420": {
        "slug": "foreign-trade-jan-aug-2026",
        "publisher": "NCSI",
        "dataset_title": "Foreign trade, January-August 2026 (NCSI news release)",
        "locator_kind": "web_page",
        "publication_date": date(2026, 11, 3),
        "reference_period": "January-August 2026 and the matching 2025 period",
        "geographic_coverage": "Oman (national)",
        "reuse_conditions": "Official news release of the National Centre for Statistics and "
        "Information; values rounded to OMR 0.1 billion.",
    },
}
# Base factors, to compare a staged value with a published one in another unit of the measure.
FACTOR = {
    "GWh": 1, "MW": 1, "percent": 1, "subscriber": 1, "feddan": 1, "tonne": 1, "OMR": 1,
    "thousand_tonnes": 1000, "million_tonnes": 1_000_000, "thousand_head": 1000,
    "thousand_connections": 1000, "thousand_m3": 1000, "million_m3": 1_000_000,
    "thousand_OMR": 1000, "million_OMR": 1_000_000,
}  # fmt: skip


def source_for(url: str) -> dict | None:
    """The publication details for a row's address (matched by the start of the address)."""
    return next((meta for prefix, meta in SOURCES.items() if url.startswith(prefix)), None)


def same_value(staged: dict[str, str], published_base: Decimal) -> bool:
    """A staged figure equals a published one when they differ by no more than the rounding the
    workbook figure is written with (3,685 thousand tonnes is the same as 3,684,696 tonnes)."""
    step = Decimal(staged.get("_step") or "0")
    in_unit = published_base / FACTOR.get(staged["unit_code"], 1)
    return abs(in_unit - Decimal(staged["value"])) <= step / 2


def sheet_rows(book, name: str, header_row: int) -> list[dict[str, str]]:  # noqa: ANN001
    sheet = book.sheet(name)
    header = sheet.row(header_row)
    out = []
    for r in sheet.rows():
        if r <= header_row:
            continue
        cells = sheet.row(r)
        out.append({header[c]: cells.get(c, "") for c in header})
    return out


def published_values(session) -> dict[tuple[str, str, str, str], list[tuple[Decimal, str]]]:  # noqa: ANN001
    from sqlalchemy import text

    rows = session.execute(text(
        "SELECT i.code, a.code, o.period_start, o.period_end, o.value, un.code, s.dataset_title "
        "FROM observation o JOIN indicator i ON i.id = o.indicator_id "
        "JOIN area a ON a.id = o.area_id JOIN unit un ON un.id = o.unit_id "
        "JOIN dataset_version dv ON dv.id = o.dataset_version_id "
        "JOIN source s ON s.id = dv.source_id "
        "WHERE o.data_mode = 'verified_source' AND dv.status = 'published' AND o.value IS NOT NULL"
    ))  # fmt: skip
    found: dict[tuple[str, str, str, str], list[tuple[Decimal, str]]] = defaultdict(list)
    for code, area, start, end, value, unit, title in rows:
        base = Decimal(value) * FACTOR.get(unit, 1)
        found[(code, area, start.isoformat(), end.isoformat())].append(
            (base, f"{value} {unit} ({title})")
        )
    return found


def classify(mapped, published):  # noqa: ANN001, ANN201
    """Splits candidates into rows to stage and rows already published with the same value."""
    staged: dict[str, list[dict[str, str]]] = {}
    duplicates: list[str] = []
    for url, rows in mapped.rows.items():
        for row in rows:
            key = (row["indicator_code"], row["area_code"], row["period_start"], row["period_end"])
            same = [label for value, label in published.get(key, []) if same_value(row, value)]
            if same:
                duplicates.append(f"{' '.join(key)}: already published, {same[0]}")
                continue
            others = [label for _, label in published.get(key, [])]
            if others:
                row = {**row, "note": f"{row['note']} Differs from the published {others[0]}."}
            staged.setdefault(url, []).append(row)
    return staged, duplicates


def report(staged, duplicates, skipped) -> str:  # noqa: ANN001
    lines = [
        "# Owner's statistics workbooks of November 2026: staged imports",
        "",
        "Generated by `backend/scripts/stage_owner_workbooks.py` from "
        "`OSRIP_Oman_Annual_Research_Published_2026.xlsx` and "
        "`OSRIP_2026_Latest_Statistics_Through_October.xlsx`. Nothing here is published: each "
        "import is validated and waits for a data manager's approval in Data Management.",
        "",
        "Rules kept: complete calendar years 2021-2025 (2025 provisional) are full years; every "
        "2026 figure keeps its own period and is never a full year; nothing is assigned to a "
        "wilayat; combined reporting areas are never split.",
        "",
        "## Imports",
        "",
        "| Import file | Publication | Rows |",
        "|---|---|---|",
    ]
    for url, rows in staged.items():
        meta = source_for(url) or {}
        title = f"{meta['dataset_title']} ({meta['publisher']})"
        lines.append(f"| `{meta['slug']}.csv` | {title} | {len(rows)} |")
    lines += ["", f"## Already published with the same value ({len(duplicates)})", ""]
    lines += [f"- {d}" for d in duplicates] or ["- none"]
    lines += [
        "",
        f"## Not imported ({len(skipped)})",
        "",
        "| Sheet | Item | Why |",
        "|---|---|---|",
    ]
    lines += [f"| {s} | {i} | {w} |" for s, i, w in skipped]
    return "\n".join(lines) + "\n"


def stage(staged, username: str) -> list[str]:  # noqa: ANN001
    from sqlalchemy import select

    from app.core.errors import ApiError
    from app.db.session import session_factory
    from app.domain.enums import DataMode
    from app.models import Source
    from app.services import accounts
    from app.services.imports import owner_workbooks, workflow
    from app.services.principal import Principal

    out = []
    session = session_factory()()
    with session.begin():
        user = accounts.find_by_username(session, username)
        if user is None:
            raise SystemExit(f"error: no account '{username}'.")
        actor = Principal(user_id=user.id, label="system:cli:stage-owner-workbooks")
    for url, rows in staged.items():
        meta = {k: v for k, v in (source_for(url) or {}).items() if k != "slug"}
        with session.begin():
            source = session.scalar(
                select(Source).where(
                    Source.url == url, Source.dataset_title == meta["dataset_title"]
                )
            )
        if source is None:
            source = workflow.register_source(
                session, actor, data_mode=DataMode.VERIFIED_SOURCE, url=url, access_date=ACCESSED,
                **meta,
            )  # fmt: skip
        data = owner_workbooks.csv_text(rows).encode("utf-8")
        slug = (source_for(url) or {})["slug"]
        try:
            state = workflow.create_import(
                session, actor, source_id=source.id, version_label=VERSION_LABEL,
                filename=f"{slug}.csv", data=data,
            )  # fmt: skip
        except ApiError as exc:
            if exc.code not in ("duplicate_file", "version_label_taken"):
                raise
            # Run again: the same file, or this label, is already staged for this publication.
            out.append(f"{slug}: already staged ({exc.code}); nothing changed")
            continue
        state = workflow.validate_import(session, actor, state.job.id)
        out.append(
            f"{slug}: import {state.job.id}, {state.version.status.value}, "
            f"rows {state.job.row_count} (rejected {state.job.rejected_row_count}, "
            f"warnings {state.job.warning_row_count})"
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("annual", type=Path)
    parser.add_argument("latest", type=Path)
    parser.add_argument("--stage", action="store_true", help="create and validate the imports")
    parser.add_argument("--as", dest="username", help="the account the imports are attributed to")
    args = parser.parse_args()
    if args.stage and not args.username:
        parser.error("--stage needs --as USERNAME")
    os.chdir(BACKEND)
    from devdb import admin_url

    os.environ.setdefault("OSRIP_DATABASE_URL", admin_url("osrip_dev"))
    from app.db.session import session_factory
    from app.services.imports import owner_workbooks as ow
    from app.services.sync.xlsx import Workbook

    annual_book = Workbook(args.annual.read_bytes(), dates=True)
    latest_book = Workbook(args.latest.read_bytes(), dates=True)
    mapped = ow.Mapped()
    ow.annual(sheet_rows(annual_book, "Annual_Long", 4), mapped)
    latest_rows = sheet_rows(latest_book, "Latest_2026", 1)
    ow.latest(latest_rows, mapped)
    ow.regions(sheet_rows(latest_book, "Regions_2026", 1), mapped)
    with session_factory()() as session, session.begin():
        staged, duplicates = classify(mapped, published_values(session))
    unknown = {url for url in staged if source_for(url) is None}
    for url in unknown:
        mapped.skipped.append(("Latest_2026", url, "publication without source details"))
        staged.pop(url)
    OUT.mkdir(parents=True, exist_ok=True)
    for url, rows in staged.items():
        (OUT / f"{(source_for(url) or {})['slug']}.csv").write_bytes(
            ow.csv_text(rows).encode("utf-8")
        )
    (OUT / "README.md").write_bytes(report(staged, duplicates, mapped.skipped).encode("utf-8"))
    total = sum(len(r) for r in staged.values())
    print(f"{total} rows in {len(staged)} imports; {len(duplicates)} already published; "
          f"{len(mapped.skipped)} not imported. Written to {OUT}")  # fmt: skip
    if args.stage:
        lines = stage(staged, args.username)
        for line in lines:
            print(line)
        staged_note = [
            "",
            f"## Staged on {date.today().isoformat()} (as {args.username})",
            "",
            "Each import is validated and waits for approval in Data Management.",
            "",
            *(f"- {line}" for line in lines),
        ]
        with (OUT / "README.md").open("a", encoding="utf-8", newline="") as f:
            f.write(chr(10).join(staged_note) + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
