"""Release 0.8: username accounts with a required password change, web research with a
review queue, and server speech. Uses the scripted providers (no network)."""

from __future__ import annotations

import struct
import uuid

import pytest
from sqlalchemy import select, text

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration

TEMP = "Temp@2233"  # a temporary password (8+ characters, must be changed)


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


def _ensure(username: str, password: str = TEMP):  # noqa: ANN202
    from app.db.session import session_factory
    from app.services import accounts
    from app.services.principal import Principal

    with session_factory()() as session, session.begin():
        r = accounts.ensure_username_account(
            session,
            Principal(None, "system:test"),
            username=username,
            display_name=username,
            password=password,
        )
        return r.user.id, r.created


# ------------------------------------------------------------------ accounts


def test_username_account_is_idempotent_and_not_privileged(app, db) -> None:  # noqa: ANN001
    from app.models import AppUser, UserPermissionGrant, UserRole

    name = f"Azz{uuid.uuid4().hex[:6]}"
    user_id, created = _ensure(name)
    assert created
    with db.begin():
        user = db.get(AppUser, user_id)
        first_hash = user.password_hash
        assert user.email is None and user.phone_e164 is None
        assert user.email_verified_at is None and user.phone_verified_at is None
        assert user.password_change_required is True and TEMP not in first_hash
        roles = set(db.scalars(select(UserRole.role_code).where(UserRole.user_id == user_id)))
        grants = list(
            db.scalars(
                select(UserPermissionGrant.permission_code).where(
                    UserPermissionGrant.user_id == user_id
                )
            )
        )
        assert roles == {"viewer"} and grants == []
    # A second run with another password changes nothing (same id, same hash).
    again_id, created_again = _ensure(name.lower(), "Different@99999")
    assert again_id == user_id and not created_again
    db.expire_all()
    with db.begin():
        assert db.get(AppUser, user_id).password_hash == first_hash


def test_temporary_password_must_be_changed_first(app) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    name = f"User{uuid.uuid4().hex[:6]}"
    _ensure(name)
    client = TestClient(app)
    bad = client.post(f"{API}/auth/login", json={"email": name, "password": "wrong-password"})
    assert bad.status_code == 401
    r = client.post(f"{API}/auth/login", json={"email": name.upper(), "password": TEMP})
    assert r.status_code == 200, r.text
    me = r.json()
    assert (
        me["username"] == name
        and me["password_change_required"] is True
        and me["permissions"] == []
    )
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    blocked = client.get(f"{API}/assistant/conversations")
    assert (
        blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    )
    weak = client.post(
        f"{API}/auth/password/change", json={"current_password": TEMP, "new_password": "short"}
    )
    assert weak.status_code == 422
    wrong = client.post(
        f"{API}/auth/password/change",
        json={"current_password": "nope-nope", "new_password": "A-much-longer-password-1"},
    )
    assert wrong.status_code == 403
    ok = client.post(
        f"{API}/auth/password/change",
        json={"current_password": TEMP, "new_password": "A-much-longer-password-1"},
    )
    assert ok.status_code == 200, ok.text
    assert (
        ok.json()["password_change_required"] is False
        and "assistant.use" in ok.json()["permissions"]
    )
    assert client.get(f"{API}/assistant/conversations").status_code == 200
    # The temporary password no longer works.
    other = TestClient(app)
    assert (
        other.post(f"{API}/auth/login", json={"email": name, "password": TEMP}).status_code == 401
    )
    assert client.post(f"{API}/auth/logout").status_code == 204


def test_regular_policy_still_needs_twelve_characters(app, db) -> None:  # noqa: ANN001
    from app.core.errors import ApiError
    from app.services import accounts
    from app.services.principal import Principal

    with pytest.raises(ApiError), db.begin():
        accounts.create_user(
            db,
            Principal(None, "t"),
            email=f"x{uuid.uuid4().hex[:6]}@test.invalid",
            display_name="x",
            password="Short#2026",
        )


# ------------------------------------------------------------------ web research


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _ask(client, content: str, **extra):  # noqa: ANN001, ANN003, ANN202
    return client.post(
        f"{API}/assistant/guest/messages",
        json={
            "content": content,
            "language": "en",
            "request_id": str(uuid.uuid4()),
            "data_mode": "synthetic",
            **extra,
        },
    )


