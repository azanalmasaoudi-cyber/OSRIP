"""Registration, sign-in and linking by phone, with SMS verification.

Rules enforced here, whatever the provider does:

* the number is validated and normalized to E.164 before anything is sent;
* a resend cooldown per number, hourly limits per number, per client address and in
  total, and a per-process limit per client (``ratelimit``) in the route;
* each challenge expires, allows a fixed number of wrong codes, and is spent once:
  the row is locked while a code is checked, and a database trigger refuses any
  change to a consumed challenge, so a replayed or concurrent request cannot reuse it;
* the browser only ever receives an opaque challenge id, never the code;
* an account is created (with the ``viewer`` role only) or signed in only after the
  code is verified; answers before verification do not reveal whether a number has
  an account;
* linking needs a signed-in session, and a number verified by one account is never
  moved to, or merged with, another account;
* replacing a verified number needs the current password, or a recent sign-in for an
  account without one, and a confirmed e-mail address is told about the change;
* the code is sent in the person's language (Arabic or English) when the provider can.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import ApiError, unprocessable
from app.domain.enums import AccountStatus, Role
from app.models import AppUser, PhoneChallenge, UserRole
from app.services import accounts, audit, identity, monitoring, phone_numbers, sms
from app.services.principal import Principal

PURPOSES = ("sign_in", "link")
SYSTEM = Principal(None, "system:phone")

DELIVERY_MESSAGES = {
    "invalid_number": (
        422,
        "The SMS service does not accept this number. Check it, or register with e-mail instead.",
    ),
    "undeliverable": (
        422,
        "A code cannot be delivered to this number. Check the number, or register with e-mail instead.",
    ),
    "provider_unavailable": (
        503,
        "The SMS service is not responding. Try again in a few minutes, or use e-mail instead.",
    ),
    "not_test_recipient": (
        422,
        "This is a WhatsApp demonstration: codes are sent only to the approved test numbers. Use e-mail instead.",
    ),
}


def _unavailable() -> ApiError:
    return ApiError(
        503,
        "sms_unavailable",
        "Phone verification is not available on this server. Register or sign in with e-mail instead.",
    )


def _delivery_error(exc: sms.DeliveryError) -> ApiError:
    monitoring.external_failure("sms", exc.code)
    status, message = DELIVERY_MESSAGES.get(exc.code, DELIVERY_MESSAGES["provider_unavailable"])
    return ApiError(status, f"sms_{exc.code}", message)


def _count(session: Session, *where: Any) -> int:
    since = accounts.now() - timedelta(hours=1)
    return (
        session.scalar(
            select(func.count())
            .select_from(PhoneChallenge)
            .where(PhoneChallenge.created_at >= since, *where)
        )
        or 0
    )


# ------------------------------------------------------------------ request a code


def request_code(
    session: Session,
    *,
    country_code: str,
    number: str,
    purpose: str,
    principal: Principal,
    client_address: str,
    password: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    s = get_settings()
    provider = sms.get_provider()
    if provider is None:
        raise _unavailable()
    if purpose not in PURPOSES:
        raise unprocessable("invalid_purpose", "Unknown purpose.")
    if purpose == "link" and not principal.is_authenticated:
        raise ApiError(401, "authentication_required", "Sign in to continue.")
    phone = phone_numbers.normalize(country_code, number)
    client_hash = security.keyed_digest(s.client_hash_key.get_secret_value(), client_address)
    now = accounts.now()

    with session.begin():
        # Serialize requests for the same number so the cooldown cannot be raced.
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 8))"), {"k": phone})
        if purpose == "link":
            user = session.get(AppUser, principal.user_id)
            if user is not None and user.phone_e164 == phone:
                raise ApiError(
                    409, "phone_already_linked", "This number is already verified on your account."
                )
            if user is not None and user.phone_e164 and user.phone_verified_at:
                # Replacing a verified number: the same step-up check as for an e-mail change.
                accounts.confirm_identity(session, principal, user, password, action="phone.change")
        last = session.scalar(
            select(func.max(PhoneChallenge.created_at)).where(PhoneChallenge.phone_e164 == phone)
        )
        if last is not None:
            wait = s.sms_resend_seconds - int((now - last).total_seconds())
            if wait > 0:
                raise ApiError(
                    429,
                    "sms_resend_cooldown",
                    f"Wait {wait} seconds before asking for another code.",
                    {"retry_after": wait},
                )
        if _count(session, PhoneChallenge.phone_e164 == phone) >= s.sms_per_number_hour:
            raise ApiError(
                429,
                "sms_number_limit",
                "Too many codes were sent to this number in the last hour. Try again later, or use e-mail.",
            )
        if _count(session, PhoneChallenge.client_hash == client_hash) >= s.sms_per_client_hour:
            raise ApiError(
                429,
                "sms_client_limit",
                "Too many code requests from this connection. Try again later.",
            )
        if _count(session) >= s.sms_global_hour:
            raise ApiError(
                503, "sms_busy", "The SMS service is busy. Try again later, or use e-mail."
            )

        try:
            started = provider.request_verification(
                phone, language if language in sms.LOCALES else None
            )
        except sms.DeliveryError as exc:
            raise _delivery_error(exc) from exc
        monitoring.external_success("sms")

        challenge = PhoneChallenge(
            phone_e164=phone,
            purpose=purpose,
            user_id=principal.user_id if purpose == "link" else None,
            provider=provider.name,
            provider_ref=started.provider_ref,
            client_hash=client_hash,
            max_attempts=s.sms_max_attempts,
            expires_at=now + timedelta(minutes=s.sms_code_minutes),
        )
        session.add(challenge)
        session.flush()
        audit.record(
            session,
            principal
            if principal.is_authenticated
            else Principal(None, phone_numbers.mask(phone) or "phone"),
            "auth.phone.request",
            entity_type="phone_challenge",
            entity_id=challenge.id,
            metadata={
                "purpose": purpose,
                "phone": phone_numbers.mask(phone),
                "provider": provider.name,
            },
        )
        return {
            "challenge_id": str(challenge.id),
            "phone_masked": phone_numbers.mask(phone),
            "expires_in": s.sms_code_minutes * 60,
            "resend_after": s.sms_resend_seconds,
            "max_attempts": s.sms_max_attempts,
        }


# ------------------------------------------------------------------ verify a code


@dataclass(frozen=True, slots=True)
class Verified:
    outcome: str  # signed_in | registered | linked | changed
    new_session: accounts.NewSession | None


INVALID = ("sms_challenge_invalid", "This code request is not valid any more. Ask for a new code.")


def _create_phone_user(session: Session, phone: str, display_name: str | None) -> AppUser:
    name = (display_name or "").strip() or "OSRIP user"
    if len(name) > 120:
        raise unprocessable("invalid_name", "Enter a name of 1 to 120 characters.")
    user = AppUser(
        email=None,
        display_name=name,
        password_hash=security.UNUSABLE_PASSWORD,  # signs in with SMS codes
        phone_e164=phone,
        phone_verified_at=accounts.now(),
        created_via="phone",
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_code=Role.VIEWER.value))  # ordinary access only
    audit.record(
        session,
        SYSTEM,
        "user.create",
        entity_type="user",
        entity_id=user.id,
        metadata={"phone": phone_numbers.mask(phone), "roles": [Role.VIEWER.value], "via": "phone"},
    )
    session.flush()
    return user


def verify_code(
    session: Session,
    *,
    challenge_id: str,
    code: str,
    display_name: str | None,
    principal: Principal,
    language: str = "en",
) -> Verified:
    provider = sms.get_provider()
    if provider is None:
        raise _unavailable()
    code = (code or "").strip()
    if not code.isdigit() or not 4 <= len(code) <= 10:
        raise unprocessable("invalid_code_format", "Enter the code from the SMS (digits only).")
    try:
        cid = uuid.UUID(challenge_id)
    except ValueError:
        raise ApiError(400, *INVALID) from None

    failure: ApiError | None = None
    result: Verified | None = None
    with session.begin():
        challenge = session.scalar(
            select(PhoneChallenge).where(PhoneChallenge.id == cid).with_for_update()
        )
        now = accounts.now()
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.provider != provider.name
        ):
            raise ApiError(400, *INVALID)
        if challenge.purpose == "link" and principal.user_id != challenge.user_id:
            raise ApiError(400, *INVALID)
        if challenge.expires_at <= now:
            raise ApiError(400, "sms_code_expired", "This code has expired. Ask for a new one.")
        if challenge.attempts >= challenge.max_attempts:
            raise ApiError(
                400, "sms_too_many_attempts", "Too many wrong codes. Ask for a new code."
            )

        challenge.attempts += 1
        session.flush()  # the attempt counts even if the provider call fails
        try:
            checked = provider.check_verification(challenge.provider_ref, code)
        except sms.DeliveryError as exc:
            checked = None
            failure = _delivery_error(exc)

        remaining = challenge.max_attempts - challenge.attempts
        if checked is sms.CheckStatus.DENIED:
            failure = (
                ApiError(
                    400,
                    "sms_code_incorrect",
                    "The code is not correct. Check the SMS and try again.",
                    {"attempts_left": remaining},
                )
                if remaining > 0
                else ApiError(
                    400, "sms_too_many_attempts", "Too many wrong codes. Ask for a new code."
                )
            )
        elif checked is sms.CheckStatus.EXPIRED:
            failure = ApiError(400, "sms_code_expired", "This code has expired. Ask for a new one.")
        elif checked is sms.CheckStatus.APPROVED:
            monitoring.external_success("sms")
            challenge.consumed_at = now
            session.flush()
            result, failure = _complete(session, challenge, display_name, language)
    # Committed either way: a wrong code still counts as an attempt, and a verified
    # challenge stays spent even if the account step is refused.
    if failure is not None:
        raise failure
    assert result is not None
    return result


def _complete(
    session: Session, challenge: PhoneChallenge, display_name: str | None, language: str
) -> tuple[Verified | None, ApiError | None]:
    phone = challenge.phone_e164
    masked = phone_numbers.mask(phone)
    if challenge.purpose == "link":
        user = session.get(AppUser, challenge.user_id)
        if user is None or user.status is not AccountStatus.ACTIVE:
            return None, ApiError(400, *INVALID)
        other = session.scalar(
            select(AppUser).where(AppUser.phone_e164 == phone, AppUser.id != user.id)
        )
        if other is not None:
            return None, ApiError(
                409,
                "phone_taken",
                "This number is verified on another OSRIP account. Accounts are never merged.",
            )
        changed = bool(user.phone_e164 and user.phone_verified_at and user.phone_e164 != phone)
        user.phone_e164 = phone
        user.phone_verified_at = accounts.now()
        if changed:
            identity.notify_phone_changed(session, user, masked or "", language)
        audit.record(
            session,
            accounts.load_principal(session, user),
            "auth.phone.change" if changed else "auth.phone.link",
            entity_type="user",
            entity_id=user.id,
            metadata={"phone": masked},
        )
        return Verified("changed" if changed else "linked", None), None

    user = session.scalar(select(AppUser).where(AppUser.phone_e164 == phone))
    outcome = "signed_in"
    if user is None:
        try:
            with session.begin_nested():
                user = _create_phone_user(session, phone, display_name)
            outcome = "registered"
        except IntegrityError:  # created concurrently by another verified request
            user = session.scalar(select(AppUser).where(AppUser.phone_e164 == phone))
    if user is None or user.is_service_account or user.status is not AccountStatus.ACTIVE:
        return None, ApiError(
            403, "account_unavailable", "This account cannot sign in. Contact an administrator."
        )
    return Verified(outcome, accounts.open_session(session, user, method="phone")), None
