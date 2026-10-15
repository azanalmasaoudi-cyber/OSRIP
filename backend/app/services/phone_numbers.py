"""Phone number normalization and masking (pure functions, no I/O).

Numbers are stored in E.164 form ("+" country code subscriber number, at most 15
digits). Only Oman, the default, gets a number-plan rule: SMS needs a mobile number,
and Omani mobile numbers are 8 digits beginning with 7 or 9. For other countries the
general E.164 length rules apply and the provider decides whether it can deliver.
"""

from __future__ import annotations

import re

from app.core.errors import unprocessable

# Offered in the interface; Oman first (the default). Any other code is accepted too.
COUNTRY_CODES = (
    "+968",
    "+971",
    "+966",
    "+974",
    "+973",
    "+965",
    "+20",
    "+44",
    "+1",
    "+91",
    "+92",
    "+63",
)
NATIONAL_RULES = {"+968": re.compile(r"^[79]\d{7}$")}
_CODE = re.compile(r"^\+[1-9]\d{0,2}$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize(country_code: str, number: str) -> str:
    """Return the E.164 form, or raise 422 invalid_phone with a message the user can act on."""
    raw = re.sub(r"[\s\-().]", "", number or "")
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if raw.startswith("+"):
        e164 = raw
    else:
        code = (country_code or "").strip()
        if not _CODE.match(code):
            raise unprocessable("invalid_country_code", "Choose a country code.")
        national = raw
        if code != "+968" and national.startswith("0"):
            national = national[1:]  # national trunk prefix (for example 07… in the UK)
        rule = NATIONAL_RULES.get(code)
        if rule is not None and not rule.match(national):
            raise unprocessable(
                "invalid_phone",
                "Enter an Omani mobile number: 8 digits beginning with 7 or 9.",
            )
        e164 = code + national
    if not _E164.match(e164):
        raise unprocessable(
            "invalid_phone", "Enter a mobile number with its country code (8 to 15 digits)."
        )
    for code, rule in NATIONAL_RULES.items():
        if e164.startswith(code) and not rule.match(e164[len(code) :]):
            raise unprocessable(
                "invalid_phone", "Enter an Omani mobile number: 8 digits beginning with 7 or 9."
            )
    return e164


def mask(e164: str | None) -> str | None:
    """'+968 ••••••67': the country code and the last two digits only."""
    if not e164:
        return None
    code = next(
        (c for c in sorted(COUNTRY_CODES, key=len, reverse=True) if e164.startswith(c)), None
    )
    if code is None:
        code = e164[:3]
    rest = e164[len(code) :]
    return f"{code} {'•' * max(len(rest) - 2, 0)}{rest[-2:]}"
