import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.domain.enums import AccountStatus, Permission
from app.models import AppUser, AuditEvent, UserGroup, UserPermissionGrant, UserRole
from app.schemas.accounts import GrantIn, RoleIn, UserCreateIn, UsernameIn, UserOut
from app.services import accounts, groups, phone_numbers
from app.services.principal import Principal

router = APIRouter(prefix="/admin", tags=["administration"])
Manager = Annotated[Principal, Depends(require(Permission.USER_MANAGE))]


def _user_out(session: DbSession, user: AppUser) -> UserOut:
    roles = sorted(session.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id)))
    grants = sorted(
        session.scalars(
            select(UserPermissionGrant.permission_code).where(
                UserPermissionGrant.user_id == user.id
            )
        )
    )
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        roles=roles,
        grants=grants,
        email_verified=user.email_verified_at is not None,
        created_via=user.created_via,
        phone=phone_numbers.mask(user.phone_e164),
        username=user.username,
        service_account=user.is_service_account,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(session: DbSession, _: Manager) -> list[UserOut]:
    with session.begin():
        return [
            _user_out(session, u)
            for u in session.scalars(
                select(AppUser)
                .where(AppUser.is_service_account.is_(False))
                .order_by(AppUser.email.nulls_last(), AppUser.created_at)
            )
        ]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreateIn, session: DbSession, actor: Manager) -> UserOut:
    with session.begin():
        user = accounts.create_user(
            session,
            actor,
            username=body.username,
            display_name=body.display_name,
            password=body.password,
            roles=body.roles,
        )
        return _user_out(session, user)


@router.post("/users/{user_id}/username", response_model=UserOut)
def set_username(
    user_id: uuid.UUID, body: UsernameIn, session: DbSession, actor: Manager
) -> UserOut:
    """Gives an account a username to sign in with (accounts that used an e-mail address or
    a phone number before those were retired have none), or changes it. Audited."""
    with session.begin():
        user = accounts.set_username(session, actor, user_id, body.username)
        return _user_out(session, user)


@router.post("/users/{user_id}/roles", response_model=UserOut)
def assign_role(user_id: uuid.UUID, body: RoleIn, session: DbSession, actor: Manager) -> UserOut:
    with session.begin():
        accounts.assign_role(session, actor, user_id, body.role)
        return _user_out(session, accounts.get_user(session, user_id))


@router.delete("/users/{user_id}/roles/{role}", response_model=UserOut)
def remove_role(user_id: uuid.UUID, role: str, session: DbSession, actor: Manager) -> UserOut:
    with session.begin():
        accounts.remove_role(session, actor, user_id, role)
        return _user_out(session, accounts.get_user(session, user_id))


@router.post("/users/{user_id}/grants", response_model=UserOut)
def grant(user_id: uuid.UUID, body: GrantIn, session: DbSession, actor: Manager) -> UserOut:
    with session.begin():
        accounts.grant_permission(session, actor, user_id, body.permission)
        return _user_out(session, accounts.get_user(session, user_id))


@router.delete("/users/{user_id}/grants/{permission}", response_model=UserOut)
def revoke(
    user_id: uuid.UUID, permission: Permission, session: DbSession, actor: Manager
) -> UserOut:
    with session.begin():
        accounts.revoke_permission(session, actor, user_id, permission)
        return _user_out(session, accounts.get_user(session, user_id))


@router.post("/users/{user_id}/suspend", response_model=UserOut)
def suspend(user_id: uuid.UUID, session: DbSession, actor: Manager) -> UserOut:
    with session.begin():
        accounts.set_status(session, actor, user_id, AccountStatus.SUSPENDED)
        return _user_out(session, accounts.get_user(session, user_id))


@router.post("/users/{user_id}/reactivate", response_model=UserOut)
def reactivate(user_id: uuid.UUID, session: DbSession, actor: Manager) -> UserOut:
    with session.begin():
        accounts.set_status(session, actor, user_id, AccountStatus.ACTIVE)
        return _user_out(session, accounts.get_user(session, user_id))


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: uuid.UUID, response: Response, session: DbSession, actor: Manager
) -> dict[str, str]:
    """A temporary password for an account that cannot recover itself, returned once for the
    administrator to hand over in person; it must be changed at the next sign-in."""
    temporary = accounts.admin_reset_password(session, actor, user_id)
    response.headers["Cache-Control"] = "no-store"
    return {"temporary_password": temporary}


