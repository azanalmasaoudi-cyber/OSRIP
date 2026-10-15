"""Research library: saved research, downloadable research briefs and the source library.

* Saving an assistant reply stores a snapshot (text, mode, evidence, calculations,
  citations, validated structured parts), so a brief always matches what was saved.
* A brief lists every claim's source with its class, publication date and the period the
  figures cover, and states the platform's limitations. It is generated from the snapshot
  only: nothing is re-asked and nothing is added.
* The source library lists the curated reference pack, registered datasets with published
  data, and sources the web research found. Unreviewed web sources are shown only to
  people who review them.
"""

from __future__ import annotations

import html
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import not_found, unprocessable
from app.domain.enums import DataMode, DatasetVersionStatus, Permission
from app.models import (
    AssistantConversation,
    AssistantMessage,
    DatasetVersion,
    Observation,
    ReferencePack,
    ReferencePackSource,
    ResearchCandidate,
    SavedResearch,
    Source,
)
from app.services.principal import Principal

MAX_SAVED = 500
MODE_LABEL = {
    "ask": ("Ask", "سؤال"),
    "analyze": ("Analyze", "تحليل"),
    "research": ("Research", "بحث"),
    "compare": ("Compare", "مقارنة"),
    "scenario": ("Scenario", "سيناريو"),
}
CLASS_LABEL = {
    "observed": ("Observed (published)", "رصد منشور"),
    "calculated": ("Calculated by OSRIP", "محسوب بواسطة OSRIP"),
    "forecast": ("Model forecast", "توقع نموذج"),
    "hypothetical": ("Hypothetical scenario", "سيناريو افتراضي"),
    "official": ("Official source", "مصدر رسمي"),
    "research": ("Research paper", "ورقة بحثية"),
    "secondary": ("Secondary source", "مصدر ثانوي"),
    "reference": ("Reference", "مرجع"),
}
BASIS_LABEL = {
    "evidence": ("Evidence", "دليل"),
    "hypothesis": ("Hypothesis", "فرضية"),
    "assumption": ("Assumption", "افتراض"),
}
DRIVER_LABEL = {
    "weather": ("Weather", "الطقس"),
    "population": ("Population", "السكان"),
    "industrial_activity": ("Industrial activity", "النشاط الصناعي"),
    "desalination": ("Desalination", "تحلية المياه"),
    "renewable_energy": ("Renewable energy", "الطاقة المتجددة"),
    "irrigation": ("Irrigation", "الري"),
    "agricultural_productivity": ("Agricultural productivity", "الإنتاجية الزراعية"),
    "commodity_prices": ("Commodity prices", "أسعار السلع"),
    "logistics": ("Logistics", "الخدمات اللوجستية"),
    "trading_partners": ("Trading partners", "الشركاء التجاريون"),
}
LIMITATIONS = {
    "en": [
        "OSRIP is an academic prototype, not an official statistical service.",
        "Missing values are reported as missing, never as zero; national or governorate totals "
        "are never divided among areas.",
        "Web findings are not part of the platform's approved statistics until a data manager "
        "reviews and imports them.",
        "Drivers marked 'hypothesis' or 'assumption' are not established by the evidence. "
        "Recommendations are options for people to examine, not decisions, and no saving or "
        "improvement is claimed unless a cited source states it.",
        "Forecasts are model estimates; scenarios are arithmetic on stated assumptions.",
    ],
    "ar": [
        "منصة OSRIP نموذج أكاديمي أولي وليست خدمة إحصائية رسمية.",
        "تُذكر القيم المفقودة على أنها مفقودة ولا تُعامل صفراً، ولا تُقسَّم المجاميع الوطنية أو "
        "مجاميع المحافظات على المناطق.",
        "نتائج البحث على الإنترنت ليست جزءاً من الإحصاءات المعتمدة في المنصة حتى يراجعها مدير "
        "البيانات ويستوردها.",
        "العوامل الموسومة بـ«فرضية» أو «افتراض» لا تثبتها الأدلة. والتوصيات خيارات للدراسة وليست "
        "قرارات، ولا يُدّعى أي توفير أو تحسن ما لم يذكره مصدر مستشهد به.",
        "التوقعات تقديرات نموذج، والسيناريوهات حساب على افتراضات معلنة.",
    ],
}


