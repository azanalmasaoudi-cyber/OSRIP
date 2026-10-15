"""Administrative registry and statistical coverage by area (public reads)."""

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession
from app.domain.enums import DataMode
from app.services import geography

router = APIRouter(tags=["geography"])


@router.get("/areas")
def areas(session: DbSession) -> dict[str, Any]:
    """Governorates and wilayats with names, parents, identifiers, verification and references.

    Registry coverage only: listing an area says nothing about whether data exists for it.
    """
    with session.begin():
        return geography.registry(session)


@router.get("/areas/coverage")
def area_coverage(data_mode: DataMode, session: DbSession) -> dict[str, Any]:
    """Statistical coverage: published observations recorded for each exact area.

    Areas without observations are absent (shown as "No data", never zero).
    """
    with session.begin():
        return geography.coverage(session, data_mode)
