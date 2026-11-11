"""Sources on request. Pure: no I/O.

Answers do not list their sources; the evidence stays stored with each reply. When the person
asks for the sources ("Show sources", "Where did you get this?", "اعرض المصادر"), the reply
lists the sources of the previous answer from that stored evidence: no model is called, nothing
is charged, and nothing is looked up again.

Only a message that is itself a request for sources counts: "What are the sources of water in
Oman?" is a question about water and goes to the assistant as usual.
"""

from __future__ import annotations

import re
from typing import Any

# Arabic letter variants and marks that do not change the word.
_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": None})
_MARKS = re.compile(r"[ً-ْٰ]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

_EN = [
    r"(please )?(can you |could you |would you )?(show|give|list|share|provide|display|send|tell)( me| us)?"
    r"( the| your| all the| all| all your)? (sources?|references?|citations?|bibliography)"
    r"( please)?( for| behind| of)?( this| that| it| these| your| the)?( previous| last)?( answer| reply| information| data| figures| numbers)?( please)?",
    r"(what|which) (are|were) (the|your) (sources?|references?)( for| behind)?( this| that| it| the answer| your answer)?",
    r"where did you (get|find) (this|that|it|these|the information|this information|that information"
    r"|the data|this data|these figures|these numbers|the numbers)( from)?",
    r"where (does|did) (this|that|it|the information|this information|the data) come from",
    r"(your |the )?(sources?|references?|citations?)( please)?",
    r"cite (your )?sources",
]
_AR = [
    r"(من فضلك )?(اعرض|اظهر|عرض|اعطني|اعطيني|هات|ارني|اذكر|وضح)( لي)? (ال)?(مصادر|مراجع)(ك)?( من فضلك)?",
    r"(ما|ما هي|ماهي|وش) (ال)?(مصادر|مراجع)(ك)?",
    # Written as folded (ى as ي, ة as ه, أ as ا): "على" is matched as "علي".
    r"من اين (حصلت|جبت|اتيت|جئت|اخذت)( علي| ب)?( هذه| هذا| ذلك| تلك)?( ال)?(معلومات|معلومه|بيانات|ارقام|اجابه)?",
    r"(ال)?(مصادر|مراجع)( من فضلك)?",
]
_REQUEST = re.compile(r"^(?:" + "|".join(_EN + _AR) + r")$")


def _normalise(text: str) -> str:
    folded = _MARKS.sub("", text.translate(_ARABIC_FOLD)).lower()
    return " ".join(_PUNCT.sub(" ", folded).split())


def is_request(question: str) -> bool:
    """True when the whole message asks for the sources of what was said."""
    return len(question) <= 120 and bool(_REQUEST.match(_normalise(question)))


# Evidence without a ``source`` block that still names a source (a web page, a documented note,
# an OSRIP study, saved research); searches, calculations, methods and scenarios do not.
_SOURCE_KINDS = {"web", "page", "note", "study", "saved_research"}


def _text(value: Any, language: str) -> str:
    if isinstance(value, dict):
        return str(value.get(language) or value.get("en") or value.get("ar") or "")
    return str(value or "")


def entries(evidence: list[dict[str, Any]], language: str) -> list[dict[str, str]]:
    """One entry per distinct source (by address, else title): title, publisher, period, address,
    date. Observations from the same table are one source."""
    out: dict[str, dict[str, str]] = {}
    for item in evidence:
        source = item.get("source") if isinstance(item.get("source"), dict) else None
        if source:
            entry = {
                "title": _text(source.get("title"), language),
                "publisher": _text(source.get("publisher"), language),
                "period": _text(source.get("reference_period"), language),
                "url": _text(source.get("url"), language),
                "date": _text(source.get("access_date"), language),
            }
        elif item.get("kind") in _SOURCE_KINDS and (item.get("title") or item.get("url")):
            entry = {
                "title": _text(item.get("title"), language),
                "publisher": _text(item.get("publisher"), language),
                "period": "",
                "url": _text(item.get("url"), language),
                "date": _text(item.get("published") or item.get("retrieved_at"), language)[:10],
            }
        else:
            continue
        key = entry["url"] or entry["title"]
        if key and key not in out:
            out[key] = entry
    return list(out.values())


def reply_text(items: list[dict[str, str]], language: str) -> str:
    """The sources as a numbered list, in the person's language."""
    arabic = language == "ar"
    if not items:
        return (
            "لا توجد مصادر لعرضها بعد: لم تستند الإجابة السابقة إلى مصدر منشور، أو لم تُطرح أي إجابة."
            if arabic
            else "There are no sources to show: the previous answer did not rest on a published"
            " source, or there is no previous answer yet."
        )
    lines = ["مصادر الإجابة السابقة:" if arabic else "Sources of the previous answer:", ""]
    for n, e in enumerate(items, 1):
        details = [d for d in (e["publisher"], e["period"]) if d and d != e["title"]]
        line = f"{n}. {e['title'] or e['url']}"
        if details:
            line += " — " + ("، " if arabic else ", ").join(details)
        if e["url"]:
            line += f" <{e['url']}>"
        if e["date"]:
            line += f" ({'تاريخ الاطلاع' if arabic else 'accessed'} {e['date']})"
        lines.append(line)
    return "\n".join(lines)