# ------------------------------------------------------------------ roles and groups


class RoleCreateIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=300)
    permissions: list[str] = Field(default_factory=list, max_length=100)


class RoleUpdateIn(BaseModel):
    description: str | None = Field(default=None, max_length=300)
    permissions: list[str] = Field(default_factory=list, max_length=100)


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    roles: list[str] = Field(default_factory=list, max_length=50)
    permissions: list[str] = Field(default_factory=list, max_length=100)


class MemberIn(BaseModel):
    user_id: uuid.UUID


@router.get("/permissions")
def list_permissions(session: DbSession, _: Manager) -> list[dict[str, str]]:
    with session.begin():
        return groups.permissions(session)


@router.get("/roles")
def list_roles(session: DbSession, _: Manager) -> list[dict[str, Any]]:
    with session.begin():
        return groups.roles(session)


@router.post("/roles", status_code=201)
def create_role(body: RoleCreateIn, session: DbSession, actor: Manager) -> list[dict[str, Any]]:
    with session.begin():
        groups.create_role(
            session, actor, code=body.code, description=body.description,
            permission_codes=body.permissions,
        )  # fmt: skip
        return groups.roles(session)


@router.put("/roles/{code}")
def update_role(
    code: str, body: RoleUpdateIn, session: DbSession, actor: Manager
) -> list[dict[str, Any]]:
    with session.begin():
        groups.update_role(
            session, actor, code, description=body.description, permission_codes=body.permissions
        )
        return groups.roles(session)


@router.delete("/roles/{code}")
def delete_role(code: str, session: DbSession, actor: Manager) -> list[dict[str, Any]]:
    with session.begin():
        groups.delete_role(session, actor, code)
        return groups.roles(session)


@router.get("/groups")
def list_groups(session: DbSession, _: Manager) -> list[dict[str, Any]]:
    with session.begin():
        return groups.groups(session)


@router.post("/groups", status_code=201)
def create_group(body: GroupIn, session: DbSession, actor: Manager) -> dict[str, Any]:
    with session.begin():
        group = groups.create_group(
            session, actor, name=body.name, description=body.description,
            role_codes=body.roles, permission_codes=body.permissions,
        )  # fmt: skip
        return groups.group_out(session, group)


@router.put("/groups/{group_id}")
def update_group(
    group_id: uuid.UUID, body: GroupIn, session: DbSession, actor: Manager
) -> dict[str, Any]:
    with session.begin():
        group = groups.update_group(
            session, actor, group_id, name=body.name, description=body.description,
            role_codes=body.roles, permission_codes=body.permissions,
        )  # fmt: skip
        return groups.group_out(session, group)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: uuid.UUID, session: DbSession, actor: Manager) -> None:
    with session.begin():
        groups.delete_group(session, actor, group_id)


@router.post("/groups/{group_id}/members")
def add_member(
    group_id: uuid.UUID, body: MemberIn, session: DbSession, actor: Manager
) -> dict[str, Any]:
    with session.begin():
        groups.add_member(session, actor, group_id, body.user_id)
        return groups.group_out(session, session.get(UserGroup, group_id))


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_member(
    group_id: uuid.UUID, user_id: uuid.UUID, session: DbSession, actor: Manager
) -> dict[str, Any]:
    with session.begin():
        groups.remove_member(session, actor, group_id, user_id)
        return groups.group_out(session, session.get(UserGroup, group_id))


@router.get("/audit-events")
def audit_events(
    session: DbSession,
    _: Annotated[Principal, Depends(require(Permission.AUDIT_READ))],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, object]]:
    with session.begin():
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit))
        return [
            {
                "id": e.id,
                "occurred_at": e.occurred_at.isoformat(),
                "actor": e.actor_label,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "outcome": e.outcome,
                "metadata": e.metadata_,
            }
            for e in events
        ]
