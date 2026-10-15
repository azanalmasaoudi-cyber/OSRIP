"""Self-service accounts: registration, verification, recovery and magic links.

Uses the development mail outbox (OSRIP_EMAIL_BACKEND=outbox, the default outside
production) to read the links a user would receive.
"""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select, text

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration

PASSWORD = f"pw-{uuid.uuid4().hex}"  # random per run; test database only


@pytest.fixture(autouse=True)
def _clear_limits() -> None:
    from app.core import ratelimit

    ratelimit.reset()


def email() -> str:
    return f"new-{uuid.uuid4().hex[:10]}@test.invalid"


def last_token(address: str, purpose: str) -> str:
    from app.db.session import session_factory
    from app.models import EmailOutbox

    with session_factory()() as s, s.begin():
        body = s.scalar(
            select(EmailOutbox.body_text)
            .where(EmailOutbox.to_address == address, EmailOutbox.purpose == purpose)
            .order_by(EmailOutbox.id.desc())
            .limit(1)
        )
    assert body is not None, f"no {purpose} message for {address}"
    match = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    assert match
    return match.group(1)


def outbox_count(address: str) -> int:
    from app.db.session import session_factory
    from app.models import EmailOutbox

    with session_factory()() as s, s.begin():
        return len(s.scalars(select(EmailOutbox.id).where(EmailOutbox.to_address == address)).all())


def register(client, address: str) -> None:  # noqa: ANN001
    r = client.post(
        f"{API}/auth/register",
        json={"email": address, "display_name": "New user", "password": PASSWORD},
    )
    assert r.status_code == 202, r.text


def login(client, address: str, password: str = PASSWORD):  # noqa: ANN001, ANN201
    return client.post(f"{API}/auth/login", json={"email": address, "password": password})


def test_registration_verification_and_ordinary_access(anonymous) -> None:  # noqa: ANN001
    address = email()
    register(anonymous, address)
    # Unverified: the right password still does not open a session.
    refused = login(anonymous, address)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "email_not_verified"

    token = last_token(address, "verify_email")
    assert anonymous.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    me = login(anonymous, address)
    assert me.status_code == 200
    body = me.json()
    assert body["roles"] == ["viewer"] and body["email_verified"] is True
    assert "import.publish" not in body["permissions"] and "user.manage" not in body["permissions"]
    assert "assistant.use" in body["permissions"]


def test_verification_token_is_single_use(anonymous) -> None:  # noqa: ANN001
    address = email()
    register(anonymous, address)
    token = last_token(address, "verify_email")
    assert anonymous.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    again = anonymous.post(f"{API}/auth/verify-email", json={"token": token})
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_or_expired_token"


def test_expired_and_wrong_purpose_tokens_fail(anonymous) -> None:  # noqa: ANN001
    from app.core import security
    from app.db.session import session_factory
    from app.models import AppUser

    address = email()
    register(anonymous, address)
    token = last_token(address, "verify_email")
    # A verification token cannot be used as a sign-in link.
    wrong = anonymous.post(f"{API}/auth/magic-link/consume", json={"token": token})
    assert wrong.status_code == 400

    expired = security.new_token()
    with session_factory()() as s, s.begin():
        user_id = s.scalar(select(AppUser.id).where(AppUser.email == address))
        s.execute(
            text(
                "INSERT INTO auth_token (user_id, purpose, token_hash, created_at, expires_at) "
                "VALUES (:u, 'verify_email', :h, now() - interval '2 days', now() - interval '1 day')"
            ),
            {"u": user_id, "h": security.token_digest(expired)},
        )
    assert anonymous.post(f"{API}/auth/verify-email", json={"token": expired}).status_code == 400


def test_a_used_token_cannot_be_revived_in_the_database(anonymous, db) -> None:  # noqa: ANN001
    from sqlalchemy.exc import DBAPIError

    from app.core import security

    address = email()
    register(anonymous, address)
    token = last_token(address, "verify_email")
    anonymous.post(f"{API}/auth/verify-email", json={"token": token})
    with pytest.raises(DBAPIError, match="already used"), db.begin():
        db.execute(
            text("UPDATE auth_token SET used_at = NULL WHERE token_hash = :h"),
            {"h": security.token_digest(token)},
        )


