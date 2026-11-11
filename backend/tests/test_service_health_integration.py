"""The administrator's Service Health view: API usage and estimated cost per provider over 24
hours and 30 days (refusals by OSRIP's own limits kept apart from calls and failures), the
official-statistics feeds with releases awaiting approval, and response times of this process
by route pattern. Only people who may read the audit log see it."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete

from app.domain.enums import Role
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration
PROVIDER = "health-check-provider"


@pytest.fixture
def calls():  # noqa: ANN201
    from app.db.session import session_factory
    from app.models import ProviderCall

    now = datetime.now(UTC)
    rows = [
        dict(status="ok", input_tokens=100, output_tokens=40, estimated_cost_usd=Decimal("0.002"),
             duration_ms=900, created_at=now - timedelta(hours=1)),
        dict(status="timeout", input_tokens=None, output_tokens=None, estimated_cost_usd=None,
             duration_ms=3000, created_at=now - timedelta(hours=2)),
        dict(status="daily_limit", input_tokens=None, output_tokens=None, estimated_cost_usd=None,
             duration_ms=0, created_at=now - timedelta(hours=3)),
        dict(status="ok", input_tokens=500, output_tokens=200, estimated_cost_usd=Decimal("0.010"),
             duration_ms=1100, created_at=now - timedelta(days=10)),
        dict(status="ok", input_tokens=999, output_tokens=999, estimated_cost_usd=Decimal("9"),
             duration_ms=1, created_at=now - timedelta(days=40)),
    ]  # fmt: skip
    with session_factory()() as s, s.begin():
        s.add_all(
            ProviderCall(provider=PROVIDER, capability="answer", model="m", **r) for r in rows
        )
    yield
    with session_factory()() as s, s.begin():
        s.execute(delete(ProviderCall).where(ProviderCall.provider == PROVIDER))


def test_usage_costs_sync_and_performance(make_user, login, calls, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    viewer = login(make_user())
    admin = login(make_user(Role.ADMINISTRATOR))
    assert viewer.get(f"{API}/admin/monitoring").status_code == 403

    view = admin.get(f"{API}/admin/monitoring").json()
    day = next(u for u in view["usage"]["windows"]["day"] if u["provider"] == PROVIDER)
    month = next(u for u in view["usage"]["windows"]["month"] if u["provider"] == PROVIDER)
    assert (day["calls"], day["failures"], day["refused"]) == (2, 1, 1)
    assert (day["input_tokens"], day["output_tokens"]) == (100, 40)
    assert day["average_ms"] == 1950, "refusals are not calls and have no duration"
    assert (month["calls"], month["input_tokens"]) == (3, 600), "40 days ago is outside"
    assert day["estimated_cost_usd"] is None, "no prices configured: the cost is unknown"

    monkeypatch.setattr(get_settings(), "provider_prices", {PROVIDER: {"input": 1.0}})
    priced = admin.get(f"{API}/admin/monitoring").json()["usage"]
    month = next(u for u in priced["windows"]["month"] if u["provider"] == PROVIDER)
    assert month["estimated_cost_usd"] == pytest.approx(0.012) and PROVIDER in priced["priced"]

    # Feeds come with their schedule and approvals waiting; nothing secret in the view.
    for feed in view["sync"]:
        assert {
            "code",
            "enabled",
            "auto_publish",
            "last_success_at",
            "awaiting_approval",
        } <= feed.keys()
    assert "secret" not in json.dumps(view).lower()

    # Response times by route pattern, never the concrete path or its query.
    from app.services import monitoring

    admin.delete(f"{API}/admin/groups/00000000-0000-0000-0000-000000000000?x=private")
    perf = admin.get(f"{API}/admin/monitoring").json()["performance"]
    assert perf["requests"] >= 3 and perf["p50_ms"] is not None
    assert perf["p50_ms"] <= perf["p95_ms"] <= perf["max_ms"]
    assert len(perf["slowest"]) <= 5
    recorded = [route for route, _, _ in monitoring._timings]
    assert "DELETE /admin/groups/{group_id}" in recorded
    assert not any("private" in r or "00000000" in r for r in recorded)
