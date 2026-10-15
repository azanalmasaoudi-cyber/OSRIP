"""Reports that freeze their inputs (booklet 3.9, 3.12; FR05, T07, T12).

At creation the report stores its filters, assumptions, data mode, the exact
observations, calculations and review cards it shows, and the dataset versions
they came from. A database trigger keeps a generated report unchanged, so a
later publication never alters it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, undefer

from app.core.errors import not_found, unprocessable
from app.domain.calculations import StockAssumption
from app.domain.enums import DataMode, Frequency, Permission, Section
from app.models import Report, ReportInput
from app.services import audit
from app.services.analysis.runs import latest_cards
from app.services.analysis.sections import AnalysisFilter, analyse
from app.services.exports import CALC_HEADER, calculation_rows, mode_label, write_csv
from app.services.observations import ObservationQuery, query_observations
from app.services.principal import Principal

FILTER_KEYS = (
    "dataset_version_id",
    "indicator",
    "area",
    "commodity",
    "partner",
    "flow",
    "frequency",
    "period_kind",
    "period_from",
    "period_to",
)
PERIOD_KINDS = {"annual", "year_to_date", "quarterly", "monthly", "statement"}


def _clean_filters(filters: dict[str, Any]) -> dict[str, str]:
    unknown = sorted(set(filters) - set(FILTER_KEYS))
    if unknown:
        raise unprocessable("unknown_filter", f"Unknown report filters: {', '.join(unknown)}.")
    return {k: str(v) for k, v in filters.items() if v not in (None, "", "all")}


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def create_report(
    session: Session,
    actor: Principal,
    *,
    title: str,
    data_mode: DataMode,
    section: Section,
    filters: dict[str, Any],
    stock_assumption: StockAssumption,
    visibility: str,
) -> Report:
    clean = _clean_filters(filters)
    # The interface's "frequency" choice is a period kind (a complete year is not a
    # year-to-date total); both keys are accepted.
    kind = clean.get("period_kind") or clean.get("frequency")
    if kind is not None and kind not in PERIOD_KINDS:
        raise unprocessable("unknown_filter", f"Unknown period kind: {kind}.")
    frequency: Frequency | None = None
    version_id = uuid.UUID(clean["dataset_version_id"]) if "dataset_version_id" in clean else None
    with session.begin():
        query = ObservationQuery(
            data_mode=data_mode,
            section=section,
            indicator=clean.get("indicator"),
            area=clean.get("area"),
            commodity=clean.get("commodity"),
            partner=clean.get("partner"),
            flow=clean.get("flow"),
            frequency=frequency,
            period_from=_date(clean.get("period_from")),
            period_to=_date(clean.get("period_to")),
            dataset_version_id=version_id,
            period_kind=kind,
        )
        series = query_observations(session, query)
        calcs = analyse(
            session,
            section,
            AnalysisFilter(
                data_mode=data_mode,
                commodity=clean.get("commodity"),
                area=clean.get("area"),
                frequency=frequency,
                period_from=query.period_from,
                period_to=query.period_to,
                stock_assumption=stock_assumption,
                dataset_version_id=version_id,
                period_kind=kind,
            ),
        )
        cards = latest_cards(session, data_mode, section)
        versions: dict[str, dict[str, Any]] = {}
        for s in series:
            v = s.meta["dataset_version"]
            versions[v["id"]] = {**v, "source": s.meta["source"]}
        for c in calcs:
            for i in c["inputs"]:
                versions.setdefault(
                    i["dataset_version"]["id"],
                    {**i["dataset_version"], "source": {"dataset_title": i["source_title"]}},
                )
        now = datetime.now(UTC)
        content = {
            "title": title,
            "data_mode": data_mode.value,
            "label": mode_label(data_mode),
            "section": section.value,
            "filters": clean,
            "assumptions": {"stock_assumption": stock_assumption.value},
            "generated_at": now.isoformat(),
            "series": [{**s.meta, "observations": s.observations} for s in series],
            "calculations": calcs,
            "review_cards": cards["cards"],
            "review_run": cards["run"],
            "sources": list(versions.values()),
        }
        report = Report(
            owner_id=actor.user_id,
            data_mode=data_mode,
            title=title.strip(),
            filters=clean,
            visibility=visibility,
            section=section,
            assumptions={"stock_assumption": stock_assumption.value},
            content=content,
            generated_at=now,
        )
        session.add(report)
        session.flush()
        session.add_all(
            ReportInput(report_id=report.id, dataset_version_id=uuid.UUID(v), data_mode=data_mode)
            for v in versions
        )
        audit.record(
            session,
            actor,
            "report.create",
            entity_type="report",
            entity_id=report.id,
            metadata={
                "section": section.value,
                "data_mode": data_mode.value,
                "input_versions": sorted(versions),
            },
        )
        return report


def _visible(principal: Principal):  # noqa: ANN202
    if principal.user_id is None:
        return Report.visibility == "published"
    return or_(Report.visibility == "published", Report.owner_id == principal.user_id)


def list_reports(session: Session, principal: Principal) -> list[Report]:
    return list(
        session.scalars(
            select(Report).where(_visible(principal)).order_by(Report.created_at.desc())
        )
    )


def get_report(session: Session, principal: Principal, report_id: uuid.UUID) -> Report:
    report = session.scalar(
        select(Report)
        .options(undefer(Report.content))
        .where(Report.id == report_id, _visible(principal))
    )
    if report is None:
        raise not_found("report")  # same answer whether it does not exist or is private
    return report


def set_visibility(
    session: Session, principal: Principal, report_id: uuid.UUID, visibility: str
) -> Report:
    with session.begin():
        report = session.get(Report, report_id)
        if (
            report is None
            or report.owner_id != principal.user_id
            or not principal.has(Permission.REPORT_CREATE)
        ):
            raise not_found("report")
        report.visibility = visibility
        audit.record(
            session,
            principal,
            "report.visibility",
            entity_type="report",
            entity_id=report.id,
            metadata={"visibility": visibility},
        )
        return report


def report_csv(report: Report) -> str:
    c = report.content or {}
    filters = "; ".join(f"{k}={v}" for k, v in (c.get("filters") or {}).items()) or "none"
    preamble = [
        f"OSRIP report - {c.get('label')}",
        f"title={c.get('title')}",
        f"data_mode={c.get('data_mode')}",
        f"section={c.get('section')}",
        f"generated_at={c.get('generated_at')}",
        f"filters={filters}",
        "assumptions=" + "; ".join(f"{k}={v}" for k, v in (c.get("assumptions") or {}).items()),
        "sources="
        + " | ".join(
            f"{s['source'].get('dataset_title')} (version {s['label']})"
            for s in c.get("sources", [])
        ),
        "Frozen at generation: later publications do not change this report. "
        "Missing values are empty, never zero. Values are unrounded.",
    ]
    obs_rows = []
    for s in c.get("series", []):
        for o in s["observations"]:
            obs_rows.append(
                [
                    s["data_mode"],
                    s["indicator"]["code"],
                    s["area"]["code"],
                    o["period_start"],
                    o["period_end"],
                    s["frequency"],
                    "" if o["value"] is None else o["value"],
                    s["unit"]["code"],
                    (s["commodity"] or {}).get("code", ""),
                    (s["partner"] or {}).get("code", ""),
                    s["flow"] or "",
                    o["quality_status"],
                    s["dataset_version"]["label"],
                    o["source_row"],
                ]
            )
    card_rows = [
        [card["rule_code"], card["status"], card["observation"]["en"], card["next_steps"]["en"]]
        for card in c.get("review_cards", [])
    ]
    return write_csv(
        preamble,
        [
            (
                [
                    "data_mode",
                    "indicator",
                    "area",
                    "period_start",
                    "period_end",
                    "frequency",
                    "value",
                    "unit",
                    "commodity",
                    "partner",
                    "flow",
                    "quality_status",
                    "dataset_version",
                    "source_row",
                ],
                obs_rows,
            ),
            (CALC_HEADER, calculation_rows(c.get("data_mode", ""), c.get("calculations", []))),
            (
                ["rule", "status_at_generation", "observation", "suggested_next_investigation"],
                card_rows,
            ),
        ],
    )
