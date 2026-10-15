"""The labelled non-AI fallback used when no answer provider is configured.

It generates no prose about the data. It recognises which domains the question names
(electricity, water, food security, trade; English or Arabic words) and returns the
latest published national records for a few headline indicators, as evidence with
their period, unit, status and source. The reply says plainly that it is not an AI
answer. It never counts against the guest allowance.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.db.session import session_factory
from app.domain.enums import DataMode
from app.services.assistant.tools import Ledger, Tools

DOMAINS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "electricity": (
        ("electric", "power", "generation", "gwh", "kwh", "energy", "كهرب", "توليد", "طاقة"),
        ("ELEC_GROSS_GENERATION", "ELEC_CONSUMPTION", "ELEC_GENERATION"),
    ),
    "water": (
        ("water", "desal", "مياه", "الماء", "تحلية"),
        ("WATER_PRODUCTION", "WATER_CONSUMPTION"),
    ),
    "food_security": (
        (
            "food",
            "fish",
            "crop",
            "agri",
            "farm",
            "self-suff",
            "غذا",
            "سمك",
            "أسماك",
            "زراع",
            "اكتفاء",
        ),
        ("FISH_CAPTURE_LANDINGS", "AGRI_CROP_PRODUCTION", "FOOD_PRODUCTION"),
    ),
    "trade": (
        ("trade", "export", "import", "port", "تجار", "صادر", "وارد", "ميناء"),
        ("TRADE_MERCH_EXPORTS", "TRADE_MERCH_IMPORTS", "TRADE_VALUE"),
    ),
}
PER_DOMAIN = 2  # indicators shown per matched domain

TEXT = {
    "found": {
        "en": "No AI answer service is configured on this server, so this reply was not "
        "written by AI. It lists the latest published national records for the topics "
        "named in your question; open each record for its period, unit, status and source.",
        "ar": "لا توجد خدمة إجابات بالذكاء الاصطناعي مُعدّة على هذا الخادم، لذلك لم يكتب "
        "الذكاء الاصطناعي هذا الرد. يعرض الرد أحدث السجلات الوطنية المنشورة للموضوعات "
        "المذكورة في سؤالك؛ افتح كل سجل لمعرفة فترته ووحدته وحالته ومصدره.",
    },
    "no_records": {
        "en": "No AI answer service is configured on this server, so this reply was not "
        "written by AI. No published national records were found for the topics named in "
        "your question in this data mode.",
        "ar": "لا توجد خدمة إجابات بالذكاء الاصطناعي مُعدّة على هذا الخادم، لذلك لم يكتب "
        "الذكاء الاصطناعي هذا الرد. لم يُعثر على سجلات وطنية منشورة للموضوعات المذكورة في "
        "سؤالك في وضع البيانات هذا.",
    },
    "no_topic": {
        "en": "No AI answer service is configured on this server, so questions cannot be "
        "answered in writing. Name a topic (electricity, water, food security or trade) to "
        "list its latest published records, or open that section of the site.",
        "ar": "لا توجد خدمة إجابات بالذكاء الاصطناعي مُعدّة على هذا الخادم، لذلك لا يمكن "
        "الإجابة عن الأسئلة كتابةً. اذكر موضوعاً (الكهرباء أو المياه أو الأمن الغذائي أو "
        "التجارة) لعرض أحدث سجلاته المنشورة، أو افتح ذلك القسم من الموقع.",
    },
}


def matched_domains(question: str) -> list[str]:
    q = question.lower()
    return [
        d for d, (words, _) in DOMAINS.items() if any(re.search(re.escape(w), q) for w in words)
    ]


def reply(question: str, language: str, data_mode: DataMode) -> dict[str, Any]:
    """Evidence for the named domains, read in a read-only transaction."""
    domains = matched_domains(question)
    ledger = Ledger(data_mode)
    if domains:
        with session_factory()() as reader:
            reader.begin()
            reader.execute(text("SET TRANSACTION READ ONLY"))
            tools = Tools(reader, ledger)
            try:
                for domain in domains:
                    shown = 0
                    for indicator in DOMAINS[domain][1]:
                        if shown >= PER_DOMAIN:
                            break
                        if tools.latest_period(indicator, "OM").get("status") == "ok":
                            shown += 1
            finally:
                reader.rollback()
    evidence = [i for i in ledger.items if i.get("kind") == "observation"]
    key = "found" if evidence else "no_records" if domains else "no_topic"
    return {
        "status": "lookup",
        "content": TEXT[key][language],
        "evidence": evidence,
        "citations": [i["id"] for i in evidence],
        "domains": domains,
    }
