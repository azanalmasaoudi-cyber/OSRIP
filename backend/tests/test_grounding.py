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


def test_a_number_written_onto_an_arabic_word_is_read_whole() -> None:
    # "و" (and) is written onto the number; codes such as CO2 or Q3 are still not figures.
    assert numbers_in("و49,132.0 GWh") == [(Decimal("49132.0"), 1)]
    assert numbers_in("CO2 in Q3") == []
    assert validate("و36,123.46 GWh في 2023 [E1].", ["E1"], LEDGER).ok
    assert not validate("و40000 GWh في 2023 [E1].", ["E1"], LEDGER).ok


def test_list_numbers_are_not_figures() -> None:
    # Seen live (DeepSeek, 2026-10-25): "**1. Like-for-like partial year ...**" was withheld.
    text = "**1. Partial year:** 37,481.8 GWh\n2) Full year\n١- أولاً\n- 3. Item\n37.5 GWh\n12 GWh"
    assert numbers_in(text) == [
        (Decimal("37481.8"), 1),
        (Decimal("37.5"), 1),
        (Decimal("12"), 0),
    ]
    reply = (
        "**1. Full year 2023:**\n- 36,123.46 GWh [E1].\n**2. The year before:**\n- 35,000 GWh [E2]."
    )
    assert validate(reply, ["E1", "E2"], LEDGER).ok


def test_the_day_of_a_written_date_is_not_a_figure() -> None:
    # Seen live (DeepSeek, 2026-10-25): "31 December" made a correct answer "unverified".
    for text in (
        "Generation was 36,123.46 GWh in the year to 31 December 2023 [E1].",
        "Generation was 36,123.46 GWh in the year to December 31, 2023 [E1].",
        "Generation was 36,123.46 GWh for 1–31 December 2023 [E1].",
        "بلغ التوليد 36,123.46 GWh حتى 31 ديسمبر 2023 [E1].",
    ):
        assert validate(text, ["E1"], LEDGER).ok, text
    # A figure next to a month that is not a day is still checked.
    assert not validate("Generation was 400 GWh in December 2023 [E1].", ["E1"], LEDGER).ok


def test_an_iso_date_must_come_from_the_cited_evidence() -> None:
    sourced = {**OBS, "source": {"access_date": "2026-09-27"}}
    ledger = [sourced, PREV, CALC]
    text = "Generation was 36,123.46 GWh in 2023 [E1].\n\nRecords checked up to 2026-09-27."
    assert validate(text, ["E1"], ledger).ok
    verdict = validate(text.replace("2026-09-27", "2026-10-30"), ["E1"], ledger)
    assert not verdict.ok and "2026-10-30" in verdict.problems[0]
    assert not validate("Records checked up to 2026-09-27.", [], ledger).ok
    # The first or last day of a month labels a period whose year the evidence supports.
    assert validate("Generation was 36,123.46 GWh to 2023-12-31 [E1].", ["E1"], ledger).ok
    assert not validate("Generation was 36,123.46 GWh to 2019-12-31 [E1].", ["E1"], ledger).ok


def test_the_cited_publication_can_be_named() -> None:
    titled = {**OBS, "source": {"title": "Statistical Year Book 2026, Issue 54"}}
    text = (
        "Generation was 36,123.46 GWh in 2023, from the Statistical Year Book 2026, Issue 54 [E1]."
    )
    assert validate(text, ["E1"], [titled]).ok
    assert not validate(text.replace("Issue 54", "Issue 55"), ["E1"], [titled]).ok
    assert not validate(text, ["E1"], [OBS]).ok  # not in an untitled record


def test_naming_a_cited_publication_is_not_a_figure() -> None:
    # Seen live: "all from the Statistical Year Book 2026, Issue 54 (S02)." without a marker.
    titled = {**OBS, "source": {"title": "Statistical Year Book 2026, Issue 54 (S02)"}}
    text = (
        "The figures come from the Statistical Year Book 2026, Issue 54 (S02).\n\n"
        "Generation was 36,123.46 GWh in 2023 [E1]."
    )
    assert validate(text, ["E1"], [titled]).ok
    assert validate(text.replace(" (S02)", ""), ["E1"], [titled]).ok
    # Not cited (no citation and no marker): its title gives no cover.
    alone = "The figures come from the Statistical Year Book 2026, Issue 54 (S02)."
    assert not validate(alone, [], [titled]).ok


def test_digits_in_a_web_address_are_not_figures() -> None:
    # Seen live: "https://ncsi.gov.om/ar/newsPage/newsDetail?id=366" made "366" a figure.
    text = "Generation was 36,123.46 GWh in 2023 [E1] (https://ncsi.gov.om/ar/newsPage/newsDetail?id=366)."
    assert validate(text, ["E1"], LEDGER).ok
    assert validate(
        "Source: [NCSI](https://ncsi.gov.om/x?id=366) reports 36,123.46 GWh [E1].", ["E1"], LEDGER
    ).ok
    assert validate(
        "See ncsi.gov.om/ar/newsPage/newsDetail?id=366: 36,123.46 GWh [E1].", ["E1"], LEDGER
    ).ok
    assert not validate("The page id 366 reports 36,123.46 GWh [E1].", ["E1"], LEDGER).ok
    # A saved record's identifier is not a figure either (seen live: "...-8572-...").
    saved = "Saved as observation cf501c1d-6e2d-4a69-8572-a64343b9e789: 36,123.46 GWh [E1]."
    assert validate(saved, ["E1"], LEDGER).ok
    assert not validate(
        "Generation was 4.5 GWh in 2023 [E1].", ["E1"], LEDGER
    ).ok  # 4.5 is no address


def test_a_real_arabic_draft_is_accepted() -> None:
    # A DeepSeek answer (2026-10-25) that was withheld before both fixes above.
    def obs(id_: str, start: str, end: str, value: str) -> dict[str, object]:
        return {
            "id": id_,
            "kind": "observation",
            "value": value,
            "period_start": start,
            "period_end": end,
            "source": {"access_date": "2026-09-27"},
        }

    ledger = [
        obs("E76", "2024-01-01", "2024-12-31", "49132.0"),
        obs("E77", "2026-01-01", "2026-08-31", "37481.8"),
        obs("E78", "2025-01-01", "2025-12-31", "50973.5"),
        obs("E79", "2026-08-01", "2026-08-31", "5743.9"),
    ]
    text = (
        "آخر قيمة منشورة لمؤشر «إجمالي توليد الكهرباء» هي 5,743.9 GWh لشهر أغسطس 2026 [E79].\n\n"
        "• 37,481.8 GWh للفترة من يناير إلى أغسطس 2026 [E77].\n"
        "• 50,973.5 GWh لسنة 2025 [E78]، و49,132.0 GWh لسنة 2024 [E76].\n\n"
        "ملاحظة: هذه القيم من سجلات جرى التحقق منها حتى 2026-09-27، وليست بيانات حيّة."
    )
    assert validate(text, ["E79", "E77", "E78", "E76"], ledger).ok
    assert not validate(text.replace("و49,132.0", "و49,312.0"), ["E76"], ledger).ok


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
