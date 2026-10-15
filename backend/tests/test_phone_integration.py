"""Registration, sign-in and linking by phone, with the scripted SMS test provider.

The test provider keeps codes in process memory; tests read them the way a phone user
reads an SMS. Production refuses this provider (see the last tests).
"""

from __future__ import annotations

import os
import secrets
import threading
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration

SMS_ENV = {
    "OSRIP_SMS_ENABLED": "true",
    "OSRIP_SMS_PROVIDER": "test",
    "OSRIP_SMS_RESEND_SECONDS": "0",
    "OSRIP_SMS_PER_NUMBER_HOUR": "50",
    "OSRIP_SMS_PER_CLIENT_HOUR": "500",
}


def _apply(env: dict[str, str | None]) -> None:
    from app.core.config import get_settings

    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


@pytest.fixture
def sms_on(database_url: str) -> Iterator[None]:
    from app.core import ratelimit
    from app.services import sms

    saved = {k: os.environ.get(k) for k in SMS_ENV}
    _apply(dict(SMS_ENV))
    ratelimit.reset()
    sms.scripted_provider().reset()
    try:
        yield
    finally:
        _apply(saved)
        ratelimit.reset()


def number() -> str:
    return f"9{1000000 + secrets.randbelow(9000000)}"  # Omani mobile format, test only


def request_code(client, national: str, purpose: str = "sign_in"):  # noqa: ANN001, ANN201
    return client.post(
        f"{API}/auth/phone/request",
        json={"country_code": "+968", "number": national, "purpose": purpose},
    )


def code_for(national: str) -> str:
    from app.services import sms

    return next(m["code"] for m in sms.scripted_provider().outbox() if m["to"] == f"+968{national}")


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


def register_by_phone(client, national: str, name: str = "Phone user"):  # noqa: ANN001, ANN201
    r = request_code(client, national)
    assert r.status_code == 202, r.text
    challenge = r.json()["challenge_id"]
    return client.post(
        f"{API}/auth/phone/verify",
        json={"challenge_id": challenge, "code": code_for(national), "display_name": name},
    )


# ------------------------------------------------------------------ availability


def test_unconfigured_sms_is_reported_unavailable(anonymous) -> None:  # noqa: ANN001
    providers = anonymous.get(f"{API}/auth/providers").json()
    assert providers["sms"]["available"] is False and providers["sms"]["status"] == "disabled"
    assert providers["sms"]["default_country"] == "+968"
    r = request_code(anonymous, number())
    assert r.status_code == 503 and r.json()["error"]["code"] == "sms_unavailable"
    assert "e-mail" in r.json()["error"]["message"]
    assert anonymous.get(f"{API}/dev/sms-outbox").status_code == 404


def test_enabled_without_an_adapter_stays_unavailable(anonymous, sms_on) -> None:  # noqa: ANN001
    _apply({"OSRIP_SMS_PROVIDER": "somevendor"})
    status = anonymous.get(f"{API}/auth/providers").json()["sms"]
    assert status["available"] is False and status["status"] == "not_configured"
    assert request_code(anonymous, number()).status_code == 503


# ------------------------------------------------------------------ registration and sign-in


def test_phone_registration_creates_an_ordinary_account_and_session(anonymous, sms_on) -> None:  # noqa: ANN001
    national = number()
    r = request_code(anonymous, national)
    assert r.status_code == 202
    body = r.json()
    assert set(body) == {
        "challenge_id",
        "phone_masked",
        "expires_in",
        "resend_after",
        "max_attempts",
    }
    assert body["phone_masked"] == f"+968 ••••••{national[-2:]}"
    assert code_for(national) not in r.text  # the code never travels to the browser

    verified = anonymous.post(
        f"{API}/auth/phone/verify",
        json={
            "challenge_id": body["challenge_id"],
            "code": code_for(national),
            "display_name": "Salim",
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "registered"
    me = anonymous.get(f"{API}/auth/me").json()
    assert me["authenticated"] and me["display_name"] == "Salim"
    assert me["roles"] == ["viewer"] and me["email"] is None and me["phone_verified"] is True
    assert me["phone"] == f"+968 ••••••{national[-2:]}" and me["has_password"] is False
    assert "user.manage" not in me["permissions"] and "import.publish" not in me["permissions"]


def test_existing_number_signs_in_and_answers_do_not_reveal_accounts(app, sms_on) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    national = number()
    assert register_by_phone(TestClient(app), national).status_code == 200
    fresh = number()
    known = request_code(TestClient(app), national).json()
    unknown = request_code(TestClient(app), fresh).json()
    assert set(known) == set(unknown)  # same shape for an existing and a new number
    assert {k: v for k, v in known.items() if k not in ("challenge_id", "phone_masked")} == {
        k: v for k, v in unknown.items() if k not in ("challenge_id", "phone_masked")
    }
    second = TestClient(app)
    r = request_code(second, national)
    verified = second.post(
        f"{API}/auth/phone/verify",
        json={"challenge_id": r.json()["challenge_id"], "code": code_for(national)},
    )
    assert verified.json()["status"] == "signed_in"


def test_wrong_codes_count_and_lock_the_challenge(anonymous, sms_on) -> None:  # noqa: ANN001
    national = number()
    challenge = request_code(anonymous, national).json()["challenge_id"]
    code = code_for(national)
    for left in (4, 3, 2, 1):
        r = anonymous.post(
            f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": wrong(code)}
        )
        assert r.status_code == 400 and r.json()["error"]["code"] == "sms_code_incorrect"
        assert r.json()["error"]["details"]["attempts_left"] == left
    last = anonymous.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": wrong(code)}
    )
    assert last.json()["error"]["code"] == "sms_too_many_attempts"
    # Even the right code no longer works on this challenge.
    right = anonymous.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code}
    )
    assert right.status_code == 400 and right.json()["error"]["code"] == "sms_too_many_attempts"
    assert anonymous.get(f"{API}/auth/me").json()["authenticated"] is False


