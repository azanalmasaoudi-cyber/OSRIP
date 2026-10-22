"""Studies as background jobs ("Create study"), and scheduled reports for administrators.

Creating a study returns at once (202) with its id; the study runs in a worker thread and its
steps, progress and result are read with GET. It can be stopped, and a failed, partial or
stopped study can be retried from its last completed step."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.api.deps import DbSession, require
from app.domain.enums import Permission
from app.services import audit
from app.services.principal import Principal
from app.services.research import jobs, schedules

router = APIRouter(tags=["studies"])
User = Annotated[Principal, Depends(require(Permission.ASSISTANT_USE))]
Admin = Annotated[Principal, Depends(require(Permission.USER_MANAGE))]


class JobIn(BaseModel):
    params: dict[str, Any]
    refresh: bool = False


def _admin(principal: Principal) -> bool:
    return principal.has(Permission.USER_MANAGE)


@router.post("/research/jobs", status_code=202)
def create_job(body: JobIn, session: DbSession, principal: User) -> dict[str, Any]:
    """Queue a study (or serve an identical recent one from cache) and return at once."""
    with session.begin():
        job = jobs.create(session, body.params, user_id=principal.user_id, refresh=body.refresh)
        out = jobs.view(job)
    if out["state"] == "queued":
        jobs.kick()
    return out


@router.get("/research/jobs")
def my_jobs(session: DbSession, principal: User) -> list[dict[str, Any]]:
    with session.begin():
        return jobs.list_mine(session, principal.user_id)


@router.get("/research/jobs/{job_id}")
def get_job(job_id: uuid.UUID, session: DbSession, principal: User) -> dict[str, Any]:
    with session.begin():
        return jobs.view(jobs.own(session, job_id, principal.user_id, admin=_admin(principal)))


@router.get("/research/jobs/{job_id}/documents")
def job_documents(job_id: uuid.UUID, session: DbSession, principal: User) -> list[dict[str, Any]]:
    """The documents the study retrieved, with provenance. Their text is untrusted evidence."""
    with session.begin():
        job = jobs.own(session, job_id, principal.user_id, admin=_admin(principal))
        return jobs.documents(session, job)


@router.post("/research/jobs/{job_id}/cancel")
def cancel_job(job_id: uuid.UUID, session: DbSession, principal: User) -> dict[str, Any]:
    with session.begin():
        job = jobs.own(session, job_id, principal.user_id, admin=_admin(principal), lock=True)
        jobs.cancel(session, job)
        session.flush()
        return jobs.view(job)


@router.post("/research/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: uuid.UUID, session: DbSession, principal: User) -> dict[str, Any]:
    with session.begin():
        job = jobs.own(session, job_id, principal.user_id, admin=_admin(principal), lock=True)
        jobs.retry(session, job)
        session.flush()
        out = jobs.view(job)
    jobs.kick()
    return out


# ------------------------------------------------------------------ administrators


@router.get("/admin/research/status")
def retrieval_status(_: Admin) -> dict[str, Any]:
    """Whether page retrieval and scheduled reports are set up (no secret values)."""
    return schedules.status()


@router.get("/admin/report-schedules")
def list_schedules(session: DbSession, _: Admin) -> list[dict[str, Any]]:
    with session.begin():
        return schedules.list_all(session)


@router.post("/admin/report-schedules", status_code=201)
def create_schedule(body: dict[str, Any], session: DbSession, principal: Admin) -> dict[str, Any]:
    with session.begin():
        row = schedules.create(session, body, principal.user_id)
        flags = {"enabled": row["enabled"], "paid": row["paid"]}
        audit.record(session, principal, "report_schedule.create", entity_type="report_schedule",
                     entity_id=row["id"], metadata=flags)  # fmt: skip
        return row


@router.put("/admin/report-schedules/{schedule_id}")
def update_schedule(
    schedule_id: uuid.UUID, body: dict[str, Any], session: DbSession, principal: Admin
) -> dict[str, Any]:
    with session.begin():
        row = schedules.update(session, schedule_id, body)
        flags = {"enabled": row["enabled"], "paid": row["paid"]}
        audit.record(session, principal, "report_schedule.update", entity_type="report_schedule",
                     entity_id=schedule_id, metadata=flags)  # fmt: skip
        return row


@router.delete("/admin/report-schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: uuid.UUID, session: DbSession, principal: Admin) -> Response:
    with session.begin():
        schedules.delete(session, schedule_id)
        audit.record(session, principal, "report_schedule.delete", entity_type="report_schedule",
                     entity_id=schedule_id)  # fmt: skip
    return Response(status_code=204)


@router.post("/admin/report-schedules/{schedule_id}/run", status_code=202)
def run_schedule_now(
    schedule_id: uuid.UUID, session: DbSession, principal: Admin
) -> dict[str, Any]:
    """One run now, within the schedule's limits (also when it is not enabled)."""
    with session.begin():
        out = schedules.run_now(session, schedule_id)
        audit.record(session, principal, "report_schedule.run", entity_type="report_schedule",
                     entity_id=schedule_id)  # fmt: skip
    jobs.kick()
    return out
