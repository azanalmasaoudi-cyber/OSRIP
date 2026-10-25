"""Review queue for statistics found by the assistant's web research (``research.review``,
held by data managers). "approved" saves a figure that is mapped to platform codes and written
in its stored document, through the import workflow (a figure that differs from a published one
is saved beside it as a revision, never in its place); "accepted" (kept for figures that are
not mapped) only lists it for a normal import."""

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
    status: Literal["pending", "conflict", "approved", "accepted", "rejected", "duplicate"]
    | None = "pending",
) -> list[dict[str, Any]]:
    with session.begin():
        return research.list_candidates(session, status)


class ReviewIn(BaseModel):
    decision: Literal["approved", "accepted", "rejected", "duplicate"]
    note: str | None = Field(default=None, max_length=2000)


@router.post("/candidates/{candidate_id}/review")
def review(
    candidate_id: uuid.UUID, body: ReviewIn, session: DbSession, principal: Reviewer
) -> dict[str, Any]:
    if body.decision == "approved":
        from app.models import ResearchCandidate
        from app.services.research import saving

        saving.save_reviewed(session, principal, candidate_id, body.note or "")
        with session.begin():
            row = session.get(ResearchCandidate, candidate_id)
            assert row is not None
            return research.candidate_out(row)
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
