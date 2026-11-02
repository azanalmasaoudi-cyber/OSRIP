"""Self-service accounts: registration, e-mail verification, password recovery, magic links,
adding or changing an e-mail address.

* New accounts get the ``viewer`` role only; administrators grant anything more.
* Tokens are 256-bit random values; only SHA-256 digests are stored. Each one
  expires and can be spent exactly once (atomic update plus a database trigger).
* Every request that takes an e-mail address answers the same way whether or not an
  account exists, so the endpoints cannot be used to discover registered addresses.
* Messages are only sent in response to the user's own request (no unsolicited mail),
  in Arabic and English with the reader's language first (``mail_templates``).
* Changing a confirmed address needs the current password (or a recent sign-in for an
  account without one); the new address is stored only when the link sent to it is
  opened, and the old address is then told about the change.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import ApiError, unprocessable
from app.domain.enums import AccountStatus, Role
from app.models import AppUser, AuthToken
from app.services import accounts, audit, mail, mail_templates
from app.services.principal import Principal

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SYSTEM = Principal(None, "system:identity")

GENERIC_EMAIL_REPLY = (
    "If the address can be used, we have sent a message to it. Check your inbox and spam folder."
)


def _check_email(email: str) -> str:
    email = accounts.normalize_email(email)
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise unprocessable("invalid_email", "Enter a valid e-mail address.")
    return email


def _user(session: Session, email: str) -> AppUser | None:
    return session.scalar(select(AppUser).where(AppUser.email == email))


def _link(path: str, token: str | None = None) -> str:
    base = f"{get_settings().public_base_url.rstrip('/')}{path}"
    return f"{base}?token={token}" if token else base


def mask_email(email: str) -> str:
    """a•••@example.com: enough for the owner to recognise, not to read off."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}" if domain else "•••"


def _send(
    session: Session,
    kind: str,
    *,
    to: str,
    language: str,
    link: str | None = None,
    **values: object,
) -> None:
    message = mail_templates.render(kind, language, link=link, **values)
    mail.send(
        session, to=to, subject=message.subject, body=message.text, html=message.html, purpose=kind
    )


def _recent_tokens(session: Session, user_id: uuid.UUID, purpose: str) -> int:
    since = accounts.now() - timedelta(hours=1)
    return (
        session.scalar(
            select(func.count()).where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == purpose,
                AuthToken.created_at >= since,
            )
        )
        or 0
    )


def issue_token(
    session: Session, user: AppUser, purpose: str, ttl: timedelta, email: str | None = None
) -> str | None:
    """New single-use token, or None when the hourly limit for this user is reached."""
    if _recent_tokens(session, user.id, purpose) >= get_settings().email_requests_per_hour:
        return None
    raw = security.new_token()
    session.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=security.token_digest(raw),
            expires_at=accounts.now() + ttl,
            email=email,
        )
    )
    session.flush()
    return raw


def consume_token(session: Session, raw: str, purpose: str) -> AppUser:
    """Spend a token once. Unknown, expired, reused or wrong-purpose tokens all fail alike."""
    user_id = session.scalar(
        update(AuthToken)
        .where(
            AuthToken.token_hash == security.token_digest(raw),
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > func.now(),
        )
        .values(used_at=func.now())
        .returning(AuthToken.user_id)
        .execution_options(synchronize_session=False)
    )
    user = session.get(AppUser, user_id) if user_id else None
    if user is None or user.is_service_account or user.status is not AccountStatus.ACTIVE:
        raise ApiError(
            400,
            "invalid_or_expired_token",
            "This link is invalid, has expired or has already been used. Request a new one.",
        )
    return user


# ------------------------------------------------------------------ messages (EN + AR)


def _send_verification(session: Session, user: AppUser, language: str) -> None:
    assert user.email is not None
    hours = get_settings().verify_email_hours
    raw = issue_token(session, user, "verify_email", timedelta(hours=hours))
    if raw is None:
        return
    _send(
        session, "verify_email", to=user.email, language=language,
        link=_link("/verify-email", raw), name=user.display_name, hours=hours,
    )  # fmt: skip


