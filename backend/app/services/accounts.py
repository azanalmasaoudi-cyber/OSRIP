"""Accounts, roles, permission grants and server-side sessions (booklet 3.9, 3.15).

Authorization is always derived from the database at request time: a session
only identifies the user. Suspending an account, removing a role or revoking a
grant therefore takes effect on the very next request of an existing session.
"""

from __future__ import annotations

import re
import secrets
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
    GroupMember,
    GroupPermission,
    GroupRole,
    LoginAttempt,
    PermissionRow,
    RolePermission,
    RoleRow,
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
    # Roles: the person's own and those their groups give (migration 0026).
    in_groups = select(GroupMember.group_id).where(GroupMember.user_id == user.id)
    roles = frozenset(
        [
            *session.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id)),
            *session.scalars(select(GroupRole.role_code).where(GroupRole.group_id.in_(in_groups))),
        ]
    )
    from_roles = session.scalars(
        select(RolePermission.permission_code).where(RolePermission.role_code.in_(roles))
    )
    from_groups = session.scalars(
        select(GroupPermission.permission_code).where(GroupPermission.group_id.in_(in_groups))
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
        permissions=frozenset()
        if change_required
        else frozenset([*from_roles, *from_groups, *grants]),
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


def assign_role(session: Session, actor: Principal, user_id: uuid.UUID, role: Role | str) -> None:
    """A built-in or custom role (by its code) for one person."""
    code = role.value if isinstance(role, Role) else str(role)
    get_user(session, user_id)
    if session.get(RoleRow, code) is None:
        raise not_found("role")
    if session.get(UserRole, (user_id, code)) is None:
        session.add(UserRole(user_id=user_id, role_code=code, granted_by=actor.user_id))
    audit.record(
        session,
        actor,
        "user.role.assign",
        entity_type="user",
        entity_id=user_id,
        metadata={"role": code},
    )
    session.flush()


def remove_role(session: Session, actor: Principal, user_id: uuid.UUID, role: Role | str) -> None:
    code = role.value if isinstance(role, Role) else str(role)
    if code == Role.ADMINISTRATOR.value and user_id == actor.user_id:
        raise ApiError(
            409, "own_administrator_role", "You cannot remove your own administrator role."
        )
    if code == Role.ADMINISTRATOR.value and _other_administrators(session, user_id) == 0:
        raise ApiError(409, "last_administrator", "OSRIP must keep at least one administrator.")
    session.execute(delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_code == code))
    audit.record(
        session,
        actor,
        "user.role.remove",
        entity_type="user",
        entity_id=user_id,
        metadata={"role": code},
    )


def _other_administrators(session: Session, user_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(AppUser, AppUser.id == UserRole.user_id)
            .where(
                UserRole.role_code == Role.ADMINISTRATOR.value,
                UserRole.user_id != user_id,
                AppUser.status == AccountStatus.ACTIVE,
            )
        )
        or 0
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
    persistent: bool = False  # remember me: the cookie outlives the browser session


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


def login(
    session: Session,
    email: str,
    password: str,
    client_address: str,
    *,
    remember: bool = False,
) -> NewSession:
    """Verify credentials and open a new session. Commits its own attempt record.
    ``email`` is the sign-in identifier: an e-mail address or a username. ``remember``
    keeps the session on this device (session_remember_days)."""
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
                return open_session(session, user, method="password", persistent=remember)
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


def open_session(
    session: Session, user: AppUser, *, method: str, persistent: bool = False
) -> NewSession:
    """Create a server-side session inside the caller's transaction. A persistent session
    (remember me) lasts session_remember_days; otherwise session_absolute_hours with the
    idle limit."""
    settings = get_settings()
    token, csrf_token = security.new_token(), security.new_token()
    lifetime = (
        timedelta(days=settings.session_remember_days)
        if persistent
        else timedelta(hours=settings.session_absolute_hours)
    )
    expires_at = now() + lifetime
    user_session = UserSession(
        user_id=user.id,
        token_hash=security.token_digest(token),
        csrf_token_hash=security.token_digest(csrf_token),
        expires_at=expires_at,
        persistent=persistent,
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
        metadata={"method": method, "remember": persistent},
    )
    return NewSession(token, csrf_token, expires_at, principal, persistent)


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
        idle = (
            timedelta(days=settings.session_remember_days)
            if user_session.persistent
            else timedelta(minutes=settings.session_idle_minutes)
        )
        idle_limit = user_session.last_seen_at + idle
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


