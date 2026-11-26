# ruff: noqa: E501 - bilingual labels are kept on one line each, as in services/studies.py
"""Electricity's and water's annual indicators side by side, as distinct indicators, for chosen
full years: what the sector pages show before any analysis.

Each row is one published series (indicator and area) read through ``timeline.build``, so the
values, units, provisional marks and year-on-year changes are the platform's own (deterministic,
never written by a language model). Indicators are never merged: net actual electricity
consumption, electricity distributed and electricity produced are separate rows, and a water
utility's operational measures are a separate group with their own scope. Missing years stay
empty, never zero; nothing is subtracted to show a shortage, surplus or loss.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.domain.enums import DataMode, Section
from app.services import timeline
from app.services.imports.csv_file import safe_cell

T = dict[str, str]


def _t(en: str, ar: str) -> T:
    return {"en": en, "ar": ar}


GROUPS: dict[str, list[tuple[str, T, list[tuple[str, str]]]]] = {
    "electricity": [
        ("consumption", _t("Consumption by category", "الاستهلاك حسب الفئة"), [
            ("ELEC_CONSUMPTION_RESIDENTIAL", "OM"), ("ELEC_CONSUMPTION_COMMERCIAL", "OM"), ("ELEC_CONSUMPTION_INDUSTRIAL", "OM"),
            ("ELEC_CONSUMPTION_GOVERNMENT", "OM"), ("ELEC_CONSUMPTION_OTHER", "OM"),
        ]),
        ("totals", _t("Totals (separate indicators)", "المجاميع (مؤشرات منفصلة)"), [
            ("ELEC_CONSUMPTION", "OM"), ("ELEC_DISTRIBUTION", "OM"), ("ELEC_GROSS_GENERATION", "OM"),
        ]),
    ],
    "water": [
        ("national", _t("Oman", "سلطنة عُمان"), [("WATER_PRODUCTION", "OM"), ("WATER_DISTRIBUTION", "OM")]),
        ("regions", _t("By region, as published", "حسب المنطقة كما نُشرت"), [
            ("WATER_PRODUCTION", "OM-MA"), ("WATER_DISTRIBUTION", "OM-MA"), ("WATER_PRODUCTION", "OM-ZU"),
            ("WATER_DISTRIBUTION", "OM-ZU"), ("WATER_PRODUCTION", "OM-GRP-OTHER-WATER"), ("WATER_DISTRIBUTION", "OM-GRP-OTHER-WATER"),
        ]),
        ("utility", _t("Utility operations (a separate scope)", "عمليات المرفق (نطاق منفصل)"), [
            ("WATER_SUPPLY_UTILITY", "OM-GRP-NWS"), ("WATER_DELIVERED_UTILITY", "OM-GRP-NWS"),
        ]),
    ],
}  # fmt: skip

NOTES: dict[str, list[T]] = {
    "electricity": [
        _t(
            "Net actual consumption, electricity distributed and electricity produced are different published indicators: in 2022 consumption was 36,427.1 GWh and distribution 36,178.6 GWh.",
            "صافي الاستهلاك الفعلي والكهرباء الموزعة والكهرباء المنتجة مؤشرات منشورة مختلفة: في 2022 بلغ الاستهلاك 36,427.1 جيجاواط ساعة والتوزيع 36,178.6.",
        ),
        _t(
            "Production minus consumption is not a shortage or surplus: the figures do not share a system boundary.",
            "الإنتاج ناقص الاستهلاك ليس عجزاً أو فائضاً: الأرقام لا تشترك في حدود النظام نفسها.",
        ),
    ],
    "water": [
        _t(
            "Water produced and water distributed are different measures; produced minus distributed is not leakage.",
            "المياه المنتجة والمياه الموزعة مقياسان مختلفان؛ والفرق بينهما ليس تسرباً.",
        ),
        _t(
            "The utility's figures cover its own operations (all governorates except Dhofar) and are not the national NCSI measures.",
            "أرقام المرفق تغطي عملياته (جميع المحافظات عدا ظفار) وليست المقاييس الوطنية للمركز الوطني للإحصاء.",
        ),
    ],
}


def table(
    session: Session, section: Section, data_mode: DataMode, year_from: int, year_to: int
) -> dict[str, Any]:
    if section.value not in GROUPS:
        raise ApiError(
            404,
            "not_available",
            "Annual indicators side by side are available for electricity and water.",
        )
    if not 1900 <= year_from <= year_to <= 2100 or year_to - year_from > 15:
        raise ApiError(
            422, "invalid_years", "Choose up to 16 full years, the first not after the last."
        )
    years = [str(y) for y in range(year_from, year_to + 1)]
    groups = []
    for code, label, members in GROUPS[section.value]:
        rows = []
        for indicator, area in members:
            try:
                doc = timeline.build(session, data_mode, indicator, area=area, view="annual",
                                     period_from=date(year_from, 1, 1), period_to=date(year_to, 12, 31))  # fmt: skip
            except ApiError as exc:
                if exc.status_code == 404:
                    continue  # an indicator this database does not define yet: no row
                raise
            cells: dict[str, dict[str, Any]] = {}
            for r in doc.get("rows", []):
                year = r["period_start"][:4]
                if (
                    r["nature"] == "forecast"
                    or r["period_end"] != f"{year}-12-31"
                    or year not in years
                ):
                    continue
                yoy = next((c for c in r["changes"] if c["basis"] == "year_on_year"), None)
                cells[year] = {
                    "value": r["value"], "value_operator": r["value_operator"], "nature": r["nature"],
                    "revision_status": r["revision_status"], "provisional": r["revision_status"] in ("provisional", "preliminary"),
                    "change_percent": yoy["percent"] if yoy else None, "change_absolute": yoy["absolute"] if yoy else None,
                    "source": (r.get("source") or {}).get("dataset_title"), "locator": r.get("locator"),
                }  # fmt: skip
            rows.append(
                {
                    "indicator": {"code": indicator, "name": doc["indicator"]["name"]},
                    "area": area,
                    "unit": doc["unit"]["label"] if doc.get("status") == "ok" else None,
                    "status": doc.get("status"),
                    "limitation": doc["indicator"]["limitation"],
                    "cells": [cells.get(y) for y in years],
                }
            )
        groups.append({"code": code, "label": label, "rows": rows})
    return {
        "section": section.value,
        "data_mode": data_mode.value,
        "years": years,
        "groups": groups,
        "notes": NOTES[section.value],
    }


CSV_COLUMNS = [
    "section", "group", "indicator_code", "indicator", "area_code", "year", "value", "value_operator", "unit",
    "nature", "revision_status", "provisional", "change_yoy_absolute", "change_yoy_percent", "source", "source_locator",
]  # fmt: skip


def to_csv(doc: dict[str, Any], language: str = "en") -> str:
    """The table's cells, one line per indicator, area and year, with the notes as comment
    lines. A missing year is an empty value, never zero; text cells are neutralised against
    spreadsheet formulas."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [f"# OSRIP annual indicators - {doc['section']} - {doc['years'][0]}-{doc['years'][-1]}"]
    )
    writer.writerow([f"# data_mode={doc['data_mode']}"])
    for note in doc["notes"]:
        writer.writerow([safe_cell(f"# {note[language]}")])
    writer.writerow(CSV_COLUMNS)
    for group in doc["groups"]:
        for row in group["rows"]:
            unit = (row["unit"] or {}).get(language, "")
            for year, c in zip(doc["years"], row["cells"], strict=True):
                c = c or {}
                writer.writerow([
                    doc["section"], group["code"], row["indicator"]["code"], safe_cell(row["indicator"]["name"][language]),
                    row["area"], year, c.get("value") or "", c.get("value_operator") or "", safe_cell(unit),
                    c.get("nature") or "missing", c.get("revision_status") or "", "true" if c.get("provisional") else "false",
                    c.get("change_absolute") or "", c.get("change_percent") or "",
                    safe_cell(c.get("source") or ""), safe_cell(c.get("locator") or ""),
                ])  # fmt: skip
    return buffer.getvalue()
