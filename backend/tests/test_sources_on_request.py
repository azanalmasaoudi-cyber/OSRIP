"""Sources on request (pure): which messages ask for the sources, and how they are listed."""

from __future__ import annotations

import pytest

from app.services.assistant.sources import entries, is_request, reply_text


@pytest.mark.parametrize(
    "message",
    [
        "Show sources",
        "show me the sources",
        "Give me references",
        "Can you show the sources for this answer?",
        "Where did you get this information?",
        "where did you get that from",
        "What are your sources?",
        "Sources?",
        "references please",
        "اعرض المصادر",
        "أعطني المراجع",
        "ما هي المصادر؟",
        "ما مصادرك",
        "من أين حصلت على هذه المعلومات؟",
        "المصادر",
    ],
)
def test_requests_for_sources_are_recognised(message: str) -> None:
    assert is_request(message)


@pytest.mark.parametrize(
    "message",
    [
        "What are the main sources of water in Oman?",
        "Show sources of electricity generation by fuel",
        "Which renewable sources grew fastest?",
        "ما هي مصادر المياه في عمان؟",
        "Compare water production between 2022 and 2023.",
        "Show the trend",
    ],
)
def test_questions_that_mention_sources_go_to_the_assistant(message: str) -> None:
    assert not is_request(message)


EVIDENCE = [
    {
        "id": "E1",
        "kind": "observation",
        "value": "36123.4",
        "source": {
            "title": "Statistical Year Book 2025",
            "publisher": "NCSI",
            "url": "https://www.ncsi.gov.om/yearbook",
            "access_date": "2026-10-01",
            "reference_period": "2024",
        },
    },
    {  # the same table again: one source
        "id": "E2",
        "kind": "observation",
        "value": "35000",
        "source": {
            "title": "Statistical Year Book 2025",
            "publisher": "NCSI",
            "url": "https://www.ncsi.gov.om/yearbook",
            "access_date": "2026-10-01",
            "reference_period": "2023",
        },
    },
    {
        "id": "E3",
        "kind": "web",
        "title": "Nama annual report",
        "url": "https://nama.om/report",
        "publisher": "Nama",
        "published": "2026-04-30T00:00:00",
    },
    {"id": "E4", "kind": "search", "query": "electricity Oman"},
    {"id": "E5", "kind": "calculation", "value": "3.2", "inputs": ["E1", "E2"]},
]


def test_each_source_is_listed_once_and_searches_and_calculations_are_not_sources() -> None:
    listed = entries(EVIDENCE, "en")
    assert [e["url"] for e in listed] == [
        "https://www.ncsi.gov.om/yearbook",
        "https://nama.om/report",
    ]
    text = reply_text(listed, "en")
    assert text.startswith("Sources of the previous answer:")
    assert (
        "1. Statistical Year Book 2025 — NCSI, 2024 <https://www.ncsi.gov.om/yearbook>"
        " (accessed 2026-10-01)"
    ) in text
    assert "2. Nama annual report — Nama <https://nama.om/report> (accessed 2026-04-30)" in text


def test_arabic_listing_and_nothing_to_show() -> None:
    assert reply_text(entries(EVIDENCE[:1], "ar"), "ar").startswith("مصادر الإجابة السابقة:")
    assert "لا توجد مصادر" in reply_text([], "ar")
    assert "no sources to show" in reply_text([], "en")