# ------------------------------------------------------------------ registration by username

# The database enforces the same pattern (migration 0011) and case-insensitive uniqueness.
USERNAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,31}")
# Names that could pass for the platform or its staff are not offered to the public.
RESERVED_USERNAMES = frozenset(
    {"admin", "administrator", "root", "system", "support", "osrip", "security", "moderator",
     "owner", "staff", "help", "service", "official", "ncsi"}
)  # fmt: skip
# Recovery codes: 20 characters in 5 groups from an alphabet without look-alikes (0/O,
# 1/I/L, U/V), about 97 bits; only an Argon2id hash is stored.
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTWXYZ23456789"
SYSTEM_REGISTRATION = Principal(None, "system:registration")


@dataclass(frozen=True, slots=True)
class WithRecoveryCode:
    new_session: NewSession
    recovery_code: str  # shown once to its owner, never stored


def username_problem(username: str) -> ApiError | None:
    if not USERNAME_PATTERN.fullmatch(username):
        return unprocessable(
            "invalid_username",
            "Use 3 to 32 characters: English letters, digits, '.', '_' or '-', "
            "starting with a letter.",
        )
    if username.lower() in RESERVED_USERNAMES:
        return unprocessable("username_reserved", "This username is reserved. Choose another.")
    return None


def password_problem(password: str, confirm: str, username: str) -> ApiError | None:
    if password != confirm:
        return unprocessable("password_mismatch", "The two passwords do not match.")
    if len(password) < security.MIN_PASSWORD_LENGTH:
        return unprocessable(
            "weak_password",
            f"Password must be at least {security.MIN_PASSWORD_LENGTH} characters.",
        )
    if username and username.lower() in password.lower():
        return unprocessable(
            "password_contains_username", "The password must not contain the username."
        )
    if len(set(password)) < 5:
        return unprocessable(
            "password_too_simple", "The password is too simple: use more different characters."
        )
    return None


def new_recovery_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(20))
    return "-".join(raw[i : i + 4] for i in range(0, 20, 4))


