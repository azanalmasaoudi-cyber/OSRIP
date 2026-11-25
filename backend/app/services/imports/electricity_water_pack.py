# ruff: noqa: E501 - source notes and bilingual labels are kept on one line each, as in services/studies.py
"""The owner's electricity and water pack of 24 November 2026
(``OSRIP_Electricity_Water_2022_2032_Source_Verified.xlsx``): observed statistics as import rows for
the reviewed import workflow, and the official outlook as outlook items (services/outlook.py).

Every candidate figure is compared with the value read from its source document (``VERIFIED``,
read on 24 November 2026 from the PDFs whose SHA-256 is in ``SOURCES``); a mismatch stops the
mapping, and no figure is altered to make totals add up.

* ``Electricity_Annual`` (Statistical Year Book 2026, PDF p. 131): residential, commercial,
  industrial, government and other consumption, net actual consumption, electricity distributed and
  electricity produced, 2022-2025 (2025 provisional). Net actual consumption and electricity
  distributed are different published indicators (36,427.1 against 36,178.6 GWh in 2022).
* ``Water_Annual`` (p. 131): water produced and distributed for Oman, Muscat, Dhofar and the other
  regions together (a published group), 2022-2025.
* ``Governorates_2025`` (pp. 134, 137): electricity distributed, water distributed and produced for
  the 11 governorates. Never shared out among wilayats.
* ``Nama_Water_Operations`` (Nama Water Services annual report 2025, p. 23): water supplied and
  delivered within the utility's own operations (all governorates except Dhofar), 2023-2025; their
  own indicators and scope, never the national NCSI measures.
* ``Nama_2026_2032`` (PWP 7-year statements 2026-2032, Issue 20): peak demand, the renewable share
  and target, planned and considered plants and storage. Outlook items with their evidence class,
  staged as pending; never observations.
"""

from __future__ import annotations

from decimal import Decimal

from .governorate_pack import _row, _rows
from .owner_workbooks import Mapped, _number

YEARBOOK = (
    "https://api.ncsi.gov.om/uploads/pdfs/statistical_year_book_2026___issue_54_1777550341.pdf"
)
NWS_REPORT = "https://nws.nama.om/Portals/0/Nama%20Water%20Services%20%E2%80%93%20Annual%20Report%20Without%20Financial%20%202025%20copy.pdf"
PWP_POWER = "https://omanpwp.om/storage/files/1/7-year-statement/6af016a6ebea1.pdf"
PWP_WATER = "https://omanpwp.om/storage/files/1/7-year-statement/69804a560ddb9.pdf"

# The documents read on 24 November 2026: what they are and the hash of the file read.
SOURCES = {
    YEARBOOK: {
        "code": "NCSI2026",
        "title": "Statistical Year Book 2026, Issue 54",
        "publisher": "National Centre for Statistics and Information (NCSI)",
        "sha256": "f6463214ba1458d4b947e56bdf99cdf2ac3350681b24971f91ed4a9dc9fe7d8e",
        "issued": "Uploaded 30 April 2026 (published May 2026)",
        "pages": "PDF pp. 131, 134, 137",
    },
    NWS_REPORT: {
        "code": "NAMA_NWS_2025",
        "title": "Nama Water Services Annual Report 2025 (without financial statements)",
        "publisher": "Nama Water Services",
        "sha256": "d0b556c77c2ea130a8d06c4196c112bdd30d5e71639ce34bd1744ac9ce01eefe",
        "issued": "2026",
        "pages": "p. 23 (PDF p. 24); scope p. 4",
    },
    PWP_POWER: {
        "code": "NAMA_PWP_PWR_2026",
        "title": "PWP Power 7-Year Statement 2026-2032, Issue 20",
        "publisher": "Nama Power and Water Procurement (PWP)",
        "sha256": "f8df0410efff0186921580ba5305bc775fdcababeda69b86d60f4db76ed08804",
        "issued": "2026",
        "pages": "PDF pp. 5, 6, 19",
    },
    PWP_WATER: {
        "code": "NAMA_PWP_WTR_2026",
        "title": "PWP Water 7-Year Statement 2026-2032, Issue 20",
        "publisher": "Nama Power and Water Procurement (PWP)",
        "sha256": "48c2a6f6088dcbc45fd9239631b270b13ab1aa6c2338c4e97adc931e81d200d6",
        "issued": "2026",
        "pages": "PDF p. 4 (overview)",
    },
}

