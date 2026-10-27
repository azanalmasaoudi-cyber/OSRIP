"""Research and dataset reports: frozen when created, private to their owner, exported as PDF,
Excel or CSV (migration 0024, table analysis_report).

* From a dataset: its computed analysis, the checked AI summary in the report's language (if
  one was written) and the research questions the person typed.
* From an assistant answer: only an answer that passed the evidence check (status
  answered), in a conversation of the person's own account, with the question asked before it.

Another account's report, dataset or answer is "not found", whether it exists or not. Every
creation and deletion is in the audit log (never the content).
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session, undefer

from app.core.errors import ApiError, conflict, not_found, unprocessable
from app.models import AnalysisDataset, AnalysisReport, AssistantConversation, AssistantMessage
from app.services import audit
from app.services.datasets import store as datasets
from app.services.documents import build, export
from app.services.documents.fonts import FontError
from app.services.documents.model import Document
from app.services.documents.xlsx import Number, Sheet
from app.services.exports import safe_cell
from app.services.principal import Principal

MAX_REPORTS_PER_USER = 200
_PLAIN = re.compile(r"^-?\d+(\.\d+)?$")
MEDIA = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
}


def summary(r: AnalysisReport) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "kind": r.kind,
        "title": r.title,
        "language": r.language,
        "created_at": r.created_at.isoformat(),
        "dataset_id": str(r.dataset_id) if r.dataset_id else None,
        "message_id": r.message_id,
    }


def _room(session: Session, actor: Principal) -> None:
    count = session.scalar(select(func.count()).where(AnalysisReport.owner_id == actor.user_id))
    if (count or 0) >= MAX_REPORTS_PER_USER:
        raise conflict(
            "report_limit",
            f"You have {count} reports, the most one account may keep. Delete one first.",
            {"limit": MAX_REPORTS_PER_USER},
        )


def _store(
    session: Session, actor: Principal, kind: str, document: dict[str, Any], **links: Any
) -> AnalysisReport:
    report = AnalysisReport(
        owner_id=actor.user_id,
        kind=kind,
        title=document["title"],
        language=document["language"],
        content=document,
        **links,
    )
    session.add(report)
    session.flush()
    audit.record(
        session, actor, "analysis_report.create", entity_type="analysis_report",
        entity_id=report.id, metadata={"kind": kind, "language": report.language},
    )  # fmt: skip
    session.refresh(report)
    return report


def from_dataset(
    session: Session, actor: Principal, dataset_id: uuid.UUID, *, language: str,
    title: str | None, questions: list[str],
) -> AnalysisReport:  # fmt: skip
    with session.begin():
        _room(session, actor)
        ds = datasets.load(session, actor, dataset_id)
        info = {
            "name": ds.name, "file_type": ds.file_type, "sheet": ds.sheet,
            "created_at": ds.created_at.isoformat(), "sha256": ds.sha256,
        }  # fmt: skip
        document = build.dataset_document(
            info, ds.analysis, (ds.summary or {}).get(language), language,
            (title or "").strip() or ds.name, [q.strip() for q in questions if q.strip()],
        )  # fmt: skip
        return _store(session, actor, "dataset", document, dataset_id=ds.id)


def from_answer(
    session: Session, actor: Principal, message_id: int, *, language: str, title: str | None
) -> AnalysisReport:
    with session.begin():
        _room(session, actor)
        message = session.scalar(
            select(AssistantMessage)
            .join(
                AssistantConversation, AssistantConversation.id == AssistantMessage.conversation_id
            )
            .where(
                AssistantMessage.id == message_id,
                AssistantMessage.role == "assistant",
                AssistantConversation.user_id == actor.user_id,
            )
        )
        if message is None:
            raise not_found("answer")
        if message.status != "answered":
            raise unprocessable(
                "answer_not_verified",
                "Only an answer that passed the evidence check can become a report.",
            )
        question = (
            session.scalar(
                select(AssistantMessage.content)
                .where(
                    AssistantMessage.conversation_id == message.conversation_id,
                    AssistantMessage.role == "user",
                    AssistantMessage.id < message.id,
                )
                .order_by(AssistantMessage.id.desc())
                .limit(1)
            )
            or ""
        )
        default = re.sub(r"\s+", " ", question).strip()[:120] or (
            "تقرير بحثي" if language == "ar" else "Research report"
        )
        document = build.research_document(
            question,
            {
                "content": message.content, "evidence": message.evidence,
                "citations": message.citations, "calculations": message.calculations,
                "structured": message.structured, "model": message.model,
            },
            language,
            (title or "").strip() or default,
        )  # fmt: skip
        return _store(session, actor, "research", document, message_id=message.id)


def list_reports(session: Session, actor: Principal) -> list[dict[str, Any]]:
    with session.begin():
        rows = session.scalars(
            select(AnalysisReport)
            .where(AnalysisReport.owner_id == actor.user_id)
            .order_by(AnalysisReport.created_at.desc())
        ).all()
        return [summary(r) for r in rows]


def get(session: Session, actor: Principal, report_id: uuid.UUID) -> AnalysisReport:
    with session.begin():
        report = session.scalar(
            select(AnalysisReport)
            .options(undefer(AnalysisReport.content))
            .where(AnalysisReport.id == report_id, AnalysisReport.owner_id == actor.user_id)
        )
        if report is None:
            raise not_found("report")
        return report


def delete(session: Session, actor: Principal, report_id: uuid.UUID) -> None:
    with session.begin():
        report = session.scalar(
            select(AnalysisReport).where(
                AnalysisReport.id == report_id, AnalysisReport.owner_id == actor.user_id
            )
        )
        if report is None:
            raise not_found("report")
        audit.record(session, actor, "analysis_report.delete", entity_type="analysis_report",
                     entity_id=report.id, metadata={"kind": report.kind})  # fmt: skip
        session.delete(report)


def disposition(title: str, fmt: str, fallback: str) -> str:
    """Content-Disposition naming the file after its title: an ASCII name (the title's Latin
    letters, or the id-based fallback when it has none) and the full title in UTF-8."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:60]
    ascii_name = f"{slug if re.search(r'[A-Za-z]', slug) else fallback}.{fmt}"
    readable = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title).strip()[:120] or fallback
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(readable)}.{fmt}"


