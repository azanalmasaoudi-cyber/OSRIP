from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Process liveness only; says nothing about the database."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    """Database reachability. Errors are mapped to a stable 503 by the app handler."""
    session.execute(text("SELECT 1"))
    return {"status": "ok"}
