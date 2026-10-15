"""Phone number normalization and masking; the scripted SMS provider (pure, no database)."""

from __future__ import annotations

import pytest

from app.core.errors import ApiError
from app.services import phone_numbers, sms


@pytest.mark.parametrize(
    ("code", "number", "expected"),
    [
        ("+968", "9123 4567", "+96891234567"),
        ("+968", "7123-4567", "+96871234567"),
        ("+971", "+96891234567", "+96891234567"),  # a full international number wins
        ("+968", "0096891234567", "+96891234567"),
        ("+44", "07911 123456", "+447911123456"),  # national trunk 0 removed
        ("+1", "(202) 555-0123", "+12025550123"),
    ],
)
def test_normalize_to_e164(code: str, number: str, expected: str) -> None:
    assert phone_numbers.normalize(code, number) == expected


@pytest.mark.parametrize(
    ("code", "number"),
    [
        ("+968", "24123456"),  # Omani landline: cannot receive SMS
        ("+968", "9123456"),  # 7 digits
        ("+968", "912345678"),  # 9 digits
        ("+968", "+96824123456"),  # landline written internationally
        ("+44", "12"),
        ("968", "91234567"),  # country code without "+"
        ("+968", "abcdefgh"),
    ],
)
def test_invalid_numbers_are_refused(code: str, number: str) -> None:
    with pytest.raises(ApiError) as err:
        phone_numbers.normalize(code, number)
    assert err.value.status_code == 422


def test_mask_shows_only_country_code_and_last_two_digits() -> None:
    assert phone_numbers.mask("+96891234567") == "+968 ••••••67"
    assert phone_numbers.mask("+447911123456") == "+44 ••••••••56"
    assert phone_numbers.mask(None) is None


def test_scripted_provider_codes_are_single_use_and_checked_exactly() -> None:
    p = sms.ScriptedSmsProvider()
    started = p.request_verification("+96891234567")
    code = p.outbox()[0]["code"]
    assert len(code) == 6 and code.isdigit()
    wrong = "0" * 6 if code != "0" * 6 else "1" * 6
    assert p.check_verification(started.provider_ref, wrong) is sms.CheckStatus.DENIED
    assert p.check_verification(started.provider_ref, code) is sms.CheckStatus.APPROVED
    assert p.check_verification(started.provider_ref, code) is sms.CheckStatus.EXPIRED


def test_scripted_provider_simulates_delivery_failures() -> None:
    p = sms.ScriptedSmsProvider()
    for number, code in (
        (sms.TEST_UNDELIVERABLE, "undeliverable"),
        (sms.TEST_OUTAGE, "provider_unavailable"),
    ):
        with pytest.raises(sms.DeliveryError) as err:
            p.request_verification(number)
        assert err.value.code == code