def test_a_challenge_cannot_be_replayed(app, sms_on) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    national = number()
    first = TestClient(app)
    challenge = request_code(first, national).json()["challenge_id"]
    code = code_for(national)
    assert (
        first.post(
            f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code}
        ).status_code
        == 200
    )
    replay = TestClient(app).post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code}
    )
    assert replay.status_code == 400 and replay.json()["error"]["code"] == "sms_challenge_invalid"


def test_concurrent_verification_succeeds_once(app, sms_on) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    national = number()
    challenge = request_code(TestClient(app), national).json()["challenge_id"]
    code = code_for(national)
    results: list[int] = []

    def attempt() -> None:
        r = TestClient(app).post(
            f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code}
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 400, 400, 400]


def test_expired_challenge_is_refused(anonymous, sms_on) -> None:  # noqa: ANN001
    from app.db.session import session_factory

    national = number()
    challenge = request_code(anonymous, national).json()["challenge_id"]
    with session_factory()() as s, s.begin():
        # The trigger forbids changing expiry; bypass it the way only a superuser can.
        s.execute(text("SET LOCAL session_replication_role = replica"))
        s.execute(
            text(
                "UPDATE phone_challenge SET created_at = now() - interval '1 hour', expires_at = now() - interval '1 minute' WHERE id = :i"
            ),
            {"i": challenge},
        )
    r = anonymous.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code_for(national)}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "sms_code_expired"


def test_consumed_challenge_is_immutable_in_the_database(anonymous, sms_on) -> None:  # noqa: ANN001
    from sqlalchemy.exc import DBAPIError

    from app.db.session import session_factory

    national = number()
    assert register_by_phone(anonymous, national).status_code == 200
    with session_factory()() as s, pytest.raises(DBAPIError), s.begin():
        s.execute(
            text("UPDATE phone_challenge SET consumed_at = NULL WHERE phone_e164 = :p"),
            {"p": f"+968{national}"},
        )


def test_invalid_input_is_explained(anonymous, sms_on) -> None:  # noqa: ANN001
    landline = request_code(anonymous, "24123456")
    assert landline.status_code == 422 and landline.json()["error"]["code"] == "invalid_phone"
    bad_code = anonymous.post(
        f"{API}/auth/phone/verify", json={"challenge_id": str(uuid.uuid4()), "code": "12ab"}
    )
    assert bad_code.json()["error"]["code"] == "invalid_code_format"
    unknown = anonymous.post(
        f"{API}/auth/phone/verify", json={"challenge_id": str(uuid.uuid4()), "code": "123456"}
    )
    assert unknown.status_code == 400 and unknown.json()["error"]["code"] == "sms_challenge_invalid"


# ------------------------------------------------------------------ limits and delivery errors


def test_resend_cooldown_and_number_limit(anonymous, sms_on) -> None:  # noqa: ANN001
    _apply({"OSRIP_SMS_RESEND_SECONDS": "60", "OSRIP_SMS_PER_NUMBER_HOUR": "2"})
    national = number()
    assert request_code(anonymous, national).status_code == 202
    again = request_code(anonymous, national)
    assert again.status_code == 429 and again.json()["error"]["code"] == "sms_resend_cooldown"
    assert 0 < again.json()["error"]["details"]["retry_after"] <= 60
    _apply({"OSRIP_SMS_RESEND_SECONDS": "0"})
    assert request_code(anonymous, national).status_code == 202
    limited = request_code(anonymous, national)
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "sms_number_limit"


def test_client_limit(anonymous, sms_on) -> None:  # noqa: ANN001
    from app.core import security
    from app.core.config import get_settings
    from app.db.session import session_factory

    # Count only this test's requests: other tests share the test client's address.
    with session_factory()() as s, s.begin():
        key = security.keyed_digest(get_settings().client_hash_key.get_secret_value(), "testclient")
        used = s.scalar(
            text(
                "SELECT count(*) FROM phone_challenge WHERE client_hash = :k AND created_at > now() - interval '1 hour'"
            ),
            {"k": key},
        )
    _apply({"OSRIP_SMS_PER_CLIENT_HOUR": str(used + 2)})
    assert request_code(anonymous, number()).status_code == 202
    assert request_code(anonymous, number()).status_code == 202
    third = request_code(anonymous, number())
    assert third.status_code == 429 and third.json()["error"]["code"] == "sms_client_limit"


