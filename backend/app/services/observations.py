"""Read published observations with their metadata (booklet 3.10-3.12, T05).

* Data mode is required and filters every table touched; modes are never mixed.
* By default each source contributes its single published snapshot. An explicit
  dataset version may be requested instead (published or superseded only; drafts
  are private).
* A response that would mix frequencies or units for one indicator is refused
  with an explanation instead of being returned side by side.
* Period kinds keep apart what must not be compared: complete years, year-to-date
  totals (for each end month), quarters, months and dated statements.
* An indicator published in several units of one dimension is shown in its display
  unit, converted only through an explicit rule (unit_conversion); every point keeps
  its original value and unit.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import ApiError, not_found, unprocessable
from app.domain.enums import DataMode, DatasetVersionStatus, Frequency, Section
from app.models import (
    Area,
    Commodity,
    DatasetVersion,
    Indicator,
    Observation,
    Partner,
    Source,
    Unit,
    UnitConversion,
)

PERIOD_KINDS = ("annual", "year_to_date", "quarterly", "monthly", "statement")


def period_kind(obs: Observation) -> str:
    """annual, year_to_date, quarterly, monthly or statement (partial: another partial year)."""
    frequency = obs.frequency.value
    if frequency == "annual" and not obs.period_complete:
        return "year_to_date" if obs.period_start.month == 1 else "partial"
    return frequency


def conversions(session: Session) -> dict[tuple[str, str], Decimal]:
    to_unit = aliased(Unit)
    rows = session.execute(
        select(Unit.code, to_unit.code, UnitConversion.factor)
        .join(UnitConversion, UnitConversion.from_unit_id == Unit.id)
        .join(to_unit, to_unit.id == UnitConversion.to_unit_id)
    )
    return {(f, t): factor for f, t, factor in rows}


PUBLIC_VERSION_STATUSES = (DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.SUPERSEDED)


@dataclass(frozen=True, slots=True)
class ObservationQuery:
    data_mode: DataMode
    section: Section | None = None
    indicator: str | None = None
    area: str | None = None
    commodity: str | None = None
    partner: str | None = None
    flow: str | None = None
    frequency: Frequency | None = None
    period_from: date | None = None
    period_to: date | None = None
    dataset_version_id: uuid.UUID | None = None
    # annual | year_to_date | quarterly | monthly | statement (narrower than frequency).
    period_kind: str | None = None
    # Year-to-date totals ending in this month (7: January to July). Without it, a selection
    # of year-to-date totals with several end months shows the latest end month published.
    ytd_end_month: int | None = None


@dataclass(slots=True)
class SeriesOut:
    key: tuple[Any, ...]
    meta: dict[str, Any]
    observations: list[dict[str, Any]] = field(default_factory=list)


def _versions_for(session: Session, q: ObservationQuery) -> list[uuid.UUID]:
    if q.dataset_version_id is not None:
        version = session.get(DatasetVersion, q.dataset_version_id)
        if version is None or version.status not in PUBLIC_VERSION_STATUSES:
            raise not_found("dataset version")
        if version.data_mode is not q.data_mode:
            raise unprocessable(
                "data_mode_mismatch",
                f"That dataset version is {version.data_mode.value} data, not {q.data_mode.value}.",
            )
        return [version.id]
    return list(
        session.scalars(
            select(DatasetVersion.id).where(
                DatasetVersion.data_mode == q.data_mode,
                DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
            )
        )
    )


def query_observations(
    session: Session, q: ObservationQuery, *, allow_mixed: bool = False
) -> list[SeriesOut]:
    """Series for the query. ``allow_mixed`` is for callers that keep each frequency
    and unit apart themselves (the analysis layer); plain reads refuse the mix."""
    version_ids = _versions_for(session, q)
    if not version_ids:
        return []

    partner = aliased(Partner)
    commodity = aliased(Commodity)
    stmt = (
        select(Observation, Indicator, Unit, Area, DatasetVersion, Source, commodity, partner)
        .join(Indicator, Indicator.id == Observation.indicator_id)
        .join(Unit, Unit.id == Observation.unit_id)
        .join(Area, Area.id == Observation.area_id)
        .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
        .join(Source, Source.id == DatasetVersion.source_id)
        .outerjoin(commodity, commodity.id == Observation.commodity_id)
        .outerjoin(partner, partner.id == Observation.partner_id)
        .where(
            Observation.dataset_version_id.in_(version_ids),
            Observation.data_mode == q.data_mode,
            DatasetVersion.data_mode == q.data_mode,
            Source.data_mode == q.data_mode,
        )
        .order_by(
            Indicator.code, Observation.flow, partner.code.nulls_first(), Observation.period_start
        )
    )
    if q.section is Section.FOOD_SECURITY:
        # Food security reuses the national trade quantities of the shared commodity
        # registry (imports and exports feed apparent availability); partner rows stay on Trade.
        stmt = stmt.where(
            or_(
                Indicator.section == Section.FOOD_SECURITY,
                and_(Indicator.code == "TRADE_QUANTITY", Observation.partner_id.is_(None)),
            )
        )
    elif q.section:
        stmt = stmt.where(Indicator.section == q.section)
    if q.indicator:
        stmt = stmt.where(Indicator.code == q.indicator)
    if q.area:
        stmt = stmt.where(Area.code == q.area)
    if q.commodity:
        stmt = stmt.where(commodity.code == q.commodity)
    if q.partner == "total":
        stmt = stmt.where(Observation.partner_id.is_(None))
    elif q.partner:
        stmt = stmt.where(partner.code == q.partner)
    if q.flow:
        stmt = stmt.where(Observation.flow == q.flow)
    if q.frequency:
        stmt = stmt.where(Observation.frequency == q.frequency)
    if q.period_kind in ("annual", "year_to_date"):
        stmt = stmt.where(
            Observation.frequency == Frequency.ANNUAL,
            Observation.period_complete.is_(q.period_kind == "annual"),
        )
        if q.period_kind == "year_to_date" and q.ytd_end_month:
            stmt = stmt.where(func.extract("month", Observation.period_end) == q.ytd_end_month)
    elif q.period_kind in ("quarterly", "monthly", "statement"):
        stmt = stmt.where(Observation.frequency == Frequency(q.period_kind))
    if q.period_from:
        stmt = stmt.where(Observation.period_end >= q.period_from)
    if q.period_to:
        stmt = stmt.where(Observation.period_start <= q.period_to)

    rules = conversions(session)
    display_units = {u.code: u for u in session.scalars(select(Unit))}
    series: dict[tuple[Any, ...], SeriesOut] = {}
    shapes: dict[str, set[tuple[str, int, str]]] = defaultdict(set)
    for obs, ind, source_unit, area, version, source, com, par in session.execute(stmt):
        kind = period_kind(obs)
        ytd_end = obs.period_end.month if kind == "year_to_date" else None
        # Show the indicator's display unit when an explicit conversion rule exists.
        factor = None
        unit = source_unit
        if ind.display_unit_code and ind.display_unit_code != source_unit.code:
            factor = rules.get((source_unit.code, ind.display_unit_code))
            if factor is not None:
                unit = display_units[ind.display_unit_code]
        shapes[ind.code].add((kind, ytd_end or 0, unit.code))
        key = (
            version.id,
            ind.code,
            area.code,
            unit.code,
            obs.frequency.value,
            kind,
            ytd_end,
            com.code if com else None,
            par.code if par else None,
            obs.flow.value if obs.flow else None,
        )
        if key not in series:
            series[key] = SeriesOut(
                key,
                {
                    "indicator": {
                        "code": ind.code,
                        "section": ind.section.value,
                        "value_type": ind.value_type.value,
                        "name_en": ind.name_en,
                        "name_ar": ind.name_ar,
                        "definition_en": ind.definition_en,
                        "definition_ar": ind.definition_ar,
                        "limitation_en": ind.limitation_en,
                        "limitation_ar": ind.limitation_ar,
                        "parent_code": ind.parent_code,
                    },
                    "unit": {
                        "code": unit.code,
                        "dimension": unit.dimension.value,
                        "label_en": unit.label_en,
                        "label_ar": unit.label_ar,
                    },
                    "frequency": obs.frequency.value,
                    "period_kind": kind,
                    "ytd_end_month": ytd_end,
                    "area": {
                        "code": area.code,
                        "name_en": area.name_en,
                        "name_ar": area.name_ar,
                        "level": area.level,
                    },
                    "commodity": None
                    if com is None
                    else {
                        "code": com.code,
                        "name_en": com.name_en,
                        "name_ar": com.name_ar,
                        "mapping_status": com.mapping_status,
                    },
                    "partner": None
                    if par is None
                    else {
                        "code": par.code,
                        "name_en": par.name_en,
                        "name_ar": par.name_ar,
                        "is_fictional": par.is_fictional,
                    },
                    "flow": obs.flow.value if obs.flow else None,
                    "valuation_basis": obs.valuation_basis,
                    "data_mode": q.data_mode.value,
                    "source": {
                        "id": str(source.id),
                        "dataset_title": source.dataset_title,
                        "publisher": source.publisher,
                        "url": source.url,
                        "locator_kind": source.locator_kind,
                        "access_date": source.access_date.isoformat()
                        if source.access_date
                        else None,
                        "reference_period": source.reference_period,
                        "geographic_coverage": source.geographic_coverage,
                        "reuse_conditions": source.reuse_conditions,
                        "source_code": source.source_code,
                        "source_role": source.source_role,
                    },
                    "dataset_version": {
                        "id": str(version.id),
                        "label": version.version_label,
                        "status": version.status.value,
                        "checksum_sha256": version.checksum_sha256,
                        "published_at": version.published_at.isoformat()
                        if version.published_at
                        else None,
                    },
                },
            )
        value = obs.value if factor is None or obs.value is None else obs.value * factor
        series[key].observations.append(
            {
                "period_start": obs.period_start.isoformat(),
                "period_end": obs.period_end.isoformat(),
                "period_complete": obs.period_complete,
                # Decimal string, unrounded; null stays null (never 0).
                "value": None
                if value is None
                else format(value.normalize() if factor else value, "f"),
                "quality_status": obs.quality_status.value,
                "source_row": obs.source_row,
                "record_ref": obs.record_ref,
                "revision_status": obs.revision_status,
                "value_operator": obs.value_operator,
                "source_locator": obs.source_locator,
                "statement_date": obs.statement_date.isoformat() if obs.statement_date else None,
                "note": obs.note,
                # The published value and unit, kept whenever a conversion was applied.
                "original_value": None
                if factor is None or obs.value is None
                else format(obs.value, "f"),
                "original_unit": None if factor is None else source_unit.code,
                "conversion_factor": None if factor is None else format(factor.normalize(), "f"),
            }
        )

    if q.period_kind == "year_to_date" and not q.ytd_end_month and not allow_mixed:
        # Totals to different months (January-July, January-August) are different periods:
        # never mixed. Each indicator shows the end month of its latest total, and says which
        # other end months exist (ytd_end_month selects one).
        by_indicator: dict[str, list[SeriesOut]] = defaultdict(list)
        for out in series.values():
            by_indicator[out.meta["indicator"]["code"]].append(out)
        kept: dict[tuple[Any, ...], SeriesOut] = {}
        for code, group in by_indicator.items():
            months = sorted({g.meta["ytd_end_month"] for g in group if g.meta["ytd_end_month"]})
            latest = max(group, key=lambda g: max(o["period_end"] for o in g.observations))
            for g in group:
                if len(months) <= 1 or g.meta["ytd_end_month"] == latest.meta["ytd_end_month"]:
                    g.meta["ytd_end_months_available"] = months
                    kept[g.key] = g
            shapes[code] = {
                (k, m, u)
                for k, m, u in shapes[code]
                if len(months) <= 1 or m == latest.meta["ytd_end_month"]
            }
        series = kept
    mixed = {code: sorted(s) for code, s in shapes.items() if len(s) > 1}
    if mixed and not allow_mixed:
        raise ApiError(
            422,
            "incompatible_series",
            "The selection mixes frequencies or units for the same indicator. Choose one frequency "
            "(and unit) so values are not compared across incompatible periods or units.",
            {
                code: [
                    {"frequency": k, "period_kind": k, "ytd_end_month": m or None, "unit": u}
                    for k, m, u in combos
                ]
                for code, combos in mixed.items()
            },
        )
    return list(series.values())
