"""The data-based report given when the AI answer service fails (no AI interpretation).

When the answering model cannot be reached or refuses the request (an invalid key, an
unknown model, a timeout, a limit), the question still gets what OSRIP can say without a
model: the published records for the topics it names, the platform's own calculations of
the latest change, and, for a shortage or surplus question, the deterministic balance
analysis. Every sentence is built here from those results, carries its evidence ids and is
checked by the same evidence validation as a model's answer. Nothing is interpreted: no
causes, no recommendations beyond the balance analysis's documented rules.

When the question names no topic, or no published record matches, the report says what is
missing and what to do next instead of giving figures.

The reply has status ``data_report``: labelled "data-based report without AI
interpretation", never charged to a guest's allowance, and retryable.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from app.db.session import session_factory
from app.domain import calculations as calc
from app.domain.enums import DataMode
from app.services.assistant import grounding, lookup
from app.services.assistant.progress import Tracker
from app.services.assistant.study_events import period_label
from app.services.assistant.tools import Ledger, Tools, _observation_item
from app.services.observations import SeriesOut

PER_DOMAIN = 2  # indicators reported per topic named in the question
ROWS_PER_SERIES = 24  # observations shown per series (the table and chart)

# Headline indicators per topic and data mode, in order of preference. Chosen so that the
# report does not mix definitions (consumption is never shown as generation).
HEADLINES: dict[str, dict[DataMode, tuple[str, ...]]] = {
    "electricity": {
        DataMode.VERIFIED_SOURCE: (
            "ELEC_CONSUMPTION",
            "ELEC_GROSS_GENERATION",
            "ELEC_INSTALLED_CAPACITY",
        ),
        DataMode.SYNTHETIC: ("ELEC_GENERATION", "ELEC_CONSUMPTION"),
    },
    "water": {
        DataMode.VERIFIED_SOURCE: ("WATER_PRODUCTION", "WATER_CONSUMPTION", "WATER_DISTRIBUTION"),
        DataMode.SYNTHETIC: ("WATER_CONSUMPTION", "WATER_PRODUCTION"),
    },
    "food_security": {
        DataMode.VERIFIED_SOURCE: ("AGRI_CROP_PRODUCTION", "FISH_CAPTURE_LANDINGS"),
        DataMode.SYNTHETIC: ("FOOD_PRODUCTION",),
    },
    "trade": {
        DataMode.VERIFIED_SOURCE: ("TRADE_MERCH_EXPORTS", "TRADE_MERCH_IMPORTS"),
        DataMode.SYNTHETIC: ("TRADE_VALUE",),
    },
}

# Words that point at one indicator; it is reported first when its topic is named.
FOCUS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("generation", "generated", "توليد", "المولد"), ("ELEC_GROSS_GENERATION", "ELEC_GENERATION")),
    (("capacity", "القدرة", "قدرة", "السعة"), ("ELEC_INSTALLED_CAPACITY",)),
    (
        ("consumption", "consumed", "demand", "استهلاك", "الطلب"),
        ("ELEC_CONSUMPTION", "WATER_CONSUMPTION"),
    ),
    (("distribut", "توزيع"), ("ELEC_DISTRIBUTION", "WATER_DISTRIBUTION")),
    (("production", "produced", "إنتاج", "انتاج"), ("WATER_PRODUCTION", "AGRI_CROP_PRODUCTION")),
    (("fish", "landings", "سمك", "أسماك", "اسماك"), ("FISH_CAPTURE_LANDINGS",)),
    (("export", "صادر", "تصدير"), ("TRADE_MERCH_EXPORTS",)),
    (("import", "وارد", "استيراد"), ("TRADE_MERCH_IMPORTS",)),
)

BALANCE_WORDS = (
    "shortage", "surplus", "deficit", "gap", "balance", "supply and demand", "self-suff",
    "عجز", "فائض", "نقص", "فجوة", "توازن", "العرض والطلب", "اكتفاء",
)  # fmt: skip

CATEGORY_TEXT: dict[str, dict[str, str]] = {
    "authentication": {
        "en": "the service rejected the server's credentials",
        "ar": "رفضت الخدمة بيانات اعتماد الخادم",
    },
    "model_unavailable": {
        "en": "the configured model is not available",
        "ar": "النموذج المُعدّ غير متاح",
    },
    "rate_limited": {"en": "the service is limiting requests", "ar": "الخدمة تحدّ من الطلبات"},
    "timeout": {"en": "the service did not reply in time", "ar": "لم تردّ الخدمة في الوقت المحدد"},
    "network": {"en": "the service could not be reached", "ar": "تعذّر الوصول إلى الخدمة"},
    "server_error": {"en": "the service reported an error", "ar": "أبلغت الخدمة عن خطأ"},
    "invalid_response": {
        "en": "the service returned an unusable reply",
        "ar": "أعادت الخدمة رداً غير صالح للاستخدام",
    },
    "budget": {
        "en": "today's request limit or budget is used up",
        "ar": "نفد حدّ الطلبات أو الميزانية لليوم",
    },
    "insufficient_balance": {
        "en": "the AI service account has no balance left",
        "ar": "نفد رصيد حساب خدمة الذكاء الاصطناعي",
    },
    "not_configured": {
        "en": "no answer service is configured",
        "ar": "لا توجد خدمة إجابات مُعدّة",
    },
    "other": {"en": "the service failed", "ar": "تعطلت الخدمة"},
}

DOMAIN_NAMES = {
    "electricity": {"en": "electricity", "ar": "الكهرباء"},
    "water": {"en": "water", "ar": "المياه"},
    "food_security": {"en": "food security", "ar": "الأمن الغذائي"},
    "trade": {"en": "trade", "ar": "التجارة"},
}

LABEL = {
    "en": "Data-based report without AI interpretation",
    "ar": "تقرير قائم على البيانات دون تفسير بالذكاء الاصطناعي",
}


def _domain_of(indicator: str) -> str | None:
    if indicator.startswith("ELEC_"):
        return "electricity"
    if indicator.startswith("WATER_"):
        return "water"
    if indicator.startswith(("AGRI_", "FISH_", "FOOD_", "SELF_SUFFICIENCY_", "LIVESTOCK_")):
        return "food_security"
    if indicator.startswith("TRADE_"):
        return "trade"
    return None


def wants_balance(question: str) -> bool:
    q = question.lower()
    return any(w in q for w in BALANCE_WORDS)


def candidates(question: str, domains: list[str], data_mode: DataMode) -> dict[str, list[str]]:
    """Indicators to try per topic: those the question points at first, then the headlines."""
    q = question.lower()
    out: dict[str, list[str]] = {}
    for domain in domains:
        focused = [
            code
            for words, codes in FOCUS
            if any(w in q for w in words)
            for code in codes
            if _domain_of(code) == domain
        ]
        defaults = HEADLINES[domain].get(data_mode, ())
        out[domain] = list(dict.fromkeys([*focused, *defaults]))
    return out


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def fmt(value: Any, places: int | None = None) -> str:
    """A number with thousands separators, as published (or rounded to ``places``)."""
    d = _decimal(value)
    if d is None:
        return str(value)
    if places is not None:
        d = d.quantize(Decimal(1).scaleb(-places))
    text_ = f"{abs(d):,f}"
    if "." in text_:
        text_ = text_.rstrip("0").rstrip(".")
    return text_


def _pick_series(series: list[SeriesOut]) -> list[SeriesOut]:
    """The national total series (no partner, no product group), dated periods only;
    annual first, at most two (for example annual and monthly)."""
    totals = [
        s
        for s in series
        if s.meta.get("partner") is None
        and s.meta.get("commodity") is None
        and s.meta.get("period_kind", s.meta.get("frequency")) != "statement"
        and any(o["value"] is not None for o in s.observations)
    ]
    order = {"annual": 0, "year_to_date": 1, "quarterly": 2, "monthly": 3}
    totals.sort(key=lambda s: order.get(str(s.meta.get("period_kind", s.meta["frequency"])), 9))
    return totals[:2]


class _Builder:
    def __init__(self, tools: Tools, ledger: Ledger, language: str, tracker: Tracker) -> None:
        self.tools, self.ledger, self.lang, self.tracker = tools, ledger, language, tracker
        self.lines: list[str] = []
        self.cited: list[str] = []
        self.studies: list[dict[str, Any]] = []
        self.missing: list[dict[str, str]] = []
        self.published: list[str] = []

    def say(self, en: str, ar: str, ids: list[str]) -> None:
        markers = "".join(f"[{i}]" for i in ids)
        sentence = (ar if self.lang == "ar" else en).rstrip(".")
        self.lines.append(f"{sentence} {markers}." if markers else f"{sentence}.")
        self.cited.extend(i for i in ids if i not in self.cited)

    def series(self, s: SeriesOut) -> bool:
        kind = str(s.meta.get("period_kind", s.meta["frequency"]))
        rows = s.observations[-ROWS_PER_SERIES:]
        items = [self.ledger.add(_observation_item(s, o)) for o in rows]
        if self.tracker.stream is not None:
            keys = ("id", "indicator", "area", "period_kind", "period_start", "period_end",
                    "period_complete", "value", "value_operator", "unit", "commodity",
                    "partner", "flow", "revision_status", "dataset_version")  # fmt: skip
            self.tracker.stream.on_tool(
                "get_observations",
                {"status": "ok", "observations": [{k: i[k] for k in keys} for i in items]},
                self.ledger.by_id(),
                self.tracker,
            )
        self.published += [str(i["published_at"]) for i in items if i.get("published_at")]
        name = s.meta["indicator"]
        unit = s.meta["unit"]
        area = s.meta["area"]
        with_value = [(o, i) for o, i in zip(rows, items, strict=True) if o["value"] is not None]
        if not with_value:
            return False
        last_o, last_i = with_value[-1]
        period = period_label(kind, last_o["period_start"], last_o["period_end"])
        op = {">": ("more than ", "أكثر من "), "<": ("less than ", "أقل من ")}.get(
            str(last_o.get("value_operator") or ""), ("", "")
        )
        partial = (
            (" (year to date, not a full year)", " (منذ بداية العام حتى تاريخه، وليست سنة كاملة)")
            if kind == "year_to_date"
            else ("", "")
        )
        # Two series of one indicator come from different publications: name the publisher
        # (only when it has no digits of its own, which the evidence check would not find).
        source = s.meta.get("source") or {}
        publisher = str(source.get("publisher") or "")
        code = str(source.get("source_code") or "")
        by = ("", "")
        if publisher and not re.search(r"\d", publisher):
            ref = f", source {code}" if re.fullmatch(r"[A-Z]+\d+", code) else ""
            ref_ar = f"، المصدر {code}" if ref else ""
            by = (f" (published by {publisher}{ref})", f" (نشره: {publisher}{ref_ar})")
        self.say(
            f"{name['name_en']}, {area['name_en']}, {period}{partial[0]}: "
            f"{op[0]}{fmt(last_o['value'])} {unit['label_en']}{by[0]}",
            f"{name['name_ar']}، {area['name_ar']}، {period}{partial[1]}: "
            f"{op[1]}{fmt(last_o['value'])} {unit['label_ar']}{by[1]}",
            [last_i["id"]],
        )
        complete = [(o, i) for o, i in with_value if o["period_complete"]]
        if len(complete) < 2 or kind not in ("annual", "monthly", "quarterly"):
            return True
        (prev_o, prev_i), (cur_o, cur_i) = complete[-2], complete[-1]
        a, b = self.tools._measure(s, prev_o), self.tools._measure(s, cur_o)
        absolute = self.tools._calc_item(
            "absolute_change", [prev_i["id"], cur_i["id"]], calc.absolute_change(a, b), unit["code"]
        )
        percent = self.tools._calc_item(
            "percentage_change",
            [prev_i["id"], cur_i["id"]],
            calc.percentage_change(a, b),
            "percent",
        )
        p_prev = period_label(kind, prev_o["period_start"], prev_o["period_end"])
        p_cur = period_label(kind, cur_o["period_start"], cur_o["period_end"])
        change = _decimal(absolute["value"])
        if change is None:
            reason = absolute.get("reason") or {"en": "not comparable", "ar": "غير قابلة للمقارنة"}
            self.say(
                f"The change from {p_prev} to {p_cur} was not calculated: {reason['en']}",
                f"لم يُحسب التغير من {p_prev} إلى {p_cur}: {reason['ar']}",
                [absolute["id"]],
            )
            return True
        direction = (
            ("increased by", "ارتفع بمقدار")
            if change > 0
            else ("decreased by", "انخفض بمقدار")
            if change < 0
            else ("was unchanged", "لم يتغير")
        )
        amount_en = amount_ar = ""
        if change != 0:
            amount_en = f" {fmt(change)} {unit['label_en']}"
            amount_ar = f" {fmt(change)} {unit['label_ar']}"
        pct = _decimal(percent["value"])
        if pct is not None and change != 0:
            amount_en += f" ({fmt(pct, 1)}%)"
            amount_ar += f" ({fmt(pct, 1)}٪)"
        elif pct is None and percent.get("reason"):
            amount_en += f"; the percentage change is not given: {percent['reason']['en']}"
            amount_ar += f"؛ لا تُعطى نسبة التغير: {percent['reason']['ar']}"
        ids = [absolute["id"]] + ([percent["id"]] if percent["value"] is not None else [])
        self.say(
            f"From {p_prev} to {p_cur} it {direction[0]}{amount_en} (OSRIP calculation)",
            f"من {p_prev} إلى {p_cur} {direction[1]}{amount_ar} (حساب OSRIP)",
            ids,
        )
        return True

    def balance(self, sector: str) -> None:
        output = self.tools.balance_analysis(sector)
        if self.tracker.stream is not None:
            self.tracker.stream.on_tool(
                "balance_analysis", output, self.ledger.by_id(), self.tracker
            )
        item = self.ledger.by_id().get(str(output.get("evidence_id")))
        if item is None:
            return
        self.studies.append(item)
        en, ar = output.get("summary") or [], output.get("summary_ar") or []
        for s_en, s_ar in list(zip(en, ar, strict=False))[:3]:
            self.say(s_en, s_ar, [item["id"]])
        for gap in (item["study"].get("data_gaps") or [])[:3]:
            missing = gap.get("missing") or {}
            if missing.get("en"):
                self.missing.append({"en": missing["en"], "ar": missing.get("ar") or missing["en"]})


def _next_steps(category: str, has_topic: bool, has_data: bool) -> list[dict[str, str]]:
    steps = []
    if not has_topic:
        steps.append({
            "en": "Name a topic (electricity, water, food security or trade) and an indicator.",
            "ar": "اذكر موضوعاً (الكهرباء أو المياه أو الأمن الغذائي أو التجارة) ومؤشراً.",
        })  # fmt: skip
    elif not has_data:
        steps.append({
            "en": "Open the sector page to see which indicators and periods are published.",
            "ar": "افتح صفحة القطاع لمعرفة المؤشرات والفترات المنشورة.",
        })  # fmt: skip
    steps.append({
        "en": "Ask again later for an AI-written answer.",
        "ar": "اسأل مرة أخرى لاحقاً للحصول على إجابة مكتوبة بالذكاء الاصطناعي.",
    })  # fmt: skip
    if category in (
        "authentication", "model_unavailable", "not_configured", "budget", "insufficient_balance",
    ):  # fmt: skip
        steps.append({
            "en": "An administrator should check the answer service in Settings › Services.",
            "ar": "على المسؤول مراجعة خدمة الإجابات في الإعدادات › الخدمات.",
        })  # fmt: skip
    return steps


def build(
    question: str,
    language: str,
    data_mode: DataMode,
    *,
    category: str,
    incident: str,
    ledger: Ledger | None = None,
    tracker: Tracker | None = None,
) -> dict[str, Any]:
    """The report's text, cited evidence and structured notice. ``ledger`` continues the
    failed run's evidence numbering (its items stay uncited); ``tracker`` streams the tables."""
    tracker = tracker or Tracker(None)
    if ledger is None:
        ledger = Ledger(data_mode, language=language)
        if tracker.stream is not None:
            ledger.on_add = tracker.stream.on_evidence
    domains = lookup.matched_domains(question)
    shown_any = False
    with session_factory()() as reader:
        reader.begin()
        reader.execute(text("SET TRANSACTION READ ONLY"))
        tools = Tools(reader, ledger)
        b = _Builder(tools, ledger, language, tracker)
        try:
            for domain, codes in candidates(question, domains, data_mode).items():
                tracker.stage("published_data")
                shown = 0
                for code in codes:
                    if shown >= PER_DOMAIN:
                        break
                    picked = _pick_series(tools._series(code, "OM", None, None, None))
                    if picked:
                        tracker.stage("calculating")
                    done = [b.series(s) for s in picked]
                    if any(done):
                        shown += 1
                        shown_any = True
                if shown == 0:
                    names = DOMAIN_NAMES[domain]
                    b.missing.append({
                        "en": f"Published national records for {names['en']} in this data mode",
                        "ar": f"سجلات وطنية منشورة لقطاع {names['ar']} في وضع البيانات هذا",
                    })  # fmt: skip
            if domains and wants_balance(question):
                for domain in domains:
                    b.balance(domain)
        finally:
            reader.rollback()
    if not domains:
        b.missing.append({
            "en": "The topic of the question (electricity, water, food security or trade)",
            "ar": "موضوع السؤال (الكهرباء أو المياه أو الأمن الغذائي أو التجارة)",
        })  # fmt: skip
    reason = CATEGORY_TEXT.get(category, CATEGORY_TEXT["other"])
    if b.cited:
        intro = {
            "en": f"The AI answer service is unavailable ({reason['en']}), so this is a "
            "data-based report without AI interpretation: published records and OSRIP's own "
            "calculations, with no AI-written explanation.",
            "ar": f"خدمة الإجابات بالذكاء الاصطناعي غير متاحة ({reason['ar']})، لذلك هذا تقرير "
            "قائم على البيانات دون تفسير بالذكاء الاصطناعي: سجلات منشورة وحسابات OSRIP نفسها، "
            "دون شرح مكتوب بالذكاء الاصطناعي.",
        }
    else:
        intro = {
            "en": f"The AI answer service is unavailable ({reason['en']}), and the published "
            "data do not answer this question, so no figures are given. The missing "
            "information and next steps are listed below.",
            "ar": f"خدمة الإجابات بالذكاء الاصطناعي غير متاحة ({reason['ar']})، والبيانات "
            "المنشورة لا تجيب عن هذا السؤال، لذلك لا تُعطى أرقام. المعلومات الناقصة والخطوات "
            "التالية مذكورة أدناه.",
        }
    content = "\n".join([intro[language], *b.lines])
    visible = [i for i in ledger.items if i.get("kind") != "grounded_context"]
    verdict = grounding.validate(content, b.cited, visible)
    if not verdict.ok:  # a defect here must never show an unsupported figure
        content, b.cited, b.studies = intro[language], [], []
    cited = set(b.cited)
    by_id = ledger.by_id()
    evidence = [i for i in ledger.items if i["id"] in cited]
    for item in list(evidence):
        for input_id in item.get("inputs", []):
            if input_id in by_id and by_id[input_id] not in evidence:
                evidence.append(by_id[input_id])
    last_update = _latest(b.published)
    notice = {
        "label": LABEL,
        "category": category,
        "reason": reason,
        "incident": incident,
        "sufficient": bool(b.cited),
        "data_last_updated": last_update,
        "web_search": "not_attempted",
        "missing": b.missing,
        "next_steps": _next_steps(category, bool(domains), shown_any),
        "domains": domains,
    }
    return {
        "content": content,
        "citations": b.cited,
        "evidence": evidence,
        "studies": [i for i in b.studies if i["id"] in cited],
        "notice": notice,
        "ledger": ledger,
    }


def _latest(stamps: list[str]) -> str | None:
    days: list[date] = []
    for stamp in stamps:
        try:
            days.append(datetime.fromisoformat(stamp).date())
        except ValueError:
            match = re.match(r"\d{4}-\d{2}-\d{2}", stamp)
            if match:
                days.append(date.fromisoformat(match.group(0)))
    return max(days).isoformat() if days else None
