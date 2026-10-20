"""Plain-language explanations for every reason and caveat code (EN / AR).

One source of wording for the interface, CSV exports and frozen reports, so a
limitation reads the same wherever the value travels. Arabic text requires
review by a qualified Arabic speaker before release.
"""

from __future__ import annotations

from app.domain.results import Caveat, ReasonCode

# Codes used by the analysis layer when a calculation cannot be offered at all.
UNAVAILABLE_CODES = {
    "inequality_not_compared": (
        "One of the values is published as an inequality (for example more than 95 percent), "
        "so it is not treated as an exact number and no change is calculated.",
        "إحدى القيمتين منشورة كمتباينة (مثل أكثر من 95%)، لذا لا تُعامل كرقم دقيق ولا يُحسب تغير.",
    ),
    "derived_not_published": (
        "Calculated by OSRIP from the published exports and imports of the same source and "
        "period. It is not a published figure; the published balance is shown separately.",
        "حسبته OSRIP من الصادرات والواردات المنشورة للمصدر والفترة نفسيهما. ليس رقماً منشوراً؛ "
        "ويُعرض الميزان المنشور منفصلاً.",
    ),
    "no_comparable_period": (
        "No comparable observation: only one period of this kind is published for this series, "
        "so no change can be calculated.",
        "نُشرت فترة واحدة فقط لهذه السلسلة، لذا لا يمكن حساب التغير.",
    ),
    "no_subscriber_series": (
        "No subscriber count with the same coverage and period is published, so use per "
        "subscriber is not calculated. It is never derived from a total alone.",
        "لا يوجد عدد مشتركين منشور بالتغطية والفترة نفسيهما، لذا لا يُحسب الاستخدام لكل مشترك. "
        "لا يُشتق أبداً من الإجمالي وحده.",
    ),
    "leakage_not_inferred": (
        "Production minus consumption is not calculated as leakage. The difference can also come "
        "from billing coverage, unmetered use, timing or different service areas.",
        "لا يُحسب الفرق بين الإنتاج والاستهلاك على أنه تسرب. قد ينتج الفرق أيضاً عن تغطية الفوترة أو "
        "الاستخدام غير المقاس أو التوقيت أو اختلاف مناطق الخدمة.",
    ),
    "no_source_breakdown": (
        "No breakdown of production by water source is published, so source composition is not "
        "shown and is not estimated.",
        "لا يوجد توزيع منشور للإنتاج حسب مصدر المياه، لذا لا يُعرض تكوين المصادر ولا يُقدَّر.",
    ),
    "component_not_published": (
        "A required component is not published for this commodity and period.",
        "أحد المكونات المطلوبة غير منشور لهذه السلعة والفترة.",
    ),
    "conflicting_sources": (
        "More than one published source reports this component. The calculation is withheld rather "
        "than choosing one silently; select a single dataset version.",
        "يُبلّغ أكثر من مصدر منشور عن هذا المكوّن. تُحجب العملية الحسابية بدلاً من اختيار أحدها بصمت؛ "
        "اختر إصداراً واحداً لمجموعة البيانات.",
    ),
    "generation_not_consumption": (
        "Generation is not divided by subscribers: generation is not consumption.",
        "لا يُقسم التوليد على المشتركين: التوليد ليس استهلاكاً.",
    ),
    "latest_pair_only": (
        "Change between the latest two periods in the selected years. Narrow the years to see an "
        "earlier change.",
        "التغير بين آخر فترتين ضمن السنوات المختارة. ضيّق نطاق السنوات لعرض تغير سابق.",
    ),
}

