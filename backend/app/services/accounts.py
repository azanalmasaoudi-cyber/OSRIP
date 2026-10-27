"""Accounts, roles, permission grants and server-side sessions (booklet 3.9, 3.15).

Authorization is always derived from the database at request time: a session
only identifies the user. Suspending an account, removing a role or revoking a
grant therefore takes effect on the very next request of an existing session.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import ApiError, conflict, not_found, unprocessable
from app.domain.enums import AccountStatus, Permission, Role
from app.models import (
    AppUser,
    LoginAttempt,
    PermissionRow,
    RolePermission,
    UserPermissionGrant,
    UserRole,
    UserSession,
)
from app.services import audit, phone_numbers
from app.services.principal import Principal


def now() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


# ------------------------------------------------------------------ permissions


def load_principal(
    session: Session, user: AppUser, user_session: UserSession | None = None
) -> Principal:
    roles = frozenset(
        session.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id))
    )
    from_roles = session.scalars(
        select(RolePermission.permission_code)
        .join(UserRole, UserRole.role_code == RolePermission.role_code)
        .where(UserRole.user_id == user.id)
    )
    grants = session.scalars(
        select(UserPermissionGrant.permission_code).where(UserPermissionGrant.user_id == user.id)
    )
    change_required = bool(user.password_change_required)
    return Principal(
        user_id=user.id,
        label=user.email
        or phone_numbers.mask(user.phone_e164)
        or (f"username:{user.username}" if user.username else f"user:{user.id}"),
        display_name=user.display_name,
        roles=roles,
        # Nothing is permitted until a temporary password has been replaced.
        permissions=frozenset() if change_required else frozenset([*from_roles, *grants]),
        session_id=user_session.id if user_session else None,
        csrf_token_hash=user_session.csrf_token_hash if user_session else None,
        password_change_required=change_required,
    )


# ------------------------------------------------------------------ administration


def create_user(
    session: Session,
    actor: Principal,
    *,
    email: str,
    display_name: str,
    password: str | None,
    roles: list[Role] | None = None,
    service_account: bool = False,
    email_verified: bool = True,
    created_via: str = "administrator",
) -> AppUser:
    """Accounts created by an administrator or operator count as verified; self-service
    registration passes `email_verified=False` and must prove the address first."""
    email = normalize_email(email)
    if service_account or (password is None and created_via in ("google", "microsoft")):
        password_hash = security.UNUSABLE_PASSWORD
    else:
        if password is None:
            raise unprocessable(
                "password_required", "A password is required for a personal account."
            )
        try:
            password_hash = security.hash_password(password)
        except ValueError as exc:
            raise unprocessable("weak_password", str(exc)) from exc
    user = AppUser(
        email=email,
        display_name=display_name.strip(),
        password_hash=password_hash,
        is_service_account=service_account,
        email_verified_at=now() if email_verified and not service_account else None,
        created_via=created_via,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict(
            "email_taken", "An account with this e-mail address already exists."
        ) from exc
    for role in roles or []:
        session.add(UserRole(user_id=user.id, role_code=role.value, granted_by=actor.user_id))
    audit.record(
        session,
        actor,
        "user.create",
        entity_type="user",
        entity_id=user.id,
        metadata={"email": email, "roles": [r.value for r in roles or []]},
    )
    session.flush()  # sessions do not autoflush; make the new rows visible to later reads
    return user


def get_user(session: Session, user_id: uuid.UUID) -> AppUser:
    user = session.get(AppUser, user_id)
    if user is None:
        raise not_found("user")
    return user


def assign_role(session: Session, actor: Principal, user_id: uuid.UUID, role: Role) -> None:
    get_user(session, user_id)
    if session.get(UserRole, (user_id, role.value)) is None:
        session.add(UserRole(user_id=user_id, role_code=role.value, granted_by=actor.user_id))
    audit.record(
        session,
        actor,
        "user.role.assign",
        entity_type="user",
        entity_id=user_id,
        metadata={"role": role.value},
    )
    session.flush()


def remove_role(session: Session, actor: Principal, user_id: uuid.UUID, role: Role) -> None:
    session.execute(
        delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_code == role.value)
    )
    audit.record(
        session,
        actor,
        "user.role.remove",
        entity_type="user",
        entity_id=user_id,
        metadata={"role": role.value},
    )


def grant_permission(
    session: Session, actor: Principal, user_id: uuid.UUID, permission: Permission
) -> None:
    get_user(session, user_id)
    if session.get(PermissionRow, permission.value) is None:
        raise not_found("permission")
    if session.get(UserPermissionGrant, (user_id, permission.value)) is None:
        session.add(
            UserPermissionGrant(
                user_id=user_id, permission_code=permission.value, granted_by=actor.user_id
            )
        )
    audit.record(
        session,
        actor,
        "user.grant",
        entity_type="user",
        entity_id=user_id,
        metadata={"permission": permission.value},
    )
    session.flush()


def revoke_permission(
    session: Session, actor: Principal, user_id: uuid.UUID, permission: Permission
) -> None:
    session.execute(
        delete(UserPermissionGrant).where(
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.permission_code == permission.value,
        )
    )
    audit.record(
        session,
        actor,
        "user.revoke",
        entity_type="user",
        entity_id=user_id,
        metadata={"permission": permission.value},
    )


def set_status(
    session: Session, actor: Principal, user_id: uuid.UUID, status: AccountStatus
) -> None:
    if user_id == actor.user_id and status is AccountStatus.SUSPENDED:
        raise unprocessable(
            "cannot_suspend_self", "Administrators cannot suspend their own account."
        )
    user = get_user(session, user_id)
    user.status = status
    if status is AccountStatus.SUSPENDED:
        revoke_all_sessions(session, user_id)
    audit.record(
        session,
        actor,
        f"user.{'suspend' if status is AccountStatus.SUSPENDED else 'reactivate'}",
        entity_type="user",
        entity_id=user_id,
    )


# ------------------------------------------------------------------ sign-in


@dataclass(frozen=True, slots=True)
class NewSession:
    token: str  # goes in the HttpOnly cookie; never stored
    csrf_token: str  # goes in the readable CSRF cookie; never stored
    expires_at: datetime
    principal: Principal


def _throttled(session: Session, email: str, client_hash: str) -> bool:
    settings = get_settings()
    since = now() - timedelta(minutes=settings.login_window_minutes)
    failures_for_email = (
        session.scalar(
            select(func.count()).where(
                LoginAttempt.email == email,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.attempted_at >= since,
            )
        )
        or 0
    )
    failures_for_client = (
        session.scalar(
            select(func.count()).where(
                LoginAttempt.client_hash == client_hash,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.attempted_at >= since,
            )
        )
        or 0
    )
    return (
        failures_for_email >= settings.login_max_failures
        or failures_for_client >= settings.login_max_failures * 4
    )


def find_by_username(session: Session, username: str) -> AppUser | None:
    return session.scalar(
        select(AppUser).where(func.lower(AppUser.username) == username.strip().lower())
    )


def _find_for_login(session: Session, identifier: str) -> AppUser | None:
    """An e-mail address (contains '@') or a username (case-insensitive)."""
    if "@" in identifier:
        return session.scalar(select(AppUser).where(AppUser.email == identifier))
    return find_by_username(session, identifier)


def login(session: Session, email: str, password: str, client_address: str) -> NewSession:
    """Verify credentials and open a new session. Commits its own attempt record.
    ``email`` is the sign-in identifier: an e-mail address or a username."""
    settings = get_settings()
    email = normalize_email(email)
    client_hash = security.keyed_digest(settings.client_hash_key.get_secret_value(), client_address)

    unverified = False
    with session.begin():
        if _throttled(session, email, client_hash):
            audit.record(
                session,
                Principal(None, email),
                "auth.login",
                "denied",
                metadata={"reason": "throttled"},
            )
            raise ApiError(
                429,
                "too_many_attempts",
                "Too many failed sign-in attempts. Wait a few minutes and try again.",
            )

        user = _find_for_login(session, email)
        ok = (
            user is not None
            and user.status is AccountStatus.ACTIVE
            and not user.is_service_account
            and security.verify_password(user.password_hash, password)
        )
        if user is None:
            security.verify_password(None, password)  # equal work for unknown accounts
        session.add(LoginAttempt(email=email, client_hash=client_hash, succeeded=ok))
        if not ok or user is None:
            audit.record(
                session,
                Principal(None, email),
                "auth.login",
                "denied",
                metadata={"reason": "invalid_credentials"},
            )
            # Committed deliberately (failed attempts count towards throttling).
        else:
            if user.email is not None and user.email_verified_at is None and "@" in email:
                # The password is right, so this reveals nothing to a stranger.
                unverified = True
            else:
                if security.needs_rehash(user.password_hash):
                    user.password_hash = security.hash_password(password)
                return open_session(session, user, method="password")
    if unverified:
        raise ApiError(
            403,
            "email_not_verified",
            "Confirm your e-mail address first. Use the link we sent, or ask for a new one.",
        )

    # Same message for unknown account, wrong password and suspended account.
    raise ApiError(
        401, "invalid_credentials", "The username, e-mail address or password is not correct."
    )


# ------------------------------------------------------------------ usernames and password changes


@dataclass(frozen=True, slots=True)
class EnsureResult:
    user: AppUser
    created: bool


def ensure_username_account(
    session: Session,
    actor: Principal,
    *,
    username: str,
    display_name: str,
    password: str,
) -> EnsureResult:
    """Create a standard (viewer) account identified only by a username, with a
    temporary password that must be changed at first sign-in. Idempotent: an existing
    account with that username is returned unchanged; its password, roles and grants
    are never reset or modified here. No e-mail address or phone number is invented."""
    username = username.strip()
    existing = find_by_username(session, username)
    if existing is not None:
        return EnsureResult(existing, created=False)
    try:
        password_hash = security.hash_password(password, temporary=True)
    except ValueError as exc:
        raise unprocessable("weak_password", str(exc)) from exc
    user = AppUser(
        username=username,
        email=None,
        display_name=display_name.strip() or username,
        password_hash=password_hash,
        created_via="cli",
        password_change_required=True,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict(
            "username_invalid_or_taken",
            "That username is already used or is not valid (3-32 letters, digits, '.', '_' "
            "or '-', starting with a letter).",
        ) from exc
    session.add(UserRole(user_id=user.id, role_code=Role.VIEWER.value, granted_by=actor.user_id))
    audit.record(
        session,
        actor,
        "user.create",
        entity_type="user",
        entity_id=user.id,
        metadata={"username": username, "roles": [Role.VIEWER.value], "temporary_password": True},
    )
    session.flush()
    return EnsureResult(user, created=True)


def change_password(
    session: Session, principal: Principal, current_password: str, new_password: str
) -> None:
    """The signed-in user replaces their password (and clears a required change). Every
    other session of the account is revoked; the current one stays signed in."""
    with session.begin():
        user = get_user(session, principal.user_id)  # type: ignore[arg-type]
        if not security.verify_password(user.password_hash, current_password):
            audit.record(
                session,
                principal,
                "auth.password.change",
                "denied",
                metadata={"reason": "wrong_current_password"},
            )
            raise ApiError(403, "wrong_current_password", "The current password is not correct.")
        if security.verify_password(user.password_hash, new_password):
            raise unprocessable(
                "password_unchanged", "Choose a new password that differs from the current one."
            )
        try:
            user.password_hash = security.hash_password(new_password)
        except ValueError as exc:
            raise unprocessable("weak_password", str(exc)) from exc
        user.password_changed_at = now()
        user.password_change_required = False
        session.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.id != principal.session_id,
            )
            .values(revoked_at=now())
        )
        audit.record(
            session, principal, "auth.password.change", entity_type="user", entity_id=user.id
        )


def open_session(session: Session, user: AppUser, *, method: str) -> NewSession:
    """Create a server-side session inside the caller's transaction."""
    settings = get_settings()
    token, csrf_token = security.new_token(), security.new_token()
    expires_at = now() + timedelta(hours=settings.session_absolute_hours)
    user_session = UserSession(
        user_id=user.id,
        token_hash=security.token_digest(token),
        csrf_token_hash=security.token_digest(csrf_token),
        expires_at=expires_at,
    )
    session.add(user_session)
    session.flush()
    principal = load_principal(session, user, user_session)
    audit.record(
        session,
        principal,
        "auth.login",
        entity_type="session",
        entity_id=user_session.id,
        metadata={"method": method},
    )
    return NewSession(token, csrf_token, expires_at, principal)


