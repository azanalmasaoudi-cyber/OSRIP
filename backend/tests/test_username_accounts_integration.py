"""Registration and sign-in with a username and password only.

The username rule (1-10 Arabic or English letters and digits, reserved names), uniqueness
without regard to case or Arabic look-alike letters, the lowest role whatever the request says,
throttled sign-in failures and registrations, the retired e-mail, phone, Google and Microsoft
methods (410, no account, no session), an older account with a longer username that keeps
working, the database's own check, usernames given by an administrator, the one-time recovery
code (stored as a hash only, spent on use) and an administrator's reset to a temporary password.
"""

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
    """A unique username of exactly 10 characters."""
    return f"{prefix}{uuid.uuid4().hex}"[:10]


def register(client: TestClient, username: str, password: str = PASSWORD, **extra):  # noqa: ANN003, ANN201
    return client.post(
        f"{API}/auth/register/username",
        json={"username": username, "password": password, "password_confirm": password, **extra},
    )


def sign_in(app, username: str, password: str = PASSWORD):  # noqa: ANN001, ANN201
    client = TestClient(app)
    return client, client.post(
        f"{API}/auth/login", json={"username": username, "password": password}
    )


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
    assert len(username) == 10, "exactly the longest a username may be"
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


def test_arabic_usernames_register_and_sign_in(app) -> None:  # noqa: ANN001
    tag = "".join("ابتثجحخدذر"[int(c, 16) % 10] for c in uuid.uuid4().hex[:4])
    username = f"أحمد{tag}٢٠"  # Arabic letters and Arabic-Indic digits, 10 characters
    first = TestClient(app)
    r = register(first, username)
    assert r.status_code == 201, r.text
    stored_name = r.json()["me"]["username"]
    assert stored_name == f"أحمد{tag}20", "digits are stored as 0-9"
    # Spelling variants that look alike are the same name: taken for registration, and
    # accepted for sign-in.
    look_alike = f"احمد{tag}20"
    taken = register(TestClient(app), look_alike)
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "username_taken"
    _, signed = sign_in(app, f"  {look_alike} ")
    assert signed.status_code == 200 and signed.json()["username"] == stored_name


def test_ten_characters_at_most(anonymous) -> None:  # noqa: ANN001
    ten = name("Ten")
    assert register(anonymous, ten).status_code == 201
    for too_long in (name("Eleven") + "x", "سالمسالمسالم"):
        r = register(TestClient(anonymous.app), too_long)
        assert r.status_code == 422, r.text
        body = r.json()["error"]
        assert body["code"] == "username_too_long"
        assert body["message"] == "Username must not exceed 10 characters."
    one = register(TestClient(anonymous.app), f"q{uuid.uuid4().hex[:1]}"[:1])
    assert one.status_code in (201, 409), "one letter is a valid username"


@pytest.mark.parametrize(
    ("username", "password", "confirm", "code"),
    [
        ("   ", PASSWORD, PASSWORD, "username_required"),
        ("9lives", PASSWORD, PASSWORD, "invalid_username"),
        ("name space", PASSWORD, PASSWORD, "invalid_username"),
        ("salimسالم", PASSWORD, PASSWORD, "invalid_username"),
        ("عَلي", PASSWORD, PASSWORD, "invalid_username"),
        ("a@b.om", PASSWORD, PASSWORD, "invalid_username"),
        ("+96890000", PASSWORD, PASSWORD, "invalid_username"),
        ("x" * 11, PASSWORD, PASSWORD, "username_too_long"),
        ("Admin", PASSWORD, PASSWORD, "username_reserved"),
        ("admin_2", PASSWORD, PASSWORD, "username_reserved"),
        ("المدير", PASSWORD, PASSWORD, "username_reserved"),
        ("Mulhim", PASSWORD, PASSWORD, "username_reserved"),
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
        client.post(f"{API}/auth/login", json={"username": username, "password": f"wrong-{i}"})
        .status_code
        for i in range(6)
    ]  # fmt: skip
    assert codes[:5] == [401] * 5 and codes[5] == 429
    blocked = client.post(f"{API}/auth/login", json={"username": username, "password": PASSWORD})
    assert blocked.status_code == 429, "even the right password waits out the window"

    from app.core import ratelimit

    ratelimit.reset()  # every test client shares one address
    burst = TestClient(app)
    statuses = [register(burst, name("burst")).status_code for _ in range(21)]
    assert statuses[:20] == [201] * 20 and statuses[20] == 429


RETIRED = [
    (
        "post",
        "/auth/register",
        {"email": "new@test.invalid", "display_name": "N", "password": PASSWORD},
    ),
    ("post", "/auth/verify-email", {"token": "t" * 40}),
    ("post", "/auth/verify-email/resend", {"email": "x@test.invalid"}),
    ("post", "/auth/password/forgot", {"email": "x@test.invalid"}),
    ("post", "/auth/password/reset", {"token": "t" * 40, "password": PASSWORD}),
    ("post", "/auth/magic-link", {"email": "x@test.invalid"}),
    ("post", "/auth/magic-link/consume", {"token": "t" * 40}),
    ("post", "/auth/phone/request", {"country_code": "+968", "number": "90000001"}),
    ("post", "/auth/phone/verify", {"challenge_id": "c", "code": "123456"}),
    ("post", "/auth/email/link", {"email": "x@test.invalid"}),
    ("post", "/auth/email/link/confirm", {"token": "t" * 40}),
    ("get", "/auth/oidc/google/start", None),
    ("get", "/auth/oidc/microsoft/callback?code=c&state=s", None),
    ("get", "/auth/identities", None),
]


def test_only_the_username_signs_in(app, db) -> None:  # noqa: ANN001
    """An account that kept an e-mail address and a phone number on record: the username and
    password sign it in; the address, the number and every retired method do not."""
    from datetime import UTC, datetime

    from app.core import security
    from app.models import AppUser, UserRole

    username = name("Old")
    address = f"{username.lower()}@test.invalid"
    with db.begin():
        user = AppUser(
            username=username,
            email=address,
            phone_e164="+96890000123",
            phone_verified_at=datetime.now(UTC),
            display_name="Older account",
            password_hash=security.hash_password(PASSWORD),
            created_via="self_registration",
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code=Role.VIEWER.value))
    for identifier in (address, "+96890000123", "90000123"):
        _, r = sign_in(app, identifier)
        assert r.status_code in (401, 422), (identifier, r.text)
    client = TestClient(app)
    for method, path, body in RETIRED:
        r = getattr(client, method)(f"{API}{path}", **({"json": body} if body else {}))
        assert r.status_code == 410, (path, r.status_code)
        assert r.json()["error"]["code"] == "sign_in_method_retired"
    assert client.get(f"{API}/auth/me").json()["authenticated"] is False, "no session opened"
    assert db.scalar(select(AppUser).where(AppUser.email == "new@test.invalid")) is None
    _, ok = sign_in(app, username)
    assert ok.status_code == 200, ok.text
    providers = client.get(f"{API}/auth/providers").json()
    assert providers == {"password": True, "registration": True, "methods": ["username_password"]}


