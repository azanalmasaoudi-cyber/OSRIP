"""The Twilio Verify adapter without network (httpx.MockTransport): requests follow Twilio's
documentation (checked 2026-10-27), Twilio's error codes become OSRIP's three delivery
errors, checks map to approved / denied / expired, the number and the code are never
logged, and the adapter is offered only when its settings are complete. These are not live
Twilio responses; nothing here shows that SMS delivery to Oman works."""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import sms

SERVICE = "VA" + "0" * 32
NUMBER = "+96891234567"


def _serve(monkeypatch, handler) -> list[httpx.Request]:  # noqa: ANN001
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        sms,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(wrapped)),
    )
    return seen


def _provider() -> sms.TwilioVerifyProvider:
    return sms.TwilioVerifyProvider(
        username="SK" + "1" * 32,
        secret="not-a-real-secret",  # noqa: S106
        service_sid=SERVICE,
        timeout=5,
    )


def _form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_a_verification_is_requested_by_sms_in_the_readers_language(monkeypatch) -> None:  # noqa: ANN001
    seen = _serve(
        monkeypatch,
        lambda r: httpx.Response(
            201, json={"sid": "VE" + "a" * 32, "status": "pending", "channel": "sms"}
        ),
    )
    started = _provider().request_verification(NUMBER, "ar")
    assert started.provider_ref == "VE" + "a" * 32
    request = seen[0]
    assert str(request.url) == f"https://verify.twilio.com/v2/Services/{SERVICE}/Verifications"
    assert _form(request) == {"To": NUMBER, "Channel": "sms", "Locale": "ar"}
    user, _, secret = (
        base64.b64decode(request.headers["authorization"].split()[1]).decode().partition(":")
    )
    assert (user, secret) == ("SK" + "1" * 32, "not-a-real-secret")
    _provider().request_verification(NUMBER, "fr")
    assert "Locale" not in _form(seen[1]), "an unsupported language is left to Twilio's own choice"


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (400, {"code": 60200, "message": "Invalid parameter `To`"}, "invalid_number"),
        (400, {"code": 21614, "message": "not a mobile number"}, "invalid_number"),
        (403, {"code": 60605, "message": "blocked by geo permissions"}, "undeliverable"),
        (429, {"code": 60203, "message": "Max send attempts reached"}, "undeliverable"),
        (429, {"code": 60410, "message": "Fraud Guard"}, "undeliverable"),
        (401, {"code": 20003, "message": "Authenticate"}, "provider_unavailable"),
        (500, {}, "provider_unavailable"),
    ],
)
def test_twilio_errors_become_explained_delivery_errors(
    monkeypatch, caplog, status: int, body: dict[str, Any], error: str
) -> None:  # noqa: ANN001
    _serve(monkeypatch, lambda r: httpx.Response(status, json=body))
    with (
        caplog.at_level(logging.WARNING, logger="osrip.sms"),
        pytest.raises(sms.DeliveryError) as caught,
    ):
        _provider().request_verification(NUMBER, "en")
    assert caught.value.code == error
    assert NUMBER not in caplog.text and "91234567" not in caplog.text, "the number is never logged"


def test_a_timeout_is_not_retried(monkeypatch) -> None:  # noqa: ANN001
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    seen = _serve(monkeypatch, slow)
    with pytest.raises(sms.DeliveryError, match="provider_unavailable"):
        _provider().request_verification(NUMBER)
    assert len(seen) == 1, "a retry could send a second code"


@pytest.mark.parametrize(
    ("status", "body", "result"),
    [
        (200, {"status": "approved"}, sms.CheckStatus.APPROVED),
        (200, {"status": "pending"}, sms.CheckStatus.DENIED),
        (200, {"status": "canceled"}, sms.CheckStatus.EXPIRED),
        (404, {"code": 20404, "message": "not found"}, sms.CheckStatus.EXPIRED),
        (429, {"code": 60202, "message": "Max check attempts reached"}, sms.CheckStatus.EXPIRED),
    ],
)
def test_checks_map_to_approved_denied_or_expired(
    monkeypatch, caplog, status: int, body: dict[str, Any], result: sms.CheckStatus
) -> None:  # noqa: ANN001
    seen = _serve(monkeypatch, lambda r: httpx.Response(status, json=body))
    with caplog.at_level(logging.DEBUG, logger="osrip.sms"):
        assert _provider().check_verification("VE" + "b" * 32, "482913") is result
    assert str(seen[0].url).endswith(f"/Services/{SERVICE}/VerificationCheck")
    assert _form(seen[0]) == {"VerificationSid": "VE" + "b" * 32, "Code": "482913"}
    assert "482913" not in caplog.text, "the code is never logged"


def test_a_failed_check_is_a_provider_error(monkeypatch) -> None:  # noqa: ANN001
    _serve(monkeypatch, lambda r: httpx.Response(503, json={"code": 20503}))
    with pytest.raises(sms.DeliveryError, match="provider_unavailable"):
        _provider().check_verification("VE" + "b" * 32, "123456")


def test_twilio_is_offered_only_with_complete_settings(monkeypatch) -> None:  # noqa: ANN001
    s = get_settings()
    for name, value in (("sms_enabled", True), ("sms_provider", "twilio_verify"), ("twilio_account_sid", None),
                        ("twilio_api_key_sid", None), ("twilio_api_key_secret", None),
                        ("twilio_auth_token", None), ("twilio_verify_service_sid", None)):  # fmt: skip
        monkeypatch.setattr(s, name, value)
    assert sms.get_provider() is None
    public = sms.status()
    assert public["status"] == "not_configured" and public["available"] is False
    assert "missing_settings" not in public, "setting names are for administrators only"
    assert sms.status(admin=True)["missing_settings"] == [
        "OSRIP_TWILIO_VERIFY_SERVICE_SID",
        "OSRIP_TWILIO_API_KEY_SID and OSRIP_TWILIO_API_KEY_SECRET (or OSRIP_TWILIO_ACCOUNT_SID and OSRIP_TWILIO_AUTH_TOKEN)",
    ]
    monkeypatch.setattr(s, "twilio_verify_service_sid", SERVICE)
    monkeypatch.setattr(s, "twilio_account_sid", "AC" + "2" * 32)
    monkeypatch.setattr(s, "twilio_auth_token", SecretStr("not-a-real-token"))
    provider = sms.get_provider()
    assert isinstance(provider, sms.TwilioVerifyProvider) and provider._auth == (
        "AC" + "2" * 32,
        "not-a-real-token",
    )
    assert sms.status()["status"] == "configured"
    monkeypatch.setattr(s, "twilio_api_key_sid", "SK" + "3" * 32)
    monkeypatch.setattr(s, "twilio_api_key_secret", SecretStr("not-a-real-key"))
    assert sms.get_provider()._auth == ("SK" + "3" * 32, "not-a-real-key"), (
        "an API key is preferred"
    )
