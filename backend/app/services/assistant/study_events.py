"""Live study events (migration 0019): what the person asking sees while the assistant works.

Each real step of an answer becomes one structured event, validated before it is written and
streamed (``GET /assistant/requests/{id}/events``):

* ``study.started``: the study (the request's id), attempt, mode, language and data mode;
* ``stage``: a step actually reached (retrieving data, validating data, calculating, searching
  the web, reading sources, checking numbers and citations);
* ``search`` and ``evidence``: each search outcome and each source as it is retrieved;
* ``dataset``: a table, with the charts drawn from it, built by OSRIP's own tools and checked
  against the same rules as stored studies (units, decimals, columns) before it is sent; a
  table that fails the check is never sent, only a ``warning``;
* ``warning``: a partial failure (a search or a page that failed, a rejected table);
* ``study.completed`` / ``study.cancelled`` / ``study.failed``: the end. Completion carries the
  validated findings, the narration segments generated from those same findings (with the
  dataset rows each one is about), which datasets the answer rests on, the recommendations,
  assumptions and method.

Identifiers keep the stream consistent: ``study_id`` (the request id), ``seq`` (order, and the
resume point after a reconnect), ``result_version`` (raised by every dataset and by completion,
so an older result never replaces a newer one), ``dataset_id`` (D1...), ``evidence_id`` (E1...),
``finding_id`` (F1...) and ``narration_segment_id`` (N1...). Datasets stay *provisional* until
completion names the ones the answer rests on; after a cancellation or failure nothing becomes
final. Nothing here invents a value: every number comes from published observations, OSRIP's
calculations or a scenario the person stated, and stays labelled as such.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select

from app.domain import study as schema
from app.domain.enums import DataMode

log = logging.getLogger("osrip.study_events")

EVENT_TYPES = (
    "study.started", "stage", "search", "evidence", "dataset", "warning",
    "study.completed", "study.cancelled", "study.failed",
)  # fmt: skip
TERMINAL = frozenset({"study.completed", "study.cancelled", "study.failed"})

DataStatus = Literal[
    "approved_official", "synthetic_demonstration", "unreviewed_external", "calculated",
    "model_forecast", "assumption_scenario", "reference",
]  # fmt: skip
_EID = r"^E\d{1,4}$"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Text(_M):
    en: str
    ar: str


# ------------------------------------------------------------------ payloads


class Started(_M):
    attempt: int = Field(ge=1)
    mode: str
    language: Literal["en", "ar"]
    data_mode: Literal["verified_source", "synthetic"]


class Stage(_M):
    stage: str
    label: Text


class Search(_M):
    evidence_id: str = Field(pattern=_EID)
    status: str
    query: str | None = None
    provider: str | None = None
    role: str = "primary"
    display_only: bool = False
    result_count: int | None = None
    error: str | None = None


class SourceRef(_M):
    title: str | None = None
    publisher: str | None = None
    url: str | None = None
    dataset_version: str | None = None
    record_ref: str | None = None


class Evidence(_M):
    evidence_id: str = Field(pattern=_EID)
    kind: Literal[
        "observation", "web", "note", "calculation", "method", "forecast", "scenario", "study"
    ]
    data_status: DataStatus
    title: Text
    area: Text | None = None
    period_start: str | None = None
    period_end: str | None = None
    value: str | None = None
    value_operator: str | None = None
    unit: Text | None = None
    source: SourceRef | None = None
    source_class: str | None = None
    published: str | None = None
    retrieved_at: str | None = None
    freshness: str | None = None
    content_kind: str | None = None
    summary_by: str | None = None
    excerpt: str | None = None
    inputs: list[str] = Field(default_factory=list)
    status: str | None = None  # a study's or a calculation's outcome (ok, not_available, ...)


class RowMeta(_M):
    row_id: str = Field(pattern=r"^r\d{1,4}$")
    evidence_id: str | None = Field(default=None, pattern=_EID)


class StudyNotes(_M):
    kind: str
    status: str
    reason: Text | None = None
    findings: list[Text] = Field(default_factory=list)
    method: Text
    assumptions: list[Text] = Field(default_factory=list)
    limitations: list[Text] = Field(default_factory=list)


class Dataset(_M):
    """One validated table and the charts drawn from exactly its rows."""

    dataset_id: str = Field(pattern=r"^D\d{1,3}$")
    origin: Literal[
        "get_observations",
        "latest_period",
        "compare_areas",
        "run_study",
        "scenario_projection",
        "balance_analysis",
    ]
    provisional: bool = True
    data_status: DataStatus
    title: Text
    subtitle: Text | None = None
    table: schema.Table
    charts: list[schema.Chart] = Field(default_factory=list)
    rows_meta: list[RowMeta]
    evidence_ids: list[str] = Field(default_factory=list)
    # The evidence item a study dataset came from (a citation of it targets the whole table).
    source_evidence_id: str | None = Field(default=None, pattern=_EID)
    study: StudyNotes | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Dataset:
        schema.check_table_and_charts(self.table, self.charts)
        if len(self.rows_meta) != len(self.table.rows):
            raise ValueError("every row needs its row id")
        ids = [m.row_id for m in self.rows_meta]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate row ids")
        if not self.table.rows:
            raise ValueError("a dataset needs at least one row")
        return self


class Warning_(_M):
    code: Literal[
        "search_failed",
        "tool_error",
        "page_unreadable",
        "dataset_rejected",
        "withheld",
        "no_evidence",
    ]
    detail: Text
    evidence_id: str | None = Field(default=None, pattern=_EID)


class Finding(_M):
    finding_id: str = Field(pattern=r"^F\d{1,3}$")
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class Target(_M):
    dataset_id: str = Field(pattern=r"^D\d{1,3}$")
    row_ids: list[str] = Field(default_factory=list)  # empty: the whole table


class Segment(_M):
    narration_segment_id: str = Field(pattern=r"^N\d{1,3}$")
    finding_id: str | None = None
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    targets: list[Target] = Field(default_factory=list)
    section: Literal["findings", "status"]


class Recommendation(_M):
    finding: str
    action: str
    expected_benefit: str
    uncertainty: str
    citations: list[str] = Field(default_factory=list)


class Completed(_M):
    status: str
    message_id: int | None = None
    language: Literal["en", "ar"]
    findings: list[Finding]
    narration: list[Segment]
    final_datasets: list[str]
    provisional_datasets: list[str]
    recommendations: list[Recommendation] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    method: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> Completed:
        findings = {f.finding_id for f in self.findings}
        datasets = set(self.final_datasets) | set(self.provisional_datasets)
        for s in self.narration:
            if s.finding_id is not None and s.finding_id not in findings:
                raise ValueError(f"segment {s.narration_segment_id} names an unknown finding")
            for t in s.targets:
                if t.dataset_id not in datasets:
                    raise ValueError(f"segment {s.narration_segment_id} targets an unknown dataset")
        return self


class Cancelled_(_M):
    reason: Literal["requested"] = "requested"


class Failed(_M):
    code: str


PAYLOADS: dict[str, type[_M]] = {
    "study.started": Started,
    "stage": Stage,
    "search": Search,
    "evidence": Evidence,
    "dataset": Dataset,
    "warning": Warning_,
    "study.completed": Completed,
    "study.cancelled": Cancelled_,
    "study.failed": Failed,
}
assert set(PAYLOADS) == set(EVENT_TYPES)


# ------------------------------------------------------------------ helpers


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _text(value: Any, fallback: str = "") -> dict[str, str]:
    if isinstance(value, dict) and "en" in value:
        return {
            "en": str(value.get("en") or fallback),
            "ar": str(value.get("ar") or value.get("en") or fallback),
        }
    v = str(value or fallback)
    return {"en": v, "ar": v}


def period_label(kind: str | None, start: str, end: str) -> str:
    """How a period is shown in a table and on a chart axis (no locale needed)."""
    if kind == "annual" and start[5:] == "01-01":
        return start[:4]
    if kind == "monthly":
        return start[:7]
    if kind == "quarterly":
        return f"{start[:4]} Q{(int(start[5:7]) - 1) // 3 + 1}"
    return f"{start} – {end}"


def _unit(code: str | None, label: Any) -> dict[str, str]:
    lab = _text(label, code or "")
    return {"code": code or "unspecified", "label_en": lab["en"], "label_ar": lab["ar"]}


def evidence_view(item: dict[str, Any]) -> dict[str, Any] | None:
    """The public, compact form of a ledger item for the evidence panel (None: not shown)."""
    kind = item.get("kind")
    base: dict[str, Any] = {
        "evidence_id": item["id"],
        "kind": kind,
        "data_status": item.get("data_status", "reference"),
    }
    if kind == "observation":
        src = item.get("source") or {}
        return {
            **base,
            "title": _text(item.get("indicator_name"), item.get("indicator", "")),
            "area": _text(item.get("area_name"), item.get("area", "")),
            "period_start": item.get("period_start"),
            "period_end": item.get("period_end"),
            "value": item.get("value"),
            "value_operator": item.get("value_operator"),
            "unit": _text(item.get("unit_label"), item.get("unit", "")),
            "source": {
                "title": src.get("title"),
                "publisher": src.get("publisher"),
                "url": src.get("url"),
                "dataset_version": item.get("dataset_version"),
                "record_ref": item.get("record_ref"),
            },
        }
    if kind == "web":
        publisher = item.get("publisher")
        return {
            **base,
            "title": _text(item.get("title"), item.get("host", "")),
            "source": {
                "title": item.get("title") if isinstance(item.get("title"), str) else None,
                "publisher": _text(publisher)["en"] if publisher else None,
                "url": item.get("url"),
            },
            "source_class": item.get("source_class"),
            "published": item.get("published"),
            "retrieved_at": item.get("retrieved_at"),
            "freshness": item.get("freshness"),
            "content_kind": item.get("content_kind"),
            "summary_by": item.get("summary_by"),
            # Untrusted page text: shown as plain text only, never interpreted.
            "excerpt": str(item.get("text") or "")[:400] or None,
        }
    if kind == "note":
        return {
            **base,
            "title": _text(item.get("title")),
            "excerpt": str(item.get("text") or "")[:400] or None,
        }
    if kind == "calculation":
        return {
            **base,
            "title": _text(item.get("formula"), str(item.get("calculation", ""))),
            "value": item.get("value"),
            "unit": _text(item.get("unit") or "") if item.get("unit") else None,
            "inputs": [str(i) for i in item.get("inputs") or []],
        }
    if kind == "method":
        return {**base, "title": _text(item.get("formula"), str(item.get("calculation", "")))}
    if kind == "forecast":
        return {**base, "title": _text(item.get("label"), str(item.get("indicator", ""))),
                "unit": _text(item.get("unit") or "") if item.get("unit") else None}  # fmt: skip
    if kind == "scenario":
        return {**base, "title": _text(item.get("label"), str(item.get("indicator", ""))),
                "inputs": [str(i) for i in item.get("inputs") or []]}  # fmt: skip
    if kind == "study":
        return {**base, "title": _text(item.get("title")), "status": item.get("status")}
    return None  # definitions (catalogue noise), search records, display-only grounded results


# ------------------------------------------------------------------ datasets from tool results

_STATUS_COL = {"key": "status", "label": {"en": "Status", "ar": "الحالة"}, "kind": "status"}
_RECORD_COL = {"key": "record", "label": {"en": "Record", "ar": "السجل"}, "kind": "text"}


def _value_text(value: Any, operator: Any) -> str | None:
    # A value with an operator (">95") stays visibly an operator value in the table; the
    # numeric cell holds the published number only.
    return None if value is None else str(value)


def observations_datasets(
    output: dict[str, Any], by_id: dict[str, dict[str, Any]], data_mode: DataMode
) -> list[dict[str, Any]]:
    """One dataset per series (never two units or period kinds in one table)."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for o in output.get("observations") or []:
        key = (o.get("indicator"), o.get("area"), o.get("unit"), o.get("period_kind"),
               o.get("flow"), o.get("commodity"), o.get("partner"))  # fmt: skip
        groups.setdefault(key, []).append(o)
    status = (
        "approved_official" if data_mode is DataMode.VERIFIED_SOURCE else "synthetic_demonstration"
    )
    out = []
    for (_indicator, _area, unit_code, kind, *_rest), rows in groups.items():
        first = by_id.get(rows[0]["id"], {})
        unit = _unit(unit_code, first.get("unit_label"))
        name = _text(first.get("indicator_name"), str(_indicator))
        area = _text(first.get("area_name"), str(_area))
        rows = sorted(rows, key=lambda r: r["period_start"])
        table_rows = [
            {
                "period": period_label(kind, r["period_start"], r["period_end"]),
                "value": _value_text(r.get("value"), r.get("value_operator")),
                "status": "published" if r.get("value") is not None else "missing_in_source",
                "record": r["id"],
            }
            for r in rows
        ]
        charts = []
        if sum(1 for r in table_rows if r["value"] is not None) >= 2:
            charts.append({
                "type": "line",
                "title": name,
                "x": "period",
                "series": [{"column": "value", "label": name, "nature": "observed"}],
                "unit": unit,
            })  # fmt: skip
        out.append({
            "origin": "get_observations",
            "data_status": status,
            "title": name,
            "subtitle": area,
            "table": {
                "columns": [
                    {"key": "period", "label": {"en": "Period", "ar": "الفترة"}, "kind": "period"},
                    {"key": "value", "label": name, "kind": "number", "unit": unit},
                    _STATUS_COL,
                    _RECORD_COL,
                ],
                "rows": table_rows,
            },
            "charts": charts,
            "row_evidence": [r["id"] for r in rows],
        })  # fmt: skip
    return out