def _older_account(db, username: str) -> uuid.UUID:  # noqa: ANN001
    """An account registered before the 10-character rule (migration 0033), inserted as it was
    then: before the rule's trigger existed."""
    from sqlalchemy import text

    from app.core import security
    from app.models import AppUser, UserRole

    with db.begin():
        db.execute(text("ALTER TABLE app_user DISABLE TRIGGER trg_app_user_username_policy"))
        user = AppUser(
            username=username,
            display_name="Older",
            password_hash=security.hash_password(PASSWORD),
            created_via="self_registration",
        )
        db.add(user)
        db.flush()
        db.execute(text("ALTER TABLE app_user ENABLE TRIGGER trg_app_user_username_policy"))
        db.add(UserRole(user_id=user.id, role_code=Role.VIEWER.value))
        return user.id


def test_an_older_longer_username_keeps_working(app, db) -> None:  # noqa: ANN001
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    username = f"Older.{uuid.uuid4().hex[:4]}.om"  # 13 characters, as before the rule
    user_id = _older_account(db, username)
    client, signed = sign_in(app, username.upper())
    assert signed.status_code == 200 and signed.json()["username"] == username
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    # Other changes to the account still work: the rule applies only to a new or changed name.
    changed = client.post(
        f"{API}/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "amber-lantern-7702"},
    )
    assert changed.status_code == 200, changed.text
    assert client.post(f"{API}/auth/recovery-code",
                       json={"current_password": "amber-lantern-7702"}).status_code == 200  # fmt: skip
    _, again = sign_in(app, username, "amber-lantern-7702")
    assert again.status_code == 200
    # Renaming it to another name that breaks the rule is refused by the database itself.
    with pytest.raises(IntegrityError), db.begin():
        db.execute(
            text("UPDATE app_user SET username = :n, username_key = lower(:n) WHERE id = :u"),
            {"n": username + "x", "u": user_id},
        )


@pytest.mark.parametrize("bad", ["x" * 11, "9lives", "a b", "salimسالم", "عـلي", ""])
def test_the_database_refuses_a_username_that_breaks_the_rule(db, bad: str) -> None:  # noqa: ANN001
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), db.begin():
        db.execute(
            text(
                "INSERT INTO app_user (username, username_key, display_name, password_hash) "
                "VALUES (:n, lower(:n), 'x', 'x')"
            ),
            {"n": bad},
        )


def test_an_administrator_gives_an_older_account_a_username(app, db, make_user, login) -> None:  # noqa: ANN001
    """An account that signed in with its e-mail address has no username: an administrator
    gives it one (audited) and a temporary password; it then signs in with them."""
    from app.core import security
    from app.models import AppUser, AuditEvent, UserRole

    address = f"old-{uuid.uuid4().hex[:8]}@test.invalid"
    with db.begin():
        user = AppUser(
            email=address,
            display_name="E-mail account",
            password_hash=security.hash_password(PASSWORD),
            created_via="self_registration",
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code=Role.VIEWER.value))
        user_id = user.id
    _, by_address = sign_in(app, address)
    assert by_address.status_code in (401, 422), "the address no longer signs in"
    viewer = login(make_user())
    assert viewer.post(f"{API}/admin/users/{user_id}/username",
                       json={"username": "x"}).status_code == 403  # fmt: skip
    admin = login(make_user(Role.ADMINISTRATOR))
    for bad, code in (("x" * 11, "username_too_long"), ("Azzan", "username_reserved")):
        r = admin.post(f"{API}/admin/users/{user_id}/username", json={"username": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == code
    new_name = name("Given")
    given = admin.post(f"{API}/admin/users/{user_id}/username", json={"username": new_name})
    assert given.status_code == 200 and given.json()["username"] == new_name
    _, signed = sign_in(app, new_name)
    assert signed.status_code == 200, "the existing password works with the new username"
    event = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "user.username", AuditEvent.entity_id == str(user_id)
        )
    ).first()
    assert event is not None and event.metadata_ == {"previous": None, "username": new_name}


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
