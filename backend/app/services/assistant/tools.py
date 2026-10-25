"""Read-only evidence functions the assistant may call. They never write.

Every record a tool returns is added to an evidence ledger with an ID (E1, E2 ...).
The model may only state numbers that appear in cited evidence; calculations are
done here with the domain functions, never by the model.

Scope: published snapshots of the conversation's data mode. In verified-source mode
only periods from January 2022 onward are used (build brief).
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.domain import calculations as calc
from app.domain.enums import DataMode, PhysicalDimension
from app.domain.explanations import explain
from app.domain.quantities import Measurement, Period, Unit
from app.models import Area, Indicator
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.observations import ObservationQuery, SeriesOut, query_observations

MAX_OBSERVATIONS = 60

# Formulas of the platform's calculations (booklet Table 3.1), for explanations.
FORMULAS: dict[str, dict[str, str]] = {
    "absolute_change": {
        "en": "current − previous, for the same series, unit and comparable complete periods",
        "ar": "القيمة الحالية − السابقة، للسلسلة والوحدة نفسيهما وفترات مكتملة قابلة للمقارنة",
    },
    "percentage_change": {
        "en": "100 × (current − previous) ÷ previous; undefined when the previous value is 0; missing when an input is missing",
        "ar": "100 × (الحالية − السابقة) ÷ السابقة؛ غير معرّف إذا كانت القيمة السابقة صفراً، ومفقود إذا غاب أحد المدخلات",
    },
    "apparent_availability": {
        "en": "production + imports − domestic exports − stock increase, same commodity, unit and year; the stock assumption is stated",
        "ar": "الإنتاج + الواردات − الصادرات المحلية − الزيادة في المخزون، للسلعة والوحدة والسنة نفسها مع بيان افتراض المخزون",
    },
    "local_production_contribution": {
        "en": "100 × production ÷ apparent availability; positive denominator required; not a complete food-security measure",
        "ar": "100 × الإنتاج ÷ التوفر الظاهري؛ يلزم مقام موجب؛ ليس مقياساً كاملاً للأمن الغذائي",
    },
    "largest_partner_share": {
        "en": "100 × largest partner's imports ÷ total imports (physical quantity), with the partner coverage stated",
        "ar": "100 × واردات أكبر شريك ÷ إجمالي الواردات (كمية مادية) مع بيان تغطية الشركاء",
    },
    "trade_balance": {
        "en": "export value − import value, same currency, commodity and period; not a profit or loss",
        "ar": "قيمة الصادرات − قيمة الواردات بالعملة والسلعة والفترة نفسها؛ ليس ربحاً أو خسارة",
    },
    "unit_value": {
        "en": "trade value ÷ physical quantity, non-zero compatible quantity; not a retail price",
        "ar": "قيمة التجارة ÷ الكمية المادية مع كمية غير صفرية ومتوافقة؛ ليس سعر تجزئة",
    },
    "use_per_subscriber": {
        "en": "consumption ÷ subscribers for the same area and period; subscribers are accounts, not people",
        "ar": "الاستهلاك ÷ المشتركين للمنطقة والفترة نفسها؛ المشتركون حسابات وليسوا أشخاصاً",
    },
    "compound_annual_growth": {
        "en": "100 × ((last ÷ first)^(1 ÷ years) − 1) between two comparable periods of one series; first value must be positive",
        "ar": "100 × ((الأخيرة ÷ الأولى)^(1 ÷ عدد السنوات) − 1) بين فترتين قابلتين للمقارنة لسلسلة واحدة؛ يجب أن تكون القيمة الأولى موجبة",
    },
    "share_of_total": {
        "en": "100 × component ÷ total, for a published component of a published total in the same period, area and unit",
        "ar": "100 × المكوّن ÷ الإجمالي لمكوّن منشور من إجمالي منشور في الفترة والمنطقة والوحدة نفسها",
    },
}


def _num(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


# What kind of statement a piece of evidence supports, shown beside every citation:
# a published value, platform arithmetic on published values, a model estimate, or the
# arithmetic consequence of a user's assumption. Definitions and formulas are references.
EVIDENCE_CLASS = {
    "observation": "observed",
    "calculation": "calculated",
    "forecast": "forecast",
    "scenario": "hypothetical",
    "definition": "reference",
    "method": "reference",
    # Web evidence sets its own class: 'official' (Omani government, sector regulators,
    # international statistical bodies) or 'secondary' (reported by others).
    "web": "secondary",
    "search": "reference",
    "note": "reference",  # documented conflicts and limitations of the reference pack
    "study": "calculated",  # a deterministic study (table, chart, export) from approved data
}
PERIOD_KINDS = ("annual", "year_to_date", "quarterly", "monthly", "statement")

# Every evidence item says which of these it is, so they are never confused in a reply.
DATA_STATUS = (
    "approved_official",  # a published value from a registered official source (verified mode)
    "synthetic_demonstration",  # labelled demonstration data (synthetic mode): never Omani statistics
    "unreviewed_external",  # found on the web; not part of OSRIP data until reviewed and imported
    "calculated",  # computed by OSRIP's own deterministic functions from the cited inputs
    "model_forecast",  # a validated model estimate, not an official statistic
    "assumption_scenario",  # hypothetical arithmetic from the person's stated assumption
    "reference",  # definitions, methods, documented notes and search records
)


def data_status(item: dict[str, Any], data_mode: DataMode) -> str:
    kind = item.get("kind", "")
    if kind == "observation":
        return (
            "approved_official"
            if data_mode is DataMode.VERIFIED_SOURCE
            else "synthetic_demonstration"
        )
    return {
        "web": "unreviewed_external",
        "grounded_context": "unreviewed_external",
        "calculation": "calculated",
        "study": "calculated",
        "forecast": "model_forecast",
        "scenario": "assumption_scenario",
    }.get(kind, "reference")


@dataclass
class Ledger:
    """Evidence gathered while answering one message."""

    data_mode: DataMode
    items: list[dict[str, Any]] = field(default_factory=list)
    language: str = "en"
    web_enabled: bool = False
    client_key: str | None = None  # keyed digest of the client address (rate limits)
    searches: int = 0
    pages: int = 0
    # Routing policy (assistant/routing.py): a numerical question needs a platform data
    # lookup before any web search, unless it is about recent events.
    web_first: bool = True
    data_lookups: int = 0
    # A second search route as a cross-check, only when the person asked for one.
    cross_check: bool = False
    # How the answer was produced: answering provider and model, fallback, routing decision.
    meta: dict[str, Any] = field(default_factory=dict)
    # Called with every recorded item (the live study's evidence panel), if set.
    on_add: Any = field(default=None, repr=False)
    # Research that saves figures (research/saving.py): the data-update job, or None; who may
    # submit figures (a Principal with research.submit, or None: nobody); what was submitted.
    job_id: uuid.UUID | None = None
    # Searches and pages this answer may use (None: the per-answer settings); Research mode
    # gets its own, larger budget.
    max_searches: int | None = None
    max_pages: int | None = None
    submitter: Any = field(default=None, repr=False)
    submissions: list[dict[str, Any]] = field(default_factory=list)
    # Tables and charts the backend built in this answer (datatable.py), the person's question
    # (a chart only when it asks for one) and the tables of earlier answers ("Draw it").
    question: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    previous_tables: list[dict[str, Any]] = field(default_factory=list)

    def add(self, item: dict[str, Any]) -> dict[str, Any]:
        item = {
            "id": f"E{len(self.items) + 1}",
            "evidence_class": EVIDENCE_CLASS.get(item.get("kind", ""), "reference"),
            **item,
        }
        item.setdefault("data_status", data_status(item, self.data_mode))
        self.items.append(item)
        if self.on_add is not None:
            self.on_add(item)
        return item

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {i["id"]: i for i in self.items}


def _floor(data_mode: DataMode, year_from: int | None) -> date | None:
    floor = STATISTICAL_SCOPE_START if data_mode is DataMode.VERIFIED_SOURCE else None
    asked = date(year_from, 1, 1) if year_from else None
    if floor and asked:
        return max(floor, asked)
    return floor or asked


def _observation_item(s: SeriesOut, o: dict[str, Any]) -> dict[str, Any]:
    m = s.meta
    return {
        "kind": "observation",
        "indicator": m["indicator"]["code"],
        "indicator_name": {"en": m["indicator"]["name_en"], "ar": m["indicator"]["name_ar"]},
        "area": m["area"]["code"],
        "area_name": {"en": m["area"]["name_en"], "ar": m["area"]["name_ar"]},
        "area_level": m["area"].get("level"),
        "frequency": m["frequency"],
        # A year-to-date total is a partial year; a statement is one dated figure.
        "period_kind": m.get("period_kind", m["frequency"]),
        "period_start": o["period_start"],
        "period_end": o["period_end"],
        "period_complete": o["period_complete"],
        "value": o["value"],
        "value_operator": o.get("value_operator"),
        "unit": m["unit"]["code"],
        "unit_label": {"en": m["unit"]["label_en"], "ar": m["unit"]["label_ar"]},
        "original_value": o.get("original_value"),
        "original_unit": o.get("original_unit"),
        "commodity": m["commodity"]["code"] if m["commodity"] else None,
        "partner": m["partner"]["code"] if m["partner"] else None,
        "flow": m["flow"],
        "data_mode": m["data_mode"],
        "record_ref": o.get("record_ref"),
        "revision_status": o.get("revision_status"),
        "statement_date": o.get("statement_date"),
        "source": {
            "title": m["source"]["dataset_title"],
            "publisher": m["source"]["publisher"],
            "url": m["source"]["url"],
            "access_date": m["source"]["access_date"],
            "reference_period": m["source"]["reference_period"],
            "source_code": m["source"].get("source_code"),
            "locator": o.get("source_locator"),
        },
        "dataset_version": m["dataset_version"]["label"],
        "published_at": m["dataset_version"]["published_at"],
        "limitation": {
            "en": m["indicator"]["limitation_en"],
            "ar": m["indicator"]["limitation_ar"],
        },
    }


class Tools:
    def __init__(self, session: Session, ledger: Ledger) -> None:
        self.session = session
        self.ledger = ledger

    # -------------------------------------------------------------- catalogue
    def list_indicators(self) -> dict[str, Any]:
        rows = self.session.scalars(select(Indicator).order_by(Indicator.section, Indicator.code))
        out = []
        for ind in rows:
            item = self.ledger.add(
                {
                    "kind": "definition",
                    "indicator": ind.code,
                    "section": ind.section.value,
                    "name": {"en": ind.name_en, "ar": ind.name_ar},
                    "definition": {"en": ind.definition_en, "ar": ind.definition_ar},
                    "limitation": {"en": ind.limitation_en, "ar": ind.limitation_ar},
                }
            )
            out.append(
                {
                    "evidence_id": item["id"],
                    "code": ind.code,
                    "section": ind.section.value,
                    "name_en": ind.name_en,
                    "name_ar": ind.name_ar,
                }
            )
        return {"indicators": out}

    def list_areas(self, level: str = "governorate") -> dict[str, Any]:
        if level not in ("national", "governorate", "wilayat"):
            level = "governorate"
        rows = self.session.scalars(select(Area).where(Area.level == level).order_by(Area.code))
        return {
            "areas": [{"code": a.code, "name_en": a.name_en, "name_ar": a.name_ar} for a in rows]
        }

    def explain_calculation(self, kind: str) -> dict[str, Any]:
        formula = FORMULAS.get(kind)
        if formula is None:
            return {"error": "unknown_calculation", "known": sorted(FORMULAS)}
        item = self.ledger.add({"kind": "method", "calculation": kind, "formula": formula})
        return {"evidence_id": item["id"], "calculation": kind, "formula": formula}

    # -------------------------------------------------------------- validated forecasts
    def get_forecast(self, indicator: str, area: str = "OM") -> dict[str, Any]:
        """The latest successful forecast run for the indicator and area (model estimates)."""
        from app.models import AnalysisRun
        from app.services import forecasting

        runs = self.session.scalars(
            select(AnalysisRun)
            .where(
                AnalysisRun.kind == "forecast",
                AnalysisRun.status == "succeeded",
                AnalysisRun.data_mode == self.ledger.data_mode,
            )
            .order_by(AnalysisRun.started_at.desc())
            .limit(200)
        )
        for run in runs:
            series = run.parameters.get("series") or {}
            if (series.get("indicator") or {}).get("code") == indicator and (
                series.get("area") or {}
            ).get("code") == area:
                detail = forecasting.run_detail(self.session, run.id)
                if not detail["outputs"]:
                    continue
                item = self.ledger.add(
                    {
                        "kind": "forecast",
                        "indicator": indicator,
                        "area": area,
                        "unit": series.get("unit", {}).get("code"),
                        "frequency": series.get("frequency"),
                        "dataset_version": series.get("dataset_version", {}).get("label"),
                        "training_cutoff": detail["training_cutoff"],
                        "selected_model": detail["selected_model"],
                        "outputs": detail["outputs"],
                        "metrics": detail["metrics"],
                        "data_mode": run.data_mode.value,
                        "label": detail["estimate_label"],
                    }
                )
                return {
                    "status": "ok",
                    "evidence_id": item["id"],
                    "note": "These are model estimates, not official statistics. Say so, give the interval, and do not add causes or events.",
                    **{
                        k: item[k]
                        for k in ("selected_model", "training_cutoff", "outputs", "metrics", "unit")
                    },
                }
        return {
            "status": "no_forecast",
            "message": "No validated forecast exists for this indicator and area (insufficient data or not run).",
        }

    # -------------------------------------------------------------- observations
    def _series(
        self,
        indicator: str,
        area: str,
        frequency: str | None,
        year_from: int | None,
        year_to: int | None,
    ) -> list[SeriesOut]:
        # The period kind keeps a year-to-date total apart from the full year it belongs to.
        kind = frequency if frequency in PERIOD_KINDS else None
        return query_observations(
            self.session,
            ObservationQuery(
                data_mode=self.ledger.data_mode,
                indicator=indicator,
                area=area,
                period_kind=kind,
                period_from=_floor(self.ledger.data_mode, year_from),
                period_to=date(year_to, 12, 31) if year_to else None,
            ),
            allow_mixed=True,
        )

    def get_observations(
        self,
        indicator: str,
        area: str = "OM",
        frequency: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> dict[str, Any]:
        series = self._series(indicator, area, frequency, year_from, year_to)
        if not series:
            return {
                "status": "no_data",
                "message": "No published observations match. Report the data as unavailable.",
            }
        out, count = [], 0
        for s in series:
            for o in s.observations[-MAX_OBSERVATIONS:]:
                if count >= MAX_OBSERVATIONS:
                    break
                item = self.ledger.add(_observation_item(s, o))
                count += 1
                out.append(
                    {
                        k: item[k]
                        for k in (
                            "id",
                            "indicator",
                            "area",
                            "period_kind",
                            "period_start",
                            "period_end",
                            "period_complete",
                            "value",
                            "value_operator",
                            "unit",
                            "commodity",
                            "partner",
                            "flow",
                            "revision_status",
                            "dataset_version",
                        )
                    }
                )
        return {
            "status": "ok",
            "observations": out,
            "note": "A null value means the source reports the value as missing; say 'data unavailable', never zero. "
            "A value_operator such as '>' must be kept ('more than 95'). Year-to-date totals are partial years.",
        }

    def latest_period(self, indicator: str, area: str = "OM") -> dict[str, Any]:
        series = self._series(indicator, area, None, None, None)
        latest = []
        for s in series:
            with_value = [o for o in s.observations if o["value"] is not None]
            if not with_value:
                continue
            item = self.ledger.add(_observation_item(s, with_value[-1]))
            latest.append(
                {
                    k: item[k]
                    for k in (
                        "id",
                        "area",
                        "period_kind",
                        "period_start",
                        "period_end",
                        "period_complete",
                        "value",
                        "value_operator",
                        "unit",
                        "revision_status",
                        "dataset_version",
                    )
                }
            )
        if not latest:
            return {
                "status": "no_data",
                "message": "No published value exists for this indicator and area.",
            }
        return {"status": "ok", "latest_by_series": latest}

    # -------------------------------------------------------------- comparison (backend arithmetic)
    def compare_periods(
        self,
        indicator: str,
        period_a_start: str,
        period_b_start: str,
        area: str = "OM",
        frequency: str = "annual",
    ) -> dict[str, Any]:
        try:
            a_start, b_start = (
                date.fromisoformat(period_a_start),
                date.fromisoformat(period_b_start),
            )
        except ValueError:
            return {
                "status": "invalid_request",
                "message": "Periods must be ISO dates (YYYY-MM-DD).",
            }
        wanted = [a_start.isoformat(), b_start.isoformat()]
        s = self._holding(
            self._series(indicator, area, frequency, None, None),
            wanted,
            lambda o: o["period_start"],
        )
        if isinstance(s, dict):
            return s
        by_start = {o["period_start"]: o for o in s.observations}
        a, b = by_start[wanted[0]], by_start[wanted[1]]
        ea, eb = self.ledger.add(_observation_item(s, a)), self.ledger.add(_observation_item(s, b))
        unit = Unit(s.meta["unit"]["code"], PhysicalDimension(s.meta["unit"]["dimension"]))

        def measure(o: dict[str, Any]) -> Measurement:
            return Measurement(
                None if o["value"] is None else Decimal(o["value"]),
                unit,
                Period(
                    date.fromisoformat(o["period_start"]),
                    date.fromisoformat(o["period_end"]),
                    o["period_complete"],
                ),
                s.meta["area"]["code"],
                s.meta["commodity"]["code"] if s.meta["commodity"] else None,
            )

        results = []
        for kind, fn, result_unit in (
            ("absolute_change", calc.absolute_change, unit.code),
            ("percentage_change", calc.percentage_change, "percent"),
        ):
            r = fn(measure(a), measure(b))
            item = self.ledger.add(
                {
                    "kind": "calculation",
                    "calculation": kind,
                    "formula": FORMULAS[kind],
                    "inputs": [ea["id"], eb["id"]],
                    "status": r.status.value,
                    "value": _num(r.value),
                    "unit": result_unit if r.value is not None else None,
                    "reason": explain(r.reason.value) if r.reason else None,
                }
            )
            results.append(
                {
                    k: item[k]
                    for k in ("id", "calculation", "status", "value", "unit", "reason", "inputs")
                }
            )
        return {"status": "ok", "previous": ea["id"], "current": eb["id"], "results": results}

    # -------------------------------------------------------------- more backend arithmetic
    def _measure(self, s: SeriesOut, o: dict[str, Any]) -> Measurement:
        return Measurement(
            None if o["value"] is None else Decimal(o["value"]),
            Unit(s.meta["unit"]["code"], PhysicalDimension(s.meta["unit"]["dimension"])),
            Period(
                date.fromisoformat(o["period_start"]),
                date.fromisoformat(o["period_end"]),
                o["period_complete"],
            ),
            s.meta["area"]["code"],
            s.meta["commodity"]["code"] if s.meta["commodity"] else None,
        )

    def _single(self, indicator: str, area: str, frequency: str) -> SeriesOut | dict[str, Any]:
        series = [
            s
            for s in self._series(indicator, area, frequency, None, None)
            if s.meta["partner"] is None
        ]
        if len(series) == 1:
            return series[0]
        return {
            "status": "not_comparable" if series else "no_data",
            "message": "More than one published series matches; ask which one (flow, commodity)."
            if series
            else "No published observations match. Report the data as unavailable.",
        }

    def _holding(
        self,
        series: list[SeriesOut],
        wanted: list[str],
        key: Callable[[dict[str, Any]], str],
    ) -> SeriesOut | dict[str, Any]:
        """The one series that has every wanted period (``key`` of an observation). An indicator
        can be published in more than one series (a year book up to 2024, a monthly bulletin
        from 2025): the series holding all the periods is used, and a calculation never mixes
        two. Periods found only in different series are recorded, so each value can be given
        with its publication, and no change is calculated across them."""
        if not series:
            return {
                "status": "no_data",
                "message": "No published observations match. Report the data as unavailable.",
            }

        def find(s: SeriesOut, k: str) -> dict[str, Any] | None:
            return next((o for o in s.observations if key(o) == k), None)

        holding = [s for s in series if all(find(s, k) is not None for k in wanted)]
        if len(holding) == 1:
            return holding[0]
        if holding:
            return {
                "status": "not_comparable",
                "message": "More than one published series has these periods; ask which one "
                "(flow, commodity, source).",
            }
        found = [(s, o) for k in wanted for s in series if (o := find(s, k)) is not None]
        if {key(o) for _, o in found} != set(wanted):
            return {
                "status": "no_data",
                "message": "One of the periods has no published observation. Report it as "
                "unavailable.",
            }
        values = []
        for s, o in found:
            item = self.ledger.add(_observation_item(s, o))
            values.append(
                {
                    **{
                        k: item[k]
                        for k in (
                            "id",
                            "period_kind",
                            "period_start",
                            "period_end",
                            "period_complete",
                            "value",
                            "value_operator",
                            "unit",
                            "revision_status",
                        )
                    },
                    "source": item["source"]["title"],
                }
            )
        return {
            "status": "different_series",
            "message": "These periods are published in different series (different "
            "publications), so the platform calculates no change between them. Give each value "
            "with its period and publication, say that no change is calculated across "
            "publications, and do not calculate it yourself.",
            "observations": values,
        }

    def _calc_item(self, kind: str, inputs: list[str], r: Any, unit: str | None) -> dict[str, Any]:
        item = self.ledger.add(
            {
                "kind": "calculation",
                "calculation": kind,
                "formula": FORMULAS[kind],
                "inputs": inputs,
                "status": r.status.value,
                "value": _num(r.value),
                "unit": unit if r.value is not None else None,
                "reason": explain(r.reason.value) if r.reason else None,
            }
        )
        return {
            k: item[k] for k in ("id", "calculation", "status", "value", "unit", "reason", "inputs")
        }

    def growth_rate(
        self,
        indicator: str,
        from_year: int,
        to_year: int,
        area: str = "OM",
        frequency: str = "annual",
    ) -> dict[str, Any]:
        """Compound annual growth between two comparable periods of one series."""
        s = self._holding(
            [
                x
                for x in self._series(indicator, area, frequency, None, None)
                if not x.meta["partner"]
            ],
            [str(int(from_year)), str(int(to_year))],
            lambda o: str(int(o["period_start"][:4])),
        )
        if isinstance(s, dict):
            return s
        by_year = {int(o["period_start"][:4]): o for o in s.observations}
        a, b = by_year[int(from_year)], by_year[int(to_year)]
        ea, eb = self.ledger.add(_observation_item(s, a)), self.ledger.add(_observation_item(s, b))
        r = calc.compound_annual_growth(
            self._measure(s, a), self._measure(s, b), int(to_year) - int(from_year)
        )
        return {
            "status": "ok",
            "result": self._calc_item("compound_annual_growth", [ea["id"], eb["id"]], r, "percent"),
        }

    def share_of_total(
        self,
        part_indicator: str,
        total_indicator: str,
        period_start: str,
        area: str = "OM",
        frequency: str = "annual",
    ) -> dict[str, Any]:
        """Share of a published component in its published total (same period and unit)."""
        part_ind = self.session.scalar(select(Indicator).where(Indicator.code == part_indicator))
        if part_ind is None or part_ind.parent_code != total_indicator:
            return {
                "status": "not_comparable",
                "message": "The platform does not record the first indicator as a component of the "
                "second, so no share is calculated.",
            }
        part, total = (
            self._single(part_indicator, area, frequency),
            self._single(total_indicator, area, frequency),
        )
        for s in (part, total):
            if isinstance(s, dict):
                return s
        assert isinstance(part, SeriesOut) and isinstance(total, SeriesOut)
        po = next((o for o in part.observations if o["period_start"] == period_start), None)
        to = next((o for o in total.observations if o["period_start"] == period_start), None)
        if po is None or to is None:
            return {
                "status": "no_data",
                "message": "The period is not published for both indicators.",
            }
        ep, et = (
            self.ledger.add(_observation_item(part, po)),
            self.ledger.add(_observation_item(total, to)),
        )
        r = calc.share_of_total(self._measure(part, po), self._measure(total, to))
        return {
            "status": "ok",
            "result": self._calc_item("share_of_total", [ep["id"], et["id"]], r, "percent"),
        }

    def compare_areas(
        self,
        indicator: str,
        period_start: str | None = None,
        frequency: str = "annual",
        level: str = "governorate",
        flow: str | None = None,
    ) -> dict[str, Any]:
        """The same indicator, period and unit across governorates (or wilayats with their own
        published values). Missing stays missing; nothing is inferred downwards."""
        from app.services import comparisons

        try:
            start = date.fromisoformat(period_start) if period_start else None
        except ValueError:
            return {"status": "invalid_request", "message": "period_start must be YYYY-MM-DD."}
        kind = frequency if frequency in PERIOD_KINDS else "annual"
        result = comparisons.compare_areas(
            self.session, self.ledger.data_mode, indicator, kind, start, level, flow
        )
        ids = {}
        for s, o in result.get("entries", []):
            ids[s.meta["area"]["code"]] = self.ledger.add(_observation_item(s, o))["id"]
        out = comparisons.public(result)
        for r in [
            *out.get("rows", []),
            *([out["national"]] if out.get("national") else []),
            *out.get("reporting_groups", []),
        ]:
            r["evidence_id"] = ids.get(r["area"])
        out["note"] = (
            "Only areas with their own published value have an evidence id. Say 'no published "
            "value' for the others, never zero; do not divide totals among areas."
        )
        return out

    def data_quality_notes(self, section: str | None = None) -> dict[str, Any]:
        """Documented conflicts, revisions and limitations of the curated reference pack."""
        from app.models import DataQualityNote, ReferencePack

        pack = self.session.scalar(
            select(ReferencePack).order_by(ReferencePack.research_cutoff.desc())
        )
        if pack is None:
            return {"status": "no_data", "message": "No reference pack is loaded."}
        notes = []
        for n in self.session.scalars(
            select(DataQualityNote)
            .where(DataQualityNote.pack_id == pack.id)
            .order_by(DataQualityNote.code)
        ):
            if section and section not in (n.sections or []):
                continue
            item = self.ledger.add(
                {
                    "kind": "note",
                    "code": n.code,
                    "title": {"en": n.title_en, "ar": n.title_ar},
                    "text": n.body_en,
                    "text_ar": n.body_ar,
                    "source_codes": list(n.source_codes or []),
                    "sections": list(n.sections or []),
                    "research_cutoff": pack.research_cutoff.isoformat(),
                }
            )
            notes.append(
                {"evidence_id": item["id"], "code": n.code, "title": n.title_en, "text": n.body_en}
            )
        return {
            "status": "ok" if notes else "no_data",
            "notes": notes,
            "note": "Documented conflicts between sources: report both figures with their sources; "
            "do not choose silently.",
        }

    # -------------------------------------------------------------- studies
    def run_study(self, kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """A deterministic study (no storage here: this transaction is read only). The full
        validated result is kept in the ledger; the reply stores it if it is cited."""
        import uuid as _uuid

        from app.services import studies

        doc = studies.build(self.session, kind, dict(params or {}), self.ledger.data_mode)
        item = self.ledger.add(
            {
                "kind": "study",
                "study_id": str(_uuid.uuid4()),
                "study_kind": doc["kind"],
                "title": doc["title"],
                "status": doc["status"],
                "study": doc,
            }
        )
        rows = doc["table"]["rows"]
        return {
            "status": doc["status"],
            "evidence_id": item["id"],
            "title": doc["title"]["en"],
            "reason": (doc.get("reason") or {}).get("en"),
            "findings": [f["text"]["en"] for f in doc["findings"]],
            "findings_ar": [f["text"]["ar"] for f in doc["findings"]],
            "cards": [
                {
                    "label": c["label"]["en"],
                    "value": c["value"],
                    "period": c.get("period"),
                    "nature": c["nature"],
                    "unit": (c.get("unit") or {}).get("code"),
                }
                for c in doc["cards"]
            ],  # fmt: skip
            "columns": [c["key"] for c in doc["table"]["columns"]],
            "rows": rows[:24],
            "rows_total": len(rows),
            "method": doc["method"]["en"],
            "assumptions": [a["en"] for a in doc["assumptions"]],
            "limitations": [x["en"] for x in doc["limitations"]],
            "data_mode": doc["data_mode"],
            "note": "The user sees this study as a table and chart. Report its findings with the "
            "evidence id; do not recompute its numbers.",
        }

    def balance_analysis(self, sector: str, period_kind: str = "annual") -> dict[str, Any]:
        """Shortage and surplus analysis of one sector (deterministic; stored with the reply only
        if it is cited, like a study)."""
        import uuid as _uuid

        from app.services.analysis import balance

        doc = balance.build(
            self.session, {"sector": sector, "period_kind": period_kind}, self.ledger.data_mode
        )
        item = self.ledger.add(
            {
                "kind": "study",
                "study_id": str(_uuid.uuid4()),
                "study_kind": doc["kind"],
                "title": doc["title"],
                "status": doc["status"],
                "study": doc,
            }
        )
        return {
            "status": doc["status"],
            "evidence_id": item["id"],
            "title": doc["title"]["en"],
            "summary": [s["en"] for s in doc["summary"]],
            "summary_ar": [s["ar"] for s in doc["summary"]],
            "balances": [
                {
                    "title": b["title"]["en"],
                    "status": b["status"],
                    "status_label": b["status_label"]["en"],
                    "period": b["period"],
                    "gap": b["gap"],
                    "gap_unit": (b["gap_unit"] or {}).get("code"),
                    "reason": b["reason"]["en"],
                }
                for b in doc["balances"]
            ],
            "recommendations": [
                {
                    "priority": r["priority"],
                    "problem": r["problem"]["en"],
                    "action": r["action"]["en"],
                    "quantity": r["quantity"],
                    "unit": (r["quantity_unit"] or {}).get("code"),
                }
                for r in doc["recommendations"][:10]
            ],
            "missing_information": [g["missing"]["en"] for g in doc["data_gaps"]],
            "forecast": doc["forecast"]["text"]["en"],
            "data_mode": doc["data_mode"],
            "note": "The user sees this analysis as tables, charts and a recommendation table. Cite its "
            "evidence id for every number you take from it and do not recompute them. State a "
            "shortage or surplus only for a balance whose status is not 'not_determinable'; for the "
            "others, say what information is missing.",
        }

    # -------------------------------------------------------------- web research (untrusted)
    def web_search(
        self, query: str, domain: str = "general", query_other_language: str | None = None
    ) -> dict[str, Any]:
        if not self.ledger.web_enabled:
            return {
                "status": "disabled",
                "message": "Web research is switched off for this question.",
            }
        if not self.ledger.web_first and self.ledger.data_lookups == 0:
            # Routing policy: a numerical question starts with the platform's approved data.
            return {
                "status": "data_first",
                "message": "This is a numerical question: look up the platform's published data first "
                "(list_indicators, get_observations, latest_period, ...). Search the web only for what "
                "the data do not cover.",
            }
        from app.services.research import service as research

        return research.web_search(
            self.ledger,
            str(query),
            str(domain),
            self.ledger.client_key,
            other_language_query=str(query_other_language) if query_other_language else None,
        )

    def read_web_page(self, evidence_id: str, focus: str | None = None) -> dict[str, Any]:
        if not self.ledger.web_enabled:
            return {
                "status": "disabled",
                "message": "Web research is switched off for this question.",
            }
        from app.services.research import service as research

        return research.read_web_page(self.ledger, str(evidence_id), focus)

    # -------------------------------------------------------------- research that saves figures
    def submit_observations(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        """Figures read in official documents, for backend validation; only the ones every
        check passes are saved (research/saving.py). Never a database write of the model's."""
        if self.ledger.submitter is None:
            return {
                "status": "not_permitted",
                "message": "Saving figures needs a signed-in account with research permission. "
                "Report the figures with their sources and say they were not saved.",
            }
        if not isinstance(observations, list) or not observations:
            return {"status": "invalid_request", "message": "Give at least one observation."}
        from app.db.session import session_factory
        from app.services.research import saving

        with session_factory()() as writer:
            outcomes = saving.submit(
                writer,
                [o for o in observations if isinstance(o, dict)],
                self.ledger.items,
                submitter=self.ledger.submitter,
                language=self.ledger.language,
                job_id=self.ledger.job_id,
            )
        results = [o.as_dict() for o in outcomes]
        self.ledger.submissions.extend(results)
        return {
            "status": "ok",
            "counts": dict(Counter(r["status"] for r in results)),
            "results": results,
            "note": "saved=true only for figures now published as observations (status approved). "
            "duplicate: already published, nothing added. conflict: differs from a published or "
            "submitted figure, kept for a reviewer, nothing overwritten. pending: waits for a "
            "reviewer (reasons). rejected: cannot be saved (reasons). Say exactly which were "
            "saved; never call the others saved.",
        }

    def research_status(
        self, scope: str = "this_answer", indicator: str | None = None
    ) -> dict[str, Any]:
        """What research saved or left waiting: this answer's submissions, or the latest ones."""
        from app.services.research import saving

        if scope == "this_answer":
            ids = [
                uuid.UUID(r["candidate_id"])
                for r in self.ledger.submissions
                if r.get("candidate_id")
            ]
            if not ids:
                return {"status": "none", "message": "Nothing was submitted in this answer."}
            out = saving.status(self.session, candidate_ids=ids)
        else:
            out = saving.status(self.session, indicator_code=indicator or None, limit=20)
        for item in out["items"]:
            if item["saved"]:
                # A saved figure is a published observation: citable like one.
                added = self.ledger.add(
                    {
                        "kind": "saved_research",
                        "indicator": item["indicator_code"],
                        "area": item["area_code"],
                        "period_start": item["period_start"],
                        "period_end": item["period_end"],
                        "period_kind": item["period_kind"],
                        "value": item["value"],
                        "unit": item["unit"],
                        "observation_id": item["observation_id"],
                        "source": {
                            "title": item["source_title"],
                            "publisher": item["publisher"],
                            "url": item["source_url"],
                        },
                        "publication_date": item["publication_date"],
                        "retrieved_at": item["retrieved_at"],
                    }
                )
                item["evidence_id"] = added["id"]
        return {
            "status": "ok",
            **out,
            "note": "Only items with saved=true are published data (cite their evidence_id). "
            "Pending, conflict and rejected items are not facts: name them as waiting or refused.",
        }

    # -------------------------------------------------------------- tables and charts
    def make_table(
        self,
        series: list[dict[str, Any]],
        year_from: int | None = None,
        year_to: int | None = None,
        latest: int | None = None,
    ) -> dict[str, Any]:
        """A table built by the backend from published observations (datatable.py)."""
        from app.services.assistant import datatable

        if not isinstance(series, list) or not series or len(series) > 6:
            return {"status": "invalid_request", "message": "Give one to six series."}
        rows: list[dict[str, Any]] = []
        missing: list[str] = []
        clean = []
        for spec in series:
            if not isinstance(spec, dict):
                continue
            indicator = str(spec.get("indicator", "")).strip()
            area = str(spec.get("area", "OM") or "OM").strip()
            kind = str(spec.get("period_kind", "")).strip()
            if kind not in datatable.KINDS:
                return {
                    "status": "invalid_request",
                    "message": "period_kind must be monthly, quarterly, annual or year_to_date: "
                    "one kind per series (monthly values are never made from annual ones).",
                }
            if self.session.scalar(select(Indicator.id).where(Indicator.code == indicator)) is None:
                codes = self.session.scalars(select(Indicator.code).order_by(Indicator.code)).all()
                return {
                    "status": "unknown_indicator",
                    "indicator": indicator,
                    "message": "Use a platform indicator code, for example: " + ", ".join(codes),
                }
            clean.append({"indicator": indicator, "area": area, "period_kind": kind})
            found = self._series(indicator, area, kind, year_from, year_to)
            obs = [(s_, o) for s_ in found if s_.meta["partner"] is None for o in s_.observations]
            obs.sort(key=lambda t: t[1]["period_start"])
            if latest:
                periods = sorted({o["period_start"] for _, o in obs})[
                    -max(1, min(int(latest), 24)) :
                ]
                obs = [(s_, o) for s_, o in obs if o["period_start"] in periods]
            if not obs:
                missing.append(f"{indicator}/{area}/{kind}")
            for s_, o in obs:
                item = self.ledger.add(_observation_item(s_, o))
                rows.append(datatable.row_from_item(item))
        if not rows:
            return {
                "status": "no_data",
                "missing": missing,
                "message": "No published observations match. Report the data as unavailable.",
            }
        tables = datatable.build_tables(rows)
        number = len(self.ledger.tables) + 1
        self.ledger.tables.append(
            {
                "id": f"T{number}",
                "params": {
                    "series": clean,
                    "year_from": year_from,
                    "year_to": year_to,
                    "latest": latest,
                },
                "tables": tables,
            }
        )
        return {
            "status": "ok",
            "table_id": f"T{number}",
            "missing_series": missing,
            "rows": [
                {
                    "evidence_id": r["evidence_id"],
                    "period": datatable.period_text(
                        r["period_start"], r["period_end"], r["period_kind"]
                    ),
                    "period_kind": r["period_kind"],
                    "indicator": r["indicator_code"],
                    "area": r["area"],
                    "value": r["value"],
                    "unit": r["unit"],
                    "revision_status": r["revision_status"],
                    "source": r["source"]["title"],
                }
                for t in tables
                for r in t["rows"]
            ],
            "note": "The table is shown to the person under your reply exactly as built (with a CSV "
            "download). Do not repeat it as a Markdown table: describe what it shows and cite the "
            "evidence ids. Missing values stay missing.",
        }

    def make_chart(self, table: str = "latest", title: str | None = None) -> dict[str, Any]:
        """A chart over the rows of a table built in this answer, or of the previous answer's
        table (rebuilt from published data), only when the person asked for a chart."""
        from app.services.assistant import datatable, routing

        if not routing.asks_for_chart(self.ledger.question):
            return {
                "status": "not_requested",
                "message": "Charts are drawn only when the person asks for one.",
            }
        source = None
        if self.ledger.tables and table != "previous":
            source = self.ledger.tables[-1]
        elif self.ledger.previous_tables:
            params = self.ledger.previous_tables[-1]
            rebuilt = self.make_table(**params)
            if rebuilt.get("status") != "ok":
                return {
                    "status": "no_data",
                    "message": "The earlier table's data are no longer published.",
                }
            source = self.ledger.tables[-1]
        if source is None:
            return {
                "status": "no_table",
                "message": "Build the table first (make_table) for the series to draw; if the "
                "period is unknown, ask one short question.",
            }
        # One chart per unit (the table is already split by unit): values in different units
        # never share an axis.
        drawn, refused = [], []
        for block in source["tables"]:
            rows = block["rows"]
            first = rows[0]
            names = sorted(
                {(r["indicator_name"] or {}).get("en", r["indicator_code"]) for r in rows}
            )
            names_ar = sorted(
                {(r["indicator_name"] or {}).get("ar", r["indicator_code"]) for r in rows}
            )
            area = first["area_name"] or {}
            default = {
                "en": f"{' / '.join(names)} · {area.get('en', first['area'])}",
                "ar": f"{' / '.join(names_ar)} · {area.get('ar', first['area'])}",
            }
            if title and title.strip() and len(source["tables"]) == 1:
                default = {"en": title.strip()[:120], "ar": title.strip()[:120]}
            built = datatable.build_chart(rows, default)
            if built["status"] != "ok":
                refused.append({"unit": block["unit"]["code"], **built})
                continue
            self.ledger.charts.append({**built, "table_id": source["id"], "title": default})
            drawn.append(
                {
                    "unit": block["unit"]["code"],
                    "type": built["type"],
                    "points": built["points"],
                    "period_kind": built["period_kind"],
                    "evidence_ids": built["evidence_ids"],
                    "sources": built["sources"],
                }
            )
        if not drawn:
            return {
                "status": refused[0]["status"] if refused else "no_data",
                "refused": refused,
                "message": "No chart: explain why (only one comparable value, or values that "
                "cannot share one chart) instead of drawing one.",
            }
        return {
            "status": "ok",
            "charts": drawn,
            "refused": refused,
            "note": "Each chart is drawn under your reply from the same rows as the table, one per "
            "unit. Name what each shows (period, unit, sources); do not describe them as images.",
        }

    # -------------------------------------------------------------- hypothetical scenarios
    def scenario_projection(
        self,
        indicator: str,
        growth_pct: float,
        years: int = 1,
        one_off_pct: float = 0,
        area: str = "OM",
    ) -> dict[str, Any]:
        """Arithmetic consequence of the user's stated assumption, from the latest complete
        published year. Not a forecast and not a causal model."""
        from app.services import scenarios
        from app.services.forecasting import _series_id

        matches = [
            s
            for s in scenarios._series(self.session, self.ledger.data_mode)
            if s.meta["indicator"]["code"] == indicator and s.meta["area"]["code"] == area
        ]
        if not matches:
            return {
                "status": "no_data",
                "message": "No complete published year exists to start a scenario from.",
            }
        try:
            result = scenarios.projection(
                self.session,
                self.ledger.data_mode,
                _series_id(matches[0]),
                Decimal(str(growth_pct)),
                int(years),
                Decimal(str(one_off_pct)),
            )
        except ApiError as exc:
            return {"status": "invalid_assumption", "message": exc.message}
        base = self.ledger.add(_observation_item(matches[0], result["base"]))
        item = self.ledger.add(
            {
                "kind": "scenario",
                "indicator": indicator,
                "area": area,
                "unit": matches[0].meta["unit"]["code"],
                "inputs": [base["id"]],
                "assumptions": result["assumptions"],
                "formula": result["formula"],
                "points": result["points"],
                "label": result["label"],
            }
        )
        return {
            "status": "ok",
            "evidence_id": item["id"],
            "base": base["id"],
            "points": result["points"],
            "note": "Hypothetical: the result of the user's assumption applied to a published value. "
            "Say so; it is not a forecast or an official figure.",
        }


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_indicators",
        "description": "List the platform's indicators with definitions and limitations (evidence of kind 'definition').",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_areas",
        "description": "List administrative areas (codes and names). Use codes such as OM (national) or OM-MA (Muscat).",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["national", "governorate", "wilayat"]}
            },
        },
    },
    {
        "name": "get_observations",
        "description": "Published observations for one indicator and area, from January 2022 in verified mode. Each has an evidence id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "area": {"type": "string", "default": "OM"},
                "frequency": {
                    "type": "string",
                    "enum": list(PERIOD_KINDS),
                    "description": "Period kind; year_to_date is a partial year",
                },
                "year_from": {"type": "integer"},
                "year_to": {"type": "integer"},
            },
            "required": ["indicator"],
        },
    },
    {
        "name": "latest_period",
        "description": "The latest period with a published value, separately for each series of an indicator and area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "area": {"type": "string", "default": "OM"},
            },
            "required": ["indicator"],
        },
    },
    {
        "name": "compare_periods",
        "description": "Absolute and percentage change between two periods of one series, computed by the platform with its comparability checks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "period_a_start": {
                    "type": "string",
                    "description": "Earlier period start, YYYY-MM-DD",
                },
                "period_b_start": {
                    "type": "string",
                    "description": "Later period start, YYYY-MM-DD",
                },
                "area": {"type": "string", "default": "OM"},
                "frequency": {
                    "type": "string",
                    "enum": list(PERIOD_KINDS),
                    "default": "annual",
                    "description": "Compare like with like: year_to_date only with year_to_date",
                },
            },
            "required": ["indicator", "period_a_start", "period_b_start"],
        },
    },
    {
        "name": "explain_calculation",
        "description": "The formula and guards of a platform calculation.",
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": sorted(FORMULAS)}},
            "required": ["kind"],
        },
    },
    {
        "name": "get_forecast",
        "description": "The latest validated forecast (model estimates with prediction intervals and backtest errors) for an indicator and area, if one exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "area": {"type": "string", "default": "OM"},
            },
            "required": ["indicator"],
        },
    },
    {
        "name": "scenario_projection",
        "description": "Hypothetical arithmetic for a user-stated assumption (e.g. 'if demand grew 3% a year'): "
        "value(k) = base × (1 + one-off) × (1 + growth)^k from the latest complete published year. "
        "Not a forecast; use only when the user states the assumption.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "growth_pct": {"type": "number", "description": "Assumed annual change in percent"},
                "years": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
                "one_off_pct": {"type": "number", "default": 0},
                "area": {"type": "string", "default": "OM"},
            },
            "required": ["indicator", "growth_pct"],
        },
    },
    {
        "name": "final_answer",
        "description": "Give the final reply. Call exactly once, at the end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["answered", "clarification", "no_evidence"]},
                "text": {
                    "type": "string",
                    "description": "Reply in the user's language. Every number must come from cited evidence.",
                },
                "citations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Evidence ids supporting the statements, e.g. ['E3','E5']",
                },
                "suggested_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 3,
                },
                "web_records": {
                    "type": "array",
                    "maxItems": 10,
                    "description": "Numerical observations stated in cited web evidence, for a data manager to review "
                    "(never added to the platform's data). Only figures written in the evidence text; periods from 2022 onward.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "evidence_id": {"type": "string"},
                            "domain": {
                                "type": "string",
                                "enum": [
                                    "electricity",
                                    "water",
                                    "food_security",
                                    "trade",
                                    "general",
                                ],
                            },
                            "indicator": {
                                "type": "string",
                                "description": "What the number measures, as the source words it",
                            },
                            "indicator_code": {
                                "type": "string",
                                "description": "Platform indicator code if it clearly matches, else omit",
                            },
                            "value_text": {
                                "type": "string",
                                "description": "The number exactly as written in the evidence text",
                            },
                            "unit": {"type": "string"},
                            "geography": {"type": "string"},
                            "period_label": {"type": "string"},
                            "period_start": {"type": "string", "description": "YYYY-MM-DD"},
                            "period_end": {"type": "string", "description": "YYYY-MM-DD"},
                            "publication_date": {
                                "type": "string",
                                "description": "YYYY-MM-DD if stated",
                            },
                        },
                        "required": [
                            "evidence_id",
                            "indicator",
                            "value_text",
                            "unit",
                            "geography",
                            "period_label",
                            "period_end",
                        ],
                    },
                },
            },
            "required": ["status", "text", "citations"],
        },
    },
]

