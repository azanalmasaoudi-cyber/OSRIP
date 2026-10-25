"""One indicator published in two series (a year book up to 2024, a monthly bulletin with
2025): a calculation uses the series that holds both periods, and periods found only in
different series are reported with their publications, with no change calculated across
them. Found live with DeepSeek (2026-10-25): "Compare it with the previous year." was refused
as "ask the user which one", and the model kept retrying until it ran out of rounds."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.enums import DataMode
from app.services.assistant.grounding import validate
from app.services.assistant.service import UNANSWERED, _turns
from app.services.assistant.tools import Ledger, Tools
from app.services.observations import SeriesOut


def _meta(code: str, title: str) -> dict[str, Any]:
    return {
        "indicator": {
            "code": "ELEC_GROSS_GENERATION",
            "name_en": "Gross electricity generation",
            "name_ar": "إجمالي توليد الكهرباء",
            "limitation_en": "",
            "limitation_ar": "",
        },
        "area": {"code": "OM", "name_en": "Oman", "name_ar": "عُمان", "level": "national"},
        "frequency": "annual",
        "period_kind": "annual",
        "unit": {"code": "GWh", "label_en": "GWh", "label_ar": "GWh", "dimension": "energy"},
        "commodity": None,
        "partner": None,
        "flow": None,
        "data_mode": "verified_source",
        "source": {
            "dataset_title": title,
            "publisher": "NCSI",
            "url": None,
            "access_date": "2026-09-27",
            "reference_period": None,
            "source_code": code,
        },
        "dataset_version": {"label": "reference", "published_at": "2026-09-28T21:19:59+04:00"},
    }


def _obs(year: int, value: str) -> dict[str, Any]:
    return {
        "period_start": f"{year}-01-01",
        "period_end": f"{year}-12-31",
        "period_complete": True,
        "value": value,
    }


YEAR_BOOK = SeriesOut(
    ("S02",),
    _meta("S02", "Statistical Year Book 2026"),
    [_obs(2022, "42510.6"), _obs(2023, "44965.7"), _obs(2024, "49132.0")],
)
BULLETIN = SeriesOut(
    ("S01",), _meta("S01", "Monthly Statistical Bulletin"), [_obs(2025, "50973.5")]
)


def _tools(*series: SeriesOut) -> Tools:
    tools = Tools(None, Ledger(DataMode.VERIFIED_SOURCE))  # type: ignore[arg-type]
    tools._series = lambda *args: list(series)  # type: ignore[method-assign]
    return tools


def test_the_series_holding_both_periods_is_used() -> None:
    tools = _tools(YEAR_BOOK, BULLETIN)
    out = tools.compare_periods("ELEC_GROSS_GENERATION", "2023-01-01", "2024-01-01")
    assert out["status"] == "ok"
    change = next(r for r in out["results"] if r["calculation"] == "absolute_change")
    assert change["status"] == "ok" and Decimal(change["value"]) == Decimal("4166.3")
    growth = tools.growth_rate("ELEC_GROSS_GENERATION", 2022, 2024)
    assert growth["status"] == "ok"


def test_periods_in_different_series_are_reported_not_calculated() -> None:
    tools = _tools(YEAR_BOOK, BULLETIN)
    out = tools.compare_periods("ELEC_GROSS_GENERATION", "2024-01-01", "2025-01-01")
    assert out["status"] == "different_series"
    assert [(o["value"], o["source"]) for o in out["observations"]] == [
        ("49132.0", "Statistical Year Book 2026"),
        ("50973.5", "Monthly Statistical Bulletin"),
    ]
    assert {i["kind"] for i in tools.ledger.items} == {"observation"}  # no change calculated
    assert tools.growth_rate("ELEC_GROSS_GENERATION", 2024, 2025)["status"] == "different_series"
    # The values are evidence: an answer giving both, each cited, passes the evidence check.
    first, second = (o["id"] for o in out["observations"][:2])
    text = (
        f"Gross generation was 49,132.0 GWh in 2024 [{first}] and 50,973.5 GWh in 2025 "
        f"[{second}], from different publications, so no change is calculated."
    )
    assert validate(text, [first, second], tools.ledger.items).ok


def test_a_missing_period_or_two_matching_series() -> None:
    tools = _tools(YEAR_BOOK, BULLETIN)
    assert tools.compare_periods("X", "2021-01-01", "2024-01-01")["status"] == "no_data"
    assert _tools().compare_periods("X", "2023-01-01", "2024-01-01")["status"] == "no_data"
    twice = _tools(YEAR_BOOK, SeriesOut(("S03",), YEAR_BOOK.meta, YEAR_BOOK.observations))
    assert twice.compare_periods("X", "2023-01-01", "2024-01-01")["status"] == "not_comparable"


def test_an_unanswered_question_is_not_joined_to_the_next() -> None:
    turns = _turns(
        [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Compare it with the previous year."},
            {"role": "user", "content": "ما آخر قيمة منشورة لإنتاج المياه في عُمان؟"},
            {"role": "assistant", "content": "520.0 million m3 [E1]."},
        ]
    )
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]
    assert turns[0]["content"] == "Compare it with the previous year."
    assert turns[1]["content"] == UNANSWERED


def test_earlier_replies_lose_their_evidence_ids() -> None:
    turns = _turns(
        [
            {"role": "user", "content": "What is the latest generation?"},
            {"role": "assistant", "content": "50,973.5 GWh in 2025 [E85], 49,132.0 in 2024 [E82]."},
        ]
    )
    assert turns[1]["content"] == "50,973.5 GWh in 2025, 49,132.0 in 2024."
