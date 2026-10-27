"""SMS verification providers.

The application talks to a provider through two operations:

* ``request_verification(phone_e164, locale)`` asks the provider to send a code (in the
  person's language when the provider supports it) and returns the provider's reference
  for that verification;
* ``check_verification(provider_ref, code)`` asks the provider whether the code is
  right.

The code is generated, delivered and checked by the provider; OSRIP never stores it.
Challenge expiry, attempt limits, resend cooldowns and single use are enforced by
OSRIP as well (``app.services.phone``), whatever the provider does.

Implemented adapters:

* ``twilio_verify``: the Twilio Verify API v2, written from Twilio's documentation
  (checked 2026-10-27): ``POST /v2/Services/{VA...}/Verifications`` with ``To``,
  ``Channel=sms`` and ``Locale`` (``ar`` or ``en``), and ``POST .../VerificationCheck``
  with ``VerificationSid`` and ``Code``. HTTP Basic authentication with an API key (SID
  and secret) or the Account SID and Auth Token. One attempt per call, no automatic retry
  (a retry could send a second code), with the configured timeout. Twilio deletes a
  verification once it is approved, expires (10 minutes) or reaches its check limit; a
  check then answers 404, which is reported as expired. Twilio's error codes are mapped to
  the three errors below; the number and the code are never logged.
* ``test``: scripted delivery for automated tests and local development. Codes are
  kept in process memory and shown only by the development endpoint
  ``GET /dev/sms-outbox``. The API refuses to start with it in production.

Delivery to Oman needs a pre-registered alphanumeric sender ID (see docs/INTEGRATIONS.md);
no delivery is reported as working until it has been tested with a real phone.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger("osrip.sms")
LOCALES = ("ar", "en")


class CheckStatus(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"  # wrong code
    EXPIRED = "expired"  # the provider no longer accepts this verification


class DeliveryError(Exception):
    """The provider could not deliver or check a code.

    ``code`` is one of: ``invalid_number`` (the provider rejects the number),
    ``undeliverable`` (accepted but cannot be delivered to this destination) or
    ``provider_unavailable`` (outage, timeout, authentication failure).
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Started:
    provider_ref: str


class SmsProvider(Protocol):
    name: str

    def request_verification(self, phone_e164: str, locale: str | None = None) -> Started: ...

    def check_verification(self, provider_ref: str, code: str) -> CheckStatus: ...


# ------------------------------------------------------------------ test provider


# Documented test numbers (Oman format, never real subscribers in this project's tests).
TEST_UNDELIVERABLE = "+96890000000"
TEST_OUTAGE = "+96890000001"


class ScriptedSmsProvider:
    """In-memory provider for automated tests. Never used in production."""

    name = "test"
    code_length = 6

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[str, str, float]] = {}  # ref -> (phone, digest, expires)
        self._outbox: list[dict[str, Any]] = []

    def request_verification(self, phone_e164: str, locale: str | None = None) -> Started:
        if phone_e164 == TEST_UNDELIVERABLE:
            raise DeliveryError("undeliverable")
        if phone_e164 == TEST_OUTAGE:
            raise DeliveryError("provider_unavailable")
        code = f"{secrets.randbelow(10**self.code_length):0{self.code_length}d}"
        ref = "test_" + secrets.token_urlsafe(18)
        ttl = get_settings().sms_code_minutes * 60
        with self._lock:
            self._pending[ref] = (phone_e164, _digest(code), time.monotonic() + ttl)
            self._outbox.insert(
                0, {"to": phone_e164, "code": code, "locale": locale, "sent_at": time.time()}
            )
            del self._outbox[50:]
        return Started(ref)

    def check_verification(self, provider_ref: str, code: str) -> CheckStatus:
        with self._lock:
            entry = self._pending.get(provider_ref)
            if entry is None:
                return CheckStatus.EXPIRED
            _phone, digest, expires = entry
            if time.monotonic() >= expires:
                self._pending.pop(provider_ref, None)
                return CheckStatus.EXPIRED
            if not hmac.compare_digest(digest, _digest(code)):
                return CheckStatus.DENIED
            self._pending.pop(provider_ref, None)  # a provider-side code works once
            return CheckStatus.APPROVED

    def outbox(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(m) for m in self._outbox]

    def reset(self) -> None:
        with self._lock:
            self._pending.clear()
            self._outbox.clear()


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


_test_provider = ScriptedSmsProvider()
_ADAPTERS: dict[str, SmsProvider] = {"test": _test_provider}


def scripted_provider() -> ScriptedSmsProvider:
    return _test_provider


# ------------------------------------------------------------------ Twilio Verify

TWILIO_VERIFY_URL = "https://verify.twilio.com/v2/Services/{service}/{resource}"
# Twilio error codes (https://www.twilio.com/docs/api/errors). Invalid destination:
# 21211 invalid "To" number, 21614 not a mobile number, 60200 invalid parameter, 60205
# SMS not supported by this landline. Not deliverable now: 60203 max send attempts (429),
# 60410 delivery blocked by Fraud Guard for 12 hours, 60605 blocked by Verify geo
# permissions (403), 21408 region not enabled, 21610 the recipient opted out.
TWILIO_INVALID_NUMBER = frozenset({21211, 21614, 60200, 60205})
TWILIO_UNDELIVERABLE = frozenset({21408, 21610, 60203, 60410, 60605})
TWILIO_MAX_CHECKS = 60202  # max check attempts reached: the verification cannot succeed

