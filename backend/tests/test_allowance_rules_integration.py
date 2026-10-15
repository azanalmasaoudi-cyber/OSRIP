"""The guest allowance rules together, in one visitor's session (the integrated experience):

* the fixed greeting never consumes an answer, in either persona or language;
* a failed generation, and a retry of it with the same request id, consume nothing;
* a completed answer counts once: replaying the request, interrupting or repeating its
  playback (whole reply or one narration segment), stopping it after it finished, or
  reopening its live study never charges again;
* the five answers are shared by both personas, both languages, typed questions, research
  and compare modes and spoken questions;
* after five, every channel is refused before any answer is attempted, greetings stay free,
  and the database holds exactly five charged requests (no reservation left behind).

Atomic enforcement under concurrency and the database constraint are covered in
``test_guest_allowance_integration.py`` (two requests racing for the last slot; an UPDATE
beyond the limit refused by the table's CHECK).
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
    for name, value in (
        ("assistant_provider", "fake"), ("assistant_fallback_provider", ""),
        ("research_provider", "fake"), ("research_fallback_provider", ""),
        ("speech_provider", "fake"), ("guest_asks_per_minute", 1000),
        ("guest_asks_per_client_hour", 1000), ("guest_sessions_per_client_hour", 1000),
    ):  # fmt: skip
        monkeypatch.setattr(s, name, value)
    ratelimit.reset()
    with session_factory()() as session:
        seed_booklet_fixtures(session)


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _guest_row(client):  # noqa: ANN001, ANN202
    from app.core import security
    from app.db.session import session_factory
    from app.models import GuestSession

    digest = security.token_digest(client.cookies["osrip_guest"])
    with session_factory()() as s:
        return s.scalar(select(GuestSession).where(GuestSession.token_hash == digest))


def _ask(client, content: str, rid: uuid.UUID | None = None, **extra: Any):  # noqa: ANN001, ANN202
    return client.post(
        f"{API}/assistant/guest/messages",
        json={"content": content, "language": extra.pop("language", "en"),
              "request_id": str(rid or uuid.uuid4()), "data_mode": "synthetic", **extra},
    )  # fmt: skip


def _used(client) -> int:  # noqa: ANN001
    return int(client.get(f"{API}/assistant/guest").json()["allowance"]["used"])


def test_the_allowance_rules_hold_together_across_personas_languages_text_and_voice(
    app, db
) -> None:  # noqa: ANN001
    client = _guest(app)
    queued: list[int] = []

    # The fixed greeting, in both personas and languages: an approved reply, never charged.
    for persona, greeting, language in (("ilham", "السلام عليكم", "ar"), ("mulhim", "Hello", "en")):
        r = _ask(client, greeting, persona=persona, language=language)
        assert r.status_code == 201 and r.json()["message"]["status"] == "profile"
    assert _used(client) == 0

    # A failed generation, and a retry of the same request, consume nothing.
    failed = uuid.uuid4()
    for _ in range(2):
        r = _ask(client, "please fail", failed)
        assert r.status_code == 201 and r.json()["message"]["status"] == "unavailable"
    assert _used(client) == 0

    # Answer 1 (Al Mulhim, English, typed) counts once...
    first = uuid.uuid4()
    r = _ask(client, "What is the latest electricity generation?", first, persona="mulhim")
    message = r.json()["message"]
    assert message["status"] == "answered" and r.json()["allowance"]["used"] == 1
    # ... whatever happens to it afterwards: the same request again is replayed, not charged;
    again = _ask(client, "What is the latest electricity generation?", first, persona="mulhim")
    assert again.json()["message"]["replayed"] is True and again.json()["allowance"]["used"] == 1
    # playback started, interrupted and restarted (one narration segment, then the whole reply);
    for body in ({"segment_id": "N1"}, {}, {"segment_id": "N1"}):
        spoken = client.post(f"{API}/assistant/voice/speak",
                             json={"message_id": message["id"], "language": "en", **body})  # fmt: skip
        assert spoken.status_code == 200
    # "Stop" pressed after it finished; and its live study reopened.
    stop = client.post(f"{API}/assistant/guest/requests/{first}/cancel")
    assert stop.status_code == 202 and stop.json()["state"] == "completed"
    assert client.get(f"{API}/assistant/guest/requests/{first}/study").status_code == 200
    assert _used(client) == 1

    # Answers 2-5: Ilham in Arabic, a spoken question, research mode, compare mode.
    r = _ask(client, "ما آخر قيمة لتوليد الكهرباء؟", persona="ilham", language="ar")
    assert r.json()["message"]["status"] == "answered" and r.json()["message"]["persona"] == "ilham"
    guest = _guest_row(client)
    call = bridge.Call(
        bridge.Caller("guest", guest.id), "en", data_mode=DataMode.SYNTHETIC, persona="ilham"
    )
    assert bridge.answer(call, "What is the latest electricity generation?")["status"] == "answered"
    r = _ask(client, "Search the web for electricity generation", persona="mulhim", mode="research")
    assert r.json()["message"]["status"] == "answered", r.text
    queued.append(r.json()["message"]["id"])
    r = _ask(client, "What is the latest electricity generation?", persona="ilham", mode="compare")
    assert r.status_code == 201
    assert _used(client) == 5

    # A sixth is refused for both personas and by voice, before any answer is attempted.
    for persona in ("mulhim", "ilham"):
        refused = _ask(client, "What is the latest electricity generation?", persona=persona)
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "guest_allowance_exhausted"
    with pytest.raises(ApiError) as voice_refused:
        bridge.answer(call, "What is the latest electricity generation?")
    assert voice_refused.value.code == "guest_allowance_exhausted"
    # Greetings stay free and available.
    assert (
        _ask(client, "مرحبا", persona="ilham", language="ar").json()["message"]["status"]
        == "profile"
    )

    # Exactly five charged requests and nothing left reserved.
    row = _guest_row(client)
    assert row.answers_used == 5 and row.answers_reserved == 0
    with db.begin():
        charged = db.execute(
            text("SELECT count(*) FROM assistant_request WHERE guest_session_id = :g AND charged"),
            {"g": row.id},
        ).scalar()
    assert charged == 5

    with db.begin():  # the research answer's scripted web figure: keep the review queue clean
        db.execute(text("DELETE FROM research_candidate WHERE message_id = ANY(:m)"), {"m": queued})