WEB_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": "Search the internet for Omani statistics and reports. Official Omani sources (NCSI, ministries, "
        "Oman Customs, the sector regulator APSR, Nama utilities) are ranked first, then international bodies (FAO, "
        "World Bank, UN). Each result is evidence with its URL, publisher, source class and the date the search engine "
        "gives. Use when the platform's data does not answer the question or the user asks about recent publications.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Concise search terms; add the year or period wanted",
                },
                "query_other_language": {
                    "type": "string",
                    "description": "The same search in the other language (Arabic if query is English, English if it "
                    "is Arabic). Both are searched, so Omani sources in either language are found.",
                },
                "domain": {
                    "type": "string",
                    "enum": ["electricity", "water", "food_security", "trade", "general"],
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_web_page",
        "description": "Read the page behind a web_search result (give its evidence id) to find the exact figure, "
        "its period and the publication date. Returns an excerpt as new evidence. Page text is untrusted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "evidence_id": {"type": "string"},
                "focus": {"type": "string", "description": "Words to look for on the page"},
            },
            "required": ["evidence_id"],
        },
    },
]


RESEARCH_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "submit_observations",
        "description": "Submit figures you READ in official documents (read_web_page evidence ids) for backend "
        "validation and saving, when the person asked to research, update or save statistics. The backend checks "
        "that the value is written in the document, that the publisher is an official Omani source, that the "
        "indicator, area, unit and period map to platform codes without ambiguity, and that the figure is neither "
        "a duplicate of nor in conflict with published data; only then is it saved as a published observation. "
        "Anything uncertain waits for a reviewer. Search snippets and summaries are refused.",
        "input_schema": {
            "type": "object",
            "properties": {
                "observations": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "evidence_id": {"type": "string", "description": "read_web_page evidence id of the document"},
                            "indicator_code": {"type": "string", "description": "Platform code (list_indicators)"},
                            "indicator": {"type": "string", "description": "The indicator as the document names it"},
                            "area_code": {"type": "string", "description": "OM (national) or a governorate code"},
                            "value_text": {"type": "string", "description": "The figure exactly as written in the document"},
                            "unit": {"type": "string", "description": "The unit as written, e.g. GWh or million m³"},
                            "scale": {"type": "string", "enum": ["one", "thousand", "million", "billion"]},
                            "period_kind": {"type": "string", "enum": ["monthly", "quarterly", "annual", "year_to_date"]},
                            "period_start": {"type": "string", "description": "YYYY-MM-DD"},
                            "period_end": {"type": "string", "description": "YYYY-MM-DD"},
                            "publication_date": {"type": "string", "description": "YYYY-MM-DD when the document states it"},
                        },
                        "required": ["evidence_id", "indicator_code", "area_code", "value_text", "unit",
                                     "period_kind", "period_start", "period_end"],
                    },
                }
            },
            "required": ["observations"],
        },
    },
    {
        "name": "research_status",
        "description": "What research saved or left waiting for review: this answer's submissions "
        "(scope this_answer), or the latest research results (scope recent, optionally for one indicator), "
        "with their sources, saved observation ids and the latest saved period.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["this_answer", "recent"]},
                "indicator": {"type": "string"},
            },
        },
    },
]  # fmt: skip

