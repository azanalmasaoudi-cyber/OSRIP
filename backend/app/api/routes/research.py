"""Review queue for statistics found by the assistant's web research (``research.review``,
held by data managers). Reviewing never publishes: an accepted figure still has to be
imported through the normal upload, validation, approval and publication workflow."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.api.deps import DbSession, require
from app.domain.enums import Permission
from app.services.principal import Principal
from app.services.research import service as research

router = APIRouter(prefix="/research", tags=["research"])
Reviewer = Annotated[Principal, Depends(require(Permission.RESEARCH_REVIEW))]


@router.get("/candidates")
def candidates(
    session: DbSession,
    _: Reviewer,
    status: Literal["pending", "accepted", "rejected", "duplicate"] | None = "pending",
) -> list[dict[str, Any]]:
    with session.begin():
        return research.list_candidates(session, status)


class ReviewIn(BaseModel):
    decision: Literal["accepted", "rejected", "duplicate"]
    note: str | None = Field(default=None, max_length=2000)


@router.post("/candidates/{candidate_id}/review")
def review(
    candidate_id: uuid.UUID, body: ReviewIn, session: DbSession, principal: Reviewer
) -> dict[str, Any]:
    with session.begin():
        return research.review(session, principal, candidate_id, body.decision, body.note)


@router.get("/candidates/accepted.csv")
def accepted_csv(session: DbSession, _: Reviewer) -> Response:
    """Accepted figures with full provenance, to prepare a normal import file."""
    with session.begin():
        text = research.accepted_csv(session)
    return Response(
        text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="research-accepted.csv"',
            "Cache-Control": "no-store",
        },
    )
