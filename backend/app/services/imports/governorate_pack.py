# ruff: noqa: E501 - source tables, totals and notes are kept on one line each, as in services/studies.py
"""The owner's governorate evidence pack of 23 November 2026
(``OSRIP_Oman_11_Governorates_63_Wilayats_Official_Data_2026.xlsx``) as import rows for the
reviewed import workflow (stage, validate, approve, publish). The pack is research evidence, not
an approved import: every figure mapped here was checked against the NCSI publications it cites
(the reconciliation totals below are those publications' own totals), and nothing is published
without a data manager's approval.

* ``Governorates 2025``: full calendar year 2025 by governorate from the Statistical Year Book
  2026 (Issue 54): gross electricity production and distribution (Table 3-8, provisional), water
  production and distribution (Table 6-8, provisional), dates (tonnes; the yearbook marks the
  quantity as estimated) and honey (kilograms) (Table 4-5). The yearbook's "Other" electricity
  production (outside the 11 governorates) goes to its own reporting group. The count of
  enterprises of all economic activities (Table 6-9) is NOT imported: it is business context,
  not trade values or trade registrations, and the registry has no indicator for it.
* ``Fishery 2025``: artisanal (traditional) fish landings in the six regions the yearbook
  publishes (Table 6-5); Al Batinah North and South stay one combined figure.
* ``Latest 2026``: January-October 2026 gross electricity and water production and
  January-September 2026 merchandise exports from the Monthly Statistical Bulletin, November
  2026 (Tables 21, 22 and 5), with the same months of 2025. Years to date, never full years;
  grouped regions stay grouped (reporting groups), never shared out among governorates.
* ``Wilayats 63``: the governorate of each wilayat, checked against the registry; not data.

Nothing is estimated: a governorate or wilayat without a published figure stays without one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .owner_workbooks import Mapped, _number, _step

YEARBOOK = (
    "https://api.ncsi.gov.om/uploads/pdfs/statistical_year_book_2026___issue_54_1777963604.pdf"
)
BULLETIN = "https://api.ncsi.gov.om/uploads/pdfs/monthly_statistical_bulletin__november_2026_1795081756.pdf"

# Governorates by the pack's English and Arabic names (both must agree).
GOVERNORATES = {
    "Muscat": ("OM-MA", "مسقط"),
    "Dhofar": ("OM-ZU", "ظفار"),
    "Musandam": ("OM-MU", "مسندم"),
    "Al Buraimi": ("OM-BU", "البريمي"),
    "Ad Dakhliyah": ("OM-DA", "الداخلية"),
    "Al Batinah North": ("OM-BS", "شمال الباطنة"),
    "Al Batinah South": ("OM-BJ", "جنوب الباطنة"),
    "Ash Sharqiyah South": ("OM-SJ", "جنوب الشرقية"),
    "Ash Sharqiyah North": ("OM-SS", "شمال الشرقية"),
    "Adh Dhahirah": ("OM-ZA", "الظاهرة"),
    "Al Wusta": ("OM-WU", "الوسطى"),
}

# Governorates 2025 columns (header text with its line breaks removed) -> indicator, unit, table.
ANNUAL_2025 = {
    "Electricity gross production GWh 2025": ("ELEC_GROSS_GENERATION", "GWh", "Table 3-8"),
    "Electricity distribution GWh 2025": ("ELEC_DISTRIBUTION", "GWh", "Table 3-8"),
    "Water production million m3 2025": ("WATER_PRODUCTION", "million_m3", "Table 6-8"),
    "Water distribution million m3 2025": ("WATER_DISTRIBUTION", "million_m3", "Table 6-8"),
    "Dates production Ton 2025": ("AGRI_PROD_DATES", "tonne", "Table 4-5"),
    "Honey production kg 2025": ("AGRI_PROD_HONEY", "kg", "Table 4-5"),
}
NOT_IMPORTED_2025 = {
    "All-sector active enterprises 2025 (NOT trade value)": (
        "enterprises of all economic activities (Statistical Year Book 2026, Table 6-9): business "
        "context, not trade values or trade registrations; the registry has no indicator for it, "
        "so it is kept in the evidence report only"
    ),
}
NOTES_2025 = {
    "ELEC_GROSS_GENERATION": "Gross production by governorate, 2025 (provisional). Production in a "
    "governorate is not its consumption: power moves between governorates.",
    "ELEC_DISTRIBUTION": "Electricity distributed in the governorate, 2025 (provisional).",
    "WATER_PRODUCTION": "Production = wells + water received from the main network and small "
    "desalination plants (yearbook note); Muscat includes the Barka plants. 2025 provisional. "
    "Production minus distribution is not reported as losses.",
    "WATER_DISTRIBUTION": "Water distributed in the governorate, 2025 (provisional).",
    "AGRI_PROD_DATES": "The yearbook states that the quantity of dates production is estimated.",
    "AGRI_PROD_HONEY": "Honey production in kilograms, 2025.",
}
REVISION_2025 = {"AGRI_PROD_DATES": "estimate", "AGRI_PROD_HONEY": "reported"}

# Fishery 2025 regions as published -> area (Al Batinah is one combined figure).
FISHERY_REGIONS = {
    "Musandam": "OM-MU",
    "Al Batinah": "OM-GRP-BATINAH",
    "Muscat": "OM-MA",
    "Ash Sharqiyah South": "OM-SJ",
    "Al Wusta": "OM-WU",
    "Dhofar": "OM-ZU",
    "TOTAL ARTISANAL": "OM",
}

# Latest 2026 geographic scopes as published -> area (grouped regions are reporting groups).
SCOPES_2026 = {
    ("Electricity", "Oman"): "OM",
    ("Electricity", "Muscat"): "OM-MA",
    ("Electricity", "Dhofar"): "OM-ZU",
    ("Electricity", "Musandam"): "OM-MU",
    ("Electricity", "Ad Dakhliyah"): "OM-DA",
    ("Electricity", "Al Batinah (N+S) plus Adh Dhahirah"): "OM-GRP-BATINAH-DHAHIRAH",
    ("Electricity", "Ash Sharqiyah (N+S)"): "OM-GRP-SHARQIYAH",
    ("Electricity", "Al Wusta"): "OM-WU",
    ("Electricity", "Other areas"): "OM-GRP-OTHER-ELEC",
    ("Water", "Oman"): "OM",
    ("Water", "Muscat"): "OM-MA",
    ("Water", "Dhofar"): "OM-ZU",
    ("Water", "Other governorates (combined)"): "OM-GRP-OTHER-WATER",
    ("Trade", "Oman"): "OM",
}
INDICATORS_2026 = {
    ("Electricity", "Gross generation"): ("ELEC_GROSS_GENERATION", {"GWh": "GWh"}, "Table 21"),
    ("Water", "Production"): ("WATER_PRODUCTION", {"1000 m3": "thousand_m3"}, "Table 22"),
    ("Trade", "Merchandise exports"): (
        "TRADE_MERCH_EXPORTS",
        {"Million OMR": "million_OMR"},
        "Table 5",
    ),
}
_PERIOD_2026 = re.compile(r"^(\d{4})-(\d{2}) to (\d{4})-(\d{2})$")
_MONTH_END = {"09": "30", "10": "31"}

# The NCSI publications' own totals, read from the PDFs on 23 November 2026, which the sum of
# the staged areas must match within the rounding of its terms.
PUBLISHED_TOTALS = {
    ("ELEC_GROSS_GENERATION", "2025"): (Decimal("50973.5"), "Year Book 2026 Table 3-8 total (11 governorates and Other)"),
    ("ELEC_DISTRIBUTION", "2025"): (Decimal("45033.1"), "Year Book 2026 Table 3-8 total"),
    ("WATER_PRODUCTION", "2025"): (Decimal("508.1"), "Year Book 2026 Table 6-8 total"),
    ("WATER_DISTRIBUTION", "2025"): (Decimal("344.6"), "Year Book 2026 Table 6-8 total"),
    ("AGRI_PROD_DATES", "2025"): (Decimal("405997"), "Year Book 2026 Table 4-5 total"),
    ("AGRI_PROD_HONEY", "2025"): (Decimal("934443"), "Year Book 2026 Table 4-5 total"),
    ("FISH_LANDINGS_TRADITIONAL", "2025"): (Decimal("715745"), "Year Book 2026 Table 6-5 total"),
    ("ELEC_GROSS_GENERATION", "2026-ytd"): (Decimal("47842.9"), "Bulletin Nov 2026 Table 21 total, Jan-Oct 2026"),
    ("WATER_PRODUCTION", "2026-ytd"): (Decimal("417201.4"), "Bulletin Nov 2026 Table 22 total, Jan-Oct 2026"),
}  # fmt: skip


def _key(header: str) -> str:
    return " ".join(str(header).split())


def _rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{_key(k): (v if isinstance(v, str) else str(v)) for k, v in r.items()} for r in rows]


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


@dataclass
class Checks:
    """What the mapping found: sums against the publications' totals, and the registry match."""

    sums: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    # The rounding allowed: half of each term's last written digit, added up.
    tolerances: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    wilayats_matched: int = 0
    wilayat_problems: list[str] = field(default_factory=list)

    def add(self, key: tuple[str, str], value: Decimal, step: Decimal) -> None:
        self.sums[key] = self.sums.get(key, Decimal(0)) + value
        self.tolerances[key] = self.tolerances.get(key, Decimal(0)) + step / 2

    def reconciliation(self) -> list[tuple[str, Decimal, Decimal, Decimal, bool, str]]:
        """(what, sum of areas, published total, tolerance, agrees, where the total is from)."""
        out = []
        for key, (total, where) in PUBLISHED_TOTALS.items():
            if key not in self.sums:
                continue
            tolerance = self.tolerances[key]
            agrees = abs(self.sums[key] - total) <= tolerance
            out.append((f"{key[0]} {key[1]}", self.sums[key], total, tolerance, agrees, where))
        return out


