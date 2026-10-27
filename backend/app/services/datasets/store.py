"""Uploaded datasets: stored privately for their owner, analysed once at upload, summarised on
request. Every action is checked against the owner (another account's dataset is "not found",
whether it exists or not) and recorded in the audit log without the file's content."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, undefer

from app.core.config import get_settings
from app.core.errors import ApiError, conflict, not_found, unprocessable
from app.models import AnalysisDataset, AuditEvent
from app.services import audit
from app.services.assistant.provider import (
    ProviderError,
    failure_category,
    get_fallback_provider,
    get_provider,
    transient,
)
from app.services.datasets import analysis as analysis_
from app.services.datasets import summary as summary_
from app.services.datasets.parsing import DatasetError, parse
from app.services.principal import Principal

PREVIEW_ROWS = 5000


def _name(filename: str) -> str:
    name = PurePath(filename or "dataset").name.replace("\x00", "").strip()
    return name[:200] or "dataset"


def info(ds: AnalysisDataset) -> dict[str, Any]:
    return {
        "id": str(ds.id),
        "name": ds.name,
        "file_type": ds.file_type,
        "file_size": ds.file_size,
        "sheet": ds.sheet,
        "columns": ds.columns,
        "row_count": ds.row_count,
        "notes": ds.notes,
        "created_at": ds.created_at.isoformat(),
        "summary_languages": sorted(ds.summary or {}),
    }


def create(
    session: Session, actor: Principal, filename: str, data: bytes, sheet: str | None
) -> tuple[AnalysisDataset, bool]:
    """(dataset, created): the same file and sheet uploaded again returns the stored one."""
    s = get_settings()
    try:
        parsed = parse(
            filename, data, max_rows=s.dataset_max_rows, max_columns=s.dataset_max_columns,
            sheet=sheet or None,
        )  # fmt: skip
    except DatasetError as exc:
        raise unprocessable(str(exc), _error_text(str(exc), exc.params), exc.params) from exc
    digest = hashlib.sha256(data).hexdigest()
    with session.begin():
        existing = session.scalar(
            select(AnalysisDataset).where(
                AnalysisDataset.owner_id == actor.user_id,
                AnalysisDataset.sha256 == digest,
                AnalysisDataset.sheet.is_not_distinct_from(parsed.sheet),
            )
        )
        if existing is not None:
            return existing, False
        owned = session.scalar(
            select(func.count()).where(AnalysisDataset.owner_id == actor.user_id)
        )
        if (owned or 0) >= s.dataset_max_per_user:
            raise conflict(
                "dataset_limit",
                f"You have {owned} datasets, the most one account may keep. Delete one first.",
                {"limit": s.dataset_max_per_user},
            )
        result = analysis_.analyse(parsed.columns, parsed.rows)
        notes = {**parsed.notes, **({"sheets": parsed.sheets} if parsed.sheets else {})}
        ds = AnalysisDataset(
            owner_id=actor.user_id,
            name=_name(filename),
            file_type=parsed.file_type,
            file_size=len(data),
            sha256=digest,
            sheet=parsed.sheet,
            columns=parsed.columns,
            rows=parsed.rows,
            row_count=len(parsed.rows),
            notes=notes,
            analysis=result,
            summary={},
        )
        session.add(ds)
        session.flush()
        audit.record(
            session, actor, "dataset.upload", entity_type="analysis_dataset", entity_id=ds.id,
            metadata={"file_type": ds.file_type, "rows": ds.row_count,
                      "columns": len(ds.columns), "bytes": ds.file_size},
        )  # fmt: skip
        session.refresh(ds)
        return ds, True


def _owned(
    session: Session, actor: Principal, dataset_id: uuid.UUID, *extra: Any
) -> AnalysisDataset:
    ds = session.scalar(
        select(AnalysisDataset)
        .options(*extra)
        .where(AnalysisDataset.id == dataset_id, AnalysisDataset.owner_id == actor.user_id)
    )
    if ds is None:
        raise not_found("dataset")
    return ds


def list_datasets(session: Session, actor: Principal) -> list[dict[str, Any]]:
    with session.begin():
        rows = session.scalars(
            select(AnalysisDataset)
            .where(AnalysisDataset.owner_id == actor.user_id)
            .order_by(AnalysisDataset.created_at.desc())
        ).all()
        return [info(ds) for ds in rows]


def get(session: Session, actor: Principal, dataset_id: uuid.UUID) -> dict[str, Any]:
    with session.begin():
        ds = _owned(session, actor, dataset_id, undefer(AnalysisDataset.analysis))
        return {**info(ds), "analysis": ds.analysis, "summary": ds.summary or {}}


def rows(
    session: Session, actor: Principal, dataset_id: uuid.UUID, limit: int = PREVIEW_ROWS
) -> dict[str, Any]:
    with session.begin():
        ds = _owned(session, actor, dataset_id, undefer(AnalysisDataset.rows))
        return {
            "columns": ds.columns,
            "rows": ds.rows[:limit],
            "row_count": ds.row_count,
            "truncated": ds.row_count > limit,
        }


def load(session: Session, actor: Principal, dataset_id: uuid.UUID) -> AnalysisDataset:
    """The dataset with its rows and analysis (for exports and reports); caller's transaction."""
    return _owned(
        session, actor, dataset_id, undefer(AnalysisDataset.rows), undefer(AnalysisDataset.analysis)
    )