# Workbook codes -> OSRIP indicator, area, unit (no official metric is renamed: the note keeps the
# source's own name).
ANNUAL = {
    "consumption_residential": (
        "ELEC_CONSUMPTION_RESIDENTIAL",
        "OM",
        "GWh",
        "Residential consumption",
    ),
    "consumption_commercial": (
        "ELEC_CONSUMPTION_COMMERCIAL",
        "OM",
        "GWh",
        "Commercial consumption",
    ),
    "consumption_industrial": (
        "ELEC_CONSUMPTION_INDUSTRIAL",
        "OM",
        "GWh",
        "Industrial consumption",
    ),
    "consumption_government": (
        "ELEC_CONSUMPTION_GOVERNMENT",
        "OM",
        "GWh",
        "Government consumption",
    ),
    "consumption_other": ("ELEC_CONSUMPTION_OTHER", "OM", "GWh", "Other consumption"),
    "consumption_total": (
        "ELEC_CONSUMPTION",
        "OM",
        "GWh",
        "Consumption of electric power (net actual consumption)",
    ),
    "electricity_distributed": ("ELEC_DISTRIBUTION", "OM", "GWh", "Distribution"),
    "electricity_produced": (
        "ELEC_GROSS_GENERATION",
        "OM",
        "GWh",
        "Production (the same total as the bulletin's gross production)",
    ),
    "water_distributed_total": (
        "WATER_DISTRIBUTION",
        "OM",
        "million_m3",
        "Water distribution, Oman",
    ),
    "water_produced_total": ("WATER_PRODUCTION", "OM", "million_m3", "Water production, Oman"),
    "water_distributed_muscat": (
        "WATER_DISTRIBUTION",
        "OM-MA",
        "million_m3",
        "Water distribution, Muscat",
    ),
    "water_produced_muscat": (
        "WATER_PRODUCTION",
        "OM-MA",
        "million_m3",
        "Water production, Muscat",
    ),
    "water_distributed_dhofar": (
        "WATER_DISTRIBUTION",
        "OM-ZU",
        "million_m3",
        "Water distribution, Dhofar",
    ),
    "water_produced_dhofar": (
        "WATER_PRODUCTION",
        "OM-ZU",
        "million_m3",
        "Water production, Dhofar",
    ),
    "water_distributed_other": (
        "WATER_DISTRIBUTION",
        "OM-GRP-OTHER-WATER",
        "million_m3",
        "Water distribution, other regions (a published group)",
    ),
    "water_produced_other": (
        "WATER_PRODUCTION",
        "OM-GRP-OTHER-WATER",
        "million_m3",
        "Water production, other regions (a published group)",
    ),
}
YEARS = ("2022", "2023", "2024", "2025*")

# Values read from the PDFs on 24 November 2026 (Year Book p. 131): code -> 2022..2025.
VERIFIED_ANNUAL = {
    "consumption_residential": ("15776.1", "17187.3", "18115.7", "18624.9"),
    "consumption_commercial": ("8962.3", "9740.6", "10981.5", "12161.8"),
    "consumption_industrial": ("6093.6", "6453.3", "6815.3", "8136.6"),
    "consumption_government": ("4706.4", "4612.6", "4426.2", "4538.7"),
    "consumption_other": ("888.6", "1302.2", "1817.6", "1571.1"),
    "consumption_total": ("36427.1", "39296.0", "42156.3", "45033.1"),
    "electricity_distributed": ("36178.6", "39296.0", "42156.3", "45033.1"),
    "electricity_produced": ("42510.6", "44965.7", "49132.0", "50973.5"),
    "water_distributed_total": ("281.3", "297.9", "329.9", "344.6"),
    "water_produced_total": ("512.4", "520.4", "520.0", "508.1"),
    "water_distributed_muscat": ("130.2", "132.1", "137.0", "133.4"),
    "water_produced_muscat": ("224.3", "223.4", "233.6", "202.2"),
    "water_distributed_dhofar": ("17.7", "28.5", "52.3", "54.7"),
    "water_produced_dhofar": ("69.6", "71.6", "74.2", "76.6"),
    "water_distributed_other": ("133.5", "137.3", "143.3", "156.6"),
    "water_produced_other": ("218.6", "225.3", "212.2", "229.2"),
}