BRIEF_CSS = (
    "body{font-family:system-ui,'Segoe UI',Tahoma,sans-serif;max-width:60rem;"
    "margin:2rem auto;padding:0 1rem;line-height:1.55;color:#1d2a33;background:#fff}"
    "table{border-collapse:collapse;width:100%;font-size:.85rem}"
    "th,td{border:1px solid #c9d2d8;padding:.35rem .5rem;text-align:start;vertical-align:top}"
    "dt{font-weight:600}dd{margin:0 0 .4rem}a{color:#0b5d6b;word-break:break-all}"
    "@media print{a{color:inherit}}"
)


def _now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------ saved research


def _saved(session: Session, principal: Principal, saved_id: uuid.UUID) -> SavedResearch:
    row = session.get(SavedResearch, saved_id)
    if row is None or row.user_id != principal.user_id:
        raise not_found("saved research")
    return row


def saved_out(row: SavedResearch, *, full: bool = False) -> dict[str, Any]:
    out = {
        "id": str(row.id),
        "title": row.title,
        "note": row.note,
        "question": row.question,
        "mode": row.mode,
        "language": row.language,
        "data_mode": row.data_mode.value,
        "message_id": row.message_id,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "source_count": len(row.snapshot.get("evidence", [])),
        "recommendation_count": len(
            (row.snapshot.get("structured") or {}).get("recommendations", [])
        ),
    }
    if full:
        out["snapshot"] = row.snapshot
    return out


def save(
    session: Session, principal: Principal, message_id: int, title: str | None, note: str | None
) -> dict[str, Any]:
    message = session.get(AssistantMessage, message_id)
    conv = session.get(AssistantConversation, message.conversation_id) if message else None
    if (
        message is None
        or conv is None
        or conv.user_id != principal.user_id
        or message.role != "assistant"
    ):
        raise not_found("assistant reply")
    if message.status not in ("answered", "no_evidence", "clarification", "lookup"):
        raise unprocessable("not_saveable", "Only completed replies can be saved.")
    existing = session.scalar(
        select(SavedResearch).where(
            SavedResearch.user_id == principal.user_id, SavedResearch.message_id == message_id
        )
    )
    if existing is not None:
        return saved_out(existing)
    count = (
        session.scalar(select(func.count()).where(SavedResearch.user_id == principal.user_id)) or 0
    )
    if count >= MAX_SAVED:
        raise unprocessable("library_full", f"The library holds at most {MAX_SAVED} items.")
    question = (
        session.scalar(
            select(AssistantMessage.content)
            .where(
                AssistantMessage.conversation_id == conv.id,
                AssistantMessage.role == "user",
                AssistantMessage.id < message.id,
            )
            .order_by(AssistantMessage.id.desc())
            .limit(1)
        )
        or ""
    )
    clean_title = (
        " ".join((title or question or "Saved research").split())[:200] or "Saved research"
    )
    row = SavedResearch(
        user_id=principal.user_id,
        message_id=message.id,
        title=clean_title,
        note=(note or "").strip()[:4000] or None,
        question=question,
        mode=message.mode,
        language=conv.language,
        data_mode=conv.data_mode,
        snapshot={
            "content": message.content,
            "status": message.status,
            "mode": message.mode,
            "evidence": message.evidence,
            "calculations": message.calculations,
            "citations": message.citations,
            "structured": message.structured or {},
            "model": message.model,
            "ai_generated": message.model is not None,
            "answered_at": message.created_at.isoformat(),
            "research_cutoff": _cutoff(session),
        },
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    return saved_out(row)


def _cutoff(session: Session) -> str | None:
    cutoff = session.scalar(select(func.max(ReferencePack.research_cutoff)))
    return cutoff.isoformat() if cutoff else None


def list_saved(session: Session, principal: Principal) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(SavedResearch)
        .where(SavedResearch.user_id == principal.user_id)
        .order_by(SavedResearch.created_at.desc())
    )
    return [saved_out(r) for r in rows]