TABLE_TOOL_SPEC: dict[str, Any] = {
    "name": "make_table",
    "description": "Build a table from the platform's published observations when the person asks for a table "
    "or a comparison: Period | Indicator | Value | Unit | Geography | Source, in period order, missing values "
    "kept missing. The backend builds it; it is shown under your reply with a CSV download. One kind of period "
    "per series (monthly, quarterly, annual or year_to_date: a year-to-date total is a partial year).",
    "input_schema": {
        "type": "object",
        "properties": {
            "series": {
                "type": "array",
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "indicator": {"type": "string"},
                        "area": {"type": "string", "default": "OM"},
                        "period_kind": {"type": "string", "enum": ["monthly", "quarterly", "annual", "year_to_date"]},
                    },
                    "required": ["indicator", "period_kind"],
                },
            },
            "year_from": {"type": "integer"},
            "year_to": {"type": "integer"},
            "latest": {"type": "integer", "description": "Only the latest N periods of each series"},
        },
        "required": ["series"],
    },
}  # fmt: skip

CHART_TOOL_SPEC: dict[str, Any] = {
    "name": "make_chart",
    "description": "Draw a chart because the person asked for one, from the rows of the table built in this "
    "answer, or (table: previous) of the table in the previous answer (\"Draw it\"). The backend chooses a line "
    "chart for a time trend, bars for categories or grouped bars for compatible series, with title, period, "
    "unit, legend and sources; it refuses values that cannot share one chart or fewer than two values.",
    "input_schema": {
        "type": "object",
        "properties": {
            "table": {"type": "string", "enum": ["latest", "previous"]},
            "title": {"type": "string"},
        },
    },
}  # fmt: skip


