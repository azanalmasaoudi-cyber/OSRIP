"""Registration and sign-in with a username and password only: rules and case-insensitive
uniqueness, the lowest role whatever the request says, throttled sign-in failures and
registrations, existing e-mail accounts unaffected, the one-time recovery code (stored as a
hash only, spent on use) and an administrator's reset to a temporary password."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.enums import Role
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration
PASSWORD = "river-falcon-9417"  # noqa: S105 - a test-only password


@pytest.fixture(autouse=True)
def _clear_limits() -> Iterator[None]:
    from sqlalchemy import delete, func

    from app.core import ratelimit
    from app.db.session import session_factory
    from app.models import LoginAttempt

    ratelimit.reset()
    with session_factory()() as s:
        started = s.scalar(select(func.now()))
    yield
    ratelimit.reset()
    # The failed sign-ins and recovery attempts made here count against the one address every
    # test client shares; removed, so later tests are not throttled by them.
    with session_factory()() as s, s.begin():
        s.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at >= started))


def name(prefix: str = "user") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def register(client: TestClient, username: str, password: str = PASSWORD, **extra):  # noqa: ANN003, ANN201
    return client.post(
        f"{API}/auth/register/username",
        json={"username": username, "password": password, "password_confirm": password, **extra},
    )


def sign_in(app, username: str, password: str = PASSWORD):  # noqa: ANN001, ANN201
    client = TestClient(app)
    return client, client.post(f"{API}/auth/login", json={"email": username, "password": password})


def stored(username: str) -> tuple[str | None, list[str]]:
    from app.db.session import session_factory
    from app.models import AppUser, UserRole

    with session_factory()() as s:
        user = s.scalar(select(AppUser).where(AppUser.username == username))
        assert user is not None
        roles = list(s.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id)))
        return user.recovery_code_hash, roles


def test_registration_needs_only_a_username_and_password(app, anonymous) -> None:  # noqa: ANN001
    username = name("Salim")
    r = register(anonymous, username, roles=["administrator"], email="x@test.invalid")
    assert r.status_code == 201, r.text
    body = r.json()
    code = body["recovery_code"]
    assert len(code) == 24 and code.count("-") == 4, "five groups of four"
    me = body["me"]
    assert (me["username"], me["email"], me["phone"]) == (username, None, None)
    assert me["roles"] == ["viewer"], "a public registration never gets more than viewer"
    assert me["has_recovery_code"] is True
    assert anonymous.get(f"{API}/auth/me").json()["authenticated"] is True, "signed in at once"
    digest, roles = stored(username)
    assert roles == [Role.VIEWER.value]
    assert digest and digest.startswith("$argon2id$") and code.replace("-", "") not in digest

    # Sign-in with the username in any case, and only with the right password.
    _, ok = sign_in(app, username.upper())
    assert ok.status_code == 200 and ok.json()["username"] == username
    _, wrong = sign_in(app, username, "not-the-password-1")
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_credentials"


def test_usernames_are_unique_without_regard_to_case(anonymous, app) -> None:  # noqa: ANN001
    username = name("Mona")
    assert register(anonymous, username).status_code == 201
    again = register(TestClient(app), username.swapcase())
    assert again.status_code == 409 and again.json()["error"]["code"] == "username_taken"


@pytest.mark.parametrize(
    ("username", "password", "confirm", "code"),
    [
        ("ab", PASSWORD, PASSWORD, "invalid_username"),
        ("9lives", PASSWORD, PASSWORD, "invalid_username"),
        ("name with space", PASSWORD, PASSWORD, "invalid_username"),
        ("سالم", PASSWORD, PASSWORD, "invalid_username"),
        ("Admin", PASSWORD, PASSWORD, "username_reserved"),
        ("validname1", PASSWORD, PASSWORD + "x", "password_mismatch"),
        ("validname2", "short-pw", "short-pw", "weak_password"),
        ("validname3", "xx-validname3-xx", "xx-validname3-xx", "password_contains_username"),
        ("validname4", "aaaaaaaaaaaa", "aaaaaaaaaaaa", "password_too_simple"),
    ],
)
def test_rules_are_explained(
    anonymous, username: str, password: str, confirm: str, code: str
) -> None:  # noqa: ANN001
    r = anonymous.post(
        f"{API}/auth/register/username",
        json={"username": username, "password": password, "password_confirm": confirm},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_failed_sign_ins_and_registrations_are_throttled(app, anonymous) -> None:  # noqa: ANN001
    username = name("Huda")
    assert register(anonymous, username).status_code == 201
    client = TestClient(app)
    codes = [
        client.post(f"{API}/auth/login", json={"email": username, "password": f"wrong-{i}-pass"})
        .status_code
        for i in range(6)
    ]  # fmt: skip
    assert codes[:5] == [401] * 5 and codes[5] == 429
    blocked = client.post(f"{API}/auth/login", json={"email": username, "password": PASSWORD})
    assert blocked.status_code == 429, "even the right password waits out the window"

    from app.core import ratelimit

    ratelimit.reset()  # every test client shares one address
    burst = TestClient(app)
    statuses = [register(burst, name("burst")).status_code for _ in range(21)]
    assert statuses[:20] == [201] * 20 and statuses[20] == 429


def test_existing_email_accounts_still_sign_in(make_user, login) -> None:  # noqa: ANN001
    person = make_user()
    me = login(person).get(f"{API}/auth/me").json()
    assert me["authenticated"] and me["email"] == person.email and me["username"] is None


def test_the_recovery_code_resets_the_password_once(app, anonymous) -> None:  # noqa: ANN001
    username = name("Rashid")
    code = register(anonymous, username).json()["recovery_code"]
    elsewhere, _ = sign_in(app, username)
    new_password = "olive-harbour-5820"  # noqa: S105 - test only

    def recover(recovery_code: str, password: str = new_password):  # noqa: ANN202
        return TestClient(app).post(
            f"{API}/auth/recover",
            json={"username": username, "recovery_code": recovery_code,
                  "new_password": password, "new_password_confirm": password},
        )  # fmt: skip

    wrong = recover("AAAA-BBBB-CCCC-DDDD-EEEE")
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_recovery"
    unknown = TestClient(app).post(
        f"{API}/auth/recover",
        json={"username": name("nobody"), "recovery_code": code,
              "new_password": new_password, "new_password_confirm": new_password},
    )  # fmt: skip
    assert unknown.status_code == 401, "the same answer for an unknown username"

    done = recover(code.lower().replace("-", " "))  # case and separators do not matter
    assert done.status_code == 200, done.text
    fresh = done.json()["recovery_code"]
    assert fresh != code and done.json()["me"]["username"] == username
    assert recover(code).status_code == 401, "a recovery code works once"
    assert elsewhere.get(f"{API}/auth/me").json()["authenticated"] is False, "other sessions end"
    assert anonymous.get(f"{API}/auth/me").json()["authenticated"] is False
    assert sign_in(app, username)[1].status_code == 401, "the old password no longer works"
    assert sign_in(app, username, new_password)[1].status_code == 200


def test_a_new_recovery_code_needs_the_current_password(app, anonymous) -> None:  # noqa: ANN001
    username = name("Aisha")
    first = register(anonymous, username).json()["recovery_code"]
    anonymous.headers["X-CSRF-Token"] = anonymous.cookies["osrip_csrf"]
    refused = anonymous.post(
        f"{API}/auth/recovery-code", json={"current_password": "wrong-one-123"}
    )
    assert refused.status_code == 403
    second = anonymous.post(f"{API}/auth/recovery-code", json={"current_password": PASSWORD})
    assert second.status_code == 200 and second.json()["recovery_code"] != first
    old = TestClient(app).post(
        f"{API}/auth/recover",
        json={"username": username, "recovery_code": first,
              "new_password": "cedar-meadow-3311", "new_password_confirm": "cedar-meadow-3311"},
    )  # fmt: skip
    assert old.status_code == 401, "the replaced code stops working"


def test_an_administrator_resets_to_a_temporary_password(app, anonymous, make_user, login) -> None:  # noqa: ANN001
    username = name("Khalid")
    register(anonymous, username)
    from app.db.session import session_factory
    from app.models import AppUser

    with session_factory()() as s:
        user_id = s.scalar(select(AppUser.id).where(AppUser.username == username))
    viewer = login(make_user())
    assert viewer.post(f"{API}/admin/users/{user_id}/reset-password").status_code == 403
    admin_person = make_user(Role.ADMINISTRATOR)
    admin = login(admin_person)
    own = admin.post(f"{API}/admin/users/{admin_person.id}/reset-password")
    assert own.status_code == 422 and own.json()["error"]["code"] == "own_account"

    r = admin.post(f"{API}/admin/users/{user_id}/reset-password")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    temporary = r.json()["temporary_password"]
    assert anonymous.get(f"{API}/auth/me").json()["authenticated"] is False, "sessions ended"
    assert stored(username)[0] is None, "the old recovery code stops working"
    client, signed = sign_in(app, username, temporary)
    assert signed.status_code == 200 and signed.json()["password_change_required"] is True
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    changed = client.post(
        f"{API}/auth/password/change",
        json={"current_password": temporary, "new_password": "amber-lantern-7702"},
    )
    assert changed.status_code == 200 and changed.json()["password_change_required"] is False