def get_saved(session: Session, principal: Principal, saved_id: uuid.UUID) -> dict[str, Any]:
    return saved_out(_saved(session, principal, saved_id), full=True)


def update_saved(
    session: Session, principal: Principal, saved_id: uuid.UUID, title: str | None, note: str | None
) -> dict[str, Any]:
    row = _saved(session, principal, saved_id)
    if title is not None:
        cleaned = " ".join(title.split())[:200]
        if not cleaned:
            raise unprocessable("title_required", "Give the saved research a title.")
        row.title = cleaned
    if note is not None:
        row.note = note.strip()[:4000] or None
    row.updated_at = _now()
    session.flush()
    return saved_out(row)


def delete_saved(session: Session, principal: Principal, saved_id: uuid.UUID) -> None:
    session.delete(_saved(session, principal, saved_id))


# ------------------------------------------------------------------ briefs


def _pick(pair: tuple[str, str], language: str) -> str:
    return pair[1] if language == "ar" else pair[0]


def _label(labels: dict[str, tuple[str, str]], key: str, language: str) -> str:
    return _pick(labels.get(key, (key, key)), language)


def _evidence_rows(snapshot: dict[str, Any], language: str) -> list[dict[str, str]]:
    rows = []
    for e in [*snapshot.get("evidence", []), *snapshot.get("calculations", [])]:
        kind = e.get("kind", "")
        cls = e.get("evidence_class") or "reference"
        src = e.get("source") or {}
        if kind == "web":
            title = e.get("title") or e.get("url", "")
            publisher = (e.get("publisher") or {}).get("ar" if language == "ar" else "en", "")
            published = e.get("published") or ("غير مذكور" if language == "ar" else "not stated")
            covered = ""
            url = e.get("url", "")
            accessed = (e.get("retrieved_at") or "")[:10]
        elif kind == "search":
            continue
        elif kind in ("calculation", "method"):
            title = e.get("calculation", "")
            publisher = "OSRIP"
            published = ""
            covered = ""
            url = ""
            accessed = ""
        else:
            names = e.get("indicator_name") or e.get("title") or e.get("name") or {}
            title = (
                names.get("ar" if language == "ar" else "en", "")
                if isinstance(names, dict)
                else str(names)
            )
            area = e.get("area_name") or {}
            if isinstance(area, dict) and area:
                title = f"{title} · {area.get('ar' if language == 'ar' else 'en', '')}"
            title = title or f"{e.get('indicator') or ''} {kind}".strip()
            publisher = src.get("publisher") or src.get("title") or ""
            published = (e.get("published_at") or "")[:10]
            start, end = e.get("period_start"), e.get("period_end")
            covered = f"{start} – {end}" if start and end and start != end else (start or "")
            url = src.get("url") or ""
            accessed = src.get("access_date") or ""
        value = e.get("value")
        unit = e.get("unit") or ""
        rows.append(
            {
                "id": e.get("id", ""),
                "class": _pick(CLASS_LABEL.get(cls, (cls, cls)), language),
                "title": str(title),
                "value": ""
                if value is None
                else f"{e.get('value_operator') or ''}{value} {unit}".strip(),
                "covered": covered,
                "publisher": str(publisher),
                "published": str(published),
                "accessed": str(accessed),
                "url": str(url),
                "record": str(e.get("record_ref") or (src.get("locator") or "")),
            }
        )
    return rows


