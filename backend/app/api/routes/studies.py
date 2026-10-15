"""Studies: deterministic analyses of approved observations with one shared result for the
table, chart and export (booklet 3.25, 3.29, 3.31). Running a study needs no account (it
reads only published data); a signed-in user's runs are listed for them."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DbSession, optional_session, require_authenticated
from app.core import ratelimit
from app.domain.enums import DataMode
from app.domain.study import STUDY_KINDS
from app.services import studies
from app.services.principal import Principal

router = APIRouter(prefix="/studies", tags=["studies"])


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    """The allowlisted study kinds and their parameters (JSON Schema)."""
    return {
        "kinds": [
            {
                "kind": k,
                "title": studies.CATALOG[k],
                "params": studies.PARAMS[k].model_json_schema(),
            }
            for k in STUDY_KINDS
        ]
    }


class StudyIn(BaseModel):
    kind: Literal[
        "trend",
        "growth",
        "compare_regions",
        "seasonal_profile",
        "import_dependence",
        "partner_concentration",
        "data_quality",
        "scenario",
        "forecast_eligibility",
        "programme_assessment",
    ]
    data_mode: DataMode
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=201)
def run(
    body: StudyIn,
    request: Request,
    session: DbSession,
    principal: Annotated[Principal, Depends(optional_session)],
) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    ratelimit.check(f"study:{client}", 240, 3600)
    with session.begin():
        return studies.run(session, body.kind, body.params, body.data_mode, principal)


@router.post("/preview")
def preview(body: StudyIn, request: Request, session: DbSession) -> dict[str, Any]:
    """The same validated study, computed but not stored: the workspace shows it for the
    current selection without creating a stored run on every filter change. Run a study
    (``POST /studies``) to keep, export or reproduce it."""
    client = request.client.host if request.client else "unknown"
    ratelimit.check(f"study-preview:{client}", 600, 3600)
    with session.begin():
        return {"study": studies.build(session, body.kind, body.params, body.data_mode)}


@router.get("")
def mine(
    session: DbSession, principal: Annotated[Principal, Depends(require_authenticated)]
) -> list[dict[str, Any]]:
    with session.begin():
        return studies.list_mine(session, principal)


@router.get("/{study_id}")
def get(study_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    with session.begin():
        return studies.out(studies.get(session, study_id))


@router.get("/{study_id}/reproduce")
def reproduce(study_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    """Rebuild from the stored parameters and compare with the stored result."""
    with session.begin():
        return studies.reproduce(session, study_id)


def _file_name(row: Any, study_id: uuid.UUID, extension: str) -> str:
    return f"osrip-study-{row.kind}-{str(study_id)[:8]}.{extension}"


@router.get("/{study_id}/export.csv")
def export_csv(
    study_id: uuid.UUID, session: DbSession, language: Literal["en", "ar"] = "en"
) -> Response:
    with session.begin():
        row = studies.get(session, study_id)
        text = studies.export_csv(row.result, language)
    return Response(
        "\ufeff" + text,  # BOM so spreadsheet programs read Arabic correctly
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{_file_name(row, study_id, "csv")}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{study_id}/export.json")
def export_json(study_id: uuid.UUID, session: DbSession) -> Response:
    import json

    with session.begin():
        row = studies.get(session, study_id)
        body = json.dumps({**studies.out(row)}, ensure_ascii=False, indent=2)
    return Response(
        body,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{_file_name(row, study_id, "json")}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/{study_id}", status_code=204)
def delete(
    study_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> Response:
    with session.begin():
        studies.delete(session, principal, study_id)
    return Response(status_code=204)
