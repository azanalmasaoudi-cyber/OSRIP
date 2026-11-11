"""The November 2026 wilayat evidence review
(``OSRIP_Wilayat_Evidence_Development_Review_2026.xlsx``)
as import rows for the reviewed import workflow (stage, validate, approve, publish).

* ``Wilayats_63``: population at the end of 2024 and 2025 for each of the 63 wilayats
  (POP_TOTAL), Omani and non-Omani for 2025 (components, never added to the total). Wilayats are
  matched to the registry by their Arabic names; a row that cannot be matched is reported, never
  guessed.
* ``Trade_Wilayat_Events``: commercial registrations announced by the ministry, kept apart by
  what they measure and for which period: new registrations in 2025 (a full year), in the first
  quarter of 2026 and in the second quarter of 2026 (each a quarter, never a year or a year to
  date), and registrations on record at the end of the second quarter of 2026 (a stock, its own
  indicator). They are never added together.
* ``Water_Governorates``: water production and distribution in 2024 and 2025 for each
  governorate. Governorates only: nothing is assigned to a wilayat, and production minus
  distribution is not reported as losses.
* ``Annual_National`` and ``2026_Interim``: national figures; complete calendar years as full
  years, January-September 2026 as a partial year. Figures without a matching OSRIP area or
  indicator (a provider's service area, a derived total, capture and aquaculture together) are
  listed as not imported, with the reason.

Wilayats without a value stay without one: no figure is estimated from a governorate or national
total, or from population. ``Axis_Coverage_252`` (one coverage status for each wilayat and axis)
is documentation, not observations: ``coverage()`` reads it for the report.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from .owner_workbooks import Mapped, _number, _step

YEARBOOK = (
    "https://api.ncsi.gov.om/uploads/pdfs/statistical_year_book_2026___issue_54_1777963604.pdf"
)
ELECTRICITY_PORTAL = "https://data.gov.om/OMELCT2016/electricity"

# The workbook's governorate names -> registry codes (checked against the registry in tests).
GOVERNORATES = {
    "Muscat": "OM-MA",
    "Dhofar": "OM-ZU",
    "Musandam": "OM-MU",
    "Al Buraimi": "OM-BU",
    "Ad Dakhiliyah": "OM-DA",
    "Al Batinah North": "OM-BS",
    "Al Batinah South": "OM-BJ",
    "Ash Sharqiyah South": "OM-SJ",
    "Ash Sharqiyah North": "OM-SS",
    "Adh Dhahirah": "OM-ZA",
    "Al Wusta": "OM-WU",
}

# Trade_Wilayat_Events "Actual period" -> (period start, end, frequency, complete, indicator).
TRADE_PERIODS = {
    ("2025", "NEW_COMMERCIAL_REGISTRATIONS"): (
        "2025-01-01",
        "2025-12-31",
        "annual",
        "true",
        "TRADE_NEW_COMMERCIAL_REGISTRATIONS",
    ),
    ("2026-Q1", "NEW_COMMERCIAL_REGISTRATIONS"): (
        "2026-01-01",
        "2026-03-31",
        "quarterly",
        "true",
        "TRADE_NEW_COMMERCIAL_REGISTRATIONS",
    ),
    ("2026-Q2", "NEW_COMMERCIAL_REGISTRATIONS"): (
        "2026-04-01",
        "2026-06-30",
        "quarterly",
        "true",
        "TRADE_NEW_COMMERCIAL_REGISTRATIONS",
    ),
    ("2026-Q2-end", "CUMULATIVE_COMMERCIAL_REGISTRATIONS"): (
        "2026-04-01",
        "2026-06-30",
        "quarterly",
        "true",
        "TRADE_COMMERCIAL_REGISTRATIONS_STOCK",
    ),
}

# Annual_National "Indicator" -> (indicator, unit, publication precision) or the reason it is
# not imported.
NATIONAL = {
    "Electricity distribution": ("ELEC_DISTRIBUTION", "GWh", "0.1"),
}
NATIONAL_NOT_IMPORTED = {
    "Total population": "derived by adding the 63 wilayat rows, not a published figure; it is "
    "the reconciliation check of the wilayat import (5,359,557)",
    "Agricultural area": "a rounded media summary ('about 326 thousand feddan'); the yearbook "
    "figure is the one to import",
    "Fish production": "capture and aquaculture together; the registry holds capture landings "
    "by fishing method and has no aquaculture indicator",
    "Nama Water supply": "Nama Water Services' service area (excludes Dhofar) is not an OSRIP "
    "area; attached to Oman it would be read as national production",
}
# 2026_Interim "Indicator" -> (indicator, unit).
INTERIM = {
    "Total electricity generation": ("ELEC_GROSS_GENERATION", "GWh"),
    "Net electricity generation": ("ELEC_NET_GENERATION", "GWh"),
    "Total water production": ("WATER_PRODUCTION", "million_m3"),
    "New commercial registrations": ("TRADE_NEW_COMMERCIAL_REGISTRATIONS", "registration"),
}


@dataclass(frozen=True)
class Area:
    code: str
    name_en: str
    name_ar: str
    level: str
    parent_code: str | None


_MARKS = re.compile(r"[ً-ْٰـ]")  # harakat, superscript alef, tatweel


def arabic_key(name: str) -> str:
    """An Arabic name for matching: no diacritics or tatweel, one form of alef, ya, waw and ta
    marbuta, no hamza on the line, no spaces. Registry and workbook write the same name slightly
    differently (بهلاء / بهلا, دماء والطائيين / دما والطايين)."""
    s = unicodedata.normalize("NFKC", name or "")
    s = _MARKS.sub("", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    s = s.replace("ئ", "ي").replace("ؤ", "و").replace("ء", "")
    s = re.sub("ي+", "ي", s)  # الطائيين / الطايين
    return re.sub(r"\s+", "", s)


def english_key(name: str) -> str:
    """An English name for matching inside one governorate: letters only, without 'and'/'the'
    ('Shalim & Hallaniyat Islands' / 'Shalim and the Hallaniyat Islands')."""
    words = re.findall(r"[a-z]+", (name or "").lower())
    return "".join(w for w in words if w not in ("and", "the"))


class Registry:
    """The registry's wilayats by Arabic name (and by English name inside each governorate), and
    every area by code."""

    def __init__(self, areas: list[Area]) -> None:
        self.by_code = {a.code: a for a in areas}
        self.wilayats = {arabic_key(a.name_ar): a for a in areas if a.level == "wilayat"}
        self.english: dict[tuple[str | None, str], list[Area]] = {}
        for a in areas:
            if a.level == "wilayat":
                self.english.setdefault((a.parent_code, english_key(a.name_en)), []).append(a)

    def wilayat(
        self, name_ar: str, governorate: str | None = None, name_en: str = ""
    ) -> Area | None:
        found = self.wilayats.get(arabic_key(name_ar))
        if found and governorate and found.parent_code != governorate:
            return None  # the same name in another governorate: never matched across them
        if found is None and governorate and name_en:
            # Arabic spelt differently (لوى / ليوا; word order): the English name, but only
            # inside the stated governorate and only when exactly one wilayat has it.
            same = self.english.get((governorate, english_key(name_en)), [])
            found = same[0] if len(same) == 1 else None
        return found


def _int_text(raw: object) -> str | None:
    value = _number(raw)
    if value is None or value != value.to_integral_value():
        return None
    return format(value.to_integral_value(), "f")


def population(rows: list[dict[str, str]], registry: Registry, out: Mapped) -> dict[str, str]:
    """Wilayats_63: POP_TOTAL for 2024 and 2025, POP_OMANI and POP_NON_OMANI for 2025.
    Returns the workbook's English wilayat name -> registry code (to place the trade rows)."""
    english: dict[str, str] = {}
    for r in rows:
        name_en, name_ar = r.get("Wilayat EN", "").strip(), r.get("Wilayat AR", "").strip()
        gov = GOVERNORATES.get(r.get("Governorate EN", "").strip())
        area = registry.wilayat(name_ar, gov, name_en)
        if area is None:
            out.skipped.append(
                (
                    "Wilayats_63",
                    f"{name_en} / {name_ar}",
                    "not matched to a registry wilayat of that governorate",
                )
            )
            continue
        english[name_en] = area.code
        url = (r.get("Population source") or YEARBOOK).strip()
        values = (
            ("POP_TOTAL", "2024", r.get("Population 2024")),
            ("POP_TOTAL", "2025", r.get("Population 2025")),
            ("POP_OMANI", "2025", r.get("Omani 2025")),
            ("POP_NON_OMANI", "2025", r.get("Non-Omani 2025")),
        )
        for code, year, raw in values:
            value = _int_text(raw)
            if value is None:
                out.skipped.append(("Wilayats_63", f"{name_en} {code} {year}", "no value"))
                continue
            out.add(
                url,
                {
                    "indicator_code": code,
                    "area_code": area.code,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "frequency": "annual",
                    "period_complete": "true",
                    "unit_code": "person",
                    "value": value,
                    "quality_status": "accepted",
                    "revision_status": "reported",
                    "source_locator": "Statistical Year Book 2026, Issue 54: population by wilayat",
                    "note": f"Population at the end of {year} "
                    f"({name_en}, {r.get('Governorate EN', '')}).",
                },
            )
        # The parts must make up the total, or neither is imported as such.
        omani, non, total = (
            _number(r.get(k)) for k in ("Omani 2025", "Non-Omani 2025", "Population 2025")
        )
        if None not in (omani, non, total) and omani + non != total:
            out.skipped.append(
                (
                    "Wilayats_63",
                    f"{name_en} 2025",
                    f"Omani + non-Omani ({omani + non}) differs from the total ({total})",
                )
            )
    return english


