"""Remember me (migration 0027): without it the session cookie ends with the browser and the
server keeps its 8-hour limit and 30-minute idle limit; with it the cookie and the server
session last session_remember_days on that device, and an idle gap that would end an ordinary
session does not end it. Signing out still ends it at once."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


def _sign_in(app, person, remember: bool):  # noqa: ANN001, ANN202
    client = TestClient(app)
    response = client.post(
        f"{API}/auth/login",
        json={"username": person.username, "password": person.password, "remember": remember},
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    cookie = next(
        h for h in response.headers.get_list("set-cookie") if h.startswith("osrip_session=")
    )
    return client, cookie


def _age_sessions(user_id, minutes: int) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.models import UserSession

    with session_factory()() as s, s.begin():
        s.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(last_seen_at=datetime.now(UTC) - timedelta(minutes=minutes))
        )


def test_ordinary_sign_in_ends_with_the_browser_and_the_idle_limit(app, make_user) -> None:  # noqa: ANN001
    person = make_user()
    client, cookie = _sign_in(app, person, remember=False)
    assert "max-age" not in cookie.lower(), "a browser-session cookie"
    assert client.get(f"{API}/auth/me").json()["authenticated"] is True
    _age_sessions(person.id, 45)  # longer than the 30-minute idle limit
    assert client.get(f"{API}/auth/me").json()["authenticated"] is False


def test_remember_me_keeps_the_session_on_this_device(app, make_user) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.models import UserSession

    person = make_user()
    client, cookie = _sign_in(app, person, remember=True)
    assert f"max-age={14 * 86400}" in cookie.lower()
    with session_factory()() as s:
        row = s.scalar(select(UserSession).where(UserSession.user_id == person.id))
        assert row is not None and row.persistent is True
        assert row.expires_at - row.created_at > timedelta(days=13)
    _age_sessions(person.id, 6 * 60)  # an idle gap that ends an ordinary session
    assert client.get(f"{API}/auth/me").json()["authenticated"] is True
    assert client.post(f"{API}/auth/logout").status_code in (200, 204)
    assert client.get(f"{API}/auth/me").json()["authenticated"] is False