def latest_dataset(
    output: dict[str, Any], by_id: dict[str, dict[str, Any]], data_mode: DataMode
) -> list[dict[str, Any]]:
    latest = [r for r in output.get("latest_by_series") or [] if r.get("id")]
    if not latest:
        return []
    found = observations_datasets(
        {"observations": [{**by_id.get(r["id"], {}), **r} for r in latest]}, by_id, data_mode
    )
    return [{**d, "origin": "latest_period"} for d in found]


def areas_dataset(
    output: dict[str, Any], by_id: dict[str, dict[str, Any]], data_mode: DataMode
) -> list[dict[str, Any]]:
    """Each governorate's own value (comparable comparisons only; totals never divided)."""
    if output.get("status") != "ok" or not output.get("rows"):
        return []
    meta = output.get("unit") or {}
    unit = {"code": meta.get("code", "unspecified"), "label_en": meta.get("label_en", meta.get("code", "")),
            "label_ar": meta.get("label_ar", meta.get("code", ""))}  # fmt: skip
    name = _text(output.get("indicator_name"), str(output.get("indicator", "")))
    period = period_label(
        output.get("period_kind"), output.get("period_start") or "", output.get("period_end") or ""
    )
    rows = output["rows"]
    table_rows = [
        {"area": r["name"]["en"], "area_ar": r["name"]["ar"], "value": _value_text(r.get("value"), r.get("value_operator")),
         "status": r.get("status"), "record": r.get("evidence_id")}
        for r in rows
    ]  # fmt: skip
    charts = []
    if sum(1 for r in table_rows if r["value"] is not None) >= 2:
        charts.append({"type": "bar", "title": name, "x": "area",
                       "series": [{"column": "value", "label": name, "nature": "observed"}], "unit": unit})  # fmt: skip
    status = (
        "approved_official" if data_mode is DataMode.VERIFIED_SOURCE else "synthetic_demonstration"
    )
    return [{
        "origin": "compare_areas",
        "data_status": status,
        "title": name,
        "subtitle": {"en": f"Governorates, {period}", "ar": f"المحافظات، {period}"},
        "table": {
            "columns": [
                {"key": "area", "label": {"en": "Governorate", "ar": "المحافظة"}, "kind": "text"},
                {"key": "area_ar", "label": {"en": "Governorate (Arabic)", "ar": "المحافظة"}, "kind": "text"},
                {"key": "value", "label": name, "kind": "number", "unit": unit},
                _STATUS_COL,
                _RECORD_COL,
            ],
            "rows": table_rows,
        },
        "charts": charts,
        "row_evidence": [r.get("evidence_id") for r in rows],
    }]  # fmt: skip


