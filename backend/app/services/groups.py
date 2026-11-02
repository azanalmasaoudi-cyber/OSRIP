"""Custom roles and user groups (migration 0026), for administrators (``user.manage``).

* Built-in roles (viewer, analyst, data manager, administrator) keep the permissions the
  migrations give them; custom roles carry any set of existing permissions.
* A group gives its members roles and permissions. A user's permissions are those of their
  own roles, their groups' roles, their groups' permissions and their explicit grants
  (``accounts.load_principal``), so every check stays on the server.
* The administrator role is never given through a group: it is assigned to a person, one at
  a time, so it cannot spread by group membership.
* Every change is audited.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, conflict, not_found, unprocessable
from app.domain.enums import Role
from app.models import (
    AppUser,
    GroupMember,
    GroupPermission,
    GroupRole,
    PermissionRow,
    RolePermission,
    RoleRow,
    UserGroup,
    UserRole,
)
from app.services import audit
from app.services.principal import Principal

ROLE_CODE = re.compile(r"[a-z][a-z0-9_]{2,39}")


# ------------------------------------------------------------------ catalog


def permissions(session: Session) -> list[dict[str, str]]:
    rows = session.execute(
        select(PermissionRow.code, PermissionRow.description).order_by(PermissionRow.code)
    )
    return [{"code": code, "description": description} for code, description in rows]


def roles(session: Session) -> list[dict[str, Any]]:
    perms: dict[str, list[str]] = {}
    for role_code, permission_code in session.execute(
        select(RolePermission.role_code, RolePermission.permission_code)
    ):
        perms.setdefault(role_code, []).append(permission_code)
    users = dict(
        session.execute(select(UserRole.role_code, func.count()).group_by(UserRole.role_code)).all()
    )
    groups_using = dict(
        session.execute(
            select(GroupRole.role_code, func.count()).group_by(GroupRole.role_code)
        ).all()
    )
    out = []
    for row in session.scalars(select(RoleRow).order_by(RoleRow.builtin.desc(), RoleRow.code)):
        out.append(
            {
                "code": row.code,
                "description": row.description,
                "builtin": row.builtin,
                "permissions": sorted(perms.get(row.code, [])),
                "users": users.get(row.code, 0),
                "groups": groups_using.get(row.code, 0),
            }
        )
    return out


def _known_permissions(session: Session, codes: list[str]) -> list[str]:
    wanted = sorted(set(codes))
    known = set(session.scalars(select(PermissionRow.code).where(PermissionRow.code.in_(wanted))))
    unknown = [c for c in wanted if c not in known]
    if unknown:
        raise unprocessable("unknown_permission", "Unknown permission.", {"permissions": unknown})
    return wanted


def _custom_role(session: Session, code: str) -> RoleRow:
    row = session.get(RoleRow, code)
    if row is None:
        raise not_found("role")
    if row.builtin:
        raise ApiError(409, "builtin_role", "Built-in roles cannot be changed or removed.")
    return row


# ------------------------------------------------------------------ custom roles


def create_role(
    session: Session, actor: Principal, *, code: str, description: str, permission_codes: list[str]
) -> None:
    code = code.strip().lower()
    if not ROLE_CODE.fullmatch(code):
        raise unprocessable(
            "invalid_role_code",
            "Use 3 to 40 lower-case letters, digits or underscores, starting with a letter.",
        )
    description = description.strip()
    if not 1 <= len(description) <= 300:
        raise unprocessable("invalid_description", "Describe the role in 1 to 300 characters.")
    wanted = _known_permissions(session, permission_codes)
    if session.get(RoleRow, code) is not None:
        raise conflict("role_exists", "A role with this code already exists.")
    session.add(
        RoleRow(code=code, description=description, builtin=False, created_by=actor.user_id)
    )
    session.flush()
    session.add_all(RolePermission(role_code=code, permission_code=p) for p in wanted)
    audit.record(session, actor, "role.create", entity_type="role", entity_id=code,
                 metadata={"permissions": wanted})  # fmt: skip
    session.flush()


def update_role(
    session: Session,
    actor: Principal,
    code: str,
    *,
    description: str | None,
    permission_codes: list[str],
) -> None:
    row = _custom_role(session, code)
    if description is not None:
        description = description.strip()
        if not 1 <= len(description) <= 300:
            raise unprocessable("invalid_description", "Describe the role in 1 to 300 characters.")
        row.description = description
    wanted = _known_permissions(session, permission_codes)
    session.execute(delete(RolePermission).where(RolePermission.role_code == code))
    session.add_all(RolePermission(role_code=code, permission_code=p) for p in wanted)
    audit.record(session, actor, "role.update", entity_type="role", entity_id=code,
                 metadata={"permissions": wanted})  # fmt: skip
    session.flush()


def delete_role(session: Session, actor: Principal, code: str) -> None:
    """A custom role is removed with its assignments (to people and to groups)."""
    _custom_role(session, code)
    removed_users = session.execute(delete(UserRole).where(UserRole.role_code == code)).rowcount
    session.execute(delete(GroupRole).where(GroupRole.role_code == code))
    session.execute(delete(RolePermission).where(RolePermission.role_code == code))
    session.execute(delete(RoleRow).where(RoleRow.code == code))
    audit.record(session, actor, "role.delete", entity_type="role", entity_id=code,
                 metadata={"assignments_removed": removed_users})  # fmt: skip


# ------------------------------------------------------------------ groups


def _group(session: Session, group_id: uuid.UUID) -> UserGroup:
    group = session.get(UserGroup, group_id)
    if group is None:
        raise not_found("group")
    return group


def group_out(session: Session, group: UserGroup) -> dict[str, Any]:
    members = session.execute(
        select(AppUser.id, AppUser.display_name, AppUser.username, AppUser.email)
        .join(GroupMember, GroupMember.user_id == AppUser.id)
        .where(GroupMember.group_id == group.id)
        .order_by(AppUser.display_name)
    ).all()
    return {
        "id": str(group.id),
        "name": group.name,
        "description": group.description,
        "roles": sorted(
            session.scalars(select(GroupRole.role_code).where(GroupRole.group_id == group.id))
        ),
        "permissions": sorted(
            session.scalars(
                select(GroupPermission.permission_code).where(GroupPermission.group_id == group.id)
            )
        ),
        "members": [
            {
                "id": str(m.id),
                "display_name": m.display_name,
                "username": m.username,
                "email": m.email,
            }
            for m in members
        ],
    }


def groups(session: Session) -> list[dict[str, Any]]:
    return [
        group_out(session, g) for g in session.scalars(select(UserGroup).order_by(UserGroup.name))
    ]


def _check_group_fields(name: str, description: str) -> tuple[str, str]:
    name, description = name.strip(), description.strip()
    if not 1 <= len(name) <= 80:
        raise unprocessable("invalid_name", "Name the group in 1 to 80 characters.")
    if len(description) > 500:
        raise unprocessable("invalid_description", "Describe the group in at most 500 characters.")
    return name, description


def _set_access(
    session: Session, group: UserGroup, role_codes: list[str], permission_codes: list[str]
) -> None:
    wanted_roles = sorted(set(role_codes))
    if Role.ADMINISTRATOR.value in wanted_roles:
        raise ApiError(
            409,
            "administrator_by_group",
            "The administrator role is given to a person directly, never through a group.",
        )
    known = set(session.scalars(select(RoleRow.code).where(RoleRow.code.in_(wanted_roles))))
    unknown = [r for r in wanted_roles if r not in known]
    if unknown:
        raise unprocessable("unknown_role", "Unknown role.", {"roles": unknown})
    wanted_perms = _known_permissions(session, permission_codes)
    session.execute(delete(GroupRole).where(GroupRole.group_id == group.id))
    session.execute(delete(GroupPermission).where(GroupPermission.group_id == group.id))
    session.add_all(GroupRole(group_id=group.id, role_code=r) for r in wanted_roles)
    session.add_all(GroupPermission(group_id=group.id, permission_code=p) for p in wanted_perms)


def create_group(
    session: Session, actor: Principal, *, name: str, description: str,
    role_codes: list[str], permission_codes: list[str],
) -> UserGroup:  # fmt: skip
    name, description = _check_group_fields(name, description)
    group = UserGroup(name=name, description=description, created_by=actor.user_id)
    session.add(group)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise conflict("group_exists", "A group with this name already exists.") from exc
    _set_access(session, group, role_codes, permission_codes)
    audit.record(session, actor, "group.create", entity_type="group", entity_id=group.id,
                 metadata={"name": name, "roles": sorted(set(role_codes)),
                           "permissions": sorted(set(permission_codes))})  # fmt: skip
    session.flush()
    return group


def update_group(
    session: Session, actor: Principal, group_id: uuid.UUID, *, name: str, description: str,
    role_codes: list[str], permission_codes: list[str],
) -> UserGroup:  # fmt: skip
    group = _group(session, group_id)
    group.name, group.description = _check_group_fields(name, description)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise conflict("group_exists", "A group with this name already exists.") from exc
    _set_access(session, group, role_codes, permission_codes)
    audit.record(session, actor, "group.update", entity_type="group", entity_id=group.id,
                 metadata={"name": group.name, "roles": sorted(set(role_codes)),
                           "permissions": sorted(set(permission_codes))})  # fmt: skip
    session.flush()
    return group


def delete_group(session: Session, actor: Principal, group_id: uuid.UUID) -> None:
    group = _group(session, group_id)
    name = group.name
    session.delete(group)
    audit.record(session, actor, "group.delete", entity_type="group", entity_id=group_id,
                 metadata={"name": name})  # fmt: skip


def add_member(session: Session, actor: Principal, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
    _group(session, group_id)
    user = session.get(AppUser, user_id)
    if user is None:
        raise not_found("user")
    if user.is_service_account:
        raise unprocessable("service_account", "Service accounts are not group members.")
    if session.get(GroupMember, (group_id, user_id)) is None:
        session.add(GroupMember(group_id=group_id, user_id=user_id, added_by=actor.user_id))
    audit.record(session, actor, "group.member.add", entity_type="group", entity_id=group_id,
                 metadata={"user_id": str(user_id)})  # fmt: skip
    session.flush()


def remove_member(
    session: Session, actor: Principal, group_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    _group(session, group_id)
    session.execute(
        delete(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
    )
    audit.record(session, actor, "group.member.remove", entity_type="group", entity_id=group_id,
                 metadata={"user_id": str(user_id)})  # fmt: skip
