"""Research library: source library, saved research with downloadable briefs, indicator
watchlists with alert rules, alert events, and comparable governorate views."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_authenticated
from app.core.errors import unprocessable
from app.domain.enums import DataMode
from app.models import Indicator
from app.services import alerts, comparisons, library
from app.services.principal import Principal

router = APIRouter(tags=["library"])
Authed = Annotated[Principal, Depends(require_authenticated)]
PeriodKind = Literal["annual", "year_to_date", "quarterly", "monthly", "statement"]


# ------------------------------------------------------------------ source library


@router.get("/library/sources")
def source_library(
    session: DbSession,
    principal: CurrentPrincipal,
    q: str | None = None,
    source_class: Literal[
        "official", "international", "research", "secondary", "reference_pack", "dataset", "web"
    ]
    | None = None,
    domain: Literal["electricity", "water", "food", "trade"] | None = None,
) -> dict[str, Any]:
    with session.begin():
        return library.sources(
            session,
            principal if principal.is_authenticated else None,
            q=q[:100] if q else None,
            source_class=source_class,
            domain=domain,
        )


# ------------------------------------------------------------------ saved research


class SaveIn(BaseModel):
    message_id: int
    title: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=4000)


class SavedUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=4000)


@router.get("/library/saved")
def saved_list(session: DbSession, principal: Authed) -> list[dict[str, Any]]:
    with session.begin():
        return library.list_saved(session, principal)


@router.post("/library/saved", status_code=201)
def saved_create(body: SaveIn, session: DbSession, principal: Authed) -> dict[str, Any]:
    with session.begin():
        return library.save(session, principal, body.message_id, body.title, body.note)


@router.get("/library/saved/{saved_id}")
def saved_get(saved_id: uuid.UUID, session: DbSession, principal: Authed) -> dict[str, Any]:
    with session.begin():
        return library.get_saved(session, principal, saved_id)


@router.patch("/library/saved/{saved_id}")
def saved_update(
    saved_id: uuid.UUID, body: SavedUpdateIn, session: DbSession, principal: Authed
) -> dict[str, Any]:
    with session.begin():
        return library.update_saved(session, principal, saved_id, body.title, body.note)


@router.delete("/library/saved/{saved_id}", status_code=204)
def saved_delete(saved_id: uuid.UUID, session: DbSession, principal: Authed) -> Response:
    with session.begin():
        library.delete_saved(session, principal, saved_id)
    return Response(status_code=204)


@router.get("/library/saved/{saved_id}/brief")
def saved_brief(
    saved_id: uuid.UUID,
    session: DbSession,
    principal: Authed,
    format: Literal["md", "html"] = "html",  # noqa: A002 - public query parameter name
) -> Response:
    with session.begin():
        content, media_type, filename = library.brief(session, principal, saved_id, format)
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            # The brief is a document, not an app page: no scripts run in it.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        },
    )


# ------------------------------------------------------------------ watchlist and alerts


class WatchIn(BaseModel):
    indicator: str = Field(max_length=64)
    area: str = Field(default="OM", max_length=32)
    period_kind: PeriodKind = "annual"
    data_mode: DataMode


class RuleIn(BaseModel):
    kind: Literal["new_data", "above", "below"]
    threshold: Decimal | None = None
    channel: Literal["in_app", "email"] = "in_app"


class RuleUpdateIn(BaseModel):
    enabled: bool | None = None
    channel: Literal["in_app", "email"] | None = None
    threshold: Decimal | None = None


@router.get("/watchlist")
def watchlist(session: DbSession, principal: Authed) -> list[dict[str, Any]]:
    with session.begin():
        return alerts.list_items(session, principal)


@router.post("/watchlist", status_code=201)
def watch(body: WatchIn, session: DbSession, principal: Authed) -> dict[str, Any]:
    with session.begin():
        return alerts.add_item(
            session, principal, body.indicator, body.area, body.period_kind, body.data_mode
        )


@router.delete("/watchlist/{item_id}", status_code=204)
def unwatch(item_id: int, session: DbSession, principal: Authed) -> Response:
    with session.begin():
        alerts.remove_item(session, principal, item_id)
    return Response(status_code=204)


@router.post("/watchlist/{item_id}/rules", status_code=201)
def add_rule(item_id: int, body: RuleIn, session: DbSession, principal: Authed) -> dict[str, Any]:
    with session.begin():
        return alerts.add_rule(session, principal, item_id, body.kind, body.threshold, body.channel)


@router.patch("/alerts/rules/{rule_id}")
def update_rule(
    rule_id: int, body: RuleUpdateIn, session: DbSession, principal: Authed
) -> dict[str, Any]:
    with session.begin():
        return alerts.update_rule(
            session,
            principal,
            rule_id,
            enabled=body.enabled,
            channel=body.channel,
            threshold=body.threshold,
        )


@router.delete("/alerts/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: DbSession, principal: Authed) -> Response:
    with session.begin():
        alerts.delete_rule(session, principal, rule_id)
    return Response(status_code=204)


@router.get("/alerts")
def alert_events(
    session: DbSession, principal: Authed, unread_only: bool = False
) -> dict[str, Any]:
    with session.begin():
        return alerts.list_events(session, principal, unread_only)


class ReadIn(BaseModel):
    event_id: int | None = None


@router.post("/alerts/read")
def alerts_read(body: ReadIn, session: DbSession, principal: Authed) -> dict[str, int]:
    with session.begin():
        return {"marked": alerts.mark_read(session, principal, body.event_id)}


# ------------------------------------------------------------------ comparable areas


@router.get("/areas/compare")
def compare(
    session: DbSession,
    indicator: str,
    data_mode: DataMode,
    period_kind: PeriodKind = "annual",
    period_start: date | None = None,
    level: Literal["governorate", "wilayat"] = "governorate",
    flow: Literal["import", "domestic_export", "re_export"] | None = None,
) -> dict[str, Any]:
    with session.begin():
        if session.scalar(select(Indicator.id).where(Indicator.code == indicator)) is None:
            raise unprocessable("unknown_indicator", "That indicator does not exist.")
        result = comparisons.compare_areas(
            session, data_mode, indicator, period_kind, period_start, level, flow
        )
        return comparisons.public(result)
