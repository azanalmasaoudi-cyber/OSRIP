"""SMS verification providers.

The application talks to a provider through two operations:

* ``request_verification(phone_e164)`` asks the provider to send a code and returns
  the provider's reference for that verification;
* ``check_verification(provider_ref, code)`` asks the provider whether the code is
  right.

The code is generated, delivered and checked by the provider; OSRIP never stores it.
Challenge expiry, attempt limits, resend cooldowns and single use are enforced by
OSRIP as well (``app.services.phone``), whatever the provider does.

Implemented adapters:

* ``test``: scripted delivery for automated tests and local development. Codes are
  kept in process memory and shown only by the development endpoint
  ``GET /dev/sms-outbox``. The API refuses to start with it in production.

No production adapter exists yet, because no SMS provider has been selected for the
project. Adding one means implementing the two operations against that provider's
official documentation and registering it in ``_ADAPTERS``; see docs/INTEGRATIONS.md.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.core.config import get_settings


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

    def request_verification(self, phone_e164: str) -> Started: ...

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

    def request_verification(self, phone_e164: str) -> Started:
        if phone_e164 == TEST_UNDELIVERABLE:
            raise DeliveryError("undeliverable")
        if phone_e164 == TEST_OUTAGE:
            raise DeliveryError("provider_unavailable")
        code = f"{secrets.randbelow(10**self.code_length):0{self.code_length}d}"
        ref = "test_" + secrets.token_urlsafe(18)
        ttl = get_settings().sms_code_minutes * 60
        with self._lock:
            self._pending[ref] = (phone_e164, _digest(code), time.monotonic() + ttl)
            self._outbox.insert(0, {"to": phone_e164, "code": code, "sent_at": time.time()})
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


# ------------------------------------------------------------------ selection and status


def get_provider() -> SmsProvider | None:
    s = get_settings()
    if not s.sms_enabled:
        return None
    return _ADAPTERS.get(s.sms_provider)


def status() -> dict[str, Any]:
    """Public, secret-free description of SMS availability."""
    s = get_settings()
    if not s.sms_enabled:
        state, note = "disabled", "SMS verification is switched off on this server."
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
        "default_country": s.sms_default_country,
        "resend_seconds": s.sms_resend_seconds,
        "code_minutes": s.sms_code_minutes,
    }
