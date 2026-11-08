"""Custom roles and user groups (migration 0026), enforced by the server: a group's roles and
permissions reach its members on their next request and leave with them; built-in roles stay
fixed; the administrator role is never given through a group and the last administrator is
kept; only user managers change any of it; every change is audited. Also the ensure-admin
command for the first administrator (temporary password, changed at first sign-in)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.enums import Role
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


def audited(action: str) -> int:
    from app.db.session import session_factory
    from app.models import AuditEvent

    with session_factory()() as s:
        return len(list(s.scalars(select(AuditEvent.id).where(AuditEvent.action == action))))


def test_a_custom_role_gives_its_permissions_and_built_in_roles_stay_fixed(
    make_user, login
) -> None:  # noqa: ANN001
    admin = login(make_user(Role.ADMINISTRATOR))
    person = make_user()
    viewer = login(person)
    code = f"reviewer_{uuid.uuid4().hex[:6]}"
    assert viewer.get(f"{API}/admin/audit-events").status_code == 403

    r = admin.post(f"{API}/admin/roles", json={"code": code, "description": "Reads the audit log",
                                               "permissions": ["audit.read"]})  # fmt: skip
    assert r.status_code == 201
    role = next(x for x in r.json() if x["code"] == code)
    assert role["permissions"] == ["audit.read"] and role["builtin"] is False
    assert (
        admin.post(f"{API}/admin/users/{person.id}/roles", json={"role": code}).status_code == 200
    )
    assert viewer.get(f"{API}/admin/audit-events").status_code == 200, "enforced on the server"

    # Built-in roles cannot be edited or removed; bad input is explained.
    assert admin.put(f"{API}/admin/roles/viewer", json={"permissions": []}).status_code == 409
    assert admin.delete(f"{API}/admin/roles/administrator").status_code == 409
    bad = admin.post(f"{API}/admin/roles", json={"code": "Bad Code", "description": "x"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_role_code"
    unknown = admin.post(f"{API}/admin/roles", json={"code": f"x_{uuid.uuid4().hex[:6]}",
                                                     "description": "x", "permissions": ["no.such"]})  # fmt: skip
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unknown_permission"

    # Removing the role (and with it its assignments) takes the permission away at once.
    assert admin.delete(f"{API}/admin/roles/{code}").status_code == 200
    assert viewer.get(f"{API}/admin/audit-events").status_code == 403
    assert audited("role.create") >= 1 and audited("role.delete") >= 1


def test_a_group_gives_its_members_roles_and_permissions(make_user, login) -> None:  # noqa: ANN001
    admin = login(make_user(Role.ADMINISTRATOR))
    person = make_user()
    member = login(person)
    name = f"Auditors {uuid.uuid4().hex[:6]}"
    created = admin.post(f"{API}/admin/groups", json={"name": name, "roles": ["analyst"],
                                                      "permissions": ["audit.read"]})  # fmt: skip
    assert created.status_code == 201
    group_id = created.json()["id"]
    again = admin.post(f"{API}/admin/groups", json={"name": name.upper()})
    assert again.status_code == 409, "group names are unique whatever their case"

    added = admin.post(f"{API}/admin/groups/{group_id}/members", json={"user_id": str(person.id)})
    assert added.status_code == 200 and [m["id"] for m in added.json()["members"]] == [
        str(person.id)
    ]
    me = member.get(f"{API}/auth/me").json()
    assert "analyst" in me["roles"] and "audit.read" in me["permissions"]
    assert "analysis.run" in me["permissions"], "the analyst role's own permissions come too"
    assert member.get(f"{API}/admin/audit-events").status_code == 200

    removed = admin.delete(f"{API}/admin/groups/{group_id}/members/{person.id}")
    assert removed.status_code == 200 and removed.json()["members"] == []
    assert member.get(f"{API}/admin/audit-events").status_code == 403, "gone on the next request"
    assert admin.delete(f"{API}/admin/groups/{group_id}").status_code == 204
    assert audited("group.member.add") >= 1 and audited("group.delete") >= 1


def test_the_administrator_role_is_never_given_through_a_group(make_user, login) -> None:  # noqa: ANN001
    admin = login(make_user(Role.ADMINISTRATOR))
    r = admin.post(f"{API}/admin/groups", json={"name": f"G {uuid.uuid4().hex[:6]}",
                                                "roles": ["administrator"]})  # fmt: skip
    assert r.status_code == 409 and r.json()["error"]["code"] == "administrator_by_group"


def test_only_user_managers_change_roles_and_groups(make_user, login) -> None:  # noqa: ANN001
    analyst = login(make_user(Role.ANALYST))
    assert analyst.get(f"{API}/admin/roles").status_code == 403
    assert analyst.post(f"{API}/admin/groups", json={"name": "Mine"}).status_code == 403
    assert (
        analyst.post(
            f"{API}/admin/roles", json={"code": "mine_role", "description": "x"}
        ).status_code
        == 403
    )


def test_administrators_cannot_remove_their_own_role(make_user, login) -> None:  # noqa: ANN001
    person = make_user(Role.ADMINISTRATOR)
    admin = login(person)
    r = admin.delete(f"{API}/admin/users/{person.id}/roles/administrator")
    assert r.status_code == 409 and r.json()["error"]["code"] == "own_administrator_role"


def test_ensure_admin_creates_a_temporary_administrator(app, monkeypatch) -> None:  # noqa: ANN001
    from app import cli

    username = f"Azzan{uuid.uuid4().hex[:6]}"
    temporary = f"temp-{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("OSRIP_NEW_USER_PASSWORD", temporary)
    cli.main(["ensure-admin", "--username", username])
    client = TestClient(app)
    signed = client.post(f"{API}/auth/login", json={"email": username, "password": temporary})
    assert signed.status_code == 200
    me = signed.json()
    assert "administrator" in me["roles"] and me["password_change_required"] is True
    assert me["permissions"] == [], "nothing works until the temporary password is replaced"

    # Run again: the existing account is left alone unless --promote is given.
    cli.main(["ensure-admin", "--username", username])
    monkeypatch.setenv("OSRIP_NEW_USER_PASSWORD", "short")
    with pytest.raises(SystemExit):
        cli.main(["ensure-admin", "--username", f"Other{uuid.uuid4().hex[:6]}"])


def test_choosing_the_administrators_name_never_makes_anyone_an_administrator(
    app, monkeypatch
) -> None:  # noqa: ANN001
    from app import cli

    client = TestClient(app)
    password = f"pw-{uuid.uuid4().hex}"
    form = {"password": password, "password_confirm": password}
    # The owner's administrator name is not offered to the public, in any case.
    for name in ("Azzan", "azzan", "AZZAN"):
        r = client.post(f"{API}/auth/register/username", json={"username": name, **form})
        assert r.status_code == 422 and r.json()["error"]["code"] == "username_reserved", r.text
    # An account its holder created is never promoted, even with --promote.
    squatter = f"Azzan{uuid.uuid4().hex[:6]}"
    r = client.post(f"{API}/auth/register/username", json={"username": squatter, **form})
    assert r.status_code in (200, 201), r.text
    with pytest.raises(SystemExit, match="never made an administrator"):
        cli.main(["ensure-admin", "--username", squatter, "--promote"])
    signed = TestClient(app).post(
        f"{API}/auth/login", json={"email": squatter, "password": password}
    )
    assert signed.status_code == 200 and "administrator" not in signed.json()["roles"]
