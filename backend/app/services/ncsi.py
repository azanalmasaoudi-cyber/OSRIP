"""Convert NCSI data-portal exports (data.gov.om) into OSRIP import files. Pure.

The output is an ordinary OSRIP import CSV. It still goes through upload, mapping,
validation, error review, explicit approval and publication; nothing here publishes.

Rules applied while converting:
* only periods from January 2022 onward are kept (platform scope);
* an annual value for the current (unfinished) year, or later, is skipped: a partial
  year is never presented as a complete year;
* regions are matched to registry codes by exact NCSI spellings only. Unknown names
  (for example the pre-2011 "Ash Sharqiyah") are reported, never guessed;
* indicators are converted only through an explicit mapping written by a data
  manager (NCSI indicator name -> OSRIP indicator code and unit). Nothing is
  mapped by similar wording;
* values are copied as text, never rounded or rescaled unless the mapping states a
  scale factor; empty values stay empty (missing, never zero).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.imports.validation import STATISTICAL_SCOPE_START

# NCSI portal spellings (data.gov.om, Electricity dataset region list, read 2026-09-25)
# -> OSRIP registry codes. Governorates first, then wilayats.
REGION_CODES: dict[str, str] = {
    "Oman": "OM",
    "Muscat": "OM-MA",
    "Dhofar": "OM-ZU",
    "Musandam": "OM-MU",
    "Al Buraymi": "OM-BU",
    "Ad Dakhliyah": "OM-DA",
    "Al Batinah North": "OM-BS",
    "Al Batinah South": "OM-BJ",
    "Ash Sharqiyah South": "OM-SJ",
    "Ash Sharqiyah North": "OM-SS",
    "Adh Dhahirah": "OM-ZA",
    "Al Wusta": "OM-WU",
    "Wilayat Muscat": "OM-MA-01",
    "Wilayat Al Amrat": "OM-MA-02",
    "Wilayat As Seeb": "OM-MA-03",
    "Wilayat Bawshar": "OM-MA-04",
    "Wilayat Mutrah": "OM-MA-05",
    "Wilayat Qurayyat": "OM-MA-06",
    "Wilayat Salalah": "OM-ZU-01",
    "Wilayat Al Mazyunah": "OM-ZU-02",
    "Wilayat Dalkut": "OM-ZU-03",
    "Wilayat Mirbat": "OM-ZU-04",
    "Wilayat Muqshin": "OM-ZU-05",
    "Wilayat Rakhyut": "OM-ZU-06",
    "Wilayat Sadah": "OM-ZU-07",
    "Wilayat Shalim Wa Juzor Al Hallaniyat": "OM-ZU-08",
    "Wilayat Taqah": "OM-ZU-09",
    "Wilayat Thumrayt": "OM-ZU-10",
    "Wilayat Khasab": "OM-MU-01",
    "Wilayat Bukha": "OM-MU-02",
    "Wilayat Daba": "OM-MU-03",
    "Wilayat Madha": "OM-MU-04",
    "Wilayat Al Buraymi": "OM-BU-01",
    "Wilayat As Sunaynah": "OM-BU-02",
    "Wilayat Mahadah": "OM-BU-03",
    "Wilayat Nizwa": "OM-DA-01",
    "Wilayat Adam": "OM-DA-02",
    "Wilayat Al Hamra": "OM-DA-03",
    "Wilayat Bahla": "OM-DA-04",
    "Wilayat Bidbid": "OM-DA-05",
    "Wilayat Izki": "OM-DA-06",
    "Wilayat Manah": "OM-DA-07",
    "Wilayat Samail": "OM-DA-08",
    "Wilayat Al Jabal Al Akhdar": "OM-DA-09",
    "Wilayat Sohar": "OM-BS-01",
    "Wilayat Al Khaburah": "OM-BS-02",
    "Wilayat As Suwayq": "OM-BS-03",
    "Wilayat Liwa": "OM-BS-04",
    "Wilayat Saham": "OM-BS-05",
    "Wilayat Shinas": "OM-BS-06",
    "Wilayat Ar Rustaq": "OM-BJ-01",
    "Wilayat Al Awabi": "OM-BJ-02",
    "Wilayat Al Musanaah": "OM-BJ-03",
    "Wilayat Barka": "OM-BJ-04",
    "Wilayat Nakhal": "OM-BJ-05",
    "Wilayat Wadi Al Maawil": "OM-BJ-06",
    "Wilayat Ibri": "OM-ZA-01",
    "Wilayat Dank": "OM-ZA-02",
    "Wilayat Yanqul": "OM-ZA-03",
    "Wilayat Ibra": "OM-SS-01",
    "Wilayat Bidiyah": "OM-SS-02",
    "Wilayat Al Qabil": "OM-SS-03",
    "Wilayat Al Mudaybi": "OM-SS-04",
    "Wilayat Dama Wa At Taiyin": "OM-SS-05",
    "Wilayat Wadi Bani Khalid": "OM-SS-06",
    "Wilayat Sinaw": "OM-SS-07",
    "Wilayat Sur": "OM-SJ-01",
    "Wilayat Al Kamil Wa Al Wafi": "OM-SJ-02",
    "Wilayat Jaalan Bani Bu Ali": "OM-SJ-03",
    "Wilayat Jaalan Bani Bu Hasan": "OM-SJ-04",
    "Wilayat Masirah": "OM-SJ-05",
    "Wilayat Hayma": "OM-WU-01",
    "Wilayat Al Jazir": "OM-WU-02",
    "Wilayat Ad Duqm": "OM-WU-03",
    "Wilayat Mahawt": "OM-WU-04",
}

OUTPUT_HEADER = [
    "indicator_code",
    "area_code",
    "period_start",
    "period_end",
    "frequency",
    "unit_code",
    "value",
    "period_complete",
]

_MONTHLY = re.compile(r"^(\d{4})[-M ]?(\d{1,2})$")
_QUARTERLY = re.compile(r"^(\d{4})[- ]?Q([1-4])$", re.IGNORECASE)
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


@dataclass(frozen=True, slots=True)
class Period:
    start: date
    end: date
    frequency: str


def _month_end(y: int, m: int) -> date:
    import calendar

    return date(y, m, calendar.monthrange(y, m)[1])


def parse_period(raw: str, frequency_hint: str | None = None) -> Period | None:
    """'2023' (annual), '2023M04' / '2023-04' (monthly), '2023Q2' (quarterly), ISO dates."""
    text = raw.strip()
    hint = (frequency_hint or "").strip().lower()
    if re.fullmatch(r"\d{4}", text):
        y = int(text)
        return Period(date(y, 1, 1), date(y, 12, 31), "annual")
    if m := _QUARTERLY.match(text):
        y, q = int(m.group(1)), int(m.group(2))
        return Period(date(y, 3 * q - 2, 1), _month_end(y, 3 * q), "quarterly")
    if m := _MONTHLY.match(text):
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return Period(date(y, mo, 1), _month_end(y, mo), "monthly")
    if m := _ISO.match(text):
        y, mo = int(m.group(1)), int(m.group(2))
        if hint.startswith("a"):
            return Period(date(y, 1, 1), date(y, 12, 31), "annual")
        if hint.startswith("q"):
            q = (mo - 1) // 3 + 1
            return Period(date(y, 3 * q - 2, 1), _month_end(y, 3 * q), "quarterly")
        return Period(date(y, mo, 1), _month_end(y, mo), "monthly")
    return None


@dataclass(slots=True)
class Conversion:
    rows: list[list[str]] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    unmapped_indicators: set[str] = field(default_factory=set)
    unknown_regions: set[str] = field(default_factory=set)
    inventory: dict[tuple[str, str, str], int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def csv_text(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(OUTPUT_HEADER)
        writer.writerows(self.rows)
        return buffer.getvalue()


def convert(
    text: str,
    mapping: dict[str, Any],
    *,
    columns: dict[str, str],
    today: date,
) -> Conversion:
    """``columns`` names the input columns: indicator, region, date, value, and optionally
    frequency and unit. ``mapping['indicators']`` maps NCSI indicator names to
    ``{"code": OSRIP code, "unit": OSRIP unit code, "scale": optional multiplier}``."""
    out = Conversion()
    indicators: dict[str, dict[str, Any]] = mapping.get("indicators", {})
    for record in csv.DictReader(io.StringIO(text)):
        name = (record.get(columns["indicator"]) or "").strip()
        region = (record.get(columns["region"]) or "").strip()
        unit_in = (record.get(columns.get("unit", ""), "") or "").strip()
        out.inventory[(name, region, unit_in)] = out.inventory.get((name, region, unit_in), 0) + 1
        target = indicators.get(name)
        if target is None:
            out.unmapped_indicators.add(name)
            out.skip("indicator_not_mapped")
            continue
        area = REGION_CODES.get(region)
        if area is None:
            out.unknown_regions.add(region)
            out.skip("region_not_in_registry")
            continue
        period = parse_period(
            record.get(columns["date"]) or "", record.get(columns.get("frequency", ""), None)
        )
        if period is None:
            out.skip("unreadable_period")
            continue
        if period.start < STATISTICAL_SCOPE_START:
            out.skip("before_2022")
            continue
        if period.frequency == "annual" and period.start.year >= today.year:
            out.skip("annual_value_for_unfinished_year")
            continue
        if period.end >= today:
            out.skip("period_not_finished")
            continue
        raw_value = (record.get(columns["value"]) or "").strip().replace(",", "")
        value = ""
        if raw_value:
            try:
                number = Decimal(raw_value)
            except InvalidOperation:
                out.skip("unreadable_value")
                continue
            scale = Decimal(str(target.get("scale", 1)))
            value = format(number * scale, "f") if scale != 1 else raw_value
        out.rows.append(
            [
                target["code"],
                area,
                period.start.isoformat(),
                period.end.isoformat(),
                period.frequency,
                target["unit"],
                value,
                "true",
            ]
        )
    return out
