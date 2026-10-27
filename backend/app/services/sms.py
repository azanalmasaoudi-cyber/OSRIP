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
* ``whatsapp``: the Meta WhatsApp Cloud API (``POST /{version}/{phone-number-id}/messages``,
  bearer token), checked against Meta's documentation on 2026-10-27. WhatsApp only
  delivers: OSRIP makes the code, sends it with an authentication template (Meta's preset
  text in Arabic or English, copy-code button) and keeps only a keyed digest of it. In
  ``test`` mode it sends only to the approved test recipients (Meta's free test sender);
  ``production`` is charged per delivered code and stays off until set explicitly.
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
    ``undeliverable`` (accepted but cannot be delivered to this destination),
    ``not_test_recipient`` (a test sender asked to message a number outside its approved
    list) or ``provider_unavailable`` (outage, timeout, authentication failure).
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


# ------------------------------------------------------------------ WhatsApp (Meta Cloud API)

WHATSAPP_URL = "https://graph.facebook.com/{version}/{phone_number_id}/messages"
WHATSAPP_LANGUAGES = {"ar": "ar", "en": "en"}  # template languages created by the setup script
WHATSAPP_CODE_LENGTH = 6
# Meta error codes (https://developers.facebook.com/documentation/business-messaging/whatsapp/
# support/error-codes). 131030: the recipient is not on the test number's allowed list.
# 131021: sender and recipient are the same number. Not deliverable now: 131026 (not on
# WhatsApp, terms not accepted, old client), 131056 (too many messages to this person),
# 131049 (withheld for ecosystem engagement). Anything else (token 190, permissions 10/200,
# template 132000/132001, payment 131042, registration 133010, limits 130429/80007) is a
# configuration or service problem, reported as unavailable with the code in the log.
WHATSAPP_NOT_TEST_RECIPIENT = frozenset({131030})
WHATSAPP_INVALID_NUMBER = frozenset({131021})
WHATSAPP_UNDELIVERABLE = frozenset({131026, 131049, 131056})


def parse_recipients(value: str) -> frozenset[str]:
    """The approved test recipients: comma-separated E.164 numbers (spaces and dashes are
    ignored, anything else that is not ``+`` and 8 to 15 digits is dropped)."""
    numbers = set()
    for raw in value.split(","):
        number = raw.strip().replace(" ", "").replace("-", "")
        if number.startswith("+") and number[1:].isdigit() and 8 <= len(number) - 1 <= 15:
            numbers.add(number)
    return frozenset(numbers)


class WhatsAppProvider:
    """Meta WhatsApp Cloud API with an authentication template (copy-code button).

    WhatsApp only delivers the message, so OSRIP makes the code: six random digits, of which
    only a keyed digest (HMAC with the server's secret key and a per-challenge nonce) is kept
    in the challenge's ``provider_ref``. Expiry, attempts and single use are enforced by
    ``app.services.phone`` as for every provider. In ``test`` mode the code is sent only to
    the approved test recipients, so the free test sender is never asked to message anyone
    else and nothing can be charged; ``production`` mode sends to any number.
    """

    name = "whatsapp"

    def __init__(
        self,
        *,
        token: str,
        phone_number_id: str,
        template: str,
        version: str,
        key: str,
        timeout: float,
        test_recipients: frozenset[str] | None,
    ) -> None:
        self._token = token
        self._url = WHATSAPP_URL.format(version=version, phone_number_id=phone_number_id)
        self._template = template
        self._key = key
        self._timeout = timeout
        self._test_recipients = test_recipients  # None in production mode

    def _digest(self, nonce: str, code: str) -> str:
        return hmac.new(
            self._key.encode(), f"whatsapp-otp:{nonce}:{code}".encode(), hashlib.sha256
        ).hexdigest()

    def request_verification(self, phone_e164: str, locale: str | None = None) -> Started:
        if self._test_recipients is not None and phone_e164 not in self._test_recipients:
            raise DeliveryError("not_test_recipient")
        code = f"{secrets.randbelow(10**WHATSAPP_CODE_LENGTH):0{WHATSAPP_CODE_LENGTH}d}"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_e164.lstrip("+"),
            "type": "template",
            "template": {
                "name": self._template,
                "language": {"code": WHATSAPP_LANGUAGES.get(locale or "", "en")},
                # The code appears twice: in the preset body and in the copy-code button.
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": code}]},
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": "0",
                        "parameters": [{"type": "text", "text": code}],
                    },
                ],
            },
        }
        try:
            with http_client_factory(self._timeout) as client:
                response = client.post(
                    self._url, json=payload, headers={"Authorization": f"Bearer {self._token}"}
                )
        except httpx.HTTPError as exc:
            logger.warning("whatsapp send failed: %s", type(exc).__name__)
            raise DeliveryError("provider_unavailable") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        messages = body.get("messages")
        if response.status_code == 200 and isinstance(messages, list) and messages:
            nonce = secrets.token_urlsafe(12)
            return Started(f"wa1.{nonce}.{self._digest(nonce, code)}")
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        meta_code = error.get("code")
        # The status and Meta's error code only: never the number, the code or the message.
        logger.warning(
            "whatsapp send refused: http %s, code %s, subcode %s",
            response.status_code,
            meta_code,
            error.get("error_subcode"),
        )
        if meta_code in WHATSAPP_NOT_TEST_RECIPIENT:
            raise DeliveryError("not_test_recipient")
        if meta_code in WHATSAPP_INVALID_NUMBER:
            raise DeliveryError("invalid_number")
        if meta_code in WHATSAPP_UNDELIVERABLE:
            raise DeliveryError("undeliverable")
        raise DeliveryError("provider_unavailable")

    def check_verification(self, provider_ref: str, code: str) -> CheckStatus:
        version, _, rest = provider_ref.partition(".")
        nonce, _, digest = rest.partition(".")
        if version != "wa1" or not nonce or not digest:
            return CheckStatus.EXPIRED
        if hmac.compare_digest(digest, self._digest(nonce, code)):
            return CheckStatus.APPROVED
        return CheckStatus.DENIED


