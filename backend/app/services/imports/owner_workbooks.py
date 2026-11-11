"""The owner's statistics workbooks of November 2026, as rows for the controlled import.

Two workbooks were supplied with the rewritten academic booklet:

* ``OSRIP_Oman_Annual_Research_Published_2026.xlsx``: complete calendar years 2021-2025 from the
  NCSI Statistical Year Book 2026 (Issue 54), national; 2025 is provisional.
* ``OSRIP_2026_Latest_Statistics_Through_October.xlsx``: the newest preliminary 2026 figures,
  each for its own period (electricity and water January-September, trade January-August,
  fisheries January-June), with the matching 2025 period, and governorate figures.

This module only maps workbook rows onto the import's canonical columns (imports/validation.py);
it never publishes. Every row keeps its exact period: a partial year is ``period_complete``
false and never a full year. Nothing is assigned to a wilayat; a combined reporting area (for
example "North/South Al Batinah + Ad Dhahirah") is never split into governorates; figures with
no indicator in the registry (population, consumer prices, fish exports, total trade exchange,
imports including unrecorded ones) are listed as not imported, with the reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

COLUMNS = (
    "indicator_code", "area_code", "period_start", "period_end", "frequency", "period_complete",
    "flow", "unit_code", "value", "value_operator", "quality_status", "revision_status",
    "source_locator", "note",
)  # fmt: skip

# Annual_Long "Indicator EN" -> (indicator code, unit code, multiplier to that unit).
ANNUAL = {
    "Electricity production": ("ELEC_GROSS_GENERATION", "GWh", 1),
    "Electricity distribution": ("ELEC_DISTRIBUTION", "GWh", 1),
    "Net actual electricity consumption": ("ELEC_CONSUMPTION", "GWh", 1),
    "Residential electricity consumption": ("ELEC_CONSUMPTION_RESIDENTIAL", "GWh", 1),
    "Commercial electricity consumption": ("ELEC_CONSUMPTION_COMMERCIAL", "GWh", 1),
    "Industrial electricity consumption": ("ELEC_CONSUMPTION_INDUSTRIAL", "GWh", 1),
    "Electricity connections": ("ELEC_CONNECTIONS", "thousand_connections", 1),
    "Installed generation capacity": ("ELEC_INSTALLED_CAPACITY", "MW", 1),
    "Water production": ("WATER_PRODUCTION", "million_m3", 1),
    "Water distribution": ("WATER_DISTRIBUTION", "million_m3", 1),
    "Water connections": ("WATER_CONNECTIONS", "thousand_connections", 1),
    "Cultivated area estimate": ("AGRI_CULTIVATED_AREA", "feddan", 1000),
    "Crop production estimate": ("AGRI_CROP_PRODUCTION", "thousand_tonnes", 1),
    "Cattle estimate": ("LIVESTOCK_CATTLE", "thousand_head", 1),
    "Camel estimate": ("LIVESTOCK_CAMELS", "thousand_head", 1),
    "Sheep estimate": ("LIVESTOCK_SHEEP", "thousand_head", 1),
    "Goat estimate": ("LIVESTOCK_GOATS", "thousand_head", 1),
    "Artisanal fishing": ("FISH_LANDINGS_TRADITIONAL", "tonne", 1),
    "Commercial fishing": ("FISH_LANDINGS_COMMERCIAL", "tonne", 1),
    "Coastal fishing": ("FISH_LANDINGS_COASTAL", "tonne", 1),
    "Merchandise imports (recorded)": ("TRADE_MERCH_IMPORTS", "million_OMR", 1),
    "Merchandise exports": ("TRADE_MERCH_EXPORTS", "million_OMR", 1),
    "Non-oil merchandise exports": ("TRADE_NON_OIL_EXPORTS", "million_OMR", 1),
    "Re-exports": ("TRADE_REEXPORTS", "million_OMR", 1),
    "Published trade balance": ("TRADE_BALANCE_REPORTED", "million_OMR", 1),
}
# Trade indicators carry their flow, as the published series do.
FLOWS = {
    "TRADE_MERCH_IMPORTS": "import",
    "TRADE_NON_OIL_EXPORTS": "domestic_export",
    "TRADE_REEXPORTS": "re_export",
}
# Workbook figures with no matching indicator: why they are not imported.
NOT_IN_REGISTRY = {
    "Total registered population": "population is not an indicator of the four OSRIP axes",
    "Omani population": "population is not an indicator of the four OSRIP axes",
    "Expatriate population": "population is not an indicator of the four OSRIP axes",
    "Live births": "population is not an indicator of the four OSRIP axes",
    "Registered resident population": "population is not an indicator of the four OSRIP axes",
    "Fish landed / produced": "capture and aquaculture together; the registry holds capture "
    "landings by fishing method (imported) and has no aquaculture indicator",
    "Aquaculture": "the registry has no aquaculture indicator",
    "Fish exports (quantity)": "fish exports need a commodity and flow the workbook does not give",
    "Fish exports (value)": "fish exports need a commodity and flow the workbook does not give",
    "Merchandise imports (total)": "includes unrecorded imports; the registry's imports are the "
    "recorded imports (imported)",
    "Total merchandise trade exchange": "the registry has no trade-exchange total",
}

# Latest_2026 "Indicator" -> (indicator code, unit code, multiplier, value operator, quality, note).
LATEST = {
    "Total generation": ("ELEC_GROSS_GENERATION", "GWh", 1, "", "accepted", ""),
    "Net generation": ("ELEC_NET_GENERATION", "GWh", 1, "", "accepted", ""),
    "Total water production": ("WATER_PRODUCTION", "million_m3", 1, "", "accepted", ""),
    "Total goods exports": ("TRADE_MERCH_EXPORTS", "million_OMR", 1000, "~", "warning",
                            "Published rounded to OMR 0.1 billion; the release says exports "
                            "exceeded this value."),
    "Total goods imports": ("TRADE_MERCH_IMPORTS", "million_OMR", 1000, "~", "warning",
                            "Published rounded to OMR 0.1 billion; the release does not say "
                            "whether unrecorded imports are included."),
    "Trade balance surplus": ("TRADE_BALANCE_REPORTED", "million_OMR", 1000, "~", "warning",
                              "Published balance, rounded to OMR 0.1 billion; not recomputed "
                              "from rounded exports and imports."),
    "Oil & gas goods exports": ("TRADE_OIL_GAS_EXPORTS", "million_OMR", 1000, "~", "warning",
                                "Published rounded to OMR 0.1 billion."),
    "Non-oil merchandise exports": ("TRADE_NON_OIL_EXPORTS", "million_OMR", 1000, "~", "warning",
                                    "Published rounded to OMR 0.1 billion."),
    "Fish landings total": ("FISH_CAPTURE_LANDINGS", "tonne", 1, "", "accepted",
                            "Artisanal, coastal and commercial; excludes aquaculture."),
    "Fishing and aquaculture value": ("FISH_VALUE_INCL_AQUACULTURE", "thousand_OMR", 1000, "",
                                      "accepted", ""),
}  # fmt: skip
LATEST_NOT_IN_REGISTRY = "consumer price change, not production; the registry has no CPI indicator"

# Regions_2026 "Geographic coverage" -> governorate code; combined areas are never split.
GOVERNORATES = {
    "Muscat": "OM-MA",
    "Ad Dakhiliyah": "OM-DA",
    "Dhofar": "OM-ZU",
    "Al Wusta": "OM-WU",
    "Musandam": "OM-MU",
}
REGION_SECTORS = {
    "Electricity": ("ELEC_GROSS_GENERATION", "GWh"),
    "Water": ("WATER_PRODUCTION", "million_m3"),
}


@dataclass
class Mapped:
    """Candidate import rows (by source URL) and the workbook items not imported, with why."""

    rows: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    skipped: list[tuple[str, str, str]] = field(default_factory=list)  # (sheet, item, reason)

    def add(self, url: str, row: dict[str, str]) -> None:
        # ``_step``: the rounding of the figure as the workbook writes it, in the import unit
        # (for comparing with published figures; never written to the import file).
        kept = {c: row.get(c, "") for c in COLUMNS}
        kept["flow"] = FLOWS.get(kept["indicator_code"], "")
        if "_step" in row:
            kept["_step"] = row["_step"]
        self.rows.setdefault(url, []).append(kept)


def _number(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _scaled(raw: Any, multiplier: int) -> str | None:
    value = _number(raw)
    if value is None:
        return None
    return format((value * multiplier).normalize(), "f")


def _step(raw: Any, multiplier: int) -> str:
    """The rounding of a workbook figure in the import unit: 266 thousand feddan is written to
    the nearest 1,000 feddan; 18.3 billion OMR to the nearest 100 million."""
    value = _number(raw) or Decimal(0)
    exponent = value.normalize().as_tuple().exponent
    decimals = max(0, -exponent) if isinstance(exponent, int) else 0
    return format((Decimal(multiplier) / (Decimal(10) ** decimals)).normalize(), "f")


def annual(rows: list[dict[str, str]], out: Mapped) -> None:
    """Annual_Long: complete calendar years, national (2025 provisional)."""
    for r in rows:
        name, year, area = r.get("Indicator EN", ""), r.get("Year", ""), r.get("Area", "")
        if name in NOT_IN_REGISTRY:
            out.skipped.append(("Annual_Long", f"{name} {year}", NOT_IN_REGISTRY[name]))
            continue
        if name not in ANNUAL:
            out.skipped.append(("Annual_Long", f"{name} {year}", "no matching indicator"))
            continue
        if area != "Oman" or r.get("Period type") != "FULL_CALENDAR_YEAR":
            out.skipped.append(("Annual_Long", f"{name} {year}", "not a national full year"))
            continue
        code, unit, multiplier = ANNUAL[name]
        value = _scaled(r.get("Value"), multiplier)
        if value is None or not str(year).isdigit():
            out.skipped.append(("Annual_Long", f"{name} {year}", "no value"))
            continue
        out.add(r.get("Source URL", ""), {
            "indicator_code": code, "area_code": "OM", "period_start": f"{year}-01-01",
            "period_end": f"{year}-12-31", "frequency": "annual", "period_complete": "true",
            "unit_code": unit, "value": value, "quality_status": "accepted",
            "_step": _step(r.get("Value"), multiplier),
            "revision_status": "provisional" if year == "2025" else "reported",
            "source_locator": "Statistical Year Book 2026, Issue 54",
            "note": f"NCSI Statistical Year Book 2026: {name}"
            + (" (2025 provisional)" if year == "2025" else ""),
        })  # fmt: skip


def latest(rows: list[dict[str, str]], out: Mapped) -> None:
    """Latest_2026: each figure for its own 2026 period, and the matching 2025 period."""
    for r in rows:
        name = r.get("المؤشر / Indicator", "")
        if r.get("المحور / Axis") in ("Food security", "Population") and name not in LATEST:
            reason = (LATEST_NOT_IN_REGISTRY if r.get("المحور / Axis") == "Food security"
                      else NOT_IN_REGISTRY.get(name, "no matching indicator"))  # fmt: skip
            out.skipped.append(("Latest_2026", name, reason))
            continue
        if name not in LATEST:
            out.skipped.append(("Latest_2026", name, "no matching indicator"))
            continue
        code, unit, multiplier, operator, quality, note = LATEST[name]
        start, end = r.get("Jan / period start", ""), r.get("Period end", "")
        period = r.get("2026 reference period", "")
        url = r.get("Source URL", "")
        published = r.get("Publication date", "")
        dated = f" Published {published}." if published else ""
        for value_raw, year in ((r.get("2026 value"), "2026"), (r.get("2025 matching"), "2025")):
            value = _scaled(value_raw, multiplier)
            if value is None:
                continue
            out.add(url, {
                "indicator_code": code, "area_code": "OM",
                "period_start": start.replace("2026", year, 1),
                "period_end": end.replace("2026", year, 1),
                "frequency": "annual", "period_complete": "false", "unit_code": unit,
                "value": value, "value_operator": operator, "quality_status": quality,
                "_step": _step(value_raw, multiplier),
                "revision_status": "preliminary", "source_locator": url,
                "note": f"{period}" + (" (matching 2025 period)" if year == "2025" else "")
                + (f". {note}" if note else "") + f". {r.get('Evidence / interpretation', '')}."
                + dated,
            })  # fmt: skip


def regions(rows: list[dict[str, str]], out: Mapped) -> None:
    """Regions_2026: governorate figures; a combined reporting area is never split."""
    for r in rows:
        sector, area = r.get("Sector", ""), r.get("Geographic coverage", "")
        item = f"{sector}: {area}"
        if "combined" in area.lower():
            out.skipped.append(("Regions_2026", item, "combined reporting area; never split "
                                "into governorates or wilayats"))  # fmt: skip
            continue
        if sector == "Fisheries":
            if area == "Musandam, artisanal catch":
                code, unit, gov = "FISH_LANDINGS_TRADITIONAL", "tonne", "OM-MU"
                start = "2026-01-01"
            else:
                out.skipped.append(("Regions_2026", item, "no matching indicator"))
                continue
        else:
            if sector not in REGION_SECTORS or area not in GOVERNORATES:
                out.skipped.append(("Regions_2026", item, "no matching indicator or area"))
                continue
            code, unit = REGION_SECTORS[sector]
            gov, start = GOVERNORATES[area], "2026-01-01"
        end = r.get("Period end", "")
        url = r.get("Source URL", "")
        for value_raw, year in ((r.get("2026 value"), "2026"), (r.get("2025 same period"), "2025")):
            value = _scaled(value_raw, 1)
            if value is None:
                continue
            out.add(url, {
                "indicator_code": code, "area_code": gov,
                "period_start": start.replace("2026", year, 1),
                "period_end": end.replace("2026", year, 1),
                "frequency": "annual", "period_complete": "false", "unit_code": unit,
                "value": value, "quality_status": "accepted", "revision_status": "preliminary",
                "_step": _step(value_raw, 1),
                "source_locator": url,
                "note": f"{area}, January to {end[5:7]}/{year}"
                + (" (matching 2025 period)" if year == "2025" else "")
                + f". {r.get('Notes', '')}",
            })  # fmt: skip


def csv_text(rows: list[dict[str, str]]) -> str:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(COLUMNS), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