def resolve_session(session: Session, token: str | None) -> Principal | None:
    """Return the principal for a live session, or None. Re-checks the account every time."""
    if not token:
        return None
    settings = get_settings()
    current = now()
    with session.begin():
        row = session.execute(
            select(UserSession, AppUser)
            .join(AppUser, AppUser.id == UserSession.user_id)
            .where(UserSession.token_hash == security.token_digest(token))
        ).first()
        if row is None:
            return None
        user_session, user = row
        idle_limit = user_session.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
        if (
            user_session.revoked_at is not None
            or user_session.expires_at <= current
            or idle_limit <= current
            or user.status is not AccountStatus.ACTIVE
        ):
            if user_session.revoked_at is None:
                user_session.revoked_at = current
            return None
        if current - user_session.last_seen_at > timedelta(seconds=60):
            user_session.last_seen_at = current
        return load_principal(session, user, user_session)


def logout(session: Session, principal: Principal) -> None:
    with session.begin():
        if principal.session_id is not None:
            session.execute(
                update(UserSession)
                .where(UserSession.id == principal.session_id)
                .values(revoked_at=now())
            )
        audit.record(
            session, principal, "auth.logout", entity_type="session", entity_id=principal.session_id
        )


def revoke_all_sessions(session: Session, user_id: uuid.UUID) -> None:
    session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )


def has_password(user: AppUser) -> bool:
    return user.password_hash != security.UNUSABLE_PASSWORD


def confirm_identity(
    session: Session, principal: Principal, user: AppUser, password: str | None, *, action: str
) -> None:
    """Step-up check before changing a confirmed e-mail address or phone number: the current
    password, or, for an account that has none (phone, Google or Microsoft sign-in), a session
    opened within ``reauth_minutes``. A refusal is audited in its own transaction."""
    if has_password(user):
        if password and security.verify_password(user.password_hash, password):
            return
        audit.record_separately(
            principal, f"auth.{action}", "denied", metadata={"reason": "wrong_current_password"}
        )
        raise ApiError(403, "wrong_current_password", "The current password is not correct.")
    minutes = get_settings().reauth_minutes
    opened = (
        session.scalar(select(UserSession.created_at).where(UserSession.id == principal.session_id))
        if principal.session_id
        else None
    )
    if opened is None or now() - opened > timedelta(minutes=minutes):
        audit.record_separately(
            principal, f"auth.{action}", "denied", metadata={"reason": "reauthentication_required"}
        )
        raise ApiError(
            403,
            "reauthentication_required",
            f"For your security, sign in again and make this change within {minutes} minutes.",
            {"minutes": minutes},
        )