def delete(session: Session, actor: Principal, dataset_id: uuid.UUID) -> None:
    with session.begin():
        ds = _owned(session, actor, dataset_id)
        audit.record(session, actor, "dataset.delete", entity_type="analysis_dataset",
                     entity_id=ds.id, metadata={"rows": ds.row_count})  # fmt: skip
        session.delete(ds)


def _summaries_today(session: Session, actor: Principal) -> int:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.scalar(
            select(func.count()).where(
                AuditEvent.actor_id == actor.user_id,
                AuditEvent.action == "dataset.summary",
                AuditEvent.occurred_at >= start,
            )
        )
        or 0
    )


def summarise(
    session: Session, actor: Principal, dataset_id: uuid.UUID, language: str
) -> dict[str, Any]:
    """A checked AI summary of the computed analysis, stored with the dataset by language."""
    limit = get_settings().dataset_summaries_per_day
    with session.begin():
        ds = _owned(session, actor, dataset_id, undefer(AnalysisDataset.analysis))
        result = ds.analysis
        if _summaries_today(session, actor) >= limit:
            raise ApiError(429, "summary_limit", f"At most {limit} summaries per day.")
    provider = get_provider()
    fallback = get_fallback_provider()
    if provider is None and fallback is None:
        raise ApiError(503, "summary_unavailable", "No answering model is configured.")
    summary: dict[str, Any] | None = None
    failure: ProviderError | None = None
    for candidate in (provider, fallback):
        if candidate is None:
            continue
        try:
            summary = summary_.summarise(candidate, result, language)
            break
        except ProviderError as exc:
            failure = exc
            if not (
                transient(str(exc), exc.detail) or str(exc) in ("daily_limit", "budget_exhausted")
            ):
                break
    with session.begin():
        ds = _owned(session, actor, dataset_id)
        outcome = "success" if summary is not None else "failure"
        audit.record(
            session, actor, "dataset.summary", outcome, entity_type="analysis_dataset",
            entity_id=ds.id,
            metadata={"language": language, "status": (summary or {}).get("status"),
                      "removed": (summary or {}).get("removed"),
                      "error": None if failure is None or summary else str(failure)},
        )  # fmt: skip
        if summary is not None:
            ds.summary = {**(ds.summary or {}), language: summary}
    if summary is None:  # the failed attempt stays in the audit log (and counts)
        code = str(failure) if failure else "unavailable"
        category = failure_category(code, failure.detail if failure else None)
        raise ApiError(502, "summary_failed", "The model could not write a summary.",
                       {"code": code, "category": category})  # fmt: skip
    return summary


_ERRORS = {
    "unsupported_file_type": "Upload a CSV, Excel (.xlsx) or JSON file.",
    "empty_file": "The file is empty.",
    "no_header": "No header row was found.",
    "no_rows": "The file has a header but no rows of data.",
    "too_many_rows": "The file has more rows than allowed ({limit}).",
    "too_many_columns": "The file has {found} columns; at most {limit} are allowed.",
    "row_longer_than_header": "A row has more values than the header has columns (data row {row}).",
    "unknown_text_encoding": "The text is neither UTF-8 nor Windows-1256 (Arabic).",
    "not_a_text_file": "The file is not a text (CSV) file.",
    "csv_unreadable": "The CSV file could not be read.",
    "json_unreadable": "The JSON file could not be read.",
    "json_not_a_table": "The JSON is not a table: use an array of objects or columns and rows.",
    "json_rows_not_lists": "Each JSON row must be a list of values.",
    "json_columns_differ_in_length": "The JSON columns have different lengths.",
    "sheet_missing": "The workbook has no sheet named {sheet}.",
}


def _error_text(code: str, params: dict[str, Any]) -> str:
    template = _ERRORS.get(code)
    if template is None:
        return "The Excel file could not be read safely." if code.startswith("xlsx_") else code
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return template
