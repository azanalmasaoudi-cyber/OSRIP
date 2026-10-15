"""Value objects carrying the metadata a calculation must check."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import PhysicalDimension


@dataclass(frozen=True, slots=True)
class Unit:
    code: str  # e.g. "GWh", "MW", "million_m3", "tonne", "OMR"
    dimension: PhysicalDimension


@dataclass(frozen=True, slots=True)
class Period:
    start: date
    end: date
    is_complete: bool = True  # False for year-to-date / partial periods

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("Period end precedes start.")

    @property
    def length_days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True, slots=True)
class Measurement:
    """One observed value. ``value is None`` means missing, never zero."""

    value: Decimal | None
    unit: Unit
    period: Period
    coverage: str  # explicit area / coverage identity, e.g. "OM" for national
    commodity: str | None = None  # registry code; required for commodity indicators


# Reference units used by fixtures and tests. The authoritative registry is the
# ``unit`` table; these constants exist so pure-function tests need no database.
GWH = Unit("GWh", PhysicalDimension.ENERGY)
MW = Unit("MW", PhysicalDimension.POWER)
MILLION_M3 = Unit("million_m3", PhysicalDimension.VOLUME)
TONNE = Unit("tonne", PhysicalDimension.MASS)
OMR = Unit("OMR", PhysicalDimension.CURRENCY)
SUBSCRIBERS = Unit("subscriber", PhysicalDimension.COUNT)
