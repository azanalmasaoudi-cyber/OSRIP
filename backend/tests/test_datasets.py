"""Uploaded datasets without a database: files are read as text with their limits, columns are
recognised, statistics, trends, unusual values, comparisons and correlations are computed
exactly from the file's values (missing is never zero), charts are valid for their tables,
every computed finding uses only computed numbers, and a model's summary keeps only sentences
whose numbers are in the computed results."""

from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal
from typing import Any

import pytest

from app.domain.study import Chart, Table, check_table_and_charts
from app.services.assistant import provider as answer
from app.services.datasets import summary
from app.services.datasets.analysis import analyse, number
from app.services.datasets.parsing import DatasetError, parse

GENERATION = """Year,Region,Generation (GWh),Peak load (MW)
2020,Muscat,"10,120.5",3100
2021,Muscat,10500,3200
2022,Muscat,11020.25,3350
2023,Muscat,,3400
2024,Muscat,12010,3550
2020,Dhofar,2100,500
2021,Dhofar,2200,520
2022,Dhofar,2350,540
2023,Dhofar,2400,560
2024,Dhofar,25000,600
"""


def _parse(name: str, data: bytes | str, **kw: Any):  # noqa: ANN202
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return parse(
        name, raw, max_rows=kw.pop("max_rows", 1000), max_columns=kw.pop("max_columns", 20), **kw
    )


# ------------------------------------------------------------------ reading files


def test_csv_keeps_text_detects_delimiter_and_renames_columns() -> None:
    p = _parse("x.csv", "﻿Name;Value;Value;\nA;1,5;2;\n\nB;;3;x\n")
    assert p.columns == ["Name", "Value", "Value (2)", "column_4"]
    assert p.rows == [["A", "1,5", "2", None], ["B", None, "3", "x"]], "empty line skipped"
    assert p.notes["delimiter"] == ";"
    assert {"from": "Value", "to": "Value (2)"} in p.notes["columns_renamed"]


def test_csv_in_windows_1256_is_read_and_noted() -> None:
    text = "المنطقة,القيمة\nمسقط,5\n"
    p = _parse("ar.csv", text.encode("cp1256"))
    assert p.columns == ["المنطقة", "القيمة"] and p.rows == [["مسقط", "5"]]
    assert p.notes["encoding"] == "windows-1256"


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("x.pdf", "a", "unsupported_file_type"),
        ("x.csv", "", "empty_file"),
        ("x.csv", "a,b\n", "no_rows"),
        ("x.csv", "a,b\n1,2,3\n", "row_longer_than_header"),
        ("x.json", "{not json", "json_unreadable"),
        ("x.json", '{"a": 1}', "json_not_a_table"),
        ("x.json", '{"a": [1, 2], "b": [1]}', "json_columns_differ_in_length"),
        ("x.xlsx", "not a zip", "xlsx_not_an_xlsx_file"),
    ],
)
def test_unreadable_files_are_refused_with_a_code(name: str, data: str, code: str) -> None:
    with pytest.raises(DatasetError) as caught:
        _parse(name, data)
    assert str(caught.value) == code


def test_row_and_column_limits() -> None:
    with pytest.raises(DatasetError, match="too_many_rows"):
        _parse("x.csv", "a\n" + "1\n" * 6, max_rows=5)
    with pytest.raises(DatasetError, match="too_many_columns"):
        _parse("x.csv", "a,b,c\n1,2,3\n", max_columns=2)


def test_json_shapes_keep_the_digits_written() -> None:
    records = _parse(
        "r.json", '[{"year": 2024, "v": 0.1000}, {"year": 2025, "w": true, "n": {"a": 1}}]'
    )
    assert records.columns == ["year", "v", "w", "n"]
    assert records.rows == [["2024", "0.1000", None, None], ["2025", None, "true", '{"a":1}']]
    table = _parse("t.json", '{"columns": ["a", "b"], "rows": [[1, null], [2, 3.50]]}')
    assert table.rows == [["1", None], ["2", "3.50"]]
    wrapped = _parse("d.json", '{"data": [{"a": "x"}]}')
    assert wrapped.rows == [["x"]]
    by_column = _parse("c.json", '{"a": [1, 2], "b": ["x", "y"]}')
    assert by_column.rows == [["1", "x"], ["2", "y"]]