REASONS: dict[ReasonCode, tuple[str, str]] = {
    ReasonCode.INPUT_MISSING: (
        "An input value is missing in the source. The result stays missing; it is never treated as zero.",
        "إحدى القيم المدخلة مفقودة في المصدر. تبقى النتيجة مفقودة ولا تُعامل صفراً أبداً.",
    ),
    ReasonCode.PREVIOUS_VALUE_ZERO: (
        "The previous value is zero, so a percentage change is undefined.",
        "القيمة السابقة صفر، لذا فإن نسبة التغير غير معرّفة.",
    ),
    ReasonCode.DIMENSION_MISMATCH: (
        "The inputs measure different things (for example energy and power), so they cannot be combined.",
        "المدخلات تقيس أشياء مختلفة (مثل الطاقة والقدرة)، لذا لا يمكن جمعها.",
    ),
    ReasonCode.UNIT_MISMATCH: (
        "The inputs use different units and no registered conversion exists.",
        "المدخلات بوحدات مختلفة ولا يوجد معامل تحويل مسجل.",
    ),
    ReasonCode.PERIOD_NOT_COMPARABLE: (
        "The periods are not comparable (different length, completeness or overlap).",
        "الفترات غير قابلة للمقارنة (اختلاف الطول أو الاكتمال أو التداخل).",
    ),
    ReasonCode.COVERAGE_NOT_COMPARABLE: (
        "The inputs cover different geographies, so they are not combined.",
        "المدخلات تغطي مناطق جغرافية مختلفة، لذا لا تُجمع.",
    ),
    ReasonCode.NON_POSITIVE_DENOMINATOR: (
        "The denominator is zero or negative, so the ratio is not calculated.",
        "المقام صفر أو سالب، لذا لا تُحسب النسبة.",
    ),
    ReasonCode.ZERO_OR_MISSING_QUANTITY: (
        "The quantity is zero or missing, so a unit value cannot be calculated.",
        "الكمية صفر أو مفقودة، لذا لا يمكن حساب قيمة الوحدة.",
    ),
    ReasonCode.CURRENCY_MISMATCH: (
        "The values are in different currencies.",
        "القيم بعملات مختلفة.",
    ),
    ReasonCode.NO_PARTNER_RECORDS: (
        "No partner-level quantities are published for this flow.",
        "لا توجد كميات منشورة على مستوى الشركاء لهذا الاتجاه.",
    ),
    ReasonCode.COMMODITY_MISMATCH: (
        "The inputs refer to different commodities.",
        "المدخلات تخص سلعاً مختلفة.",
    ),
    ReasonCode.STOCK_CHANGE_MISSING: (
        "A known stock change was requested but none is published.",
        "طُلب تغير معروف في المخزون ولكن لا يوجد تغير منشور.",
    ),
    ReasonCode.PARTNER_SUM_EXCEEDS_TOTAL: (
        "Partner quantities add up to more than the stated total, so shares are not calculated.",
        "مجموع كميات الشركاء أكبر من الإجمالي المعلن، لذا لا تُحسب الحصص.",
    ),
    ReasonCode.NON_POSITIVE_START: (
        "A growth rate needs a positive first value and a non-negative last value.",
        "يتطلب معدل النمو قيمة أولى موجبة وقيمة أخيرة غير سالبة.",
    ),
    ReasonCode.PERIODS_NOT_IN_ORDER: (
        "The later period must come after the earlier one, at least one year apart.",
        "يجب أن تأتي الفترة اللاحقة بعد السابقة بفارق سنة واحدة على الأقل.",
    ),
    ReasonCode.COMPONENT_EXCEEDS_TOTAL: (
        "The component is larger than the published total, so a share is not calculated.",
        "المكوّن أكبر من الإجمالي المنشور، لذا لا تُحسب الحصة.",
    ),
    ReasonCode.NOT_A_RATIO: (
        "A self-sufficiency gap needs a ratio published in percent.",
        "تتطلب فجوة الاكتفاء الذاتي نسبة منشورة بالنسبة المئوية.",
    ),
    ReasonCode.NEGATIVE_RATIO: (
        "A self-sufficiency ratio cannot be negative, so no gap is calculated.",
        "لا يمكن أن تكون نسبة الاكتفاء الذاتي سالبة، لذا لا تُحسب فجوة.",
    ),
}