def _structured_sections(structured: dict[str, Any], language: str) -> list[tuple[str, list[str]]]:
    ar = language == "ar"
    sections: list[tuple[str, list[str]]] = []
    cards = structured.get("recommendations") or []
    if cards:
        lines = []
        for n, c in enumerate(cards, 1):
            lines.append(
                f"{n}. "
                + "; ".join(
                    f"{label}: {c.get(key, '')}"
                    for key, label in (
                        ("finding", "النتيجة" if ar else "Finding"),
                        ("evidence", "الدليل" if ar else "Evidence"),
                        ("action", "الإجراء المقترح" if ar else "Suggested action"),
                        ("expected_benefit", "الفائدة المتوقعة" if ar else "Expected benefit"),
                        ("prerequisites", "المتطلبات المسبقة" if ar else "Prerequisites"),
                        ("uncertainty", "عدم اليقين" if ar else "Uncertainty"),
                    )
                )
                + f" [{', '.join(c.get('citations', []))}]"
            )
        sections.append(("التوصيات" if ar else "Recommendations", lines))
    drivers = structured.get("drivers") or []
    if drivers:
        sections.append(
            (
                "العوامل المؤثرة" if ar else "Drivers",
                [
                    f"{_label(DRIVER_LABEL, d['driver'], language)} "
                    f"({_label(BASIS_LABEL, d['basis'], language)}): {d['relation']}"
                    + (f" [{', '.join(d['citations'])}]" if d.get("citations") else "")
                    for d in drivers
                ],
            )
        )
    for key, en, ar_title in (
        ("evidence_points", "Evidence", "الأدلة"),
        ("hypotheses", "Hypotheses", "الفرضيات"),
        ("assumptions", "Assumptions", "الافتراضات"),
    ):
        items = structured.get(key) or []
        if items:
            sections.append(
                (
                    ar_title if ar else en,
                    [
                        i["statement"]
                        + (f" [{', '.join(i['citations'])}]" if i.get("citations") else "")
                        for i in items
                    ],
                )
            )
    conflicts = structured.get("conflicts") or []
    if conflicts:
        sections.append(
            (
                "تعارض المصادر" if ar else "Conflicting sources",
                [
                    f"{c['topic']}: "
                    + "; ".join(f"{v['value_text']} [{v['evidence_id']}]" for v in c["values"])
                    + (f" — {c['note']}" if c.get("note") else "")
                    for c in conflicts
                ],
            )
        )
    withheld = structured.get("withheld") or {}
    if withheld:
        total = sum(withheld.values())
        sections.append(
            (
                "أجزاء محجوبة" if ar else "Withheld parts",
                [
                    f"حُجب {total} جزءاً لأن الأدلة المستشهد بها لا تدعمه."
                    if ar
                    else f"{total} part(s) were withheld because the cited evidence "
                    "did not support them."
                ],
            )
        )
    return sections


