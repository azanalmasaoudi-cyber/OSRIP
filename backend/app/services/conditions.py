"""Candidate development conditions per domain (booklet 3.36, Table 3.9).

These are research candidates, not established causes. A factor is reported as
``measured`` only when the platform holds published observations of a compatible
indicator in the requested data mode; otherwise it is a ``scenario_assumption`` that a
user may vary in a scenario, together with the evidence that would be needed to
measure it. No coefficient linking a factor to an outcome is estimated or implied.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import DataMode
from app.models import DatasetVersion, Indicator, Observation
from app.services.forecasting import INSUFFICIENT_LABEL
from app.services.observations import PUBLIC_VERSION_STATUSES


def _f(
    code: str,
    en: str,
    ar: str,
    indicators: tuple[str, ...],
    evidence_en: str,
    evidence_ar: str,
    note_en: str = "",
    note_ar: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "name": {"en": en, "ar": ar},
        "indicators": indicators,
        "evidence_needed": {"en": evidence_en, "ar": evidence_ar},
        "note": {"en": note_en, "ar": note_ar} if note_en else None,
    }


CATALOGUE: dict[str, list[dict[str, Any]]] = {
    "electricity": [
        _f(
            "demand_growth",
            "Demand growth",
            "نمو الطلب",
            ("ELEC_CONSUMPTION",),
            "A continuous series of billed consumption with stable definitions.",
            "سلسلة متصلة للاستهلاك المفوتر بتعريفات ثابتة.",
            "Consumption describes past demand; it does not by itself explain why demand changes.",
            "يصف الاستهلاك الطلب السابق، ولا يفسّر وحده سبب تغيّر الطلب.",
        ),
        _f(
            "population",
            "Population",
            "السكان",
            (),
            "Population estimates matched to the same years and service areas.",
            "تقديرات سكانية مطابقة للسنوات ومناطق الخدمة نفسها.",
        ),
        _f(
            "cooling_demand",
            "Temperature and cooling demand",
            "الحرارة والطلب على التبريد",
            (),
            "Matched weather observations (e.g. cooling degree days) and demand history.",
            "أرصاد جوية مطابقة (مثل درجات أيام التبريد) وسجل الطلب.",
        ),
        _f(
            "industrial_load",
            "Industrial expansion",
            "التوسع الصناعي",
            ("ELEC_CONSUMPTION_INDUSTRIAL",),
            "Industrial consumption with commissioned-project dates.",
            "الاستهلاك الصناعي مع تواريخ تشغيل المشروعات.",
            "Industrial consumption is a component of total consumption; do not add it to the total.",
            "الاستهلاك الصناعي مكوّن من إجمالي الاستهلاك؛ لا تجمعه مع الإجمالي.",
        ),
        _f(
            "renewables_storage",
            "Renewable generation and storage",
            "التوليد المتجدد والتخزين",
            (),
            "Generation by source and commissioned capacity of solar, wind and storage, with dates.",
            "التوليد حسب المصدر والقدرة المشغّلة للطاقة الشمسية والرياح والتخزين، مع التواريخ.",
        ),
        _f(
            "efficiency",
            "Efficiency measures",
            "تدابير الكفاءة",
            (),
            "Dated programme records and measured savings.",
            "سجلات برامج مؤرخة ووفورات مقاسة.",
        ),
        _f(
            "capacity",
            "Available capacity",
            "القدرة المتاحة",
            ("ELEC_INSTALLED_CAPACITY",),
            "Installed capacity with consistent definitions and availability factors.",
            "القدرة المركّبة بتعريفات ثابتة وعوامل إتاحة.",
            "Installed capacity is not the same as available capacity at peak.",
            "القدرة المركّبة ليست هي القدرة المتاحة وقت الذروة.",
        ),
    ],
    "water": [
        _f(
            "service_demand",
            "Population and service demand",
            "السكان والطلب على الخدمة",
            ("WATER_CONSUMPTION",),
            "Billed consumption and connections for the same areas and years.",
            "الاستهلاك المفوتر والتوصيلات للمناطق والسنوات نفسها.",
        ),
        _f(
            "desalination",
            "Desalination capacity",
            "قدرة التحلية",
            (),
            "Plant capacity and commissioning dates; production is not capacity.",
            "قدرة المحطات وتواريخ تشغيلها؛ الإنتاج ليس قدرة.",
        ),
        _f(
            "rainfall",
            "Rainfall and drought",
            "الأمطار والجفاف",
            (),
            "Hydrological and rainfall observations for matching periods.",
            "أرصاد هيدرولوجية ومطرية لفترات مطابقة.",
        ),
        _f(
            "network_losses",
            "Verified network-loss measurements",
            "قياسات موثقة لفاقد الشبكة",
            (),
            "Compatible, metered loss measurements.",
            "قياسات فاقد متوافقة ومقيسة بالعدادات.",
            "Production minus consumption is not a loss measurement (reference note Q02).",
            "الإنتاج ناقص الاستهلاك ليس قياساً للفاقد (الملاحظة المرجعية Q02).",
        ),
        _f(
            "reuse",
            "Wastewater reuse",
            "إعادة استخدام المياه المعالجة",
            (),
            "Treated-wastewater volumes and reuse by purpose.",
            "أحجام مياه الصرف المعالجة وإعادة استخدامها حسب الغرض.",
        ),
        _f(
            "energy_for_water",
            "Energy requirements",
            "متطلبات الطاقة",
            (),
            "Energy used per cubic metre produced, by technology.",
            "الطاقة المستخدمة لكل متر مكعب منتج حسب التقنية.",
        ),
        _f(
            "irrigation",
            "Irrigation demand",
            "الطلب على الري",
            (),
            "Agricultural water-use estimates with stated methods.",
            "تقديرات استخدام المياه في الزراعة مع بيان الطرق.",
        ),
    ],
    "food_security": [
        _f(
            "cultivated_area",
            "Cultivated area",
            "المساحة المزروعة",
            ("AGRI_CULTIVATED_AREA",),
            "Cultivated area with consistent crop coverage.",
            "المساحة المزروعة بتغطية محاصيل ثابتة.",
        ),
        _f(
            "crop_yields",
            "Crop yields",
            "إنتاجية المحاصيل",
            (),
            "Production and area for the same crops and years (yield is not published directly).",
            "الإنتاج والمساحة للمحاصيل والسنوات نفسها (الإنتاجية غير منشورة مباشرة).",
        ),
        _f(
            "crop_production",
            "Crop production",
            "إنتاج المحاصيل",
            ("AGRI_CROP_PRODUCTION",),
            "Production by crop group with consistent definitions.",
            "الإنتاج حسب مجموعة المحاصيل بتعريفات ثابتة.",
        ),
        _f(
            "irrigation_availability",
            "Irrigation availability",
            "توفر مياه الري",
            (),
            "Falaj and well flow observations and allocation records.",
            "أرصاد تدفق الأفلاج والآبار وسجلات التخصيص.",
        ),
        _f(
            "climate",
            "Temperature and rainfall",
            "الحرارة والأمطار",
            (),
            "Weather observations matched to growing seasons.",
            "أرصاد جوية مطابقة لمواسم الزراعة.",
        ),
        _f(
            "input_costs",
            "Input costs",
            "تكاليف المدخلات",
            (),
            "Fertiliser, feed, energy and labour cost series.",
            "سلاسل تكاليف الأسمدة والأعلاف والطاقة والعمالة.",
        ),
        _f(
            "cold_chain",
            "Storage and cold-chain capacity",
            "قدرة التخزين وسلسلة التبريد",
            (),
            "Storage capacity and stock records.",
            "قدرة التخزين وسجلات المخزون.",
        ),
        _f(
            "import_dependence",
            "Import dependence and supply disruption",
            "الاعتماد على الواردات واضطراب الإمدادات",
            (),
            "Commodity-matched production and trade in the same units and years.",
            "إنتاج وتجارة مطابقان للسلع بالوحدات والسنوات نفسها.",
            "Self-sufficiency figures are dated statements, not a series (reference note Q03).",
            "أرقام الاكتفاء الذاتي تصريحات مؤرخة وليست سلسلة (الملاحظة المرجعية Q03).",
        ),
        _f(
            "fisheries",
            "Fish landings",
            "إنزال الأسماك",
            ("FISH_CAPTURE_LANDINGS",),
            "Landings by fleet segment with consistent coverage.",
            "الإنزال حسب فئة الأسطول بتغطية ثابتة.",
        ),
    ],
    "trade": [
        _f(
            "export_composition",
            "Export composition",
            "تركيبة الصادرات",
            ("TRADE_NON_OIL_EXPORTS", "TRADE_OIL_GAS_EXPORTS", "TRADE_REEXPORTS"),
            "Exports by product group under one classification.",
            "الصادرات حسب مجموعة المنتجات وفق تصنيف واحد.",
        ),
        _f(
            "partner_concentration",
            "Partner concentration",
            "تركّز الشركاء",
            ("TRADE_MERCH_IMPORTS",),
            "Trade by partner with stated coverage of the total.",
            "التجارة حسب الشريك مع بيان تغطية الإجمالي.",
            "Partner tables in the reference pack cover the leading partners only.",
            "جداول الشركاء في الحزمة المرجعية تغطي الشركاء الرئيسيين فقط.",
        ),
        _f(
            "ports_logistics",
            "Port and logistics capacity",
            "قدرة الموانئ والخدمات اللوجستية",
            (),
            "Port throughput and capacity series.",
            "سلاسل مناولة الموانئ وقدرتها.",
        ),
        _f(
            "transport_costs",
            "Transport costs",
            "تكاليف النقل",
            (),
            "Freight-rate series for relevant routes.",
            "سلاسل أسعار الشحن للطرق المعنية.",
        ),
        _f(
            "commodity_prices",
            "Commodity prices",
            "أسعار السلع",
            (),
            "Price series for the main traded commodities.",
            "سلاسل أسعار للسلع الرئيسية المتداولة.",
        ),
        _f(
            "external_demand",
            "External demand",
            "الطلب الخارجي",
            (),
            "Partner-economy demand indicators.",
            "مؤشرات الطلب في اقتصادات الشركاء.",
        ),
        _f(
            "policy_changes",
            "Documented policy or tariff changes",
            "تغييرات موثقة في السياسات أو التعرفة",
            (),
            "Dated, verified policy and tariff records.",
            "سجلات سياسات وتعرفة مؤرخة وموثقة.",
        ),
    ],
}

EXPLANATION = {
    "en": "Candidate factors that may influence future development. They are not proven causes, "
    "and no effect size is estimated. A factor counts as measured only when OSRIP holds a published, "
    "compatible series for it; otherwise it can only be explored as a stated assumption in a scenario.",
    "ar": "عوامل مرشّحة قد تؤثر في التطور المستقبلي. وهي ليست أسباباً مثبتة، ولا يُقدَّر حجم أثرها. "
    "يُعد العامل مقيساً فقط عندما يملك OSRIP سلسلة منشورة متوافقة له؛ وإلا فلا يمكن استكشافه إلا "
    "بوصفه افتراضاً معلناً في سيناريو.",
}


def _published(session: Session, data_mode: DataMode) -> dict[str, dict[str, Any]]:
    """Indicator code -> observation count and last period, for published versions in the mode."""
    rows = session.execute(
        select(Indicator.code, func.count(Observation.id), func.max(Observation.period_end))
        .join(Observation, Observation.indicator_id == Indicator.id)
        .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
        .where(
            DatasetVersion.data_mode == data_mode,
            DatasetVersion.status.in_(PUBLIC_VERSION_STATUSES),
            Observation.value.is_not(None),
        )
        .group_by(Indicator.code)
    ).all()
    return {code: {"observations": n, "last_period": last.isoformat()} for code, n, last in rows}


def conditions(session: Session, data_mode: DataMode) -> dict[str, Any]:
    published = _published(session, data_mode)
    domains = {}
    for domain, factors in CATALOGUE.items():
        out = []
        for factor in factors:
            measured = [
                {"indicator": code, **published[code]}
                for code in factor["indicators"]
                if code in published
            ]
            out.append(
                {
                    **{k: v for k, v in factor.items() if k != "indicators"},
                    "candidate_indicators": list(factor["indicators"]),
                    "status": "measured" if measured else "scenario_assumption",
                    "measured_by": measured,
                }
            )
        domains[domain] = out
    return {
        "data_mode": data_mode.value,
        "explanation": EXPLANATION,
        "insufficient_label": INSUFFICIENT_LABEL,
        "domains": domains,
    }
