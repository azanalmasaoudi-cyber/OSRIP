"""Report documents built from stored results, in English or Arabic.

* ``dataset_document``: an uploaded dataset's computed analysis (and its checked AI summary,
  labelled as such), with the research questions the person wrote.
* ``research_document``: an assistant answer that passed the evidence check: the question,
  the answer, its cards, tables and charts (built by the server from published rows), what
  the research read and saved, conflicts and assumptions, and every cited source.
* ``platform_document``: a frozen platform report (observations, calculations, review
  cards and sources).

Nothing here computes a figure: tables carry the values stored with the dataset, answer or
report. Inline evidence markers ([E3]) become reference numbers ([3]).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.datasets.analysis import computed
from app.services.documents.model import validate
from app.services.exports import calculation_rows

L = {
    "en": {
        "questions": "Research questions", "summary": "Executive summary", "dataset": "Dataset",
        "analysis": "Analysis", "charts": "Charts", "conclusions": "Findings and conclusions",
        "limits": "Limits of the data", "question": "Research question", "answer": "Answer",
        "figures": "Key findings", "tables": "Data tables", "research": "Research carried out",
        "caveats": "Conflicts, assumptions and limitations", "observations": "Published observations",
        "calculations": "Calculations", "review": "Review cards", "file": "File", "rows": "Rows",
        "columns": "Columns", "uploaded": "Uploaded", "created": "Created", "kind": "Report",
        "dataset_kind": "Dataset analysis", "research_kind": "Research answer",
        "platform_kind": "Platform report", "column": "Column", "type": "Kind", "unit": "Unit",
        "filled": "Filled", "missing": "Missing", "distinct": "Distinct", "count": "Count",
        "sum": "Sum", "mean": "Mean", "median": "Median", "min": "Minimum", "max": "Maximum",
        "std": "Standard deviation", "group": "Group", "first": "First", "last": "Last",
        "change": "Change", "change_pct": "Change (%)", "cagr": "Compound annual growth (%)",
        "period": "Period", "value": "Value", "statistics": "Statistics", "trends": "Trends",
        "unusual": "Unusual values", "method": "Method", "values": "Values", "share": "Share (%)",
        "correlations": "Correlations", "pair": "Columns", "pairs": "Rows with both",
        "strength": "Strength", "ai_by": "Written by {model} ({provider}) from the computed results; OSRIP checked every number against them{removed}.",
        "ai_removed": " and removed {n} sentence(s) with other numbers",
        "computed_by": "Built by OSRIP from computed values (no AI summary in this language).",
        "number": "number", "text": "text", "period_kind": "period",
        "finding": "Finding", "evidence": "Evidence", "action": "Action",
        "status": "Status", "source": "Source", "indicator": "Indicator", "saved": "saved",
        "read": "Documents read", "submitted": "Figures submitted for validation",
        "conflict": "Conflicting figures", "assumption": "Assumption", "hypothesis": "Hypothesis",
        "driver": "Driver", "basis": "Basis", "data_mode": "Data", "section": "Section",
        "filters": "Filters", "dataset_note": "Values from the uploaded file and computed by OSRIP; nothing was estimated. Missing values were left out, never counted as zero.",
        "dataset_notice": "Frozen when created on {date}. A correlation shows that two measures move together, not that one causes the other; an unusual value may be real or a data error.",
        "research_notice": "Frozen when created on {date}. The answer passed OSRIP's evidence check: every number in it was found in the evidence it cites. Web figures are as published by their sources; only figures marked saved were added to the platform's data.",
        "platform_notice": "Frozen at generation: later publications do not change this report. Missing values are empty, never zero.",
        "method_ref": "Modified z-score for unusual values (Iglewicz and Hoaglin, 1993); compound annual growth over full years only.",
        "file_ref": "Uploaded file (SHA-256 {sha})",
        "calc_note": "Calculated by the platform from the published values in the sources shown, not published figures; values rounded for display.",
        "methods": {"modified_z_score": "Modified z-score", "iqr_fences": "1.5 × IQR fences"},
        "strengths": {"strong": "strong", "moderate": "moderate", "weak": "weak"},
    },
    "ar": {
        "questions": "أسئلة البحث", "summary": "الملخص التنفيذي", "dataset": "مجموعة البيانات",
        "analysis": "التحليل", "charts": "الرسوم البيانية", "conclusions": "النتائج والاستنتاجات",
        "limits": "حدود البيانات", "question": "سؤال البحث", "answer": "الإجابة",
        "figures": "أهم النتائج", "tables": "جداول البيانات", "research": "البحث المُنجز",
        "caveats": "التعارضات والافتراضات والقيود", "observations": "الملاحظات المنشورة",
        "calculations": "الحسابات", "review": "بطاقات المراجعة", "file": "الملف", "rows": "الصفوف",
        "columns": "الأعمدة", "uploaded": "تاريخ الرفع", "created": "تاريخ الإنشاء", "kind": "التقرير",
        "dataset_kind": "تحليل مجموعة بيانات", "research_kind": "إجابة بحثية",
        "platform_kind": "تقرير المنصة", "column": "العمود", "type": "النوع", "unit": "الوحدة",
        "filled": "مملوءة", "missing": "مفقودة", "distinct": "قيم مختلفة", "count": "العدد",
        "sum": "المجموع", "mean": "المتوسط", "median": "الوسيط", "min": "الأدنى", "max": "الأعلى",
        "std": "الانحراف المعياري", "group": "المجموعة", "first": "الأولى", "last": "الأخيرة",
        "change": "التغير", "change_pct": "التغير (%)", "cagr": "معدل النمو السنوي المركب (%)",
        "period": "الفترة", "value": "القيمة", "statistics": "الإحصاءات", "trends": "الاتجاهات",
        "unusual": "قيم غير معتادة", "method": "الطريقة", "values": "القيم", "share": "النسبة (%)",
        "correlations": "الارتباطات", "pair": "العمودان", "pairs": "صفوف فيها القيمتان",
        "strength": "القوة", "ai_by": "كتبه {model} ({provider}) من النتائج المحسوبة؛ وتحقق OSRIP من كل رقم فيه مقابلها{removed}.",
        "ai_removed": " وحذف {n} جملة فيها أرقام أخرى",
        "computed_by": "أعدّه OSRIP من قيم محسوبة (لا يوجد ملخص بالذكاء الاصطناعي بهذه اللغة).",
        "number": "رقم", "text": "نص", "period_kind": "فترة",
        "finding": "النتيجة", "evidence": "الدليل", "action": "الإجراء",
        "status": "الحالة", "source": "المصدر", "indicator": "المؤشر", "saved": "حُفظ",
        "read": "الوثائق المقروءة", "submitted": "الأرقام المرسلة للتحقق",
        "conflict": "أرقام متعارضة", "assumption": "افتراض", "hypothesis": "فرضية",
        "driver": "العامل", "basis": "الأساس", "data_mode": "البيانات", "section": "القسم",
        "filters": "عوامل التصفية", "dataset_note": "القيم من الملف المرفوع وحسبها OSRIP؛ لم يُقدَّر شيء. استُبعدت القيم المفقودة ولم تُحسب صفرًا.",
        "dataset_notice": "جُمّد عند إنشائه في {date}. يدل الارتباط على أن المقياسين يتغيران معًا، ولا يعني أن أحدهما سبب الآخر؛ وقد تكون القيمة غير المعتادة حقيقية أو خطأً في البيانات.",
        "research_notice": "جُمّد عند إنشائه في {date}. اجتازت الإجابة فحص الأدلة في OSRIP: وُجد كل رقم فيها في الدليل الذي تستشهد به. أرقام الويب كما نشرتها مصادرها؛ ولم يُضف إلى بيانات المنصة إلا ما وُسم بأنه حُفظ.",
        "platform_notice": "جُمّد عند إعداده: لا تغيّر المنشورات اللاحقة هذا التقرير. القيم المفقودة فارغة ولا تُحسب صفرًا.",
        "method_ref": "درجة z المعدلة للقيم غير المعتادة (Iglewicz وHoaglin، 1993)؛ ومعدل النمو السنوي المركب على السنوات الكاملة فقط.",
        "file_ref": "الملف المرفوع (SHA-256 {sha})",
        "calc_note": "حسبتها المنصة من القيم المنشورة في المصادر المبيّنة، وليست أرقامًا منشورة؛ القيم مقرّبة للعرض.",
        "methods": {"modified_z_score": "درجة z المعدلة", "iqr_fences": "حدود 1.5 × المدى الربيعي"},
        "strengths": {"strong": "قوي", "moderate": "متوسط", "weak": "ضعيف"},
    },
}  # fmt: skip


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _day(iso: str) -> str:
    return iso[:10]


def _table(
    title: str | None,
    columns: list[tuple[str, bool]],
    rows: list[list[Any]],
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "table",
        "title": title,
        "columns": [{"label": label, "numeric": numeric} for label, numeric in columns],
        "rows": [[None if v is None else str(v) for v in row] for row in rows],
        "note": note,
    }


def _paragraph(text: str, note: bool = False) -> dict[str, Any]:
    return {"type": "paragraph", "text": text, "note": note}


# ------------------------------------------------------------------ datasets


def dataset_document(
    dataset: dict[str, Any], analysis: dict[str, Any], summary: dict[str, Any] | None,
    language: str, title: str, questions: list[str],
) -> dict[str, Any]:  # fmt: skip
    t = L[language]
    created = _now()
    sections: list[dict[str, Any]] = []
    if questions:
        sections.append(
            {"heading": t["questions"], "blocks": [{"type": "bullets", "items": questions}]}
        )
    summary_blocks: list[dict[str, Any]] = []
    if summary and summary.get("status") == "ok":
        summary_blocks.append(_paragraph(summary["overview"]))
        if summary.get("highlights"):
            summary_blocks.append({"type": "bullets", "items": summary["highlights"]})
        removed = t["ai_removed"].format(n=summary["removed"]) if summary.get("removed") else ""
        summary_blocks.append(
            _paragraph(
                t["ai_by"].format(
                    model=summary["model"], provider=summary["provider"], removed=removed
                ),
                note=True,
            )
        )
    else:
        findings = [f["text"][language] for f in analysis["findings"][:5]]
        if findings:
            summary_blocks.append({"type": "bullets", "items": findings})
        summary_blocks.append(_paragraph(t["computed_by"], note=True))
    sections.append({"heading": t["summary"], "blocks": summary_blocks})

    kinds = {"number": t["number"], "text": t["text"], "period": t["period_kind"]}
    profile = [
        [c["name"], kinds[c["kind"]], (c.get("unit") or {}).get("label_ar" if language == "ar" else "label_en"),
         c["count"], c["missing"], c["distinct"]]
        for c in analysis["profile"]
    ]  # fmt: skip
    sections.append({"heading": t["dataset"], "blocks": [
        _paragraph(f"{t['file']}: {dataset['name']} ({dataset['file_type'].upper()}{' · ' + dataset['sheet'] if dataset.get('sheet') else ''}) · "
                   f"{t['rows']}: {analysis['rows']} · {t['columns']}: {analysis['columns']} · {t['uploaded']}: {_day(dataset['created_at'])}"),
        _table(None, [(t["column"], False), (t["type"], False), (t["unit"], False), (t["filled"], True),
                      (t["missing"], True), (t["distinct"], True)], profile),
        _paragraph(t["dataset_note"], note=True),
    ]})  # fmt: skip

    blocks: list[dict[str, Any]] = []
    if analysis["statistics"]:
        blocks.append(_table(t["statistics"], [
            (t["column"], False), (t["count"], True), (t["sum"], True), (t["mean"], True), (t["median"], True),
            (t["min"], True), (t["max"], True), (t["std"], True),
        ], [[s["column"], s["count"], s["sum"], s["mean"], s["median"], s["min"]["value"], s["max"]["value"], s["std"]]
            for s in analysis["statistics"]]))  # fmt: skip
    if analysis["trends"]:
        blocks.append(_table(t["trends"], [
            (t["column"], False), (t["group"], False), (t["first"], False), (t["last"], False),
            (t["change"], True), (t["change_pct"], True), (t["cagr"], True),
        ], [[tr["column"], (tr["group"] or {}).get("value"), f"{tr['first']['value']} ({tr['first']['period']})",
             f"{tr['last']['value']} ({tr['last']['period']})", tr["change"], tr["change_pct"], tr["cagr_pct"]]
            for tr in analysis["trends"]]))  # fmt: skip
    unusual = [a for a in analysis["anomalies"] if a["status"] == "found"]
    if unusual:
        blocks.append(_table(t["unusual"], [(t["column"], False), (t["method"], False), (t["values"], False)], [
            [a["column"], t["methods"].get(a["method"], a["method"]), "; ".join(f"{i['value']} (#{i['row']}{', ' + i['period'] if i.get('period') else ''})" for i in a["items"])]
            for a in unusual
        ]))  # fmt: skip
    for c in analysis["comparisons"][:6]:
        blocks.append(_table(f"{c['column']} · {c['category']}", [
            (t["group"], False), (t["count"], True), (t["sum"], True), (t["mean"], True), (t["share"], True),
        ], [[g["group"], g["count"], g["sum"], g["mean"], g["share_pct"]] for g in c["groups"]]))  # fmt: skip
    if analysis["correlations"]:
        blocks.append(_table(t["correlations"], [(t["pair"], False), ("r", True), (t["pairs"], True), (t["strength"], False)],
                             [[f"{c['x']} · {c['y']}", c["r"], c["pairs"], t["strengths"][c["strength"]]] for c in analysis["correlations"]]))  # fmt: skip
    if blocks:
        sections.append({"heading": t["analysis"], "blocks": blocks})
    charts = [
        {"type": "chart", "title": v["title"][language], "table": v["table"], "chart": v["chart"],
         "note": (v.get("note") or {}).get(language)}
        for v in analysis["views"][:6]
    ]  # fmt: skip
    if charts:
        sections.append({"heading": t["charts"], "blocks": charts})
    conclusions: list[dict[str, Any]] = (
        [{"type": "bullets", "items": [f["text"][language] for f in analysis["findings"]]}]
        if analysis["findings"]
        else []
    )
    if summary and summary.get("status") == "ok" and summary.get("caveats"):
        conclusions += [_paragraph(t["limits"]), {"type": "bullets", "items": summary["caveats"]}]
    if conclusions:
        sections.append({"heading": t["conclusions"], "blocks": conclusions})
    return validate({
        "kind": "dataset", "language": language, "title": title, "subtitle": t["dataset_kind"],
        "created_at": created,
        "meta": [(t["file"], dataset["name"]), (t["created"], _day(created))],
        "sections": sections,
        "references": [
            {"title": dataset["name"], "note": t["file_ref"].format(sha=dataset["sha256"][:16] + "…"),
             "published": _day(dataset["created_at"])},
            {"title": t["method_ref"]},
        ],
        "notice": t["dataset_notice"].format(date=_day(created)),
    })  # fmt: skip


# ------------------------------------------------------------------ research answers

# An evidence marker as answers write it: [E3], or E3 on its own (as the evidence check accepts).
_MARKER = re.compile(r"\s?\[?(?<![A-Za-z0-9])(E\d+)(?![A-Za-z0-9])\]?")


def _plain(text: str) -> str:
    """Answer text without Markdown emphasis or heading marks."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"^#+\s*", "", text, flags=re.MULTILINE).strip()


