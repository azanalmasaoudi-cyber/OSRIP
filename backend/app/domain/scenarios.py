"""Hypothetical scenarios: user-chosen assumptions applied to a published value. Pure.

A scenario is arithmetic on assumptions, not a statistical estimate. It has no
error measures and no probability, and it is never labelled a forecast. The only
input taken from data is the base: the latest published value of one series.

value(k) = base × (1 + one_off / 100) × (1 + growth / 100) ** k, for k = 1..years
(the one-off change, e.g. an import change, applies from the first projected year).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

MAX_YEARS = 10
GROWTH_RANGE = (Decimal(-50), Decimal(50))
ONE_OFF_RANGE = (Decimal(-100), Decimal(200))

LABEL = {
    "en": "Hypothetical scenario: the result of the assumptions you chose, applied to the latest published value. It is not a forecast, an estimate of what will happen, or an official figure.",
    "ar": "سيناريو افتراضي: نتيجة الافتراضات التي اخترتها مطبقةً على آخر قيمة منشورة. ليس تنبؤاً ولا تقديراً لما سيحدث ولا رقماً رسمياً.",
}


@dataclass(frozen=True, slots=True)
class ScenarioPoint:
    step: int
    value: Decimal


def project(
    base: Decimal, growth_pct: Decimal, years: int, one_off_pct: Decimal = Decimal(0)
) -> list[ScenarioPoint]:
    if not 1 <= years <= MAX_YEARS:
        raise ValueError(f"years must be between 1 and {MAX_YEARS}")
    if not GROWTH_RANGE[0] <= growth_pct <= GROWTH_RANGE[1]:
        raise ValueError("growth is outside the allowed range")
    if not ONE_OFF_RANGE[0] <= one_off_pct <= ONE_OFF_RANGE[1]:
        raise ValueError("one-off change is outside the allowed range")
    factor = Decimal(1) + growth_pct / 100
    shifted = base * (Decimal(1) + one_off_pct / 100)
    return [ScenarioPoint(k, shifted * factor**k) for k in range(1, years + 1)]
