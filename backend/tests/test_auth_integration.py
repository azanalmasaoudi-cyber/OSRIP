"""Authentication, server-side authorization and session protection.

Booklet 3.9, 3.15 and 4.5; acceptance tests SEC01 and T06.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.domain.enums import DatasetVersionStatus, Permission, Role
from app.models import AppUser, AuditEvent, DatasetVersion, Observation, UserSession
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def approved_import(make_user, login):  # noqa: ANN001, ANN201
    """An approved, unpublished import created by a fully permitted manager."""
    manager = login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )
    source_id = register_synthetic_source(manager)
    return upload_validate_approve(
        manager,
        source_id,
        csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,48000,,,"),
    )


def state_of(db, imp: dict) -> tuple[DatasetVersionStatus, int]:  # noqa: ANN001
    db.expire_all()
    version = db.get(DatasetVersion, imp["version"]["id"])
    count = db.scalar(
        select(func.count())
        .select_from(Observation)
        .where(Observation.dataset_version_id == version.id)
    )
    return version.status, count


# ------------------------------------------------------------------ T06 / SEC01


def test_public_viewer_cannot_publish_even_with_a_direct_request(
    approved_import, anonymous, db
) -> None:  # noqa: ANN001
    before = state_of(db, approved_import)
    response = anonymous.post(f"{API}/imports/{approved_import['id']}/publish")
    assert response.status_code == 401
    assert state_of(db, approved_import) == before == (DatasetVersionStatus.APPROVED, 0)


@pytest.mark.parametrize(
    "roles, grants",
    [
        ((Role.VIEWER,), ()),
        ((Role.ANALYST,), ()),
        ((Role.DATA_MANAGER,), ()),  # can upload and validate, not publish
        ((Role.DATA_MANAGER,), (Permission.IMPORT_APPROVE,)),  # approval is not publication
        ((Role.ADMINISTRATOR,), ()),  # controls accounts, does not publish
    ],
)
def test_publication_needs_the_explicit_publish_grant(
    approved_import, make_user, login, db, roles, grants
) -> None:  # noqa: ANN001
    client = login(make_user(*roles, grants=grants))
    response = client.post(f"{API}/imports/{approved_import['id']}/publish")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    assert state_of(db, approved_import) == (DatasetVersionStatus.APPROVED, 0)


def test_denied_attempts_are_audited(approved_import, make_user, login, db) -> None:  # noqa: ANN001
    person = make_user(Role.VIEWER)
    login(person).post(f"{API}/imports/{approved_import['id']}/publish")
    event = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.actor_label == person.email)
        .order_by(AuditEvent.id.desc())
    ).first()
    assert event is not None and event.outcome == "denied"
    assert event.metadata_["missing"] == ["import.publish"]
    assert "password" not in str(event.metadata_).lower()


def test_viewer_cannot_upload_or_register_sources(make_user, login) -> None:  # noqa: ANN001
    viewer = login(make_user(Role.VIEWER))
    assert (
        viewer.post(
            f"{API}/sources",
            json={"data_mode": "synthetic", "dataset_title": "x", "geographic_coverage": "OM"},
        ).status_code
        == 403
    )
    assert viewer.get(f"{API}/imports").status_code == 403


def test_uploader_ownership_is_enforced_for_validation(approved_import, make_user, login) -> None:  # noqa: ANN001
    owner = login(make_user(Role.DATA_MANAGER))
    other = login(make_user(Role.DATA_MANAGER))
    source_id = register_synthetic_source(owner)
    imp = owner.post(
        f"{API}/imports",
        data={"source_id": source_id, "version_label": "own"},
        files={
            "file": (
                "f.csv",
                csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,1,,,"),
                "text/csv",
            )
        },
    ).json()
    refused = other.post(f"{API}/imports/{imp['id']}/validate")
    assert refused.status_code == 403
    assert owner.post(f"{API}/imports/{imp['id']}/validate").status_code == 200


def test_only_administrators_manage_accounts(make_user, login) -> None:  # noqa: ANN001
    manager = login(make_user(Role.DATA_MANAGER))
    denied = manager.post(
        f"{API}/admin/users",
        json={
            "email": "x@test.invalid",
            "display_name": "X",
            "password": "long-enough-password",
            "roles": ["administrator"],
        },
    )
    assert denied.status_code == 403
    admin = login(make_user(Role.ADMINISTRATOR))
    created = admin.post(
        f"{API}/admin/users",
        json={
            "email": "New.Person@Test.invalid",
            "display_name": "New",
            "password": "long-enough-password",
            "roles": ["analyst"],
        },
    )
    assert created.status_code == 201
    assert created.json()["email"] == "new.person@test.invalid" and created.json()["roles"] == [
        "analyst"
    ]


# ------------------------------------------------------------------ sign-in and sessions


def test_login_sets_protected_cookies_and_stores_only_hashes(app, make_user, db) -> None:  # noqa: ANN001
    person = make_user(Role.ANALYST)
    response = TestClient(app).post(
        f"{API}/auth/login", json={"email": person.email, "password": person.password}
    )
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("osrip_session="))
    csrf_cookie = next(c for c in cookies if c.startswith("osrip_csrf="))
    assert "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie
    assert "HttpOnly" not in csrf_cookie  # the app's own script echoes it in a header
    token = session_cookie.split(";")[0].split("=", 1)[1]

    user = db.scalar(select(AppUser).where(AppUser.email == person.email))
    assert user.password_hash.startswith("$argon2id$") and person.password not in user.password_hash
    stored = db.scalars(select(UserSession.token_hash).where(UserSession.user_id == user.id)).all()
    assert token not in stored and len(stored[0]) == 64  # SHA-256 digest only


def test_secure_flag_is_on_by_default(app, make_user, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    person = make_user(Role.VIEWER)
    monkeypatch.setattr(get_settings(), "session_cookie_secure", True)
    response = TestClient(app).post(
        f"{API}/auth/login", json={"email": person.email, "password": person.password}
    )
    assert all("Secure" in c for c in response.headers.get_list("set-cookie"))


def test_wrong_password_and_unknown_account_get_the_same_answer(anonymous, make_user) -> None:  # noqa: ANN001
    person = make_user(Role.VIEWER)
    wrong = anonymous.post(
        f"{API}/auth/login", json={"email": person.email, "password": "wrong-password-123"}
    )
    unknown = anonymous.post(
        f"{API}/auth/login", json={"email": "nobody@test.invalid", "password": "whatever-123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_repeated_failures_are_throttled_even_with_the_right_password(anonymous, make_user) -> None:  # noqa: ANN001
    person = make_user(Role.VIEWER)
    for _ in range(5):
        anonymous.post(
            f"{API}/auth/login", json={"email": person.email, "password": "wrong-password-123"}
        )
    blocked = anonymous.post(
        f"{API}/auth/login", json={"email": person.email, "password": person.password}
    )
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "too_many_attempts"


def test_state_changing_requests_need_the_csrf_token(make_user, login) -> None:  # noqa: ANN001
    client = login(make_user(Role.DATA_MANAGER))
    body = {"data_mode": "synthetic", "dataset_title": "CSRF test", "geographic_coverage": "OM"}
    del client.headers["X-CSRF-Token"]
    assert client.post(f"{API}/sources", json=body).json()["error"]["code"] == "csrf_failed"
    client.headers["X-CSRF-Token"] = "forged-token"
    assert client.post(f"{API}/sources", json=body).json()["error"]["code"] == "csrf_failed"
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    assert client.post(f"{API}/sources", json=body).status_code == 201


def test_suspended_account_loses_access_through_an_existing_session(make_user, login) -> None:  # noqa: ANN001
    person = make_user(Role.DATA_MANAGER)
    client = login(person)
    assert client.get(f"{API}/imports").status_code == 200
    admin = login(make_user(Role.ADMINISTRATOR))
    assert admin.post(f"{API}/admin/users/{person.id}/suspend").status_code == 200
    assert client.get(f"{API}/imports").status_code == 401
    assert client.get(f"{API}/auth/me").json()["authenticated"] is False
    # Reactivation does not revive the old session; a fresh sign-in is needed.
    admin.post(f"{API}/admin/users/{person.id}/reactivate")
    assert client.get(f"{API}/imports").status_code == 401


def test_revoked_grant_takes_effect_on_the_next_request(
    approved_import, make_user, login, db
) -> None:  # noqa: ANN001
    person = make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_PUBLISH,))
    client = login(person)
    admin = login(make_user(Role.ADMINISTRATOR))
    admin.delete(f"{API}/admin/users/{person.id}/grants/import.publish")
    assert client.post(f"{API}/imports/{approved_import['id']}/publish").status_code == 403
    assert state_of(db, approved_import)[1] == 0


def test_logout_revokes_the_session(make_user, login) -> None:  # noqa: ANN001
    client = login(make_user(Role.DATA_MANAGER))
    token = client.cookies["osrip_session"]
    assert client.post(f"{API}/auth/logout").status_code == 204
    client.cookies.set("osrip_session", token)  # replay the old cookie
    assert client.get(f"{API}/imports").status_code == 401


def test_service_accounts_cannot_sign_in(anonymous, db) -> None:  # noqa: ANN001
    from app.services.fixtures import SERVICE_EMAIL, seed_booklet_fixtures

    seed_booklet_fixtures(db)
    response = anonymous.post(f"{API}/auth/login", json={"email": SERVICE_EMAIL, "password": "!"})
    assert response.status_code == 401


# ------------------------------------------------------------------ append-only history


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM audit_event",
        "UPDATE audit_event SET outcome = 'success'",
        "TRUNCATE audit_event",
        "DELETE FROM recommendation_review",
        "TRUNCATE recommendation_review",
    ],
)
def test_history_tables_are_append_only(db, statement: str) -> None:  # noqa: ANN001
    with pytest.raises(DBAPIError, match="append-only"), db.begin():
        db.execute(text(statement))
