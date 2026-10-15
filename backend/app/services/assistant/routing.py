"""The routing policy for one question, decided by rules (not by a model).

* A numerical question (a figure, quantity, rate, share, change or comparison) starts with
  OSRIP's approved data: web search is refused until the platform's data have been looked up
  in this answer. The web may then fill a gap the data leave.
* A question about recent events ("latest news", "this week", "now", ...) may use web research
  from the start, where web research is available.
* One provider answers; a second only as a fallback after a failure, or for a cross-check the
  person asks for (see ``app.services.providers``).

The decision is recorded with the answer ("How this answer was prepared").
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_NUMERIC = re.compile(
    r"\d|\b(how (much|many)|what (is|was|were) the (level|amount|value|total|share|rate)|"
    r"latest (figure|value|number)|growth|increase|decrease|change|rate|share|percent|percentage|"
    r"total|average|compare|comparison|gwh|mwh|tonnes?|tons?|cubic|m3|omr|rial|volume|production|"
    r"generation|consumption|imports?|exports?)\b"
    r"|كم|نسبة|معدل|نمو|زيادة|انخفاض|تغير|تغيّر|حصة|إجمالي|اجمالي|متوسط|قارن|مقارنة|حجم|إنتاج|انتاج|"
    r"توليد|استهلاك|واردات|صادرات|رقم|قيمة|[٠-٩]",
    re.IGNORECASE,
)
_RECENT = re.compile(
    r"\b(latest news|news|today|yesterday|this (week|month|year)|last (week|month)|recent(ly)?|"
    r"current(ly)?|right now|now|announced|announcement|just)\b"
    r"|اليوم|أمس|امس|هذا الأسبوع|هذا الاسبوع|هذا الشهر|هذا العام|هذه السنة|مؤخراً|مؤخرا|حالياً|حاليا|"
    r"الآن|الان|أحدث الأخبار|آخر الأخبار|اخر الاخبار|أُعلن|أعلن|إعلان",
    re.IGNORECASE,
)

DATA_TOOLS = frozenset(
    {
        "list_indicators", "get_observations", "latest_period", "compare_periods",
        "growth_rate", "share_of_total", "compare_areas", "run_study", "data_quality_notes",
        "get_forecast", "scenario_projection",
    }
)  # fmt: skip


@dataclass(frozen=True)
class Route:
    numerical: bool
    recent: bool
    web_first: bool  # web research may come before a platform data lookup

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


def classify(question: str) -> Route:
    numerical = bool(_NUMERIC.search(question))
    recent = bool(_RECENT.search(question))
    return Route(numerical=numerical, recent=recent, web_first=recent or not numerical)