# Governorates_2025 names (both spellings the packs use) -> code; values from pp. 134 and 137:
# electricity distributed (GWh), water distributed, water produced (million m3).
GOVERNORATES = {
    "Muscat": "OM-MA", "Dhofar": "OM-ZU", "Musandam": "OM-MU", "Al Buraimi": "OM-BU",
    "Ad Dakhiliyah": "OM-DA", "Ad Dakhliyah": "OM-DA", "North Al Batinah": "OM-BS", "Al Batinah North": "OM-BS",
    "South Al Batinah": "OM-BJ", "Al Batinah South": "OM-BJ", "South Ash Sharqiyah": "OM-SJ", "Ash Sharqiyah South": "OM-SJ",
    "North Ash Sharqiyah": "OM-SS", "Ash Sharqiyah North": "OM-SS", "Ad Dhahirah": "OM-ZA", "Adh Dhahirah": "OM-ZA",
    "Al Wusta": "OM-WU",
}  # fmt: skip
VERIFIED_GOVERNORATES = {
    "OM-MA": ("13555.4", "133.4", "202.2"), "OM-ZU": ("5236.7", "54.7", "76.6"), "OM-MU": ("487.6", "4.3", "5.6"),
    "OM-BU": ("773.7", "7.1", "8.6"), "OM-DA": ("3317.8", "30.0", "48.3"), "OM-BS": ("4985.7", "36.6", "54.4"),
    "OM-BJ": ("11428.0", "28.6", "40.4"), "OM-SJ": ("1867.5", "22.9", "37.8"), "OM-SS": ("1472.9", "11.5", "14.4"),
    "OM-ZA": ("1415.2", "10.9", "14.0"), "OM-WU": ("492.5", "4.7", "5.8"),
}  # fmt: skip
GOVERNORATE_COLUMNS = (
    ("Electricity distributed (GWh)", "ELEC_DISTRIBUTION", "GWh", "PDF p. 134"),
    ("Water distributed (million m3)", "WATER_DISTRIBUTION", "million_m3", "PDF p. 137"),
    ("Water produced (million m3)", "WATER_PRODUCTION", "million_m3", "PDF p. 137"),
)

# Nama Water Services, p. 23 (positions of the chart labels read on 24 November 2026).
NWS = {
    "nama_water_delivered": ("WATER_DELIVERED_UTILITY", "Water delivered"),
    "nama_water_supply": ("WATER_SUPPLY_UTILITY", "Water supply"),
}
VERIFIED_NWS = {
    ("nama_water_delivered", "2023"): "269.37", ("nama_water_delivered", "2024"): "280.28", ("nama_water_delivered", "2025"): "287.58",
    ("nama_water_supply", "2023"): "488.78", ("nama_water_supply", "2024"): "445.57", ("nama_water_supply", "2025"): "428.8",
}  # fmt: skip

