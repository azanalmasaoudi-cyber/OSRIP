"""Request-scoped authentication and server-side authorization.

Every protected route declares ``Depends(require(Permission.X))``. The check runs
on the server for every request; the frontend hiding a button is never relied on
(booklet 3.9). Denied attempts are audited in a separate transaction and change
no data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_session
from app.domain.enums import Permission
from app.services import accounts, audit
from app.services.principal import ANONYMOUS, Principal

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "osrip_csrf"

DbSession = Annotated[Session, Depends(get_session)]


def current_principal(request: Request, session: DbSession) -> Principal:
    token = request.cookies.get(get_settings().session_cookie_name)
    return accounts.resolve_session(session, token) or ANONYMOUS


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def _check_csrf(request: Request, principal: Principal) -> None:
    """Session-bound CSRF token (double submit) for state-changing requests."""
    if request.method in SAFE_METHODS:
        return
    supplied = request.headers.get(CSRF_HEADER, "")
    if (
        not supplied
        or principal.csrf_token_hash is None
        or not security.digests_equal(security.token_digest(supplied), principal.csrf_token_hash)
    ):
        audit.record_separately(
            principal,
            f"{request.method} {request.url.path}",
            "denied",
            metadata={"reason": "csrf_failed"},
        )
        raise ApiError(
            403, "csrf_failed", "The request could not be verified. Reload the page and try again."
        )


def require_session(request: Request, principal: CurrentPrincipal) -> Principal:
    """Signed in (with CSRF), even while a temporary password must still be changed.
    Only signing out and changing the password use this directly."""
    if not principal.is_authenticated:
        raise ApiError(401, "authentication_required", "Sign in to continue.")
    _check_csrf(request, principal)
    return principal


def _password_change_gate(principal: Principal) -> None:
    if principal.password_change_required:
        raise ApiError(
            403,
            "password_change_required",
            "Choose a new password before using this account.",
        )


def require_authenticated(request: Request, principal: CurrentPrincipal) -> Principal:
    require_session(request, principal)
    _password_change_gate(principal)
    return principal


def optional_session(request: Request, principal: CurrentPrincipal) -> Principal:
    """Open to visitors; a signed-in caller must still send the CSRF token, so another site
    cannot act under their session."""
    if principal.is_authenticated:
        _check_csrf(request, principal)
    return principal


def require(*permissions: Permission) -> Callable[..., Principal]:
    """Dependency: the principal must hold every listed permission."""

    def dependency(request: Request, principal: CurrentPrincipal) -> Principal:
        action = f"{request.method} {request.url.path}"
        if not principal.is_authenticated:
            audit.record_separately(
                principal, action, "denied", metadata={"reason": "authentication_required"}
            )
            raise ApiError(401, "authentication_required", "Sign in to continue.")
        _check_csrf(request, principal)
        _password_change_gate(principal)
        missing = [p.value for p in permissions if not principal.has(p)]
        if missing:
            audit.record_separately(
                principal,
                action,
                "denied",
                metadata={"reason": "permission_denied", "missing": missing},
            )
            raise ApiError(
                403,
                "permission_denied",
                "Your account does not have permission for this action.",
                {"missing_permissions": missing},
            )
        return principal

    return dependency
