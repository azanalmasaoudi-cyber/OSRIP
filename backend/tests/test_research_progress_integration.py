"""Visible progress and stopping a question (migration 0016), for guests and signed-in users.

Stages are written while the answer is prepared and can be read by the person who asked
(and nobody else). Stopping a question ends it at the next step with a 'cancelled' reply
that is never counted against a guest's allowance. The scripted FakeProvider stands in for
the model; no request leaves the machine.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.enums import Permission, Role
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def setup(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "research_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    monkeypatch.setattr(s, "assistant_max_per_minute", 1000)
    monkeypatch.setattr(s, "assistant_max_per_hour", 1000)
    ratelimit.reset()


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _ask(client, content: str, request_id: uuid.UUID, **extra: Any) -> dict[str, Any]:  # noqa: ANN001
    r = client.post(
        f"{API}/assistant/guest/messages",
        json={"content": content, "language": extra.pop("language", "en"), "request_id": str(request_id),
              "data_mode": "synthetic", "mode": extra.pop("mode", "ask"), **extra},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()


def stages(body: dict[str, Any]) -> list[str]:
    return [s["stage"] for s in body["stages"]]


def test_a_guest_sees_the_real_stages_of_an_answer(app, db) -> None:  # noqa: ANN001
    client = _guest(app)
    rid = uuid.uuid4()
    body = _ask(client, "What was the growth of electricity generation?", rid)
    progress = client.get(f"{API}/assistant/guest/requests/{rid}/progress")
    assert progress.status_code == 200, progress.text
    seen = stages(progress.json())
    assert seen[0] == "received" and seen[-1] == "done"
    assert "calculating" in seen and "checking" in seen
    assert "web_search" not in seen  # no search was made, so none is shown
    assert all(s["label"]["en"] and s["label"]["ar"] for s in progress.json()["stages"])
    method = body["message"]["structured"]["method"]
    assert "calculating" in method["steps"] and method["searches"] == 0

    # Research mode with the scripted search: searching and its languages appear.
    rid2 = uuid.uuid4()
    body = _ask(client, "Search the web for electricity generation", rid2, mode="research")
    seen = stages(client.get(f"{API}/assistant/guest/requests/{rid2}/progress").json())
    assert "web_search" in seen
    assert body["message"]["structured"]["method"]["searches"] >= 1
    # The scripted web figure went to the review queue; remove it so the module that checks
    # that queue later finds its own candidate (candidates are de-duplicated by source).
    with db.begin():
        db.execute(
            text("DELETE FROM research_candidate WHERE message_id = :m"),
            {"m": body["message"]["id"]},
        )


def test_another_visitor_cannot_read_or_stop_a_request(app) -> None:  # noqa: ANN001
    owner, other = _guest(app), _guest(app)
    rid = uuid.uuid4()
    _ask(owner, "What was the growth of electricity generation?", rid)
    assert other.get(f"{API}/assistant/guest/requests/{rid}/progress").status_code == 404
    assert other.post(f"{API}/assistant/guest/requests/{rid}/cancel").status_code == 404
    # Stopping a finished question changes nothing.
    done = owner.post(f"{API}/assistant/guest/requests/{rid}/cancel")
    assert done.status_code == 202 and done.json()["state"] == "completed"
    assert done.json()["cancel_requested"] is False


@pytest.fixture
def stop_on_first_model_call(monkeypatch):  # noqa: ANN001, ANN201
    """The person presses Stop while the model is working on its first step."""
    from app.db.session import session_factory
    from app.services.assistant import provider

    original = provider.FakeProvider.complete
    pending: dict[str, uuid.UUID] = {}

    def patched(self, system, messages, tools):  # noqa: ANN001, ANN202
        rid = pending.pop("rid", None)
        if rid is not None:
            with session_factory()() as s, s.begin():
                s.execute(
                    text("UPDATE assistant_request SET cancel_requested_at = now() "
                         "WHERE idempotency_key = :rid AND state = 'reserved'"),
                    {"rid": rid},
                )  # fmt: skip
        return original(self, system, messages, tools)

    monkeypatch.setattr(provider.FakeProvider, "complete", patched)
    return pending


def test_a_stopped_guest_question_is_cancelled_and_not_counted(
    app, db, stop_on_first_model_call
) -> None:  # noqa: ANN001
    client = _guest(app)
    before = client.get(f"{API}/assistant/guest").json()["allowance"]["remaining"]
    rid = uuid.uuid4()
    stop_on_first_model_call["rid"] = rid
    body = _ask(client, "What was the growth of electricity generation?", rid, language="ar")
    message = body["message"]
    assert message["status"] == "cancelled"
    assert "أوقفتَ هذا السؤال" in message["content"]
    assert body["allowance"]["remaining"] == before  # not counted
    row = db.execute(
        text(
            "SELECT state, charged, cancel_requested_at FROM assistant_request WHERE idempotency_key = :r"
        ),
        {"r": rid},
    ).one()
    assert row.state == "cancelled" and row.charged is False and row.cancel_requested_at is not None
    progress = client.get(f"{API}/assistant/guest/requests/{rid}/progress").json()
    assert progress["state"] == "cancelled" and progress["cancel_requested"] is True
    seen = stages(progress)
    assert seen[-1] == "cancelled" and "calculating" not in seen  # stopped before the tool ran
    # The stopped reply is kept in the conversation but is not sent to the model as history.
    conv = client.get(f"{API}/assistant/guest/conversations/{body['conversation_id']}").json()
    assert conv["messages"][-1]["status"] == "cancelled"


def test_a_signed_in_user_reads_and_stops_only_their_own_requests(
    app, make_user, login, stop_on_first_model_call
) -> None:  # noqa: ANN001
    owner = login(make_user(Role.VIEWER, grants=(Permission.ASSISTANT_USE,)))
    other = login(make_user(Role.VIEWER, grants=(Permission.ASSISTANT_USE,)))
    conv = owner.post(
        f"{API}/assistant/conversations", json={"language": "en", "data_mode": "synthetic"}
    )
    assert conv.status_code == 201, conv.text
    cid = conv.json()["id"]
    rid = uuid.uuid4()
    r = owner.post(
        f"{API}/assistant/conversations/{cid}/messages",
        json={"content": "What was the growth of electricity generation?", "language": "en",
              "request_id": str(rid)},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert stages(owner.get(f"{API}/assistant/requests/{rid}/progress").json())[-1] == "done"
    assert other.get(f"{API}/assistant/requests/{rid}/progress").status_code == 404
    assert other.post(f"{API}/assistant/requests/{rid}/cancel").status_code == 404

    rid2 = uuid.uuid4()
    stop_on_first_model_call["rid"] = rid2
    r = owner.post(
        f"{API}/assistant/conversations/{cid}/messages",
        json={"content": "What was the growth of electricity generation?", "language": "en",
              "request_id": str(rid2)},
    )  # fmt: skip
    assert r.status_code == 201 and r.json()["status"] == "cancelled"
    assert owner.get(f"{API}/assistant/requests/{rid2}/progress").json()["state"] == "cancelled"