def whatsapp_missing() -> list[str]:
    """Names (never values) of the settings the WhatsApp adapter still needs."""
    s = get_settings()
    missing = [] if s.whatsapp_access_token else ["OSRIP_WHATSAPP_ACCESS_TOKEN"]
    if not s.whatsapp_phone_number_id:
        missing.append("OSRIP_WHATSAPP_PHONE_NUMBER_ID")
    if s.whatsapp_mode not in ("test", "production"):
        missing.append("OSRIP_WHATSAPP_MODE (test or production)")
    elif s.whatsapp_mode == "test" and not parse_recipients(s.whatsapp_test_recipients):
        missing.append("OSRIP_WHATSAPP_TEST_RECIPIENTS")
    return missing


def _whatsapp() -> WhatsAppProvider | None:
    s = get_settings()
    if whatsapp_missing():
        return None
    assert s.whatsapp_access_token and s.whatsapp_phone_number_id
    return WhatsAppProvider(
        token=s.whatsapp_access_token.get_secret_value(),
        phone_number_id=s.whatsapp_phone_number_id,
        template=s.whatsapp_template_name,
        version=s.whatsapp_api_version,
        key=s.client_hash_key.get_secret_value(),
        timeout=s.sms_provider_timeout_seconds,
        test_recipients=(
            parse_recipients(s.whatsapp_test_recipients) if s.whatsapp_mode == "test" else None
        ),
    )


# ------------------------------------------------------------------ selection and status


def get_provider() -> SmsProvider | None:
    s = get_settings()
    if not s.sms_enabled:
        return None
    if s.sms_provider == "twilio_verify":
        return _twilio()
    if s.sms_provider == "whatsapp":
        return _whatsapp()
    return _ADAPTERS.get(s.sms_provider)


def status(*, admin: bool = False) -> dict[str, Any]:
    """Secret-free description of SMS availability. The names of missing settings are
    listed only for administrators (service health), never on the public endpoint."""
    s = get_settings()
    missing: list[str] = []
    if not s.sms_enabled:
        state, note = "disabled", "SMS verification is switched off on this server."
    elif s.sms_provider == "whatsapp":
        missing = whatsapp_missing()
        if missing:
            state, note = (
                "not_configured",
                "WhatsApp verification needs its settings on the server.",
            )
        elif s.whatsapp_mode == "test":
            # Real WhatsApp messages, but only to the approved test numbers.
            state = "sandbox"
            note = "WhatsApp test sender: codes reach only the approved test numbers."
        else:
            state, note = "configured", None
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
        "available": state in ("test", "sandbox", "configured"),
        "status": state,
        "channel": "whatsapp" if s.sms_provider == "whatsapp" else "sms",
        "provider": s.sms_provider or None,
        "note": note,
        **({"missing_settings": missing} if admin else {}),
        "default_country": s.sms_default_country,
        "resend_seconds": s.sms_resend_seconds,
        "code_minutes": s.sms_code_minutes,
    }