def trade(
    rows: list[dict[str, str]], english: dict[str, str], registry: Registry, out: Mapped
) -> None:
    """Trade_Wilayat_Events: each row for its own measure and period, never added together."""
    for r in rows:
        name = r.get("Wilayat", "").strip()
        period, measure = (
            r.get("Actual period", "").strip(),
            r.get("Indicator / definition", "").strip(),
        )
        label = f"{name} {measure} {period}"
        spec = TRADE_PERIODS.get((period, measure))
        if spec is None:
            out.skipped.append(("Trade_Wilayat_Events", label, "unknown period or measure"))
            continue
        code = english.get(name)
        gov = GOVERNORATES.get(r.get("Governorate", "").strip())
        if code is None or (gov and registry.by_code[code].parent_code != gov):
            out.skipped.append(
                ("Trade_Wilayat_Events", label, "wilayat not matched in its governorate")
            )
            continue
        value = _int_text(r.get("Value"))
        if value is None or r.get("Unit", "").strip() != "registrations":
            out.skipped.append(
                ("Trade_Wilayat_Events", label, "no whole-number count of registrations")
            )
            continue
        start, end, frequency, complete, indicator = spec
        interpretation = r.get("Interpretation note", "").strip()
        unverified = (
            "verify definition" in interpretation.lower()
            or "wording varies" in interpretation.lower()
        )
        out.add(
            r.get("Official URL", "").strip(),
            {
                "indicator_code": indicator,
                "area_code": code,
                "period_start": start,
                "period_end": end,
                "frequency": frequency,
                "period_complete": complete,
                "unit_code": "registration",
                "value": value,
                # The announcement's wording should be checked against the definition
                # before approval.
                "quality_status": "warning" if unverified else "accepted",
                "revision_status": "reported",
                "source_locator": f"Ministry announcement ({r.get('Source ID', '').strip()})",
                "note": interpretation,
            },
        )