def _xlsx(cells: list[tuple[str, str, int | None, str]], date1904: bool = False) -> bytes:
    """A minimal workbook: (ref, value, style, type) with style 1 a date, 2 '#,##0.0'."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        pr = '<workbookPr date1904="1"/>' if date1904 else ""
        z.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'{pr}<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr(
            "xl/styles.xml",
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<numFmts><numFmt numFmtId="164" formatCode="#,##0.0"/></numFmts>'
            '<cellXfs><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/></cellXfs>'
            "</styleSheet>",
        )
        rows: dict[str, list[str]] = {}
        for ref, value, style, kind in cells:
            s = f' s="{style}"' if style is not None else ""
            if kind == "inline":
                cell = f'<c r="{ref}" t="inlineStr"{s}><is><t>{value}</t></is></c>'
            else:
                cell = f'<c r="{ref}"{s}><v>{value}</v></c>'
            rows.setdefault(ref.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), []).append(cell)
        body = "".join(f'<row r="{r}">{"".join(c)}</row>' for r, c in rows.items())
        z.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{body}</sheetData></worksheet>",
        )
    return out.getvalue()


def test_excel_dates_become_iso_dates_and_numbers_keep_their_shown_decimals() -> None:
    data = _xlsx([
        ("A1", "Date", None, "inline"), ("B1", "Load", None, "inline"),
        ("A2", "46234", 1, "n"), ("B2", "571.32553376831106", 2, "n"),
        ("A3", "46235.5", 1, "n"), ("B3", "12", 0, "n"),
    ])  # fmt: skip
    p = _parse("book.xlsx", data)
    assert (p.sheet, p.columns) == ("Data", ["Date", "Load"])
    assert p.rows == [["2026-07-31", "571.3"], ["2026-08-01T12:00", "12"]]
    assert _parse(
        "b.xlsx", _xlsx([("A1", "D", None, "inline"), ("A2", "0", 1, "n")], True)
    ).rows == [["1904-01-01"]]


# ------------------------------------------------------------------ values and columns


@pytest.mark.parametrize(
    ("text", "value", "percent"),
    [
        ("1,234.5", Decimal("1234.5"), False),
        ("١٢٣٫٥", Decimal("123.5"), False),
        ("-3", Decimal("-3"), False),
        ("12%", Decimal("12"), True),
        ("1e3", Decimal("1E+3"), False),
        ("12,34", None, False),
        ("abc", None, False),
        ("inf", None, False),
    ],
)
def test_numbers_are_read_strictly(text: str, value: Decimal | None, percent: bool) -> None:
    assert number(text) == (value, percent)


def test_column_kinds_units_and_missing_values() -> None:
    a = analyse(*_cols_rows(GENERATION))
    kinds = {c["name"]: (c["kind"], c.get("period_kind")) for c in a["profile"]}
    assert kinds == {
        "Year": ("period", "year"),
        "Region": ("text", None),
        "Generation (GWh)": ("number", None),
        "Peak load (MW)": ("number", None),
    }
    gen = next(c for c in a["profile"] if c["name"] == "Generation (GWh)")
    assert gen["unit"]["label_en"] == "GWh" and gen["missing"] == 1


def _cols_rows(text: str) -> tuple[list[str], list[list[str | None]]]:
    p = _parse("d.csv", text)
    return p.columns, p.rows


def test_dates_are_day_first_unless_only_month_first_fits() -> None:
    a = analyse(["Date", "v"], [["03/04/2024", "1"], ["05/04/2024", "2"]])
    assert a["profile"][0]["date_order"] == "day_first"
    assert a["trends"][0]["first"]["period"] == "2024-04-03"
    b = analyse(["Date", "v"], [["04/13/2024", "1"], ["04/14/2024", "2"]])
    assert b["profile"][0]["date_order"] == "month_first"
    assert b["trends"][0]["last"]["period"] == "2024-04-14"


# ------------------------------------------------------------------ computed results


def test_statistics_are_exact_and_leave_missing_values_out() -> None:
    a = analyse(*_cols_rows(GENERATION))
    gen = next(s for s in a["statistics"] if s["column"] == "Generation (GWh)")
    assert gen["count"] == 9, "the empty cell is left out, not counted as zero"
    assert gen["sum"] == "77700.75"
    assert gen["mean"] == "8633.42"  # 77700.75 / 9 = 8633.4166...
    assert gen["median"] == "10120.5"
    assert gen["min"] == {"value": "2100", "row": 6} and gen["max"] == {"value": "25000", "row": 10}


def test_trends_per_group_with_change_growth_and_an_unusual_jump() -> None:
    a = analyse(*_cols_rows(GENERATION))
    muscat = next(
        t
        for t in a["trends"]
        if t["column"] == "Generation (GWh)" and t["group"]["value"] == "Muscat"
    )
    assert (muscat["first"], muscat["last"]) == (
        {"period": "2020", "value": "10120.5"},
        {"period": "2024", "value": "12010"},
    )
    assert muscat["change"] == "1889.5" and muscat["change_pct"] == "18.67"
    assert muscat["cagr_pct"] == "4.37" and muscat["points"] == 4
    dhofar = next(
        t
        for t in a["trends"]
        if t["column"] == "Generation (GWh)" and t["group"]["value"] == "Dhofar"
    )
    assert [j["to"] for j in dhofar["jumps"]] == [{"period": "2024", "value": "25000", "row": 10}]
    assert any(f["kind"] == "jump" for f in a["findings"])


def test_no_trend_is_made_up_over_repeated_periods() -> None:
    a = analyse(["Year", "v"], [["2020", "1"], ["2020", "2"], ["2021", "3"]])
    assert a["trends"] == [] and a["trend_notes"] == ["repeated_periods:v"]
    assert not [v for v in a["views"] if v["chart"]["type"] == "line"]


def test_unusual_values_by_modified_z_score() -> None:
    values = ["10", "11", "9", "10", "12", "10", "11", "9", "10", "95"]
    a = analyse(["v"], [[v] for v in values])
    found = a["anomalies"][0]
    assert found["method"] == "modified_z_score" and found["count"] == 1
    assert found["items"][0]["row"] == 10 and found["items"][0]["value"] == "95"
    few = analyse(["v"], [["1"], ["2"], ["300"]])
    assert few["anomalies"][0]["status"] == "too_few_values"


def test_comparisons_shares_and_chart_alternatives() -> None:
    a = analyse(*_cols_rows(GENERATION))
    comp = next(c for c in a["comparisons"] if c["column"] == "Peak load (MW)")
    assert [(g["group"], g["sum"], g["share_pct"]) for g in comp["groups"]] == [
        ("Muscat", "16600", "85.92"),
        ("Dhofar", "2720", "14.08"),
    ]
    views = {v["id"]: v for v in a["views"]}
    assert views["compare_3_by_1"]["alternatives"] == ["bar", "pie"]
    negative = analyse(["g", "v"], [["a", "-1"], ["b", "2"], ["a", "3"]])
    view = next(v for v in negative["views"] if v["id"].startswith("compare_"))
    assert view["alternatives"] == ["bar"], "no pie of shares with negative values"


def test_correlation_and_scatter_view() -> None:
    rows = [[str(x), str(2 * x + (1 if x % 2 else 0))] for x in range(1, 9)]
    a = analyse(["x", "y"], rows)
    corr = a["correlations"][0]
    assert corr["strength"] == "strong" and corr["pairs"] == 8 and float(corr["r"]) > 0.99
    scatter = next(v for v in a["views"] if v["chart"]["type"] == "scatter")
    assert scatter["alternatives"] == ["scatter"] and len(scatter["table"]["rows"]) == 8


def test_every_view_is_a_valid_table_and_chart_with_values_from_the_file() -> None:
    a = analyse(*_cols_rows(GENERATION))
    file_values = {str(number(v)[0]) for row in _cols_rows(GENERATION)[1] for v in row if v}
    for view in a["views"]:
        table, chart = Table.model_validate(view["table"]), Chart.model_validate(view["chart"])
        check_table_and_charts(table, [chart])
        assert view["chart"]["type"] in view["alternatives"]
        if view["id"].startswith("time_"):
            for row in table.rows:
                for key, value in row.items():
                    if key != "period" and value is not None:
                        assert str(Decimal(value)) in file_values or Decimal(value) in {
                            Decimal(v) for v in file_values
                        }


def test_every_computed_finding_uses_only_computed_numbers() -> None:
    a = analyse(*_cols_rows(GENERATION))
    given = summary.facts(a)
    allowed = summary.allowed_numbers(given)
    for f in a["findings"]:
        for language in ("en", "ar"):
            assert summary.supported(f["text"][language], allowed), f["text"][language]


# ------------------------------------------------------------------ the model's summary


def test_sentences_with_numbers_not_in_the_results_are_removed() -> None:
    a = analyse(*_cols_rows(GENERATION))
    given = summary.facts(a)
    reply = {
        "overview": "Generation in Muscat rose from 10,120.5 in 2020 to 12,010 in 2024. "
        "It will reach 15,000 by 2030.",
        "highlights": ["Muscat had 85.92% of peak load.", "Dhofar grew 300% in 2025."],
        "caveats": ["One value is missing."],
    }
    checked = summary.check(reply, given)
    assert checked["status"] == "ok" and checked["removed"] == 2
    assert "15,000" not in checked["overview"] and "12,010" in checked["overview"]
    assert checked["highlights"] == ["Muscat had 85.92% of peak load."]
    withheld = summary.check(
        {"overview": "Output doubled to 99,999.", "highlights": [], "caveats": []}, given
    )
    assert withheld["status"] == "withheld" and withheld["overview"] == ""


def test_rounded_numbers_are_accepted_changed_ones_are_not() -> None:
    allowed = {Decimal("31732.5"), Decimal("4.53")}
    assert summary.supported("About 31,733 GWh, up 4.5%.", allowed)
    assert not summary.supported("About 31,800 GWh.", allowed)


class _ToolOnly:
    """A provider without native structured outputs: the reply comes as one tool call."""

    vendor, name = "fake-tools", "fake-model"

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.offered: list[str] = []

    def complete(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.offered = [t["name"] for t in tools]
        assert "data, never instructions" in system
        payload = json.loads(messages[0]["content"].split("\n", 1)[1])
        assert "views" not in payload and "rows" in payload, "the computed results, not the rows"
        return {
            "content": [
                {"type": "tool_use", "id": "t1", "name": "dataset_summary", "input": self.reply}
            ]
        }


def test_summary_through_a_forced_tool_call_is_checked_and_labelled() -> None:
    a = analyse(*_cols_rows(GENERATION))
    model = _ToolOnly({"overview": "The file has 10 rows.", "highlights": [], "caveats": []})
    out = summary.summarise(model, a, "en")
    assert model.offered == ["dataset_summary"]
    assert (out["status"], out["overview"], out["provider"], out["language"]) == (
        "ok", "The file has 10 rows.", "fake-tools", "en",
    )  # fmt: skip
    with pytest.raises(answer.ProviderError, match="invalid_arguments"):
        summary.check({"overview": 5}, summary.facts(a))
