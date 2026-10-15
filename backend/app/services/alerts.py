"""Indicator watchlists and data-update / threshold alerts, with user controls.

* A watchlist item is one series a user follows: indicator, area, period kind, data mode.
* A rule on an item is ``new_data`` (any newly published or revised value), ``above`` or
  ``below`` a threshold in the unit the platform displays. Rules can be switched off,
  changed or deleted at any time; the channel is in-app or e-mail.
* Evaluation runs inside the publication transaction (``evaluate_version``), so alerts
  exist only for data that was actually published. A value counts as new when no
  earlier published value exists for that series and period, and as revised when the
  earlier value differs; republishing an unchanged value raises nothing.
* E-mail is delivered after the publication commits (``deliver_pending``); a failure is
  recorded on the event and never undoes the publication.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found, unprocessable
from app.domain import calculations as calc
from app.domain.enums import DataMode, DatasetVersionStatus, PhysicalDimension
from app.domain.quantities import Measurement, Period
from app.domain.quantities import Unit as QUnit
from app.models import (
    AlertEvent,
    AlertRule,
    AppUser,
    Area,
    DatasetVersion,
    Indicator,
    Observation,
    Unit,
    WatchlistItem,
)
from app.services import mail
from app.services.observations import (
    PERIOD_KINDS,
    ObservationQuery,
    conversions,
    period_kind,
    query_observations,
)
from app.services.principal import Principal

KINDS = ("new_data", "above", "below")
CHANNELS = ("in_app", "email")
MAX_ITEMS = 50
PUBLIC_STATUSES = (DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.SUPERSEDED)


def _now() -> datetime:
    return datetime.now(UTC)


def _num(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


# ------------------------------------------------------------------ watchlist


def _item(session: Session, principal: Principal, item_id: int) -> WatchlistItem:
    item = session.get(WatchlistItem, item_id)
    if item is None or item.user_id != principal.user_id:
        raise not_found("watchlist item")
    return item


def add_item(
    session: Session,
    principal: Principal,
    indicator_code: str,
    area_code: str,
    period_kind_: str,
    data_mode: DataMode,
) -> dict[str, Any]:
    if period_kind_ not in PERIOD_KINDS:
        raise unprocessable(
            "invalid_period_kind", "Choose annual, year_to_date, quarterly, monthly or statement."
        )
    if session.scalar(select(Indicator.id).where(Indicator.code == indicator_code)) is None:
        raise unprocessable("unknown_indicator", "That indicator does not exist.")
    if session.scalar(select(Area.id).where(Area.code == area_code)) is None:
        raise unprocessable("unknown_area", "That area does not exist.")
    existing = session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == principal.user_id,
            WatchlistItem.indicator_code == indicator_code,
            WatchlistItem.area_code == area_code,
            WatchlistItem.period_kind == period_kind_,
            WatchlistItem.data_mode == data_mode,
        )
    )
    if existing is None:
        count = (
            session.scalar(select(func.count()).where(WatchlistItem.user_id == principal.user_id))
            or 0
        )
        if count >= MAX_ITEMS:
            raise unprocessable("watchlist_full", f"A watchlist holds at most {MAX_ITEMS} series.")
        existing = WatchlistItem(
            user_id=principal.user_id,
            indicator_code=indicator_code,
            area_code=area_code,
            period_kind=period_kind_,
            data_mode=data_mode,
        )
        session.add(existing)
        session.flush()
    return item_out(session, existing)


def remove_item(session: Session, principal: Principal, item_id: int) -> None:
    session.delete(_item(session, principal, item_id))


def _latest_two(session: Session, item: WatchlistItem) -> tuple[Any, list[dict[str, Any]]]:
    series = [
        s
        for s in query_observations(
            session,
            ObservationQuery(
                item.data_mode,
                indicator=item.indicator_code,
                area=item.area_code,
                period_kind=item.period_kind,
            ),
            allow_mixed=True,
        )
        if s.meta["partner"] is None and s.meta["commodity"] is None
    ]
    if not series:
        return None, []
    s = series[0]
    with_values = [o for o in s.observations if o["value"] is not None]
    return s, with_values[-2:]


def item_out(session: Session, item: WatchlistItem) -> dict[str, Any]:
    ind = session.scalar(select(Indicator).where(Indicator.code == item.indicator_code))
    area = session.scalar(select(Area).where(Area.code == item.area_code))
    s, last = _latest_two(session, item)
    latest = last[-1] if last else None
    change = None
    if s is not None and len(last) == 2:
        unit = QUnit(s.meta["unit"]["code"], PhysicalDimension(s.meta["unit"]["dimension"]))

        def m(o: dict[str, Any]) -> Measurement:
            return Measurement(
                Decimal(o["value"]),
                unit,
                Period(
                    datetime.fromisoformat(o["period_start"]).date(),
                    datetime.fromisoformat(o["period_end"]).date(),
                    o["period_complete"],
                ),
                item.area_code,
            )

        r = calc.percentage_change(m(last[0]), m(last[1]))
        change = {
            "status": r.status.value,
            "percent": _num(r.value),
            "previous_period_start": last[0]["period_start"],
            "previous_value": last[0]["value"],
        }
    rules = session.scalars(
        select(AlertRule).where(AlertRule.watchlist_item_id == item.id).order_by(AlertRule.id)
    ).all()
    return {
        "id": item.id,
        "indicator": {
            "code": item.indicator_code,
            "name": {"en": ind.name_en, "ar": ind.name_ar} if ind else None,
        },
        "area": {
            "code": item.area_code,
            "name": {"en": area.name_en, "ar": area.name_ar} if area else None,
        },
        "period_kind": item.period_kind,
        "data_mode": item.data_mode.value,
        "unit": s.meta["unit"] if s is not None else None,
        "latest": None
        if latest is None
        else {
            "period_start": latest["period_start"],
            "period_end": latest["period_end"],
            "value": latest["value"],
            "value_operator": latest.get("value_operator"),
            "revision_status": latest.get("revision_status"),
            "source": s.meta["source"]["dataset_title"],
        },
        # Platform arithmetic between the two latest published values of the same series.
        "change": change,
        "rules": [rule_out(r) for r in rules],
    }


def list_items(session: Session, principal: Principal) -> list[dict[str, Any]]:
    items = session.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == principal.user_id)
        .order_by(WatchlistItem.created_at)
    ).all()
    return [item_out(session, i) for i in items]


# ------------------------------------------------------------------ rules


def rule_out(r: AlertRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "kind": r.kind,
        "threshold": _num(r.threshold),
        "enabled": r.enabled,
        "channel": r.channel,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
    }


def _check_channel(session: Session, principal: Principal, channel: str) -> None:
    if channel not in CHANNELS:
        raise unprocessable("invalid_channel", "Choose in_app or email.")
    if channel == "email":
        if mail.delivery_mode() == "disabled":
            raise ApiError(
                503,
                "email_not_configured",
                "E-mail delivery is not configured on this server; use in-app alerts.",
            )
        user = session.get(AppUser, principal.user_id)
        if user is None or not user.email or user.email_verified_at is None:
            raise unprocessable(
                "verified_email_required",
                "Add and confirm an e-mail address to receive alerts by e-mail.",
            )


def _threshold(kind: str, threshold: Any) -> Decimal | None:
    if kind not in KINDS:
        raise unprocessable("invalid_kind", "Choose new_data, above or below.")
    if kind == "new_data":
        return None
    try:
        value = Decimal(str(threshold))
    except (InvalidOperation, TypeError):
        value = None
    if value is None or not value.is_finite():
        raise unprocessable("threshold_required", "Give the threshold value, in the unit shown.")
    return value


def add_rule(
    session: Session,
    principal: Principal,
    item_id: int,
    kind: str,
    threshold: Any = None,
    channel: str = "in_app",
) -> dict[str, Any]:
    item = _item(session, principal, item_id)
    value = _threshold(kind, threshold)
    _check_channel(session, principal, channel)
    rule = AlertRule(
        user_id=principal.user_id,
        watchlist_item_id=item.id,
        kind=kind,
        threshold=value,
        channel=channel,
    )
    session.add(rule)
    session.flush()
    session.refresh(rule)
    return rule_out(rule)


def _rule(session: Session, principal: Principal, rule_id: int) -> AlertRule:
    rule = session.get(AlertRule, rule_id)
    if rule is None or rule.user_id != principal.user_id:
        raise not_found("alert rule")
    return rule


def update_rule(
    session: Session,
    principal: Principal,
    rule_id: int,
    *,
    enabled: bool | None = None,
    channel: str | None = None,
    threshold: Any = None,
) -> dict[str, Any]:
    rule = _rule(session, principal, rule_id)
    if enabled is not None:
        rule.enabled = enabled
    if channel is not None and channel != rule.channel:
        _check_channel(session, principal, channel)
        rule.channel = channel
    if threshold is not None:
        rule.threshold = _threshold(rule.kind, threshold)
    session.flush()
    return rule_out(rule)


def delete_rule(session: Session, principal: Principal, rule_id: int) -> None:
    session.delete(_rule(session, principal, rule_id))


# ------------------------------------------------------------------ events


def event_out(e: AlertEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "rule_id": e.rule_id,
        "kind": e.kind,
        "indicator_code": e.indicator_code,
        "area_code": e.area_code,
        "value": _num(e.value),
        "unit": e.unit,
        "period_start": e.period_start.isoformat(),
        "period_end": e.period_end.isoformat(),
        "threshold": _num(e.threshold),
        "message": {"en": e.message_en, "ar": e.message_ar},
        "delivery": e.delivery,
        "created_at": e.created_at.isoformat(),
        "read_at": e.read_at.isoformat() if e.read_at else None,
    }


def list_events(
    session: Session, principal: Principal, unread_only: bool = False
) -> dict[str, Any]:
    stmt = select(AlertEvent).where(AlertEvent.user_id == principal.user_id)
    if unread_only:
        stmt = stmt.where(AlertEvent.read_at.is_(None))
    events = session.scalars(stmt.order_by(AlertEvent.created_at.desc()).limit(100)).all()
    unread = (
        session.scalar(
            select(func.count()).where(
                AlertEvent.user_id == principal.user_id, AlertEvent.read_at.is_(None)
            )
        )
        or 0
    )
    return {"unread": unread, "events": [event_out(e) for e in events]}


def mark_read(session: Session, principal: Principal, event_id: int | None = None) -> int:
    stmt = (
        update(AlertEvent)
        .where(AlertEvent.user_id == principal.user_id, AlertEvent.read_at.is_(None))
        .values(read_at=_now())
        .execution_options(synchronize_session=False)
    )
    if event_id is not None:
        stmt = stmt.where(AlertEvent.id == event_id)
    return session.execute(stmt).rowcount or 0


# ------------------------------------------------------------------ evaluation


def _message(
    kind: str,
    change: str,
    ind: Indicator,
    area: Area,
    value: str | None,
    unit: str,
    period: str,
    threshold: str | None,
) -> tuple[str, str]:
    shown = value if value is not None else "missing in the source"
    shown_ar = value if value is not None else "مفقودة في المصدر"
    what_en = {"new": "New published value", "revised": "Revised published value"}[change]
    what_ar = {"new": "قيمة منشورة جديدة", "revised": "قيمة منشورة منقحة"}[change]
    en = f"{what_en}: {ind.name_en}, {area.name_en}, {period}: {shown} {unit}."
    ar = f"{what_ar}: {ind.name_ar}، {area.name_ar}، {period}: {shown_ar} {unit}."
    if kind == "above":
        en += f" It is above your threshold of {threshold} {unit}."
        ar += f" وهي أعلى من الحد الذي حددته ({threshold} {unit})."
    elif kind == "below":
        en += f" It is below your threshold of {threshold} {unit}."
        ar += f" وهي أدنى من الحد الذي حددته ({threshold} {unit})."
    return en, ar


def evaluate_version(session: Session, version: DatasetVersion) -> int:
    """Create alert events for the newly published or revised values of ``version``.
    Runs inside the publication transaction; returns the number of events."""
    rows = session.execute(
        select(Observation, Indicator, Area, Unit)
        .join(Indicator, Indicator.id == Observation.indicator_id)
        .join(Area, Area.id == Observation.area_id)
        .join(Unit, Unit.id == Observation.unit_id)
        .where(
            Observation.dataset_version_id == version.id,
            Observation.partner_id.is_(None),
            Observation.commodity_id.is_(None),
        )
    ).all()
    if not rows:
        return 0
    keys = {(ind.code, area.code) for _, ind, area, _ in rows}
    watched = session.execute(
        select(WatchlistItem, AlertRule)
        .join(AlertRule, AlertRule.watchlist_item_id == WatchlistItem.id)
        .where(
            AlertRule.enabled.is_(True),
            WatchlistItem.data_mode == version.data_mode,
            WatchlistItem.indicator_code.in_({k[0] for k in keys}),
            WatchlistItem.area_code.in_({k[1] for k in keys}),
        )
    ).all()
    if not watched:
        return 0
    factors = conversions(session)
    display_units = {
        code: unit_code
        for code, unit_code in session.execute(
            select(Indicator.code, Indicator.display_unit_code).where(
                Indicator.code.in_({k[0] for k in keys})
            )
        )
    }
    created = 0
    for obs, ind, area, unit in rows:
        kind_of = period_kind(obs)
        matches = [
            (w, r)
            for w, r in watched
            if w.indicator_code == ind.code
            and w.area_code == area.code
            and w.period_kind == kind_of
        ]
        if not matches:
            continue
        earlier = session.scalar(
            select(Observation.value)
            .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
            .where(
                Observation.indicator_id == obs.indicator_id,
                Observation.area_id == obs.area_id,
                Observation.period_start == obs.period_start,
                Observation.period_end == obs.period_end,
                Observation.data_mode == obs.data_mode,
                Observation.dataset_version_id != version.id,
                Observation.partner_id.is_(None),
                Observation.commodity_id.is_(None),
                DatasetVersion.status.in_(PUBLIC_STATUSES),
            )
            .order_by(DatasetVersion.published_at.desc().nulls_last())
            .limit(1)
        )
        had_earlier = session.scalar(
            select(func.count())
            .select_from(Observation)
            .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
            .where(
                Observation.indicator_id == obs.indicator_id,
                Observation.area_id == obs.area_id,
                Observation.period_start == obs.period_start,
                Observation.period_end == obs.period_end,
                Observation.dataset_version_id != version.id,
                DatasetVersion.status.in_(PUBLIC_STATUSES),
            )
        )
        if had_earlier and earlier == obs.value:
            continue  # republished unchanged: nothing new to report
        change = "revised" if had_earlier else "new"
        target = display_units.get(ind.code)
        factor = factors.get((unit.code, target)) if target and target != unit.code else None
        value = obs.value if factor is None or obs.value is None else obs.value * factor
        shown_unit = target if factor is not None else unit.code
        period = (
            obs.period_start.isoformat()
            if obs.period_start == obs.period_end
            else f"{obs.period_start.isoformat()} to {obs.period_end.isoformat()}"
        )
        for w, r in matches:
            if r.kind == "above" and (value is None or r.threshold is None or value <= r.threshold):
                continue
            if r.kind == "below" and (value is None or r.threshold is None or value >= r.threshold):
                continue
            en, ar = _message(
                r.kind, change, ind, area, _num(value), shown_unit, period, _num(r.threshold)
            )
            exists = session.scalar(
                select(AlertEvent.id).where(
                    AlertEvent.rule_id == r.id,
                    AlertEvent.dataset_version_id == version.id,
                    AlertEvent.period_start == obs.period_start,
                    AlertEvent.period_end == obs.period_end,
                )
            )
            if exists:
                continue
            session.add(
                AlertEvent(
                    rule_id=r.id,
                    user_id=w.user_id,
                    dataset_version_id=version.id,
                    kind=r.kind,
                    indicator_code=ind.code,
                    area_code=area.code,
                    value=value,
                    unit=shown_unit,
                    period_start=obs.period_start,
                    period_end=obs.period_end,
                    threshold=r.threshold,
                    message_en=en,
                    message_ar=ar,
                    delivery="email_pending" if r.channel == "email" else "in_app",
                )
            )
            r.last_triggered_at = _now()
            created += 1
    session.flush()
    return created


def deliver_pending(session: Session) -> dict[str, int]:
    """Send e-mail alerts after publication; failures are recorded per event."""
    counts = {"email_sent": 0, "email_failed": 0, "email_unavailable": 0}
    with session.begin():
        events = session.execute(
            select(AlertEvent, AppUser)
            .join(AppUser, AppUser.id == AlertEvent.user_id)
            .where(AlertEvent.delivery == "email_pending")
            .with_for_update(of=AlertEvent, skip_locked=True)
            .limit(200)
        ).all()
        for event, user in events:
            if (
                not user.email
                or user.email_verified_at is None
                or mail.delivery_mode() == "disabled"
            ):
                event.delivery = "email_unavailable"
            else:
                try:
                    mail.send(
                        session,
                        to=user.email,
                        subject="OSRIP alert: " + event.message_en[:120],
                        body=f"{event.message_en}\n\n{event.message_ar}\n\nManage alerts in OSRIP: "
                        "Research library > Watchlist and alerts.",
                        purpose="alert",
                    )
                    event.delivery = "email_sent"
                except ApiError:
                    event.delivery = "email_failed"
            counts[event.delivery] += 1
    return counts


def owner_of(session: Session, user_id: uuid.UUID) -> AppUser | None:
    return session.get(AppUser, user_id)
