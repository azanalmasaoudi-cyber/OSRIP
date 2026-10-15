"""The curated Oman reference pack: extraction, validation and import with provenance.

Two steps, both repeatable:

1. ``build_pack(docx)`` reads the English reference document (tables of records
   OM-0001 ..., the reference list S01 ... and the reconciliation notes Q01 ...) and
   returns a versioned JSON pack. Every label is mapped explicitly; an unknown
   indicator, area, unit, period, status or source identifier stops the build.
2. ``import_pack(session, pack)`` registers the sources, loads each source's records
   through the normal import workflow (validation, error report, approval,
   all-or-nothing publication) and records the pack's references and notes.

The pack is curated evidence extracted from official publications and statements;
it is not an official API feed. Values keep the unit in which they were published.
Nothing is invented: a record that fails validation is reported, never repaired.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import DataMode, DatasetVersionStatus, Permission, Role
from app.models import (
    AppUser,
    DataQualityNote,
    DatasetVersion,
    ImportJob,
    ReferencePack,
    ReferencePackSource,
    Source,
)
from app.services import accounts
from app.services.imports import workflow
from app.services.principal import Principal

PACK_FILE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "reference"
    / "oman_reference_pack_2026-09-27.json"
)
LOADER_EMAIL = "reference-loader@osrip.invalid"
SYSTEM = Principal(user_id=None, label="system:reference-pack")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# ------------------------------------------------------------------ explicit mappings

SECTION_TITLES = {
    "Electricity observations": "electricity",
    "Water observations": "water",
    "Food security observations": "food_security",
    "Merchandise trade observations": "trade",
}

INDICATORS: dict[tuple[str, str], str] = {
    ("electricity", "gross generation"): "ELEC_GROSS_GENERATION",
    ("electricity", "net generation"): "ELEC_NET_GENERATION",
    ("electricity", "consumption"): "ELEC_CONSUMPTION",
    ("electricity", "consumption residential"): "ELEC_CONSUMPTION_RESIDENTIAL",
    ("electricity", "consumption commercial"): "ELEC_CONSUMPTION_COMMERCIAL",
    ("electricity", "consumption industrial"): "ELEC_CONSUMPTION_INDUSTRIAL",
    ("electricity", "consumption government"): "ELEC_CONSUMPTION_GOVERNMENT",
    ("electricity", "consumption other"): "ELEC_CONSUMPTION_OTHER",
    ("electricity", "distribution"): "ELEC_DISTRIBUTION",
    ("electricity", "installed capacity"): "ELEC_INSTALLED_CAPACITY",
    ("electricity", "connections"): "ELEC_CONNECTIONS",
    ("water", "production"): "WATER_PRODUCTION",
    ("water", "distribution"): "WATER_DISTRIBUTION",
    ("water", "connections"): "WATER_CONNECTIONS",
    ("water", "consumption portal"): "WATER_CONSUMPTION",
    ("food_security", "crop production"): "AGRI_CROP_PRODUCTION",
    ("food_security", "cultivated area"): "AGRI_CULTIVATED_AREA",
    ("food_security", "production vegetables"): "AGRI_PROD_VEGETABLES",
    ("food_security", "production tomatoes"): "AGRI_PROD_TOMATOES",
    ("food_security", "production cucumbers"): "AGRI_PROD_CUCUMBERS",
    ("food_security", "production potatoes"): "AGRI_PROD_POTATOES",
    ("food_security", "production onions"): "AGRI_PROD_ONIONS",
    ("food_security", "production garlic"): "AGRI_PROD_GARLIC",
    ("food_security", "production field crops"): "AGRI_PROD_FIELD_CROPS",
    ("food_security", "production wheat"): "AGRI_PROD_WHEAT",
    ("food_security", "production fodder"): "AGRI_PROD_FODDER",
    ("food_security", "production fruit"): "AGRI_PROD_FRUIT",
    ("food_security", "production dates"): "AGRI_PROD_DATES",
    ("food_security", "production mango"): "AGRI_PROD_MANGO",
    ("food_security", "production banana"): "AGRI_PROD_BANANA",
    ("food_security", "livestock cattle"): "LIVESTOCK_CATTLE",
    ("food_security", "livestock camels"): "LIVESTOCK_CAMELS",
    ("food_security", "livestock sheep"): "LIVESTOCK_SHEEP",
    ("food_security", "livestock goats"): "LIVESTOCK_GOATS",
    ("food_security", "traditional fish landings"): "FISH_LANDINGS_TRADITIONAL",
    ("food_security", "coastal fish landings"): "FISH_LANDINGS_COASTAL",
    ("food_security", "commercial fish landings"): "FISH_LANDINGS_COMMERCIAL",
    ("food_security", "capture fish landings"): "FISH_CAPTURE_LANDINGS",
    ("food_security", "fish value including aquaculture"): "FISH_VALUE_INCL_AQUACULTURE",
    ("food_security", "self sufficiency fish"): "SELF_SUFFICIENCY_FISH",
    ("food_security", "self sufficiency dates"): "SELF_SUFFICIENCY_DATES",
    ("food_security", "self sufficiency vegetables"): "SELF_SUFFICIENCY_VEGETABLES",
    ("food_security", "self sufficiency eggs"): "SELF_SUFFICIENCY_EGGS",
    ("food_security", "self sufficiency milk"): "SELF_SUFFICIENCY_MILK",
    ("food_security", "self sufficiency white meat"): "SELF_SUFFICIENCY_WHITE_MEAT",
    ("food_security", "self sufficiency red meat"): "SELF_SUFFICIENCY_RED_MEAT",
    (
        "food_security",
        "self sufficiency fruit excluding dates",
    ): "SELF_SUFFICIENCY_FRUIT_EXCL_DATES",
    ("food_security", "agriculture and fisheries production"): "AGRI_FISH_PRODUCTION_TOTAL",
    ("trade", "merchandise exports"): "TRADE_MERCH_EXPORTS",
    ("trade", "oil gas exports"): "TRADE_OIL_GAS_EXPORTS",
    ("trade", "crude oil exports"): "TRADE_CRUDE_OIL_EXPORTS",
    ("trade", "refined oil exports"): "TRADE_REFINED_OIL_EXPORTS",
    ("trade", "lng exports"): "TRADE_LNG_EXPORTS",
    ("trade", "non oil exports"): "TRADE_NON_OIL_EXPORTS",
    ("trade", "non oil base metals exports"): "TRADE_NONOIL_BASE_METALS_EXPORTS",
    ("trade", "non oil chemical exports"): "TRADE_NONOIL_CHEMICAL_EXPORTS",
    ("trade", "non oil plastics rubber exports"): "TRADE_NONOIL_PLASTICS_RUBBER_EXPORTS",
    ("trade", "non oil mineral exports"): "TRADE_NONOIL_MINERAL_EXPORTS",
    ("trade", "non oil precious material exports"): "TRADE_NONOIL_PRECIOUS_EXPORTS",
    ("trade", "reexports"): "TRADE_REEXPORTS",
    ("trade", "recorded merchandise imports"): "TRADE_MERCH_IMPORTS",
    ("trade", "electrical machinery imports"): "TRADE_IMPORTS_ELECTRICAL_MACHINERY",
    ("trade", "mineral imports"): "TRADE_IMPORTS_MINERAL",
    ("trade", "base metals imports"): "TRADE_IMPORTS_BASE_METALS",
    ("trade", "precious material imports"): "TRADE_IMPORTS_PRECIOUS",
    ("trade", "transport equipment imports"): "TRADE_IMPORTS_TRANSPORT_EQUIPMENT",
    ("trade", "trade balance reported"): "TRADE_BALANCE_REPORTED",
}

# Indicators whose partner slices exist; the database requires a trade flow with a partner.
FLOWS = {
    "TRADE_NON_OIL_EXPORTS": "domestic_export",
    "TRADE_REEXPORTS": "re_export",
    "TRADE_MERCH_IMPORTS": "import",
}

AREAS = {
    "Oman": "OM",
    "Muscat": "OM-MA",
    "Dhofar": "OM-ZU",
    "Musandam": "OM-MU",
    "Ad Dakhliyah": "OM-DA",
    "Al Wusta": "OM-WU",
    "South Ash Sharqiyah": "OM-SJ",
    "North & South Al Batinah + Adh Dhahirah": "OM-GRP-BATINAH-DHAHIRAH",
    "North & South Ash Sharqiyah": "OM-GRP-SHARQIYAH",
    "North & South Al Batinah": "OM-GRP-BATINAH",
}
# "Other governorates" means different groups in the electricity and water tables.
OTHER_GOVERNORATES = {"electricity": "OM-GRP-OTHER-ELEC", "water": "OM-GRP-OTHER-WATER"}

PARTNERS = {
    "UAE": "ARE",
    "Saudi Arabia": "SAU",
    "India": "IND",
    "United States": "USA",
    "South Korea": "KOR",
    "Iran": "IRN",
    "Hong Kong": "HKG",
    "United Kingdom": "GBR",
    "China": "CHN",
    "Turkey": "TUR",
}

UNITS = {
    "GWh": "GWh",
    "MW": "MW",
    "feddan": "feddan",
    "million OMR": "million_OMR",
    "million m³": "million_m3",
    "million_tonnes": "million_tonnes",
    "percent": "percent",
    "thousand OMR": "thousand_OMR",
    "thousand connections": "thousand_connections",
    "thousand head": "thousand_head",
    "thousand m³": "thousand_m3",
    "thousand tonnes": "thousand_tonnes",
    "tonnes": "tonne",
}

STATUSES = {
    "reported": "reported",
    "provisional": "provisional",
    "preliminary": "preliminary",
    "estimate": "estimate",
    "official statement": "official_statement",
    "reported statement": "reported_statement",
}

MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        start=1,
    )
}

# Registration details the document does not state in machine-readable form.
SOURCE_REGISTRATION = {
    "S01": (
        "direct_file",
        "Official statistics published by the National Centre for Statistics and Information (NCSI); cited with attribution.",
    ),
    "S02": (
        "direct_file",
        "Official statistics published by the National Centre for Statistics and Information (NCSI); cited with attribution.",
    ),
    "S03": ("statistical_table", "NCSI data portal time series; cited with attribution."),
    "S04": ("web_page", "Official government statement; figures cited with attribution."),
    "S05": (
        "web_page",
        "News report of a ministerial statement; figures cited with attribution, the article is not reproduced.",
    ),
}

ROLE_WORDS = {
    "primary": "primary",
    "official statement": "official_statement",
    "secondary ministerial reporting": "secondary",
    "crosscheck only": "crosscheck",
    "superseded crosscheck": "superseded_crosscheck",
}

# Arabic translations of the reconciliation notes and the sections each note concerns.
NOTES_AR = {
    "Q01": (
        "مراجعات بيانات الكهرباء والمياه السنوية لعام 2025",
        "أورد بيان صحفي سابق (S08): إجمالي التوليد 51612.3 جيجاواط ساعة وصافيه 50160.6 والمياه 509.9 مليون م³. "
        "وأورد S01 (سبتمبر): الإجمالي 50973.5 والصافي 49532.4 والمياه 508066.3 ألف م³. يُستخدم S01 لهذا الإصدار دون خلط الإصدارات.",
    ),
    "Q02": (
        "إنتاج المياه ليس استهلاكاً",
        "استهلاك S03: 343.1 مليون م³ (2025)؛ توزيع S02: 344.6؛ إنتاج S01: 508.0663. التسميات والتغطية مختلفة وقد تكون هناك مراجعات؛ "
        "لا يُستنتج تسرب ولا عجز مائي.",
    ),
    "Q03": (
        "فترات الاكتفاء الذاتي الغذائي",
        "S04: الخضروات 77% والبيض أكثر من 95%؛ S05: الخضروات 79% والبيض 95%. التقرير اللاحق لا يثبت صراحة سلسلة معدّلة لعام 2025. "
        "يُعرض تاريخ التصريح ويُحتفظ بكليهما دون اختلاق اتجاه.",
    ),
    "Q04": (
        "عدم اتساق المجموع الفرعي للأسماك لعام 2025",
        "في S01 ص19 مجموع الصيد التقليدي السنوي حسب المناطق 891067 طناً ومجموع الأنواع 897710. إجمالي الصيد 981849 ويساوي "
        "891067+9678+81104. يُعزل مجموع الأنواع السنوي حتى يُوضَّح.",
    ),
    "Q05": (
        "تباين داخلي في بيانات التجارة السنوية لعام 2025",
        "جداول S01 ص8/ص9 تذكر الواردات 17161 مليون ريال، والرسم التاريخي في ص9 يذكر 17167 والميزان 6097. تُعتمد واردات الجدول افتراضياً، "
        "ولا يُخلط ميزان الرسم مع واردات الجدول. وتختلف مجاميع مكونات صادرات 2025 بمقدار مليون واحد بسبب التقريب.",
    ),
    "Q06": (
        "خلط وحدات في بيانات المياه الصحفية",
        "يخلط S06 بين المتر المكعب وألف المتر المكعب. تُستخدم بيانات S01 الموسومة صراحة بألف م³، ولا تُستورد الأرقام الصحفية.",
    ),
    "Q07": (
        "فروق صغيرة في مجاميع الزراعة",
        "مجموع المحاصيل في S02 ص87 لعام 2025 = 4085864 طناً (لا 4085865 المذكور سابقاً). ولعام 2023: ص87 = 3684696 مقابل ص88 = 3684697. "
        "تُعتمد ص87 باتساق.",
    ),
    "Q08": (
        "عدم اتساق الترجمة الإنجليزية",
        "يذكر نص S04 العربي 493 مشروعاً و50000 فدان، وتختلف الترجمة الإنجليزية. مجاميع الاستثمار تمتد 2021–2025 ومستبعدة من مجموعة "
        "المشاهدات من 2022 فصاعداً.",
    ),
    "Q09": (
        "التغطية الجغرافية",
        "تجمع بيانات الكهرباء الباطنة والظاهرة معاً والشرقية بشقيها، وتستخدم بيانات المياه مسقط وظفار وبقية المحافظات. لا تُقسم قيم "
        "المجموعات بالتساوي ولا تُعرض كأرقام ولايات أو محافظات منفردة.",
    ),
}
NOTE_SECTIONS = {
    "Q01": ["electricity", "water"],
    "Q02": ["water"],
    "Q03": ["food_security"],
    "Q04": ["food_security"],
    "Q05": ["trade"],
    "Q06": ["water"],
    "Q07": ["food_security"],
    "Q08": ["food_security"],
    "Q09": ["electricity", "water", "food_security"],
}


class PackError(ValueError):
    """The document or pack cannot be used as it is; the message says why."""


# ------------------------------------------------------------------ document reading


def _text(el: ET.Element) -> str:
    return "".join(n.text or "" for n in el.iter() if n.tag == f"{_W}t")


def _cell_parts(tc: ET.Element) -> list[str]:
    parts: list[str] = []
    for p in tc.iter(f"{_W}p"):
        current: list[str] = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                current.append(node.text)
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("".join(current))
                current = []
        parts.append("".join(current))
    return [x.strip() for x in parts if x.strip()]


def _style(p: ET.Element) -> str | None:
    s = p.find(f"{_W}pPr/{_W}pStyle")
    return s.get(f"{_W}val") if s is not None else None


def _parse_period(label: str) -> dict[str, Any]:
    if m := re.fullmatch(r"(\d{4}) annual", label):
        y = int(m[1])
        return {
            "frequency": "annual",
            "period_start": f"{y}-01-01",
            "period_end": f"{y}-12-31",
            "period_complete": True,
        }
    if m := re.fullmatch(r"(\d{4})-(\d{2}) monthly", label):
        y, mo = int(m[1]), int(m[2])
        end = date(y + mo // 12, mo % 12 + 1, 1).toordinal() - 1
        return {
            "frequency": "monthly",
            "period_start": f"{y}-{mo:02d}-01",
            "period_end": date.fromordinal(end).isoformat(),
            "period_complete": True,
        }
    if m := re.fullmatch(r"Jan[–-](\w{3}) (\d{4})", label):
        y, mo = int(m[2]), MONTHS.get(m[1])
        if mo is None:
            raise PackError(f"Unknown month in period {label!r}.")
        end = date(y + mo // 12, mo % 12 + 1, 1).toordinal() - 1
        # Year to date: an incomplete annual period starting in January.
        return {
            "frequency": "annual",
            "period_start": f"{y}-01-01",
            "period_end": date.fromordinal(end).isoformat(),
            "period_complete": False,
        }
    if m := re.fullmatch(r"Reported (\d{4}-\d{2}-\d{2})", label):
        return {
            "frequency": "statement",
            "period_start": m[1],
            "period_end": m[1],
            "period_complete": True,
            "statement_date": m[1],
        }
    raise PackError(f"Unknown period label {label!r}.")


def _parse_value(raw: str) -> tuple[str | None, str]:
    raw = raw.replace(",", "").strip()
    operator = None
    for op in (">=", "<=", ">", "<", "~"):
        if raw.startswith(op):
            operator, raw = op, raw[len(op) :].strip()
            break
    if not re.fullmatch(r"-?\d+(\.\d+)?", raw):
        raise PackError(f"Not a plain number: {raw!r}.")
    return operator, raw


def build_pack(docx_path: Path) -> dict[str, Any]:
    """Extract the reference pack from the English reference document."""
    try:
        archive = zipfile.ZipFile(docx_path)
        # Operator-supplied document read by the CLI; expat resolves no external entities.
        body = ET.fromstring(archive.read("word/document.xml")).find(f"{_W}body")  # noqa: S314
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise PackError(f"Cannot read {docx_path.name} as a Word document: {exc}") from exc
    if body is None:
        raise PackError("The document has no body.")

    paragraphs = [
        (child, _style(child), _text(child).strip()) for child in body if child.tag == f"{_W}p"
    ]
    cutoff_match = next(
        (
            re.search(r"Research cutoff (\d{1,2}) (\w+) (\d{4})", t)
            for _, _, t in paragraphs
            if "Research cutoff" in t
        ),
        None,
    )
    if not cutoff_match:
        raise PackError("The document does not state its research cutoff.")
    cutoff = date(int(cutoff_match[3]), MONTHS[cutoff_match[2][:3]], int(cutoff_match[1]))
    title = next((t for _, s, t in paragraphs if s == "Title"), "Reference pack")

    records: list[dict[str, Any]] = []
    section: str | None = None
    for child in body:
        if child.tag == f"{_W}p" and _style(child) == "Title":
            section = SECTION_TITLES.get(_text(child).strip())
        elif child.tag == f"{_W}tbl" and section:
            for tr in child.iter(f"{_W}tr"):
                cells = [_cell_parts(tc) for tc in tr.iter(f"{_W}tc")]
                if not cells or not cells[0] or not cells[0][0].startswith("OM-"):
                    continue
                records.append(_record(section, cells))

    ids = [r["record_ref"] for r in records]
    if len(ids) != len(set(ids)):
        raise PackError("Record identifiers repeat in the document.")
    stated = next(
        (
            re.search(r"(\d+) source-linked statistical observations", t)
            for _, _, t in paragraphs
            if "source-linked" in t
        ),
        None,
    )
    if stated and int(stated[1]) != len(records):
        raise PackError(
            f"The document states {stated[1]} observations but {len(records)} were found."
        )

    sources = _references(paragraphs)
    known = {s["code"] for s in sources}
    unknown = sorted({r["source_id"] for r in records} - known)
    if unknown:
        raise PackError(f"Records cite unknown source identifiers: {', '.join(unknown)}.")
    return {
        "code": f"oman-reference-{cutoff.isoformat()}",
        "title": title,
        "research_cutoff": cutoff.isoformat(),
        "document": docx_path.name,
        "record_count": len(records),
        "records": records,
        "sources": sources,
        "notes": _notes(paragraphs),
    }


def _record(section: str, cells: list[list[str]]) -> dict[str, Any]:
    ref = cells[0][0]
    label, *coverage_parts = cells[1]
    coverage = coverage_parts[0] if coverage_parts else ""
    code = INDICATORS.get((section, label))
    if code is None:
        raise PackError(f"{ref}: unknown indicator label {label!r} in the {section} table.")
    partner = None
    if " / " in coverage:
        coverage, partner_label = coverage.split(" / ", 1)
        partner = PARTNERS.get(partner_label)
        if partner is None:
            raise PackError(f"{ref}: unknown partner {partner_label!r}.")
    area = (
        OTHER_GOVERNORATES.get(section) if coverage == "Other governorates" else AREAS.get(coverage)
    )
    if area is None:
        raise PackError(f"{ref}: unknown geography {coverage!r}.")
    period = _parse_period(cells[2][0])
    operator, value = _parse_value(cells[3][0])
    unit_label = cells[3][1] if len(cells[3]) > 1 else ""
    unit = UNITS.get(unit_label)
    if unit is None:
        raise PackError(f"{ref}: unsupported unit {unit_label!r}.")
    source_cell, status_label = cells[4][0], cells[4][-1]
    status = STATUSES.get(status_label)
    if status is None:
        raise PackError(f"{ref}: unknown status {status_label!r}.")
    source_id, _, locator = source_cell.partition(";")
    locator = locator.strip()
    if locator and locator[0].isdigit():
        locator = "; ".join(f"p. {part.strip()}" for part in locator.split(";"))
    return {
        "record_ref": ref,
        "section": section,
        "indicator_label": label,
        "indicator_code": code,
        "coverage": coverage if not partner else f"{coverage} / {partner}",
        "area_code": area,
        "partner_code": partner,
        "flow": FLOWS.get(code),
        "period_label": cells[2][0],
        **period,
        "value": value,
        "value_operator": operator,
        "unit_label": unit_label,
        "unit_code": unit,
        "source_id": source_id.strip(),
        "source_locator": locator or None,
        "status_label": status_label,
        "revision_status": status,
    }


def _references(paragraphs: list[tuple[ET.Element, str | None, str]]) -> list[dict[str, Any]]:
    start = next(
        (i for i, (_, s, t) in enumerate(paragraphs) if s == "Title" and t == "References"), None
    )
    if start is None:
        raise PackError("The document has no References section.")
    sources: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for _, style, text in paragraphs[start + 1 :]:
        if style == "Heading2" and re.match(r"S\d{2} ", text):
            code, publisher = text.split(" ", 1)
            current = {"code": code, "publisher": publisher.strip(), "locations": None}
            sources.append(current)
        elif current is not None and text.startswith("http"):
            current["url"] = text
        elif current is not None and text.startswith("Locations:"):
            current["locations"] = text.removeprefix("Locations:").strip()
        elif current is not None and "Accessed" in text and "Role:" in text:
            m = re.match(
                r"(.*?)\. Publication: (.*?)\. Accessed (\d{1,2}) (\w+) (\d{4})\. Role: (.*?)\.?$",
                text,
            )
            if not m:
                raise PackError(f"{current['code']}: cannot read the reference line {text!r}.")
            role = ROLE_WORDS.get(m[6].strip().lower())
            if role is None:
                raise PackError(f"{current['code']}: unknown source role {m[6]!r}.")
            current.update(
                {
                    "title": m[1].strip(),
                    "publication": m[2].strip(),
                    "accessed_on": date(int(m[5]), MONTHS[m[4][:3]], int(m[3])).isoformat(),
                    "role": role,
                }
            )
    for s in sources:
        missing = [k for k in ("title", "url", "accessed_on", "role") if not s.get(k)]
        if missing:
            raise PackError(f"{s['code']}: the reference lacks {', '.join(missing)}.")
    return sources


def _notes(paragraphs: list[tuple[ET.Element, str | None, str]]) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for i, (_, style, text) in enumerate(paragraphs):
        m = re.match(r"(Q\d{2}) (.+)", text) if style == "Heading2" else None
        if not m:
            continue
        body = paragraphs[i + 1][2] if i + 1 < len(paragraphs) else ""
        code = m[1]
        if code not in NOTES_AR:
            raise PackError(f"No Arabic translation is prepared for note {code}.")
        title_ar, body_ar = NOTES_AR[code]
        notes.append(
            {
                "code": code,
                "title_en": m[2].strip(),
                "title_ar": title_ar,
                "body_en": body,
                "body_ar": body_ar,
                "source_codes": sorted(set(re.findall(r"S\d{2}", body))),
                "sections": NOTE_SECTIONS.get(code, []),
            }
        )
    return notes


def write_pack(pack: dict[str, Any], path: Path = PACK_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pack, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def load_pack(path: Path = PACK_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ import

CSV_FIELDS = (
    "record_ref",
    "indicator_code",
    "area_code",
    "partner_code",
    "flow",
    "period_start",
    "period_end",
    "period_complete",
    "frequency",
    "statement_date",
    "unit_code",
    "value",
    "value_operator",
    "revision_status",
    "source_locator",
)


def records_csv(pack: dict[str, Any], source_code: str) -> bytes:
    """One source's records in the import workflow's canonical columns."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for r in pack["records"]:
        if r["source_id"] != source_code:
            continue
        writer.writerow(
            {
                **{k: r.get(k) or "" for k in CSV_FIELDS},
                "period_complete": "true" if r["period_complete"] else "false",
            }
        )
    return out.getvalue().encode("utf-8")