def research_document(
    question: str, message: dict[str, Any], language: str, title: str
) -> dict[str, Any]:  # fmt: skip
    t = L[language]
    created = _now()
    structured = message.get("structured") or {}
    evidence = message.get("evidence") or []
    by_id = {e["id"]: e for e in evidence if isinstance(e, dict) and e.get("id")}
    # Platform calculations (stored apart from the evidence) are numbered C1, C2 ...
    calculations = [
        c
        for c in message.get("calculations") or []
        if isinstance(c, dict) and c.get("kind") == "calculation"
    ]
    calc_number = {c["id"]: n for n, c in enumerate(calculations, start=1)}
    # References: every cited item that names a source, in citation order, then the inputs
    # of the calculations.
    order: list[str] = []
    inputs = [i for c in calculations for i in c.get("inputs") or []]
    for eid in [*(message.get("citations") or []), *inputs]:
        if (
            eid in by_id
            and eid not in order
            and by_id[eid].get("kind") in ("web", "observation", "series")
        ):
            order.append(eid)
    number = {eid: n for n, eid in enumerate(order, start=1)}

    def cite(text: str) -> str:
        # A cited source becomes its reference number and a calculation its C number;
        # another evidence id is dropped; anything else that looks like a marker stays.
        def swap(m: re.Match[str]) -> str:
            eid = m.group(1)
            if eid in number:
                return f" [{number[eid]}]"
            if eid in calc_number:
                return f" [C{calc_number[eid]}]"
            return "" if eid in by_id else m.group(0)

        return _MARKER.sub(swap, text)

    def cites(ids: list[str]) -> str:
        found = [f"[{number[i]}]" for i in ids if i in number]
        return " " + "".join(found) if found else ""

    answer_blocks: list[dict[str, Any]] = []
    bullets: list[str] = []
    for chunk in re.split(r"\n\s*\n", _plain(message.get("content") or "")):
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        for ln in lines:
            if re.match(r"^[-*•]\s+", ln):
                bullets.append(cite(re.sub(r"^[-*•]\s+", "", ln)))
                continue
            if bullets:
                answer_blocks.append({"type": "bullets", "items": bullets})
                bullets = []
            answer_blocks.append(_paragraph(cite(ln)))
    if bullets:
        answer_blocks.append({"type": "bullets", "items": bullets})
    sections = [
        {"heading": t["question"], "blocks": [_paragraph(question)]},
        {"heading": t["summary"], "blocks": answer_blocks or [_paragraph("—")]},
    ]
    findings = structured.get("recommendations") or []
    points = structured.get("evidence_points") or []
    if findings or points:
        blocks: list[dict[str, Any]] = []
        if points:
            blocks.append(
                {
                    "type": "bullets",
                    "items": [p["statement"] + cites(p.get("citations", [])) for p in points],
                }
            )
        if findings:
            blocks.append(_table(None, [(t["finding"], False), (t["evidence"], False), (t["action"], False)],
                                 [[f["finding"], f["evidence"] + cites(f.get("citations", [])), f["action"]] for f in findings]))  # fmt: skip
        sections.append({"heading": t["figures"], "blocks": blocks})
    if calculations:
        rows = []
        for c in calculations:
            value = c.get("value")
            if value is not None:
                try:
                    value = computed(Decimal(str(value)))
                except InvalidOperation:
                    value = str(value)
            unit = "%" if c.get("unit") == "percent" else c.get("unit")
            inputs = "".join(f"[{number[i]}]" for i in c.get("inputs") or [] if i in number)
            formula = (c.get("formula") or {}).get(language) or c.get("calculation") or ""
            rows.append([f"C{calc_number[c['id']]}", formula, value, unit, inputs or None])
        sections.append({"heading": t["calculations"], "blocks": [
            _table(None, [("#", False), (t["method"], False), (t["value"], True), (t["unit"], False), (t["source"], False)], rows),
            _paragraph(t["calc_note"], note=True),
        ]})  # fmt: skip
    tables = []
    for entry in structured.get("data_tables") or []:
        for block in entry.get("tables") or []:
            table = block["table"]
            cols = table["columns"]
            labels = []
            for c in cols:
                unit = c.get("unit")
                suffix = (
                    f" ({unit['label_ar' if language == 'ar' else 'label_en']})" if unit else ""
                )
                labels.append((c["label"][language] + suffix, c["kind"] == "number"))
            tables.append(
                _table(None, labels, [[r.get(c["key"]) for c in cols] for r in table["rows"]])
            )
    if tables:
        sections.append({"heading": t["tables"], "blocks": tables})
    charts = [
        {"type": "chart", "title": c["title"][language], "table": c["table"], "chart": c["chart"]}
        for c in structured.get("data_charts") or []
        if c.get("status") == "ok"
    ]
    if charts:
        sections.append({"heading": t["charts"], "blocks": charts})
    research = structured.get("research")
    if research:
        blocks = []
        read = research.get("sources_read") or []
        if read:
            blocks.append(_table(t["read"], [(t["source"], False), (t["period"], False)],
                                 [[r.get("title") or r["url"], r.get("published")] for r in read]))  # fmt: skip
        submitted = (research.get("saved") or []) + (research.get("not_saved") or [])
        if submitted:
            blocks.append(_table(t["submitted"], [
                (t["indicator"], False), (t["period"], False), (t["value"], True), (t["unit"], False), (t["status"], False),
            ], [[s.get("indicator_code") or s.get("indicator"), s.get("period"), s.get("value") or s.get("value_text"),
                 s.get("unit"), t["saved"] if s.get("saved") else s.get("status")] for s in submitted]))  # fmt: skip
        if blocks:
            sections.append({"heading": t["research"], "blocks": blocks})
    caveats: list[str] = []
    for c in structured.get("conflicts") or []:
        values = ", ".join(v["value_text"] + cites([v["evidence_id"]]) for v in c["values"])
        caveats.append(
            f"{t['conflict']}: {c['topic']}: {values}" + (f". {c['note']}" if c.get("note") else "")
        )
    for key, label in (("assumptions", t["assumption"]), ("hypotheses", t["hypothesis"])):
        caveats += [
            f"{label}: {p['statement']}{cites(p.get('citations', []))}"
            for p in structured.get(key) or []
        ]
    for d in structured.get("drivers") or []:
        caveats.append(
            f"{t['driver']} ({d['basis']}): {d['relation']}{cites(d.get('citations', []))}"
        )
    notice = structured.get("web_notice")
    if isinstance(notice, dict) and notice.get(language):
        caveats.append(str(notice[language]))
    if caveats:
        sections.append(
            {"heading": t["caveats"], "blocks": [{"type": "bullets", "items": caveats}]}
        )
    references = []
    for eid in order:
        e = by_id[eid]
        if e.get("kind") == "web":
            publisher = e.get("publisher") or {}
            references.append({
                "title": e.get("title") or e.get("url") or eid, "url": e.get("url"),
                "publisher": publisher.get(language) or publisher.get("en"),
                "published": e.get("published"),
                "retrieved": (e.get("retrieved_at") or "")[:16].replace("T", " ") or None,
                "note": e.get("content_kind"),
            })  # fmt: skip
        else:
            source = e.get("source") or {}
            references.append({
                "title": source.get("title") or e.get("indicator_name", {}).get(language) or eid,
                "url": source.get("url"), "publisher": source.get("publisher"),
                "published": None, "retrieved": None,
                "note": f"{e.get('indicator')} · {e.get('area')} · {e.get('period_start')}–{e.get('period_end')}",
            })  # fmt: skip
    return validate({
        "kind": "research", "language": language, "title": title, "subtitle": t["research_kind"],
        "created_at": created,
        "meta": [(t["created"], _day(created)), *([("AI", message["model"])] if message.get("model") else [])],
        "sections": sections, "references": references,
        "notice": t["research_notice"].format(date=_day(created)),
    })  # fmt: skip


