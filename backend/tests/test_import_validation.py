"""Import validation rules (booklet 3.2, 3.3; FR01, T03, T04, T09). No database needed."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from app.core.errors import ApiError
from app.domain.enums import DataMode, Frequency, RowOutcome
from app.services.imports.csv_file import parse_csv, safe_cell
from app.services.imports.validation import (
    AreaRef,
    CommodityRef,
    IndicatorRef,
    PartnerRef,
    Reference,
    UnitRef,
    check_mapping,
    expected_period_end,
    suggest_mapping,
    validate_rows,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "booklet_synthetic_fixtures_v1.csv"

# A reference snapshot shaped like migrations 0002-0003 (ids are placeholders).
REF = Reference(
    indicators={
        "ELEC_GENERATION": IndicatorRef("i-gen", "energy", "generation", False, False),
        "ELEC_PEAK_DEMAND": IndicatorRef("i-peak", "power", "peak_demand", False, False),
        "WATER_CONSUMPTION": IndicatorRef("i-wat", "volume", "consumption", False, False),
        "FOOD_PRODUCTION": IndicatorRef("i-food", "mass", "production", True, False),
        "FOOD_STOCK_INCREASE": IndicatorRef("i-stock", "mass", "stock_increase", True, False),
        "TRADE_QUANTITY": IndicatorRef("i-tq", "mass", "trade_quantity", True, True),
        "TRADE_VALUE": IndicatorRef("i-tv", "currency", "trade_value", True, True),
    },
    units={
        "GWh": UnitRef("u-gwh", "energy"),
        "MW": UnitRef("u-mw", "power"),
        "million_m3": UnitRef("u-m3", "volume"),
        "tonne": UnitRef("u-t", "mass"),
        "kg": UnitRef("u-kg", "mass"),
        "OMR": UnitRef("u-omr", "currency"),
    },
    areas={
        "OM": AreaRef("a-om", None, None),
        "OLD_AREA": AreaRef("a-old", None, date(2000, 12, 31)),
    },
    commodities={
        "WHEAT": CommodityRef("c-wheat", "provisional", False, "tonne"),
        "SYNTH_COMMODITY": CommodityRef("c-synth", "provisional", True, "tonne"),
        "RETIRED": CommodityRef("c-ret", "withdrawn", False, "tonne"),
    },
    partners={
        "PARTNER_A": PartnerRef("p-a", True),
        "PARTNER_B": PartnerRef("p-b", True),
        "PARTNER_C": PartnerRef("p-c", True),
        "REAL_X": PartnerRef("p-x", False),
    },
)

HEADER = [
    "indicator_code",
    "area_code",
    "period_start",
    "period_end",
    "frequency",
    "unit_code",
    "value",
    "commodity_code",
    "partner_code",
    "flow",
    "period_complete",
]
MAPPING = {h: h for h in HEADER}


def row(
    indicator: str = "ELEC_GENERATION",
    unit: str = "GWh",
    value: str = "48000",
    *,
    start: str = "2001-01-01",
    end: str = "2001-12-31",
    frequency: str = "annual",
    area: str = "OM",
    commodity: str = "",
    partner: str = "",
    flow: str = "",
    complete: str = "",
) -> dict[str, str]:
    return dict(
        zip(
            HEADER,
            [
                indicator,
                area,
                start,
                end,
                frequency,
                unit,
                value,
                commodity,
                partner,
                flow,
                complete,
            ],
            strict=True,
        )
    )


def validate(rows: list[dict[str, str]], mode: DataMode = DataMode.SYNTHETIC):
    return validate_rows(rows, MAPPING, REF, mode)


def codes(result) -> set[str]:  # noqa: ANN001
    return {i.code for i in result.issues}


# ------------------------------------------------------------------ the booklet fixture file


def test_booklet_fixture_file_validates_without_rejections() -> None:
    parsed = parse_csv(FIXTURE.read_bytes(), FIXTURE.name)
    mapping = suggest_mapping(parsed.header)
    assert check_mapping(mapping, parsed.header) == []
    results = validate_rows(parsed.rows, mapping, REF, DataMode.SYNTHETIC)
    assert len(results) == 12
    assert [r.outcome for r in results].count(RowOutcome.REJECTED) == 0
    # Partner A/B/C (48,000 + 20,000 + 12,000) reconcile exactly with the 80,000 t import total.
    assert all("partial_partner_coverage" not in codes(r) for r in results)
    values = {
        (
            r.normalized["indicator_code"],
            r.normalized["partner_code"],
            r.normalized["flow"],
            r.normalized["period_start"],
        ): r.normalized["value"]
        for r in results
    }
    assert values[("ELEC_GENERATION", None, None, "2001-01-01")] == "48000"
    assert values[("TRADE_VALUE", None, "import", "2002-01-01")] == "40000000"


# ------------------------------------------------------------------ required fields and values


def test_missing_required_field_rejects_row() -> None:
    [result] = validate([row(area="")])
    assert result.outcome is RowOutcome.REJECTED
    assert "missing_required" in codes(result)
    assert result.normalized is None


def test_empty_value_is_kept_as_missing_never_zero() -> None:
    [result] = validate([row(value="")])
    assert result.outcome is RowOutcome.WARNING  # published, with the reason recorded
    assert "value_missing" in codes(result)
    assert result.normalized is not None and result.normalized["value"] is None


@pytest.mark.parametrize("value", ["48,000", "n/a", "NaN", "Infinity", "4 8000"])
def test_non_numeric_values_are_rejected_with_explanation(value: str) -> None:
    [result] = validate([row(value=value)])
    assert result.outcome is RowOutcome.REJECTED
    assert codes(result) & {"invalid_number"}


def test_negative_value_only_allowed_for_stock_increase() -> None:
    generation, stock = validate(
        [
            row(value="-5"),
            row(
                "FOOD_STOCK_INCREASE",
                "tonne",
                "-5",
                start="2002-01-01",
                end="2002-12-31",
                commodity="WHEAT",
            ),
        ]
    )
    assert "negative_value" in codes(generation)
    assert stock.outcome is RowOutcome.VALID


# ------------------------------------------------------------------ units (T03)


def test_power_unit_on_energy_indicator_is_rejected() -> None:
    [result] = validate([row(unit="MW")])
    assert "unit_incompatible" in codes(result)


def test_unknown_unit_is_rejected() -> None:
    [result] = validate([row(unit="TWh")])
    assert "unknown_unit" in codes(result)


def test_commodity_quantity_must_use_registered_unit_without_silent_conversion() -> None:
    [result] = validate(
        [
            row(
                "FOOD_PRODUCTION",
                "kg",
                "100000000",
                start="2002-01-01",
                end="2002-12-31",
                commodity="WHEAT",
            )
        ]
    )
    assert "unit_differs_from_commodity_unit" in codes(result)


# ------------------------------------------------------------------ dates and frequency


@pytest.mark.parametrize("start", ["31/12/2001", "2001-13-01", "01-01-2001", "2001/01/01"])
def test_ambiguous_or_invalid_dates_are_rejected(start: str) -> None:
    [result] = validate([row(start=start)])
    assert "invalid_date" in codes(result)


def test_period_end_before_start_is_rejected() -> None:
    [result] = validate([row(start="2002-01-01", end="2001-12-31")])
    assert "period_order" in codes(result)


def test_complete_annual_period_must_cover_the_year() -> None:
    [result] = validate([row(end="2001-06-30")])
    assert "period_frequency_mismatch" in codes(result)


def test_year_to_date_is_allowed_when_marked_incomplete() -> None:
    [result] = validate([row(end="2001-06-30", complete="false")])
    assert result.outcome is RowOutcome.VALID
    assert result.normalized["period_complete"] is False


def test_monthly_period_longer_than_a_month_is_rejected() -> None:
    [result] = validate([row(frequency="monthly", end="2001-02-28")])
    assert "period_frequency_mismatch" in codes(result)


def test_unknown_frequency_is_rejected() -> None:
    [result] = validate([row(frequency="weekly")])
    assert "unknown_frequency" in codes(result)


def test_expected_period_end_handles_leap_years() -> None:
    assert expected_period_end(date(2004, 2, 1), Frequency.MONTHLY) == date(2004, 2, 29)
    assert expected_period_end(date(2001, 10, 1), Frequency.QUARTERLY) == date(2001, 12, 31)


# ------------------------------------------------------------------ geography


def test_unknown_area_identifier_is_rejected() -> None:
    [result] = validate([row(area="MUSCAT")])
    assert "unknown_area" in codes(result)


def test_area_outside_its_validity_dates_is_rejected() -> None:
    [result] = validate([row(area="OLD_AREA")])
    assert "area_not_valid_for_period" in codes(result)


# ------------------------------------------------------------------ duplicates (T04)


def test_duplicate_natural_key_rejects_every_occurrence() -> None:
    first, second, other = validate(
        [row(value="48000"), row(value="49000"), row(start="2002-01-01", end="2002-12-31")]
    )
    assert first.outcome is second.outcome is RowOutcome.REJECTED
    assert "duplicate_key" in codes(first) and "duplicate_key" in codes(second)
    assert other.outcome is RowOutcome.VALID


def test_partner_is_part_of_the_natural_key() -> None:
    results = validate(
        [
            row(
                "TRADE_QUANTITY",
                "tonne",
                "80000",
                start="2002-01-01",
                end="2002-12-31",
                commodity="WHEAT",
                flow="import",
            ),
            row(
                "TRADE_QUANTITY",
                "tonne",
                "80000",
                start="2002-01-01",
                end="2002-12-31",
                commodity="WHEAT",
                flow="import",
                partner="PARTNER_A",
            ),
        ]
    )
    assert all("duplicate_key" not in codes(r) for r in results)


# ------------------------------------------------------------------ commodities


def test_commodity_indicator_without_commodity_is_rejected() -> None:
    [result] = validate(
        [row("FOOD_PRODUCTION", "tonne", "1", start="2002-01-01", end="2002-12-31")]
    )
    assert "commodity_required" in codes(result)


def test_commodity_on_non_commodity_indicator_is_rejected() -> None:
    [result] = validate([row(commodity="WHEAT")])
    assert "commodity_not_applicable" in codes(result)


def test_withdrawn_and_unknown_commodities_are_rejected() -> None:
    withdrawn, unknown = validate(
        [
            row(
                "FOOD_PRODUCTION",
                "tonne",
                "1",
                start="2002-01-01",
                end="2002-12-31",
                commodity="RETIRED",
            ),
            row(
                "FOOD_PRODUCTION",
                "tonne",
                "1",
                start="2001-01-01",
                end="2001-12-31",
                commodity="MAIZE",
            ),
        ]
    )
    assert "commodity_withdrawn" in codes(withdrawn)
    assert "unknown_commodity" in codes(unknown)


def test_synthetic_only_commodity_is_rejected_in_verified_mode() -> None:
    [result] = validate(
        [
            row(
                "FOOD_PRODUCTION",
                "tonne",
                "1",
                start="2002-01-01",
                end="2002-12-31",
                commodity="SYNTH_COMMODITY",
            )
        ],
        DataMode.VERIFIED_SOURCE,
    )
    assert "commodity_synthetic_only" in codes(result)


def test_provisional_commodity_in_verified_mode_is_flagged_not_hidden() -> None:
    [result] = validate(
        [
            row(
                "FOOD_PRODUCTION",
                "tonne",
                "1",
                start="2022-01-01",
                end="2022-12-31",
                commodity="WHEAT",
            )
        ],
        DataMode.VERIFIED_SOURCE,
    )
    assert result.outcome is RowOutcome.WARNING
    assert "commodity_mapping_provisional" in codes(result)


def test_verified_statistics_start_in_january_2022() -> None:
    before, first = validate(
        [
            row(
                "ELEC_GENERATION",
                "GWh",
                "1",
                start="2021-12-01",
                end="2021-12-31",
                frequency="monthly",
            ),
            row(
                "ELEC_GENERATION",
                "GWh",
                "1",
                start="2022-01-01",
                end="2022-01-31",
                frequency="monthly",
            ),
        ],
        DataMode.VERIFIED_SOURCE,
    )
    assert before.outcome is RowOutcome.REJECTED
    assert "before_statistical_scope" in codes(before)
    assert first.outcome is RowOutcome.VALID
    # Synthetic fixtures keep their placeholder years (SPEC_CONFLICTS C11).
    [synthetic] = validate(
        [row("ELEC_GENERATION", "GWh", "1", start="2001-01-01", end="2001-12-31")],
        DataMode.SYNTHETIC,
    )
    assert "before_statistical_scope" not in codes(synthetic)


# ------------------------------------------------------------------ partners and coverage (T09)


def trade(value: str, partner: str = "", flow: str = "import") -> dict[str, str]:
    return row(
        "TRADE_QUANTITY",
        "tonne",
        value,
        start="2002-01-01",
        end="2002-12-31",
        commodity="WHEAT",
        partner=partner,
        flow=flow,
    )


def test_real_partner_is_rejected_in_synthetic_mode() -> None:
    [_, partner] = validate([trade("100"), trade("100", "REAL_X")])
    assert "partner_not_fictional" in codes(partner)


def test_fictional_partner_is_rejected_in_verified_mode() -> None:
    [_, partner] = validate([trade("100"), trade("100", "PARTNER_A")], DataMode.VERIFIED_SOURCE)
    assert "partner_fictional" in codes(partner)


def test_partners_exceeding_the_stated_total_are_rejected() -> None:
    total, a, b = validate(
        [trade("70000"), trade("48000", "PARTNER_A"), trade("30000", "PARTNER_B")]
    )
    assert total.outcome is not RowOutcome.REJECTED
    assert a.outcome is b.outcome is RowOutcome.REJECTED
    assert "partner_sum_exceeds_total" in codes(a)


def test_partial_partner_coverage_is_labelled() -> None:
    _, a = validate([trade("80000"), trade("48000", "PARTNER_A")])
    assert a.outcome is RowOutcome.WARNING
    assert "partial_partner_coverage" in codes(a)


def test_partner_rows_without_a_stated_total_are_flagged() -> None:
    [a] = validate([trade("48000", "PARTNER_A")])
    assert "partner_total_absent" in codes(a)


def test_flow_is_required_for_trade_and_refused_elsewhere() -> None:
    no_flow, stray = validate([trade("1", flow=""), row(flow="import")])
    assert "flow_required" in codes(no_flow)
    assert "flow_not_applicable" in codes(stray)


# ------------------------------------------------------------------ mapping and file safety


def test_mapping_must_cover_required_fields_and_existing_columns() -> None:
    problems = check_mapping(
        {"indicator_code": "Indicator", "value": "nope"}, ["Indicator", "Value"]
    )
    joined = " ".join(problems)
    assert "Required fields are not mapped" in joined
    assert "not in the file" in joined


def test_mapping_cannot_reuse_a_column() -> None:
    mapping = {f: "x" for f in ("indicator_code", "area_code")}
    assert any("only one field" in p for p in check_mapping(mapping, ["x"]))


def test_csv_parser_rejects_non_csv_and_binary_content() -> None:
    with pytest.raises(ApiError) as not_csv:
        parse_csv(b"a,b\n1,2\n", "data.xlsx")
    assert not_csv.value.code == "unsupported_format"
    with pytest.raises(ApiError) as binary:
        parse_csv(b"a,b\n\x00\x01,2\n", "data.csv")
    assert binary.value.code == "invalid_encoding"
    with pytest.raises(ApiError) as ragged:
        parse_csv(b"a,b\n1,2,3\n", "data.csv")
    assert ragged.value.code == "ragged_row"


def test_formula_cells_are_plain_text_and_neutralised_on_export() -> None:
    parsed = parse_csv(b'indicator_code,value\n"=HYPERLINK(""http://x"")",1\n', "data.csv")
    assert parsed.rows[0]["indicator_code"].startswith(
        "=HYPERLINK"
    )  # read as text, never evaluated
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("48000") == "48000"


def test_fixture_file_is_plain_csv_with_the_canonical_header() -> None:
    with FIXTURE.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert set(suggest_mapping(header)) >= {"indicator_code", "value", "partner_code", "flow"}