# Injectable for tests (httpx.MockTransport; nothing reaches Twilio).
http_client_factory: Callable[[float], httpx.Client] = lambda timeout: httpx.Client(timeout=timeout)  # noqa: E731


class TwilioVerifyProvider:
    """Twilio Verify API v2 (SMS channel). The code is generated, sent and checked by Twilio."""

    name = "twilio_verify"

    def __init__(self, *, username: str, secret: str, service_sid: str, timeout: float) -> None:
        self._auth = (username, secret)
        self._service = service_sid
        self._timeout = timeout

    def _post(self, resource: str, data: dict[str, str]) -> tuple[int, dict[str, Any]]:
        url = TWILIO_VERIFY_URL.format(service=self._service, resource=resource)
        try:
            with http_client_factory(self._timeout) as client:
                response = client.post(url, data=data, auth=self._auth)
        except httpx.HTTPError as exc:
            logger.warning("twilio verify %s failed: %s", resource, type(exc).__name__)
            raise DeliveryError("provider_unavailable") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        return response.status_code, body if isinstance(body, dict) else {}

    def request_verification(self, phone_e164: str, locale: str | None = None) -> Started:
        data = {"To": phone_e164, "Channel": "sms"}
        if locale in LOCALES:
            data["Locale"] = locale
        status, body = self._post("Verifications", data)
        sid = str(body.get("sid") or "")
        if status in (200, 201) and sid.startswith("VE"):
            return Started(sid)
        code = body.get("code")
        # The status and Twilio's error code only: never the number, never the message.
        logger.warning("twilio verify request refused: http %s, code %s", status, code)
        if code in TWILIO_INVALID_NUMBER:
            raise DeliveryError("invalid_number")
        if code in TWILIO_UNDELIVERABLE:
            raise DeliveryError("undeliverable")
        raise DeliveryError("provider_unavailable")

    def check_verification(self, provider_ref: str, code: str) -> CheckStatus:
        data = {"VerificationSid": provider_ref, "Code": code}
        status, body = self._post("VerificationCheck", data)
        if status == 404:  # deleted after approval, expiry or the check limit
            return CheckStatus.EXPIRED
        if status in (200, 201):
            result = body.get("status")
            if result == "approved":
                return CheckStatus.APPROVED
            if result == "pending":  # wrong code; the verification stays open
                return CheckStatus.DENIED
            return CheckStatus.EXPIRED  # canceled, expired, max_attempts_reached, failed, deleted
        if body.get("code") == TWILIO_MAX_CHECKS:
            return CheckStatus.EXPIRED
        logger.warning("twilio verify check refused: http %s, code %s", status, body.get("code"))
        raise DeliveryError("provider_unavailable")


def twilio_missing() -> list[str]:
    """Names (never values) of the settings Twilio Verify still needs."""
    s = get_settings()
    missing = [] if s.twilio_verify_service_sid else ["OSRIP_TWILIO_VERIFY_SERVICE_SID"]
    has_key = bool(s.twilio_api_key_sid and s.twilio_api_key_secret)
    has_token = bool(s.twilio_account_sid and s.twilio_auth_token)
    if not (has_key or has_token):
        missing.append(
            "OSRIP_TWILIO_API_KEY_SID and OSRIP_TWILIO_API_KEY_SECRET "
            "(or OSRIP_TWILIO_ACCOUNT_SID and OSRIP_TWILIO_AUTH_TOKEN)"
        )
    return missing


def _twilio() -> TwilioVerifyProvider | None:
    s = get_settings()
    if twilio_missing():
        return None
    if s.twilio_api_key_sid and s.twilio_api_key_secret:
        username, secret = s.twilio_api_key_sid, s.twilio_api_key_secret.get_secret_value()
    else:
        assert s.twilio_account_sid and s.twilio_auth_token
        username, secret = s.twilio_account_sid, s.twilio_auth_token.get_secret_value()
    return TwilioVerifyProvider(
        username=username,
        secret=secret,
        service_sid=s.twilio_verify_service_sid or "",
        timeout=s.sms_provider_timeout_seconds,
    )


# ------------------------------------------------------------------ selection and status


def get_provider() -> SmsProvider | None:
    s = get_settings()
    if not s.sms_enabled:
        return None
    if s.sms_provider == "twilio_verify":
        return _twilio()
    return _ADAPTERS.get(s.sms_provider)


def status(*, admin: bool = False) -> dict[str, Any]:
    """Secret-free description of SMS availability. The names of missing settings are
    listed only for administrators (service health), never on the public endpoint."""
    s = get_settings()
    missing: list[str] = []
    if not s.sms_enabled:
        state, note = "disabled", "SMS verification is switched off on this server."
    elif s.sms_provider == "twilio_verify":
        missing = twilio_missing()
        if missing:
            state, note = "not_configured", "Twilio Verify needs its settings on the server."
        else:
            state, note = "configured", None
    elif s.sms_provider not in _ADAPTERS:
        state = "not_configured"
        note = (
            "No SMS provider adapter is configured."
            if not s.sms_provider
            else f"No adapter exists for the SMS provider '{s.sms_provider}'."
        )
    elif s.sms_provider == "test":
        state, note = "test", "Test delivery: codes are not sent to real phones."
    else:
        state, note = "configured", None
    return {
        "available": state in ("test", "configured"),
        "status": state,
        "provider": s.sms_provider or None,
        "note": note,
        **({"missing_settings": missing} if admin else {}),
        "default_country": s.sms_default_country,
        "resend_seconds": s.sms_resend_seconds,
        "code_minutes": s.sms_code_minutes,
    }