# ------------------------------------------------------------------ platform reports


def platform_document(content: dict[str, Any], language: str) -> dict[str, Any]:
    t = L[language]
    sections = []
    obs = []
    for s in content.get("series", []):
        name = s["indicator"]["name_ar" if language == "ar" else "name_en"]
        area = s["area"]["name_ar" if language == "ar" else "name_en"]
        unit = s["unit"]["label_ar" if language == "ar" else "label_en"]
        obs.append(_table(f"{name} · {area} · {unit}", [
            (t["period"], False), (t["value"], True), (t["status"], False), (t["source"], False),
        ], [[f"{o['period_start']} – {o['period_end']}", o["value"], o["quality_status"], s["dataset_version"]["label"]]
            for o in s["observations"]]))  # fmt: skip
    if obs:
        sections.append({"heading": t["observations"], "blocks": obs})
    calcs = calculation_rows(content.get("data_mode", ""), content.get("calculations", []))
    if calcs:
        sections.append({"heading": t["calculations"], "blocks": [_table(None, [
            (t["finding"], False), (t["status"], False), (t["value"], True), (t["unit"], False),
        ], [[r[2], r[4], r[5] or None, r[6]] for r in calcs])]})  # fmt: skip
    cards = content.get("review_cards") or []
    if cards:
        sections.append({"heading": t["review"], "blocks": [{"type": "bullets", "items": [
            f"{c['rule_code']} ({c['status']}): {c['observation'][language]}" for c in cards
        ]}]})  # fmt: skip
    filters = "; ".join(f"{k}={v}" for k, v in (content.get("filters") or {}).items()) or "—"
    return validate({
        "kind": "platform", "language": language, "title": content.get("title") or t["platform_kind"],
        "subtitle": f"{t['platform_kind']} · {content.get('label', '')}",
        "created_at": content.get("generated_at") or _now(),
        "meta": [(t["data_mode"], str(content.get("data_mode"))), (t["section"], str(content.get("section"))),
                 (t["filters"], filters)],
        "sections": sections or [{"heading": t["observations"], "blocks": [_paragraph("—")]}],
        "references": [
            {"title": s["source"].get("dataset_title") or s.get("label") or "", "note": s.get("label")}
            for s in content.get("sources", [])
        ],
        "notice": t["platform_notice"],
    })  # fmt: skip