# The outlook: workbook metric -> code, Arabic name; units; scopes in Arabic; what each item's status
# is according to the statement (read on 24 November 2026).
OUTLOOK_METRICS = {
    "MIS peak electricity demand": (
        "ELEC_PEAK_DEMAND_MIS",
        "الحمل الأقصى للكهرباء في النظام الرئيسي المترابط",
    ),
    "Dhofar peak electricity demand": (
        "ELEC_PEAK_DEMAND_DPS",
        "الحمل الأقصى للكهرباء في نظام ظفار",
    ),
    "Renewable electricity generation share": (
        "ELEC_RENEWABLE_SHARE",
        "حصة الطاقة المتجددة من إنتاج الكهرباء",
    ),
    "Renewable electricity generation share target": (
        "ELEC_RENEWABLE_SHARE_TARGET",
        "الهدف الوطني لحصة الطاقة المتجددة من إنتاج الكهرباء",
    ),
    "Ibri III Solar IPP nameplate capacity": (
        "ELEC_PLANT_IBRI_III_SOLAR",
        "القدرة الاسمية لمشروع عبري 3 للطاقة الشمسية",
    ),
    "Dhofar II Wind IPP nameplate capacity": (
        "ELEC_PLANT_DHOFAR_II_WIND",
        "القدرة الاسمية لمشروع ظفار 2 لطاقة الرياح",
    ),
    "Utility scale BESS first commercial operation": (
        "ELEC_BESS_FIRST_COD",
        "بدء التشغيل التجاري لأول مشروع تخزين بالبطاريات على نطاق المرافق",
    ),
    "Pumped-hydro storage commercial operation": (
        "ELEC_PHS_COD",
        "بدء التشغيل التجاري لتخزين الطاقة بالضخ المائي",
    ),
    "MIS peak water demand": (
        "WATER_PEAK_DEMAND_MIS",
        "الطلب الأقصى على المياه في النظام الرئيسي المترابط",
    ),
    "Sharqiyah peak water demand": (
        "WATER_PEAK_DEMAND_SHARQIYAH",
        "الطلب الأقصى على المياه في منطقة الشرقية",
    ),
    "Dhofar peak water demand": (
        "WATER_PEAK_DEMAND_DHOFAR",
        "الطلب الأقصى على المياه في منطقة ظفار",
    ),
    "Ghubrah III desalination plant capacity": (
        "WATER_PLANT_GHUBRAH_III",
        "قدرة محطة الغبرة 3 لتحلية المياه",
    ),
    "Dhofar Water 2030 IWP capacity": (
        "WATER_PLANT_DHOFAR_2030",
        "قدرة مشروع مياه ظفار 2030 المستقل",
    ),
    "Additional desalination at Sohar Zone": (
        "WATER_PLANT_SOHAR_ADDITIONAL",
        "قدرة تحلية إضافية في منطقة صحار",
    ),
}
OUTLOOK_UNITS = {
    "MW": "MW",
    "%": "percent",
    "thousand m3/day": "thousand_m3_per_day",
    "m3/day": "m3_per_day",
    "year": "event",
}
SCOPES_AR = {
    "MIS system": "النظام الرئيسي المترابط", "Dhofar Power System": "نظام كهرباء ظفار",
    "Oman electricity production": "إنتاج الكهرباء في عُمان", "Ibri": "عبري", "Dhofar": "ظفار",
    "Oman (location not specified)": "عُمان (الموقع غير محدد)", "Main Interconnected System": "النظام الرئيسي المترابط",
    "Sharqiyah Zone": "منطقة الشرقية", "Dhofar Zone": "منطقة ظفار", "Ghubrah / Muscat": "الغبرة / مسقط",
    "Raysut / Dhofar": "ريسوت / ظفار", "Sohar Zone": "منطقة صحار",
}  # fmt: skip
CLASSES = {"observed": "observed", "observed_or_baseline": "observed", "forecast": "forecast", "estimate": "estimate",
           "policy_target": "policy_target", "planned": "planned", "under_consideration": "under_consideration"}  # fmt: skip