def _send_account_exists(session: Session, user: AppUser, language: str) -> None:
    assert user.email is not None
    _send(session, "account_exists", to=user.email, language=language, link=_link("/sign-in"))


# ------------------------------------------------------------------ registration


def register(
    session: Session, *, email: str, display_name: str, password: str, language: str = "en"
) -> None:
    mail.require_delivery()
    email = _check_email(email)
    name = display_name.strip()
    if not 1 <= len(name) <= 120:
        raise unprocessable("invalid_name", "Enter a name of 1 to 120 characters.")
    try:
        security.hash_password(password)  # strength check before touching the database
    except ValueError as exc:
        raise unprocessable("weak_password", str(exc)) from exc
    with session.begin():
        existing = _user(session, email)
        if existing is not None:
            if existing.email_verified_at is None and not existing.is_service_account:
                _send_verification(session, existing, language)
            elif not existing.is_service_account:
                _send_account_exists(session, existing, language)
            return
        user = accounts.create_user(
            session,
            SYSTEM,
            email=email,
            display_name=name,
            password=password,
            roles=[Role.VIEWER],  # ordinary access only
            email_verified=False,
            created_via="self_registration",
        )
        _send_verification(session, user, language)


def verify_email(session: Session, token: str) -> None:
    with session.begin():
        user = consume_token(session, token, "verify_email")
        if user.email_verified_at is None:
            user.email_verified_at = accounts.now()
        audit.record(
            session,
            accounts.load_principal(session, user),
            "auth.verify_email",
            entity_type="user",
            entity_id=user.id,
        )


def resend_verification(session: Session, email: str, language: str = "en") -> None:
    mail.require_delivery()
    email = _check_email(email)
    with session.begin():
        user = _user(session, email)
        if user is not None and user.email_verified_at is None and not user.is_service_account:
            _send_verification(session, user, language)


# ------------------------------------------------------------------ password recovery


def forgot_password(session: Session, email: str, language: str = "en") -> None:
    mail.require_delivery()
    email = _check_email(email)
    with session.begin():
        user = _user(session, email)
        if user is None or user.is_service_account or user.status is not AccountStatus.ACTIVE:
            return
        ttl = timedelta(minutes=get_settings().reset_password_minutes)
        raw = issue_token(session, user, "reset_password", ttl)
        if raw is None or user.email is None:
            return
        _send(
            session, "reset_password", to=user.email, language=language,
            link=_link("/reset-password", raw), name=user.display_name,
            minutes=ttl.seconds // 60,
        )  # fmt: skip


def reset_password(session: Session, token: str, password: str) -> None:
    try:
        new_hash = security.hash_password(password)
    except ValueError as exc:
        raise unprocessable("weak_password", str(exc)) from exc
    with session.begin():
        user = consume_token(session, token, "reset_password")
        user.password_hash = new_hash
        user.password_changed_at = accounts.now()
        if user.email_verified_at is None:  # the link proved ownership of the address
            user.email_verified_at = accounts.now()
        accounts.revoke_all_sessions(session, user.id)  # sign out everywhere
        audit.record(
            session,
            accounts.load_principal(session, user),
            "auth.reset_password",
            entity_type="user",
            entity_id=user.id,
        )


# ------------------------------------------------------------------ magic links


def request_magic_link(session: Session, email: str, language: str = "en") -> None:
    mail.require_delivery()
    email = _check_email(email)
    with session.begin():
        user = _user(session, email)
        if (
            user is None
            or user.is_service_account
            or user.status is not AccountStatus.ACTIVE
            or user.email_verified_at is None
        ):
            return
        ttl = timedelta(minutes=get_settings().magic_link_minutes)
        raw = issue_token(session, user, "magic_link", ttl)
        if raw is None or user.email is None:
            return
        _send(
            session, "magic_link", to=user.email, language=language,
            link=_link("/magic-link", raw), name=user.display_name, minutes=ttl.seconds // 60,
        )  # fmt: skip


