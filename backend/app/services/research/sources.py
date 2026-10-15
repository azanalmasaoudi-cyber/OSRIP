"""Which publishers count as official. Pure: no I/O.

* ``official``: Omani government domains (``*.gov.om``, e.g. the National Centre for
  Statistics and Information, ministries, Oman Customs) and the official regulator and
  state companies of the electricity and water sectors.
* ``international``: international statistical and multilateral organisations.
* ``secondary``: everything else (news, companies, blogs, aggregators) - reported, not
  official data, whatever the page says about itself.
The class comes from the host name only, never from page content.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit

# host suffix -> (publisher name EN, AR)
OFFICIAL: dict[str, tuple[str, str]] = {
    "ncsi.gov.om": (
        "National Centre for Statistics and Information",
        "المركز الوطني للإحصاء والمعلومات",
    ),
    "data.gov.om": ("Oman open data portal", "بوابة البيانات المفتوحة لسلطنة عمان"),
    "customs.gov.om": ("Oman Customs", "الجمارك العمانية"),
    "maf.gov.om": (
        "Ministry of Agriculture, Fisheries and Water Resources",
        "وزارة الثروة الزراعية والسمكية وموارد المياه",
    ),
    "moci.gov.om": (
        "Ministry of Commerce, Industry and Investment Promotion",
        "وزارة التجارة والصناعة وترويج الاستثمار",
    ),
    "mof.gov.om": ("Ministry of Finance", "وزارة المالية"),
    "cbo.gov.om": ("Central Bank of Oman", "البنك المركزي العماني"),
    "mem.gov.om": ("Ministry of Energy and Minerals", "وزارة الطاقة والمعادن"),
    "gov.om": ("Government of Oman", "حكومة سلطنة عمان"),
    "apsr.om": ("Authority for Public Services Regulation", "هيئة تنظيم الخدمات العامة"),
    "omanpwp.om": ("Nama Power and Water Procurement", "نماء لشراء الطاقة والمياه"),
    "omangrid.com": ("Oman Electricity Transmission Company", "الشركة العمانية لنقل الكهرباء"),
    "nama.om": ("Nama Group (state-owned utilities)", "مجموعة نماء"),
}

INTERNATIONAL: dict[str, tuple[str, str]] = {
    "fao.org": (
        "Food and Agriculture Organization of the United Nations",
        "منظمة الأغذية والزراعة للأمم المتحدة",
    ),
    "worldbank.org": ("World Bank", "البنك الدولي"),
    "imf.org": ("International Monetary Fund", "صندوق النقد الدولي"),
    "un.org": ("United Nations", "الأمم المتحدة"),
    "unstats.un.org": ("UN Statistics Division", "الشعبة الإحصائية للأمم المتحدة"),
    "comtrade.un.org": ("UN Comtrade", "قاعدة بيانات الأمم المتحدة لتجارة السلع"),
    "unctad.org": ("UNCTAD", "مؤتمر الأمم المتحدة للتجارة والتنمية"),
    "wto.org": ("World Trade Organization", "منظمة التجارة العالمية"),
    "iea.org": ("International Energy Agency", "وكالة الطاقة الدولية"),
    "irena.org": ("International Renewable Energy Agency", "الوكالة الدولية للطاقة المتجددة"),
    "gccstat.org": ("GCC Statistical Center", "المركز الإحصائي لدول مجلس التعاون"),
    "oecd.org": ("OECD", "منظمة التعاون الاقتصادي والتنمية"),
}

# Peer-reviewed publishers, scholarly indexes and university repositories. Research papers
# give context, methods and drivers; they are not official statistics.
RESEARCH: dict[str, tuple[str, str]] = {
    "doi.org": ("DOI-registered publication", "منشور مسجّل بمعرّف DOI"),
    "sciencedirect.com": ("ScienceDirect (Elsevier)", "ساينس دايركت (إلسفير)"),
    "springer.com": ("Springer", "سبرينغر"),
    "nature.com": ("Nature Portfolio", "مجموعة نيتشر"),
    "mdpi.com": ("MDPI", "إم دي بي آي"),
    "tandfonline.com": ("Taylor & Francis", "تايلور وفرانسيس"),
    "wiley.com": ("Wiley", "وايلي"),
    "frontiersin.org": ("Frontiers", "فرونتيرز"),
    "iwaponline.com": ("IWA Publishing", "منشورات الجمعية الدولية للمياه"),
    "cambridge.org": ("Cambridge University Press", "مطبعة جامعة كامبريدج"),
    "oup.com": ("Oxford University Press", "مطبعة جامعة أكسفورد"),
    "ieee.org": ("IEEE", "معهد مهندسي الكهرباء والإلكترونيات"),
    "plos.org": ("PLOS", "بلوس"),
    "sagepub.com": ("SAGE", "سيج"),
    "emerald.com": ("Emerald", "إميرالد"),
    "jstor.org": ("JSTOR", "جستور"),
    "arxiv.org": ("arXiv (preprint, not peer reviewed)", "أرخايف (مسودة غير محكّمة)"),
    "ssrn.com": ("SSRN (preprint, not peer reviewed)", "إس إس آر إن (مسودة غير محكّمة)"),
    "squ.edu.om": ("Sultan Qaboos University", "جامعة السلطان قابوس"),
    "utas.edu.om": (
        "University of Technology and Applied Sciences",
        "جامعة التقنية والعلوم التطبيقية",
    ),
}

# Preferred hosts for site-restricted searches, by domain of the question.
PREFERRED_SITES: dict[str, list[str]] = {
    "electricity": ["ncsi.gov.om", "apsr.om", "omanpwp.om", "omangrid.com", "iea.org", "irena.org"],
    "water": ["ncsi.gov.om", "apsr.om", "omanpwp.om", "nama.om", "maf.gov.om"],
    "food_security": ["ncsi.gov.om", "maf.gov.om", "fao.org"],
    "trade": ["ncsi.gov.om", "customs.gov.om", "moci.gov.om", "comtrade.un.org", "wto.org"],
    "general": ["ncsi.gov.om", "gov.om", "fao.org", "worldbank.org"],
}


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _match(host: str, table: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    best = None
    for suffix, names in table.items():
        if (host == suffix or host.endswith("." + suffix)) and (
            best is None or len(suffix) > len(best[0])
        ):
            best = (suffix, names)
    return best[1] if best else None


def classify(url: str) -> dict[str, object]:
    """{'source_class', 'publisher': {'en','ar'}, 'host'} for a URL."""
    host = host_of(url)
    if names := _match(host, OFFICIAL):
        cls = "official"
    elif names := _match(host, INTERNATIONAL):
        cls = "international"
    elif names := _match(host, RESEARCH):
        cls = "research"
    else:
        cls, names = "secondary", (host, host)
    return {"source_class": cls, "publisher": {"en": names[0], "ar": names[1]}, "host": host}


def rank(source_class: str) -> int:
    """Omani official sources first, then international organisations, then research
    papers, then everything else."""
    return {"official": 0, "international": 1, "research": 2}.get(source_class, 3)


def evidence_class(source_class: str) -> str:
    """How a web item is labelled beside its citation."""
    if source_class in ("official", "international"):
        return "official"
    return "research" if source_class == "research" else "secondary"


STALE_AFTER_DAYS = 3 * 365


def freshness(published: str | None, today: date) -> dict[str, object]:
    """Whether a source may be out of date: published more than three years before
    ``today``, or with no publication date at all (its age cannot be judged)."""
    if not published:
        return {"stale": None, "age_days": None, "freshness": "undated"}
    try:
        day = date.fromisoformat(published[:10])
    except ValueError:
        return {"stale": None, "age_days": None, "freshness": "undated"}
    age = (today - day).days
    stale = age > STALE_AFTER_DAYS
    return {"stale": stale, "age_days": age, "freshness": "stale" if stale else "current"}
