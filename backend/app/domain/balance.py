"""The shortage and surplus analysis result (osrip.balance/1): one validated document that the
tables, charts, recommendation table, CSV export, printable report and spoken summary all read.

Rules the validator enforces (beyond the table and chart rules of ``app.domain.study``):

* a balance is "surplus", "shortfall" or "balanced" only with a calculated gap and the
  evidence it rests on; otherwise it is "not_determinable" and must say why;
* every evidence id named by a balance, a recommendation or a data gap exists in ``sources``;
* a recommendation never carries a cost figure: costs are "unknown" unless a cited source
  states them, and quantities are either a calculated value with its unit or explicitly
  "not quantified" with the reason;
* scenario rows are labelled scenario, never observed.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.study import Chart, Table, Text, Unit, check_table_and_charts

SCHEMA = "osrip.balance/1"
SECTORS = ("electricity", "water", "food_security", "trade")
Sector = Literal["electricity", "water", "food_security", "trade"]
BalanceStatus = Literal["surplus", "shortfall", "balanced", "not_determinable"]
# What kind of response a recommendation is. For a shortfall: efficiency, loss reduction,
# redistribution, storage, capacity expansion or supplier diversification; for a surplus:
# storage, local use, redistribution, processing or exports where feasible (never assumed);
# and data improvements and monitoring for either.
OptionKind = Literal[
    "efficiency", "loss_reduction", "redistribution", "storage", "capacity_expansion",
    "supplier_diversification", "local_use", "processing", "export", "data_improvement",
    "monitoring",
]  # fmt: skip
_EV = r"^S\d{1,4}$"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _decimal(value: str | None) -> None:
    if value is not None:
        try:
            Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"not a decimal: {value!r}") from exc


class Source(_M):
    """One published observation an analysis rests on, with its full citation."""

    id: str = Field(pattern=_EV)
    indicator: str
    indicator_name: Text
    area: str
    area_name: Text
    period_start: str
    period_end: str
    period_label: str
    period_kind: str
    value: str | None
    value_operator: str | None = None
    unit: Unit
    publisher: str | None = None
    title: str
    url: str | None = None
    publication: str | None = None  # the publication as recorded in the reference pack
    accessed: str | None = None  # when the source was retrieved
    dataset_version: str
    record_ref: str | None = None
    data_status: Literal["approved_official", "synthetic_demonstration"]
    # Statistics before 2022 are context only and labelled as such.
    older_context: bool = False

    @model_validator(mode="after")
    def _check(self) -> Source:
        _decimal(self.value)
        return self


class Balance(_M):
    """One supply-against-demand comparison (or the reason it cannot be made)."""

    id: str = Field(pattern=r"^B\d{1,3}$")
    code: str
    title: Text
    status: BalanceStatus
    # The words used for the status in this sector (e.g. "trade deficit", "net importer").
    status_label: Text
    reason: Text  # why this status, or why it cannot be determined
    interpretation: Text  # what the gap means and what it does not mean
    period: str | None = None
    period_kind: str | None = None
    gap: str | None = None
    gap_unit: Unit | None = None
    gap_share: str | None = None  # percent of the demand measure, where meaningful
    supply_label: Text | None = None
    demand_label: Text | None = None
    table: Table
    charts: list[Chart] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    constraints: list[Text] = Field(default_factory=list)
    notes: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Balance:
        check_table_and_charts(self.table, self.charts)
        _decimal(self.gap)
        _decimal(self.gap_share)
        if self.status == "not_determinable":
            if self.gap is not None:
                raise ValueError(f"{self.id}: an undetermined balance carries no gap")
        else:
            if self.gap is None or self.gap_unit is None:
                raise ValueError(f"{self.id}: a determined balance needs its gap and unit")
            if not self.evidence:
                raise ValueError(f"{self.id}: a determined balance needs its evidence")
        return self


class Recommendation(_M):
    """One row of the recommendation table (decision support, not a guaranteed outcome)."""

    id: str = Field(pattern=r"^R\d{1,3}$")
    balance: str | None = Field(default=None, pattern=r"^B\d{1,3}$")
    problem: Text
    evidence: Text
    evidence_ids: list[str] = Field(default_factory=list)
    action: Text
    quantity: str | None = None
    quantity_unit: Unit | None = None
    quantity_note: Text  # what the quantity is, or why it is not quantified
    horizon: Literal["short", "medium", "long"]
    constraints: Text
    cost: Text  # "unknown" unless a cited source states it
    cost_known: Literal[False] = False
    outcome: Text  # expected outcome and the assumptions it rests on
    priority: Literal["high", "medium", "low", "conditional"]
    priority_basis: Text
    kpi: Text
    nature: Literal["recommendation", "data_improvement", "conditional_option"]
    option: OptionKind | None = None

    @model_validator(mode="after")
    def _check(self) -> Recommendation:
        _decimal(self.quantity)
        if (self.quantity is None) != (self.quantity_unit is None):
            raise ValueError(f"{self.id}: a quantity needs its unit (and a unit its quantity)")
        return self


class DataGap(_M):
    id: str = Field(pattern=r"^G\d{1,3}$")
    balance: str | None = Field(default=None, pattern=r"^B\d{1,3}$")
    missing: Text  # what is missing
    blocks: Text  # what it prevents
    where: Text | None = None  # who would publish it (never a guessed URL)


class Finding(_M):
    text: Text
    evidence: list[str] = Field(default_factory=list)  # S ids
    balance: str | None = Field(default=None, pattern=r"^B\d{1,3}$")


class NextStudy(_M):
    question: Text
    data: Text  # the information that would answer it
    where: Text | None = None  # who would publish it (never a guessed URL)


class Conclusion(_M):
    """How every study ends: what was found, how far the evidence goes, what to do now and
    later, and what the next study needs."""

    main_findings: list[Finding]
    evidence_limitations: list[Text]
    immediate_actions: list[str] = Field(default_factory=list)  # R ids, short horizon
    medium_term_options: list[str] = Field(default_factory=list)  # R ids, medium or long
    next_study: list[NextStudy] = Field(default_factory=list)


class Scenario(_M):
    status: Literal["ok", "not_applicable", "not_requested"]
    reason: Text | None = None
    assumptions: list[Text] = Field(default_factory=list)
    balance: str | None = None
    table: Table | None = None
    charts: list[Chart] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Scenario:
        if self.status == "ok":
            if self.table is None or not self.table.rows:
                raise ValueError("a scenario needs its rows")
            check_table_and_charts(self.table, self.charts)
            if any(s.nature != "scenario" for c in self.charts for s in c.series):
                raise ValueError("scenario charts may only draw scenario series")
        elif self.reason is None:
            raise ValueError("a scenario that is not shown must say why")
        return self


class Forecast(_M):
    status: Literal["eligible", "withheld", "not_available"]
    indicator: str | None = None
    text: Text


class BalanceAnalysis(_M):
    schema_: Literal["osrip.balance/1"] = Field(default=SCHEMA, alias="schema")
    kind: Literal["supply_balance"] = "supply_balance"
    sector: Sector
    status: Literal["ok", "partial", "not_available"]
    title: Text
    question: Text
    params: dict[str, Any]
    data_mode: Literal["verified_source", "synthetic"]
    dataset_versions: list[str]
    summary: list[Text]
    balances: list[Balance]
    recommendations: list[Recommendation] = Field(default_factory=list)
    prioritization: Text
    data_gaps: list[DataGap] = Field(default_factory=list)
    scenario: Scenario
    forecast: Forecast
    sources: list[Source] = Field(default_factory=list)
    method: Text
    assumptions: list[Text] = Field(default_factory=list)
    limitations: list[Text] = Field(default_factory=list)
    # Present in every analysis built since 2026-10-21 (older stored ones have none).
    conclusion: Conclusion | None = None
    generated_by: Literal["deterministic"] = "deterministic"

    @model_validator(mode="after")
    def _consistent(self) -> BalanceAnalysis:
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source ids")
        known = set(ids)
        balances = {b.id for b in self.balances}
        if len(balances) != len(self.balances):
            raise ValueError("duplicate balance ids")
        for b in self.balances:
            if set(b.evidence) - known:
                raise ValueError(f"{b.id} cites unknown evidence")
        for r in self.recommendations:
            if set(r.evidence_ids) - known:
                raise ValueError(f"{r.id} cites unknown evidence")
            if r.balance is not None and r.balance not in balances:
                raise ValueError(f"{r.id} names an unknown balance")
        for g in self.data_gaps:
            if g.balance is not None and g.balance not in balances:
                raise ValueError(f"{g.id} names an unknown balance")
        if self.conclusion is not None:
            recs = {r.id: r for r in self.recommendations}
            named = self.conclusion.immediate_actions + self.conclusion.medium_term_options
            if set(named) - set(recs):
                raise ValueError("the conclusion names an unknown recommendation")
            for f in self.conclusion.main_findings:
                if set(f.evidence) - known:
                    raise ValueError("a finding cites unknown evidence")
                if f.balance is not None and f.balance not in balances:
                    raise ValueError("a finding names an unknown balance")
            if any(recs[r].horizon != "short" for r in self.conclusion.immediate_actions):
                raise ValueError("immediate actions are short-term recommendations only")
        determined = [b for b in self.balances if b.status != "not_determinable"]
        expected = (
            "ok"
            if determined and len(determined) == len(self.balances)
            else ("partial" if determined else "not_available")
        )
        if self.status != expected:
            raise ValueError(f"status must be {expected!r} for these balances")
        return self


def validate(document: dict[str, Any]) -> dict[str, Any]:
    """Validate an analysis and return it in canonical JSON form."""
    return BalanceAnalysis.model_validate(document).model_dump(mode="json", by_alias=True)
