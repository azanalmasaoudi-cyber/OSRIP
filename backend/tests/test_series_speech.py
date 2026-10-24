"""The spoken explanation of a selected range (pure): a few sentences from the timeline's own
summary, in English or Arabic, never the table row by row; spoken numbers rounded for listening;
missing periods named; no total for a level; a selection without values says so."""

from __future__ import annotations

from typing import Any

from app.services.timeline import _spoken_number, spoken_summary


def _doc(**summary: Any) -> dict[str, Any]:
    base = {
        "periods": 3, "with_value": 3, "missing": 0,
        "first": {"period_start": "2026-06-01", "value": "42.736", "nature": "provisional"},
        "last": {"period_start": "2026-08-01", "value": "43.1651", "nature": "provisional"},
        "change": {"absolute": "0.4291", "percent": "1.00"},
        "highest": None, "lowest": None, "total": "128.4349", "total_reason": None,
    }  # fmt: skip
    base.update(summary)
    return {
        "status": "ok",
        "view": "monthly",
        "indicator": {"name": {"en": "Water production", "ar": "إنتاج المياه"}},
        "unit": {"label": {"en": "million m³", "ar": "مليون م³"}},
        "summary": base,
        "sources": [{"publisher": "NCSI"}],
        "rows": [{"period_start": f"2026-0{m}-01"} for m in (6, 7, 8)],
    }


def test_spoken_numbers_are_rounded_for_listening_only() -> None:
    assert _spoken_number("43.1651") == "43.2"
    assert _spoken_number("0.4291") == "0.43"
    assert _spoken_number("117879.4") == "117,879.4"
    assert _spoken_number("1000") == "1,000"


def test_the_english_explanation_is_short_and_from_the_summary() -> None:
    text = spoken_summary(_doc(), "en", "Oman (national)")
    assert text.startswith(
        "Water production for Oman (national), monthly figures from June 2026 to August 2026."
    )
    assert "The latest value is 43.2 million m³, for August 2026." in text
    assert "up 0.43 million m³, or 1.0%, from June 2026" in text
    assert "The total over the period is 128.4 million m³." in text
    assert "provisional" in text and text.endswith("Source: NCSI.")
    assert len(text) < 600  # a few sentences, not a table


def test_the_arabic_explanation_uses_arabic_months_and_words() -> None:
    text = spoken_summary(_doc(), "ar", "عُمان (وطني)")
    assert "إنتاج المياه في عُمان (وطني)، القيم الشهرية من يونيو 2026 إلى أغسطس 2026." in text
    assert "أحدث قيمة 43.2 مليون م³ في أغسطس 2026." in text
    assert "ارتفعت بمقدار 0.43" in text and "المصدر: NCSI." in text


def test_missing_periods_no_total_for_a_level_and_no_values() -> None:
    gap = spoken_summary(_doc(periods=4, with_value=3, missing=1, total=None), "en", "Oman")
    assert "1 of the 4 periods are not published." in gap and "total" not in gap
    down = spoken_summary(_doc(change={"absolute": "-2.5", "percent": "-5.00"}), "en", "Oman")
    assert "down 2.5 million m³, or 5.0%," in down
    empty = spoken_summary({**_doc(with_value=0), "status": "ok"}, "en", "Oman")
    assert empty == "No published values of Water production for Oman in the selected period."
    none = spoken_summary(
        {"status": "no_published_data", "indicator": _doc()["indicator"]}, "ar", "عُمان"
    )
    assert none.startswith("لا توجد قيم منشورة")
