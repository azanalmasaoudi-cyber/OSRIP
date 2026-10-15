"""The five-answer guest allowance (booklet 3.35; acceptance T26-T29).

Server state is checked, not only the counter the interface shows: five successful
answers across both languages, the sixth refused before any provider request,
failures and withheld replies not charged, idempotent replays, a race for the last
slot, abandoned reservations, CSRF, and the explicit link into an account.
The scripted FakeProvider answers "generation" questions from synthetic data.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def setup(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    settings = get_settings()
    monkeypatch.setattr(settings, "assistant_provider", "fake")
    # Abuse limits are exercised separately; here they must not interfere.
    monkeypatch.setattr(settings, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(settings, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(settings, "guest_sessions_per_client_hour", 1000)
    ratelimit.reset()
    with session_factory()() as s:
        seed_booklet_fixtures(s)  # idempotent


@pytest.fixture
def calls(monkeypatch):  # noqa: ANN001, ANN201
    """Counts provider requests (each model round is one request)."""
    from app.services.assistant import provider

    counter = {"n": 0}
    original = provider.FakeProvider.complete

    def counted(self, system, messages, tools):  # noqa: ANN001, ANN202
        counter["n"] += 1
        return original(self, system, messages, tools)

    monkeypatch.setattr(provider.FakeProvider, "complete", counted)
    return counter


def guest(app) -> Any:  # noqa: ANN001
    from fastapi.testclient import TestClient

    client = TestClient(app)
    body = client.get(f"{API}/assistant/guest").json()
    assert body["authenticated"] is False and body["allowance"]["remaining"] == 5
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def ask(client, content: str, language: str = "en", request_id: str | None = None, **extra):  # noqa: ANN001, ANN003, ANN201
    return client.post(
        f"{API}/assistant/guest/messages",
        json={
            "content": content,
            "language": language,
            "request_id": request_id or str(uuid.uuid4()),
            "data_mode": "synthetic",
            **extra,
        },
    )


GOOD = {"en": "What is the latest electricity generation?", "ar": "ما آخر قيمة لتوليد الكهرباء؟"}


def test_five_answers_across_languages_then_sign_in_required(app, calls) -> None:  # noqa: ANN001
    client = guest(app)
    conversation = None
    for n, language in enumerate(["en", "ar", "en", "ar", "en"], start=1):
        r = ask(client, GOOD[language], language, conversation_id=conversation)
        assert r.status_code == 201, r.text
        body = r.json()
        conversation = body["conversation_id"]
        assert body["message"]["status"] == "answered" and body["message"]["content"]
        assert body["allowance"]["used"] == n and body["allowance"]["remaining"] == 5 - n
    # The fifth answer was delivered completely; the next question needs an account.
    assert body["allowance"]["authentication_required"] is True
    before = calls["n"]
    sixth = ask(client, GOOD["en"])
    assert sixth.status_code == 403
    error = sixth.json()["error"]
    assert error["code"] == "guest_allowance_exhausted"
    assert error["details"]["authentication_required"] is True
    assert calls["n"] == before, "refused before any provider request"
    # Reload / another tab (same cookie jar) and a language switch keep the count.
    again = client.get(f"{API}/assistant/guest").json()
    assert again["allowance"]["used"] == 5 and again["allowance"]["remaining"] == 0
    history = client.get(f"{API}/assistant/guest/conversations/{conversation}").json()
    assert len(history["messages"]) == 10 and history["language"] in ("en", "ar")
    # Public statistics stay open without an account.
    assert (
        client.get(
            f"{API}/observations", params={"data_mode": "synthetic", "section": "water"}
        ).status_code
        == 200
    )


def test_failures_and_withheld_replies_do_not_consume(app) -> None:  # noqa: ANN001
    client = guest(app)
    failed = ask(client, "please fail")
    assert failed.status_code == 201 and failed.json()["message"]["status"] == "unavailable"
    assert failed.json()["allowance"]["used"] == 0
    withheld = ask(client, "Invent the latest electricity generation")
    assert withheld.json()["message"]["status"] == "unverified"
    assert (
        withheld.json()["allowance"]["used"] == 0 and withheld.json()["allowance"]["remaining"] == 5
    )
    ok = ask(client, GOOD["en"])
    assert ok.json()["allowance"]["used"] == 1


def test_retry_and_replay_are_not_charged_twice(app, calls, monkeypatch) -> None:  # noqa: ANN001
    from app.services.assistant import provider

    client = guest(app)
    key = str(uuid.uuid4())
    # First attempt: the provider fails (transport error) -> released, not charged.
    original = provider.FakeProvider.complete

    def outage(self, system, messages, tools):  # noqa: ANN001, ANN202
        raise provider.ProviderError("timeout")

    monkeypatch.setattr(provider.FakeProvider, "complete", outage)
    first = ask(client, GOOD["en"], request_id=key)
    assert (
        first.json()["message"]["status"] == "unavailable"
        and first.json()["allowance"]["used"] == 0
    )
    # Retry of the same request id: answered and charged once.
    monkeypatch.setattr(provider.FakeProvider, "complete", original)
    second = ask(client, GOOD["en"], request_id=key)
    assert (
        second.json()["message"]["status"] == "answered" and second.json()["allowance"]["used"] == 1
    )
    conv = second.json()["conversation_id"]
    # The delivery was "lost": the same id again returns the stored reply, no new charge.
    before = calls["n"]
    third = ask(client, GOOD["en"], request_id=key)
    assert third.status_code == 201 and third.json()["message"]["replayed"] is True
    assert third.json()["message"]["id"] == second.json()["message"]["id"]
    assert third.json()["allowance"]["used"] == 1 and calls["n"] == before
    # The retried question appears once in the thread.
    messages = client.get(f"{API}/assistant/guest/conversations/{conv}").json()["messages"]
    assert [m["role"] for m in messages].count("user") == 1
    # The same id for a different question is refused.
    reused = ask(client, "What is the latest water production?", request_id=key)
    assert reused.status_code == 422 and reused.json()["error"]["code"] == "request_id_reused"


def test_two_requests_race_for_the_last_slot(app, monkeypatch, db) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    from app.services.assistant import provider

    client = guest(app)
    for _ in range(4):
        assert ask(client, GOOD["en"]).json()["allowance"]["used"] in (1, 2, 3, 4)
    original = provider.FakeProvider.complete

    def slow(self, system, messages, tools):  # noqa: ANN001, ANN202
        time.sleep(0.4)  # both requests are in flight together
        return original(self, system, messages, tools)

    monkeypatch.setattr(provider.FakeProvider, "complete", slow)
    results: list[int] = []

    def fire() -> None:
        other = TestClient(app)
        other.cookies.update(client.cookies)
        other.headers["X-Guest-CSRF"] = client.headers["X-Guest-CSRF"]
        results.append(ask(other, GOOD["en"]).status_code)

    threads = [threading.Thread(target=fire) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 403], results
    final = client.get(f"{API}/assistant/guest").json()["allowance"]
    assert final["used"] == 5 and final["in_progress"] == 0


def test_the_database_refuses_more_than_the_limit(db) -> None:  # noqa: ANN001
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), db.begin():
        db.execute(
            text(
                "INSERT INTO guest_session (token_hash, csrf_hash, answer_limit, answers_used, "
                "answers_reserved, expires_at) VALUES ('t-limit', 'c', 5, 5, 1, now() + interval '1 day')"
            )
        )


def test_abandoned_reservations_are_released_but_completed_ones_are_not(app, db) -> None:  # noqa: ANN001
    client = guest(app)
    ok = ask(client, GOOD["en"]).json()
    with db.begin():
        gid = db.scalar(
            text("SELECT guest_session_id FROM assistant_request WHERE response_message_id = :m"),
            {"m": ok["message"]["id"]},
        )
        # A worker crashed while answering: one reservation left open, long expired.
        db.execute(text("UPDATE guest_session SET answers_reserved = 1 WHERE id = :g"), {"g": gid})
        db.execute(
            text(
                "INSERT INTO assistant_request (guest_session_id, idempotency_key, question_digest, "
                "language, state, reserved_until) VALUES (:g, :k, 'd', 'en', 'reserved', now() - interval '1 hour')"
            ),
            {"g": gid, "k": str(uuid.uuid4())},
        )
    assert client.get(f"{API}/assistant/guest").json()["allowance"]["in_progress"] == 1
    after = ask(client, GOOD["en"]).json()["allowance"]
    assert after["used"] == 2 and after["in_progress"] == 0  # released, and the completed one kept
    with db.begin():
        states = db.execute(
            text(
                "SELECT state, charged FROM assistant_request WHERE guest_session_id = :g ORDER BY id"
            ),
            {"g": gid},
        ).all()
    assert [tuple(s) for s in states] == [
        ("completed", True),
        ("released", False),
        ("completed", True),
    ]


def test_guest_requests_need_the_cookie_and_the_csrf_token(app) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    client = guest(app)
    no_csrf = TestClient(app)
    no_csrf.cookies.update(client.cookies)
    assert ask(no_csrf, GOOD["en"]).json()["error"]["code"] == "csrf_failed"
    stranger = TestClient(app)
    stranger.headers["X-Guest-CSRF"] = "x"
    assert ask(stranger, GOOD["en"]).json()["error"]["code"] == "guest_session_required"
    other = guest(app)  # another browser has its own session and cannot read this one's history
    conv = ask(client, GOOD["en"]).json()["conversation_id"]
    assert other.get(f"{API}/assistant/guest/conversations/{conv}").status_code == 404


def test_abuse_limit_per_guest_session(app, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "guest_asks_per_minute", 2)
    client = guest(app)
    assert ask(client, "please fail").status_code == 201
    assert ask(client, "please fail").status_code == 201
    limited = ask(client, "please fail")
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "too_many_requests"


def test_without_a_provider_the_lookup_answers_and_nothing_is_charged(app, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "assistant_provider", "disabled")
    client = guest(app)
    r = ask(client, "electricity generation?").json()
    assert r["message"]["status"] == "lookup" and r["message"]["ai_generated"] is False
    assert (
        r["message"]["evidence"]
        and r["allowance"]["used"] == 0
        and r["allowance"]["remaining"] == 5
    )


def test_sign_in_keeps_the_conversation_only_through_an_explicit_link(app, make_user) -> None:  # noqa: ANN001
    from app.domain.enums import Role

    client = guest(app)
    conv = ask(client, GOOD["en"]).json()["conversation_id"]
    person = make_user(Role.VIEWER)
    # Signing in on the same browser: the guest history is offered, not merged.
    assert (
        client.post(
            f"{API}/auth/login", json={"email": person.email, "password": person.password}
        ).status_code
        == 200
    )
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    status = client.get(f"{API}/assistant/guest").json()
    assert status == {**status, "authenticated": True, "linkable_history": True}
    assert conv not in {c["id"] for c in client.get(f"{API}/assistant/conversations").json()}
    linked = client.post(f"{API}/assistant/guest/link")
    assert linked.status_code == 200 and linked.json()["linked_conversations"] == 1
    mine = client.get(f"{API}/assistant/conversations/{conv}").json()
    assert [m["role"] for m in mine["messages"]] == ["user", "assistant"]
    # Signed-in users ask from their account; the guest endpoint refuses them.
    assert ask(client, GOOD["en"]).status_code == 409
    # Another account cannot claim the same guest history.
    other = make_user(Role.VIEWER)
    client.post(f"{API}/auth/logout")
    client.post(f"{API}/auth/login", json={"email": other.email, "password": other.password})
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    assert client.post(f"{API}/assistant/guest/link").status_code == 409


def test_signed_in_replay_and_daily_fair_use(make_user, login, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings
    from app.domain.enums import Role

    user = login(make_user(Role.VIEWER))
    conv = user.post(f"{API}/assistant/conversations", json={"data_mode": "synthetic"}).json()["id"]
    key = str(uuid.uuid4())
    url = f"{API}/assistant/conversations/{conv}/messages"
    first = user.post(url, json={"content": GOOD["en"], "request_id": key}).json()
    again = user.post(url, json={"content": GOOD["en"], "request_id": key}).json()
    assert again["replayed"] is True and again["id"] == first["id"]
    monkeypatch.setattr(get_settings(), "assistant_max_per_day", 1)
    limited = user.post(url, json={"content": GOOD["en"]})
    assert (
        limited.status_code == 429 and limited.json()["error"]["code"] == "assistant_rate_limited"
    )
