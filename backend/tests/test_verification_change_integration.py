"""Changing a confirmed e-mail address or a verified phone number, with the development mail
outbox and the scripted SMS provider: the current password (or a recent sign-in for an
account without one) is required, the new address or number is stored only after it is
proved, the previous address is told, messages are bilingual with the reader's language
first, and nothing is moved between accounts."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text

from tests.test_identity_integration import PASSWORD, email, last_token, outbox_count
from tests.test_phone_integration import code_for, number, request_code, sms_on  # noqa: F401
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_limits() -> Iterator[None]:
    from app.core import ratelimit

    ratelimit.reset()
    yield
    ratelimit.reset()  # the limit test fills them up


def last_message(address: str, purpose: str) -> tuple[str, str]:
    from app.db.session import session_factory
    from app.models import EmailOutbox

    with session_factory()() as s, s.begin():
        row = s.execute(
            select(EmailOutbox.subject, EmailOutbox.body_text)
            .where(EmailOutbox.to_address == address, EmailOutbox.purpose == purpose)
            .order_by(EmailOutbox.id.desc())
            .limit(1)
        ).first()
    assert row is not None, f"no {purpose} message for {address}"
    return row.subject, row.body_text


def audited(user_id: uuid.UUID, action: str) -> list[str]:
    from app.db.session import session_factory
    from app.models import AuditEvent

    with session_factory()() as s, s.begin():
        return list(
            s.scalars(
                select(AuditEvent.outcome)
                .where(AuditEvent.actor_id == user_id, AuditEvent.action == action)
                .order_by(AuditEvent.id)
            )
        )


def test_changing_a_confirmed_address_needs_the_password_and_tells_the_old_one(
    make_user, login, anonymous
) -> None:  # noqa: ANN001
    person = make_user()
    client = login(person)
    new = email()

    wrong = client.post(f"{API}/auth/email/link", json={"email": new, "password": "not-it"})
    assert wrong.status_code == 403 and wrong.json()["error"]["code"] == "wrong_current_password"
    missing = client.post(f"{API}/auth/email/link", json={"email": new})
    assert missing.status_code == 403
    assert audited(person.id, "auth.email.change") == ["denied", "denied"]
    same = client.post(
        f"{API}/auth/email/link", json={"email": person.email, "password": person.password}
    )
    assert same.status_code == 409 and same.json()["error"]["code"] == "email_unchanged"

    asked = client.post(
        f"{API}/auth/email/link", json={"email": new, "password": person.password, "language": "ar"}
    )
    assert asked.status_code == 202
    subject, body = last_message(new, "change_email")
    assert subject.startswith("تأكيد بريدك الإلكتروني الجديد في OSRIP / Confirm your new OSRIP")
    assert body.index("تأكيد بريدك الإلكتروني الجديد") < body.index(
        "Confirm your new e-mail address"
    )
    assert client.get(f"{API}/auth/me").json()["email"] == person.email, "nothing changes yet"

    # The link works from any browser (it proves the new address), once.
    token = last_token(new, "change_email")  # the message kind; the token is a link_email token
    done = anonymous.post(f"{API}/auth/email/link/confirm", json={"token": token, "language": "ar"})
    assert done.status_code == 200 and done.json() == {"status": "changed"}
    assert (
        anonymous.post(f"{API}/auth/email/link/confirm", json={"token": token}).status_code == 400
    )
    me = client.get(f"{API}/auth/me").json()
    assert (me["email"], me["email_verified"]) == (new, True)

    _, notice = last_message(person.email, "email_changed")
    assert f"{new[0]}•••@test.invalid" in notice and new not in notice, (
        "the old address sees it masked"
    )
    assert "/forgot-password" in notice
    signed = anonymous.post(f"{API}/auth/login", json={"email": new, "password": person.password})
    assert signed.status_code == 200
    assert audited(person.id, "auth.email.change") == ["denied", "denied", "success"]


def test_an_address_of_another_account_is_never_taken(make_user, login) -> None:  # noqa: ANN001
    owner, other = make_user(), make_user()
    client = login(other)
    before = outbox_count(owner.email)
    r = client.post(
        f"{API}/auth/email/link", json={"email": owner.email, "password": other.password}
    )
    assert r.status_code == 202, "the same answer as for a free address"
    assert outbox_count(owner.email) == before + 1, "the owner is told instead"
    assert last_message(owner.email, "account_exists")[0].startswith(
        "OSRIP: an account already exists"
    )


@pytest.mark.usefixtures("sms_on")
def test_without_a_password_a_recent_sign_in_is_needed(anonymous, db) -> None:  # noqa: ANN001
    national = number()
    request = request_code(anonymous, national).json()
    signed = anonymous.post(
        f"{API}/auth/phone/verify",
        json={"challenge_id": request["challenge_id"], "code": code_for(national)},
    )
    assert signed.status_code == 200 and signed.json()["status"] == "registered"
    anonymous.headers["X-CSRF-Token"] = anonymous.cookies["osrip_csrf"]
    first = email()
    assert anonymous.post(f"{API}/auth/email/link", json={"email": first}).status_code == 202
    token = last_token(first, "link_email")
    linked = anonymous.post(f"{API}/auth/email/link/confirm", json={"token": token})
    assert linked.json() == {"status": "linked"}

    # Changing that confirmed address: fine within the re-authentication window ...
    assert anonymous.post(f"{API}/auth/email/link", json={"email": email()}).status_code == 202
    # ... refused once the session is older than it.
    db.execute(
        text("UPDATE user_session SET created_at = now() - interval '30 minutes' "
             "WHERE user_id = (SELECT id FROM app_user WHERE email = :e)"),
        {"e": first},
    )  # fmt: skip
    db.commit()
    late = anonymous.post(f"{API}/auth/email/link", json={"email": email()})
    assert late.status_code == 403 and late.json()["error"]["code"] == "reauthentication_required"


@pytest.mark.usefixtures("sms_on")
def test_changing_a_verified_number_needs_the_password_and_tells_the_address(
    make_user, login
) -> None:  # noqa: ANN001, F811
    person = make_user()
    client = login(person)
    first, second = number(), number()
    linked = client.post(
        f"{API}/auth/phone/request",
        json={"country_code": "+968", "number": first, "purpose": "link"},
    ).json()
    done = client.post(
        f"{API}/auth/phone/verify",
        json={"challenge_id": linked["challenge_id"], "code": code_for(first)},
    )
    assert done.json()["status"] == "linked"

    refused = client.post(
        f"{API}/auth/phone/request",
        json={"country_code": "+968", "number": second, "purpose": "link"},
    )
    assert (
        refused.status_code == 403 and refused.json()["error"]["code"] == "wrong_current_password"
    )
    asked = client.post(
        f"{API}/auth/phone/request",
        json={"country_code": "+968", "number": second, "purpose": "link",
              "password": person.password, "language": "ar"},
    )  # fmt: skip
    assert asked.status_code == 202
    from app.services import sms

    sent = next(m for m in sms.scripted_provider().outbox() if m["to"] == f"+968{second}")
    assert sent["locale"] == "ar", "the code is requested in the reader's language"
    changed = client.post(
        f"{API}/auth/phone/verify",
        json={
            "challenge_id": asked.json()["challenge_id"],
            "code": code_for(second),
            "language": "ar",
        },
    )
    assert changed.status_code == 200 and changed.json()["status"] == "changed"
    me = client.get(f"{API}/auth/me").json()
    assert me["phone"].endswith(second[-2:])
    subject, body = last_message(person.email, "phone_changed")
    assert subject.startswith("تغيّر رقم هاتفك في OSRIP")
    assert second not in body and f"+968{second}" not in body, "the number appears masked only"
    assert audited(person.id, "auth.phone.change") == ["denied", "success"]


def test_messages_are_sent_in_html_and_text_with_smtp(make_user, login, monkeypatch) -> None:  # noqa: ANN001
    import smtplib

    from app.core.config import get_settings

    sent = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):  # noqa: ANN001
            self.host = host

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *exc):  # noqa: ANN002, ANN204
            return False

        def starttls(self) -> None: ...

        def login(self, user, password) -> None: ...  # noqa: ANN001

        def send_message(self, message) -> None:  # noqa: ANN001
            sent.append(message)

    s = get_settings()
    monkeypatch.setattr(s, "email_backend", "smtp")
    monkeypatch.setattr(s, "smtp_host", "smtp.test.invalid")
    monkeypatch.setattr(s, "smtp_from", "OSRIP <no-reply@test.invalid>")
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    address = email()
    r = login(make_user()).post(f"{API}/auth/password/forgot", json={"email": address})
    assert r.status_code == 202 and sent == [], "an unknown address gets no message"
    person = make_user()
    r = login(person).post(
        f"{API}/auth/password/forgot", json={"email": person.email, "language": "ar"}
    )
    assert r.status_code == 202 and len(sent) == 1
    message = sent[0]
    assert message.is_multipart() and [p.get_content_type() for p in message.iter_parts()] == [
        "text/plain", "text/html",
    ]  # fmt: skip
    html = message.get_body(("html",)).get_content()
    assert 'dir="rtl" lang="ar"' in html and "/reset-password?token=" in html
    assert "<script" not in html.lower() and "<img" not in html.lower()
    assert PASSWORD not in html


@pytest.mark.usefixtures("sms_on")
def test_the_per_address_guard_follows_the_configured_sms_limit(anonymous, monkeypatch) -> None:  # noqa: ANN001
    # Invalid numbers are refused before any SMS, yet still count against the address.
    from app.core.config import get_settings

    def burst(n: int) -> list[int]:
        return [
            anonymous.post(
                f"{API}/auth/phone/request", json={"country_code": "+968", "number": "1234"}
            ).status_code
            for _ in range(n)
        ]

    monkeypatch.setattr(get_settings(), "sms_per_client_hour", 10)  # the default
    assert burst(21)[-2:] == [422, 429], "20 per hour with the default settings"
    from app.core import ratelimit

    ratelimit.reset()
    monkeypatch.setattr(get_settings(), "sms_per_client_hour", 30)
    assert burst(31)[-2:] == [422, 429], "raised together with the SMS limit"
