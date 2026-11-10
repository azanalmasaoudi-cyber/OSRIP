"""Stage the November 2026 wilayat evidence review as reviewed imports (nothing is published).

    backend\\.venv\\Scripts\\python.exe scripts\\stage_wilayat_evidence.py EVIDENCE.xlsx
    ... scripts\\stage_wilayat_evidence.py EVIDENCE.xlsx --stage --as USERNAME
    ... scripts\\stage_wilayat_evidence.py EVIDENCE.xlsx --reject --as USERNAME

Without ``--stage`` this is a dry run: the workbook is mapped (app/services/imports/
wilayat_evidence.py), checked against the registry and against the figures already published or
already waiting for review, and the import files and a report are written to
docs/data-imports/2026-11-wilayat/; the database is not changed. ``--stage`` registers each
publication as a verified source, creates one import per publication and validates it: each
then waits for a data manager's approval and publication in Data Management. ``--reject`` is the
rollback: it rejects this batch's imports that are not yet published (by their version label).

The 63 wilayat populations are reconciled with the workbook's national total before anything is
written; a mismatch stops the script.
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
import stage_owner_workbooks as sow  # noqa: E402

OUT = BACKEND.parent / "docs" / "data-imports" / "2026-11-wilayat"
ACCESSED = date(2026, 11, 9)
VERSION_LABEL = "2026-11 wilayat evidence review"
NATIONAL_POPULATION_2025 = Decimal(5359557)  # the workbook's 'Recorded 2025 population'
sow.FACTOR.update({"person": 1, "registration": 1})

_MOC = "Ministry of Commerce, Industry and Investment Promotion"
_MOC_REUSE = (
    "Official ministry announcement; check the wording of each count against the "
    "ministry's definition before approval."
)


def _moc(slug: str, title: str, period: str, coverage: str) -> dict:
    return {
        "slug": slug,
        "publisher": _MOC,
        "dataset_title": title,
        "locator_kind": "web_page",
        "publication_date": None,
        "reference_period": period,
        "geographic_coverage": coverage,
        "reuse_conditions": _MOC_REUSE,
    }


SOURCES = {
    sow.YEARBOOK: {
        "slug": "ncsi-yearbook-2026-wilayats",
        "publisher": "NCSI",
        "dataset_title": "Statistical Year Book 2026, Issue 54: population by wilayat and water "
        "by governorate, 2024-2025 (wilayat evidence review, November 2026)",
        "locator_kind": "direct_file",
        "publication_date": None,
        "reference_period": "End of 2024 and 2025 (population); "
        "calendar years 2024 and 2025 (water)",
        "geographic_coverage": "63 wilayats (population); 11 governorates (water)",
        "reuse_conditions": "Official statistics of the National Centre for Statistics and "
        "Information; reuse with attribution.",
    },
    "https://data.gov.om/OMELCT2016/electricity": {
        "slug": "ncsi-portal-electricity-distribution",
        "publisher": "NCSI Data Portal",
        "dataset_title": "Electricity distributed, 2021-2025 (NCSI data portal)",
        "locator_kind": "statistical_table",
        "publication_date": None,
        "reference_period": "Calendar years 2021-2025",
        "geographic_coverage": "Oman (national)",
        "reuse_conditions": "Official statistics of the National Centre for Statistics and "
        "Information; reuse with attribution.",
    },
    "https://www.tejarah.gov.om/en/media/news/wj2kyzv883nirxm7e05boa4u": _moc(
        "moc-new-crs-batinah-north-2025",
        "New commercial registrations by wilayat, Al Batinah North, 2025 (announced May 2026)",
        "Calendar year 2025",
        "6 wilayats of Al Batinah North",
    ),
    "https://tejarah.gov.om/en/media/news/sitwnr6f210ajzce1i4501wr": _moc(
        "moc-new-crs-batinah-south-2025",
        "New commercial registrations by wilayat, Al Batinah South, 2025 (announced March 2026)",
        "Calendar year 2025",
        "6 wilayats of Al Batinah South",
    ),
    "https://tejarah.gov.om/en/media/news/j1rg1e9wzrmgsni2ffewr1q0": _moc(
        "moc-new-crs-sharqiyah-north-2025",
        "New commercial registrations by wilayat, Ash Sharqiyah North, 2025 (announced April 2026)",
        "Calendar year 2025",
        "7 wilayats of Ash Sharqiyah North",
    ),
    "https://tejarah.gov.om/en/media/news/l7zh38rhz6a9nd3q227yml3n": _moc(
        "moc-new-crs-dakhiliyah-2025",
        "New commercial registrations by wilayat, Ad Dakhiliyah, 2025 (announced March 2026)",
        "Calendar year 2025",
        "5 of the 9 wilayats of Ad Dakhiliyah (the others not stated)",
    ),
    "https://www.tejarah.gov.om/en/media/news/qwo0y18pciqubu31rtxxexv0": _moc(
        "moc-new-crs-sharqiyah-south-2026q1",
        "New commercial registrations by wilayat, Ash Sharqiyah South, first quarter 2026 "
        "(announced June 2026)",
        "First quarter of 2026 only",
        "5 wilayats of Ash Sharqiyah South",
    ),
    "https://www.tejarah.gov.om/en/media/news/n0xg1wbmm8289y2fsyu4obmo": _moc(
        "moc-new-crs-dhahirah-2026q1",
        "New commercial registrations by wilayat, Adh Dhahirah, first quarter 2026 (announced "
        "June 2026)",
        "First quarter of 2026 only",
        "3 wilayats of Adh Dhahirah",
    ),
    "https://www.tejarah.gov.om/en/media/news/fsfe138mwuclrlkyfkk9jvkb": _moc(
        "moc-crs-wusta-2026q2",
        "Commercial registrations by wilayat, Al Wusta, second quarter 2026: new during the "
        "quarter and on record at its end (announced September 2026)",
        "Second quarter of 2026 (new) and 30 June 2026 (on record)",
        "4 wilayats of Al Wusta",
    ),
    "https://www.tejarah.gov.om/en/media/news/chvx8ju2kgls4ojsqcj": _moc(
        "moc-new-crs-national-jan-sep-2026",
        "New commercial registrations, Oman, January-September 2026 (ministry announcement)",
        "January-September 2026 only",
        "Oman (national)",
    ),
    "https://www.omandaily.om/article/1214358": sow.SOURCES[
        "https://www.omandaily.om/article/1214358"
    ],
}


def source_for(url: str) -> dict | None:
    return next((meta for prefix, meta in SOURCES.items() if url.startswith(prefix)), None)


def staged_values(session):  # noqa: ANN001, ANN201
    """Figures already waiting for review (draft, validated or approved imports)."""
    from sqlalchemy import text

    rows = session.execute(
        text(
            "SELECT r.raw, dv.status, j.original_filename FROM import_row r "
            "JOIN import_job j ON j.id = r.import_job_id "
            "JOIN dataset_version dv ON dv.id = j.dataset_version_id "
            "WHERE j.data_mode = 'verified_source' "
            "AND dv.status IN ('draft', 'validated', 'approved')"
        )
    )
    found: dict[tuple[str, str, str, str], list[tuple[Decimal, str]]] = defaultdict(list)
    for raw, status, filename in rows:
        try:
            base = Decimal(raw.get("value", "")) * sow.FACTOR.get(raw.get("unit_code", ""), 1)
        except ArithmeticError:
            continue
        key = (
            raw.get("indicator_code", ""),
            raw.get("area_code", ""),
            raw.get("period_start", ""),
            raw.get("period_end", ""),
        )
        found[key].append(
            (base, f"{raw.get('value')} {raw.get('unit_code')} ({filename}, {status})")
        )
    return found


def classify(mapped, published, waiting):  # noqa: ANN001, ANN201
    """Rows to stage, and the rows already published or already waiting with the same value."""
    staged: dict[str, list[dict[str, str]]] = {}
    duplicates: list[str] = []
    for url, rows in mapped.rows.items():
        for row in rows:
            key = (row["indicator_code"], row["area_code"], row["period_start"], row["period_end"])
            same = [label for value, label in published.get(key, []) if sow.same_value(row, value)]
            if same:
                duplicates.append(f"{' '.join(key)}: already published, {same[0]}")
                continue
            queued = [label for value, label in waiting.get(key, []) if sow.same_value(row, value)]
            if queued:
                duplicates.append(f"{' '.join(key)}: already waiting for review, {queued[0]}")
                continue
            others = [label for _, label in [*published.get(key, []), *waiting.get(key, [])]]
            if others:
                row = {**row, "note": f"{row['note']} Differs from {others[0]}."}
            staged.setdefault(url, []).append(row)
    return staged, duplicates


def report(staged, duplicates, skipped, coverage, totals) -> str:  # noqa: ANN001
    from app.services.imports import wilayat_evidence as we

    lines = [
        "# Wilayat evidence review of November 2026: staged imports",
        "",
        "Generated by `backend/scripts/stage_wilayat_evidence.py` from "
        "`OSRIP_Wilayat_Evidence_Development_Review_2026.xlsx`, mapped by "
        "`backend/app/services/imports/wilayat_evidence.py`. Nothing here is published: each "
        "import is validated and waits for a data manager's approval in Data Management.",
        "",
        "Rules kept: population is context (not a fifth axis); wilayats are matched to the "
        "registry by their Arabic names (English inside the same governorate only when the "
        "Arabic is spelt differently); water stays at governorate level; new commercial "
        "registrations in 2025, in the first quarter of 2026 and in the second quarter of 2026, "
        "and registrations on record at the end of June 2026 are separate periods and indicators, "
        "never added together; January-September 2026 is a partial year; no wilayat value is "
        "estimated from a governorate or national total, or from population.",
        "",
        "## Reconciliation",
        "",
        f"- Wilayats matched: {totals['matched']} of 63",
        f"- Population 2025, sum of the 63 wilayats: {totals['2025']:,} (workbook total "
        f"{NATIONAL_POPULATION_2025:,})",
        f"- Population 2024, sum of the 63 wilayats: {totals['2024']:,}",
        f"- Wilayat and axis coverage statuses: {sum(coverage.values())} "
        "(documentation, not observations): "
        + "; ".join(f"{status}: {n}" for status, n in sorted(coverage.items())),
        "",
        "## Imports",
        "",
        "| Import file | Publication | Rows |",
        "|---|---|---|",
    ]
    for url, rows in staged.items():
        meta = source_for(url) or {}
        lines.append(
            f"| `{meta.get('slug')}.csv` | {meta.get('dataset_title')} "
            f"({meta.get('publisher')}) | {len(rows)} |"
        )
    lines += [
        "",
        f"## Already published or waiting for review with the same value ({len(duplicates)})",
        "",
    ]
    lines += [f"- {d}" for d in duplicates] or ["- none"]
    lines += ["", f"## Not imported ({len(skipped)})", ""]
    lines += [f"- {sheet}: {item}: {why}" for sheet, item, why in skipped] or ["- none"]
    lines += ["", "## Sources", ""]
    lines += [
        f"- {meta['publisher']}: {meta['dataset_title']}. {url}" for url, meta in SOURCES.items()
    ]
    lines += [
        "",
        f"Wilayat names: the registry's Arabic names, matched with `{we.arabic_key.__name__}`.",
        "",
    ]
    return "\n".join(lines)


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
        actor = Principal(user_id=user.id, label="system:cli:stage-wilayat-evidence")
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
                session,
                actor,
                data_mode=DataMode.VERIFIED_SOURCE,
                url=url,
                access_date=ACCESSED,
                **meta,
            )
        slug = (source_for(url) or {})["slug"]
        try:
            state = workflow.create_import(
                session,
                actor,
                source_id=source.id,
                version_label=VERSION_LABEL,
                filename=f"{slug}.csv",
                data=owner_workbooks.csv_text(rows).encode("utf-8"),
            )
        except ApiError as exc:
            if exc.code not in ("duplicate_file", "version_label_taken"):
                raise
            out.append(f"{slug}: already staged ({exc.code}); nothing changed")
            continue
        state = workflow.validate_import(session, actor, state.job.id)
        out.append(
            f"{slug}: import {state.job.id}, {state.version.status.value}, "
            f"rows {state.job.row_count} "
            f"(rejected {state.job.rejected_row_count}, warnings {state.job.warning_row_count})"
        )
    return out


def reject(username: str) -> list[str]:
    """Rollback: reject this batch's imports that are not published yet."""
    from sqlalchemy import text

    from app.db.session import session_factory
    from app.services import accounts
    from app.services.imports import workflow
    from app.services.principal import Principal

    session = session_factory()()
    with session.begin():
        user = accounts.find_by_username(session, username)
        if user is None:
            raise SystemExit(f"error: no account '{username}'.")
        actor = Principal(user_id=user.id, label="system:cli:stage-wilayat-evidence")
        jobs = session.execute(
            text(
                "SELECT j.id, j.original_filename FROM import_job j "
                "JOIN dataset_version dv ON dv.id = j.dataset_version_id "
                "WHERE dv.version_label = :label "
                "AND dv.status IN ('draft', 'validated', 'approved')"
            ),
            {"label": VERSION_LABEL},
        ).all()
    out = []
    for job_id, filename in jobs:
        workflow.reject_import(
            session, actor, job_id, "Rolled back: wilayat evidence staging withdrawn."
        )
        out.append(f"{filename}: import {job_id} rejected")
    return out or ["nothing to reject"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--stage", action="store_true", help="create and validate the imports")
    parser.add_argument("--reject", action="store_true", help="reject this batch's pending imports")
    parser.add_argument("--as", dest="username", help="the account the imports are attributed to")
    args = parser.parse_args()
    if (args.stage or args.reject) and not args.username:
        parser.error("--stage and --reject need --as USERNAME")
    os.chdir(BACKEND)
    from devdb import admin_url

    os.environ.setdefault("OSRIP_DATABASE_URL", admin_url("osrip_dev"))
    if args.reject:
        for line in reject(args.username):
            print(line)
        return 0

    from sqlalchemy import text

    from app.db.session import session_factory
    from app.services.imports import owner_workbooks as ow
    from app.services.imports import wilayat_evidence as we
    from app.services.sync.xlsx import Workbook

    book = Workbook(args.workbook.read_bytes(), dates=True)
    with session_factory()() as session, session.begin():
        areas = [
            we.Area(*row)
            for row in session.execute(
                text(
                    "SELECT a.code, a.name_en, a.name_ar, a.level::text, p.code FROM area a "
                    "LEFT JOIN area p ON p.id = a.parent_id"
                )
            ).all()
        ]
        registry = we.Registry(areas)
        mapped = ow.Mapped()
        english = we.population(sow.sheet_rows(book, "Wilayats_63", 3), registry, mapped)
        we.trade(sow.sheet_rows(book, "Trade_Wilayat_Events", 3), english, registry, mapped)
        we.water(sow.sheet_rows(book, "Water_Governorates", 3), mapped)
        we.national(sow.sheet_rows(book, "Annual_National", 3), mapped)
        we.interim(sow.sheet_rows(book, "2026_Interim", 3), mapped)
        coverage = we.coverage(sow.sheet_rows(book, "Axis_Coverage_252", 3))
        staged, duplicates = classify(mapped, sow.published_values(session), staged_values(session))
    totals = {
        "matched": len(english),
        "2025": we.national_total(mapped, "2025"),
        "2024": we.national_total(mapped, "2024"),
    }
    if totals["matched"] != 63 or totals["2025"] != NATIONAL_POPULATION_2025:
        raise SystemExit(f"error: reconciliation failed: {totals}; nothing written")
    unknown = [url for url in staged if source_for(url) is None]
    for url in unknown:
        mapped.skipped.append(("sources", url, "publication without source details"))
        staged.pop(url)
    OUT.mkdir(parents=True, exist_ok=True)
    for url, rows in staged.items():
        (OUT / f"{source_for(url)['slug']}.csv").write_bytes(ow.csv_text(rows).encode("utf-8"))
    (OUT / "README.md").write_bytes(
        report(staged, duplicates, mapped.skipped, coverage, totals).encode("utf-8")
    )
    total = sum(len(r) for r in staged.values())
    print(
        f"{total} rows in {len(staged)} imports; {len(duplicates)} already published or waiting; "
        f"{len(mapped.skipped)} not imported. Written to {OUT}"
    )
    if args.stage:
        lines = stage(staged, args.username)
        for line in lines:
            print(line)
        note = [
            "",
            f"## Staged on {date.today().isoformat()} (as {args.username})",
            "",
            "Each import is validated and waits for approval in Data Management.",
            "",
            *(f"- {line}" for line in lines),
        ]
        with (OUT / "README.md").open("a", encoding="utf-8", newline="") as f:
            f.write(chr(10).join(note) + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