ANALYSIS_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "balance_analysis",
        "description": "Shortage and surplus analysis of one sector from approved observations: each "
        "supply-against-demand balance with its status (surplus, shortfall, balanced, or "
        "not_determinable with the reason and the missing information), a structured recommendation "
        "table built by fixed rules (costs are always unknown), and the sources. Use it for questions "
        "about shortages, surpluses, deficits, self-sufficiency or what to do about them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "enum": ["electricity", "water", "food_security", "trade"],
                },
                "period_kind": {
                    "type": "string",
                    "enum": ["annual", "year_to_date"],
                    "default": "annual",
                },
            },
            "required": ["sector"],
        },
    },
    {
        "name": "growth_rate",
        "description": "Compound annual growth rate between two comparable periods (same series, unit, "
        "coverage and period kind) of one indicator and area, computed by the platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "from_year": {"type": "integer"},
                "to_year": {"type": "integer"},
                "area": {"type": "string", "default": "OM"},
                "frequency": {"type": "string", "enum": list(PERIOD_KINDS), "default": "annual"},
            },
            "required": ["indicator", "from_year", "to_year"],
        },
    },
    {
        "name": "share_of_total",
        "description": "Share (percent) of a published component in its published parent total for one period "
        "and area. Refused when the platform does not record the component relation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "part_indicator": {"type": "string"},
                "total_indicator": {"type": "string"},
                "period_start": {"type": "string", "description": "YYYY-MM-DD"},
                "area": {"type": "string", "default": "OM"},
                "frequency": {"type": "string", "enum": list(PERIOD_KINDS), "default": "annual"},
            },
            "required": ["part_indicator", "total_indicator", "period_start"],
        },
    },
    {
        "name": "compare_areas",
        "description": "Compare one indicator across governorates (or wilayats that publish their own values) for "
        "the same period and unit. Areas without a value are 'no published value', never zero; reporting groups "
        "are separate; no total is divided among areas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "period_start": {
                    "type": "string",
                    "description": "YYYY-MM-DD; omit for the latest comparable period",
                },
                "frequency": {"type": "string", "enum": list(PERIOD_KINDS), "default": "annual"},
                "level": {
                    "type": "string",
                    "enum": ["governorate", "wilayat"],
                    "default": "governorate",
                },
                "flow": {"type": "string"},
            },
            "required": ["indicator"],
        },
    },
    {
        "name": "run_study",
        "description": "Run a deterministic OSRIP study from approved observations. It returns a "
        "validated table, chart, findings, method and limitations that the user sees as a study "
        "card; cite its evidence id for every number you take from it. Kinds: trend (indicator, "
        "area, period_kind), growth (indicator, area, from_year, to_year), compare_regions "
        "(indicator, period_kind, period_start?, level), seasonal_profile (indicator, area; "
        "monthly data only), import_dependence (commodity, year?), partner_concentration "
        "(commodity, year?), data_quality (indicator), scenario (indicator, area, growth_pct, "
        "years, one_off_pct: hypothetical, only for assumptions the user stated), "
        "forecast_eligibility (indicator, area), programme_assessment (indicator, area, "
        "objective, baseline_year, target_value, target_year: never claims programme impact).",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": [
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
                    ],
                },
                "params": {"type": "object"},
            },
            "required": ["kind", "params"],
        },
    },
    {
        "name": "data_quality_notes",
        "description": "Documented conflicts, revisions and limitations between official sources (reference "
        "pack notes Q01...). Use when sources disagree or a figure was revised.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["electricity", "water", "food_security", "trade"],
                }
            },
        },
    },
]

