"""Google/Microsoft sign-in callbacks, validated against a scripted OpenID provider.

The provider's discovery document, signing keys and token endpoint are served by an
httpx MockTransport with a real RSA key pair, so signature, issuer, audience, expiry,
nonce, state and PKCE checks run exactly as in production.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from tests.workflow_helpers import API

pytestmark = pytest.mark.integration

GOOGLE_ISSUER = "https://accounts.google.com"
MS_ISSUER_TEMPLATE = "https://login.microsoftonline.com/{tenantid}/v2.0"
CLIENT_ID = "osrip-test-client"


class FakeOP:
    """A scripted OpenID provider."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwks = {"keys": [{**jwk, "kid": "k1", "alg": "RS256", "use": "sig"}]}
        self.next_claims: dict[str, Any] = {}
        self.sign_with = self.key
        self.last_token_request: dict[str, list[str]] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            ms = "microsoftonline" in url
            return httpx.Response(
                200,
                json={
                    "issuer": MS_ISSUER_TEMPLATE if ms else GOOGLE_ISSUER,
                    "authorization_endpoint": "https://op.test/authorize",
                    "token_endpoint": "https://op.test/token",
                    "jwks_uri": "https://op.test/jwks",
                },
            )
        if url == "https://op.test/jwks":
            return httpx.Response(200, json=self.jwks)
        if url == "https://op.test/token":
            self.last_token_request = parse_qs(request.content.decode())
            token = jwt.encode(
                self.next_claims, self.sign_with, algorithm="RS256", headers={"kid": "k1"}
            )
            return httpx.Response(
                200, json={"id_token": token, "access_token": "x", "token_type": "Bearer"}
            )
        return httpx.Response(404)


@pytest.fixture
def op(monkeypatch):  # noqa: ANN001, ANN201
    from app.core.config import get_settings
    from app.services import oidc

    fake = FakeOP()
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_client_secret", SecretStr("secret"))
    monkeypatch.setattr(settings, "microsoft_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "microsoft_client_secret", SecretStr("secret"))
    monkeypatch.setattr(
        oidc,
        "http_client_factory",
        lambda: httpx.Client(transport=httpx.MockTransport(fake.handler)),
    )
    oidc.reset_cache()
    yield fake
    oidc.reset_cache()


def start(client: TestClient, provider: str = "google", intent: str = "sign_in") -> dict[str, str]:
    r = client.get(
        f"{API}/auth/oidc/{provider}/start", params={"intent": intent}, follow_redirects=False
    )
    assert r.status_code == 302, r.text
    return {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}


def claims(
    params: dict[str, str], *, sub: str, email: str, verified: bool = True, **extra: Any
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "iss": GOOGLE_ISSUER,
        "aud": CLIENT_ID,
        "sub": sub,
        "email": email,
        "email_verified": verified,
        "nonce": params["nonce"],
        "iat": now,
        "exp": now + 600,
        "name": "Test Person",
        **extra,
    }


def finish(
    client: TestClient, op: FakeOP, params: dict[str, str], provider: str = "google"
) -> dict[str, str]:
    r = client.get(
        f"{API}/auth/oidc/{provider}/callback",
        params={"code": "abc", "state": params["state"]},
        follow_redirects=False,
    )
    assert r.status_code == 302
    location = urlparse(r.headers["location"])
    return {"path": location.path, **{k: v[0] for k, v in parse_qs(location.query).items()}}


def identity_count(sub: str) -> int:
    from app.db.session import session_factory
    from app.models import ExternalIdentity

    with session_factory()() as s, s.begin():
        return s.scalar(select(func.count()).where(ExternalIdentity.subject == sub)) or 0


def test_new_account_from_a_verified_provider_identity(app, op) -> None:  # noqa: ANN001
    client = TestClient(app)
    params = start(client)
    assert params["code_challenge_method"] == "S256" and params["client_id"] == CLIENT_ID
    assert params["redirect_uri"].endswith("/api/v1/auth/oidc/google/callback")
    sub, address = uuid.uuid4().hex, f"g-{uuid.uuid4().hex[:8]}@test.invalid"
    op.next_claims = claims(params, sub=sub, email=address)
    result = finish(client, op, params)
    assert result == {"path": "/account", "signed_in": "google"}
    # PKCE: the verifier sent to the token endpoint matches the challenge.
    verifier = op.last_token_request["code_verifier"][0]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert challenge == params["code_challenge"]
    me = client.get(f"{API}/auth/me").json()
    assert me["authenticated"] and me["email"] == address and me["roles"] == ["viewer"]

    # The same identity signs in to the same account.
    again = TestClient(app)
    params2 = start(again)
    op.next_claims = claims(params2, sub=sub, email=address)
    assert finish(again, op, params2)["signed_in"] == "google"
    assert again.get(f"{API}/auth/me").json()["user_id"] == me["user_id"]


def test_matching_email_is_never_merged(app, op, make_user) -> None:  # noqa: ANN001
    person = make_user()
    client = TestClient(app)
    params = start(client)
    sub = uuid.uuid4().hex
    op.next_claims = claims(params, sub=sub, email=person.email)
    result = finish(client, op, params)
    assert result["path"] == "/sign-in" and result["notice"] == "link_required"
    assert identity_count(sub) == 0
    assert client.get(f"{API}/auth/me").json()["authenticated"] is False


def test_signed_in_user_links_then_signs_in_with_the_identity(app, op, make_user, login) -> None:  # noqa: ANN001
    person = make_user()
    client = login(person)
    params = start(client, intent="link")
    sub = uuid.uuid4().hex
    op.next_claims = claims(params, sub=sub, email=f"other-{sub[:6]}@test.invalid")
    assert finish(client, op, params) == {"path": "/account", "linked": "google"}
    identities = client.get(f"{API}/auth/identities").json()
    assert [i["provider"] for i in identities] == ["google"]

    fresh = TestClient(app)
    p2 = start(fresh)
    op.next_claims = claims(p2, sub=sub, email=f"other-{sub[:6]}@test.invalid")
    assert finish(fresh, op, p2)["signed_in"] == "google"
    assert fresh.get(f"{API}/auth/me").json()["email"] == person.email

    # Another account cannot take over the linked identity.
    intruder = login(make_user())
    p3 = start(intruder, intent="link")
    op.next_claims = claims(p3, sub=sub, email="x@test.invalid")
    assert finish(intruder, op, p3)["error"] == "identity_in_use"


def test_linking_requires_a_signed_in_account(app, op) -> None:  # noqa: ANN001
    r = TestClient(app).get(
        f"{API}/auth/oidc/google/start", params={"intent": "link"}, follow_redirects=False
    )
    assert r.status_code == 401


def test_state_is_single_use_and_bound_to_the_browser(app, op) -> None:  # noqa: ANN001
    client = TestClient(app)
    params = start(client)
    sub = uuid.uuid4().hex
    op.next_claims = claims(params, sub=sub, email=f"s-{sub[:6]}@test.invalid")
    # Another browser (no binding cookie) cannot complete this request...
    stranger = TestClient(app)
    assert finish(stranger, op, params)["error"] == "browser_mismatch"
    # ...and the attempt used up the state, so even the right browser cannot replay it.
    assert finish(client, op, params)["error"] == "invalid_state"
    assert identity_count(sub) == 0


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ("signature", "invalid_id_token"),
        ("audience", "invalid_id_token"),
        ("issuer", "invalid_id_token"),
        ("nonce", "invalid_id_token"),
        ("expired", "invalid_id_token"),
        ("unverified_email", "email_not_verified_by_provider"),
    ],
)
def test_invalid_identity_tokens_are_refused(app, op, tamper: str, expected: str) -> None:  # noqa: ANN001
    client = TestClient(app)
    params = start(client)
    sub = uuid.uuid4().hex
    c = claims(params, sub=sub, email=f"t-{sub[:6]}@test.invalid")
    if tamper == "signature":
        op.sign_with = op.other_key
    elif tamper == "audience":
        c["aud"] = "someone-else"
    elif tamper == "issuer":
        c["iss"] = "https://evil.test"
    elif tamper == "nonce":
        c["nonce"] = "not-the-nonce"
    elif tamper == "expired":
        c["exp"] = int(time.time()) - 3600
        c["iat"] = int(time.time()) - 7200
    elif tamper == "unverified_email":
        c["email_verified"] = False
    op.next_claims = c
    result = finish(client, op, params)
    assert result["path"] == "/sign-in" and result["error"] == expected
    assert identity_count(sub) == 0
    assert client.get(f"{API}/auth/me").json()["authenticated"] is False


