import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.domain.enums import AccountStatus, Permission, Role
from app.models import AppUser, AuditEvent, UserPermissionGrant, UserRole
from app.schemas.accounts import GrantIn, RoleIn, UserCreateIn, UserOut
from app.services import accounts, phone_numbers
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
            email=body.email,
            display_name=body.display_name,
            password=body.password,
            roles=body.roles,
        )
        return _user_out(session, user)


@router.post("/users/{user_id}/roles", response_model=UserOut)
def assign_role(user_id: uuid.UUID, body: RoleIn, session: DbSession, actor: Manager) -> UserOut:
    with session.begin():
        accounts.assign_role(session, actor, user_id, body.role)
        return _user_out(session, accounts.get_user(session, user_id))


@router.delete("/users/{user_id}/roles/{role}", response_model=UserOut)
def remove_role(user_id: uuid.UUID, role: Role, session: DbSession, actor: Manager) -> UserOut:
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