CAVEATS: dict[Caveat, tuple[str, str]] = {
    Caveat.STOCK_CHANGE_ASSUMED_ZERO: (
        "Assumption: stock change is zero. This is a declared assumption, not an observation.",
        "افتراض: التغير في المخزون صفر. هذا افتراض معلن وليس مشاهدة.",
    ),
    Caveat.STOCK_CHANGE_UNKNOWN_NOT_ADJUSTED: (
        "Stock change is unknown; this apparent balance is not adjusted for stocks.",
        "التغير في المخزون غير معروف؛ هذا التوازن الظاهري غير معدّل للمخزون.",
    ),
    Caveat.EXCEEDS_100_PERCENT_NOT_CAPPED: (
        "The share exceeds 100% and is shown as calculated, not capped.",
        "تتجاوز الحصة 100% وتُعرض كما حُسبت دون تقييد.",
    ),
    Caveat.NOT_COMPLETE_FOOD_SECURITY_MEASURE: (
        "Apparent availability is not a complete food-security assessment: it says nothing about "
        "household access, prices, nutrition or distribution.",
        "التوافر الظاهري ليس تقييماً كاملاً للأمن الغذائي: لا يقول شيئاً عن وصول الأسر أو الأسعار "
        "أو التغذية أو التوزيع.",
    ),
    Caveat.DOES_NOT_COMPLEMENT_PRODUCTION_RATIO: (
        "The import and production contributions do not add up to 100%: both divide by apparent "
        "availability, which subtracts exports and stock change, so the two numerators overlap "
        "what leaves the country.",
        "مساهمتا الواردات والإنتاج لا يبلغ مجموعهما 100%: كلتاهما مقسومة على التوافر الظاهري الذي "
        "تُطرح منه الصادرات والتغير في المخزون.",
    ),
    Caveat.PARTIAL_PARTNER_COVERAGE: (
        "Listed partners do not cover the stated total; shares use the stated total as denominator.",
        "الشركاء المدرجون لا يغطون الإجمالي المعلن؛ تُحسب الحصص من الإجمالي المعلن.",
    ),
    Caveat.NOT_RETAIL_PRICE: (
        "A mean unit value is trade value divided by quantity. It is not a retail or consumer price.",
        "متوسط قيمة الوحدة هو قيمة التجارة مقسومة على الكمية. ليس سعر تجزئة ولا سعراً للمستهلك.",
    ),
    Caveat.NOT_PROFIT_OR_LOSS: (
        "A trade balance is exports minus imports by value. It is not a profit or loss.",
        "الميزان التجاري هو الصادرات ناقص الواردات بالقيمة. ليس ربحاً ولا خسارة.",
    ),
    Caveat.NOMINAL_VALUE: (
        "Values are nominal (not adjusted for inflation).",
        "القيم اسمية (غير معدّلة للتضخم).",
    ),
    Caveat.NOT_EFFICIENCY_MEASURE: (
        "Use per subscriber is not an efficiency or conservation measure.",
        "الاستخدام لكل مشترك ليس مقياساً للكفاءة أو الترشيد.",
    ),
    Caveat.CONCENTRATION_NOT_DISRUPTION_PROBABILITY: (
        "Supplier concentration is not a probability of supply disruption.",
        "تركّز الموردين ليس احتمالاً لانقطاع الإمدادات.",
    ),
}


def explain(code: str) -> dict[str, str]:
    """Bilingual text for any reason, caveat or unavailability code."""
    for table in (REASONS, CAVEATS):
        for key, (en, ar) in table.items():
            if key.value == code:
                return {"code": code, "en": en, "ar": ar}
    en, ar = UNAVAILABLE_CODES.get(code, (code, code))
    return {"code": code, "en": en, "ar": ar}