def annual_2025(rows: list[dict[str, str]], out: Mapped, checks: Checks) -> None:
    """Governorates 2025: six indicators for each of the 11 governorates, and Other electricity."""
    for r in _rows(rows):
        en, ar = r.get("Governorate", "").strip(), r.get("المحافظة", "").strip()
        if ar == "Warning":
            # The yearbook's "Other" production row, given in the pack as a warning sentence.
            m = re.search(r"'Other' category \(([\d.]+) GWh\)", en)
            if m:
                value = Decimal(m.group(1))
                checks.add(("ELEC_GROSS_GENERATION", "2025"), value, Decimal(_step(m.group(1), 1)))
                out.add(YEARBOOK, _row(
                    "ELEC_GROSS_GENERATION", "OM-GRP-OTHER-ELEC", "2025-01-01", "2025-12-31", True, "GWh",
                    value, m.group(1), "accepted", "provisional",
                    "Statistical Year Book 2026, Issue 54, Table 3-8 (Other)",
                    "Production outside the 11 governorates ('Other' in the yearbook), 2025 "
                    "(provisional); never assigned to a governorate or wilayat.",
                ))  # fmt: skip
            continue
        if en not in GOVERNORATES:
            continue
        code, arabic = GOVERNORATES[en]
        if ar and ar != arabic:
            out.skipped.append(
                ("Governorates 2025", en, f"Arabic name '{ar}' does not match '{arabic}'")
            )
            continue
        if "full calendar year" not in r.get("Reporting period", ""):
            out.skipped.append(("Governorates 2025", en, "not a full calendar year"))
            continue
        for column, why in NOT_IMPORTED_2025.items():
            if _number(r.get(column)) is not None:
                out.skipped.append(("Governorates 2025", f"{en}: {column}", why))
        for column, (indicator, unit, table) in ANNUAL_2025.items():
            raw = r.get(column)
            value = _number(raw)
            if value is None:
                out.skipped.append(("Governorates 2025", f"{en}: {column}", "no value"))
                continue
            checks.add((indicator, "2025"), value, Decimal(_step(raw, 1)))
            out.add(YEARBOOK, _row(
                indicator, code, "2025-01-01", "2025-12-31", True, unit, value, raw, "accepted",
                REVISION_2025.get(indicator, "provisional"),
                f"Statistical Year Book 2026, Issue 54, {table}", f"{en}, 2025. {NOTES_2025[indicator]}",
            ))  # fmt: skip


