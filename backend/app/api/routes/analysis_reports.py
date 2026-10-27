"""Research and dataset reports and their exports (PDF, Excel, CSV).

POST /datasets/{id}/report, POST /assistant/messages/{id}/report, GET /analysis-reports,
GET /analysis-reports/{id}, DELETE /analysis-reports/{id},
GET /analysis-reports/{id}/export.{pdf|xlsx|csv}, GET /datasets/{id}/export.{csv|xlsx},
GET /reports/{id}/export.{pdf|xlsx} (platform reports, in the language asked)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, DbSession, require
from app.domain.enums import Permission
from app.services import analysis_reports as service
from app.services import reports as platform_reports
from app.services.datasets import store as datasets
from app.services.documents import build
from app.services.documents.model import Document
from app.services.principal import Principal

router = APIRouter(tags=["reports"])
SignedIn = Annotated[Principal, Depends(require())]
Analyst = Annotated[Principal, Depends(require(Permission.DATASET_ANALYZE))]
Language = Literal["en", "ar"]


class FromDataset(BaseModel):
    language: Language = "en"
    title: str | None = Field(default=None, max_length=200)
    questions: list[Annotated[str, Field(max_length=300)]] = Field(
        default_factory=list, max_length=5
    )


class FromAnswer(BaseModel):
    language: Language = "en"
    title: str | None = Field(default=None, max_length=200)


def _file(content: bytes, fmt: str, disposition: str) -> Response:
    return Response(
        content,
        media_type=service.MEDIA[fmt],
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/datasets/{dataset_id}/report", status_code=201)
def report_from_dataset(
    dataset_id: uuid.UUID, body: FromDataset, session: DbSession, actor: Analyst
) -> dict[str, Any]:
    report = service.from_dataset(
        session, actor, dataset_id, language=body.language, title=body.title,
        questions=body.questions,
    )  # fmt: skip
    return service.summary(report)


@router.post("/assistant/messages/{message_id}/report", status_code=201)
def report_from_answer(
    message_id: int, body: FromAnswer, session: DbSession, actor: SignedIn
) -> dict[str, Any]:
    report = service.from_answer(
        session, actor, message_id, language=body.language, title=body.title
    )
    return service.summary(report)


@router.get("/analysis-reports")
def list_reports(session: DbSession, actor: SignedIn) -> list[dict[str, Any]]:
    return service.list_reports(session, actor)


@router.get("/analysis-reports/{report_id}")
def get_report(report_id: uuid.UUID, session: DbSession, actor: SignedIn) -> dict[str, Any]:
    report = service.get(session, actor, report_id)
    return {**service.summary(report), "content": report.content}


@router.delete("/analysis-reports/{report_id}", status_code=204)
def delete_report(report_id: uuid.UUID, session: DbSession, actor: SignedIn) -> Response:
    service.delete(session, actor, report_id)
    return Response(status_code=204)


@router.get("/analysis-reports/{report_id}/export.{fmt}")
def export_report(
    report_id: uuid.UUID, fmt: Literal["pdf", "xlsx", "csv"], session: DbSession, actor: SignedIn
) -> Response:
    report = service.get(session, actor, report_id)
    document = Document.model_validate(report.content)
    name = service.disposition(report.title, fmt, f"osrip-report-{str(report.id)[:8]}")
    return _file(service.render(document, fmt), fmt, name)


@router.get("/datasets/{dataset_id}/export.{fmt}")
def export_dataset(
    dataset_id: uuid.UUID,
    fmt: Literal["csv", "xlsx"],
    session: DbSession,
    actor: Analyst,
    language: Annotated[Language, Query()] = "en",
) -> Response:
    """CSV: the dataset's rows as uploaded. Excel: the rows, then the computed analysis."""
    with session.begin():
        ds = datasets.load(session, actor, dataset_id)
        stem = service.disposition(ds.name.rsplit(".", 1)[0], fmt, f"dataset-{str(ds.id)[:8]}")
        if fmt == "csv":
            return _file(service.dataset_csv(ds), "csv", stem)
        info = {
            "name": ds.name, "file_type": ds.file_type, "sheet": ds.sheet,
            "created_at": ds.created_at.isoformat(), "sha256": ds.sha256,
        }  # fmt: skip
        document = Document.model_validate(
            build.dataset_document(
                info, ds.analysis, (ds.summary or {}).get(language), language, ds.name, []
            )
        )
        rows_sheet = service.dataset_rows_sheet(ds, language)
    return _file(service.render(document, "xlsx", [rows_sheet]), "xlsx", stem)


@router.get("/reports/{report_id}/export.{fmt}")
def export_platform_report(
    report_id: uuid.UUID,
    fmt: Literal["pdf", "xlsx"],
    session: DbSession,
    principal: CurrentPrincipal,
    language: Annotated[Language, Query()] = "en",
) -> Response:
    """A platform report as PDF or Excel (its CSV export is GET /reports/{id}/export.csv)."""
    with session.begin():
        report = platform_reports.get_report(session, principal, report_id)
        document = Document.model_validate(build.platform_document(report.content or {}, language))
    name = service.disposition(report.title, fmt, f"osrip-report-{str(report.id)[:8]}")
    return _file(service.render(document, fmt), fmt, name)
