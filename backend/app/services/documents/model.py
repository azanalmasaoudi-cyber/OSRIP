"""The report document (osrip.report/1): one structure for the page, PDF, Excel and CSV.

A report is frozen when it is created: its text, tables, chart tables and references are
stored as they were. Tables hold text cells exactly as computed or read (decimal strings
for numbers, None for missing); a chart is a validated study chart over its own table, so
every drawn value is a value in the report.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.study import Chart, Table, check_table_and_charts

SCHEMA = "osrip.report/1"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Paragraph(_Model):
    type: Literal["paragraph"] = "paragraph"
    text: str
    note: bool = False  # a smaller, muted line (method notes, labels)


class Bullets(_Model):
    type: Literal["bullets"] = "bullets"
    items: list[str]


class TableColumn(_Model):
    label: str
    numeric: bool = False


class TableBlock(_Model):
    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[TableColumn]
    rows: list[list[str | None]]
    note: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> TableBlock:
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("every table row has one cell per column")
        return self


class ChartBlock(_Model):
    type: Literal["chart"] = "chart"
    title: str
    table: Table
    chart: Chart
    note: str | None = None

    @model_validator(mode="after")
    def _valid(self) -> ChartBlock:
        check_table_and_charts(self.table, [self.chart])
        return self


Block = Annotated[Paragraph | Bullets | TableBlock | ChartBlock, Field(discriminator="type")]


class Section(_Model):
    heading: str
    blocks: list[Block] = Field(default_factory=list)


class Reference(_Model):
    title: str
    url: str | None = None
    publisher: str | None = None
    published: str | None = None
    retrieved: str | None = None
    note: str | None = None


class Document(_Model):
    schema_: Literal["osrip.report/1"] = Field(default=SCHEMA, alias="schema")
    kind: Literal["research", "dataset", "platform"]
    language: Literal["en", "ar"]
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = None
    created_at: str
    meta: list[tuple[str, str]] = Field(default_factory=list)
    sections: list[Section]
    references: list[Reference] = Field(default_factory=list)
    notice: str | None = None


def validate(document: dict[str, Any]) -> dict[str, Any]:
    """A report document in canonical JSON form (raises ValidationError when malformed)."""
    return Document.model_validate(document).model_dump(mode="json", by_alias=True)
