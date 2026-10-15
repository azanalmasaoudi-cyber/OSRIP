"""Sources and the import workflow (booklet 3.2, 3.12; Table 3.5)."""

import csv
import io
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import CurrentPrincipal, DbSession, require
from app.core.config import get_settings
from app.core.errors import ApiError
from app.domain.enums import DataMode, DatasetVersionStatus, Permission
from app.models import DatasetVersion, ImportJob, ImportRow, Source
from app.schemas.imports import (
    ApproveIn,
    ImportOut,
    ImportRowOut,
    ImportRowsOut,
    MappingIn,
    PublishOut,
    RejectIn,
    SourceIn,
    SourceOut,
    VersionOut,
)
from app.services.imports import workflow
from app.services.imports.csv_file import safe_cell
from app.services.imports.validation import OPTIONAL_FIELDS, REQUIRED_FIELDS
from app.services.principal import Principal

router = APIRouter(tags=["imports"])

VERIFICATION_NOTE = (
    "A registered source records where values came from. It does not verify any particular number; "
    "each published value keeps its own source row and dataset version."
)
PUBLIC_STATUSES = {DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.SUPERSEDED}


def _version_out(v: DatasetVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        label=v.version_label,
        status=v.status,
        checksum_sha256=v.checksum_sha256,
        created_at=v.created_at,
        approved_at=v.approved_at,
        published_at=v.published_at,
        superseded_at=v.superseded_at,
    )


def _import_out(state: workflow.ImportState) -> ImportOut:
    j, v, s = state.job, state.version, state.source
    return ImportOut(
        id=j.id,
        source_id=s.id,
        source_title=s.dataset_title,
        data_mode=j.data_mode,
        version=_version_out(v),
        original_filename=j.original_filename,
        file_size=j.file_size,
        header=j.header,
        column_mapping=j.column_mapping,
        required_fields=list(REQUIRED_FIELDS),
        optional_fields=list(OPTIONAL_FIELDS),
        row_count=j.row_count,
        valid_row_count=j.valid_row_count,
        warning_row_count=j.warning_row_count,
        rejected_row_count=j.rejected_row_count,
        created_at=j.created_at,
        validated_at=j.validated_at,
        approval_note=j.approval_note,
        acknowledged_rejected_rows=j.acknowledged_rejected_rows,
        rejection_reason=j.rejection_reason,
        last_error_code=j.last_error_code,
    )


# ------------------------------------------------------------------ sources


@router.get("/sources", response_model=list[SourceOut])
def list_sources(
    session: DbSession, principal: CurrentPrincipal, data_mode: DataMode
) -> list[SourceOut]:
    """Public: sources with a published or superseded version. Import readers also see drafts."""
    private = principal.has(Permission.IMPORT_READ)
    with session.begin():
        out = []
        for source in session.scalars(
            select(Source).where(Source.data_mode == data_mode).order_by(Source.dataset_title)
        ):
            versions = [
                v
                for v in session.scalars(
                    select(DatasetVersion)
                    .where(DatasetVersion.source_id == source.id)
                    .order_by(DatasetVersion.created_at)
                )
                if private or v.status in PUBLIC_STATUSES
            ]
            if not versions and not private:
                continue
            out.append(
                SourceOut(
                    id=source.id,
                    data_mode=source.data_mode,
                    dataset_title=source.dataset_title,
                    publisher=source.publisher,
                    url=source.url,
                    locator_kind=source.locator_kind,
                    access_date=source.access_date,
                    publication_date=source.publication_date,
                    reference_period=source.reference_period,
                    geographic_coverage=source.geographic_coverage,
                    definition_note=source.definition_note,
                    reuse_conditions=source.reuse_conditions,
                    versions=[_version_out(v) for v in versions],
                    verification_note=VERIFICATION_NOTE,
                )
            )
        return out


@router.post("/sources", response_model=SourceOut, status_code=201)
def register_source(
    body: SourceIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.SOURCE_REGISTER))],
) -> SourceOut:
    fields = body.model_dump()
    fields["url"] = str(body.url) if body.url else None
    fields["locator_kind"] = body.locator_kind.value if body.locator_kind else None
    source = workflow.register_source(session, actor, **fields)
    return SourceOut(
        **{
            k: getattr(source, k)
            for k in (
                "id",
                "data_mode",
                "dataset_title",
                "publisher",
                "url",
                "locator_kind",
                "access_date",
                "publication_date",
                "reference_period",
                "geographic_coverage",
                "definition_note",
                "reuse_conditions",
            )
        },
        versions=[],
        verification_note=VERIFICATION_NOTE,
    )


# ------------------------------------------------------------------ imports


@router.post("/imports", response_model=ImportOut, status_code=201)
def upload(
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_CREATE))],
    source_id: Annotated[uuid.UUID, Form()],
    version_label: Annotated[str, Form(max_length=100)],
    file: Annotated[UploadFile, File()],
) -> ImportOut:
    limit = get_settings().upload_max_bytes
    data = file.file.read(limit + 1)  # never read more than the limit allows
    if len(data) > limit:
        raise ApiError(
            413, "file_too_large", f"The file is larger than {limit // (1024 * 1024)} MB."
        )
    state = workflow.create_import(
        session,
        actor,
        source_id=source_id,
        version_label=version_label,
        filename=file.filename or "upload.csv",
        data=data,
    )
    return _import_out(state)