def water(rows: list[dict[str, str]], out: Mapped) -> None:
    """Water_Governorates: production and distribution by governorate, 2024 and 2025."""
    columns = (
        ("WATER_PRODUCTION", "2024", "Production 2024 (Mm3)"),
        ("WATER_PRODUCTION", "2025", "Production 2025 (Mm3)"),
        ("WATER_DISTRIBUTION", "2024", "Distribution 2024 (Mm3)"),
        ("WATER_DISTRIBUTION", "2025", "Distribution 2025 (Mm3)"),
    )
    for r in rows:
        name = r.get("Governorate EN", "").strip()
        gov = GOVERNORATES.get(name)
        if gov is None or r.get("Geographic coverage", "").strip() != "governorate":
            out.skipped.append(("Water_Governorates", name, "not a registry governorate"))
            continue
        for code, year, column in columns:
            raw = r.get(column)
            if _number(raw) is None:
                out.skipped.append(("Water_Governorates", f"{name} {column}", "no value"))
                continue
            out.add(
                (r.get("Source URL") or YEARBOOK).strip(),
                {
                    "indicator_code": code,
                    "area_code": gov,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "frequency": "annual",
                    "period_complete": "true",
                    "unit_code": "million_m3",
                    "value": format(_number(raw).normalize(), "f"),
                    "_step": _step(raw, 1),
                    "quality_status": "accepted",
                    "revision_status": "reported",
                    "source_locator": "Statistical Year Book 2026, Issue 54: water by governorate",
                    "note": f"{name}, {year}. Governorate only; production minus "
                    "distribution is not reported as losses.",
                },
            )


