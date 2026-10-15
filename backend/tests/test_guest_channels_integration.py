"""One five-answer guest allowance across every way of asking (Stage 7): typed questions in
English and Arabic, research mode with web search, compare mode and spoken questions through
the voice bridge all draw on the same server-side count; after five answers each channel is
refused the same way, while greetings stay free. Self-registration cannot grant roles,
permissions or a verified state, whatever extra fields are sent.

The count is per guest session (an HttpOnly cookie): the interface says it is a fair-use
measure, and nothing here pretends it is enforced across devices or browsers.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select, text

from app.core.errors import ApiError
from app.domain.enums import DataMode
from app.voice import bridge
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def setup(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "research_provider", "fake")
    monkeypatch.setattr(s, "speech_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    ratelimit.reset()
    with session_factory()() as session:
        seed_booklet_fixtures(session)


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _guest_id(client) -> uuid.UUID:  # noqa: ANN001
    from app.core import security
    from app.db.session import session_factory
    from app.models import GuestSession

    digest = security.token_digest(client.cookies["osrip_guest"])
    with session_factory()() as s:
        return s.scalar(select(GuestSession.id).where(GuestSession.token_hash == digest))


def _ask(client, content: str, **extra: Any):  # noqa: ANN001, ANN202
    return client.post(
        f"{API}/assistant/guest/messages",
        json={"content": content, "language": extra.pop("language", "en"),
              "request_id": str(uuid.uuid4()), "data_mode": "synthetic", **extra},
    )  # fmt: skip


def test_the_allowance_is_shared_by_text_research_languages_and_voice(app, db) -> None:  # noqa: ANN001
    client = _guest(app)
    call = bridge.Call(
        bridge.Caller("guest", _guest_id(client)), "ar", data_mode=DataMode.SYNTHETIC
    )
    used: list[str] = []

    r = _ask(client, "What is the latest electricity generation?")
    assert r.status_code == 201 and r.json()["message"]["status"] == "answered"
    used.append("text-en")
    r = _ask(client, "Search the web for electricity generation", mode="research")
    assert r.status_code == 201 and r.json()["message"]["status"] == "answered", r.text
    research_message = r.json()["message"]["id"]
    used.append("research")
    r = _ask(client, "ما آخر قيمة لتوليد الكهرباء؟", language="ar")
    assert r.status_code == 201 and r.json()["message"]["status"] == "answered"
    used.append("text-ar")
    spoken = bridge.answer(call, "ما آخر قيمة لتوليد الكهرباء؟")
    assert spoken["status"] == "answered"
    used.append("voice")
    r = _ask(client, "What is the latest electricity generation?", mode="compare")
    assert r.status_code == 201
    used.append("compare")

    status = client.get(f"{API}/assistant/guest").json()["allowance"]
    assert status["used"] == 5 and status["remaining"] == 0 and len(used) == 5

    # Every channel is now refused the same way, before any answer is attempted.
    for refused in (
        _ask(client, "What is the latest electricity generation?"),
        _ask(client, "ما آخر قيمة لتوليد الكهرباء؟", language="ar"),
        _ask(client, "Search the web for electricity generation", mode="research"),
    ):
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "guest_allowance_exhausted"
    with pytest.raises(ApiError) as voice_refused:
        bridge.answer(call, "What is the latest electricity generation?")
    assert voice_refused.value.code == "guest_allowance_exhausted"
    # Server speech for questions is closed too (it only serves the assistant).
    transcribe = client.post(
        f"{API}/assistant/voice/transcribe", params={"language": "en"}, content=b"RIFF",
        headers={"Content-Type": "audio/wav"},
    )  # fmt: skip
    assert transcribe.status_code == 403

    # Greetings are approved replies, not answers: still free, by text and by voice.
    hello = _ask(client, "السلام عليكم", language="ar")
    assert hello.status_code == 201 and hello.json()["message"]["status"] == "profile"
    assert bridge.answer(call, "السلام عليكم")["status"] == "profile"
    assert client.get(f"{API}/assistant/guest").json()["allowance"]["used"] == 5

    # The research answer's web figure went to the review queue; remove it so later modules
    # that check that queue find their own candidate (candidates are de-duplicated).
    with db.begin():
        db.execute(
            text("DELETE FROM research_candidate WHERE message_id = :m"), {"m": research_message}
        )


def test_another_browser_starts_its_own_count_and_says_so(app) -> None:  # noqa: ANN001
    first, second = _guest(app), _guest(app)
    assert _ask(first, "What is the latest electricity generation?").status_code == 201
    a = first.get(f"{API}/assistant/guest").json()
    b = second.get(f"{API}/assistant/guest").json()
    assert a["allowance"]["used"] == 1 and b["allowance"]["used"] == 0
    # The notice is honest that this is a per-browser fair-use measure.
    assert "fair-use measure, not a guarantee" in b["notice"]["en"]


def test_registration_ignores_requested_roles_permissions_and_verification(anonymous, db) -> None:  # noqa: ANN001
    from app.models import AppUser, UserPermissionGrant, UserRole

    address = f"sneaky-{uuid.uuid4().hex[:8]}@test.invalid"
    r = anonymous.post(
        f"{API}/auth/register",
        json={"email": address, "display_name": "X", "password": "pw-a-long-enough-password-1",
              "roles": ["admin", "data_manager"], "permissions": ["user.manage", "import.publish"],
              "email_verified": True, "email_verified_at": "2026-01-01T00:00:00Z", "status": "active"},
    )  # fmt: skip
    assert r.status_code == 202, r.text
    user = db.scalar(select(AppUser).where(AppUser.email == address))
    assert user is not None and user.email_verified_at is None
    roles = set(db.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id)))
    assert roles == {"viewer"}
    grants = list(
        db.scalars(
            select(UserPermissionGrant.permission_code).where(
                UserPermissionGrant.user_id == user.id
            )
        )
    )
    assert grants == []
    # Unverified: the password alone does not open a session.
    login = anonymous.post(
        f"{API}/auth/login", json={"email": address, "password": "pw-a-long-enough-password-1"}
    )
    assert login.status_code == 403 and login.json()["error"]["code"] == "email_not_verified"