# (metric code, year) -> (value as read, status note en, status note ar).
VERIFIED_OUTLOOK = {
    ("ELEC_PEAK_DEMAND_MIS", 2025): (
        "7863",
        "The statement's base year (2025), as stated by PWP.",
        "سنة الأساس في البيان (2025) كما ذكرتها الشركة.",
    ),
    ("ELEC_PEAK_DEMAND_MIS", 2032): (
        "14147",
        "Projected; about 8.8% a year from 2025.",
        "متوقع؛ نحو 8.8٪ سنوياً منذ 2025.",
    ),
    ("ELEC_PEAK_DEMAND_DPS", 2025): (
        "850",
        "The statement's base year (2025), as stated by PWP.",
        "سنة الأساس في البيان (2025) كما ذكرتها الشركة.",
    ),
    ("ELEC_PEAK_DEMAND_DPS", 2032): (
        "1450",
        "Forecast; about 7.9% a year from 2025.",
        "متوقع؛ نحو 7.9٪ سنوياً منذ 2025.",
    ),
    ("ELEC_RENEWABLE_SHARE", 2025): (
        "9",
        '"Around 9%" of total electricity production in 2025.',
        '"نحو 9٪" من إجمالي إنتاج الكهرباء في 2025.',
    ),
    ("ELEC_RENEWABLE_SHARE_TARGET", 2030): (
        "30",
        "A national target, not an achievement; the pipeline is expected to reach it.",
        "هدف وطني وليس إنجازاً؛ يُتوقع أن تبلغه المشاريع المخطط لها.",
    ),
    ("ELEC_PLANT_IBRI_III_SOLAR", 2027): (
        "500",
        "Scheduled commercial operation Q2 2027.",
        "التشغيل التجاري المجدول في الربع الثاني 2027.",
    ),
    ("ELEC_PLANT_DHOFAR_II_WIND", 2027): (
        "125",
        "Scheduled commercial operation Q3 2027.",
        "التشغيل التجاري المجدول في الربع الثالث 2027.",
    ),
    ("ELEC_BESS_FIRST_COD", 2028): (
        None,
        "Procurement planned; anticipated commercial operation in 2028. Construction status to be confirmed separately.",
        "الطرح مخطط؛ التشغيل التجاري المتوقع في 2028. تُتحقق حالة الإنشاء بشكل منفصل.",
    ),
    ("ELEC_PHS_COD", 2032): (
        None,
        "Under procurement; commercial operation expected by the end of 2032.",
        "قيد الطرح؛ التشغيل التجاري متوقع بنهاية 2032.",
    ),
    ("WATER_PEAK_DEMAND_MIS", 2025): (
        "1211",
        "The statement's base year (2025).",
        "سنة الأساس في البيان (2025).",
    ),
    ("WATER_PEAK_DEMAND_MIS", 2032): (
        "1483",
        "Projected; about 3% a year.",
        "متوقع؛ نحو 3٪ سنوياً.",
    ),
    ("WATER_PEAK_DEMAND_SHARQIYAH", 2025): (
        "137",
        "The statement's base year (2025).",
        "سنة الأساس في البيان (2025).",
    ),
    ("WATER_PEAK_DEMAND_SHARQIYAH", 2032): (
        "178",
        "Expected; about 4% a year.",
        "متوقع؛ نحو 4٪ سنوياً.",
    ),
    ("WATER_PEAK_DEMAND_DHOFAR", 2025): (
        "201",
        "The statement's base year (2025).",
        "سنة الأساس في البيان (2025).",
    ),
    ("WATER_PEAK_DEMAND_DHOFAR", 2032): (
        "240",
        "Expected; about 3% a year.",
        "متوقع؛ نحو 3٪ سنوياً.",
    ),
    ("WATER_PLANT_GHUBRAH_III", 2027): (
        "300000",
        "Under construction according to the statement; commercial operation expected in 2027. Not delivered water.",
        "قيد الإنشاء وفق البيان؛ التشغيل التجاري متوقع في 2027. ليست مياهاً مسلّمة.",
    ),
    ("WATER_PLANT_DHOFAR_2030", 2030): (
        "80000",
        "Requested by Nama Dhofar Services; capacity range around 80,000 m³/day, to be operational by 2030; procurement planned.",
        "طلبتها نماء ظفار للخدمات؛ قدرة في حدود 80,000 م³/يوم للتشغيل بحلول 2030؛ الطرح مخطط.",
    ),
    ("WATER_PLANT_SOHAR_ADDITIONAL", 2032): (
        "150000",
        "Being considered by Nama Water Services, targeting 2032. Not a decision.",
        "تدرسها نماء لخدمات المياه بهدف 2032. ليست قراراً.",
    ),
}
_OUTLOOK_SOURCE = {
    "PWP Power 7-Year Statement 2026–2032": PWP_POWER,
    "PWP Water 7-Year Statement 2026–2032": PWP_WATER,
}


class Mismatch(Exception):
    """A workbook figure that differs from its source: the mapping stops."""


def _same(raw: object, verified: str) -> bool:
    value = _number(raw)
    return value is not None and value == Decimal(verified)


def annual(rows: list[dict[str, str]], sheet: str, out: Mapped) -> None:
    for r in _rows(rows):
        code = r.get("Indicator Code", "").strip()
        if code not in ANNUAL:
            continue
        indicator, area, unit, name = ANNUAL[code]
        for i, year in enumerate(YEARS):
            raw = r.get(year)
            if not _same(raw, VERIFIED_ANNUAL[code][i]):
                raise Mismatch(
                    f"{sheet} {code} {year}: {raw!r} is not {VERIFIED_ANNUAL[code][i]} (Year Book p. 131)"
                )
            y = year.rstrip("*")
            provisional = year.endswith("*")
            note = f"Year Book table: '{name}', {y}."
            if code == "consumption_total" and y == "2022":
                note += " Net actual consumption (36,427.1 GWh) and electricity distributed (36,178.6 GWh) are different published indicators."
            out.add(YEARBOOK, _row(
                indicator, area, f"{y}-01-01", f"{y}-12-31", True, unit, _number(raw), raw, "accepted",
                "provisional" if provisional else "reported", "Statistical Year Book 2026, Issue 54, PDF p. 131",
                note + (" Provisional." if provisional else " As published in the 2026 yearbook (earlier years may be revised)."),
            ))  # fmt: skip