def brief(
    session: Session, principal: Principal, saved_id: uuid.UUID, fmt: str
) -> tuple[str, str, str]:
    """(content, media type, file name) of a research brief built from the snapshot."""
    if fmt not in ("md", "html"):
        raise unprocessable("invalid_format", "Choose md or html.")
    row = _saved(session, principal, saved_id)
    snap = row.snapshot
    lang = row.language
    ar = lang == "ar"
    mode = _pick(MODE_LABEL.get(row.mode or "ask", ("Ask", "سؤال")), lang)
    meta = [
        ("السؤال" if ar else "Question", row.question),
        ("الوضع" if ar else "Mode", mode),
        ("وضع البيانات" if ar else "Data mode", row.data_mode.value),
        ("تاريخ الإجابة" if ar else "Answered", snap.get("answered_at", "")[:10]),
        ("تاريخ التنزيل" if ar else "Downloaded", _now().date().isoformat()),
        (
            "تاريخ التحقق من السجلات" if ar else "Records checked up to",
            snap.get("research_cutoff") or "—",
        ),
        (
            "مصدر الإجابة" if ar else "Answer",
            (
                "مولّد بالذكاء الاصطناعي وتم التحقق من أرقامه مقابل الأدلة"
                if ar
                else "AI-generated; every figure checked against the cited evidence"
            )
            if snap.get("ai_generated")
            else (
                "بحث في السجلات، ليس بالذكاء الاصطناعي" if ar else "Record lookup, not AI-generated"
            ),
        ),
    ]
    sections = _structured_sections(snap.get("structured") or {}, lang)
    evidence = _evidence_rows(snap, lang)
    columns = (
        [
            "المعرّف",
            "النوع",
            "العنصر",
            "القيمة",
            "الفترة المغطاة",
            "الناشر",
            "تاريخ النشر",
            "تاريخ الاطلاع",
            "المرجع",
            "الرابط",
        ]
        if ar
        else [
            "ID",
            "Type",
            "Item",
            "Value",
            "Period covered",
            "Publisher",
            "Published",
            "Accessed",
            "Record",
            "Link",
        ]
    )
    keys = [
        "id",
        "class",
        "title",
        "value",
        "covered",
        "publisher",
        "published",
        "accessed",
        "record",
        "url",
    ]
    slug = re.sub(r"[^A-Za-z0-9]+", "-", row.title.lower()).strip("-")[:50] or "research"
    if fmt == "md":
        out = [f"# {row.title}", ""]
        out += [f"- **{k}:** {v}" for k, v in meta]
        if row.note:
            out += ["", f"> {row.note}"]
        out += ["", f"## {'الإجابة' if ar else 'Answer'}", "", snap.get("content", "")]
        for title, lines in sections:
            out += ["", f"## {title}", ""] + [f"- {ln}" for ln in lines]
        out += ["", f"## {'المصادر والأدلة' if ar else 'Sources and evidence'}", ""]
        out.append("| " + " | ".join(columns) + " |")
        out.append("|" + "---|" * len(columns))
        for r in evidence:
            out.append("| " + " | ".join(r[k].replace("|", "/") for k in keys) + " |")
        out += ["", f"## {'حدود الاستخدام' if ar else 'Limitations'}", ""] + [
            f"- {x}" for x in LIMITATIONS[lang]
        ]
        return "\n".join(out) + "\n", "text/markdown; charset=utf-8", f"osrip-brief-{slug}.md"
    e = html.escape
    body = [f"<h1>{e(row.title)}</h1>", "<dl>"]
    body += [f"<dt>{e(k)}</dt><dd>{e(str(v))}</dd>" for k, v in meta]
    body.append("</dl>")
    if row.note:
        body.append(f"<blockquote>{e(row.note)}</blockquote>")
    body.append(f"<h2>{'الإجابة' if ar else 'Answer'}</h2>")
    body += [f"<p>{e(p)}</p>" for p in snap.get("content", "").split("\n") if p.strip()]
    for title, lines in sections:
        body.append(
            f"<h2>{e(title)}</h2><ul>" + "".join(f"<li>{e(ln)}</li>" for ln in lines) + "</ul>"
        )
    body.append(f"<h2>{'المصادر والأدلة' if ar else 'Sources and evidence'}</h2><table><thead><tr>")
    body += [f"<th scope='col'>{e(c)}</th>" for c in columns]
    body.append("</tr></thead><tbody>")
    for r in evidence:
        cells = []
        for k in keys:
            if k == "url" and r[k].startswith(("http://", "https://")):
                cells.append(
                    f"<td><a href='{e(r[k], quote=True)}' rel='noreferrer'>{e(r[k])}</a></td>"
                )
            else:
                cells.append(f"<td>{e(r[k])}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    body.append("</tbody></table>")
    body.append(f"<h2>{'حدود الاستخدام' if ar else 'Limitations'}</h2><ul>")
    body += [f"<li>{e(x)}</li>" for x in LIMITATIONS[lang]]
    body.append("</ul>")
    doc = (
        f"<!doctype html><html lang='{lang}' dir='{'rtl' if ar else 'ltr'}'><head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{e(row.title)}</title><style>{BRIEF_CSS}</style></head><body>"
        + "".join(body)
        + "</body></html>"
    )
    return doc, "text/html; charset=utf-8", f"osrip-brief-{slug}.html"


# ------------------------------------------------------------------ source library


def sources(
    session: Session,
    principal: Principal | None,
    *,
    q: str | None = None,
    source_class: str | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    reviewer = principal is not None and principal.has(Permission.RESEARCH_REVIEW)
    term = f"%{q.strip()}%" if q and q.strip() else None
    out: list[dict[str, Any]] = []

    pack = session.scalar(select(ReferencePack).order_by(ReferencePack.research_cutoff.desc()))
    if pack is not None and source_class in (None, "official", "reference_pack"):
        stmt = select(ReferencePackSource).where(ReferencePackSource.pack_id == pack.id)
        if term:
            stmt = stmt.where(
                or_(
                    ReferencePackSource.title.ilike(term), ReferencePackSource.publisher.ilike(term)
                )
            )
        for s in session.scalars(stmt.order_by(ReferencePackSource.code)):
            out.append(
                {
                    "kind": "reference_pack",
                    "code": s.code,
                    "title": s.title,
                    "publisher": s.publisher,
                    "publication": s.publication,
                    "source_class": "official"
                    if s.role in ("primary", "official_statement")
                    else ("secondary" if "crosscheck" not in s.role else "crosscheck"),
                    "role": s.role,
                    "url": s.url,
                    "accessed_on": s.accessed_on.isoformat(),
                    "research_cutoff": pack.research_cutoff.isoformat(),
                }
            )

    if source_class in (None, "official", "dataset"):
        counts = (
            select(Source.id, func.count(Observation.id).label("n"))
            .join(DatasetVersion, DatasetVersion.source_id == Source.id)
            .join(Observation, Observation.dataset_version_id == DatasetVersion.id)
            .where(
                Source.data_mode == DataMode.VERIFIED_SOURCE,
                DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
            )
            .group_by(Source.id)
            .subquery()
        )
        stmt = select(Source, counts.c.n).join(counts, counts.c.id == Source.id)
        if term:
            stmt = stmt.where(or_(Source.dataset_title.ilike(term), Source.publisher.ilike(term)))
        for s, n in session.execute(stmt.order_by(Source.dataset_title)):
            out.append(
                {
                    "kind": "dataset",
                    "code": s.source_code,
                    "title": s.dataset_title,
                    "publisher": s.publisher,
                    "source_class": "official",
                    "url": s.url,
                    "accessed_on": s.access_date.isoformat() if s.access_date else None,
                    "reference_period": s.reference_period,
                    "published_records": n,
                }
            )

    if source_class in (None, "official", "international", "research", "secondary", "web"):
        stmt = select(
            ResearchCandidate.source_url,
            func.max(ResearchCandidate.source_title),
            func.max(ResearchCandidate.publisher),
            func.max(ResearchCandidate.source_class),
            func.max(ResearchCandidate.publication_date),
            func.max(ResearchCandidate.retrieved_at),
            func.count(),
            func.count().filter(ResearchCandidate.status == "accepted"),
            func.count().filter(ResearchCandidate.status == "pending"),
            func.max(ResearchCandidate.domain),
        ).group_by(ResearchCandidate.source_url)
        if not reviewer:
            stmt = stmt.where(ResearchCandidate.status == "accepted")
        if source_class in ("official", "international", "research", "secondary"):
            stmt = stmt.where(ResearchCandidate.source_class == source_class)
        if domain:
            stmt = stmt.where(ResearchCandidate.domain == domain)
        if term:
            stmt = stmt.where(
                or_(
                    ResearchCandidate.source_title.ilike(term),
                    ResearchCandidate.publisher.ilike(term),
                )
            )
        for (
            url,
            title,
            publisher,
            cls,
            published,
            retrieved,
            total,
            accepted,
            pending,
            dom,
        ) in session.execute(stmt):
            out.append(
                {
                    "kind": "web_found",
                    "title": title,
                    "publisher": publisher,
                    "source_class": cls,
                    "url": url,
                    "publication_date": published.isoformat() if published else None,
                    "retrieved_at": retrieved.isoformat() if retrieved else None,
                    "domain": dom,
                    "figures_found": total,
                    "figures_accepted": accepted,
                    "figures_pending": pending if reviewer else None,
                }
            )
    return {
        "sources": out,
        "note": {
            "en": "Reference-pack and dataset sources supply the platform's approved statistics. "
            "Web-found sources are listed with what the review queue decided; their figures are "
            "not approved statistics until imported.",
            "ar": "مصادر الحزمة المرجعية ومجموعات البيانات هي مصدر الإحصاءات المعتمدة في المنصة. "
            "وتُعرض المصادر التي عُثر عليها على الإنترنت مع قرار قائمة المراجعة، وأرقامها ليست "
            "إحصاءات معتمدة حتى تُستورد.",
        },
    }