def _recovery_key(code: str) -> str:
    """What is hashed and compared: upper case, without spaces or dashes."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _set_recovery_code(user: AppUser) -> str:
    code = new_recovery_code()
    user.recovery_code_hash = security.hash_secret(_recovery_key(code))
    user.recovery_code_created_at = now()
    return code


def _revoke_sessions(session: Session, user_id: uuid.UUID) -> None:
    session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )


def register_username(
    session: Session, *, username: str, password: str, password_confirm: str
) -> WithRecoveryCode:
    """Public registration with a username and password only: an ordinary (viewer) account,
    signed in at once, with a recovery code shown once. No role can be requested."""
    username = username.strip()
    problem = username_problem(username) or password_problem(password, password_confirm, username)
    if problem is not None:
        raise problem
    taken = conflict("username_taken", "This username is already used. Choose another.")
    with session.begin():
        if find_by_username(session, username) is not None:
            raise taken
        user = AppUser(
            username=username,
            email=None,
            display_name=username,
            password_hash=security.hash_password(password),
            created_via="self_registration",
        )
        code = _set_recovery_code(user)
        session.add(user)
        try:
            with session.begin_nested():
                session.flush()
        except IntegrityError as exc:  # registered concurrently with the same name
            raise taken from exc
        session.add(UserRole(user_id=user.id, role_code=Role.VIEWER.value))  # lowest role
        audit.record(
            session,
            SYSTEM_REGISTRATION,
            "user.create",
            entity_type="user",
            entity_id=user.id,
            metadata={"username": username, "roles": [Role.VIEWER.value], "via": "username"},
        )
        session.flush()
        return WithRecoveryCode(open_session(session, user, method="password"), code)


def recover_with_code(
    session: Session,
    *,
    username: str,
    recovery_code: str,
    new_password: str,
    new_password_confirm: str,
    client_address: str,
) -> WithRecoveryCode:
    """A forgotten password: the username, the recovery code and a new password. The code
    is spent (a new one is issued and shown once), every other session is signed out, and
    failed attempts are throttled like sign-in attempts."""
    settings = get_settings()
    username = username.strip()
    problem = password_problem(new_password, new_password_confirm, username)
    if problem is not None:
        raise problem
    key = f"recover:{username.lower()}"
    client_hash = security.keyed_digest(settings.client_hash_key.get_secret_value(), client_address)
    with session.begin():
        if _throttled(session, key, client_hash):
            audit.record(
                session, Principal(None, key), "auth.recover", "denied",
                metadata={"reason": "throttled"},
            )  # fmt: skip
            raise ApiError(
                429,
                "too_many_attempts",
                "Too many failed attempts. Wait a few minutes and try again.",
            )
        user = find_by_username(session, username)
        stored = user.recovery_code_hash if user is not None else None
        ok = (
            user is not None
            and user.status is AccountStatus.ACTIVE
            and not user.is_service_account
            and security.verify_password(stored, _recovery_key(recovery_code))
        )
        session.add(LoginAttempt(email=key, client_hash=client_hash, succeeded=ok))
        if ok and user is not None:
            user.password_hash = security.hash_password(new_password)
            user.password_changed_at = now()
            user.password_change_required = False
            code = _set_recovery_code(user)
            _revoke_sessions(session, user.id)
            audit.record(
                session, load_principal(session, user), "auth.recover",
                entity_type="user", entity_id=user.id,
            )  # fmt: skip
            return WithRecoveryCode(open_session(session, user, method="recovery_code"), code)
        audit.record(
            session, Principal(None, key), "auth.recover", "denied",
            metadata={"reason": "invalid_recovery"},
        )  # fmt: skip
        # Committed deliberately: failed attempts count towards throttling.
    raise ApiError(401, "invalid_recovery", "The username or recovery code is not correct.")


def replace_recovery_code(session: Session, principal: Principal, current_password: str) -> str:
    """A new recovery code for the signed-in account (the previous one stops working)."""
    with session.begin():
        user = get_user(session, principal.user_id)  # type: ignore[arg-type]
        if not has_password(user):
            raise ApiError(
                409,
                "no_password",
                "This account signs in without a password, so it needs no recovery code.",
            )
        if not security.verify_password(user.password_hash, current_password):
            audit.record_separately(
                principal, "auth.recovery_code", "denied",
                metadata={"reason": "wrong_current_password"},
            )  # fmt: skip
            raise ApiError(403, "wrong_current_password", "The current password is not correct.")
        code = _set_recovery_code(user)
        audit.record(
            session, principal, "auth.recovery_code", entity_type="user", entity_id=user.id
        )
        return code


def admin_reset_password(session: Session, actor: Principal, user_id: uuid.UUID) -> str:
    """An administrator's reset for an account that cannot recover itself: a temporary
    password (returned once, for the administrator to hand over in person) that must be
    changed at the next sign-in. Every session is signed out and the old recovery code
    stops working."""
    with session.begin():
        user = get_user(session, user_id)
        if user.is_service_account:
            raise unprocessable("service_account", "Service accounts have no password.")
        if user.id == actor.user_id:
            raise unprocessable("own_account", "Use Change password for your own account.")
        temporary = new_recovery_code()[:14]  # three groups of four, e.g. ABCD-EFGH-JKMN
        user.password_hash = security.hash_password(temporary, temporary=True)
        user.password_changed_at = now()
        user.password_change_required = True
        user.recovery_code_hash = None
        user.recovery_code_created_at = None
        _revoke_sessions(session, user.id)
        audit.record(session, actor, "user.password.reset", entity_type="user", entity_id=user.id)
        return temporary