def fishery_2025(rows: list[dict[str, str]], out: Mapped, checks: Checks) -> None:
    """Fishery 2025: artisanal landings in the six published regions, and their total."""
    for r in _rows(rows):
        region = r.get("Region as published", "").strip()
        code = FISHERY_REGIONS.get(region)
        raw = r.get("Traditional fishing 2025 (ton)")
        value = _number(raw)
        if code is None or value is None:
            if region:
                out.skipped.append(("Fishery 2025", region, "not a published region"))
            continue
        if code != "OM":
            checks.add(("FISH_LANDINGS_TRADITIONAL", "2025"), value, Decimal(_step(raw, 1)))
        note = (
            "Al Batinah North and South as one published figure; never split between them."
            if code == "OM-GRP-BATINAH"
            else "Artisanal (traditional) fishing only, not all fish production or aquaculture."
        )
        out.add(YEARBOOK, _row(
            "FISH_LANDINGS_TRADITIONAL", code, "2025-01-01", "2025-12-31", True, "tonne", value, raw,
            "accepted", "provisional", "Statistical Year Book 2026, Issue 54, Table 6-5",
            f"{region}, 2025. {note}",
        ))  # fmt: skip


def latest_2026(rows: list[dict[str, str]], out: Mapped, checks: Checks) -> None:
    """Latest 2026: years to date as published, and the same months of 2025."""
    for r in _rows(rows):
        sector, name = r.get("Sector", "").strip(), r.get("Indicator", "").strip()
        scope = r.get("Geographic scope as published", "").strip()
        spec = INDICATORS_2026.get((sector, name))
        area = SCOPES_2026.get((sector, scope))
        match = _PERIOD_2026.match(r.get("Period", "").strip())
        if spec is None or area is None or match is None:
            if sector:
                out.skipped.append(
                    (
                        "Latest 2026",
                        f"{sector} {name} {scope}",
                        "no matching indicator, area or period",
                    )
                )
            continue
        indicator, units, table = spec
        unit = units.get(r.get("Unit", "").strip())
        y1, m1, y2, m2 = match.groups()
        if unit is None or m1 != "01" or y1 != y2 or m2 not in _MONTH_END:
            out.skipped.append(
                ("Latest 2026", f"{sector} {name} {scope}", "unit or period not as expected")
            )
            continue
        end = f"{_MONTH_END[m2]}"
        months = "January-October" if m2 == "10" else "January-September"
        grouped = area.startswith("OM-GRP-")
        note = (f"{months} {y1} only, not the year. "
                + ("A published regional group; never shared out among its governorates. " if grouped else "")
                + r.get("Coverage / quality note", "").strip())  # fmt: skip
        for year, raw, revision in (
            (y1, r.get("Value"), "preliminary"),
            (str(int(y1) - 1), r.get("Comparison 2025 same period"), "provisional"),
        ):
            value = _number(raw)
            if value is None:
                continue
            if (
                year == y1
                and area != "OM"
                and indicator in ("ELEC_GROSS_GENERATION", "WATER_PRODUCTION")
            ):
                checks.add((indicator, "2026-ytd"), value, Decimal(_step(raw, 1)))
            out.add(BULLETIN, _row(
                indicator, area, f"{year}-01-01", f"{year}-{m2}-{end}", False, unit, value, raw,
                "accepted", revision, f"Monthly Statistical Bulletin, November 2026, {table}",
                note if year == y1 else f"Same months of {year}, for comparison: {months} only.",
            ))  # fmt: skip


