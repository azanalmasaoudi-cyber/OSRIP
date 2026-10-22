"""Chronological series rules (pure): order, gaps, derivation by value type, year-to-date
totals kept apart, revisions between publications, and changes with zero denominators and
inexact values."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain import timeline as tl
from app.domain.enums import PhysicalDimension
from app.domain.quantities import Unit

GWH = Unit("GWh", PhysicalDimension.ENERGY)
SRC_A = {"id": "a", "source_code": "S01", "dataset_title": "Bulletin"}
SRC_B = {"id": "b", "source_code": "S02", "dataset_title": "Yearbook"}
V_OLD = {"id": "v1", "label": "v1", "published_at": "2026-01-10T00:00:00+00:00"}
V_NEW = {"id": "v2", "label": "v2", "published_at": "2026-09-10T00:00:00+00:00"}


def month(y: int, m: int, value: str | None, *, status: str | None = None,
          op: str | None = None, src: dict = SRC_A, ver: dict = V_NEW) -> tl.Published:  # fmt: skip
    return tl.Published(
        date(y, m, 1), tl.month_end(y, m), "monthly",
        None if value is None else Decimal(value), op, status, src, ver,
    )  # fmt: skip


def year(y: int, value: str, **kw) -> tl.Published:  # noqa: ANN003
    return tl.Published(date(y, 1, 1), date(y, 12, 31), "annual", Decimal(value),
                        kw.get("op"), kw.get("status"), kw.get("src", SRC_B),
                        kw.get("ver", V_NEW))  # fmt: skip


def ytd(y: int, end_month: int, value: str) -> tl.Published:
    return tl.Published(date(y, 1, 1), tl.month_end(y, end_month), "year_to_date",
                        Decimal(value), None, "provisional", SRC_A, V_NEW)  # fmt: skip


def build(published, view="monthly", value_type="period_total", **kw):  # noqa: ANN001, ANN003, ANN201
    return tl.build(published, value_type, view, GWH, "OM", **kw)


def values(t: tl.Timeline) -> list[tuple[str, str | None]]:
    return [(r.start.isoformat()[:7], r.out()["value"]) for r in t.rows]


def test_rows_are_in_time_order_whatever_the_input_order() -> None:
    t = build(
        [month(2024, 3, "3"), month(2023, 12, "12"), month(2024, 1, "1"), month(2024, 2, "2")]
    )
    assert [r.start for r in t.rows] == sorted(r.start for r in t.rows)
    assert values(t)[0] == ("2023-12", "12")
    # Month numbers sort as dates, not as text ("10" after "9").
    t = build([month(2024, 10, "10"), month(2024, 9, "9")])
    assert values(t) == [("2024-09", "9"), ("2024-10", "10")]


def test_missing_months_stay_missing_never_zero() -> None:
    t = build([month(2024, 1, "5"), month(2024, 3, "7"), month(2024, 4, None)])
    rows = {r.start.month: r for r in t.rows}
    assert rows[2].value is None and rows[2].nature == "missing"
    assert rows[2].status == "not_published"
    assert rows[4].value is None and rows[4].status == "missing_in_source"
    # A change against a missing month is not calculated.
    march = rows[3].changes[0]
    assert march["basis"] == "month_on_month" and march["status"] == "missing"
    assert march["absolute"] is None and march["percent"] is None


def test_annual_totals_are_never_split_into_months_or_quarters() -> None:
    t = build([year(2022, "100"), year(2023, "120")], view="monthly")
    assert t.rows == [] and t.available_views == ["annual"]
    q = build([year(2022, "100")], view="quarterly")
    assert q.rows == []


def test_quarters_and_years_from_complete_months_by_value_type() -> None:
    months = [month(2024, m, str(m)) for m in range(1, 13)]
    total = build(months, view="quarterly")
    assert values(total) == [("2024-01", "6"), ("2024-04", "15"), ("2024-07", "24"),
                             ("2024-10", "33")]  # fmt: skip
    assert all(r.nature == "derived" and r.basis == "sum_of_components" for r in total.rows)
    assert total.rows[0].components == ["2024-01", "2024-02", "2024-03"]
    assert "sum_of_components" in total.rules
    annual = build(months, view="annual")
    assert values(annual) == [("2024-01", "78")]
    # Levels are never added: the quarter takes its last month.
    stock = build(months, view="quarterly", value_type="end_of_period")
    assert values(stock) == [("2024-01", "3"), ("2024-04", "6"), ("2024-07", "9"),
                             ("2024-10", "12")]  # fmt: skip
    assert stock.rows[0].basis == "end_of_period" and "end_of_period" in stock.rules
    peak = build(months, view="annual", value_type="maximum")
    assert values(peak) == [("2024-01", "12")] and peak.rows[0].basis == "maximum_of_components"
    # Averages and ratios are not combined without weights.
    rate = build(months, view="quarterly", value_type="average")
    assert all(r.value is None for r in rate.rows)
    assert rate.rows[0].reason["code"] == "rate_not_derived"
    assert "not_derived_rate" in rate.rules


def test_an_incomplete_set_of_months_gives_no_total() -> None:
    t = build([month(2024, 1, "1"), month(2024, 2, "2")], view="quarterly")
    [q1] = t.rows
    assert q1.value is None and q1.reason["code"] == "components_incomplete"
    assert "2 of 3" in q1.reason["en"]
    assert t.available_views == ["monthly"]


def test_a_year_from_four_published_quarters() -> None:
    quarters = [
        tl.Published(
            tl.quarter_start(2024, q),
            tl.month_end(2024, 3 * q),
            "quarterly",
            Decimal(10 * q),
            None,
            None,
            SRC_A,
            V_NEW,
        )  # fmt: skip
        for q in range(1, 5)
    ]
    t = build(quarters, view="annual")
    assert values(t) == [("2024-01", "100")]
    assert t.rows[0].components == ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]


def test_year_to_date_totals_are_kept_apart_and_compared_with_the_same_months() -> None:
    t = build(
        [month(2026, 6, "5"), month(2026, 7, "6"), ytd(2025, 8, "100"), ytd(2026, 8, "110"),
         ytd(2026, 7, "95")],
    )  # fmt: skip
    assert all(r.frequency == "monthly" for r in t.rows)
    assert [(r.start.year, r.end.month) for r in t.year_to_date] == [
        (2025, 8),
        (2026, 7),
        (2026, 8),
    ]
    jan_aug = t.year_to_date[-1]
    assert jan_aug.changes[0]["percent"] == "10.00"
    # January-July 2026 has no January-July 2025 to compare with.
    assert t.year_to_date[1].changes == []
    assert "year_to_date_apart" in t.rules


def test_revisions_prefer_final_then_newer_and_keep_the_other_value() -> None:
    provisional = year(2024, "100", status="provisional", src=SRC_A, ver=V_NEW)
    final = year(2024, "104", status=None, src=SRC_B, ver=V_OLD)
    t = build([provisional, final], view="annual")
    [row] = t.rows
    assert row.value == Decimal("104") and row.source == SRC_B
    assert row.out()["revised"] is True
    assert row.others[0]["value"] == "100" and row.others[0]["revision_status"] == "provisional"
    assert "revised" in t.rules
    # Same value from two publications: one row, nothing flagged.
    same = build(
        [year(2023, "90", src=SRC_A), year(2023, "90", src=SRC_B, ver=V_OLD)], view="annual"
    )
    assert same.rows[0].others == [] and "revised" not in same.rules
    # Two provisional figures: the newer publication wins.
    newer = build([year(2022, "80", status="provisional", ver=V_OLD),
                   year(2022, "81", status="provisional", ver=V_NEW)], view="annual")  # fmt: skip
    assert newer.rows[0].value == Decimal("81")


def test_zero_denominators_and_inexact_values_give_no_percentage() -> None:
    t = build([month(2024, 1, "0"), month(2024, 2, "5"), month(2024, 3, "95", op=">"),
               month(2024, 4, "100")])  # fmt: skip
    feb = t.rows[1].changes[0]
    assert feb["absolute"] == "5" and feb["percent"] is None
    assert feb["status"] == "undefined" and feb["reason"]["code"] == "previous_value_zero"
    mar, apr = t.rows[2].changes[0], t.rows[3].changes[0]
    assert mar["status"] == "inexact" and apr["status"] == "inexact"
    assert mar["absolute"] is None and apr["percent"] is None


def test_year_on_year_for_months_and_quarters() -> None:
    t = build([month(2023, 5, "50"), month(2024, 4, "10"), month(2024, 5, "60")])
    may = next(r for r in t.rows if r.start == date(2024, 5, 1))
    bases = {c["basis"]: c for c in may.changes}
    assert bases["month_on_month"]["percent"] == "500.00"
    assert bases["year_on_year"]["percent"] == "20.00"


def test_period_range_and_digest() -> None:
    published = [month(2024, m, str(m)) for m in range(1, 7)]
    t = build(published, period_from=date(2024, 3, 1), period_to=date(2024, 4, 30))
    assert values(t) == [("2024-03", "3"), ("2024-04", "4")]
    # The same input gives the same dataset id; a different value a different one.
    assert build(published).digest() == build(list(reversed(published))).digest()
    changed = [*published[:-1], month(2024, 6, "60")]
    assert build(changed).digest() != build(published).digest()
