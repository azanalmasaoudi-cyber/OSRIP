"""The routing policy for one question, decided by rules (not by a model).

* A numerical question (a figure, quantity, rate, share, change or comparison) starts with
  OSRIP's approved data: web search is refused until the platform's data have been looked up
  in this answer. The web may then fill a gap the data leave. Internet research (the Research
  mode) is the exception: it searches the web first and uses OSRIP's data only to compare.
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
    r"generation|consumption|imports?|exports?|shortages?|surplus(es)?|deficits?|self-sufficiency)\b"
    r"|كم|نسبة|معدل|نمو|زيادة|انخفاض|تغير|تغيّر|حصة|إجمالي|اجمالي|متوسط|قارن|مقارنة|حجم|إنتاج|انتاج|"
    r"توليد|استهلاك|واردات|صادرات|رقم|قيمة|عجز|فائض|نقص|اكتفاء|[٠-٩]",
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
        "get_forecast", "scenario_projection", "balance_analysis",
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


# The answer mode for "auto" (the conversation page sends it): inferred from the words of the
# question, so nobody has to choose Ask, Analyze, Research, Compare or Scenario first. Checked
# in this order; anything else is a plain question ("ask").
_MODE_PATTERNS = (
    (
        "scenario",
        r"\b(what if|scenario|suppose|assum(e|ing)|if (demand|supply|consumption|production|"
        r"imports?|exports?) (grows?|rises?|falls?|increases?|decreases?|doubles?))\b"
        r"|ماذا لو|سيناريو|افترض|بافتراض|لو (زاد|زادت|ارتفع|ارتفعت|انخفض|انخفضت|تضاعف)",
    ),
    (
        "compare",
        r"\b(compare|comparison|versus|vs|difference between|previous year|year before|"
        r"year earlier|last year)\b"
        r"|قارن|قارني|مقارنة|الفرق بين|مقابل|السنة السابقة|العام السابق|العام الماضي|السنة الماضية",
    ),
    (
        "research",
        r"\b(search (the )?(web|internet|online)|on the (web|internet)|online sources?|news|"
        r"research|find (the )?(latest|newest|most recent|current)|latest published|"
        r"original sources?|official sources?|update (the )?(data|statistics|figures)|"
        r"save (the )?(figures|statistics|data|results|observations?))\b"
        r"|ابحث في|ابحث عن|الإنترنت|الانترنت|أخبار|اخبار|أحدث (ال)?(إحصاءات|البيانات|الأرقام) المنشورة"
        r"|المصادر الأصلية|المصادر الرسمية|حدّث البيانات|حدث البيانات|احفظ",
    ),
    (
        "analyze",
        r"\b(analy[sz]e|analysis|trends?|why|explain|drivers?|causes?|recommend(ations?)?|"
        r"assess|evaluate|shortages?|surplus(es)?|deficits?)\b"
        r"|حلل|حلّل|تحليل|اتجاه|لماذا|اشرح|فسر|فسّر|أسباب|توصي|توصيات|قيّم|عجز|فائض",
    ),
)
_MODES = tuple((mode, re.compile(pattern, re.IGNORECASE)) for mode, pattern in _MODE_PATTERNS)


# Words that ask for a chart (English and Arabic), including "Draw it" after a table.
_CHART = re.compile(
    r"\b(chart|graph|plot|visuali[sz]e|visuali[sz]ation|draw)\b|رسم|مخطط|بياني|ارسم",
    re.IGNORECASE,
)


# Words that ask for the newest figures: cached searches and documents then count only while
# they are recent (``research_latest_cache_hours``), so "latest" is checked against the source.
_LATEST = re.compile(
    r"\b(latest|newest|most recent|recent|current(ly)?|up[- ]to[- ]date|now|today|this (year|month))\b"
    r"|أحدث|احدث|آخر|اخر|الأخير|الأخيرة|الحالي|الحالية|حالياً|حاليا|الآن|الان|اليوم|هذا العام|هذا الشهر",
    re.IGNORECASE,
)


def asks_for_latest(question: str) -> bool:
    return bool(question and _LATEST.search(question))


def asks_for_chart(question: str) -> bool:
    """Charts appear only when the person asks for one."""
    return bool(question and _CHART.search(question))


def answer_mode(question: str, requested: str) -> str:
    """The mode to answer in: the one the person chose, or for "auto" the one the question's
    words call for (stored with the request, so the reply shows which was used)."""
    if requested != "auto":
        return requested
    return next((mode for mode, pattern in _MODES if pattern.search(question)), "ask")


# ------------------------------------------------------------------ the three user-facing modes
#
# Quick answer ("quick") and Deep internet research ("research") work from the live web only:
# OSRIP's own datasets are not offered to the model (tools.tool_specs) nor run if asked for
# (tools.run_tool), unless the question itself asks for the platform's data. Data analysis and
# visualization ("analyze", with "ask", "compare" and "scenario" as its variants) works from
# the published OSRIP data the person selected, and searches the web only when switched on.
INTERNET_MODES = frozenset({"quick", "research"})
DATA_MODES = frozenset({"ask", "analyze", "compare", "scenario"})

# The question asks for OSRIP's own records ("in OSRIP's data", "بيانات المنصة").
_PROJECT_DATA = re.compile(
    r"\b(osrip(['’]s)? (own )?(data|datasets?|records|figures|observations)|"
    r"(the )?platform(['’]s)? (own )?(data|datasets?|records|figures)|(our|internal|published) "
    r"(osrip )?(data|datasets?|records)|in osrip|from osrip)\b"
    r"|بيانات (المنصة|OSRIP|osrip)|سجلات (المنصة|OSRIP)|البيانات المنشورة في المنصة|من بيانات المنصة"
    r"|البيانات الداخلية|في OSRIP|من OSRIP",
    re.IGNORECASE,
)

# The question asks for a generated picture (an illustration, not a chart of figures).
_IMAGE = re.compile(
    r"\b(image|illustration|illustrate|picture|infographic|poster|artwork|visual concept|"
    r"concept art|render)\b|صورة|رسم(ة)? توضيحي|رسما توضيحيا|إنفوجرافيك|انفوجرافيك|ملصق|لوحة",
    re.IGNORECASE,
)


def asks_for_project_data(question: str) -> bool:
    """The person asked for OSRIP's own data, which internet modes then also consult."""
    return bool(question and _PROJECT_DATA.search(question))


def asks_for_image(question: str) -> bool:
    """A generated illustration is made only when the person asks for one."""
    return bool(question and _IMAGE.search(question))
