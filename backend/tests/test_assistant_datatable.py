"""Tables and charts in the conversation are built by the backend from published rows
(datatable.py): one validated table per unit, in period order, missing values kept missing;
a chart only over compatible rows (one unit, one kind of period, at least two values)."""

from __future__ import annotations

from typing import Any

from app.services.assistant import datatable


def _row(n: int, indicator: str, start: str, end: str, value: str | None, *, unit: str = "GWh",
         kind: str = "annual", area: str = "OM") -> dict[str, Any]:  # fmt: skip
    return {
        "evidence_id": f"E{n}",
        "indicator_code": indicator,
        "indicator_name": {"en": indicator.title(), "ar": indicator},
        "area": area,
        "area_name": {"en": "Oman", "ar": "عُمان"},
        "period_kind": kind,
        "period_start": start,
        "period_end": end,
        "period_complete": kind != "year_to_date",
        "value": value,
        "value_operator": None,
        "unit": unit,
        "unit_label": {"en": unit, "ar": unit},
        "revision_status": None,
        "source": {
            "title": "Statistical Year Book 2026",
            "publisher": "NCSI",
            "url": "https://www.ncsi.gov.om/x",
        },
    }


def test_one_table_per_unit_in_period_order_with_missing_kept_missing() -> None:
    rows = [
        _row(1, "ELEC_CONSUMPTION", "2024-01-01", "2024-12-31", "42156.3"),
        _row(2, "ELEC_CONSUMPTION", "2022-01-01", "2022-12-31", "36427.1"),
        _row(3, "ELEC_CONSUMPTION", "2023-01-01", "2023-12-31", None),
        _row(4, "ELEC_INSTALLED_CAPACITY", "2023-01-01", "2023-12-31", "10531.6", unit="MW"),
    ]
    tables = datatable.build_tables(rows)
    assert [t["unit"]["code"] for t in tables] == ["GWh", "MW"]
    gwh = tables[0]
    assert [r["period"] for r in gwh["table"]["rows"]] == ["2022", "2023", "2024"]
    assert [r["value"] for r in gwh["table"]["rows"]] == ["36427.1", None, "42156.3"]
    assert [c["key"] for c in gwh["table"]["columns"]] == [
        "period", "indicator", "value", "unit", "geography", "source",
    ]  # fmt: skip


def test_year_to_date_is_labelled_and_never_drawn_beside_full_years() -> None:
    ytd = _row(
        1, "ELEC_GROSS_GENERATION", "2026-01-01", "2026-07-31", "31732.5", kind="year_to_date"
    )
    assert (
        datatable.period_text(ytd["period_start"], ytd["period_end"], "year_to_date")
        == "2026 Jan–Jul"
    )
    mixed = [ytd, _row(2, "ELEC_GROSS_GENERATION", "2025-01-01", "2025-12-31", "50973.5")]
    out = datatable.build_chart(mixed, {"en": "t", "ar": "t"})
    assert out == {
        "status": "not_comparable",
        "reason": "different_kinds_of_period",
        "kinds": ["annual", "year_to_date"],
    }


def test_a_chart_needs_two_values_and_one_unit() -> None:
    one = [_row(1, "ELEC_CONSUMPTION", "2025-01-01", "2025-12-31", "45033.1")]
    assert datatable.build_chart(one, {"en": "t", "ar": "t"})["status"] == "insufficient_points"
    units = [
        one[0],
        _row(2, "ELEC_INSTALLED_CAPACITY", "2025-01-01", "2025-12-31", "11796.6", unit="MW"),
    ]
    assert datatable.build_chart(units, {"en": "t", "ar": "t"})["reason"] == "different_units"


def test_the_chart_draws_exactly_the_table_rows() -> None:
    rows = [
        _row(i, ind, f"{y}-01-01", f"{y}-12-31", v)
        for i, (ind, y, v) in enumerate(
            [("ELEC_CONSUMPTION", 2022, "36427.1"), ("ELEC_CONSUMPTION", 2023, "39296.0"),
             ("ELEC_CONSUMPTION", 2024, "42156.3"), ("ELEC_DISTRIBUTION", 2022, "36178.6"),
             ("ELEC_DISTRIBUTION", 2023, "39296.0"), ("ELEC_DISTRIBUTION", 2024, None)],
            start=1,
        )
    ]  # fmt: skip
    out = datatable.build_chart(rows, {"en": "Electricity", "ar": "الكهرباء"})
    assert out["status"] == "ok" and out["type"] == "line" and out["points"] == 5
    assert out["table"]["rows"] == [
        {"period": "2022", "s0": "36427.1", "s1": "36178.6"},
        {"period": "2023", "s0": "39296.0", "s1": "39296.0"},
        {"period": "2024", "s0": "42156.3", "s1": None},  # missing stays missing
    ]
    assert [s["column"] for s in out["chart"]["series"]] == ["s0", "s1"]
    # Areas for one period are categories: bars.
    areas = [
        _row(1, "ELEC_CONSUMPTION", "2024-01-01", "2024-12-31", "100", area="OM-MA"),
        _row(2, "ELEC_CONSUMPTION", "2024-01-01", "2024-12-31", "90", area="OM-ZU"),
    ]
    assert datatable.build_chart(areas, {"en": "t", "ar": "t"})["type"] == "bar"
