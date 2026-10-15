"""Row- and file-level validation of an import (booklet 3.2, 3.3; FR01, T04, T09).

Pure: takes parsed rows, a confirmed column mapping, a snapshot of reference data
and the source's data mode, and returns one result per row. No database access,
so every rule is unit-tested directly.

Each problem is an Issue with a stable ``code``, the affected canonical field, the
original value and a plain explanation. Severity ``error`` rejects the row (kept in
the error report, never published); ``warning`` publishes the row and records why.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import (
    DataMode,
    Frequency,
    QualityStatus,
    RevisionStatus,
    RowOutcome,
    TradeFlow,
)

# ------------------------------------------------------------------ canonical fields

REQUIRED_FIELDS = (
    "indicator_code",
    "area_code",
    "period_start",
    "period_end",
    "frequency",
    "unit_code",
    "value",
)
OPTIONAL_FIELDS = (
    "period_complete",
    "commodity_code",
    "partner_code",
    "flow",
    "quality_status",
    "valuation_basis",
    "source_reference",
    # Reference-pack provenance (migration 0009).
    "record_ref",
    "revision_status",
    "value_operator",
    "source_locator",
    "statement_date",
    "note",
)
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

FREQUENCY_MONTHS = {Frequency.ANNUAL: 12, Frequency.QUARTERLY: 3, Frequency.MONTHLY: 1}
VALUE_OPERATORS = {">", ">=", "<", "<=", "~"}
# Measures whose values may be negative (a stock can fall; a published balance can be a deficit).
SIGNED_MEASURES = {"stock_increase", "balance"}
TRUE_WORDS = {"true", "yes", "1", "y"}
FALSE_WORDS = {"false", "no", "0", "n"}


# First period of the platform's verified-source statistics (build brief: January 2022 onward).
STATISTICAL_SCOPE_START = date(2022, 1, 1)


def suggest_mapping(header: list[str]) -> dict[str, str]:
    """Map columns whose names equal a canonical field (case/space-insensitive)."""
    by_key = {h.strip().lower().replace(" ", "_"): h for h in header}
    return {f: by_key[f] for f in ALL_FIELDS if f in by_key}


def check_mapping(mapping: dict[str, str], header: list[str]) -> list[str]:
    """Problems with a column mapping; empty when it can be used."""
    problems = []
    unknown_fields = sorted(set(mapping) - set(ALL_FIELDS))
    if unknown_fields:
        problems.append(f"Unknown target fields: {', '.join(unknown_fields)}.")
    missing = [f for f in REQUIRED_FIELDS if not mapping.get(f)]
    if missing:
        problems.append(f"Required fields are not mapped: {', '.join(missing)}.")
    absent = sorted({c for c in mapping.values() if c and c not in header})
    if absent:
        problems.append(f"Mapped columns are not in the file: {', '.join(absent)}.")
    used = [c for c in mapping.values() if c]
    reused = sorted({c for c in used if used.count(c) > 1})
    if reused:
        problems.append(f"A column may be mapped to only one field: {', '.join(reused)}.")
    return problems


# ------------------------------------------------------------------ reference snapshot


@dataclass(frozen=True, slots=True)
class IndicatorRef:
    id: str
    dimension: str
    measure: str
    requires_commodity: bool
    requires_flow: bool


@dataclass(frozen=True, slots=True)
class UnitRef:
    id: str
    dimension: str


@dataclass(frozen=True, slots=True)
class AreaRef:
    id: str
    valid_from: date | None
    valid_to: date | None


@dataclass(frozen=True, slots=True)
class CommodityRef:
    id: str
    mapping_status: str
    synthetic_only: bool
    quantity_unit_code: str


@dataclass(frozen=True, slots=True)
class PartnerRef:
    id: str
    is_fictional: bool


@dataclass(frozen=True, slots=True)
class Reference:
    indicators: dict[str, IndicatorRef]
    units: dict[str, UnitRef]
    areas: dict[str, AreaRef]
    commodities: dict[str, CommodityRef]
    partners: dict[str, PartnerRef]


# ------------------------------------------------------------------ results


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: str  # 'error' | 'warning'
    field: str | None
    value: str | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "value": self.value,
            "message": self.message,
        }


@dataclass(slots=True)
class RowResult:
    row_number: int
    raw: dict[str, str]
    issues: list[Issue] = field(default_factory=list)
    normalized: dict[str, Any] | None = None

    @property
    def outcome(self) -> RowOutcome:
        if any(i.severity == "error" for i in self.issues):
            return RowOutcome.REJECTED
        if self.issues:
            return RowOutcome.WARNING
        return RowOutcome.VALID

    def error(self, code: str, field_name: str | None, value: str | None, message: str) -> None:
        self.issues.append(Issue(code, "error", field_name, value, message))

    def warn(self, code: str, field_name: str | None, value: str | None, message: str) -> None:
        self.issues.append(Issue(code, "warning", field_name, value, message))


# ------------------------------------------------------------------ helpers


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    return date(d.year + month_index // 12, month_index % 12 + 1, 1)


def expected_period_end(start: date, frequency: Frequency) -> date:
    after = _add_months(start, FREQUENCY_MONTHS[frequency])
    return date.fromordinal(after.toordinal() - 1)


def _parse_date(result: RowResult, field_name: str, raw: str) -> date | None:
    try:
        if len(raw) != 10:
            raise ValueError
        return date.fromisoformat(raw)
    except ValueError:
        result.error(
            "invalid_date",
            field_name,
            raw,
            "Dates must be written as YYYY-MM-DD (for example 2002-01-31), so day and month "
            "cannot be confused.",
        )
        return None


def _parse_value(result: RowResult, raw: str, measure: str | None) -> tuple[bool, Decimal | None]:
    """Returns (ok, value). An empty cell is a missing value, never zero."""
    if raw == "":
        result.warn(
            "value_missing",
            "value",
            raw,
            "The value is empty. It is stored as missing (null), never as zero.",
        )
        return True, None
    if "," in raw or " " in raw:
        result.error(
            "invalid_number",
            "value",
            raw,
            "Write numbers with plain digits and a decimal point, without thousands separators "
            "(for example 48000 or 48000.5).",
        )
        return False, None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        result.error("invalid_number", "value", raw, "The value is not a number.")
        return False, None
    if not value.is_finite():
        result.error("invalid_number", "value", raw, "The value must be a finite number.")
        return False, None
    if value < 0 and measure not in SIGNED_MEASURES:
        result.error(
            "negative_value",
            "value",
            raw,
            "This indicator cannot be negative. Only a stock increase or a published balance "
            "may be below zero.",
        )
        return False, None
    return True, value


# ------------------------------------------------------------------ row checks


def _validate_row(result: RowResult, get: Any, reference: Reference, data_mode: DataMode) -> None:
    for field_name in REQUIRED_FIELDS:
        if field_name != "value" and get(field_name) == "":
            result.error(
                "missing_required", field_name, "", f"'{field_name}' is required and is empty."
            )

    # --- indicator and unit (incompatible units, T03)
    indicator_code, unit_code = get("indicator_code"), get("unit_code")
    indicator = reference.indicators.get(indicator_code) if indicator_code else None
    if indicator_code and indicator is None:
        result.error(
            "unknown_indicator",
            "indicator_code",
            indicator_code,
            "This indicator code is not in the indicator registry.",
        )
    unit = reference.units.get(unit_code) if unit_code else None
    if unit_code and unit is None:
        result.error(
            "unknown_unit", "unit_code", unit_code, "This unit code is not an approved unit."
        )
    if indicator and unit and unit.dimension != indicator.dimension:
        result.error(
            "unit_incompatible",
            "unit_code",
            unit_code,
            f"Unit {unit_code} measures {unit.dimension}, but {indicator_code} is measured in "
            f"{indicator.dimension}. Units are never mixed or converted silently.",
        )

    # --- frequency and period (dates)
    frequency: Frequency | None = None
    raw_frequency = get("frequency").lower()
    if raw_frequency:
        try:
            frequency = Frequency(raw_frequency)
        except ValueError:
            result.error(
                "unknown_frequency",
                "frequency",
                get("frequency"),
                "Frequency must be annual, quarterly, monthly or statement.",
            )
    start = (
        _parse_date(result, "period_start", get("period_start")) if get("period_start") else None
    )
    end = _parse_date(result, "period_end", get("period_end")) if get("period_end") else None

    complete = True
    raw_complete = get("period_complete").lower()
    if raw_complete in TRUE_WORDS or raw_complete == "":
        complete = True
    elif raw_complete in FALSE_WORDS:
        complete = False
    else:
        result.error(
            "invalid_boolean",
            "period_complete",
            get("period_complete"),
            "period_complete must be true or false.",
        )

    statement_date: date | None = None
    if get("statement_date"):
        statement_date = _parse_date(result, "statement_date", get("statement_date"))
    if frequency is Frequency.STATEMENT:
        # A dated statement: its reference period is not stated, so the "period" is the
        # statement date itself. Such rows never enter a time series.
        if statement_date is None:
            result.error(
                "statement_date_required",
                "statement_date",
                get("statement_date"),
                "A statement record needs the date the statement was made (YYYY-MM-DD).",
            )
        elif start != statement_date or end != statement_date:
            result.error(
                "statement_period_mismatch",
                "period_start",
                get("period_start"),
                "For a statement record, period_start and period_end equal the statement date.",
            )
    elif statement_date is not None:
        result.error(
            "statement_date_not_applicable",
            "statement_date",
            get("statement_date"),
            "Only statement records carry a statement date.",
        )

    if start and end and frequency is not Frequency.STATEMENT:
        if end < start:
            result.error(
                "period_order", "period_end", get("period_end"), "The period ends before it starts."
            )
        elif frequency:
            if start.day != 1:
                result.error(
                    "period_not_month_aligned",
                    "period_start",
                    get("period_start"),
                    "Periods must start on the first day of a month.",
                )
            else:
                full_end = expected_period_end(start, frequency)
                if end > full_end:
                    result.error(
                        "period_frequency_mismatch",
                        "period_end",
                        get("period_end"),
                        f"A {frequency.value} period starting {start} "
                        f"ends by {full_end} at the latest.",
                    )
                elif complete and end != full_end:
                    result.error(
                        "period_frequency_mismatch",
                        "period_end",
                        get("period_end"),
                        f"A complete {frequency.value} period starting {start} ends on {full_end}. "
                        "Mark partial periods (e.g. year to date) with period_complete = false.",
                    )
                elif not complete and end.day != calendar.monthrange(end.year, end.month)[1]:
                    result.error(
                        "period_not_month_aligned",
                        "period_end",
                        get("period_end"),
                        "A partial period must end on the last day of a month.",
                    )

    # --- statistical scope: verified-source statistics start in January 2022 (brief)
    if start and data_mode is DataMode.VERIFIED_SOURCE and start < STATISTICAL_SCOPE_START:
        result.error(
            "before_statistical_scope",
            "period_start",
            get("period_start"),
            f"Verified-source statistics start on {STATISTICAL_SCOPE_START.isoformat()}; "
            "earlier periods are outside the platform's scope.",
        )

    # --- geography
    area_code = get("area_code")
    area = reference.areas.get(area_code) if area_code else None
    if area_code and area is None:
        result.error(
            "unknown_area",
            "area_code",
            area_code,
            "This area code is not a recognised geographic identifier.",
        )
    if (
        area
        and start
        and end
        and (
            (area.valid_from and start < area.valid_from) or (area.valid_to and end > area.valid_to)
        )
    ):
        result.error(
            "area_not_valid_for_period",
            "area_code",
            area_code,
            "This area identifier was not valid for the whole period.",
        )

    # --- commodity definitions
    commodity_code = get("commodity_code")
    commodity = reference.commodities.get(commodity_code) if commodity_code else None
    if commodity_code and commodity is None:
        result.error(
            "unknown_commodity",
            "commodity_code",
            commodity_code,
            "This commodity is not in the shared commodity registry.",
        )
    if indicator:
        if indicator.requires_commodity and not commodity_code:
            result.error(
                "commodity_required",
                "commodity_code",
                "",
                f"{indicator_code} is reported per commodity; a commodity code is required.",
            )
        if not indicator.requires_commodity and commodity_code:
            result.error(
                "commodity_not_applicable",
                "commodity_code",
                commodity_code,
                f"{indicator_code} is not reported per commodity.",
            )
    if commodity:
        if commodity.mapping_status == "withdrawn":
            result.error(
                "commodity_withdrawn",
                "commodity_code",
                commodity_code,
                "This commodity definition has been withdrawn.",
            )
        if commodity.synthetic_only and data_mode is DataMode.VERIFIED_SOURCE:
            result.error(
                "commodity_synthetic_only",
                "commodity_code",
                commodity_code,
                "This invented commodity may only appear in synthetic demonstration data.",
            )
        if commodity.mapping_status == "provisional" and data_mode is DataMode.VERIFIED_SOURCE:
            result.warn(
                "commodity_mapping_provisional",
                "commodity_code",
                commodity_code,
                "The product form and classification of this commodity are not yet reviewed.",
            )
        if (
            indicator
            and unit
            and unit.dimension == reference.units[commodity.quantity_unit_code].dimension
            and unit_code != commodity.quantity_unit_code
        ):
            result.error(
                "unit_differs_from_commodity_unit",
                "unit_code",
                unit_code,
                f"Quantities of {commodity_code} are registered in {commodity.quantity_unit_code}; "
                "no conversion factor is registered for other units.",
            )

    # --- trade flow and partner
    raw_flow = get("flow").lower()
    flow: TradeFlow | None = None
    if raw_flow:
        try:
            flow = TradeFlow(raw_flow)
        except ValueError:
            result.error(
                "invalid_flow",
                "flow",
                get("flow"),
                "Flow must be import, domestic_export or re_export.",
            )
    if indicator:
        if indicator.requires_flow and not raw_flow:
            result.error("flow_required", "flow", "", f"{indicator_code} needs a trade flow.")
        if not indicator.requires_flow and raw_flow:
            result.error(
                "flow_not_applicable", "flow", get("flow"), f"{indicator_code} has no trade flow."
            )

    partner_code = get("partner_code")
    partner = reference.partners.get(partner_code) if partner_code else None
    if partner_code:
        if indicator and not indicator.requires_flow:
            result.error(
                "partner_not_applicable",
                "partner_code",
                partner_code,
                f"{indicator_code} is not reported by trading partner.",
            )
        if partner is None:
            result.error(
                "unknown_partner",
                "partner_code",
                partner_code,
                "This partner code is not in the partner registry.",
            )
        elif data_mode is DataMode.SYNTHETIC and not partner.is_fictional:
            result.error(
                "partner_not_fictional",
                "partner_code",
                partner_code,
                "Synthetic data may only use fictional partners, never real countries.",
            )
        elif data_mode is DataMode.VERIFIED_SOURCE and partner.is_fictional:
            result.error(
                "partner_fictional",
                "partner_code",
                partner_code,
                "Verified-source data cannot reference a fictional partner.",
            )

    # --- quality and valuation basis
    raw_quality = get("quality_status").lower()
    quality = QualityStatus.ACCEPTED
    if raw_quality:
        try:
            quality = QualityStatus(raw_quality)
        except ValueError:
            result.error(
                "invalid_quality_status",
                "quality_status",
                get("quality_status"),
                "Quality status must be accepted, warning or withheld.",
            )
    valuation_basis = get("valuation_basis")
    if valuation_basis and indicator and indicator.dimension != "currency":
        result.error(
            "valuation_basis_not_applicable",
            "valuation_basis",
            valuation_basis,
            "A valuation basis applies to monetary values only.",
        )

    # --- reference-pack provenance
    raw_revision = get("revision_status").lower()
    revision: str | None = None
    if raw_revision:
        try:
            revision = RevisionStatus(raw_revision).value
        except ValueError:
            result.error(
                "invalid_revision_status",
                "revision_status",
                get("revision_status"),
                "Revision status must be one of: "
                + ", ".join(s.value for s in RevisionStatus)
                + ".",
            )
    operator = get("value_operator")
    if operator and operator not in VALUE_OPERATORS:
        result.error(
            "invalid_value_operator",
            "value_operator",
            operator,
            "A value operator is one of > >= < <= ~ (for example > for 'more than 95 percent').",
        )
    record_ref = get("record_ref")
    if len(record_ref) > 40:
        result.error(
            "invalid_record_ref",
            "record_ref",
            record_ref,
            "A record reference has at most 40 characters.",
        )

    # --- value (missing retained as null)
    value_ok, value = _parse_value(result, get("value"), indicator.measure if indicator else None)

    if result.outcome is not RowOutcome.REJECTED and value_ok:
        assert indicator and unit and area and start and end and frequency
        result.normalized = {
            "indicator_id": indicator.id,
            "indicator_code": indicator_code,
            "unit_id": unit.id,
            "area_id": area.id,
            "area_code": area_code,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "period_complete": complete,
            "frequency": frequency.value,
            "value": None if value is None else str(value),
            "commodity_id": commodity.id if commodity else None,
            "commodity_code": commodity_code or None,
            "partner_id": partner.id if partner else None,
            "partner_code": partner_code or None,
            "flow": flow.value if flow else None,
            "quality_status": quality.value,
            "valuation_basis": valuation_basis or None,
            "source_reference": get("source_reference") or None,
            "record_ref": record_ref or None,
            "revision_status": revision,
            "value_operator": operator or None,
            "source_locator": get("source_locator") or None,
            "statement_date": statement_date.isoformat() if statement_date else None,
            "note": get("note") or None,
        }


# ------------------------------------------------------------------ file-level checks


def _natural_key(n: dict[str, Any]) -> tuple[Any, ...]:
    return (
        n["indicator_id"],
        n["area_id"],
        n["period_start"],
        n["period_end"],
        n["commodity_id"],
        n["partner_id"],
        n["flow"],
    )


def _reject(result: RowResult, code: str, message: str) -> None:
    result.error(code, None, None, message)
    result.normalized = None


def _check_duplicates(results: list[RowResult]) -> None:
    """T04: rows sharing a natural key are all rejected; none is silently preferred."""
    by_key: dict[tuple[Any, ...], list[RowResult]] = defaultdict(list)
    for r in results:
        if r.normalized is not None:
            by_key[_natural_key(r.normalized)].append(r)
    for group in by_key.values():
        if len(group) > 1:
            rows = ", ".join(str(r.row_number) for r in group)
            for r in group:
                _reject(
                    r,
                    "duplicate_key",
                    f"Rows {rows} describe the same indicator, area, period, "
                    "commodity, partner and "
                    "flow. None is published until the file keeps exactly one of them.",
                )


def _check_record_refs(results: list[RowResult]) -> None:
    """A record reference identifies one record: repeated references are all rejected."""
    by_ref: dict[str, list[RowResult]] = defaultdict(list)
    for r in results:
        if r.normalized is not None and r.normalized.get("record_ref"):
            by_ref[r.normalized["record_ref"]].append(r)
    for ref, group in by_ref.items():
        if len(group) > 1:
            rows = ", ".join(str(r.row_number) for r in group)
            for r in group:
                _reject(r, "duplicate_record_ref", f"Rows {rows} share the record reference {ref}.")


def _check_partner_coverage(results: list[RowResult]) -> None:
    """Partner rows must reconcile with the stated total for the same flow (T09)."""
    totals: dict[tuple[Any, ...], RowResult] = {}
    parts: dict[tuple[Any, ...], list[RowResult]] = defaultdict(list)
    for r in results:
        n = r.normalized
        if n is None or n["flow"] is None:
            continue
        key = (
            n["indicator_id"],
            n["area_id"],
            n["period_start"],
            n["period_end"],
            n["commodity_id"],
            n["flow"],
        )
        if n["partner_id"] is None:
            totals[key] = r
        else:
            parts[key].append(r)

    for key, partner_rows in parts.items():
        total_row = totals.get(key)
        if total_row is None or total_row.normalized is None:
            for r in partner_rows:
                r.warn(
                    "partner_total_absent",
                    "partner_code",
                    r.normalized and r.normalized["partner_code"],
                    "No stated national total for this flow is in the file, "
                    "so partner coverage cannot "
                    "be checked. Partner rows are never summed into a total.",
                )
            continue
        values = [r.normalized["value"] for r in partner_rows if r.normalized]
        total_value = total_row.normalized["value"]
        if total_value is None or any(v is None for v in values):
            for r in partner_rows:
                r.warn(
                    "partner_coverage_not_assessable",
                    "value",
                    None,
                    "A partner or total value is missing, so coverage cannot be checked.",
                )
            continue
        partner_sum = sum((Decimal(v) for v in values), Decimal(0))
        total = Decimal(total_value)
        if partner_sum > total:
            for r in partner_rows:
                _reject(
                    r,
                    "partner_sum_exceeds_total",
                    f"Partner rows add up to {partner_sum}, more than the stated total of {total} "
                    f"(row {total_row.row_number}). The partner rows are not published.",
                )
        elif partner_sum < total:
            for r in partner_rows:
                r.warn(
                    "partial_partner_coverage",
                    None,
                    None,
                    f"Listed partners cover {partner_sum} of the stated total {total}; "
                    "the remainder is "
                    "unattributed. Shares are always computed against the stated total.",
                )


# ------------------------------------------------------------------ entry point


def validate_rows(
    rows: list[dict[str, str]],
    mapping: dict[str, str],
    reference: Reference,
    data_mode: DataMode,
) -> list[RowResult]:
    results: list[RowResult] = []
    for index, raw in enumerate(rows):
        result = RowResult(row_number=index + 2, raw=raw)  # row 1 is the header

        def get(field_name: str, raw: dict[str, str] = raw) -> str:
            column = mapping.get(field_name)
            return raw.get(column, "").strip() if column else ""

        _validate_row(result, get, reference, data_mode)
        results.append(result)

    _check_duplicates(results)
    _check_record_refs(results)
    _check_partner_coverage(results)
    return results
