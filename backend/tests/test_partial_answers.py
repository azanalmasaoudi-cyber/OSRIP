"""Partly supported replies (pure): the sentences that fail the evidence check are left out, the
rest is kept unchanged, and nothing unsupported can remain."""

from __future__ import annotations

from app.services.assistant.grounding import keep_supported, substantive, validate

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
LEDGER = [OBS, PREV]


def test_an_invented_figure_is_left_out_and_the_rest_kept() -> None:
    reply = (
        "Generation reached 36,123.46 GWh in 2023 [E1]. Another estimate put it at 99,999 GWh [E1]."
        " Growth reflects new capacity and demand from industry."
    )
    assert not validate(reply, ["E1"], LEDGER).ok
    partial = keep_supported(reply, ["E1"], LEDGER)
    assert partial.omitted == 1
    assert "99,999" not in partial.text
    assert "36,123.46 GWh in 2023 [E1]." in partial.text
    assert "new capacity and demand" in partial.text
    assert validate(partial.text, ["E1"], LEDGER).ok


def test_a_figure_without_a_citation_nearby_is_left_out() -> None:
    reply = (
        "Generation was 36,123.46 GWh [E1].\n\nIt rose by 12 per cent since then.\n\n"
        "Demand drives it."
    )
    partial = keep_supported(reply, ["E1"], LEDGER)
    assert partial.omitted == 1 and "12 per cent" not in partial.text
    assert "Demand drives it." in partial.text


def test_a_marker_naming_no_evidence_is_removed() -> None:
    partial = keep_supported("Demand is seasonal [E9]. Supply follows it.", [], LEDGER)
    assert partial.text == "Demand is seasonal. Supply follows it." and partial.omitted == 0


def test_list_items_and_headings_keep_their_markers() -> None:
    reply = (
        "## Findings\n- In 2022 it was 35,000 GWh [E2]. Some say 77,777 GWh [E2].\n"
        "- Water use rose."
    )
    partial = keep_supported(reply, ["E2"], LEDGER)
    assert partial.text.splitlines() == [
        "## Findings",
        "- In 2022 it was 35,000 GWh [E2].",
        "- Water use rose.",
    ]


def test_unsupported_table_rows_go_and_an_empty_table_goes_with_them() -> None:
    reply = (
        "| Year | GWh |\n|---|---|\n| 2023 | 36,123.46 [E1] |\n| 2021 | 31,000 [E1] |\n\n"
        "| Year | Tonnes |\n|---|---|\n| 2020 | 5 [E1] |\n\nThe trend is upward."
    )
    partial = keep_supported(reply, ["E1"], LEDGER)
    assert partial.omitted == 2
    assert "| 2023 | 36,123.46 [E1] |" in partial.text
    assert "31,000" not in partial.text and "Tonnes" not in partial.text
    assert validate(partial.text, ["E1"], LEDGER).ok


def test_arabic_sentences_are_checked_one_by_one() -> None:
    reply = (
        "بلغ التوليد 36,123.46 جيجاواط ساعة في 2023 [E1]. وقدّره آخرون بنحو 50,000 [E1]. "
        "السبب نمو الطلب الصناعي."
    )
    partial = keep_supported(reply, ["E1"], LEDGER)
    assert partial.omitted == 1 and "50,000" not in partial.text
    assert "السبب نمو الطلب الصناعي." in partial.text


def test_too_little_left_is_not_substantive() -> None:
    partial = keep_supported("It was 123,456,789 GWh [E1].", ["E1"], LEDGER)
    assert partial.text == "" and partial.omitted == 1
    assert not substantive(partial.text)
    assert not substantive("## Results\n[E1]")
    assert substantive("Demand grows with the population and industry in the coastal cities.")
