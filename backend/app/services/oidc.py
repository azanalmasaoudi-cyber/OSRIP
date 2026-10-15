"""Google and Microsoft sign-in with OpenID Connect (authorization code flow + PKCE).

Everything is validated on the backend:
* ``state`` (random, stored as a digest, single use, 10-minute expiry) and a
  browser-binding cookie, so a callback cannot be replayed or injected into
  another browser (login CSRF);
* PKCE (S256) code verifier sent with the code exchange;
* the ID token's signature against the provider's published keys (RS256 only),
  ``iss``, ``aud`` (our client ID), ``exp``/``iat`` and our ``nonce``.

Account rules:
* an identity is (provider, subject); e-mail addresses are never used to merge
  accounts. If an unlinked identity's e-mail matches an existing account, the user
  is asked to sign in to that account first and link the identity from there;
* a new account is created only when the provider asserts a verified e-mail, and it
  gets the ``viewer`` role only;
* linking requires an authenticated OSRIP session when the flow starts.
A provider is offered only when its client ID and secret are configured.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import ApiError
from app.domain.enums import AccountStatus, Role
from app.models import AppUser, ExternalIdentity, OidcRequest
from app.services import accounts, audit, monitoring
from app.services.principal import Principal

PROVIDERS = ("google", "microsoft")
SYSTEM = Principal(None, "system:oidc")

# Injectable for tests (an httpx.MockTransport-backed client).
http_client_factory: Callable[[], httpx.Client] = lambda: httpx.Client(timeout=10)  # noqa: E731
_cache: dict[str, tuple[float, Any]] = {}
CACHE_SECONDS = 3600


def reset_cache() -> None:
    _cache.clear()


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str
    client_id: str
    client_secret: str
    discovery_url: str


def provider_config(name: str) -> ProviderConfig | None:
    s = get_settings()
    if name == "google" and s.google_client_id and s.google_client_secret:
        return ProviderConfig(
            "google",
            s.google_client_id,
            s.google_client_secret.get_secret_value(),
            "https://accounts.google.com/.well-known/openid-configuration",
        )
    if name == "microsoft" and s.microsoft_client_id and s.microsoft_client_secret:
        return ProviderConfig(
            "microsoft",
            s.microsoft_client_id,
            s.microsoft_client_secret.get_secret_value(),
            f"https://login.microsoftonline.com/{s.microsoft_tenant}/v2.0/.well-known/openid-configuration",
        )
    return None


def configured() -> dict[str, bool]:
    return {p: provider_config(p) is not None for p in PROVIDERS}


def _get_json(url: str) -> Any:
    hit = _cache.get(url)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    service = "oidc_microsoft" if "microsoftonline" in url else "oidc_google"
    data = None
    for attempt in (1, 2):  # one retry for transient network failures
        try:
            with http_client_factory() as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            break
        except (httpx.HTTPError, ValueError):
            monitoring.external_failure(service, "metadata_unavailable")
            if attempt == 2:
                data = None
    if data is None:
        raise ApiError(502, "provider_unavailable", "The sign-in provider could not be reached.")
    monitoring.external_success(service)
    _cache[url] = (time.monotonic() + CACHE_SECONDS, data)
    return data


def _redirect_uri(provider: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}{get_settings().api_prefix}/auth/oidc/{provider}/callback"


def _require(provider: str) -> ProviderConfig:
    cfg = provider_config(provider) if provider in PROVIDERS else None
    if cfg is None:
        raise ApiError(
            404,
            "provider_not_configured",
            "This sign-in provider is not configured on this server.",
        )
    return cfg


@dataclass(frozen=True, slots=True)
class Start:
    authorization_url: str
    browser_token: str  # set as a short-lived HttpOnly SameSite=Lax cookie


def start(session: Session, provider: str, intent: str, principal: Principal) -> Start:
    cfg = _require(provider)
    if intent not in ("sign_in", "link"):
        raise ApiError(422, "invalid_intent", "Unknown sign-in intent.")
    if intent == "link" and not principal.is_authenticated:
        raise ApiError(401, "authentication_required", "Sign in before linking an account.")
    meta = _get_json(cfg.discovery_url)
    state, nonce, verifier, browser = (security.new_token() for _ in range(4))
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    with session.begin():
        session.add(
            OidcRequest(
                provider=provider,
                state_hash=security.token_digest(state),
                browser_hash=security.token_digest(browser),
                nonce=nonce,
                code_verifier=verifier,
                intent=intent,
                user_id=principal.user_id if intent == "link" else None,
                expires_at=accounts.now() + timedelta(minutes=get_settings().oidc_request_minutes),
            )
        )
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": _redirect_uri(provider),
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return Start(f"{meta['authorization_endpoint']}?{urlencode(params)}", browser)


def _validate_id_token(
    cfg: ProviderConfig, meta: dict[str, Any], id_token: str, nonce: str
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise ApiError(
            400, "invalid_id_token", "The provider's identity token is invalid."
        ) from exc
    if header.get("alg") != "RS256":
        raise ApiError(400, "invalid_id_token", "Unexpected identity token algorithm.")
    keys = _get_json(meta["jwks_uri"]).get("keys", [])
    jwk = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    if jwk is None:
        reset_cache()  # keys may have rotated; the next attempt refetches them
        raise ApiError(400, "invalid_id_token", "The identity token's signing key is unknown.")
    try:
        claims = jwt.decode(
            id_token,
            jwt.PyJWK(jwk).key,
            algorithms=["RS256"],
            audience=cfg.client_id,
            leeway=60,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise ApiError(
            400, "invalid_id_token", "The provider's identity token is invalid."
        ) from exc
    issuer = meta["issuer"]
    if cfg.name == "microsoft" and "{tenantid}" in issuer:
        issuer = issuer.replace("{tenantid}", str(claims.get("tid", "")))
    if claims.get("iss") != issuer:
        raise ApiError(400, "invalid_id_token", "The identity token was issued by another party.")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ApiError(400, "invalid_id_token", "The identity token does not match this request.")
    return claims


def _email_verified(provider: str, claims: dict[str, Any]) -> bool:
    if claims.get("email_verified") is True or claims.get("email_verified") == "true":
        return True
    # Microsoft signals a domain-verified address with xms_edov (optional claim).
    return provider == "microsoft" and claims.get("xms_edov") in (True, "1", 1)


@dataclass(frozen=True, slots=True)
class Outcome:
    code: str  # signed_in | linked | link_required | error
    new_session: accounts.NewSession | None = None
    detail: str | None = None


def callback(
    session: Session, provider: str, *, code: str, state: str, browser_token: str | None
) -> Outcome:
    cfg = _require(provider)
    meta = _get_json(cfg.discovery_url)
    with session.begin():
        request = session.scalar(
            update(OidcRequest)
            .where(
                OidcRequest.state_hash == security.token_digest(state),
                OidcRequest.provider == provider,
                OidcRequest.used_at.is_(None),
                OidcRequest.expires_at > func.now(),
            )
            .values(used_at=func.now())
            .returning(OidcRequest)
            .execution_options(synchronize_session=False)
        )
        if request is None:
            return Outcome("error", detail="invalid_state")
        if not browser_token or not security.digests_equal(
            security.token_digest(browser_token), request.browser_hash
        ):
            return Outcome("error", detail="browser_mismatch")
        nonce, verifier, intent, link_user = (
            request.nonce,
            request.code_verifier,
            request.intent,
            request.user_id,
        )

    try:
        with http_client_factory() as client:
            response = client.post(
                meta["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(provider),
                    "client_id": cfg.client_id,
                    "client_secret": cfg.client_secret,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            id_token = response.json()["id_token"]
    except (httpx.HTTPError, KeyError, ValueError):
        monitoring.external_failure(f"oidc_{provider}", "token_exchange_failed")
        return Outcome("error", detail="token_exchange_failed")
    try:
        claims = _validate_id_token(cfg, meta, id_token, nonce)
    except ApiError:
        return Outcome("error", detail="invalid_id_token")

    subject = str(claims["sub"])
    email = accounts.normalize_email(
        str(claims.get("email") or claims.get("preferred_username") or "")
    )
    verified = _email_verified(provider, claims) and "@" in email

    with session.begin():
        identity = session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == provider, ExternalIdentity.subject == subject
            )
        )
        if intent == "link":
            assert link_user is not None
            if identity is not None and identity.user_id != link_user:
                return Outcome("error", detail="identity_in_use")
            if identity is None:
                session.add(
                    ExternalIdentity(
                        user_id=link_user,
                        provider=provider,
                        subject=subject,
                        issuer=str(claims["iss"]),
                        email=email or None,
                        email_verified=verified,
                    )
                )
                user = session.get(AppUser, link_user)
                audit.record(
                    session,
                    Principal(link_user, (user.email or f"user:{user.id}") if user else "unknown"),
                    "auth.identity.link",
                    entity_type="user",
                    entity_id=link_user,
                    metadata={"provider": provider},
                )
            return Outcome("linked")

        if identity is not None:
            user = session.get(AppUser, identity.user_id)
            if user is None or user.status is not AccountStatus.ACTIVE or user.is_service_account:
                return Outcome("error", detail="account_unavailable")
            identity.last_used_at = accounts.now()
            return Outcome("signed_in", accounts.open_session(session, user, method=provider))

        if not verified:
            return Outcome("error", detail="email_not_verified_by_provider")
        existing = session.scalar(select(AppUser).where(AppUser.email == email))
        if existing is not None:
            # Same address, different proof: never merge. The owner links it after signing in.
            return Outcome("link_required")
        user = accounts.create_user(
            session,
            SYSTEM,
            email=email,
            display_name=str(claims.get("name") or email.split("@")[0])[:120],
            password=None,
            roles=[Role.VIEWER],
            email_verified=True,
            created_via=provider,
        )
        session.add(
            ExternalIdentity(
                user_id=user.id,
                provider=provider,
                subject=subject,
                issuer=str(claims["iss"]),
                email=email,
                email_verified=True,
                last_used_at=accounts.now(),
            )
        )
        session.flush()
        return Outcome("signed_in", accounts.open_session(session, user, method=provider))


def identities(session: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ExternalIdentity)
        .where(ExternalIdentity.user_id == user_id)
        .order_by(ExternalIdentity.linked_at)
    )
    return [
        {
            "id": str(i.id),
            "provider": i.provider,
            "email": i.email,
            "linked_at": i.linked_at.isoformat(),
            "last_used_at": i.last_used_at.isoformat() if i.last_used_at else None,
        }
        for i in rows
    ]


def unlink(session: Session, principal: Principal, identity_id: uuid.UUID) -> None:
    with session.begin():
        identity = session.get(ExternalIdentity, identity_id)
        if identity is None or identity.user_id != principal.user_id:
            raise ApiError(404, "not_found", "That linked account was not found.")
        user = session.get(AppUser, identity.user_id)
        others = session.scalar(
            select(func.count()).where(
                ExternalIdentity.user_id == identity.user_id, ExternalIdentity.id != identity.id
            )
        )
        can_still_sign_in = bool(others) or (
            user is not None
            and (
                (
                    user.email_verified_at is not None
                    and user.password_hash != security.UNUSABLE_PASSWORD
                )
                or user.phone_verified_at is not None  # SMS sign-in
            )
        )
        if not can_still_sign_in:
            raise ApiError(
                409,
                "last_sign_in_method",
                "Set a password (use 'Forgot password') before removing your only sign-in method.",
            )
        session.delete(identity)
        audit.record(
            session,
            principal,
            "auth.identity.unlink",
            entity_type="user",
            entity_id=principal.user_id,
            metadata={"provider": identity.provider},
        )
