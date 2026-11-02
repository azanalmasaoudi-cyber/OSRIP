"""Phone registration through the API with the WhatsApp adapter in test mode, Meta's API
replaced by httpx.MockTransport: the code reaches only an approved test number, works once,
wrong codes count, and the database holds a keyed digest, never the code. Nothing here
reaches Meta or shows that WhatsApp delivery works."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import select

from tests.test_phone_integration import number, request_code, wrong
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture
def whatsapp(database_url: str, monkeypatch) -> Iterator[tuple[str, list[httpx.Request]]]:  # noqa: ANN001
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.services import sms

    approved = number()
    for name, value in {
        "OSRIP_SMS_ENABLED": "true",
        "OSRIP_SMS_PROVIDER": "whatsapp",
        "OSRIP_SMS_RESEND_SECONDS": "0",
        # Earlier tests send codes from the same test client within the hour.
        "OSRIP_SMS_PER_NUMBER_HOUR": "50",
        "OSRIP_SMS_PER_CLIENT_HOUR": "500",
        "OSRIP_WHATSAPP_MODE": "test",
        "OSRIP_WHATSAPP_ACCESS_TOKEN": "EAAG" + "y" * 60,
        "OSRIP_WHATSAPP_PHONE_NUMBER_ID": "106540352242922",
        "OSRIP_WHATSAPP_TEST_RECIPIENTS": f"+968{approved}",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    ratelimit.reset()
    seen: list[httpx.Request] = []

    def meta(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"messaging_product": "whatsapp",
                                         "messages": [{"id": "wamid.test"}]})  # fmt: skip

    monkeypatch.setattr(
        sms,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(meta)),
    )
    yield approved, seen
    monkeypatch.undo()
    get_settings.cache_clear()
    ratelimit.reset()


def sent_code(request: httpx.Request) -> str:
    return json.loads(request.content)["template"]["components"][0]["parameters"][0]["text"]


def test_registration_by_whatsapp_in_test_mode(anonymous, whatsapp) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.models import PhoneChallenge

    approved, seen = whatsapp
    providers = anonymous.get(f"{API}/auth/providers").json()["sms"]
    assert (providers["status"], providers["channel"]) == ("sandbox", "whatsapp")

    refused = request_code(anonymous, number())
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "sms_not_test_recipient"
    assert seen == [], "a number outside the approved list never reaches Meta"

    r = anonymous.post(
        f"{API}/auth/phone/request",
        json={"country_code": "+968", "number": approved, "language": "ar"},
    )
    assert r.status_code == 202, r.text
    code = sent_code(seen[0])
    assert json.loads(seen[0].content)["template"]["language"] == {"code": "ar"}
    assert code not in r.text, "the code never travels to the browser"
    with session_factory()() as s:
        ref = s.scalar(
            select(PhoneChallenge.provider_ref).where(PhoneChallenge.id == r.json()["challenge_id"])
        )
    assert ref and ref.startswith("wa1.") and code not in ref

    challenge = r.json()["challenge_id"]
    bad = anonymous.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": wrong(code)}
    )
    assert bad.status_code == 400 and bad.json()["error"]["details"]["attempts_left"] == 4
    ok = anonymous.post(
        f"{API}/auth/phone/verify",
        json={"challenge_id": challenge, "code": code, "display_name": "Demo"},
    )
    assert ok.status_code == 200 and ok.json()["status"] == "registered"
    assert ok.json()["me"]["phone"] == f"+968 ••••••{approved[-2:]}"
    anonymous.headers["X-CSRF-Token"] = anonymous.cookies["osrip_csrf"]  # now signed in
    replay = anonymous.post(
        f"{API}/auth/phone/verify", json={"challenge_id": challenge, "code": code}
    )
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "sms_challenge_invalid", "a code works once"