def study_dataset(output: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """A deterministic study's own validated table and charts (unchanged)."""
    item = by_id.get(str(output.get("evidence_id", "")))
    if not item or item.get("kind") != "study":
        return []
    doc = item["study"]
    if not doc["table"]["rows"]:
        return []
    return [{
        "origin": "run_study",
        "data_status": "calculated",
        "title": doc["title"],
        "subtitle": doc["question"],
        "table": doc["table"],
        "charts": doc["charts"],
        "row_evidence": [None] * len(doc["table"]["rows"]),
        "source_evidence_id": item["id"],
        "study": {
            "kind": doc["kind"],
            "status": doc["status"],
            "reason": doc.get("reason"),
            "findings": [f["text"] for f in doc["findings"]],
            "method": doc["method"],
            "assumptions": doc["assumptions"],
            "limitations": doc["limitations"],
        },
    }]  # fmt: skip


def balance_datasets(
    output: dict[str, Any], by_id: dict[str, dict[str, Any]], data_mode: DataMode
) -> list[dict[str, Any]]:
    """Each balance of a shortage and surplus analysis with its own validated table and charts."""
    item = by_id.get(str(output.get("evidence_id", "")))
    if (
        not item
        or item.get("kind") != "study"
        or (item.get("study") or {}).get("kind") != "supply_balance"
    ):
        return []
    doc = item["study"]
    observed = (
        "approved_official" if data_mode is DataMode.VERIFIED_SOURCE else "synthetic_demonstration"
    )
    out = []
    for b in doc["balances"]:
        if not b["table"]["rows"]:
            continue
        out.append({
            "origin": "balance_analysis",
            "data_status": observed if b["status"] == "not_determinable" else "calculated",
            "title": b["title"],
            "subtitle": b["status_label"],
            "table": b["table"],
            "charts": b["charts"],
            "row_evidence": [None] * len(b["table"]["rows"]),
            "source_evidence_id": item["id"],
            "study": {
                "kind": "supply_balance",
                "status": b["status"],
                "reason": b["reason"],
                "findings": [b["interpretation"]],
                "method": doc["method"],
                "assumptions": doc["assumptions"],
                "limitations": doc["limitations"],
            },
        })  # fmt: skip
    return out


def scenario_dataset(
    output: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """The arithmetic of the person's own assumption: labelled scenario, never observed."""
    item = by_id.get(str(output.get("evidence_id", "")))
    base = by_id.get(str(output.get("base", "")))
    if not item or not base or not output.get("points"):
        return []
    unit = _unit(base.get("unit"), base.get("unit_label"))
    name = _text(base.get("indicator_name"), str(item.get("indicator", "")))
    label = {"en": f"{name['en']} (scenario)", "ar": f"{name['ar']} (سيناريو)"}
    rows = [{"period": base["period_start"][:4], "value": base.get("value"), "nature": "base"}] + [
        {"period": str(p["year"]), "value": p["value"], "nature": "scenario"}
        for p in output["points"]
    ]
    return [{
        "origin": "scenario_projection",
        "data_status": "assumption_scenario",
        "title": label,
        "subtitle": _text(item.get("label")),
        "table": {
            "columns": [
                {"key": "period", "label": {"en": "Year", "ar": "السنة"}, "kind": "period"},
                {"key": "value", "label": label, "kind": "number", "unit": unit},
                {"key": "nature", "label": {"en": "Basis", "ar": "الأساس"}, "kind": "text"},
            ],
            "rows": rows,
        },
        "charts": [{"type": "line", "title": label, "x": "period",
                    "series": [{"column": "value", "label": label, "nature": "scenario"}], "unit": unit}],
        "row_evidence": [base["id"]] + [item["id"]] * len(output["points"]),
        "source_evidence_id": item["id"],
    }]  # fmt: skip


BUILDERS = {
    "get_observations": lambda out, by_id, mode: observations_datasets(out, by_id, mode),
    "latest_period": lambda out, by_id, mode: latest_dataset(out, by_id, mode),
    "compare_areas": lambda out, by_id, mode: areas_dataset(out, by_id, mode),
    "run_study": lambda out, by_id, mode: study_dataset(out, by_id),
    "scenario_projection": lambda out, by_id, mode: scenario_dataset(out, by_id),
    "balance_analysis": lambda out, by_id, mode: balance_datasets(out, by_id, mode),
}


# ------------------------------------------------------------------ findings and narration

_MARKER = re.compile(r"\[(E\d{1,4})\]")
# Sentence ends: punctuation followed by space or the end, or a line break. A decimal point
# ("41234.5") is never followed by a space, so numbers are never split.
_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+|\n+")


def split_findings(text: str) -> list[dict[str, Any]]:
    """The reply's validated text, one finding per sentence, each with the evidence it cites."""
    out: list[dict[str, Any]] = []
    for paragraph in re.split(r"\n+", text or ""):
        sentences = [
            s.strip() for s in _SENTENCE_END.split(paragraph) if s.strip() and re.search(r"\w", s)
        ]
        own = [list(dict.fromkeys(_MARKER.findall(s))) for s in sentences]
        for i, sentence in enumerate(sentences):
            # A citation covers its paragraph (the evidence check allows that): a sentence
            # without its own marker takes the next cited sentence's evidence, else the last.
            ids = (
                own[i]
                or next((o for o in own[i + 1 :] if o), None)
                or next((o for o in reversed(own[:i]) if o), [])
            )
            out.append({"finding_id": f"F{len(out) + 1}", "text": sentence, "evidence_ids": ids})
    return out


def speakable(text: str) -> str:
    """A sentence as it is spoken: evidence markers are not read."""
    return re.sub(r"\s+", " ", _MARKER.sub("", text)).replace(" .", ".").strip()


def narration_for(
    findings: list[dict[str, Any]], datasets: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """One narration segment per finding (the spoken explanation is generated from the same
    findings the panel shows), with the dataset rows each one is about."""
    segments = []
    for f in findings:
        targets = []
        for ds_id, ds in datasets.items():
            rows = [
                m["row_id"] for m in ds["rows_meta"] if m.get("evidence_id") in f["evidence_ids"]
            ]
            whole = ds.get("source_evidence_id") in f["evidence_ids"]
            if rows or whole:
                targets.append({"dataset_id": ds_id, "row_ids": [] if whole and not rows else rows})
        segments.append({
            "narration_segment_id": f"N{len(segments) + 1}",
            "finding_id": f["finding_id"],
            "text": speakable(f["text"]),
            "evidence_ids": f["evidence_ids"],
            "targets": targets,
            "section": "findings",
        })  # fmt: skip
    return segments


# ------------------------------------------------------------------ the stream


@dataclass
class StudyStream:
    """Writes one study's events, each validated and in its own short transaction, so the
    stream endpoint can read it at once. Without a request (tests, the voice bridge without an
    id) events are kept in memory only."""

    request_pk: int | None
    study_id: str
    conversation_id: uuid.UUID | None = None
    language: str = "en"
    data_mode: DataMode = DataMode.SYNTHETIC
    seq: int | None = None
    version: int = 0
    datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_ids: set[str] = field(default_factory=set)
    events: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    # -------------------------------------------------------------- writing
    def _next_seq(self) -> int:
        if self.seq is None:
            self.seq = 0
            if self.request_pk is not None:
                from app.db.session import session_factory
                from app.models import StudyEvent

                with session_factory()() as s, s.begin():
                    self.seq = int(
                        s.scalar(select(func.coalesce(func.max(StudyEvent.seq), 0))
                                 .where(StudyEvent.request_id == self.request_pk)) or 0
                    )  # fmt: skip
        self.seq += 1
        return self.seq

    def emit(
        self, type_: str, payload: dict[str, Any], *, bump: bool = False
    ) -> dict[str, Any] | None:
        """Validate and write one event; an invalid payload is never written."""
        if self.closed:
            return None  # nothing follows the end of a study
        data = PAYLOADS[type_].model_validate(payload).model_dump(mode="json", by_alias=True)
        if bump:
            self.version += 1
        event = {
            "study_id": self.study_id,
            "seq": self._next_seq(),
            "type": type_,
            "result_version": self.version,
            "at": _now(),
            "payload": data,
        }
        self.events.append(event)
        if self.request_pk is not None:
            from app.db.session import session_factory
            from app.models import StudyEvent

            with session_factory()() as s, s.begin():
                s.add(StudyEvent(
                    request_id=self.request_pk, conversation_id=self.conversation_id,
                    study_id=uuid.UUID(self.study_id), seq=event["seq"], type=type_,
                    result_version=self.version, payload=data,
                ))  # fmt: skip
        if type_ in TERMINAL:
            self.closed = True
        return event

    def warn(self, code: str, en: str, ar: str, evidence_id: str | None = None) -> None:
        self.emit(
            "warning", {"code": code, "detail": {"en": en, "ar": ar}, "evidence_id": evidence_id}
        )

    # -------------------------------------------------------------- hooks
    def started(self, *, attempt: int, mode: str) -> None:
        self.emit("study.started", {"attempt": attempt, "mode": mode, "language": self.language,
                                    "data_mode": self.data_mode.value})  # fmt: skip

    def stage(self, name: str, label: dict[str, str]) -> None:
        self.emit("stage", {"stage": name, "label": label})

    def on_evidence(self, item: dict[str, Any]) -> None:
        """Called by the ledger for every item it records."""
        try:
            if item.get("kind") == "search":
                self.emit("search", {
                    "evidence_id": item["id"], "status": str(item.get("status", "")),
                    "query": item.get("query"), "provider": item.get("provider"),
                    "role": item.get("role") or "primary", "display_only": bool(item.get("display_only")),
                    "result_count": item.get("result_count"), "error": item.get("error"),
                })  # fmt: skip
                if item.get("status") not in ("ok", "no_results"):
                    self.warn("search_failed", "A web search failed; the study continues with the other sources.",
                              "تعذّر بحث في الإنترنت؛ تستمر الدراسة بالمصادر الأخرى.", item["id"])  # fmt: skip
                return
            view = evidence_view(item)
            if view is not None:
                self.emit("evidence", view)
                self.evidence_ids.add(item["id"])
        except ValidationError:
            log.warning("evidence event rejected for %s", item.get("id"))

    def on_tool(
        self, name: str, output: dict[str, Any], by_id: dict[str, dict[str, Any]], tracker: Any
    ) -> None:
        """After a tool ran: a partial failure, or validated datasets from its result."""
        if not isinstance(output, dict):
            return
        if output.get("error"):
            self.warn("tool_error", "One step could not be completed; the study continues without it.",
                      "تعذّر إكمال خطوة واحدة؛ تستمر الدراسة دونها.")  # fmt: skip
            return
        if name == "read_web_page" and output.get("status") not in (None, "ok"):
            self.warn("page_unreadable", "A source page could not be read; only its search snippet is used.",
                      "تعذّرت قراءة صفحة مصدر؛ يُستخدم مقتطف البحث فقط.")  # fmt: skip
            return
        builder = BUILDERS.get(name)
        if builder is None:
            return
        candidates = builder(output, by_id, self.data_mode)
        if not candidates:
            return
        tracker.stage("validating_data")
        for c in candidates:
            self.dataset(c)

    def dataset(self, candidate: dict[str, Any]) -> str | None:
        ds_id = f"D{len(self.datasets) + 1}"
        row_evidence = candidate.pop("row_evidence", [])
        payload = {
            **candidate,
            "dataset_id": ds_id,
            "provisional": True,
            "rows_meta": [{"row_id": f"r{i + 1}", "evidence_id": e} for i, e in enumerate(row_evidence)],
            "evidence_ids": sorted({e for e in row_evidence if e} | (
                {candidate["source_evidence_id"]} if candidate.get("source_evidence_id") else set())),
        }  # fmt: skip
        try:
            event = self.emit("dataset", payload, bump=True)
        except ValidationError as exc:
            log.warning("dataset rejected: %s", str(exc)[:300])
            self.warn("dataset_rejected", "A table failed validation and is not shown.",
                      "لم يجتز جدول التحقق ولذلك لا يُعرض.")  # fmt: skip
            return None
        if event is not None:
            self.datasets[ds_id] = event["payload"]
        return ds_id

    # -------------------------------------------------------------- the end
    def finish(self, reply: Any, message_id: int | None) -> None:
        """Completion (with findings and narration from the stored, validated reply), or the
        cancellation or failure the reply records."""
        if self.closed:
            return
        status = str(reply.status)
        if status == "cancelled":
            self.emit("study.cancelled", {"reason": "requested"})
            return
        if status == "unavailable":
            self.emit("study.failed", {"code": "unavailable"})
            return
        if status == "unverified":
            self.warn("withheld", "The answer was withheld: a figure was not supported by its sources.",
                      "حُجبت الإجابة: رقم غير مدعوم بمصادره.")  # fmt: skip
        findings = (
            split_findings(reply.content)
            if status in ("answered", "no_evidence", "clarification")
            else []
        )
        cited = set(reply.citations or [])
        if status == "answered":
            final = [d for d, ds in self.datasets.items()
                     if (set(ds["evidence_ids"]) & cited)]  # fmt: skip
        else:
            final = []  # a withheld, empty or unanswerable reply confirms nothing
        narration = narration_for(findings, {d: self.datasets[d] for d in self.datasets})
        if not narration:
            narration = [{"narration_segment_id": "N1", "finding_id": None,
                          "text": speakable(reply.content), "evidence_ids": [], "targets": [],
                          "section": "status"}]  # fmt: skip
        structured = reply.structured or {}
        payload = {
            "status": status,
            "message_id": message_id,
            "language": "ar" if self.language == "ar" else "en",
            "findings": findings,
            "narration": narration,
            "final_datasets": final,
            "provisional_datasets": [d for d in self.datasets if d not in final],
            "recommendations": [
                {
                    k: (r.get(k) if k == "citations" else str(r.get(k, "")))
                    for k in ("finding", "action", "expected_benefit", "uncertainty", "citations")
                }
                for r in structured.get("recommendations") or []
            ],  # fmt: skip
            "assumptions": [
                str(a.get("statement", "")) for a in structured.get("assumptions") or []
            ],
            "method": structured.get("method") or {},
        }
        self.emit("study.completed", payload, bump=True)


# ------------------------------------------------------------------ reading (stream endpoint)


def find_request(
    request_id: uuid.UUID, user_id: uuid.UUID | None, guest_session_id: uuid.UUID | None
) -> tuple[int | None, str | None]:
    """The caller's own request (its key and state), or (None, None): another person's
    request is never found."""
    from app.db.session import session_factory
    from app.models import AssistantRequest

    if (user_id is None) == (guest_session_id is None):
        return None, None
    owner = (
        AssistantRequest.user_id == user_id
        if user_id is not None
        else AssistantRequest.guest_session_id == guest_session_id
    )
    with session_factory()() as s, s.begin():
        row = s.execute(
            select(AssistantRequest.id, AssistantRequest.state).where(
                owner, AssistantRequest.idempotency_key == request_id
            )
        ).first()
    return (row[0], row[1]) if row else (None, None)


def read_after(
    request_pk: int, after: int, limit: int = 200
) -> tuple[list[dict[str, Any]], str | None]:
    """Events after ``seq`` (in order) and the request's current state."""
    from app.db.session import session_factory
    from app.models import AssistantRequest, StudyEvent

    with session_factory()() as s, s.begin():
        rows = s.scalars(
            select(StudyEvent)
            .where(StudyEvent.request_id == request_pk, StudyEvent.seq > after)
            .order_by(StudyEvent.seq)
            .limit(limit)
        ).all()
        state = s.scalar(select(AssistantRequest.state).where(AssistantRequest.id == request_pk))
        return [public(r) for r in rows], state


def public(event: Any) -> dict[str, Any]:
    """A stored event as sent to the client."""
    return {
        "study_id": str(event.study_id),
        "seq": event.seq,
        "type": event.type,
        "result_version": event.result_version,
        "at": event.created_at.isoformat() if event.created_at else None,
        "payload": event.payload,
    }
