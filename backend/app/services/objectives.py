"""The five objectives a person can set before recommendations are given, and how they are
recognised in a sentence (English or Arabic).

The guided analysis in each sector and Al Mulhim use the same list: recommendations are given
only once at least one objective is known, chosen from this list or written in a person's own
words and recognised here. Words that match none of them leave the objectives unknown; nothing
is guessed.
"""

from __future__ import annotations

import re

OBJECTIVES = (
    "reduce_shortages",
    "improve_efficiency",
    "use_surplus",
    "strengthen",
    "diversify",
)

NAMES: dict[str, dict[str, str]] = {
    "reduce_shortages": {"en": "Reduce shortages", "ar": "تقليل العجز"},
    "improve_efficiency": {"en": "Improve efficiency", "ar": "رفع الكفاءة"},
    "use_surplus": {"en": "Use the surplus", "ar": "استثمار الفائض"},
    "strengthen": {"en": "Strengthen production and trade", "ar": "تعزيز الإنتاج والتجارة"},
    "diversify": {"en": "Diversify", "ar": "التنويع"},
}

_PATTERNS: dict[str, str] = {
    "reduce_shortages": (
        r"\bshortages?\b|\bdeficits?\b|\bsecur(e|ity of) supply\b|\bsupply gaps?\b|\boutages?\b"
        r"|\bscarcity\b|\bmeet (the )?demand\b"
        r"|عجز|نقص|شح|انقطاع|تأمين (الإمداد|الإمدادات|التزويد)|سد (الفجوة|الطلب)"
    ),
    "improve_efficiency": (
        r"\befficien(t|cy)\b|\blosses\b|\bwaste\b|\bleak(s|age)?\b|\bconserv(e|ation)\b"
        r"|كفاءة|الكفاءة|الهدر|هدر|الفاقد|فاقد|التسرب|ترشيد"
    ),
    "use_surplus": (
        r"\bsurplus\b|\bexcess (capacity|supply|production)\b|\bspare capacity\b"
        r"|فائض|الفائض|الطاقة الفائضة|الإنتاج الفائض"
    ),
    "strengthen": (
        r"\bstrengthen\b|\bboost\b|\bincrease (production|output|exports?|trade)\b"
        r"|\bgrow (production|output|exports?|trade)\b"
        r"|\bexpand (production|output|exports?|trade)\b"
        r"|تعزيز|زيادة (الإنتاج|الصادرات|التجارة)|تنمية (الإنتاج|الصادرات|التجارة)|تقوية"
    ),
    "diversify": r"\bdiversif(y|ication|ied)\b|تنويع|التنويع",
}
_COMPILED = {code: re.compile(p, re.IGNORECASE) for code, p in _PATTERNS.items()}


def detect(text: str) -> list[str]:
    """The objectives a sentence names, in the fixed order of ``OBJECTIVES`` (none when no
    objective is named)."""
    if not text:
        return []
    return [code for code in OBJECTIVES if _COMPILED[code].search(text)]


def clean(codes: list[str] | tuple[str, ...]) -> list[str]:
    """Known objective codes only, each once, in the fixed order."""
    wanted = set(codes)
    return [code for code in OBJECTIVES if code in wanted]