def governorates(rows: list[dict[str, str]], out: Mapped) -> None:
    for r in _rows(rows):
        code = GOVERNORATES.get(r.get("Governorate EN", "").strip())
        if code is None or r.get("Year", "").strip() != "2025":
            continue
        for i, (column, indicator, unit, page) in enumerate(GOVERNORATE_COLUMNS):
            raw = r.get(column)
            if not _same(raw, VERIFIED_GOVERNORATES[code][i]):
                raise Mismatch(
                    f"Governorates_2025 {code} {column}: {raw!r} is not {VERIFIED_GOVERNORATES[code][i]} ({page})"
                )
            out.add(YEARBOOK, _row(
                indicator, code, "2025-01-01", "2025-12-31", True, unit, _number(raw), raw, "accepted", "provisional",
                f"Statistical Year Book 2026, Issue 54, {page}",
                "Governorate, 2025, provisional. Never shared out among its wilayats.",
            ))  # fmt: skip


def nama_operations(rows: list[dict[str, str]], out: Mapped) -> None:
    for r in _rows(rows):
        code, year = r.get("Indicator Code", "").strip(), str(r.get("Year", "")).strip()
        if code not in NWS:
            continue
        raw = r.get("Value")
        if not _same(raw, VERIFIED_NWS[(code, year)]):
            raise Mismatch(
                f"Nama_Water_Operations {code} {year}: {raw!r} is not {VERIFIED_NWS[(code, year)]} (report p. 23)"
            )
        indicator, name = NWS[code]
        out.add(NWS_REPORT, _row(
            indicator, "OM-GRP-NWS", f"{year}-01-01", f"{year}-12-31", True, "million_m3", _number(raw), raw, "accepted",
            "reported", "Nama Water Services Annual Report 2025, p. 23",
            f"'{name}' within Nama Water Services' own operations (all governorates except Dhofar). A utility "
            "measure: not NCSI national water production or distribution.",
        ))  # fmt: skip


# The workbook says "overview" for the water statement; the overview, with every water item, is
# PDF p. 4 (read on 24 November 2026).
_LOCATORS = {"Water PDF overview": "Water PDF p.4"}


def outlook_items(rows: list[dict[str, str]], retrieved_on: str) -> list[dict[str, object]]:
    items = []
    for r in _rows(rows):
        metric = r.get("Metric / project", "").strip()
        if metric not in OUTLOOK_METRICS:
            continue
        code, metric_ar = OUTLOOK_METRICS[metric]
        year = int(str(r.get("Year", "")).strip())
        value_as_read, note_en, note_ar = VERIFIED_OUTLOOK[(code, year)]
        raw = r.get("Value")
        if value_as_read is None:
            if _number(raw) is not None:
                raise Mismatch(f"Nama_2026_2032 {code} {year}: a date, not a value")
        elif not _same(raw, value_as_read):
            raise Mismatch(f"Nama_2026_2032 {code} {year}: {raw!r} is not {value_as_read}")
        source_name = next(k for k in _OUTLOOK_SOURCE if r.get("Source", "").strip().startswith(k))
        url = _OUTLOOK_SOURCE[source_name]
        scope = r.get("Scope / location", "").strip()
        items.append({
            "section": r.get("Sector", "").strip().lower(), "metric_code": code, "metric_en": metric, "metric_ar": metric_ar,
            "year": year, "value": value_as_read, "unit": OUTLOOK_UNITS[r.get("Unit", "").strip()],
            "scope_en": scope, "scope_ar": SCOPES_AR[scope],
            "evidence_class": CLASSES[r.get("Evidence class", "").strip()],
            "status_note_en": note_en, "status_note_ar": note_ar,
            "source_title": SOURCES[url]["title"], "source_publisher": SOURCES[url]["publisher"], "source_url": url,
            "source_locator": _LOCATORS.get(r.get("Location in source", "").strip(), r.get("Location in source", "").strip()),
            "source_sha256": SOURCES[url]["sha256"],
            "retrieved_on": retrieved_on, "issue_year": 2026,
        })  # fmt: skip
    return items