def test_web_answer_cites_official_source_and_queues_candidate(app, db) -> None:  # noqa: ANN001
    status = _guest(app).get(f"{API}/assistant/status").json()
    assert status["web_research"] is True
    client = _guest(app)
    r = _ask(client, "Search the web for electricity generation 2023")
    assert r.status_code == 201, r.text
    body = r.json()
    msg = body["message"]
    assert msg["status"] == "answered" and "41,234" in msg["content"]
    web = [e for e in msg["evidence"] if e["kind"] == "web"]
    searches = [e for e in msg["evidence"] if e["kind"] == "search"]
    assert web and web[0]["source_class"] == "official" and web[0]["evidence_class"] == "official"
    assert web[0]["url"].startswith("https://www.ncsi.gov.om/") and web[0]["retrieved_at"]
    assert web[0]["published"] == "2024-05-02"
    assert searches and searches[0]["status"] == "ok"
    assert body["allowance"]["used"] == 1
    row = (
        db.execute(text("SELECT * FROM research_candidate WHERE message_id = :m"), {"m": msg["id"]})
        .mappings()
        .one()
    )
    assert (
        row["status"] == "pending"
        and row["value_text"] == "41,234"
        and str(row["value"]) == "41234"
    )
    assert row["unit"] == "GWh" and row["geography"] == "Oman" and row["period_label"] == "2023"
    assert row["publisher"] == "National Centre for Statistics and Information"
    assert row["source_url"].startswith("https://") and row["retrieved_at"] is not None
    assert row["publication_date"].isoformat() == "2024-05-02"
    # Nothing was added to the published dataset.
    assert (
        db.execute(
            text("SELECT count(*) FROM observation WHERE source_row LIKE '%41234%'")
        ).scalar()
        == 0
    )


def test_web_switched_off_or_failing_is_reported_and_not_charged(app) -> None:  # noqa: ANN001
    client = _guest(app)
    failed = _ask(client, "web search please fail")
    assert failed.status_code == 201
    body = failed.json()
    assert body["message"]["status"] == "no_evidence" and "failed" in body["message"]["content"]
    assert [e["status"] for e in body["message"]["evidence"] if e["kind"] == "search"] == ["failed"]
    assert body["allowance"]["used"] == 0, "a failed search is not a successful answer"
    off = _ask(client, "web electricity generation", web_research=False)
    assert off.status_code == 201
    assert not [e for e in off.json()["message"]["evidence"] if e["kind"] in ("web", "search")]


def test_review_queue_needs_permission_and_never_publishes(app, make_user, login) -> None:  # noqa: ANN001
    from app.domain.enums import Role

    _ask(_guest(app), "Search the web for electricity generation 2023")
    viewer = login(make_user(Role.VIEWER))
    assert viewer.get(f"{API}/research/candidates").status_code == 403
    manager = login(make_user(Role.DATA_MANAGER))
    items = manager.get(f"{API}/research/candidates").json()
    assert (
        items
        and items[0]["checks"]["official_source"] is True
        and items[0]["checks"]["in_scope"] is True
    )
    cid = items[0]["id"]
    no_note = manager.post(f"{API}/research/candidates/{cid}/review", json={"decision": "accepted"})
    assert no_note.status_code == 422
    ok = manager.post(
        f"{API}/research/candidates/{cid}/review",
        json={"decision": "accepted", "note": "Checked against the NCSI table."},
    )
    assert ok.status_code == 200 and ok.json()["status"] == "accepted"
    again = manager.post(f"{API}/research/candidates/{cid}/review", json={"decision": "rejected"})
    assert again.status_code == 409
    csv_text = manager.get(f"{API}/research/candidates/accepted.csv").text
    assert "41234" in csv_text and "https://www.ncsi.gov.om/" in csv_text


# ------------------------------------------------------------------ voice


def _wav(seconds: float = 1.0) -> bytes:
    data = b"\x00\x00" * int(16000 * seconds)
    fmt = struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16)
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", 16)
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_voice_transcribe_and_speak_ownership(app) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    client = _guest(app)
    assert client.get(f"{API}/assistant/voice").json()["configured"] is True
    r = client.post(
        f"{API}/assistant/voice/transcribe?language=ar",
        content=_wav(),
        headers={"Content-Type": "audio/wav"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["stored_audio"] is False and r.json()["text"]
    no_csrf = TestClient(app)
    no_csrf.get(f"{API}/assistant/guest")
    assert (
        no_csrf.post(
            f"{API}/assistant/voice/transcribe",
            content=_wav(),
            headers={"Content-Type": "audio/wav"},
        ).status_code
        == 403
    )
    bad = client.post(
        f"{API}/assistant/voice/transcribe",
        content=b"RIFFxxxx",
        headers={"Content-Type": "audio/wav"},
    )
    assert bad.status_code == 422
    answer = _ask(client, "What is the latest electricity generation?").json()["message"]
    spoken = client.post(
        f"{API}/assistant/voice/speak", json={"message_id": answer["id"], "language": "en"}
    )
    # The test provider returns a real WAV tone; Azure returns audio/mpeg.
    assert spoken.status_code == 200 and spoken.headers["content-type"] == "audio/wav"
    assert spoken.content[:4] == b"RIFF"
    stranger = _guest(app)
    assert (
        stranger.post(f"{API}/assistant/voice/speak", json={"message_id": answer["id"]}).status_code
        == 404
    )
