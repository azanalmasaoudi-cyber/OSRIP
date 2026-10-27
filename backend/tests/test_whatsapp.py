"""The WhatsApp Cloud API adapter without network (httpx.MockTransport): the request follows
Meta's documentation for authentication templates (checked 2026-10-27), test mode sends
only to the approved test recipients, Meta's error codes become OSRIP's delivery errors,
only a keyed digest of the code is kept, the number and the code are never logged, and the
adapter is offered only when its settings are complete. These are not live Meta responses;
nothing here shows that WhatsApp delivery works."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import sms

NUMBER = "+96891234567"
TOKEN = "EAAG" + "x" * 60  # noqa: S105 - a fake token
SENT = {"messaging_product": "whatsapp", "contacts": [{"input": "96891234567", "wa_id": "96891234567"}],
        "messages": [{"id": "wamid.HBgLOTY4OTEyMzQ1NjcVAgARGBI", "message_status": "accepted"}]}  # fmt: skip


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


def _provider(recipients: frozenset[str] | None = frozenset({NUMBER})) -> sms.WhatsAppProvider:
    return sms.WhatsAppProvider(
        token=TOKEN,
        phone_number_id="106540352242922",
        template="osrip_verification_code",
        version="v23.0",
        key="test-only-key",
        timeout=5,
        test_recipients=recipients,
    )


def _code(request: httpx.Request) -> str:
    body = json.loads(request.content)
    return body["template"]["components"][0]["parameters"][0]["text"]


def test_the_code_is_sent_with_the_authentication_template_in_the_readers_language(
    monkeypatch,
) -> None:  # noqa: ANN001
    seen = _serve(monkeypatch, lambda r: httpx.Response(200, json=SENT))
    started = _provider().request_verification(NUMBER, "ar")
    request = seen[0]
    assert str(request.url) == "https://graph.facebook.com/v23.0/106540352242922/messages"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    body = json.loads(request.content)
    code = _code(request)
    assert len(code) == 6 and code.isdigit()
    assert body == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "96891234567",
        "type": "template",
        "template": {
            "name": "osrip_verification_code",
            "language": {"code": "ar"},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
                {"type": "button", "sub_type": "url", "index": "0",
                 "parameters": [{"type": "text", "text": code}]},
            ],
        },
    }  # fmt: skip
    assert code not in started.provider_ref, "only a keyed digest of the code is kept"
    _provider().request_verification(NUMBER, None)
    assert json.loads(seen[1].content)["template"]["language"] == {"code": "en"}


def test_test_mode_sends_only_to_approved_recipients(monkeypatch) -> None:  # noqa: ANN001
    seen = _serve(monkeypatch, lambda r: httpx.Response(200, json=SENT))
    with pytest.raises(sms.DeliveryError, match="not_test_recipient"):
        _provider().request_verification("+96899999999", "en")
    assert seen == [], "Meta is not even asked"
    _provider(recipients=None).request_verification("+96899999999", "en")  # production mode
    assert len(seen) == 1


def test_the_code_checks_against_its_own_challenge_only(monkeypatch) -> None:  # noqa: ANN001
    seen = _serve(monkeypatch, lambda r: httpx.Response(200, json=SENT))
    provider = _provider()
    first = provider.request_verification(NUMBER, "en").provider_ref
    second = provider.request_verification(NUMBER, "en").provider_ref
    code1, code2 = _code(seen[0]), _code(seen[1])
    assert provider.check_verification(first, code1) is sms.CheckStatus.APPROVED
    if code1 != code2:
        assert provider.check_verification(second, code1) is sms.CheckStatus.DENIED
    assert provider.check_verification(first, f"{(int(code1) + 1) % 10**6:06d}") is (
        sms.CheckStatus.DENIED
    )
    assert provider.check_verification("VE123", code1) is sms.CheckStatus.EXPIRED
    other_key = sms.WhatsAppProvider(
        token=TOKEN, phone_number_id="1", template="t", version="v23.0", key="another-key",
        timeout=5, test_recipients=None,
    )  # fmt: skip
    assert other_key.check_verification(first, code1) is sms.CheckStatus.DENIED, (
        "the stored digest is useless without the server's key"
    )


@pytest.mark.parametrize(
    ("status", "error", "result"),
    [
        (400, {"code": 131030, "message": "Recipient phone number not in allowed list"}, "not_test_recipient"),
        (400, {"code": 131021, "message": "Recipient cannot be sender"}, "invalid_number"),
        (400, {"code": 131026, "message": "Message undeliverable"}, "undeliverable"),
        (400, {"code": 131056, "message": "Pair rate limit hit"}, "undeliverable"),
        (401, {"code": 190, "message": "Error validating access token"}, "provider_unavailable"),
        (404, {"code": 132001, "message": "Template name does not exist"}, "provider_unavailable"),
        (400, {"code": 131042, "message": "Business eligibility payment issue"}, "provider_unavailable"),
        (500, {}, "provider_unavailable"),
    ],
)  # fmt: skip
def test_meta_errors_become_explained_delivery_errors(
    monkeypatch, caplog, status: int, error: dict[str, Any], result: str
) -> None:  # noqa: ANN001
    _serve(monkeypatch, lambda r: httpx.Response(status, json={"error": error} if error else {}))
    with (
        caplog.at_level(logging.WARNING, logger="osrip.sms"),
        pytest.raises(sms.DeliveryError) as caught,
    ):
        _provider().request_verification(NUMBER, "en")
    assert caught.value.code == result
    assert "91234567" not in caplog.text, "the number is never logged"
    assert TOKEN not in caplog.text
    if error:
        assert str(error["code"]) in caplog.text, "Meta's code is logged for the administrator"


def test_a_timeout_is_not_retried_and_the_code_is_never_logged(monkeypatch, caplog) -> None:  # noqa: ANN001
    codes: list[str] = []

    def slow(request: httpx.Request) -> httpx.Response:
        codes.append(_code(request))
        raise httpx.ReadTimeout("slow", request=request)

    with caplog.at_level(logging.DEBUG, logger="osrip.sms"):
        _serve(monkeypatch, slow)
        with pytest.raises(sms.DeliveryError, match="provider_unavailable"):
            _provider().request_verification(NUMBER)
    assert len(codes) == 1, "a retry could send a second code"
    assert codes[0] not in caplog.text


def test_recipient_list_parsing() -> None:
    assert sms.parse_recipients(" +968 9123 4567, +968-7123-4567 ,9123,+12, ,abc") == {
        "+96891234567",
        "+96871234567",
    }


def _settings(monkeypatch, **values: Any) -> None:  # noqa: ANN001
    s = get_settings()
    base = {"sms_enabled": True, "sms_provider": "whatsapp", "whatsapp_mode": "test",
            "whatsapp_access_token": None, "whatsapp_phone_number_id": None,
            "whatsapp_test_recipients": ""}  # fmt: skip
    for name, value in {**base, **values}.items():
        monkeypatch.setattr(s, name, value)


def test_whatsapp_is_offered_only_with_complete_settings(monkeypatch) -> None:  # noqa: ANN001
    _settings(monkeypatch)
    assert sms.get_provider() is None
    public = sms.status()
    assert (public["status"], public["available"], public["channel"]) == (
        "not_configured", False, "whatsapp",
    )  # fmt: skip
    assert "missing_settings" not in public
    assert sms.status(admin=True)["missing_settings"] == [
        "OSRIP_WHATSAPP_ACCESS_TOKEN",
        "OSRIP_WHATSAPP_PHONE_NUMBER_ID",
        "OSRIP_WHATSAPP_TEST_RECIPIENTS",
    ]
    _settings(monkeypatch, whatsapp_access_token=SecretStr(TOKEN),
              whatsapp_phone_number_id="106540352242922", whatsapp_test_recipients=NUMBER)  # fmt: skip
    provider = sms.get_provider()
    assert isinstance(provider, sms.WhatsAppProvider)
    assert provider._test_recipients == {NUMBER}
    sandbox = sms.status()
    assert (sandbox["status"], sandbox["available"]) == ("sandbox", True)
    assert NUMBER not in json.dumps(sandbox), "the test numbers are never published"


def test_production_mode_is_explicit_and_has_no_recipient_list(monkeypatch) -> None:  # noqa: ANN001
    _settings(monkeypatch, whatsapp_access_token=SecretStr(TOKEN),
              whatsapp_phone_number_id="106540352242922", whatsapp_mode="production")  # fmt: skip
    provider = sms.get_provider()
    assert isinstance(provider, sms.WhatsAppProvider) and provider._test_recipients is None
    assert sms.status()["status"] == "configured"
    _settings(monkeypatch, whatsapp_access_token=SecretStr(TOKEN),
              whatsapp_phone_number_id="106540352242922", whatsapp_mode="live")  # fmt: skip
    assert sms.get_provider() is None, "an unknown mode is not treated as production"
    assert "OSRIP_WHATSAPP_MODE (test or production)" in sms.status(admin=True)["missing_settings"]
