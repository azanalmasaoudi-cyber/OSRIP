"""NCSI export conversion. The sample below is a hand-written file in an ASSUMED
export layout (column names are options); it is not NCSI data and not a real export."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.ncsi import REGION_CODES, convert, parse_period

COLUMNS = {
    "indicator": "Indicators",
    "region": "Regions",
    "date": "Date",
    "value": "Value",
    "frequency": "Frequency",
    "unit": "Unit",
}
SAMPLE = """Indicators,Regions,Date,Value,Frequency,Unit
Test generation indicator,Oman,2021,100,A,GWh
Test generation indicator,Oman,2022,200.5,A,GWh
Test generation indicator,Oman,2026,90,A,GWh
Test generation indicator,Muscat,2023M02,7,M,GWh
Test generation indicator,Wilayat Sinaw,2023M03,,M,GWh
Test generation indicator,Ash Sharqiyah,2023,5,A,GWh
Unmapped indicator,Oman,2023,1,A,x
"""
MAPPING = {"indicators": {"Test generation indicator": {"code": "ELEC_GENERATION", "unit": "GWh"}}}


def test_periods_are_parsed_by_frequency() -> None:
    assert parse_period("2023") and parse_period("2023").frequency == "annual"
    feb = parse_period("2024M02")
    assert feb and (feb.start, feb.end, feb.frequency) == (
        date(2024, 2, 1),
        date(2024, 2, 29),
        "monthly",
    )
    q = parse_period("2023Q4")
    assert q and (q.start, q.end) == (date(2023, 10, 1), date(2023, 12, 31))
    assert parse_period("not a date") is None


def test_conversion_keeps_scope_and_never_guesses() -> None:
    result = convert(SAMPLE, MAPPING, columns=COLUMNS, today=date(2026, 9, 25))
    assert result.rows == [
        ["ELEC_GENERATION", "OM", "2022-01-01", "2022-12-31", "annual", "GWh", "200.5", "true"],
        ["ELEC_GENERATION", "OM-MA", "2023-02-01", "2023-02-28", "monthly", "GWh", "7", "true"],
        ["ELEC_GENERATION", "OM-SS-07", "2023-03-01", "2023-03-31", "monthly", "GWh", "", "true"],
    ]
    assert result.skipped == {
        "before_2022": 1,
        "annual_value_for_unfinished_year": 1,  # 2026 is not over: never a complete year
        "region_not_in_registry": 1,  # pre-2011 'Ash Sharqiyah' is not guessed
        "indicator_not_mapped": 1,
    }
    assert result.unknown_regions == {"Ash Sharqiyah"}
    assert result.csv_text().splitlines()[0].startswith("indicator_code,area_code")


@pytest.mark.integration
def test_every_alias_points_at_a_registry_area_and_every_area_has_one(db) -> None:  # noqa: ANN001
    from sqlalchemy import select

    from app.models import Area

    with db.begin():
        codes = set(
            db.scalars(
                select(Area.code).where(Area.level.in_(("national", "governorate", "wilayat")))
            )
        )
    assert set(REGION_CODES.values()) == codes  # 1 + 11 + 63, one-to-one
    assert len(REGION_CODES) == len(codes) == 75
