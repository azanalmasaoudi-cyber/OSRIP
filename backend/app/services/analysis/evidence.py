"""Evidence: one published observation with everything needed to trace it.

Every calculation input is an Evidence item, so the interface, exports and
reports can show the value together with its indicator, unit, period,
geography, commodity/partner/flow, dataset version and source row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.enums import PhysicalDimension
from app.domain.quantities import Measurement, Period, Unit
from app.services.observations import SeriesOut


@dataclass(frozen=True, slots=True)
class Evidence:
    meta: dict[str, Any]  # series metadata from services.observations
    obs: dict[str, Any]  # one observation dict

    @property
    def indicator(self) -> str:
        return self.meta["indicator"]["code"]

    @property
    def period(self) -> tuple[str, str]:
        return self.obs["period_start"], self.obs["period_end"]

    @property
    def area(self) -> str:
        return self.meta["area"]["code"]

    @property
    def commodity(self) -> str | None:
        return self.meta["commodity"]["code"] if self.meta["commodity"] else None

    @property
    def partner(self) -> str | None:
        return self.meta["partner"]["code"] if self.meta["partner"] else None

    @property
    def flow(self) -> str | None:
        return self.meta["flow"]

    @property
    def value(self) -> str | None:
        return self.obs["value"]

    @property
    def version_id(self) -> str:
        return self.meta["dataset_version"]["id"]

    @property
    def kind(self) -> str:
        """Period kind: annual, year_to_date, quarterly, monthly or statement."""
        return self.meta.get("period_kind") or self.meta["frequency"]

    @property
    def operator(self) -> str | None:
        return self.obs.get("value_operator")

    def measurement(self) -> Measurement:
        unit = self.meta["unit"]
        return Measurement(
            value=None if self.value is None else Decimal(self.value),
            unit=Unit(unit["code"], PhysicalDimension(unit["dimension"])),
            period=Period(
                date.fromisoformat(self.obs["period_start"]),
                date.fromisoformat(self.obs["period_end"]),
                self.obs["period_complete"],
            ),
            coverage=self.area,
            commodity=self.commodity,
        )

    def as_input(self, role: str) -> dict[str, Any]:
        m = self.meta
        return {
            "role": role,
            "indicator": {
                "code": m["indicator"]["code"],
                "name_en": m["indicator"]["name_en"],
                "name_ar": m["indicator"]["name_ar"],
            },
            "value": self.value,
            "unit": {k: m["unit"][k] for k in ("code", "label_en", "label_ar")},
            "period_start": self.obs["period_start"],
            "period_end": self.obs["period_end"],
            "period_complete": self.obs["period_complete"],
            "frequency": m["frequency"],
            "area": m["area"],
            "commodity": self.commodity,
            "partner": self.partner,
            "flow": self.flow,
            "quality_status": self.obs["quality_status"],
            "dataset_version": {
                "id": m["dataset_version"]["id"],
                "label": m["dataset_version"]["label"],
            },
            "source_title": m["source"]["dataset_title"],
            "source_row": self.obs["source_row"],
            "period_kind": self.kind,
            "record_ref": self.obs.get("record_ref"),
            "source_code": m["source"].get("source_code"),
            "source_url": m["source"].get("url"),
            "source_locator": self.obs.get("source_locator"),
            "revision_status": self.obs.get("revision_status"),
            "value_operator": self.operator,
            "original_value": self.obs.get("original_value"),
            "original_unit": self.obs.get("original_unit"),
        }


def evidence_from(series: list[SeriesOut]) -> list[Evidence]:
    return [Evidence(s.meta, o) for s in series for o in s.observations]


def index(evidence: list[Evidence]) -> dict[tuple[Any, ...], list[Evidence]]:
    """Look-up by (indicator, area, period_start, period_end, commodity, partner, flow).

    A list, because two published sources can report the same component; callers
    must refuse to choose between them silently.
    """
    out: dict[tuple[Any, ...], list[Evidence]] = {}
    for e in evidence:
        out.setdefault((e.indicator, e.area, *e.period, e.commodity, e.partner, e.flow), []).append(
            e
        )
    return out
