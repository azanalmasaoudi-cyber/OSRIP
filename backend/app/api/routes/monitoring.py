"""Service health, readiness, browser error reports and the monitoring view."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DbSession, require
from app.core import ratelimit, security
from app.core.config import get_settings
from app.domain.enums import Permission
from app.services import monitoring, providers
from app.services.principal import Principal

router = APIRouter(tags=["monitoring"])
CLIENT_ERRORS_PER_HOUR = 30
PROVIDER_TESTS_PER_HOUR = 20


@router.get("/health/ready")
def ready(session: DbSession, response: Response) -> dict[str, Any]:
    """Readiness for load balancers: database reachable and migration version. 503 if not."""
    with session.begin():
        result = monitoring.readiness(session)
    if not result["ready"]:
        response.status_code = 503
    return result


class ClientErrorIn(BaseModel):
    kind: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    location: str | None = Field(default=None, max_length=2000)


@router.post("/telemetry/client-errors", status_code=204)
def client_error(body: ClientErrorIn, request: Request) -> Response:
    """Browser error report. No cookies or identity used; limited per client address."""
    client = request.client.host if request.client else "unknown"
    key = security.keyed_digest(get_settings().client_hash_key.get_secret_value(), client)
    ratelimit.check(f"client-error:{key}", CLIENT_ERRORS_PER_HOUR, 3600)
    monitoring.record_error("client", body.kind, body.message, body.location, None)
    return Response(status_code=204)


@router.get("/admin/monitoring")
def monitoring_view(
    session: DbSession, _: Annotated[Principal, Depends(require(Permission.AUDIT_READ))]
) -> dict[str, Any]:
    with session.begin():
        return {**monitoring.readiness(session), "errors": monitoring.recent_errors(session)}


@router.get("/admin/providers")
def provider_readiness(
    _: Annotated[Principal, Depends(require(Permission.AUDIT_READ))],
) -> dict[str, Any]:
    """AI and search providers: configured, tested, unavailable or failed, which role each
    plays, today's calls and limits. Names of missing settings only, never values."""
    return providers.readiness()


@router.post("/admin/providers/{name}/test")
def provider_test(
    name: Literal["anthropic", "openai", "gemini", "deepseek", "brave", "firecrawl"],
    _: Annotated[Principal, Depends(require(Permission.AUDIT_READ))],
    principal: Annotated[Principal, Depends(require(Permission.USER_MANAGE))],
    capability: Literal["answer", "search", "retrieve"] = "answer",
) -> dict[str, Any]:
    """One minimal live call to check a provider really works (it may cost a little), so it
    needs an administrator (``user.manage``) besides the read permission of the view."""
    ratelimit.check(f"provider-test:{principal.user_id}", PROVIDER_TESTS_PER_HOUR, 3600)
    result = providers.run_test(name, capability)
    return {**result, "readiness": providers.state(name)}
