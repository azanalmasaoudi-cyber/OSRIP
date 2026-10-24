"""NCSI's public list of publications (https://www.ncsi.gov.om/en/publications).

The page is the publisher's own list of releases. It carries the list as JSON in its
``__NEXT_DATA__`` script (``props.pageProps.initialPublications.publications``): for each
release an id, English and Arabic titles, the PDF and (for some releases) the Excel file on
api.ncsi.gov.om, and the publisher's ``created_at`` and ``updated_at`` times. Only that JSON
is read (no page text is scraped); a page without it, or with entries that lack the expected
fields, is reported as a layout change and nothing is changed in OSRIP.

Verified 2026-10-23: the newest entry was "Monthly Statistical Bulletin :October 2026" (id
1968, created 2026-10-20T09:28:38Z) with an .xlsx under /uploads/xls/.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

LISTING_URL = "https://www.ncsi.gov.om/en/publications"
FILE_HOST = "api.ncsi.gov.om"
_NEXT = re.compile(
    rb'<script[^>]*id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>(.*?)</script>', re.S
)


class ListingError(ValueError):
    """The listing does not have the structure this reader was verified against."""


@dataclass(frozen=True, slots=True)
class Publication:
    id: str
    title_en: str
    title_ar: str | None
    created_at: datetime | None
    updated_at: datetime | None
    xls_url: str | None
    pdf_url: str | None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _file(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith(f"https://{FILE_HOST}/uploads/"):
        return None
    return value


def parse(page: bytes) -> list[Publication]:
    m = _NEXT.search(page)
    if not m:
        raise ListingError("the publications list (__NEXT_DATA__) was not found on the page")
    try:
        data = json.loads(m.group(1))
        items = data["props"]["pageProps"]["initialPublications"]["publications"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ListingError("the publications list has an unexpected structure") from exc
    if not isinstance(items, list):
        raise ListingError("the publications list is not a list")
    out = []
    for item in items:
        if (
            not isinstance(item, dict)
            or "id" not in item
            or not isinstance(item.get("title_en"), str)
        ):
            raise ListingError("a publication entry lacks its id or English title")
        out.append(
            Publication(
                id=str(item["id"]),
                title_en=item["title_en"].strip(),
                title_ar=item.get("title_ar") if isinstance(item.get("title_ar"), str) else None,
                created_at=_time(item.get("created_at")),
                updated_at=_time(item.get("updated_at")),
                xls_url=_file(item.get("xls_file_url")),
                pdf_url=_file(item.get("pdf_file_url")),
            )
        )
    return out