def test_delivery_failures_are_explained(anonymous, sms_on) -> None:  # noqa: ANN001
    undeliverable = request_code(anonymous, "90000000")
    assert (
        undeliverable.status_code == 422
        and undeliverable.json()["error"]["code"] == "sms_undeliverable"
    )
    outage = request_code(anonymous, "90000001")
    assert (
        outage.status_code == 503 and outage.json()["error"]["code"] == "sms_provider_unavailable"
    )
    assert "e-mail" in outage.json()["error"]["message"]


# ------------------------------------------------------------------ linking


def test_linking_needs_a_session_and_verified_ownership(
    make_user, login, anonymous, sms_on
) -> None:  # noqa: ANN001
    assert request_code(anonymous, number(), purpose="link").status_code == 401
    person = make_user()
    client = login(person)
    national = number()
    challenge = request_code(client, national, purpose="link").json()["challenge_id"]
    assert client.get(f"{API}/auth/me").json()["phone"] is None  # not linked before verification
    r = client.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code_for(national)}
    )
    assert r.status_code == 200 and r.json()["status"] == "linked"
    me = client.get(f"{API}/auth/me").json()
    assert me["phone"].endswith(national[-2:]) and me["email"] == person.email


def test_a_number_on_another_account_is_never_moved(make_user, login, app, sms_on) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    national = number()
    assert register_by_phone(TestClient(app), national).status_code == 200
    client = login(make_user())
    challenge = request_code(client, national, purpose="link").json()["challenge_id"]
    r = client.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code_for(national)}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "phone_taken"
    assert client.get(f"{API}/auth/me").json()["phone"] is None


def test_link_challenge_cannot_be_used_by_another_session(make_user, login, sms_on) -> None:  # noqa: ANN001
    a, b = login(make_user()), login(make_user())
    national = number()
    challenge = request_code(a, national, purpose="link").json()["challenge_id"]
    r = b.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code_for(national)}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "sms_challenge_invalid"


def test_phone_account_adds_an_email_only_after_proving_it(app, make_user, sms_on) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    from tests.test_identity_integration import last_token, outbox_count

    client = TestClient(app)
    assert register_by_phone(client, number()).status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    address = f"linked-{uuid.uuid4().hex[:8]}@test.invalid"
    assert client.post(f"{API}/auth/email/link", json={"email": address}).status_code == 202
    assert client.get(f"{API}/auth/me").json()["email"] is None  # not before the link is opened
    token = last_token(address, "link_email")
    assert client.post(f"{API}/auth/email/link/confirm", json={"token": token}).status_code == 200
    me = client.get(f"{API}/auth/me").json()
    assert me["email"] == address and me["email_verified"] is True
    assert (
        client.post(f"{API}/auth/email/link/confirm", json={"token": token}).status_code == 400
    )  # single use

    # Another account's address: same answer, no link is sent, the owner is told instead.
    other = TestClient(app)
    assert register_by_phone(other, number()).status_code == 200
    other.headers["X-CSRF-Token"] = other.cookies["osrip_csrf"]
    owner = make_user()
    before = outbox_count(owner.email)
    assert other.post(f"{API}/auth/email/link", json={"email": owner.email}).status_code == 202
    assert outbox_count(owner.email) == before + 1
    from app.db.session import session_factory
    from app.models import AuthToken

    with session_factory()() as s, s.begin():
        assert s.scalar(select(AuthToken).where(AuthToken.email == owner.email)) is None


def test_audit_never_stores_the_full_number(anonymous, sms_on) -> None:  # noqa: ANN001
    from app.db.session import session_factory

    national = number()
    assert register_by_phone(anonymous, national).status_code == 200
    with session_factory()() as s, s.begin():
        leaked = s.scalar(
            text(
                "SELECT count(*) FROM audit_event WHERE metadata::text LIKE :p OR actor_label LIKE :p"
            ),
            {"p": f"%{national}%"},
        )
    assert leaked == 0


# ------------------------------------------------------------------ production safety


def test_production_refuses_the_test_provider(database_url: str, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("OSRIP_ENVIRONMENT", "production")
    monkeypatch.setenv("OSRIP_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("OSRIP_CLIENT_HASH_KEY", "k" * 48)
    monkeypatch.setenv("OSRIP_EMAIL_BACKEND", "disabled")
    monkeypatch.setenv("OSRIP_ASSISTANT_PROVIDER", "disabled")
    monkeypatch.setenv("OSRIP_PUBLIC_BASE_URL", "https://osrip.example.org")
    monkeypatch.setenv("OSRIP_SMS_ENABLED", "true")
    monkeypatch.setenv("OSRIP_SMS_PROVIDER", "test")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SMS_PROVIDER=test"):
            create_app()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_sms_outbox_is_closed_outside_development(anonymous, sms_on) -> None:  # noqa: ANN001
    _apply({"OSRIP_ENVIRONMENT": "production"})
    try:
        assert anonymous.get(f"{API}/dev/sms-outbox").status_code == 404
    finally:
        _apply({"OSRIP_ENVIRONMENT": None})