@dataclass(frozen=True, slots=True)
class SourceResult:
    code: str
    import_id: str
    status: str
    rows: int
    rejected: int
    warnings: int


def _loader(session: Session) -> Principal:
    with session.begin():
        user = session.scalar(select(AppUser).where(AppUser.email == LOADER_EMAIL))
        if user is None:
            user = accounts.create_user(
                session,
                SYSTEM,
                email=LOADER_EMAIL,
                display_name="Reference pack loader",
                password=None,
                roles=[Role.DATA_MANAGER],
                service_account=True,
            )
            session.flush()
            for permission in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
                accounts.grant_permission(session, SYSTEM, user.id, permission)
        session.flush()
        return accounts.load_principal(session, user)


def pack_checksum(pack: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(pack, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def import_pack(session: Session, pack: dict[str, Any], *, publish: bool) -> list[SourceResult]:
    """Register sources and stage (and optionally approve and publish) one import per source.

    Repeatable: a source whose version is already published with the same content is
    left alone, so running it again adds no duplicate observations. Without
    ``publish``, imports stop after validation for a data manager to review.
    """
    actor = _loader(session)
    checksum = pack_checksum(pack)
    with session.begin():
        stored = session.scalar(select(ReferencePack).where(ReferencePack.code == pack["code"]))
        if stored is not None and stored.checksum_sha256 != checksum:
            raise PackError(
                f"Pack {pack['code']} was already loaded with different content. "
                "A revised pack needs its own code (a new research cutoff)."
            )
        if stored is None:
            stored = ReferencePack(
                code=pack["code"],
                title=pack["title"],
                research_cutoff=date.fromisoformat(pack["research_cutoff"]),
                record_count=pack["record_count"],
                checksum_sha256=checksum,
                document=pack["document"],
            )
            session.add(stored)
            session.flush()
            for n in pack["notes"]:
                session.add(DataQualityNote(pack_id=stored.id, **n))
        pack_id = stored.id

    results: list[SourceResult] = []
    for ref in pack["sources"]:
        code = ref["code"]
        source_id = None
        if code in SOURCE_REGISTRATION and any(r["source_id"] == code for r in pack["records"]):
            source, result = _import_source(session, actor, pack, ref, publish=publish)
            source_id = source.id
            results.append(result)
        with session.begin():
            row = session.get(ReferencePackSource, (pack_id, code))
            if row is None:
                session.add(
                    ReferencePackSource(
                        pack_id=pack_id,
                        code=code,
                        publisher=ref["publisher"],
                        title=ref["title"],
                        publication=ref["publication"],
                        accessed_on=date.fromisoformat(ref["accessed_on"]),
                        role=ref["role"],
                        url=ref["url"],
                        locations=ref.get("locations"),
                        source_id=source_id,
                    )
                )
            elif source_id is not None:
                row.source_id = source_id
    return results


def _import_source(
    session: Session, actor: Principal, pack: dict[str, Any], ref: dict[str, Any], *, publish: bool
) -> tuple[Source, SourceResult]:
    code = ref["code"]
    data = records_csv(pack, code)
    checksum = hashlib.sha256(data).hexdigest()
    label = pack["code"]
    locator_kind, reuse = SOURCE_REGISTRATION[code]
    with session.begin():
        source = session.scalar(
            select(Source).where(
                Source.data_mode == DataMode.VERIFIED_SOURCE,
                Source.source_code == code,
                Source.url == ref["url"],
            )
        )
        existing = (
            None
            if source is None
            else session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.source_id == source.id, DatasetVersion.version_label == label
                )
            )
        )
    if existing is not None and existing.checksum_sha256 != checksum:
        raise PackError(f"{code}: version {label} already exists with different records.")
    if source is None:
        publication = ref["publication"]
        source = workflow.register_source(
            session,
            actor,
            data_mode=DataMode.VERIFIED_SOURCE,
            dataset_title=f"{ref['title']} ({code})",
            publisher=ref["publisher"],
            url=ref["url"],
            locator_kind=locator_kind,
            access_date=date.fromisoformat(ref["accessed_on"]),
            publication_date=date.fromisoformat(publication)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication)
            else None,
            reference_period=f"Publication: {publication}; extracted {pack['research_cutoff']}",
            geographic_coverage="Oman (national, governorate groups and partner slices as published)",
            definition_note=f"Curated extract in {pack['document']}; locations: {ref.get('locations') or 'n/a'}.",
            reuse_conditions=reuse,
            source_code=code,
            source_role=ref["role"],
        )
    if existing is None:
        state = workflow.create_import(
            session,
            actor,
            source_id=source.id,
            version_label=label,
            filename=f"{label}_{code}.csv",
            data=data,
        )
        import_id = state.job.id
        status = DatasetVersionStatus.DRAFT
    else:
        with session.begin():
            import_id = session.scalar(
                select(ImportJob.id).where(ImportJob.dataset_version_id == existing.id)
            )
        assert import_id is not None
        status = existing.status

    if status in (DatasetVersionStatus.DRAFT, DatasetVersionStatus.VALIDATED):
        state = workflow.validate_import(session, actor, import_id)
        status = state.version.status
    with session.begin():
        job = session.get(ImportJob, import_id)
        assert job is not None
        rejected, warnings = job.rejected_row_count or 0, job.warning_row_count or 0
        total = job.row_count or 0
    if publish and status is DatasetVersionStatus.VALIDATED:
        if rejected:
            raise PackError(
                f"{code}: {rejected} records were rejected; see the import's error report before publishing."
            )
        workflow.approve_import(
            session,
            actor,
            import_id,
            acknowledged_rejected_rows=0,
            note=f"Reference pack {pack['code']} loaded by the operator command.",
        )
        status = DatasetVersionStatus.APPROVED
    if publish and status is DatasetVersionStatus.APPROVED:
        workflow.publish_import(session, actor, import_id)
        status = DatasetVersionStatus.PUBLISHED
    return source, SourceResult(code, str(import_id), status.value, total, rejected, warnings)