def national(rows: list[dict[str, str]], out: Mapped) -> None:
    """Annual_National: complete calendar years for Oman."""
    for r in rows:
        name, year = r.get("Indicator", "").strip(), str(r.get("Year", "")).strip()
        if name in NATIONAL_NOT_IMPORTED:
            out.skipped.append(("Annual_National", f"{name} {year}", NATIONAL_NOT_IMPORTED[name]))
            continue
        if (
            name not in NATIONAL
            or not year.isdigit()
            or r.get("Coverage", "").strip() != "national"
        ):
            out.skipped.append(
                ("Annual_National", f"{name} {year}", "no matching national indicator")
            )
            continue
        code, unit, step = NATIONAL[name]
        value = _number(r.get("Value"))
        if value is None:
            out.skipped.append(("Annual_National", f"{name} {year}", "no value"))
            continue
        out.add(
            r.get("Official / primary URL", "").strip(),
            {
                "indicator_code": code,
                "area_code": "OM",
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "frequency": "annual",
                "period_complete": "true",
                "unit_code": unit,
                "value": format(value.normalize(), "f"),
                "_step": step,
                "quality_status": "accepted",
                "revision_status": "reported",
                "source_locator": "NCSI data portal: electricity",
                "note": r.get("Critical note", "").strip(),
            },
        )


_INTERIM_PERIOD = re.compile(r"^(\d{4})-(\d{2}) through (\d{4})-(\d{2})$")


def interim(rows: list[dict[str, str]], out: Mapped) -> None:
    """2026_Interim: national figures for part of 2026, never a full year."""
    for r in rows:
        name = r.get("Indicator", "").strip()
        match = _INTERIM_PERIOD.match(r.get("Actual observation period", "").strip())
        if (
            name not in INTERIM
            or match is None
            or r.get("Geographic level", "").strip() != "national"
        ):
            out.skipped.append(("2026_Interim", name, "no matching indicator or period"))
            continue
        y1, m1, y2, m2 = (int(g) for g in match.groups())
        if m1 != 1 or y1 != y2 or m2 >= 12:
            # Only a year to date (January to a month before December) is a partial year here.
            out.skipped.append(("2026_Interim", name, "not a year to date from January"))
            continue
        code, unit = INTERIM[name]
        last_day = calendar.monthrange(y2, m2)[1]
        value = _number(r.get("Value"))
        if value is None:
            out.skipped.append(("2026_Interim", name, "no value"))
            continue
        out.add(
            r.get("Source URL", "").strip(),
            {
                "indicator_code": code,
                "area_code": "OM",
                "period_start": f"{y1}-{m1:02d}-01",
                "period_end": f"{y2}-{m2:02d}-{last_day:02d}",
                "frequency": "annual",
                "period_complete": "false",
                "unit_code": unit,
                "value": format(value.normalize(), "f"),
                "quality_status": "accepted",
                "revision_status": "preliminary",
                "source_locator": "Preliminary figures for part of 2026",
                "note": f"January to {calendar.month_name[m2]} {y2} only, not the year. "
                f"{r.get('Definition/caveat', '').strip()}",
            },
        )


def coverage(rows: list[dict[str, str]]) -> dict[str, int]:
    """Axis_Coverage_252: how many (wilayat, axis) statuses there are, by status."""
    counts: dict[str, int] = {}
    for r in rows:
        status = r.get("Verified status", "").strip()
        if status:
            counts[status] = counts.get(status, 0) + 1
    return counts


def national_total(mapped: Mapped, year: str) -> Decimal:
    """The sum of the wilayat populations staged for a year (the reconciliation check)."""
    return sum(
        (
            Decimal(r["value"])
            for rows in mapped.rows.values()
            for r in rows
            if r["indicator_code"] == "POP_TOTAL" and r["period_start"].startswith(year)
        ),
        Decimal(0),
    )
