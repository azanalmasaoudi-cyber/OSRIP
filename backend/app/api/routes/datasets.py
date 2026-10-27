"""Datasets people upload to analyse (CSV, Excel, JSON): private to their owner.

POST /datasets (multipart: file, optional sheet), GET /datasets, GET /datasets/{id} (with the
computed analysis and summaries), GET /datasets/{id}/rows, DELETE /datasets/{id},
POST /datasets/{id}/summary (an AI summary of the computed analysis, numbers checked)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel

from app.api.deps import DbSession, require
from app.core.config import get_settings
from app.core.errors import ApiError
from app.domain.enums import Permission
from app.services.datasets import store
from app.services.principal import Principal

router = APIRouter(tags=["datasets"])
Analyst = Annotated[Principal, Depends(require(Permission.DATASET_ANALYZE))]


class SummaryIn(BaseModel):
    language: Literal["en", "ar"] = "en"


@router.post("/datasets", status_code=201)
def upload(
    session: DbSession,
    actor: Analyst,
    response: Response,
    file: Annotated[UploadFile, File()],
    sheet: Annotated[str | None, Form(max_length=100)] = None,
) -> dict[str, Any]:
    limit = get_settings().dataset_max_bytes
    data = file.file.read(limit + 1)  # never read more than the limit allows
    if len(data) > limit:
        raise ApiError(
            413, "file_too_large", f"The file is larger than {limit // (1024 * 1024)} MB.",
            {"limit_bytes": limit},
        )  # fmt: skip
    ds, created = store.create(session, actor, file.filename or "dataset.csv", data, sheet)
    if not created:
        response.status_code = 200  # the same file was uploaded before
    return {**store.get(session, actor, ds.id), "created": created}


@router.get("/datasets")
def list_datasets(session: DbSession, actor: Analyst) -> list[dict[str, Any]]:
    return store.list_datasets(session, actor)


@router.get("/datasets/{dataset_id}")
def get_dataset(session: DbSession, actor: Analyst, dataset_id: uuid.UUID) -> dict[str, Any]:
    return store.get(session, actor, dataset_id)


@router.get("/datasets/{dataset_id}/rows")
def dataset_rows(
    session: DbSession,
    actor: Analyst,
    dataset_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=store.PREVIEW_ROWS)] = store.PREVIEW_ROWS,
) -> dict[str, Any]:
    return store.rows(session, actor, dataset_id, limit)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(session: DbSession, actor: Analyst, dataset_id: uuid.UUID) -> Response:
    store.delete(session, actor, dataset_id)
    return Response(status_code=204)


@router.post("/datasets/{dataset_id}/summary")
def summarise(
    session: DbSession, actor: Analyst, dataset_id: uuid.UUID, body: SummaryIn
) -> dict[str, Any]:
    return store.summarise(session, actor, dataset_id, body.language)