def render(document: Document, fmt: str, first: list[Sheet] | None = None) -> bytes:
    """The document in one format; a missing PDF font is a clear 503, never a broken file."""
    if fmt == "pdf":
        try:
            return export.to_pdf(document)
        except FontError as exc:
            raise ApiError(
                503, "pdf_font_missing",
                "No font with Arabic and Latin letters was found for PDF reports. Set "
                "OSRIP_REPORT_FONT_PATH to a TrueType font such as DejaVuSans.ttf.",
                {"reason": str(exc)},
            ) from exc  # fmt: skip
    if fmt == "xlsx":
        return export.to_xlsx(document, first)
    return export.to_csv(document).encode("utf-8")


def dataset_rows_sheet(ds: AnalysisDataset, language: str) -> Sheet:
    """The dataset's own rows, numbers as numbers where the column is numeric."""
    numeric = {c["index"] for c in ds.analysis["profile"] if c["kind"] == "number"}
    sheet = Sheet("البيانات" if language == "ar" else "Data", freeze=1)
    sheet.add(list(ds.columns), "header")
    for row in ds.rows:
        sheet.add([Number(v) if i in numeric and v is not None and _PLAIN.match(v) else v
                   for i, v in enumerate(row)])  # fmt: skip
    return sheet


def dataset_csv(ds: AnalysisDataset) -> bytes:
    """The dataset's rows as uploaded: numbers as numbers in numeric columns, other text
    protected against spreadsheet formulas, missing values as empty cells."""
    numeric = {c["index"] for c in ds.analysis["profile"] if c["kind"] == "number"}

    def cell(i: int, value: str | None) -> str:
        if value is None:
            return ""
        return value if i in numeric and _PLAIN.match(value) else safe_cell(value)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([safe_cell(c) for c in ds.columns])
    for row in ds.rows:
        writer.writerow([cell(i, v) for i, v in enumerate(row)])
    return ("﻿" + buffer.getvalue()).encode("utf-8")
