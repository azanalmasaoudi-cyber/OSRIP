import uuid
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import (
    CSRF_COOKIE,
    CurrentPrincipal,
    DbSession,
    require_authenticated,
    require_session,
)
from app.core import ratelimit, security
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import AppUser, EmailOutbox, UserSession
from app.schemas.accounts import LoginIn, MeOut, PasswordChangeIn
from app.services import accounts, identity, mail, oidc, phone, phone_numbers, sms
from app.services.principal import Principal

router = APIRouter(prefix="/auth", tags=["auth"])
dev_router = APIRouter(prefix="/dev", tags=["development"])

OIDC_COOKIE = "osrip_oidc"
EMAIL_REQUESTS_PER_CLIENT_HOUR = 20


def _me(principal: Principal, session: DbSession | None = None) -> MeOut:
    if not principal.is_authenticated:
        return MeOut(authenticated=False)
    email, verified, phone, phone_verified, has_password = principal.label, None, None, None, None
    username = None
    if session is not None:
        with session.begin():
            user = session.get(AppUser, principal.user_id)
            if user is not None:
                email = user.email
                verified = user.email_verified_at is not None
                phone = phone_numbers.mask(user.phone_e164)
                phone_verified = user.phone_verified_at is not None
                has_password = user.password_hash != security.UNUSABLE_PASSWORD
                username = user.username
    return MeOut(
        username=username,
        password_change_required=principal.password_change_required,
        authenticated=True,
        user_id=principal.user_id,
        email=email,
        display_name=principal.display_name,
        email_verified=verified,
        phone=phone,
        phone_verified=phone_verified,
        has_password=has_password,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )


def _set_session_cookies(response: Response, new: accounts.NewSession) -> None:
    settings = get_settings()
    max_age = settings.session_absolute_hours * 3600
    # HttpOnly session cookie: unreadable by scripts. SameSite=Strict: not sent on
    # cross-site requests. Secure: HTTPS only (disabled only for local HTTP dev).
    response.set_cookie(
        settings.session_cookie_name,
        new.token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    # CSRF token: readable by the app's own scripts, echoed in X-CSRF-Token, and
    # bound to this session by its stored hash.
    response.set_cookie(
        CSRF_COOKIE,
        new.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _client_limit(request: Request, bucket: str) -> None:
    client = request.client.host if request.client else "unknown"
    key = security.keyed_digest(get_settings().client_hash_key.get_secret_value(), client)
    ratelimit.check(f"{bucket}:{key}", EMAIL_REQUESTS_PER_CLIENT_HOUR, 3600)


@router.get("/providers")
def providers() -> dict[str, Any]:
    """Which sign-in methods this server offers. Unconfigured ones are reported, not faked."""
    delivery = mail.delivery_mode()
    return {
        "password": True,
        "registration": delivery != "disabled",
        "magic_link": delivery != "disabled",
        "email_delivery": delivery,
        "oidc": oidc.configured(),
        "sms": sms.status(),
        "country_codes": list(phone_numbers.COUNTRY_CODES),
    }


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, session: DbSession) -> MeOut:
    client = request.client.host if request.client else "unknown"
    new = accounts.login(session, body.email, body.password, client)
    _set_session_cookies(response, new)
    return _me(new.principal, session)


@router.post("/password/change", response_model=MeOut)
def change_password(
    body: PasswordChangeIn,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_session)],
) -> MeOut:
    """The signed-in user sets a new password (required after a temporary one). Other
    sessions of the account are signed out."""
    accounts.change_password(session, principal, body.current_password, body.new_password)
    with session.begin():
        user = session.get(AppUser, principal.user_id)
        assert user is not None
        refreshed = accounts.load_principal(
            session, user, session.get(UserSession, principal.session_id)
        )
    return _me(refreshed, session)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_session)],
) -> Response:
    accounts.logout(session, principal)
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", secure=settings.session_cookie_secure, samesite="strict"
    )
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(principal: CurrentPrincipal, response: Response, session: DbSession) -> MeOut:
    response.headers["Cache-Control"] = "no-store"
    return _me(principal, session)


# ------------------------------------------------------------------ e-mail based flows


# The language of the page that made the request: messages put it first (both languages
# are always included).
Language = Literal["en", "ar"]


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)
    language: Language = "en"


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    language: Language = "en"


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ConfirmLinkIn(TokenIn):
    language: Language = "en"


class ResetIn(TokenIn):
    password: str = Field(min_length=1, max_length=1024)


def _accepted() -> dict[str, str]:
    return {"status": "accepted", "message": identity.GENERIC_EMAIL_REPLY}


