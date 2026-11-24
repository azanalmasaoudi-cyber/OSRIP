# ruff: noqa: E501 - bilingual sentences are kept on one line each, as in services/studies.py
"""Recommendations for one selection once its objectives are known: the last step of a sector's
guided analysis.

Rule-based and reproducible (no AI): the facts are read from the same timeline the results and
the analysis show (``timeline.build``), and every action comes from a fixed template for the
sector and objective, chosen by what those facts say (rising, falling or flat; how complete the
range is). The text quotes only figures from that timeline; it never adds a number of its own.
Each action carries its rationale (the facts it rests on), prerequisites, risks and the evidence
that OSRIP does not publish for the area, so a person can judge it. They are prompts for review,
not decisions or forecasts of outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.enums import DataMode, Section
from app.services import objectives as obj
from app.services import timeline

RULES_VERSION = "2026.11-1"
# A change of less than this share (in %) between the first and last values counts as flat.
FLAT_PCT = Decimal("1")

T = dict[str, str]


def _t(en: str, ar: str) -> T:
    return {"en": en, "ar": ar}


# Indicators whose absence for the area is reported as missing evidence, by sector.
RELATED: dict[str, tuple[str, ...]] = {
    "electricity": (
        "ELEC_PEAK_DEMAND",
        "ELEC_INSTALLED_CAPACITY",
        "ELEC_CONSUMPTION",
        "ELEC_DISTRIBUTION",
    ),
    "water": ("WATER_PRODUCTION", "WATER_DISTRIBUTION", "WATER_CONSUMPTION", "WATER_SUBSCRIBERS"),
    "food_security": (
        "AGRI_PROD_DATES",
        "FISH_CAPTURE_LANDINGS",
        "SELF_SUFFICIENCY_DATES",
        "SELF_SUFFICIENCY_FISH",
    ),
    "trade": (
        "TRADE_MERCH_EXPORTS",
        "TRADE_MERCH_IMPORTS",
        "TRADE_NON_OIL_EXPORTS",
        "TRADE_REEXPORTS",
    ),
}


@dataclass(frozen=True)
class Template:
    title: T
    rising: T
    falling: T
    flat: T
    prerequisites: tuple[T, ...]
    risks: tuple[T, ...]


def _tpl(
    title: T, rising: T, falling: T, flat: T, pre: tuple[T, ...], risks: tuple[T, ...]
) -> Template:
    return Template(title, rising, falling, flat, pre, risks)


_SAME = _t(
    "Confirm the series with the publisher before acting on it.",
    "تأكيد السلسلة مع الجهة الناشرة قبل البناء عليها.",
)

# One action per sector and objective. {indicator} and {area} are filled in; the rationale
# sentence for the direction follows the facts.
TEMPLATES: dict[str, dict[str, Template]] = {
    "electricity": {
        "reduce_shortages": _tpl(
            _t(
                "Check supply headroom against demand in {area}",
                "مراجعة هامش الإمداد مقابل الطلب في {area}",
            ),
            _t(
                "{indicator} is rising, so compare its growth with peak demand and installed capacity before planning new supply.",
                "يرتفع {indicator}، فتُقارن وتيرته بالحمل الأقصى والقدرة المركبة قبل التخطيط لإمدادات جديدة.",
            ),
            _t(
                "{indicator} is falling: find out whether supply moved to other plants or the grid before treating it as a shortage.",
                "ينخفض {indicator}: يُتحقق هل انتقل الإمداد إلى محطات أخرى أو إلى الشبكة قبل عدّه عجزاً.",
            ),
            _t(
                "{indicator} is broadly flat: test whether demand growth is being met by imports from other grids.",
                "{indicator} شبه ثابت: يُختبر هل يُغطّى نمو الطلب بنقل الطاقة من شبكات أخرى.",
            ),
            (
                _t(
                    "Peak demand and installed capacity for the same area and years.",
                    "الحمل الأقصى والقدرة المركبة للمنطقة والسنوات نفسها.",
                ),
                _t(
                    "Planned plant additions and retirements from the grid operator.",
                    "الإضافات والإحالات المخطط لها من مشغل الشبكة.",
                ),
            ),
            (
                _t(
                    "Generation in an area is not its consumption: grids move power between governorates.",
                    "التوليد في منطقة ما ليس استهلاكها: الشبكات تنقل الطاقة بين المحافظات.",
                ),
            ),
        ),
        "improve_efficiency": _tpl(
            _t(
                "Compare generation with electricity distributed in {area}",
                "مقارنة التوليد بالكهرباء الموزعة في {area}",
            ),
            _t(
                "With {indicator} rising, check that distributed electricity grows at a similar pace; a widening gap would point to losses or transfers.",
                "مع ارتفاع {indicator} يُتحقق أن الكهرباء الموزعة تنمو بوتيرة مماثلة؛ اتساع الفجوة يشير إلى فاقد أو نقل.",
            ),
            _t(
                "With {indicator} falling, check whether the fall comes from fewer losses or from less output.",
                "مع انخفاض {indicator} يُتحقق هل الانخفاض من تقليل الفاقد أم من تراجع الإنتاج.",
            ),
            _t(
                "With {indicator} flat, efficiency gains would show as falling losses per unit delivered; that needs distribution and loss data.",
                "مع ثبات {indicator} تظهر مكاسب الكفاءة في انخفاض الفاقد لكل وحدة مُسلَّمة؛ وذلك يحتاج بيانات التوزيع والفاقد.",
            ),
            (
                _t(
                    "Electricity distributed and network losses for the same area and years.",
                    "الكهرباء الموزعة وفاقد الشبكة للمنطقة والسنوات نفسها.",
                ),
            ),
            (
                _t(
                    "Gross production minus distribution is not a measured loss: transfers and station use are part of it.",
                    "الإنتاج الإجمالي ناقص التوزيع ليس فاقداً مقيساً: يدخل فيه النقل والاستهلاك الذاتي للمحطات.",
                ),
            ),
        ),
        "use_surplus": _tpl(
            _t(
                "Study whether spare generation in {area} can serve other grids",
                "دراسة إمكانية خدمة شبكات أخرى بفائض التوليد في {area}",
            ),
            _t(
                "{indicator} is rising; if it exceeds local demand, interconnection or storage could put the difference to use.",
                "يرتفع {indicator}؛ فإن تجاوز الطلب المحلي قد يتيح الربط أو التخزين الاستفادة من الفارق.",
            ),
            _t(
                "{indicator} is falling, so any surplus is shrinking; check the trend before committing to new outlets.",
                "ينخفض {indicator}، فأي فائض يتقلص؛ تُراجع الوتيرة قبل الالتزام بمنافذ جديدة.",
            ),
            _t(
                "{indicator} is flat; a surplus, if any, is stable enough to study interconnection options.",
                "{indicator} ثابت؛ الفائض إن وُجد مستقر بما يكفي لدراسة خيارات الربط.",
            ),
            (
                _t(
                    "Local consumption or distribution for the same area and years, to show whether a surplus exists.",
                    "الاستهلاك أو التوزيع المحلي للمنطقة والسنوات نفسها لبيان وجود فائض.",
                ),
            ),
            (
                _t(
                    "A surplus is not established by production figures alone.",
                    "لا يثبت الفائض من أرقام الإنتاج وحدها.",
                ),
            ),
        ),
        "strengthen": _tpl(
            _t(
                "Prioritise reliable supply where demand grows fastest",
                "إعطاء الأولوية لموثوقية الإمداد حيث ينمو الطلب أسرع",
            ),
            _t(
                "{indicator} is rising; keep capacity and network plans in step with it.",
                "يرتفع {indicator}؛ تُبقى خطط القدرة والشبكة متوافقة معه.",
            ),
            _t(
                "{indicator} is falling; identify which plants or areas explain the fall.",
                "ينخفض {indicator}؛ تُحدد المحطات أو المناطق المسببة.",
            ),
            _t(
                "{indicator} is flat; check that it is matched by stable demand.",
                "{indicator} ثابت؛ يُتحقق من مقابلته بطلب مستقر.",
            ),
            (
                _t(
                    "Demand forecasts and plant-level data from the operator.",
                    "توقعات الطلب وبيانات المحطات من المشغل.",
                ),
            ),
            (
                _t(
                    "Expanding supply ahead of demand raises costs.",
                    "التوسع في الإمداد قبل الطلب يرفع التكاليف.",
                ),
            ),
        ),
        "diversify": _tpl(
            _t("Map the generation mix behind {indicator}", "رسم مزيج التوليد وراء {indicator}"),
            _t(
                "{indicator} is rising; record how much of the growth comes from each source.",
                "يرتفع {indicator}؛ يُسجل نصيب كل مصدر من النمو.",
            ),
            _t(
                "{indicator} is falling; check whether one source dominates the change.",
                "ينخفض {indicator}؛ يُتحقق هل يهيمن مصدر واحد على التغير.",
            ),
            _t(
                "{indicator} is flat; a diversification study needs the mix by source.",
                "{indicator} ثابت؛ دراسة التنويع تحتاج المزيج حسب المصدر.",
            ),
            (
                _t(
                    "Generation by source (gas, solar, wind) for the same area and years.",
                    "التوليد حسب المصدر (غاز، شمس، رياح) للمنطقة والسنوات نفسها.",
                ),
            ),
            (
                _t(
                    "OSRIP does not publish generation by fuel or technology.",
                    "لا ينشر OSRIP التوليد حسب الوقود أو التقنية.",
                ),
            ),
        ),
    },
    "water": {
        "reduce_shortages": _tpl(
            _t(
                "Check water supply against demand in {area}",
                "مراجعة إمدادات المياه مقابل الطلب في {area}",
            ),
            _t(
                "{indicator} is rising; check that storage and distribution keep pace in peak months.",
                "يرتفع {indicator}؛ يُتحقق أن التخزين والتوزيع يواكبانه في أشهر الذروة.",
            ),
            _t(
                "{indicator} is falling; check whether demand is being met from other sources or areas.",
                "ينخفض {indicator}؛ يُتحقق هل يُغطّى الطلب من مصادر أو مناطق أخرى.",
            ),
            _t(
                "{indicator} is flat; with population growth, flat supply can mean less water per person.",
                "{indicator} ثابت؛ مع نمو السكان قد يعني ثبات الإمداد انخفاض نصيب الفرد.",
            ),
            (
                _t(
                    "Consumption and subscribers for the same area and years.",
                    "الاستهلاك والمشتركون للمنطقة والسنوات نفسها.",
                ),
                _t(
                    "Population for the same years (context only).",
                    "السكان للسنوات نفسها (للسياق فقط).",
                ),
            ),
            (
                _t(
                    "Production and distribution are different measures; neither is consumption.",
                    "الإنتاج والتوزيع مقياسان مختلفان، وليس أي منهما استهلاكاً.",
                ),
            ),
        ),
        "improve_efficiency": _tpl(
            _t(
                "Measure non-revenue water before setting a target",
                "قياس المياه غير المحاسب عليها قبل وضع هدف",
            ),
            _t(
                "{indicator} is rising; a loss-reduction programme can save more than new production.",
                "يرتفع {indicator}؛ برنامج خفض الفاقد قد يوفر أكثر من إنتاج جديد.",
            ),
            _t(
                "{indicator} is falling; confirm whether lower losses explain it.",
                "ينخفض {indicator}؛ يُتأكد هل يفسره انخفاض الفاقد.",
            ),
            _t(
                "{indicator} is flat; efficiency gains need metered losses to be seen.",
                "{indicator} ثابت؛ مكاسب الكفاءة تحتاج فاقداً مقيساً لتظهر.",
            ),
            (
                _t(
                    "Metered non-revenue water from the utility.",
                    "المياه غير المحاسب عليها المقيسة من المرفق.",
                ),
            ),
            (
                _t(
                    "Production minus distribution is not leakage: it includes storage and unmetered use.",
                    "الإنتاج ناقص التوزيع ليس تسرباً: يشمل التخزين والاستخدام غير المقيس.",
                ),
            ),
        ),
        "use_surplus": _tpl(
            _t(
                "Study whether spare production in {area} can be stored or transferred",
                "دراسة تخزين فائض الإنتاج في {area} أو نقله",
            ),
            _t(
                "{indicator} is rising; storage or transfer could serve neighbouring areas.",
                "يرتفع {indicator}؛ قد يخدم التخزين أو النقل المناطق المجاورة.",
            ),
            _t(
                "{indicator} is falling; a surplus may not last.",
                "ينخفض {indicator}؛ قد لا يدوم الفائض.",
            ),
            _t(
                "{indicator} is flat; check local demand before assuming a surplus.",
                "{indicator} ثابت؛ يُراجع الطلب المحلي قبل افتراض فائض.",
            ),
            (
                _t(
                    "Local consumption for the same area and years.",
                    "الاستهلاك المحلي للمنطقة والسنوات نفسها.",
                ),
            ),
            (
                _t(
                    "A surplus is not shown by production figures alone.",
                    "لا يظهر الفائض من أرقام الإنتاج وحدها.",
                ),
            ),
        ),
        "strengthen": _tpl(
            _t("Plan supply resilience for {area}", "تخطيط مرونة الإمداد في {area}"),
            _t(
                "{indicator} is rising; keep desalination and network plans aligned with it.",
                "يرتفع {indicator}؛ تُبقى خطط التحلية والشبكة متوافقة معه.",
            ),
            _t(
                "{indicator} is falling; identify which plants or wells explain the fall.",
                "ينخفض {indicator}؛ تُحدد المحطات أو الآبار المسببة.",
            ),
            _t(
                "{indicator} is flat; test resilience to a plant outage.",
                "{indicator} ثابت؛ تُختبر المرونة عند توقف محطة.",
            ),
            (_t("Plant-level production and outage records.", "إنتاج المحطات وسجلات التوقف."),),
            (
                _t(
                    "New capacity is costly and energy-intensive.",
                    "القدرة الجديدة مكلفة وكثيفة الطاقة.",
                ),
            ),
        ),
        "diversify": _tpl(
            _t("Map the water sources behind {indicator}", "رسم مصادر المياه وراء {indicator}"),
            _t(
                "{indicator} is rising; record the share from desalination, wells and treated water.",
                "يرتفع {indicator}؛ تُسجل حصص التحلية والآبار والمياه المعالجة.",
            ),
            _t(
                "{indicator} is falling; check which source declined.",
                "ينخفض {indicator}؛ يُتحقق أي مصدر تراجع.",
            ),
            _t(
                "{indicator} is flat; diversification needs production by source.",
                "{indicator} ثابت؛ التنويع يحتاج الإنتاج حسب المصدر.",
            ),
            (
                _t(
                    "Production by source for the same area and years.",
                    "الإنتاج حسب المصدر للمنطقة والسنوات نفسها.",
                ),
            ),
            (
                _t(
                    "OSRIP does not publish water production by source.",
                    "لا ينشر OSRIP إنتاج المياه حسب المصدر.",
                ),
            ),
        ),
    },
    "food_security": {
        "reduce_shortages": _tpl(
            _t(
                "Check self-sufficiency for this product before acting",
                "مراجعة الاكتفاء الذاتي لهذا المنتج قبل التصرف",
            ),
            _t(
                "{indicator} is rising; compare it with consumption to see whether imports can fall.",
                "يرتفع {indicator}؛ يُقارن بالاستهلاك لمعرفة هل يمكن خفض الواردات.",
            ),
            _t(
                "{indicator} is falling; check stocks and imports that cover the gap.",
                "ينخفض {indicator}؛ يُراجع المخزون والواردات التي تسد الفجوة.",
            ),
            _t(
                "{indicator} is flat; with population growth, supply per person may fall.",
                "{indicator} ثابت؛ مع نمو السكان قد ينخفض نصيب الفرد.",
            ),
            (
                _t(
                    "Self-sufficiency ratio and imports of the same product.",
                    "نسبة الاكتفاء الذاتي وواردات المنتج نفسه.",
                ),
            ),
            (
                _t(
                    "Production is one part of food security, alongside imports, stocks and access.",
                    "الإنتاج جزء من الأمن الغذائي إلى جانب الواردات والمخزون والوصول.",
                ),
            ),
        ),
        "improve_efficiency": _tpl(
            _t(
                "Look at water and land use per unit produced",
                "دراسة استخدام المياه والأرض لكل وحدة منتجة",
            ),
            _t(
                "{indicator} is rising; check whether irrigation use rises with it.",
                "يرتفع {indicator}؛ يُتحقق هل يرتفع استخدام الري معه.",
            ),
            _t(
                "{indicator} is falling; check yields and post-harvest losses.",
                "ينخفض {indicator}؛ تُراجع الإنتاجية وفاقد ما بعد الحصاد.",
            ),
            _t(
                "{indicator} is flat; efficiency gains need yields and inputs.",
                "{indicator} ثابت؛ مكاسب الكفاءة تحتاج الإنتاجية والمدخلات.",
            ),
            (
                _t(
                    "Cultivated area, irrigation withdrawals and yields.",
                    "المساحة المزروعة وسحب مياه الري والإنتاجية.",
                ),
            ),
            (
                _t(
                    "OSRIP does not publish irrigation water by product.",
                    "لا ينشر OSRIP مياه الري حسب المنتج.",
                ),
            ),
        ),
        "use_surplus": _tpl(
            _t("Study markets for surplus output", "دراسة أسواق للإنتاج الفائض"),
            _t(
                "{indicator} is rising; processing, storage or exports could absorb a surplus.",
                "يرتفع {indicator}؛ قد يستوعب التصنيع أو التخزين أو التصدير الفائض.",
            ),
            _t(
                "{indicator} is falling; a surplus may be shrinking.",
                "ينخفض {indicator}؛ قد يتقلص الفائض.",
            ),
            _t(
                "{indicator} is flat; check demand before investing in outlets.",
                "{indicator} ثابت؛ يُراجع الطلب قبل الاستثمار في المنافذ.",
            ),
            (
                _t(
                    "Consumption, stocks and export data for the product.",
                    "بيانات الاستهلاك والمخزون والصادرات للمنتج.",
                ),
            ),
            (_t("A surplus is not shown by production alone.", "لا يظهر الفائض من الإنتاج وحده."),),
        ),
        "strengthen": _tpl(
            _t("Support producers where output is growing", "دعم المنتجين حيث ينمو الإنتاج"),
            _t(
                "{indicator} is rising; value-chain support can keep the gains.",
                "يرتفع {indicator}؛ دعم سلسلة القيمة يحافظ على المكاسب.",
            ),
            _t(
                "{indicator} is falling; identify the causes with producers.",
                "ينخفض {indicator}؛ تُحدد الأسباب مع المنتجين.",
            ),
            _t(
                "{indicator} is flat; look for constraints on growth.",
                "{indicator} ثابت؛ يُبحث عن قيود النمو.",
            ),
            (
                _t(
                    "Farm or landing data by area, with costs.",
                    "بيانات المزارع أو الإنزال حسب المنطقة مع التكاليف.",
                ),
            ),
            (
                _t(
                    "Support schemes have costs and need evaluation.",
                    "برامج الدعم لها تكاليف وتحتاج تقييماً.",
                ),
            ),
        ),
        "diversify": _tpl(
            _t(
                "Compare this product with other food products in the area",
                "مقارنة هذا المنتج بمنتجات غذائية أخرى في المنطقة",
            ),
            _t(
                "{indicator} is rising; check dependence on one product.",
                "يرتفع {indicator}؛ يُتحقق من الاعتماد على منتج واحد.",
            ),
            _t(
                "{indicator} is falling; other products may offset it.",
                "ينخفض {indicator}؛ قد تعوضه منتجات أخرى.",
            ),
            _t(
                "{indicator} is flat; diversification needs production of other products.",
                "{indicator} ثابت؛ التنويع يحتاج إنتاج منتجات أخرى.",
            ),
            (
                _t(
                    "Production of other products in the same area and years.",
                    "إنتاج منتجات أخرى في المنطقة والسنوات نفسها.",
                ),
            ),
            (
                _t(
                    "Products differ in water use and market risk.",
                    "تختلف المنتجات في استهلاك المياه ومخاطر السوق.",
                ),
            ),
        ),
    },
    "trade": {
        "reduce_shortages": _tpl(
            _t(
                "Check import dependence for essential goods",
                "مراجعة الاعتماد على الواردات في السلع الأساسية",
            ),
            _t(
                "{indicator} is rising; check which goods and partners account for it.",
                "يرتفع {indicator}؛ تُحدد السلع والشركاء المسببون.",
            ),
            _t(
                "{indicator} is falling; check whether supply of essential goods is affected.",
                "ينخفض {indicator}؛ يُتحقق هل تأثر إمداد السلع الأساسية.",
            ),
            _t(
                "{indicator} is flat; concentration on few partners is the risk to check.",
                "{indicator} ثابت؛ التركز على شركاء قليلين هو الخطر الواجب فحصه.",
            ),
            (_t("Imports by commodity and partner.", "الواردات حسب السلعة والشريك."),),
            (
                _t(
                    "Trade totals hide which goods are essential.",
                    "إجماليات التجارة تخفي أي السلع أساسية.",
                ),
            ),
        ),
        "improve_efficiency": _tpl(
            _t("Review trade logistics for {area}", "مراجعة لوجستيات التجارة في {area}"),
            _t(
                "{indicator} is rising; port and customs capacity should keep pace.",
                "يرتفع {indicator}؛ يجب أن تواكبه طاقة الموانئ والجمارك.",
            ),
            _t(
                "{indicator} is falling; check whether costs or delays contribute.",
                "ينخفض {indicator}؛ يُتحقق هل تسهم التكاليف أو التأخير.",
            ),
            _t(
                "{indicator} is flat; logistics gains need time and cost data.",
                "{indicator} ثابت؛ مكاسب اللوجستيات تحتاج بيانات الوقت والتكلفة.",
            ),
            (_t("Clearance times and logistics costs.", "أزمنة التخليص وتكاليف اللوجستيات."),),
            (_t("OSRIP does not publish logistics data.", "لا ينشر OSRIP بيانات لوجستية."),),
        ),
        "use_surplus": _tpl(
            _t("Match surplus production with export markets", "ربط الإنتاج الفائض بأسواق التصدير"),
            _t(
                "{indicator} is rising; identify partners that absorb the growth.",
                "يرتفع {indicator}؛ يُحدد الشركاء الذين يستوعبون النمو.",
            ),
            _t(
                "{indicator} is falling; check market access for the products concerned.",
                "ينخفض {indicator}؛ يُراجع النفاذ إلى الأسواق للمنتجات المعنية.",
            ),
            _t(
                "{indicator} is flat; new markets need product-level data.",
                "{indicator} ثابت؛ الأسواق الجديدة تحتاج بيانات على مستوى المنتج.",
            ),
            (_t("Exports by product and partner.", "الصادرات حسب المنتج والشريك."),),
            (
                _t(
                    "Export growth depends on prices outside Oman's control.",
                    "نمو الصادرات يعتمد على أسعار خارج سيطرة عُمان.",
                ),
            ),
        ),
        "strengthen": _tpl(
            _t("Build on the trade flows that are growing", "البناء على التدفقات التجارية النامية"),
            _t(
                "{indicator} is rising; check which products drive it and support them.",
                "يرتفع {indicator}؛ تُحدد المنتجات الدافعة وتُدعم.",
            ),
            _t(
                "{indicator} is falling; identify the products and partners behind the fall.",
                "ينخفض {indicator}؛ تُحدد المنتجات والشركاء وراء الانخفاض.",
            ),
            _t(
                "{indicator} is flat; growth needs new products or partners.",
                "{indicator} ثابت؛ النمو يحتاج منتجات أو شركاء جدداً.",
            ),
            (
                _t(
                    "Trade by product and partner for the same years.",
                    "التجارة حسب المنتج والشريك للسنوات نفسها.",
                ),
            ),
            (
                _t(
                    "Oil prices can move totals regardless of policy.",
                    "قد تحرك أسعار النفط الإجماليات بغض النظر عن السياسات.",
                ),
            ),
        ),
        "diversify": _tpl(
            _t("Track the non-oil share of trade", "متابعة حصة غير النفط من التجارة"),
            _t(
                "{indicator} is rising; check how much of the rise is non-oil.",
                "يرتفع {indicator}؛ يُتحقق كم من الارتفاع غير نفطي.",
            ),
            _t(
                "{indicator} is falling; check whether oil or non-oil explains it.",
                "ينخفض {indicator}؛ يُتحقق هل يفسره النفط أم غيره.",
            ),
            _t(
                "{indicator} is flat; diversification shows in the non-oil share.",
                "{indicator} ثابت؛ يظهر التنويع في حصة غير النفط.",
            ),
            (
                _t(
                    "Non-oil exports and re-exports for the same years.",
                    "الصادرات غير النفطية وإعادة التصدير للسنوات نفسها.",
                ),
            ),
            (
                _t(
                    "Commercial registrations are not trade values.",
                    "السجلات التجارية ليست قيماً تجارية.",
                ),
            ),
        ),
    },
}


def _num(value: str | None) -> str | None:
    """The published value as published (every digit kept), with thousands separators."""
    if value is None:
        return None
    try:
        d = Decimal(value)
    except InvalidOperation:
        return value
    return f"{d.normalize():,f}" if d == d.to_integral_value() else f"{d:,f}"


def _period(start: str, view: str) -> str:
    if view == "monthly":
        return start[:7]
    if view == "quarterly":
        return f"{start[:4]} Q{(int(start[5:7]) - 1) // 3 + 1}"
    return start[:4]


def _direction(change: dict[str, Any] | None) -> str | None:
    if not change or change.get("percent") is None:
        return None
    pct = Decimal(change["percent"])
    if pct > FLAT_PCT:
        return "rising"
    if pct < -FLAT_PCT:
        return "falling"
    return "flat"


def _published_indicators(session: Session, data_mode: DataMode, area: str) -> set[str]:
    rows = session.execute(
        text(
            "SELECT DISTINCT i.code FROM observation o JOIN indicator i ON i.id = o.indicator_id "
            "JOIN area a ON a.id = o.area_id JOIN dataset_version dv ON dv.id = o.dataset_version_id "
            "WHERE o.data_mode = :mode AND dv.status = 'published' AND a.code = :area AND o.value IS NOT NULL"
        ),
        {"mode": data_mode.value, "area": area},
    )
    return {r[0] for r in rows}


def _names(session: Session, codes: tuple[str, ...]) -> dict[str, T]:
    rows = session.execute(
        text("SELECT code, name_en, name_ar FROM indicator WHERE code = ANY(:codes)"),
        {"codes": list(codes)},
    )
    return {r[0]: _t(r[1], r[2]) for r in rows}


def _area_name(session: Session, code: str) -> T:
    row = session.execute(
        text("SELECT name_en, name_ar FROM area WHERE code = :c"), {"c": code}
    ).first()
    return _t(row[0], row[1]) if row else _t(code, code)


def recommend(
    session: Session,
    section: Section,
    data_mode: DataMode,
    indicator: str,
    *,
    area: str = "OM",
    view: str = "annual",
    commodity: str | None = None,
    partner: str | None = None,
    flow: str | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    objectives: list[str],
    note: str = "",
) -> dict[str, Any]:
    """Facts, ranked actions and missing evidence for the selection and its objectives."""
    chosen = obj.clean([*objectives, *obj.detect(note)])
    doc = timeline.build(
        session, data_mode, indicator, area=area, view=view, commodity=commodity, partner=partner,
        flow=flow, period_from=period_from, period_to=period_to,
    )  # fmt: skip
    out: dict[str, Any] = {
        "rules_version": RULES_VERSION,
        "section": section.value,
        "data_mode": data_mode.value,
        "indicator": doc["indicator"],
        "area": {"code": area, "name": _area_name(session, area)},
        "view": view,
        "objectives": [{"code": c, "name": obj.NAMES[c]} for c in chosen],
        "note_recognised": bool(note.strip()) and bool(obj.detect(note)),
        "facts": [],
        "actions": [],
        "missing_evidence": [],
        "limitations": [
            _t(
                "Rule-based prompts for review, chosen from the published figures shown in the results; not forecasts, "
                "decisions or guaranteed outcomes.",
                "توجيهات قائمة على قواعد للمراجعة، مختارة من الأرقام المنشورة المعروضة في النتائج؛ ليست تنبؤات ولا قرارات ولا نتائج مضمونة.",
            ),
        ],
    }
    if doc.get("status") != "ok":
        out["status"] = "no_data"
        return out
    if not chosen:
        out["status"] = "needs_objectives"
        return out

    unit = doc["unit"]["label"]
    s = doc["summary"]
    ind_name: T = doc["indicator"]["name"]
    area_name: T = out["area"]["name"]
    facts: list[dict[str, Any]] = []
    if s.get("last"):
        last = s["last"]
        v = f"{last.get('value_operator') or ''}{_num(last['value'])}"
        facts.append(
            {
                "id": "F1",
                "kind": "latest",
                "text": _t(
                    f"Latest published value: {v} {unit['en']} ({_period(last['period_start'], view)}).",
                    f"آخر قيمة منشورة: {v} {unit['ar']} ({_period(last['period_start'], view)}).",
                ),
            }
        )
    direction = _direction(s.get("change"))
    if s.get("change") and s["change"].get("percent") is not None and s.get("first"):
        pct = Decimal(s["change"]["percent"]).quantize(Decimal("0.1"))
        sign = "+" if pct > 0 else ""
        a, b = _period(s["first"]["period_start"], view), _period(s["last"]["period_start"], view)
        facts.append(
            {
                "id": "F2",
                "kind": "change",
                "text": _t(
                    f"Change from {a} to {b}: {sign}{pct}%.",
                    f"التغير من {a} إلى {b}: {sign}{pct}٪.",
                ),
            }
        )
    facts.append(
        {
            "id": "F3",
            "kind": "coverage",
            "text": _t(
                f"Periods in the range with a published value: {s['with_value']} of {s['periods']}; missing (not zero): {s['missing']}.",
                f"فترات النطاق ذات القيمة المنشورة: {s['with_value']} من {s['periods']}؛ المفقودة (وليست صفراً): {s['missing']}.",
            ),
        }
    )
    if doc.get("year_to_date"):
        facts.append(
            {
                "id": "F4",
                "kind": "year_to_date",
                "text": _t(
                    "Year-to-date figures are published apart and are not a full year.",
                    "أرقام منذ بداية العام منشورة منفصلة وليست سنة كاملة.",
                ),
            }
        )
    out["facts"] = facts

    # Missing evidence: the sector's related indicators that are not published for this area.
    have = _published_indicators(session, data_mode, area)
    related = [c for c in RELATED.get(section.value, ()) if c != indicator]
    names = _names(session, tuple(related))
    missing = [
        _t(
            f"{names[c]['en']} for {area_name['en']} is not published in OSRIP.",
            f"{names[c]['ar']} لـ{area_name['ar']} غير منشور في OSRIP.",
        )
        for c in related
        if c not in have and c in names
    ]
    if s["missing"]:
        missing.append(
            _t(
                "Some periods in the range have no published value.",
                "بعض فترات النطاق ليس لها قيمة منشورة.",
            )
        )
    out["missing_evidence"] = missing

    fill = {"indicator": ind_name, "area": area_name}

    def fmt(t: T) -> T:
        return {
            lang: t[lang].format(indicator=fill["indicator"][lang], area=fill["area"][lang])
            for lang in ("en", "ar")
        }

    templates = TEMPLATES.get(section.value, {})
    actions: list[dict[str, Any]] = []
    for code in chosen:
        tpl = templates.get(code)
        if tpl is None:
            continue
        reason = (
            getattr(tpl, direction)
            if direction
            else _t(
                "Only one value is published in the range, so no direction can be read; widen the range first.",
                "قيمة واحدة فقط منشورة في النطاق، فلا يمكن قراءة اتجاه؛ يُوسع النطاق أولاً.",
            )
        )
        actions.append(
            {
                "objective": {"code": code, "name": obj.NAMES[code]},
                "title": fmt(tpl.title),
                "rationale": fmt(reason),
                "facts": [f["id"] for f in facts if f["kind"] in ("latest", "change")],
                "prerequisites": [fmt(p) for p in tpl.prerequisites],
                "risks": [fmt(r) for r in tpl.risks],
                "missing_evidence": missing[:3],
                "evidence": "trend" if direction else "single_value",
            }
        )
    # Better-evidenced actions first, then the order the objectives were chosen in.
    actions.sort(key=lambda a: (a["evidence"] != "trend", chosen.index(a["objective"]["code"])))
    if missing:
        actions.append(
            {
                "objective": None,
                "title": _t(
                    "Close the evidence gaps before deciding", "سد فجوات الأدلة قبل القرار"
                ),
                "rationale": _t(
                    "The actions above rest on one series; the missing evidence below would test them.",
                    "تستند الإجراءات أعلاه إلى سلسلة واحدة؛ الأدلة المفقودة أدناه تختبرها.",
                ),
                "facts": [],
                "prerequisites": [_SAME],
                "risks": [],
                "missing_evidence": missing,
                "evidence": "gap",
            }
        )
    for i, a in enumerate(actions, start=1):
        a["rank"] = i
    out["actions"] = actions
    out["status"] = "ok"
    return out