def _words(name: str) -> frozenset[str]:
    """An Arabic name's words in any order, each without a leading 'and' (و)."""
    from .wilayat_evidence import arabic_key

    return frozenset(
        arabic_key(w[1:] if w.startswith("و") and len(w) > 2 else w) for w in name.split()
    )


def _match_wilayat(registry, areas: list, gov: str | None, name_ar: str, name_en: str = ""):  # noqa: ANN001, ANN202
    """The registry's wilayat for a name inside a stated governorate: by the Arabic name, else by
    the English name or the same Arabic words in another order, both only inside that
    governorate; never across governorates."""
    found = registry.wilayat(name_ar, gov, name_en)
    if found is None and gov:
        same = [
            a
            for a in areas
            if a.level == "wilayat"
            and a.parent_code == gov
            and _words(a.name_ar) == _words(name_ar)
        ]
        found = same[0] if len(same) == 1 else None
    return found


def wilayats_63(rows: list[dict[str, str]], areas: list, checks: Checks) -> None:  # noqa: ANN001
    """Wilayats 63: each wilayat's governorate as the registry has it (no observations)."""
    from .wilayat_evidence import Registry

    registry = Registry(areas)
    for r in _rows(rows):
        gov_en = r.get("Governorate English", "").strip()
        name_ar, name_en = r.get("Wilayat Arabic", "").strip(), r.get("Wilayat English", "").strip()
        if not name_ar:
            continue
        gov = GOVERNORATES.get(gov_en, (None,))[0]
        found = _match_wilayat(registry, areas, gov, name_ar, name_en)
        if found is None:
            checks.wilayat_problems.append(
                f"{name_ar} / {name_en} ({gov_en}): not found in the registry inside that governorate"
            )
        elif found.parent_code != gov:
            checks.wilayat_problems.append(
                f"{name_ar}: the pack puts it in {gov_en}, the registry in {found.parent_code}"
            )
        else:
            checks.wilayats_matched += 1


