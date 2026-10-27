"""The versioned study result: one validated object that tables, charts, exports and
spoken summaries all read, so they can never disagree.

Values are decimal strings or None (missing, never zero). Every numeric column carries
its unit. Charts only reference columns of the table and only the permitted kinds (line,
ranked bar, heatmap). Series are labelled observed, calculated, forecast or scenario so a
scenario can never be drawn as an observation.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA = "osrip.study/1"
StudyKind = Literal[
    "trend",
    "growth",
    "compare_regions",
    "seasonal_profile",
    "import_dependence",
    "partner_concentration",
    "data_quality",
    "scenario",
    "forecast_eligibility",
    "programme_assessment",
]
STUDY_KINDS: tuple[str, ...] = StudyKind.__args__  # type: ignore[attr-defined]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Text(_Model):
    en: str
    ar: str


class Unit(_Model):
    code: str
    label_en: str
    label_ar: str


class Column(_Model):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: Text
    kind: Literal["text", "period", "number", "status"]
    unit: Unit | None = None


class Table(_Model):
    columns: list[Column]
    rows: list[dict[str, str | None]]


class ChartSeries(_Model):
    column: str
    label: Text
    nature: Literal["observed", "calculated", "forecast", "scenario"]


STUDY_CHART_TYPES = ("line", "bar", "heatmap")


class Chart(_Model):
    # pie: shares of one series across the x categories; scatter: x is a numeric column and
    # the one series is plotted against it.
    type: Literal["line", "bar", "heatmap", "pie", "scatter"]
    title: Text
    x: str
    series: list[ChartSeries] = Field(default_factory=list)  # line, bar, pie and scatter
    y: str | None = None  # heatmap rows
    value: str | None = None  # heatmap cell values
    unit: Unit | None = None


def check_table_and_charts(table: Table, charts: list[Chart]) -> None:
    """The rules every table and chart obey, wherever they are shown: unique column keys,
    a unit on every numeric column, decimal strings (or None) in numeric cells, no unknown
    columns, and charts that only reference the table's own columns."""
    keys = {c.key for c in table.columns}
    if len(keys) != len(table.columns):
        raise ValueError("duplicate column keys")
    numeric = {c.key for c in table.columns if c.kind == "number"}
    for c in table.columns:
        if c.kind == "number" and c.unit is None:
            raise ValueError(f"numeric column {c.key!r} needs a unit")
    for row in table.rows:
        extra = set(row) - keys
        if extra:
            raise ValueError(f"row has unknown columns {sorted(extra)}")
        for k in numeric & set(row):
            v = row[k]
            if v is not None:
                try:
                    Decimal(v)
                except InvalidOperation as exc:
                    raise ValueError(f"{k!r} is not a decimal: {v!r}") from exc
    for chart in charts:
        refs = [chart.x, *(s.column for s in chart.series), chart.y, chart.value]
        for r in refs:
            if r is not None and r not in keys:
                raise ValueError(f"chart references unknown column {r!r}")
        if chart.type == "heatmap" and not (chart.y and chart.value):
            raise ValueError("a heatmap needs y and value columns")
        if chart.type != "heatmap" and not chart.series:
            raise ValueError("a line or bar chart needs at least one series")
        if chart.type in ("pie", "scatter") and len(chart.series) != 1:
            raise ValueError(f"a {chart.type} chart shows exactly one series")
        if chart.type == "scatter" and chart.x not in numeric:
            raise ValueError("a scatter chart needs a numeric x column")
        if chart.type == "pie":
            values = [row.get(chart.series[0].column) for row in table.rows]
            if any(v is not None and Decimal(v) < 0 for v in values):
                raise ValueError("a pie chart cannot show negative values")


class Card(_Model):
    label: Text
    value: str | None
    unit: Unit | None = None
    period: str | None = None
    nature: Literal["observed", "calculated", "forecast", "scenario"] = "observed"


class Finding(_Model):
    text: Text
    evidence: list[str] = Field(default_factory=list)


class EvidenceRef(_Model):
    id: str
    indicator: str
    area: str
    period_start: str
    period_end: str
    value: str | None
    unit: str
    source_title: str
    source_url: str | None = None
    dataset_version: str
    record_ref: str | None = None


class StudyResult(_Model):
    schema_: Literal["osrip.study/1"] = Field(default=SCHEMA, alias="schema")
    kind: StudyKind
    status: Literal["ok", "not_available", "not_comparable"]
    title: Text
    question: Text
    params: dict[str, Any]
    data_mode: Literal["verified_source", "synthetic"]
    dataset_versions: list[str]
    periods: dict[str, str | None]
    reason: Text | None = None
    findings: list[Finding] = Field(default_factory=list)
    cards: list[Card] = Field(default_factory=list)
    table: Table
    charts: list[Chart] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    method: Text
    assumptions: list[Text] = Field(default_factory=list)
    limitations: list[Text] = Field(default_factory=list)
    next_questions: list[Text] = Field(default_factory=list)
    forecast_evaluation: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> StudyResult:
        check_table_and_charts(self.table, self.charts)
        for chart in self.charts:
            # osrip.study/1 draws lines, bars and heatmaps only (pie and scatter are for
            # uploaded datasets); a new chart type for studies needs a new schema version.
            if chart.type not in STUDY_CHART_TYPES:
                raise ValueError(f"a study chart is line, bar or heatmap, not {chart.type}")
        ids = [e.id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence ids")
        known = set(ids)
        for f in self.findings:
            missing = set(f.evidence) - known
            if missing:
                raise ValueError(f"finding cites unknown evidence {sorted(missing)}")
        if self.status == "ok" and not self.table.rows:
            raise ValueError("an ok study needs at least one table row")
        if self.status != "ok" and self.reason is None:
            raise ValueError("a study that is not ok must say why")
        return self


def validate(document: dict[str, Any]) -> dict[str, Any]:
    """Validate a study document and return it in canonical JSON form."""
    return StudyResult.model_validate(document).model_dump(mode="json", by_alias=True)