_CITED = {"type": "array", "items": {"type": "string"}, "description": "Evidence ids, e.g. ['E2']"}
STRUCTURED_PROPERTIES: dict[str, dict[str, Any]] = {
    "recommendations": {
        "type": "array",
        "maxItems": 5,
        "description": "Analyze and Research modes only. Each card must be supported by cited evidence. Never "
        "invent savings, costs or percentage improvements: any number must appear in the cited evidence.",
        "items": {
            "type": "object",
            "properties": {
                "finding": {"type": "string"},
                "evidence": {"type": "string", "description": "What the cited evidence shows"},
                "action": {
                    "type": "string",
                    "description": "Suggested action for a human analyst or decision maker",
                },
                "expected_benefit": {
                    "type": "string",
                    "description": "Qualitative unless the cited evidence states a figure",
                },
                "prerequisites": {"type": "string"},
                "uncertainty": {"type": "string"},
                "citations": _CITED,
            },
            "required": [
                "finding",
                "evidence",
                "action",
                "expected_benefit",
                "prerequisites",
                "uncertainty",
                "citations",
            ],
        },
    },
    "drivers": {
        "type": "array",
        "maxItems": 10,
        "description": "Relevant drivers and how each relates to the question. basis: 'evidence' (cited), "
        "'hypothesis' (plausible, not shown by the evidence) or 'assumption' (taken as given).",
        "items": {
            "type": "object",
            "properties": {
                "driver": {
                    "type": "string",
                    "enum": [
                        "weather",
                        "population",
                        "industrial_activity",
                        "desalination",
                        "renewable_energy",
                        "irrigation",
                        "agricultural_productivity",
                        "commodity_prices",
                        "logistics",
                        "trading_partners",
                    ],
                },
                "relation": {"type": "string"},
                "basis": {"type": "string", "enum": ["evidence", "hypothesis", "assumption"]},
                "citations": _CITED,
            },
            "required": ["driver", "relation", "basis"],
        },
    },
    "evidence_points": {
        "type": "array",
        "maxItems": 8,
        "items": {
            "type": "object",
            "properties": {"statement": {"type": "string"}, "citations": _CITED},
            "required": ["statement", "citations"],
        },
    },
    "hypotheses": {
        "type": "array",
        "maxItems": 8,
        "items": {
            "type": "object",
            "properties": {"statement": {"type": "string"}, "citations": _CITED},
            "required": ["statement"],
        },
    },
    "assumptions": {
        "type": "array",
        "maxItems": 8,
        "items": {
            "type": "object",
            "properties": {"statement": {"type": "string"}, "citations": _CITED},
            "required": ["statement"],
        },
    },
    "conflicts": {
        "type": "array",
        "maxItems": 5,
        "description": "Sources that disagree: list each value with its evidence id; do not pick one silently.",
        "items": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "values": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "evidence_id": {"type": "string"},
                            "value_text": {"type": "string"},
                        },
                        "required": ["evidence_id", "value_text"],
                    },
                },
                "note": {"type": "string"},
            },
            "required": ["topic", "values"],
        },
    },
}

