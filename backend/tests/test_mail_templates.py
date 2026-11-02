"""Account e-mails: both languages in every message with the reader's first, the Arabic part
right to left, escaped values, the link in the button and as plain text, and nothing that
loads or runs (no scripts, images or tracking)."""

from __future__ import annotations

import pytest

from app.services import mail_templates
from app.services.identity import mask_email

VALUES = {
    "name": "Sara",
    "hours": 24,
    "minutes": 30,
    "address": "s•••@example.com",
    "phone": "+968 •••• 4567",
}
LINK = "https://osrip.example/verify-email?token=abc_DEF-123"


@pytest.mark.parametrize("kind", sorted(mail_templates.TEXTS))
@pytest.mark.parametrize("language", ["en", "ar"])
def test_every_message_has_both_languages_with_the_readers_first(kind: str, language: str) -> None:
    message = mail_templates.render(kind, language, link=LINK, **VALUES)
    en, ar = mail_templates.TEXTS[kind]["en"], mail_templates.TEXTS[kind]["ar"]
    first, second = (ar, en) if language == "ar" else (en, ar)
    assert message.subject == f"{first['subject']} / {second['subject']}"
    assert message.text.index(first["title"]) < message.text.index(second["title"])
    body = message.html.split("<body", 1)[1]  # the head's <title> holds the bilingual subject
    assert body.index(first["title"]) < body.index(second["title"])
    assert 'dir="rtl" lang="ar"' in message.html and 'dir="ltr" lang="en"' in message.html
    assert message.text.count(LINK) == 2 and LINK in message.html
    lower = message.html.lower()
    assert "<script" not in lower and "<img" not in lower and "javascript:" not in lower
    assert "{" not in message.text, "every value is filled in"


def test_values_are_escaped_in_html() -> None:
    message = mail_templates.render(
        "verify_email", "en", link=LINK, name='<b onclick="x">Eve</b>', hours=24
    )
    assert (
        "<b onclick" not in message.html
        and "&lt;b onclick=&quot;x&quot;&gt;Eve&lt;/b&gt;" in message.html
    )
    assert '<b onclick="x">Eve</b>' in message.text, "plain text is shown as text"


def test_a_message_without_a_link_has_no_button() -> None:
    message = mail_templates.render("account_exists", "en")
    assert "<a href" not in message.html


def test_addresses_are_masked_for_notices() -> None:
    assert mask_email("sara.alharthi@example.com") == "s•••@example.com"
    assert mask_email("not-an-address") == "•••"
