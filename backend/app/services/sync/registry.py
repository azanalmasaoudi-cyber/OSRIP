"""The registry of official statistics feeds: which publication series OSRIP follows, how
each is reached, which OSRIP indicators it supplies, and what could not be verified.

Every entry here was checked by hand against the publisher (2026-10-23); nothing is assumed
from documentation examples. A feed's schedule and switches live in the ``source_feed`` row
of the same code (migration 0022); this file holds what the code needs to read it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.services.sync import ncsi_msb

LICENCE = (
    "Official statistics published by the National Centre for Statistics and Information "
    "(NCSI); cited with attribution (Open Government License - Sultanate of Oman)."
)


@dataclass(frozen=True, slots=True)
class FeedSpec:
    code: str
    listing_url: str | None
    listing_hosts: frozenset[str]
    file_hosts: frozenset[str]
    # A release in the listing belongs to the feed when its English title matches; the
    # groups give the reference month name and year (e.g. "October", "2026").
    title: re.Pattern[str] | None
    parser: Callable[[bytes, str], ncsi_msb.Parsed] | None
    # OSRIP sources of this series (for the latest observation period), by title prefix.
    source_titles: tuple[str, ...]
    indicators: tuple[str, ...]
    tables: tuple[str, ...]
    notes_en: str
    notes_ar: str
    verified: dict[str, str] = field(default_factory=dict)


MONTHLY_BULLETIN = FeedSpec(
    code="ncsi-monthly-bulletin",
    listing_url="https://www.ncsi.gov.om/en/publications",
    listing_hosts=frozenset({"www.ncsi.gov.om"}),
    file_hosts=frozenset({"api.ncsi.gov.om"}),
    title=re.compile(
        r"^Monthly Statistical Bulletin\s*:?\s*([A-Za-z]+)\s+(\d{4})\s*$", re.IGNORECASE
    ),
    parser=ncsi_msb.parse_workbook,
    source_titles=("Monthly Statistical Bulletin",),
    indicators=("ELEC_GROSS_GENERATION", "ELEC_NET_GENERATION", "WATER_PRODUCTION"),
    tables=(
        "21 Electricity: gross and net production by region (GWh)",
        "22 Water: production by region (thousand m³)",
    ),
    notes_en=(
        "Checked daily (when switched on) in NCSI's public list of publications. Each new "
        "bulletin with an official Excel workbook is downloaded, tables 21 and 22 are read, "
        "and only new or changed figures are staged as an import for a data manager to "
        "approve. Other tables of the bulletin are not mapped yet."
    ),
    notes_ar=(
        "يُفحص يومياً (عند تفعيله) في قائمة منشورات المركز الوطني للإحصاء والمعلومات. كل نشرة "
        "جديدة لها مصنف Excel رسمي تُنزَّل ويُقرأ منها الجدولان 21 و22، ولا يُجهَّز للاستيراد "
        "إلا الأرقام الجديدة أو المعدَّلة، ليعتمدها مدير بيانات. ولم تُربط بقية جداول النشرة بعد."
    ),
    verified={
        "listing": "https://www.ncsi.gov.om/en/publications: HTTPS 200, publications as JSON "
        "in __NEXT_DATA__ (2026-10-23)",
        "file": "Monthly Statistical Bulletin, October 2026: official .xlsx on "
        "api.ncsi.gov.om/uploads/xls/, 33 tables (2026-10-23)",
        "tables": "Table 21 (sheet '21') GWh and table 22 (sheet '22') thousand m³; years marked "
        "(1) provisional, (2) preliminary",
    },
)

DATA_PORTAL = FeedSpec(
    code="ncsi-data-portal",
    listing_url=None,
    listing_hosts=frozenset(),
    file_hosts=frozenset(),
    title=None,
    parser=None,
    source_titles=(),
    indicators=(),
    tables=(),
    notes_en=(
        "The portal's documented API (POST https://data.gov.om/api/1.1/data/details) answered "
        "HTTP 403 to every anonymous request on 2026-10-23, including the documentation's own "
        "example, and the documentation names no way to obtain access. Dataset downloads need a "
        "signed-in portal account. Until access is granted, download the CSV yourself and import "
        "it with backend/scripts/ncsi_import.py and the Data Management page."
    ),
    notes_ar=(
        "أعادت الواجهة البرمجية الموثقة للبوابة (POST https://data.gov.om/api/1.1/data/details) "
        "الرمز HTTP 403 لكل طلب دون تسجيل دخول بتاريخ 2026-10-23، بما في ذلك مثال التوثيق نفسه، "
        "ولا يذكر التوثيق طريقة للحصول على صلاحية. وتنزيل مجموعات البيانات يتطلب حساباً في البوابة. "
        "إلى أن تُمنح الصلاحية، نزّل ملف CSV بنفسك واستورده بالأداة backend/scripts/ncsi_import.py "
        "وصفحة إدارة البيانات."
    ),
    verified={
        "api": "POST https://data.gov.om/api/1.1/data/details and GET /api/1.0/meta/dataset: "
        "HTTP 403 (2026-10-23)",
    },
)

FEEDS: dict[str, FeedSpec] = {f.code: f for f in (MONTHLY_BULLETIN, DATA_PORTAL)}

MONTH_NUMBERS = {
    m: i
    for i, m in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        start=1,
    )
}


def release_label(spec: FeedSpec, title: str) -> str | None:
    """'Monthly Statistical Bulletin :October 2026' -> 'MSB-2026-10' (None: not this feed)."""
    if spec.title is None:
        return None
    m = spec.title.match(title.strip())
    if not m:
        return None
    month = MONTH_NUMBERS.get(m.group(1).lower())
    if month is None:
        return None
    return f"MSB-{m.group(2)}-{month:02d}"