MODES = ("ask", "analyze", "research", "compare", "scenario")
MODE_PARTS = {
    "ask": ("conflicts",),
    "analyze": tuple(STRUCTURED_PROPERTIES),
    "research": tuple(STRUCTURED_PROPERTIES),
    "compare": ("evidence_points", "conflicts"),
    "scenario": ("assumptions", "hypotheses", "drivers", "conflicts"),
}


def _final_answer_spec(mode: str) -> dict[str, Any]:
    base = next(t for t in TOOL_SPECS if t["name"] == "final_answer")
    props = dict(base["input_schema"]["properties"])
    for part in MODE_PARTS.get(mode, ()):
        props[part] = STRUCTURED_PROPERTIES[part]
    return {**base, "input_schema": {**base["input_schema"], "properties": props}}


def tool_specs(
    web: bool, mode: str = "ask", *, can_submit: bool = False, chart: bool = False
) -> list[dict[str, Any]]:
    """Tools per mode. The scenario tool exists only in Scenario mode, which keeps
    hypothetical scenarios apart from forecasts and observations. Submitting figures needs
    web research and a person allowed to submit; the chart tool exists only when the
    question asks for a chart."""
    core = [
        t
        for t in TOOL_SPECS
        if t["name"] != "final_answer"
        and (t["name"] != "scenario_projection" or mode == "scenario")
    ]
    extra = [TABLE_TOOL_SPEC, *([CHART_TOOL_SPEC] if chart else [])]
    tools = [*core, *ANALYSIS_TOOL_SPECS, *extra, _final_answer_spec(mode)]
    research = RESEARCH_TOOL_SPECS if can_submit else RESEARCH_TOOL_SPECS[1:]
    return [*WEB_TOOL_SPECS, *research, *tools] if web else [*RESEARCH_TOOL_SPECS[1:], *tools]


