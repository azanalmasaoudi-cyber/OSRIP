"""OSRIP API entry point: ``uvicorn app.main:app --reload``."""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import CSRF_HEADER
from app.api.routes import (
    admin,
    analysis,
    assistant,
    auth,
    balance,
    forecasting,
    geography,
    health,
    imports,
    indicators,
    library,
    observations,
    reference,
    reports,
    research,
    research_jobs,
    series,
    studies,
)
from app.api.routes import (
    monitoring as monitoring_routes,
)
from app.core.config import get_settings
from app.core.errors import ApiError
from app.services import monitoring

logger = logging.getLogger("osrip")


DEV_ONLY_KEY = "development-only-change-me"


def _check_production_settings() -> None:
    """Refuse to start outside development with development-only security settings."""
    settings = get_settings()
    if settings.environment == "development":
        return
    problems = []
    if settings.client_hash_key.get_secret_value() == DEV_ONLY_KEY:
        problems.append("OSRIP_CLIENT_HASH_KEY is the development default")
    if not settings.session_cookie_secure:
        problems.append("OSRIP_SESSION_COOKIE_SECURE is false")
    if settings.email_backend == "outbox":
        problems.append("OSRIP_EMAIL_BACKEND=outbox is a development mail sink")
    for name, value in (
        ("OSRIP_ASSISTANT_PROVIDER", settings.assistant_provider),
        ("OSRIP_ASSISTANT_FALLBACK_PROVIDER", settings.assistant_fallback_provider),
        ("OSRIP_RESEARCH_PROVIDER", settings.research_provider),
        ("OSRIP_RESEARCH_FALLBACK_PROVIDER", settings.research_fallback_provider),
    ):
        if value in ("fake", "fake-openai", "fake-gemini"):
            problems.append(f"{name}={value} is for automated tests only")
    if settings.speech_provider == "fake":
        problems.append("OSRIP_SPEECH_PROVIDER=fake is for automated tests only")
    if any(o.strip() in ("*", "") or not o.startswith("https://") for o in settings.cors_origins):
        problems.append("OSRIP_CORS_ORIGINS must list explicit https:// origins only")
    if settings.sms_provider == "test":
        problems.append("OSRIP_SMS_PROVIDER=test is for automated tests only (codes are not sent)")
    if not settings.public_base_url.startswith("https://"):
        problems.append("OSRIP_PUBLIC_BASE_URL must use https")
    if problems:
        raise RuntimeError(f"Unsafe settings for {settings.environment}: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Server start: studies left queued or interrupted by a restart are resumed, and the
    scheduled-report check starts only if it is switched on (off by default)."""
    from app.services.research import jobs, schedules

    try:
        jobs.kick()
        schedules.start_scheduler()
    except Exception:  # noqa: BLE001 - the API must start even if the database is not ready
        logger.exception("background studies could not be started")
    yield
    schedules.stop_scheduler()


def create_app() -> FastAPI:
    _check_production_settings()
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title="OSRIP API",
        version=monitoring.RELEASE,
        description=(
            "Oman Smart Resource Intelligence Platform - academic prototype. "
            "Not an official statistical service."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER, "X-Guest-CSRF"],
    )

    @app.middleware("http")
    async def request_id_and_errors(request: Request, call_next):  # noqa: ANN001, ANN202
        """Tag every request with an id; capture unhandled exceptions without leaking them."""
        request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - last-resort handler
            logger.error(
                "unhandled %s on %s (request %s)", type(exc).__name__, request.url.path, request_id
            )
            monitoring.record_error(
                "server", type(exc).__name__, str(exc), request.url.path, request_id
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Something went wrong on the server. The error was recorded.",
                        "details": {"request_id": request_id},
                    }
                },
            )
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Some request fields are missing or invalid.",
                    "details": details,
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Log details server-side; never expose internals or credentials (booklet 3.12).
        logger.error("database error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": (
                        "The data store is not available. "
                        "Published snapshots cannot be read right now."
                    ),
                }
            },
        )

    if settings.environment == "development":
        app.include_router(auth.dev_router, prefix=settings.api_prefix)
    for router in (
        health.router,
        monitoring_routes.router,
        indicators.router,
        auth.router,
        admin.router,
        imports.router,
        observations.router,
        series.router,
        geography.router,
        reference.router,
        balance.router,  # before analysis: /analysis/balance is not a section
        analysis.router,
        forecasting.router,
        assistant.router,
        reports.router,
        research.router,
        research_jobs.router,
        library.router,
        studies.router,
    ):
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