RECORDS = "https://www.opendata.gov.om/en/datasets/98748181-c3cc-41e3-afcf-abf8ec7dcd33"
# The ministry's spellings the registry writes differently, each inside its governorate only:
# Daba is officially Dibba Al-Bay'ah (دبا البيعة); Liwa is written لوى and ليوا.
RECORD_ALIASES = {("OM-MU", "دبا البيعة"): "OM-MU-03", ("OM-BS", "لوى"): "OM-BS-04"}
_GOVERNORATE_AR = {arabic: code for code, arabic in GOVERNORATES.values()}


@dataclass
class Records:
    """The ministry's records as mapped: wilayats matched, the total, and the problems found."""

    matched: set[str] = field(default_factory=set)
    total: int = 0
    by_governorate: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def commercial_records(rows: list[dict[str, str]], areas: list, out: Mapped) -> Records:  # noqa: ANN001
    """The Ministry of Commerce, Industry and Investment Promotion's active commercial records at
    the end of 2025 (cumulative), published by legal form, governorate and wilayat (open data,
    February 2026). Each wilayat's records on record are its legal forms' counts added together
    (counts of the same date); nothing is estimated and no governorate total is staged as an
    observation. Business registrations, not trade values and not enterprises."""
    from .wilayat_evidence import Registry, arabic_key

    registry = Registry(areas)
    result = Records()
    sums: dict[str, int] = {}
    forms: dict[str, set[str]] = {}
    for r in _rows(rows):
        count, form = str(r.get("العدد", "")).strip(), str(r.get("الشكل القانوني", "")).strip()
        gov_name = str(r.get("المحافظة", "")).strip().removeprefix("محافظة").strip()
        name_ar, status = str(r.get("ولاية", "")).strip(), str(r.get("حالة السجل", "")).strip()
        if not count or not count.isdigit():
            continue
        if status != "نشط":
            result.problems.append(f"{name_ar}: status '{status}' is not active")
            continue
        gov = _GOVERNORATE_AR.get(gov_name)
        found = _match_wilayat(registry, areas, gov, name_ar) if gov else None
        if found is None and gov:
            alias = next(
                (
                    code
                    for (g, n), code in RECORD_ALIASES.items()
                    if g == gov and arabic_key(n) == arabic_key(name_ar)
                ),
                None,
            )
            found = registry.by_code.get(alias) if alias else None
        if found is None:
            result.problems.append(
                f"{name_ar} ({gov_name}): not found in the registry inside that governorate"
            )
            continue
        sums[found.code] = sums.get(found.code, 0) + int(count)
        forms.setdefault(found.code, set()).add(form)
        result.by_governorate[gov] = result.by_governorate.get(gov, 0) + int(count)
        result.total += int(count)
    result.matched = set(sums)
    for code in sorted(sums):
        out.add(RECORDS, _row(
            "TRADE_COMMERCIAL_REGISTRATIONS_STOCK", code, "2025-01-01", "2025-12-31", True, "registration",
            Decimal(sums[code]), str(sums[code]), "accepted", "reported",
            "Ministry of Commerce, Industry and Investment Promotion open data: active registered commercial "
            "records up to the end of 2025 (cumulative)",
            f"Active commercial records on record at the end of 2025, {len(forms[code])} legal forms added "
            "together as published. Business registrations: not trade values, not enterprises.",
        ))  # fmt: skip
    return result


def _row(
    indicator: str, area: str, start: str, end: str, complete: bool, unit: str, value: Decimal, raw: object,
    quality: str, revision: str, locator: str, note: str,
) -> dict[str, str]:  # fmt: skip
    return {
        "indicator_code": indicator,
        "area_code": area,
        "period_start": start,
        "period_end": end,
        "frequency": "annual",
        "period_complete": "true" if complete else "false",
        "unit_code": unit,
        "value": _text(value),
        "_step": _step(raw, 1),
        "quality_status": quality,
        "revision_status": revision,
        "source_locator": locator,
        "note": note,
    }
