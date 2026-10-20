"""Migrations 0014 to 0018 go down and up again on a throwaway database without losing
messages or requests: statuses introduced later are mapped to earlier ones, the tables and
columns those migrations added are removed and recreated, and the profile version they
published is removed and published again. The provider call log (0018) is a log only: going
down removes it. The session's own test database is never touched."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration

BEFORE = "0013_assistant_profile"


@pytest.fixture
def scratch_url(database_url: str) -> Iterator[str]:
    """A separate database for this test only; the settings point back afterwards."""
    from tests.conftest import _reset_caches

    admin = make_url(os.environ["OSRIP_TEST_ADMIN_URL"])
    name = f"osrip_rt_{uuid.uuid4().hex[:10]}"
    plain = admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = admin.set(database=name).render_as_string(hide_password=False)
    previous = os.environ["OSRIP_DATABASE_URL"]
    os.environ["OSRIP_DATABASE_URL"] = url
    _reset_caches()
    try:
        yield url
    finally:
        os.environ["OSRIP_DATABASE_URL"] = previous
        _reset_caches()
        with psycopg.connect(plain, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _alembic(direction: str, target: str) -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    getattr(command, direction)(cfg, target)


def _one(url: str, sql: str, *params: object) -> tuple:
    plain = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain) as conn:
        return conn.execute(sql, params).fetchone() or ()


def _exec(url: str, sql: str, *params: object) -> None:
    plain = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute(sql, params)


def test_0014_to_0016_down_and_up_keep_messages_and_requests(scratch_url: str) -> None:
    _alembic("upgrade", "head")
    # A guest conversation with a profile reply, a cancelled reply and a cancelled request.
    guest = uuid.uuid4()
    conv = uuid.uuid4()
    _exec(
        scratch_url,
        "INSERT INTO guest_session (id, token_hash, csrf_hash, client_hash, answer_limit, expires_at, policy_version) "
        "VALUES (%s, %s, %s, %s, 5, now() + interval '1 day', 1)",
        guest, "t" * 64, "c" * 64, "h" * 64,
    )  # fmt: skip
    _exec(
        scratch_url,
        "INSERT INTO assistant_conversation (id, guest_session_id, title, language, data_mode) "
        "VALUES (%s, %s, 'Round trip', 'en', 'synthetic')",
        conv, guest,
    )  # fmt: skip
    for status in ("profile", "cancelled"):
        _exec(
            scratch_url,
            "INSERT INTO assistant_message (conversation_id, role, content, status) "
            "VALUES (%s, 'assistant', %s, %s)",
            conv, f"{status} reply", status,
        )  # fmt: skip
    key = uuid.uuid4()
    _exec(
        scratch_url,
        "INSERT INTO assistant_request (guest_session_id, idempotency_key, question_digest, language, state, "
        "reserved_until, progress) VALUES (%s, %s, 'd', 'en', 'cancelled', now(), "
        "'[{\"stage\": \"received\"}, {\"stage\": \"cancelled\"}]'::jsonb)",
        guest, key,
    )  # fmt: skip

    _alembic("downgrade", BEFORE)
    assert _one(scratch_url, "SELECT to_regclass('study_run')") == (None,)
    assert _one(
        scratch_url,
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'assistant_request' "
        "AND column_name IN ('progress', 'cancel_requested_at')",
    ) == (0,)
    # Nothing deleted: the messages and the request remain, with earlier statuses.
    statuses = _one(
        scratch_url,
        "SELECT array_agg(status ORDER BY content) FROM assistant_message WHERE conversation_id = %s",
        conv,
    )[0]
    assert statuses == ["unavailable", "lookup"]  # 'cancelled reply', 'profile reply'
    assert _one(
        scratch_url, "SELECT state FROM assistant_request WHERE idempotency_key = %s", key
    ) == ("released",)
    assert _one(scratch_url, "SELECT version FROM assistant_profile WHERE status = 'active'") == (
        1,
    )

    _alembic("upgrade", "head")
    assert _one(scratch_url, "SELECT to_regclass('study_run') IS NOT NULL") == (True,)
    assert _one(
        scratch_url, "SELECT progress FROM assistant_request WHERE idempotency_key = %s", key
    ) == ([],)
    assert _one(scratch_url, "SELECT version FROM assistant_profile WHERE status = 'active'") == (
        3,
    )


def test_0017_down_and_up_keeps_replies_and_restores_profile_versions(scratch_url: str) -> None:
    _alembic("upgrade", "head")
    assert _one(
        scratch_url,
        "SELECT version, profile ? 'personas' FROM assistant_profile WHERE status = 'active'",
    ) == (3, True)
    guest, conv = uuid.uuid4(), uuid.uuid4()
    _exec(
        scratch_url,
        "INSERT INTO guest_session (id, token_hash, csrf_hash, client_hash, answer_limit, expires_at, policy_version) "
        "VALUES (%s, %s, %s, %s, 5, now() + interval '1 day', 1)",
        guest, "u" * 64, "d" * 64, "i" * 64,
    )  # fmt: skip
    _exec(
        scratch_url,
        "INSERT INTO assistant_conversation (id, guest_session_id, title, language, data_mode) "
        "VALUES (%s, %s, 'Personas', 'ar', 'synthetic')",
        conv, guest,
    )  # fmt: skip
    _exec(
        scratch_url,
        "INSERT INTO assistant_message (conversation_id, role, content, status, persona) "
        "VALUES (%s, 'assistant', 'أنا إلهام', 'profile', 'ilham')",
        conv,
    )  # fmt: skip
    # A persona on a user's message, or a malformed code, is refused by the database.
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(
            scratch_url,
            "INSERT INTO assistant_message (conversation_id, role, content, persona) "
            "VALUES (%s, 'user', 'hi', 'ilham')",
            conv,
        )  # fmt: skip

    _alembic("downgrade", "0016_request_progress")
    assert _one(
        scratch_url,
        "SELECT count(*) FROM information_schema.columns WHERE column_name IN "
        "('persona', 'assistant_persona') AND table_name IN ('assistant_message', 'app_user')",
    ) == (0,)
    assert _one(
        scratch_url, "SELECT content FROM assistant_message WHERE conversation_id = %s", conv
    ) == ("أنا إلهام",)
    assert _one(scratch_url, "SELECT version FROM assistant_profile WHERE status = 'active'") == (
        2,
    )
    assert _one(scratch_url, "SELECT count(*) FROM assistant_profile WHERE version = 3") == (0,)

    _alembic("upgrade", "head")
    assert _one(scratch_url, "SELECT version FROM assistant_profile WHERE status = 'active'") == (
        3,
    )


def test_0018_provider_call_log_checks_and_round_trip(scratch_url: str) -> None:
    _alembic("upgrade", "head")
    _exec(
        scratch_url,
        "INSERT INTO provider_call (provider, capability, model, status, duration_ms, input_tokens, "
        "output_tokens, searches, estimated_cost_usd) "
        "VALUES ('openai', 'answer', 'configured-model', 'ok', 120, 10, 5, 0, 0.000123)",
    )  # fmt: skip
    # Only known capabilities and short outcome codes (never free text such as a prompt).
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(
            scratch_url,
            "INSERT INTO provider_call (provider, capability, status) VALUES ('openai', 'chat', 'ok')",
        )  # fmt: skip
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(
            scratch_url,
            "INSERT INTO provider_call (provider, capability, status) "
            "VALUES ('openai', 'answer', 'What is the latest figure?')",
        )  # fmt: skip

    _alembic("downgrade", "0017_assistant_personas")
    assert _one(scratch_url, "SELECT to_regclass('study_event')") == (None,)
    assert _one(scratch_url, "SELECT to_regclass('provider_call')") == (None,)
    assert _one(scratch_url, "SELECT version FROM assistant_profile WHERE status = 'active'") == (
        3,
    )
    _alembic("upgrade", "head")
    assert _one(scratch_url, "SELECT count(*) FROM provider_call") == (0,)


def test_0019_study_events_checks_and_round_trip(scratch_url: str) -> None:
    _alembic("upgrade", "head")
    guest, conv, rid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _exec(
        scratch_url,
        "INSERT INTO guest_session (id, token_hash, csrf_hash, client_hash, answer_limit, expires_at, policy_version) "
        "VALUES (%s, %s, %s, %s, 5, now() + interval '1 day', 1)",
        guest, "v" * 64, "e" * 64, "j" * 64,
    )  # fmt: skip
    _exec(
        scratch_url,
        "INSERT INTO assistant_conversation (id, guest_session_id, title, language, data_mode) "
        "VALUES (%s, %s, 'Study', 'en', 'synthetic')",
        conv, guest,
    )  # fmt: skip
    req = _one(
        scratch_url,
        "INSERT INTO assistant_request (guest_session_id, idempotency_key, question_digest, language, "
        "state, reserved_until, conversation_id) VALUES (%s, %s, 'd', 'en', 'completed', now(), %s) RETURNING id",
        guest, rid, conv,
    )[0]  # fmt: skip
    insert = (
        "INSERT INTO study_event (request_id, conversation_id, study_id, seq, type, payload) "
        "VALUES (%s, %s, %s, %s, %s, %s::jsonb)"
    )
    _exec(scratch_url, insert, req, conv, rid, 1, "study.started", '{"attempt": 1}')
    # Unknown event types, repeated sequence numbers and non-object payloads are refused.
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(scratch_url, insert, req, conv, rid, 2, "chat", "{}")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _exec(scratch_url, insert, req, conv, rid, 1, "stage", "{}")
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(scratch_url, insert, req, conv, rid, 2, "stage", "[]")
    # Deleting the conversation deletes its study events.
    _exec(scratch_url, "DELETE FROM assistant_conversation WHERE id = %s", conv)
    assert _one(scratch_url, "SELECT count(*) FROM study_event WHERE study_id = %s", rid) == (0,)

    _alembic("downgrade", "0018_provider_calls")
    assert _one(scratch_url, "SELECT to_regclass('study_event')") == (None,)
    assert _one(scratch_url, "SELECT state FROM assistant_request WHERE id = %s", req) == (
        "completed",
    )
    _alembic("upgrade", "head")
    assert _one(scratch_url, "SELECT count(*) FROM study_event") == (0,)


def test_0020_balance_analyses_checks_and_round_trip(scratch_url: str) -> None:
    _alembic("upgrade", "head")
    insert = (
        "INSERT INTO study_run (kind, schema_version, params, data_mode, result, result_sha256) "
        "VALUES (%s, %s, '{}'::jsonb, 'synthetic', %s::jsonb, %s)"
    )
    sha = "a" * 64
    balance = '{"kind": "supply_balance", "data_mode": "synthetic"}'
    trend = '{"kind": "trend", "data_mode": "synthetic"}'
    _exec(scratch_url, insert, "supply_balance", "osrip.balance/1", balance, sha)
    _exec(scratch_url, insert, "trend", "osrip.study/1", trend, sha)
    # Each kind keeps its own document schema.
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(scratch_url, insert, "supply_balance", "osrip.study/1", balance, sha)
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(scratch_url, insert, "trend", "osrip.balance/1", trend, sha)

    _alembic("downgrade", "0019_study_events")
    assert _one(scratch_url, "SELECT count(*) FROM study_run WHERE kind = 'supply_balance'") == (0,)
    assert _one(scratch_url, "SELECT count(*) FROM study_run WHERE kind = 'trend'") == (1,)
    with pytest.raises(psycopg.errors.CheckViolation):
        _exec(scratch_url, insert, "supply_balance", "osrip.balance/1", balance, sha)
    _alembic("upgrade", "head")
    _exec(scratch_url, insert, "supply_balance", "osrip.balance/1", balance, sha)
