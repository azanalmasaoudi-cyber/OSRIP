"""Self-service accounts: registration, e-mail verification, password recovery, magic links.

* New accounts get the ``viewer`` role only; administrators grant anything more.
* Tokens are 256-bit random values; only SHA-256 digests are stored. Each one
  expires and can be spent exactly once (atomic update plus a database trigger).
* Every request that takes an e-mail address answers the same way whether or not an
  account exists, so the endpoints cannot be used to discover registered addresses.
* Messages are only sent in response to the user's own request (no unsolicited mail).
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
from app.services import accounts, audit, mail
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


def _link(path: str, token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}{path}?token={token}"


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


def _send_verification(session: Session, user: AppUser) -> None:
    assert user.email is not None
    ttl = timedelta(hours=get_settings().verify_email_hours)
    raw = issue_token(session, user, "verify_email", ttl)
    if raw is None:
        return
    link = _link("/verify-email", raw)
    mail.send(
        session,
        to=user.email,
        subject="Confirm your OSRIP e-mail address / تأكيد بريدك الإلكتروني في OSRIP",
        body=(
            f"Hello {user.display_name},\n\nConfirm your e-mail address for OSRIP by opening this "
            f"link (valid for {get_settings().verify_email_hours} hours, usable once):\n{link}\n\n"
            "If you did not create an account, ignore this message.\n\n"
            f"لتأكيد بريدك الإلكتروني في OSRIP افتح الرابط التالي (صالح لمرة واحدة):\n{link}\n"
            "إذا لم تنشئ حساباً فتجاهل هذه الرسالة."
        ),
        purpose="verify_email",
    )


def _send_account_exists(session: Session, user: AppUser) -> None:
    assert user.email is not None
    mail.send(
        session,
        to=user.email,
        subject="OSRIP: an account already exists / يوجد حساب بالفعل",
        body=(
            "Someone asked to create an OSRIP account with this address, which already has one. "
            "Sign in, or use 'Forgot password'. If this was not you, no action is needed.\n\n"
            "طلب أحدهم إنشاء حساب في OSRIP بهذا العنوان، وله حساب بالفعل. سجّل الدخول أو استخدم "
            "'نسيت كلمة المرور'. إن لم تكن أنت فلا حاجة لأي إجراء."
        ),
        purpose="account_exists",
    )


# ------------------------------------------------------------------ registration


def register(session: Session, *, email: str, display_name: str, password: str) -> None:
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
                _send_verification(session, existing)
            elif not existing.is_service_account:
                _send_account_exists(session, existing)
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
        _send_verification(session, user)


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


def resend_verification(session: Session, email: str) -> None:
    mail.require_delivery()
    email = _check_email(email)
    with session.begin():
        user = _user(session, email)
        if user is not None and user.email_verified_at is None and not user.is_service_account:
            _send_verification(session, user)


# ------------------------------------------------------------------ password recovery


def forgot_password(session: Session, email: str) -> None:
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
        link = _link("/reset-password", raw)
        mail.send(
            session,
            to=user.email,
            subject="Reset your OSRIP password / إعادة تعيين كلمة المرور",
            body=(
                f"A password reset was requested for your OSRIP account. Open this link within "
                f"{ttl.seconds // 60} minutes; it works once:\n{link}\n\nIf you did not ask for "
                "this, ignore this message; your password stays unchanged.\n\n"
                f"طُلبت إعادة تعيين كلمة المرور لحسابك. افتح الرابط خلال {ttl.seconds // 60} دقيقة "
                f"(صالح لمرة واحدة):\n{link}\nإن لم تطلب ذلك فتجاهل الرسالة."
            ),
            purpose="reset_password",
        )


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


def request_magic_link(session: Session, email: str) -> None:
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
        link = _link("/magic-link", raw)
        mail.send(
            session,
            to=user.email,
            subject="Your OSRIP sign-in link / رابط الدخول إلى OSRIP",
            body=(
                f"Open this link within {ttl.seconds // 60} minutes to sign in. It works once:\n"
                f"{link}\n\nIf you did not ask for it, ignore this message.\n\n"
                f"افتح هذا الرابط خلال {ttl.seconds // 60} دقيقة لتسجيل الدخول (صالح لمرة واحدة):\n"
                f"{link}\nإن لم تطلبه فتجاهل الرسالة."
            ),
            purpose="magic_link",
        )


def consume_magic_link(session: Session, token: str) -> accounts.NewSession:
    with session.begin():
        user = consume_token(session, token, "magic_link")
        return accounts.open_session(session, user, method="magic_link")


# ------------------------------------------------------------------ linking an e-mail address


def request_email_link(session: Session, principal: Principal, email: str) -> None:
    """A signed-in account without a verified address (for example a phone-only one)
    adds one. The address is stored only when the link sent to it is opened."""
    mail.require_delivery()
    email = _check_email(email)
    with session.begin():
        user = session.get(AppUser, principal.user_id)
        if user is None:
            raise ApiError(401, "authentication_required", "Sign in to continue.")
        if user.email is not None and user.email_verified_at is not None:
            raise ApiError(
                409,
                "email_already_linked",
                "Your account already has a confirmed e-mail address.",
            )
        existing = _user(session, email)
        if existing is not None and existing.id != user.id:
            # Same answer as for a free address; the owner of that address is told instead.
            if not existing.is_service_account:
                _send_account_exists(session, existing)
            return
        ttl = timedelta(hours=get_settings().verify_email_hours)
        raw = issue_token(session, user, "link_email", ttl, email=email)
        if raw is None:
            return
        link = _link("/link-email", raw)
        mail.send(
            session,
            to=email,
            subject="Add this e-mail address to OSRIP / إضافة هذا البريد إلى OSRIP",
            body=(
                f"Hello {user.display_name},\n\nOpen this link to add this address to your OSRIP "
                f"account (valid for {get_settings().verify_email_hours} hours, usable once):\n"
                f"{link}\n\nIf you did not ask for this, ignore this message.\n\n"
                f"افتح هذا الرابط لإضافة هذا العنوان إلى حسابك في OSRIP (صالح لمرة واحدة):\n{link}\n"
                "إن لم تطلب ذلك فتجاهل الرسالة."
            ),
            purpose="link_email",
        )
        audit.record(
            session, principal, "auth.email.link_request", entity_type="user", entity_id=user.id
        )


def confirm_email_link(session: Session, token: str) -> None:
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
        user.email = row.email
        user.email_verified_at = accounts.now()
        audit.record(
            session,
            accounts.load_principal(session, user),
            "auth.email.link",
            entity_type="user",
            entity_id=user.id,
        )