def test_microsoft_issuer_is_checked_against_the_tenant(app, op) -> None:  # noqa: ANN001
    client = TestClient(app)
    params = start(client, provider="microsoft")
    sub, tid = uuid.uuid4().hex, str(uuid.uuid4())
    op.next_claims = claims(
        params,
        sub=sub,
        email=f"m-{sub[:6]}@test.invalid",
        iss=f"https://login.microsoftonline.com/{tid}/v2.0",
        tid=tid,
    )
    assert finish(client, op, params, "microsoft")["signed_in"] == "microsoft"

    wrong = TestClient(app)
    p2 = start(wrong, provider="microsoft")
    op.next_claims = claims(
        p2,
        sub=uuid.uuid4().hex,
        email="w@test.invalid",
        iss="https://login.microsoftonline.com/another/v2.0",
        tid=tid,
    )
    assert finish(wrong, op, p2, "microsoft")["error"] == "invalid_id_token"


def test_unconfigured_providers_are_reported_not_faked(anonymous) -> None:  # noqa: ANN001
    assert anonymous.get(f"{API}/auth/providers").json()["oidc"] == {
        "google": False,
        "microsoft": False,
    }
    r = anonymous.get(f"{API}/auth/oidc/google/start", follow_redirects=False)
    assert r.status_code == 404 and r.json()["error"]["code"] == "provider_not_configured"


def test_the_only_sign_in_method_cannot_be_unlinked(app, op) -> None:  # noqa: ANN001
    client = TestClient(app)
    params = start(client)
    sub = uuid.uuid4().hex
    op.next_claims = claims(params, sub=sub, email=f"u-{sub[:6]}@test.invalid")
    finish(client, op, params)
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    [identity] = client.get(f"{API}/auth/identities").json()
    r = client.delete(f"{API}/auth/identities/{identity['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_sign_in_method"