@router.post("/register", status_code=202)
def register(body: RegisterIn, request: Request, session: DbSession) -> dict[str, str]:
    """Creates an unverified account with ordinary (viewer) access and sends a link."""
    _client_limit(request, "register")
    identity.register(
        session,
        email=body.email,
        display_name=body.display_name,
        password=body.password,
        language=body.language,
    )
    return _accepted()


@router.post("/verify-email")
def verify_email(body: TokenIn, session: DbSession) -> dict[str, str]:
    identity.verify_email(session, body.token)
    return {"status": "verified"}


@router.post("/verify-email/resend", status_code=202)
def resend(body: EmailIn, request: Request, session: DbSession) -> dict[str, str]:
    _client_limit(request, "resend")
    identity.resend_verification(session, body.email, body.language)
    return _accepted()


@router.post("/password/forgot", status_code=202)
def forgot(body: EmailIn, request: Request, session: DbSession) -> dict[str, str]:
    _client_limit(request, "forgot")
    identity.forgot_password(session, body.email, body.language)
    return _accepted()


@router.post("/password/reset")
def reset(body: ResetIn, session: DbSession) -> dict[str, str]:
    """Sets a new password, revokes every existing session and marks the address verified."""
    identity.reset_password(session, body.token, body.password)
    return {"status": "password_reset"}


@router.post("/magic-link", status_code=202)
def magic_link(body: EmailIn, request: Request, session: DbSession) -> dict[str, str]:
    _client_limit(request, "magic")
    identity.request_magic_link(session, body.email, body.language)
    return _accepted()


@router.post("/magic-link/consume", response_model=MeOut)
def magic_link_consume(body: TokenIn, response: Response, session: DbSession) -> MeOut:
    new = identity.consume_magic_link(session, body.token)
    _set_session_cookies(response, new)
    return _me(new.principal, session)


# ------------------------------------------------------------------ phone (SMS verification)

PHONE_REQUESTS_PER_CLIENT_HOUR = 20
PHONE_CHECKS_PER_CLIENT_HOUR = 60  # each challenge also allows only a few wrong codes


class PhoneRequestIn(BaseModel):
    country_code: str = Field(default="+968", max_length=5)
    number: str = Field(min_length=4, max_length=24)
    purpose: str = Field(default="sign_in", pattern="^(sign_in|link)$")
    # Needed to replace a verified number on an account that has a password.
    password: str | None = Field(default=None, max_length=1024)
    language: Language = "en"


class PhoneVerifyIn(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=12)
    display_name: str | None = Field(default=None, max_length=120)
    language: Language = "en"


@router.post("/phone/request", status_code=202)
def phone_request(
    body: PhoneRequestIn, request: Request, principal: CurrentPrincipal, session: DbSession
) -> dict[str, Any]:
    """Sends a code by SMS. Returns an opaque challenge id, never the code. The answer is
    the same whether or not the number already has an account."""
    if body.purpose == "link":
        principal = require_authenticated(request, principal)  # session + CSRF
    s = get_settings()
    client = request.client.host if request.client else "unknown"
    key = security.keyed_digest(s.client_hash_key.get_secret_value(), client)
    # Also counts requests refused before any SMS; never below the configured SMS limit, so
    # raising that (as the e2e server does) raises this too.
    ratelimit.check(
        f"phone:{key}", max(PHONE_REQUESTS_PER_CLIENT_HOUR, s.sms_per_client_hour), 3600
    )
    return phone.request_code(
        session,
        country_code=body.country_code,
        number=body.number,
        purpose=body.purpose,
        principal=principal,
        client_address=client,
        password=body.password,
        language=body.language,
    )


@router.post("/phone/verify")
def phone_verify(
    body: PhoneVerifyIn,
    request: Request,
    response: Response,
    principal: CurrentPrincipal,
    session: DbSession,
) -> dict[str, Any]:
    """Checks the code. Signs in (creating an ordinary account for a new number), or
    links the number to the signed-in account."""
    if principal.is_authenticated:
        principal = require_authenticated(request, principal)  # CSRF for signed-in callers
    s = get_settings()
    client = request.client.host if request.client else "unknown"
    key = security.keyed_digest(s.client_hash_key.get_secret_value(), client)
    checks = max(PHONE_CHECKS_PER_CLIENT_HOUR, s.sms_per_client_hour * s.sms_max_attempts)
    ratelimit.check(f"phone-check:{key}", checks, 3600)
    result = phone.verify_code(
        session,
        challenge_id=body.challenge_id,
        code=body.code,
        display_name=body.display_name,
        principal=principal,
        language=body.language,
    )
    if result.new_session is not None:
        _set_session_cookies(response, result.new_session)
        return {
            "status": result.outcome,
            "me": _me(result.new_session.principal, session).model_dump(mode="json"),
        }
    response.headers["Cache-Control"] = "no-store"
    return {"status": result.outcome, "me": _me(principal, session).model_dump(mode="json")}


class LinkEmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    # Needed to change a confirmed address on an account that has a password.
    password: str | None = Field(default=None, max_length=1024)
    language: Language = "en"


@router.post("/email/link", status_code=202)
def email_link(
    body: LinkEmailIn,
    request: Request,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> dict[str, str]:
    """Adds an e-mail address to the signed-in account, or changes its confirmed address
    (with the current password, or a recent sign-in), once the link sent to it is opened."""
    _client_limit(request, "link_email")
    identity.request_email_link(
        session, principal, body.email, password=body.password, language=body.language
    )
    return _accepted()


@router.post("/email/link/confirm")
def email_link_confirm(body: ConfirmLinkIn, session: DbSession) -> dict[str, str]:
    """Stores the address; ``changed`` when it replaced a confirmed one (which is told)."""
    return {"status": identity.confirm_email_link(session, body.token, body.language)}


# ------------------------------------------------------------------ OpenID Connect


def _frontend(path: str, **params: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}{path}" + (f"?{urlencode(params)}" if params else "")


@router.get("/oidc/{provider}/start")
def oidc_start(
    provider: str,
    principal: CurrentPrincipal,
    session: DbSession,
    intent: Annotated[str, Query(pattern="^(sign_in|link)$")] = "sign_in",
) -> RedirectResponse:
    started = oidc.start(session, provider, intent, principal)
    settings = get_settings()
    response = RedirectResponse(started.authorization_url, status_code=302)
    # Lax so the browser returns it on the provider's top-level redirect back to us.
    response.set_cookie(
        OIDC_COOKIE,
        started.browser_token,
        max_age=settings.oidc_request_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=f"{settings.api_prefix}/auth/oidc",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/oidc/{provider}/callback")
def oidc_callback(
    provider: str,
    request: Request,
    session: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    outcome: oidc.Outcome | None = None
    if error or not code or not state:
        target = _frontend("/sign-in", error="provider_declined")
    else:
        outcome = oidc.callback(
            session,
            provider,
            code=code,
            state=state,
            browser_token=request.cookies.get(OIDC_COOKIE),
        )
        if outcome.code == "signed_in":
            target = _frontend("/account", signed_in=provider)
        elif outcome.code == "linked":
            target = _frontend("/account", linked=provider)
        elif outcome.code == "link_required":
            target = _frontend("/sign-in", notice="link_required", provider=provider)
        else:
            target = _frontend("/sign-in", error=outcome.detail or "sign_in_failed")
    response = RedirectResponse(target, status_code=302)
    response.delete_cookie(OIDC_COOKIE, path=f"{settings.api_prefix}/auth/oidc")
    if outcome is not None and outcome.new_session is not None:
        _set_session_cookies(response, outcome.new_session)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/identities")
def list_identities(
    session: DbSession, principal: Annotated[Principal, Depends(require_authenticated)]
) -> list[dict[str, Any]]:
    assert principal.user_id is not None
    with session.begin():
        return oidc.identities(session, principal.user_id)


@router.delete("/identities/{identity_id}", status_code=204)
def unlink_identity(
    identity_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> Response:
    oidc.unlink(session, principal, identity_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ development SMS sink


@dev_router.get("/sms-outbox")
def sms_outbox() -> list[dict[str, Any]]:
    """Development and tests only: codes 'sent' by the scripted test provider. 404 in
    production and whenever another provider is configured."""
    s = get_settings()
    if s.environment == "production" or not s.sms_enabled or s.sms_provider != "test":
        raise ApiError(404, "not_found", "Not found.")
    return sms.scripted_provider().outbox()


# ------------------------------------------------------------------ development mail sink


@dev_router.get("/outbox")
def outbox(session: DbSession) -> list[dict[str, Any]]:
    """Development only: messages stored instead of sent. 404 in any other configuration."""
    if get_settings().environment != "development" or mail.delivery_mode() != "outbox":
        raise ApiError(404, "not_found", "Not found.")
    with session.begin():
        rows = session.scalars(select(EmailOutbox).order_by(EmailOutbox.id.desc()).limit(50))
        return [
            {
                "id": r.id,
                "to": r.to_address,
                "subject": r.subject,
                "body": r.body_text,
                "purpose": r.purpose,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