def test_answers_do_not_reveal_whether_an_address_is_registered(anonymous) -> None:  # noqa: ANN001
    address = email()
    register(anonymous, address)
    last_token(address, "verify_email")
    existing = anonymous.post(
        f"{API}/auth/register", json={"email": address, "display_name": "X", "password": PASSWORD}
    )
    unknown = anonymous.post(f"{API}/auth/password/forgot", json={"email": email()})
    known = anonymous.post(f"{API}/auth/password/forgot", json={"email": address})
    assert existing.status_code == unknown.status_code == known.status_code == 202
    assert existing.json() == unknown.json() == known.json()


def test_password_reset_is_single_use_and_signs_out_everywhere(anonymous, app) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    address = email()
    register(anonymous, address)
    anonymous.post(f"{API}/auth/verify-email", json={"token": last_token(address, "verify_email")})
    other_device = TestClient(app)
    assert login(other_device, address).status_code == 200
    assert other_device.get(f"{API}/auth/me").json()["authenticated"] is True

    anonymous.post(f"{API}/auth/password/forgot", json={"email": address})
    token = last_token(address, "reset_password")
    new_password = f"new-{uuid.uuid4().hex}"
    weak = anonymous.post(f"{API}/auth/password/reset", json={"token": token, "password": "short"})
    assert weak.status_code == 422
    ok = anonymous.post(
        f"{API}/auth/password/reset", json={"token": token, "password": new_password}
    )
    assert ok.status_code == 200
    again = anonymous.post(
        f"{API}/auth/password/reset", json={"token": token, "password": new_password}
    )
    assert again.status_code == 400
    assert other_device.get(f"{API}/auth/me").json()["authenticated"] is False  # session revoked
    assert login(anonymous, address).status_code == 401
    assert login(anonymous, address, new_password).status_code == 200


def test_magic_link_signs_in_once(anonymous, app) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    address = email()
    register(anonymous, address)
    # Unverified accounts get no sign-in link.
    anonymous.post(f"{API}/auth/magic-link", json={"email": address})
    assert outbox_count(address) == 1  # only the verification message
    anonymous.post(f"{API}/auth/verify-email", json={"token": last_token(address, "verify_email")})

    assert anonymous.post(f"{API}/auth/magic-link", json={"email": address}).status_code == 202
    token = last_token(address, "magic_link")
    browser = TestClient(app)
    first = browser.post(f"{API}/auth/magic-link/consume", json={"token": token})
    assert first.status_code == 200 and first.json()["email"] == address
    assert browser.get(f"{API}/auth/me").json()["authenticated"] is True
    assert (
        TestClient(app).post(f"{API}/auth/magic-link/consume", json={"token": token}).status_code
        == 400
    )


def test_new_accounts_cannot_escalate_and_admins_grant_roles_explicitly(
    anonymous, make_user, login
) -> None:  # noqa: ANN001
    from app.domain.enums import Role

    address = email()
    register(anonymous, address)
    anonymous.post(f"{API}/auth/verify-email", json={"token": last_token(address, "verify_email")})
    from fastapi.testclient import TestClient

    user = TestClient(anonymous.app)
    me = user.post(f"{API}/auth/login", json={"email": address, "password": PASSWORD}).json()
    user.headers["X-CSRF-Token"] = user.cookies["osrip_csrf"]
    # The new account cannot give itself a role.
    assert (
        user.post(f"{API}/admin/users/{me['user_id']}/roles", json={"role": "analyst"}).status_code
        == 403
    )
    admin = login(make_user(Role.ADMINISTRATOR))
    assert (
        admin.post(f"{API}/admin/users/{me['user_id']}/roles", json={"role": "analyst"}).status_code
        == 200
    )
    assert "analysis.run" in user.get(f"{API}/auth/me").json()["permissions"]


def test_email_features_report_when_delivery_is_not_configured(anonymous, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "email_backend", "disabled")
    providers = anonymous.get(f"{API}/auth/providers").json()
    assert providers["registration"] is False and providers["email_delivery"] == "disabled"
    assert providers["oidc"] == {"google": False, "microsoft": False}
    r = anonymous.post(
        f"{API}/auth/register", json={"email": email(), "display_name": "X", "password": PASSWORD}
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "email_not_configured"


def test_email_requests_are_limited_per_client(anonymous, monkeypatch) -> None:  # noqa: ANN001
    from app.api.routes import auth

    monkeypatch.setattr(auth, "EMAIL_REQUESTS_PER_CLIENT_HOUR", 2)
    for _ in range(2):
        assert (
            anonymous.post(f"{API}/auth/password/forgot", json={"email": email()}).status_code
            == 202
        )
    assert anonymous.post(f"{API}/auth/password/forgot", json={"email": email()}).status_code == 429