@router.get("/imports", response_model=list[ImportOut])
def list_imports(
    session: DbSession, _: Annotated[Principal, Depends(require(Permission.IMPORT_READ))]
) -> list[ImportOut]:
    with session.begin():
        ids = session.scalars(
            select(ImportJob.id).order_by(ImportJob.created_at.desc()).limit(100)
        ).all()
        return [_import_out(workflow.get_state(session, i)) for i in ids]


@router.get("/imports/{import_id}", response_model=ImportOut)
def get_import(
    import_id: uuid.UUID,
    session: DbSession,
    _: Annotated[Principal, Depends(require(Permission.IMPORT_READ))],
) -> ImportOut:
    with session.begin():
        return _import_out(workflow.get_state(session, import_id))


@router.put("/imports/{import_id}/mapping", response_model=ImportOut)
def set_mapping(
    import_id: uuid.UUID,
    body: MappingIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_VALIDATE))],
) -> ImportOut:
    return _import_out(workflow.set_mapping(session, actor, import_id, body.mapping))


@router.post("/imports/{import_id}/validate", response_model=ImportOut)
def validate(
    import_id: uuid.UUID,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_VALIDATE))],
) -> ImportOut:
    return _import_out(workflow.validate_import(session, actor, import_id))


@router.get("/imports/{import_id}/rows", response_model=ImportRowsOut)
def rows(
    import_id: uuid.UUID,
    session: DbSession,
    _: Annotated[Principal, Depends(require(Permission.IMPORT_READ))],
    outcome: Literal["valid", "warning", "rejected"] | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImportRowsOut:
    """Error preview: every row with its outcome, original values and reasons."""
    with session.begin():
        workflow.get_state(session, import_id)
        where = [ImportRow.import_job_id == import_id]
        if outcome:
            where.append(ImportRow.outcome == outcome)
        total = session.scalar(select(func.count()).select_from(ImportRow).where(*where)) or 0
        page = session.scalars(
            select(ImportRow)
            .where(*where)
            .order_by(ImportRow.row_number)
            .limit(limit)
            .offset(offset)
        )
        return ImportRowsOut(
            total=total,
            rows=[
                ImportRowOut(row_number=r.row_number, outcome=r.outcome, raw=r.raw, issues=r.issues)
                for r in page
            ],
        )


@router.get("/imports/{import_id}/errors.csv")
def error_report(
    import_id: uuid.UUID,
    session: DbSession,
    _: Annotated[Principal, Depends(require(Permission.IMPORT_READ))],
) -> StreamingResponse:
    """Downloadable error list: row number, original value and reason (booklet 3.3)."""
    with session.begin():
        state = workflow.get_state(session, import_id)
        issues_rows = session.scalars(
            select(ImportRow)
            .where(ImportRow.import_job_id == import_id, ImportRow.outcome != "valid")
            .order_by(ImportRow.row_number)
        ).all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "# OSRIP import error report",
                f"data_mode={state.version.data_mode.value}",
                f"file={safe_cell(state.job.original_filename)}",
                f"version={safe_cell(state.version.version_label)}",
            ]
        )
        writer.writerow(
            ["row_number", "outcome", "severity", "code", "field", "original_value", "message"]
        )
        for r in issues_rows:
            for issue in r.issues:
                writer.writerow(
                    [
                        r.row_number,
                        r.outcome,
                        issue["severity"],
                        issue["code"],
                        issue["field"] or "",
                        safe_cell(issue["value"] or ""),
                        issue["message"],
                    ]
                )
    filename = f"import-{import_id}-{state.version.data_mode.value}-errors.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/imports/{import_id}/approve", response_model=ImportOut)
def approve(
    import_id: uuid.UUID,
    body: ApproveIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_APPROVE))],
) -> ImportOut:
    return _import_out(
        workflow.approve_import(
            session,
            actor,
            import_id,
            acknowledged_rejected_rows=body.acknowledged_rejected_rows,
            note=body.note,
        )
    )


@router.post("/imports/{import_id}/publish", response_model=PublishOut)
def publish(
    import_id: uuid.UUID,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_PUBLISH))],
) -> PublishOut:
    result = workflow.publish_import(session, actor, import_id)
    return PublishOut(
        import_=_import_out(result.state),
        already_published=result.already_published,
        observations_inserted=result.observations_inserted,
        superseded_version_id=result.superseded_version_id,
    )


@router.post("/imports/{import_id}/reject", response_model=ImportOut)
def reject(
    import_id: uuid.UUID,
    body: RejectIn,
    session: DbSession,
    actor: Annotated[Principal, Depends(require(Permission.IMPORT_REJECT))],
) -> ImportOut:
    return _import_out(workflow.reject_import(session, actor, import_id, body.reason))