def run_tool(tools: Tools, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = {
        "web_search": tools.web_search,
        "read_web_page": tools.read_web_page,
        "list_indicators": tools.list_indicators,
        "list_areas": tools.list_areas,
        "get_observations": tools.get_observations,
        "latest_period": tools.latest_period,
        "compare_periods": tools.compare_periods,
        "explain_calculation": tools.explain_calculation,
        "get_forecast": tools.get_forecast,
        "scenario_projection": tools.scenario_projection,
        "growth_rate": tools.growth_rate,
        "share_of_total": tools.share_of_total,
        "compare_areas": tools.compare_areas,
        "data_quality_notes": tools.data_quality_notes,
        "run_study": tools.run_study,
        "balance_analysis": tools.balance_analysis,
        "submit_observations": tools.submit_observations,
        "research_status": tools.research_status,
        "make_table": tools.make_table,
        "make_chart": tools.make_chart,
    }.get(name)
    if handler is None:
        return {"error": "unknown_tool"}
    from app.services.assistant.routing import DATA_TOOLS

    if name in DATA_TOOLS:
        tools.ledger.data_lookups += 1
    try:
        return handler(**arguments)
    except (TypeError, ValueError, ApiError) as exc:
        return {"error": "invalid_arguments", "message": str(exc)[:200]}