def consume_magic_link(session: Session, token: str) -> accounts.NewSession:
    with session.begin():
        user = consume_token(session, token, "magic_link")
        return accounts.open_session(session, user, method="magic_link")


# ------------------------------------------------------------------ adding or changing an address


def request_email_link(
    session: Session,
    principal: Principal,
    email: str,
    *,
    password: str | None = None,
    language: str = "en",
) -> None:
    """Add an e-mail address to the signed-in account (one without a confirmed address, such
    as a phone-only account), or change a confirmed one. A change needs the current password
    (or a recent sign-in). The address is stored only when the link sent to it is opened."""
    mail.require_delivery()
    email = _check_email(email)
    with session.begin():
        user = session.get(AppUser, principal.user_id)
        if user is None:
            raise ApiError(401, "authentication_required", "Sign in to continue.")
        changing = user.email is not None and user.email_verified_at is not None
        if changing:
            if email == user.email:
                raise ApiError(
                    409, "email_unchanged", "This is already the address of your account."
                )
            accounts.confirm_identity(session, principal, user, password, action="email.change")
        existing = _user(session, email)
        if existing is not None and existing.id != user.id:
            # Same answer as for a free address; the owner of that address is told instead.
            if not existing.is_service_account:
                _send_account_exists(session, existing, language)
            return
        hours = get_settings().verify_email_hours
        raw = issue_token(session, user, "link_email", timedelta(hours=hours), email=email)
        if raw is None:
            return
        _send(
            session, "change_email" if changing else "link_email", to=email, language=language,
            link=_link("/link-email", raw), name=user.display_name, hours=hours,
        )  # fmt: skip
        audit.record(
            session,
            principal,
            "auth.email.change_request" if changing else "auth.email.link_request",
            entity_type="user",
            entity_id=user.id,
            metadata={"to": mask_email(email)},
        )


def confirm_email_link(session: Session, token: str, language: str = "en") -> str:
    """Store the address the link was sent to. Returns ``linked`` or ``changed``; after a
    change, the previous address is told (it can then reset the password if it was not
    the owner's doing)."""
    with session.begin():
        row = session.execute(
            update(AuthToken)
            .where(
                AuthToken.token_hash == security.token_digest(token),
                AuthToken.purpose == "link_email",
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > func.now(),
            )
            .values(used_at=func.now())
            .returning(AuthToken.user_id, AuthToken.email)
            .execution_options(synchronize_session=False)
        ).first()
        user = session.get(AppUser, row.user_id) if row else None
        if row is None or user is None or user.status is not AccountStatus.ACTIVE:
            raise ApiError(
                400,
                "invalid_or_expired_token",
                "This link is invalid, has expired or has already been used. Request a new one.",
            )
        taken = session.scalar(
            select(AppUser).where(AppUser.email == row.email, AppUser.id != user.id)
        )
        if taken is not None:
            raise ApiError(
                409,
                "email_taken",
                "This address belongs to another OSRIP account. Accounts are never merged.",
            )
        previous = user.email if user.email_verified_at is not None else None
        user.email = row.email
        user.email_verified_at = accounts.now()
        changed = previous is not None and previous != row.email
        if changed:
            assert previous is not None
            _send(
                session, "email_changed", to=previous, language=language,
                link=_link("/forgot-password"), name=user.display_name,
                address=mask_email(row.email),
            )  # fmt: skip
        audit.record(
            session,
            accounts.load_principal(session, user),
            "auth.email.change" if changed else "auth.email.link",
            entity_type="user",
            entity_id=user.id,
            metadata={"to": mask_email(row.email)},
        )
        return "changed" if changed else "linked"


def notify_phone_changed(session: Session, user: AppUser, phone_masked: str, language: str) -> None:
    """Tell a confirmed e-mail address that the account's verified number changed."""
    if user.email and user.email_verified_at and mail.delivery_mode() != "disabled":
        _send(
            session, "phone_changed", to=user.email, language=language,
            link=_link("/account"), name=user.display_name, phone=phone_masked,
        )  # fmt: skip
