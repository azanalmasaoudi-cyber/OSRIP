"""Analysis of figures found on the web: the research plan, calculations, tables, charts and
diagrams of Deep internet research (and of Quick answers where useful). Pure: no I/O.

Every figure taken from the web must appear in the evidence it cites (the same check as
grounding.validate: the number written in the cited page, search result or excerpt, allowing
only rounding). Calculations are done here, never by the model; their results become
evidence the answer may cite. Tables keep only rows whose figures match their citations;
charts are drawn from those rows; diagrams may not carry figures the evidence does not hold.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

from app.services.assistant.grounding import (
    _allowed,
    _evidence_numbers,
    _is_year,
    _matches,
    numbers_in,
)

MAX_PLAN = 8
CALC_KINDS = ("percent_change", "cagr", "share", "difference", "ratio", "sum", "average", "hhi")
MAX_COLUMNS = 6
MAX_ROWS = 40
DIAGRAM_KINDS = ("flowchart", "cycle", "hierarchy", "mindmap")
MAX_NODES = 14
MAX_EDGES = 20

_FORMULA = {
    "percent_change": ("(new − old) / old × 100", "(الجديد − القديم) ÷ القديم × 100"),
    "cagr": (
        "((last / first)^(1 / years) − 1) × 100",
        "((الأخير ÷ الأول)^(1 ÷ السنوات) − 1) × 100",
    ),
    "share": ("part / total × 100", "الجزء ÷ الإجمالي × 100"),
    "difference": ("second − first", "الثاني − الأول"),
    "ratio": ("first / second", "الأول ÷ الثاني"),
    "sum": ("sum of the values", "مجموع القيم"),
    "average": ("sum / count", "المجموع ÷ العدد"),
    "hhi": (
        "Σ (each value's share of the total, in %)² (0–10,000; above 2,500 is highly concentrated)",
        "مجموع (حصة كل قيمة من الإجمالي بالنسبة المئوية)² (0–10,000؛ فوق 2,500 تركّز عالٍ)",
    ),
}
_SLUG = re.compile(r"[^a-z0-9_-]+")


def _err(message: str, **extra: Any) -> dict[str, Any]:
    return {"status": "refused", "message": message, **extra}


def plan(ledger: Any, questions: list[Any]) -> dict[str, Any]:
    """The research questions, recorded before searching (shown with the answer's method)."""
    kept = [str(q).strip()[:200] for q in questions if str(q).strip()][:MAX_PLAN]
    if not kept:
        return _err("Give one to eight research questions.")
    ledger.meta["plan"] = kept
    return {
        "status": "ok",
        "questions": len(kept),
        "next": "Search for several of these at once (several web_search calls in one step), in "
        "Arabic and English, then read the most relevant original pages.",
    }


def _value(raw: Any) -> tuple[Decimal, int] | None:
    text = str(raw).strip()
    found = numbers_in(text)
    if len(found) != 1:
        return None
    number, decimals = found[0]
    return (-number if text.startswith(("-", "−")) else number), decimals


def calculate(
    ledger: Any,
    kind: str,
    inputs: list[Any],
    *,
    label: str | None = None,
    unit: str | None = None,
    years: int | None = None,
) -> dict[str, Any]:
    """A calculation on cited web figures, done here. Each input names its evidence and the
    value as written there; a value the evidence does not hold is refused."""
    if kind not in CALC_KINDS:
        return _err(f"Unknown calculation. Use one of: {', '.join(CALC_KINDS)}.")
    items = ledger.by_id()
    values: list[Decimal] = []
    ids: list[str] = []
    for entry in inputs[:20]:
        if not isinstance(entry, dict):
            return _err("Each input is {evidence_id, value}.")
        eid = str(entry.get("evidence_id", ""))
        item = items.get(eid)
        if item is None:
            return _err(f"No evidence {eid} in this answer.")
        parsed = _value(entry.get("value", ""))
        if parsed is None:
            return _err(f"Give one number for {eid}, as written in that source.")
        number, decimals = parsed
        if not _matches(number, decimals, _evidence_numbers(item, items)):
            return _err(
                f"{entry.get('value')} is not written in {eid}. Use the figure the source gives."
            )
        values.append(number)
        ids.append(eid)
    pairs = kind in ("percent_change", "cagr", "share", "difference", "ratio")
    if (pairs and len(values) != 2) or (not pairs and len(values) < 2):
        return _err(
            "This calculation needs two values"
            if pairs
            else "This calculation needs two or more values."
        )
    try:
        result, result_unit = _compute(kind, values, years)
    except (ZeroDivisionError, DivisionByZero, InvalidOperation, ValueError) as exc:
        return _err(f"Cannot calculate: {exc}.")
    value = result.quantize(Decimal("0.0001")).normalize()
    en, ar = _FORMULA[kind]
    item = ledger.add(
        {
            "kind": "calculation",
            "calculation": kind,
            "inputs": ids,
            "value": format(value, "f"),
            "unit": result_unit or unit,
            "formula": {"en": en, "ar": ar},
            "label": (label or "")[:120] or None,
            "basis": "web",
        }
    )
    return {"status": "ok", "evidence_id": item["id"], "value": item["value"], "unit": item["unit"]}


def _compute(kind: str, v: list[Decimal], years: int | None) -> tuple[Decimal, str | None]:
    if kind == "percent_change":
        return (v[1] - v[0]) / v[0] * 100, "percent"
    if kind == "cagr":
        if not years or years < 1:
            raise ValueError("give the number of years between the two values")
        if v[0] <= 0 or v[1] <= 0:
            raise ValueError("growth rates need positive values")
        return Decimal(str((math.pow(float(v[1] / v[0]), 1 / years) - 1) * 100)), "percent"
    if kind == "share":
        return v[0] / v[1] * 100, "percent"
    if kind == "difference":
        return v[1] - v[0], None
    if kind == "ratio":
        return v[0] / v[1], None
    if kind == "sum":
        return sum(v, Decimal(0)), None
    if kind == "average":
        return sum(v, Decimal(0)) / len(v), None
    total = sum(v, Decimal(0))  # hhi
    if total <= 0:
        raise ValueError("the values must add up to more than zero")
    return sum(((x / total) * 100) ** 2 for x in v), "index"


def research_table(
    ledger: Any, title: str, columns: list[Any], rows: list[Any], note: str | None = None
) -> dict[str, Any]:
    """A table of web figures: each row cites its evidence; a row whose figures are not in its
    citations (years as labels excepted) is left out and counted."""
    cols = [str(c).strip()[:60] for c in columns if str(c).strip()][:MAX_COLUMNS]
    if len(cols) < 2:
        return _err("A table needs two to six columns.")
    items = ledger.by_id()
    kept: list[dict[str, Any]] = []
    dropped = 0
    for row in rows[:MAX_ROWS]:
        cells = [
            str(c).strip()[:160] for c in (row.get("cells") if isinstance(row, dict) else []) or []
        ]
        cites = (
            [str(c) for c in (row.get("citations") or []) if str(c) in items][:6]
            if isinstance(row, dict)
            else []
        )
        if len(cells) != len(cols):
            dropped += 1
            continue
        allowed = _allowed(cites, items) if cites else set()
        supported = all(
            _is_year(n, d) or (cites and _matches(n, d, allowed))
            for cell in cells
            for n, d in numbers_in(cell)
        )
        if supported:
            kept.append({"cells": cells, "citations": cites})
        else:
            dropped += 1
    if not kept:
        return _err(
            "No row's figures match its cited evidence. Cite the source of each row's figures."
        )
    table_id = f"RT{len(ledger.research_tables) + 1}"
    ledger.research_tables.append(
        {
            "id": table_id,
            "title": str(title).strip()[:160],
            "columns": cols,
            "rows": kept,
            "dropped": dropped,
            "note": (note or "").strip()[:300] or None,
        }
    )
    return {"status": "ok", "table_id": table_id, "rows": len(kept), "dropped": dropped}


def _number(cell: str) -> float | None:
    found = numbers_in(cell)
    if not found:
        return None
    number, _ = found[0]
    return float(-number if cell.strip().startswith(("-", "−")) else number)


def research_chart(
    ledger: Any,
    table_id: str,
    *,
    label_column: int = 0,
    value_columns: list[int] | None = None,
    kind: str = "bar",
    title: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """A bar or line chart of a research table's validated rows (two points or more)."""
    table = next((t for t in ledger.research_tables if t["id"] == table_id), None)
    if table is None:
        return _err(f"No table {table_id} in this answer: make it with research_table first.")
    width = len(table["columns"])
    picked = [
        c
        for c in (value_columns or [1])
        if isinstance(c, int) and 0 <= c < width and c != label_column
    ][:3]
    if not 0 <= label_column < width or not picked:
        return _err("Choose a label column and one to three value columns of the table.")
    labels: list[str] = []
    series = [{"name": table["columns"][c], "values": []} for c in picked]
    for row in table["rows"]:
        numbers = [_number(row["cells"][c]) for c in picked]
        if all(n is None for n in numbers):
            continue
        labels.append(row["cells"][label_column])
        for s, n in zip(series, numbers, strict=True):
            s["values"].append(n)
    if len(labels) < 2:
        return _err("A chart needs two rows or more with figures.")
    chart_id = f"RC{len(ledger.research_charts) + 1}"
    ledger.research_charts.append(
        {
            "id": chart_id,
            "table_id": table_id,
            "kind": kind if kind in ("bar", "line") else "bar",
            "title": (title or table["title"])[:160],
            "unit": (unit or "")[:40] or None,
            "labels": labels,
            "series": series,
        }
    )
    return {"status": "ok", "chart_id": chart_id, "points": len(labels)}


def diagram(
    ledger: Any, kind: str, title: str, nodes: list[Any], edges: list[Any]
) -> dict[str, Any]:
    """A diagram (flowchart, cycle, hierarchy or mind map) of the analysis: labelled nodes and
    links. A figure written on it must be in this answer's evidence."""
    if kind not in DIAGRAM_KINDS:
        return _err(f"Use one of: {', '.join(DIAGRAM_KINDS)}.")
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in nodes[:MAX_NODES]:
        if not isinstance(node, dict):
            continue
        node_id = _SLUG.sub("-", str(node.get("id", "")).lower()).strip("-")[:40]
        label = str(node.get("label", "")).strip()[:80]
        if not node_id or not label or node_id in seen:
            continue
        seen.add(node_id)
        kept.append(
            {
                "id": node_id,
                "label": label,
                "detail": str(node.get("detail") or "").strip()[:140] or None,
            }
        )
    if len(kept) < 2:
        return _err("A diagram needs two or more nodes with an id and a label.")
    links = []
    for edge in edges[:MAX_EDGES]:
        if not isinstance(edge, dict):
            continue
        a = _SLUG.sub("-", str(edge.get("from", "")).lower()).strip("-")
        b = _SLUG.sub("-", str(edge.get("to", "")).lower()).strip("-")
        if a in seen and b in seen and a != b:
            links.append(
                {"from": a, "to": b, "label": str(edge.get("label") or "").strip()[:40] or None}
            )
    items = ledger.by_id()
    allowed = _allowed(list(items), items)
    unsupported = [
        str(n)
        for node in kept
        for text in (node["label"], node["detail"] or "")
        for n, d in numbers_in(text)
        if not _is_year(n, d) and not _matches(n, d, allowed)
    ]
    if unsupported:
        return _err(
            f"Figures not in this answer's evidence: {', '.join(unsupported[:5])}. Remove them or cite them."
        )
    diagram_id = f"D{len(ledger.diagrams) + 1}"
    ledger.diagrams.append(
        {
            "id": diagram_id,
            "kind": kind,
            "title": str(title).strip()[:160],
            "nodes": kept,
            "edges": links,
        }
    )
    return {"status": "ok", "diagram_id": diagram_id, "nodes": len(kept), "links": len(links)}
