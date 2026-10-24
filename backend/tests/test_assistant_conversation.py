"""The conversation page asks with mode "auto": the answer mode is inferred from the question's
words (no need to pick Ask, Analyze, Research, Compare or Scenario first), in English and
Arabic, and an explicit choice is kept as it is."""

from __future__ import annotations

import pytest

from app.services.assistant.routing import answer_mode


@pytest.mark.parametrize(
    ("question", "mode"),
    [
        ("What is the latest electricity generation?", "ask"),
        ("Hello", "ask"),
        ("Explain electricity consumption in Oman.", "analyze"),
        ("Why did water production fall?", "analyze"),
        ("Is there an electricity shortage or surplus?", "analyze"),
        ("Compare it with the previous year.", "compare"),
        ("Water production in 2023 versus 2022", "compare"),
        ("Search the web for electricity news", "research"),
        ("What if demand grows 3% a year?", "scenario"),
        ("اشرح استهلاك الكهرباء في عُمان", "analyze"),
        ("قارنه بالعام السابق", "compare"),
        ("ماذا لو زاد الطلب ٣٪ سنوياً؟", "scenario"),
        ("ابحث في الإنترنت عن أخبار المياه", "research"),
        ("ما آخر قيمة لتوليد الكهرباء؟", "ask"),
    ],
)
def test_auto_infers_the_mode_from_the_question(question: str, mode: str) -> None:
    assert answer_mode(question, "auto") == mode


def test_an_explicit_mode_is_kept() -> None:
    assert answer_mode("Compare it with the previous year.", "ask") == "ask"
    assert answer_mode("Hello", "research") == "research"
