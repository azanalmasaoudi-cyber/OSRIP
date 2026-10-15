"""The assistant's evidence check (pure)."""

from __future__ import annotations

from decimal import Decimal

from app.services.assistant.grounding import numbers_in, validate

OBS = {
    "id": "E1",
    "kind": "observation",
    "value": "36123.456",
    "period_start": "2023-01-01",
    "period_end": "2023-12-31",
}
PREV = {
    "id": "E2",
    "kind": "observation",
    "value": "35000",
    "period_start": "2022-01-01",
    "period_end": "2022-12-31",
}
CALC = {
    "id": "E3",
    "kind": "calculation",
    "value": "3.209874285714285714285714286",
    "inputs": ["E2", "E1"],
}
LEDGER = [OBS, PREV, CALC]


def test_numbers_are_read_in_latin_and_arabic_digits() -> None:
    assert numbers_in("36,123.46 GWh in 2023 [E1]") == [
        (Decimal("36123.46"), 2),
        (Decimal("2023"), 0),
    ]
    assert numbers_in("٣٦٬١٢٣٫٥ في ٢٠٢٣") == [(Decimal("36123.5"), 1), (Decimal("2023"), 0)]


def test_supported_numbers_with_citation_pass_including_rounding() -> None:
    assert validate("Generation was 36,123.46 GWh in 2023 [E1].", ["E1"], LEDGER).ok
    assert validate(
        "It rose by 3.2% from 2022 to 2023 [E3].", ["E3"], LEDGER
    ).ok  # inputs' periods allowed


def test_an_invented_number_is_rejected() -> None:
    verdict = validate("Generation was 40,000 GWh in 2023 [E1].", ["E1"], LEDGER)
    assert not verdict.ok and "40000" in verdict.problems[0]


def test_rounding_must_be_honest() -> None:
    assert not validate("Generation was 36,200 GWh [E1].", ["E1"], LEDGER).ok
    assert validate("Generation was 36,123 GWh [E1].", ["E1"], LEDGER).ok


def test_numbers_need_citations_and_citations_must_exist() -> None:
    assert not validate("Generation was 36,123.46 GWh.", [], LEDGER).ok
    assert not validate("Generation was 36,123.46 GWh [E9].", ["E9"], LEDGER).ok


def test_a_number_from_uncited_evidence_is_rejected() -> None:
    assert not validate("In 2022 it was 35,000 [E1].", ["E1"], LEDGER).ok


def test_text_without_numbers_needs_no_citation() -> None:
    assert validate("Which indicator do you mean?", [], LEDGER).ok
