"""Sign-in with a username and password only.

Registration asks for a username and a password (an ordinary viewer account); a forgotten
password is recovered with the one-time recovery code, or by an administrator's reset to a
temporary password. E-mail, e-mail link, phone (SMS or WhatsApp), Google and Microsoft sign-in
and e-mail verification are retired: their endpoints answer 410 and do nothing. The accounts,
e-mail addresses and phone numbers recorded before stay in the database untouched.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
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
from app.schemas.accounts import (
    LoginIn,
    MeOut,
    PasswordChangeIn,
    RecoverIn,
    RecoveryCodeIn,
    UsernameRegisterIn,
)
from app.services import accounts, mail, phone_numbers
from app.services.principal import Principal

router = APIRouter(prefix="/auth", tags=["auth"])
dev_router = APIRouter(prefix="/dev", tags=["development"])

REQUESTS_PER_CLIENT_HOUR = 20


def _me(principal: Principal, session: DbSession | None = None) -> MeOut:
    if not principal.is_authenticated:
        return MeOut(authenticated=False)
    email, verified, phone, phone_verified, has_password = principal.label, None, None, None, None
    username, has_recovery_code = None, None
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
                has_recovery_code = user.recovery_code_hash is not None
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
        has_recovery_code=has_recovery_code,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )


def _set_session_cookies(response: Response, new: accounts.NewSession) -> None:
    settings = get_settings()
    # Remember me: a cookie that outlives the browser; otherwise a browser-session cookie.
    # Either way the server enforces the session's own expiry and idle limit.
    max_age = settings.session_remember_days * 86400 if new.persistent else None
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
    ratelimit.check(f"{bucket}:{key}", REQUESTS_PER_CLIENT_HOUR, 3600)


@router.get("/providers")
def providers() -> dict[str, Any]:
    """The only way to sign in: a username and a password (and registration with them)."""
    return {"password": True, "registration": True, "methods": ["username_password"]}


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, session: DbSession) -> MeOut:
    client = request.client.host if request.client else "unknown"
    new = accounts.login(session, body.username, body.password, client, remember=body.remember)
    _set_session_cookies(response, new)
    return _me(new.principal, session)


# ------------------------------------------------------------------ username accounts


@router.post("/register/username", status_code=201)
def register_username(
    body: UsernameRegisterIn, request: Request, response: Response, session: DbSession
) -> dict[str, Any]:
    """Registration with a username and password only: an ordinary (viewer) account, signed
    in at once. The recovery code in the answer is shown once and never stored."""
    _client_limit(request, "register")
    done = accounts.register_username(
        session,
        username=body.username,
        password=body.password,
        password_confirm=body.password_confirm,
    )
    _set_session_cookies(response, done.new_session)
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "registered",
        "recovery_code": done.recovery_code,
        "me": _me(done.new_session.principal, session).model_dump(mode="json"),
    }


@router.post("/recover")
def recover(
    body: RecoverIn, request: Request, response: Response, session: DbSession
) -> dict[str, Any]:
    """A forgotten password, with the username and the recovery code. A new recovery code
    replaces the spent one; other sessions are signed out."""
    _client_limit(request, "recover")
    client = request.client.host if request.client else "unknown"
    done = accounts.recover_with_code(
        session,
        username=body.username,
        recovery_code=body.recovery_code,
        new_password=body.new_password,
        new_password_confirm=body.new_password_confirm,
        client_address=client,
    )
    _set_session_cookies(response, done.new_session)
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "recovered",
        "recovery_code": done.recovery_code,
        "me": _me(done.new_session.principal, session).model_dump(mode="json"),
    }


@router.post("/recovery-code")
def recovery_code(
    body: RecoveryCodeIn,
    response: Response,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> dict[str, str]:
    """A new recovery code for the signed-in account, shown once."""
    code = accounts.replace_recovery_code(session, principal, body.current_password)
    response.headers["Cache-Control"] = "no-store"
    return {"recovery_code": code}


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


# ------------------------------------------------------------------ retired sign-in methods

# E-mail registration and verification, e-mail links, password reset by e-mail, phone codes
# (SMS or WhatsApp), Google and Microsoft. Each answers 410 without reading its body, so no
# request can reach an account, create one or open a session through them.
RETIRED: tuple[tuple[str, str], ...] = (
    ("POST", "/register"),
    ("POST", "/verify-email"),
    ("POST", "/verify-email/resend"),
    ("POST", "/password/forgot"),
    ("POST", "/password/reset"),
    ("POST", "/magic-link"),
    ("POST", "/magic-link/consume"),
    ("POST", "/phone/request"),
    ("POST", "/phone/verify"),
    ("POST", "/email/link"),
    ("POST", "/email/link/confirm"),
    ("GET", "/oidc/{provider}/start"),
    ("GET", "/oidc/{provider}/callback"),
    ("GET", "/identities"),
    ("DELETE", "/identities/{identity_id}"),
)


def _retired() -> None:
    raise ApiError(
        410,
        "sign_in_method_retired",
        "This sign-in method is no longer offered. Sign in with your username and password.",
    )


for _method, _path in RETIRED:
    router.add_api_route(_path, _retired, methods=[_method], include_in_schema=False)


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
