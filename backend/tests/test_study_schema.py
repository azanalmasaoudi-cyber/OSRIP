"""The versioned study result and the allowlisted study parameters (no database).

A study result is the one object that tables, charts, exports and spoken summaries read, so
an inconsistent document must be refused before it is stored or shown.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain import study as schema
from app.services import studies

UNIT = {"code": "GWh", "label_en": "gigawatt-hours", "label_ar": "غيغاواط ساعة"}


def doc(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": "osrip.study/1",
        "kind": "trend",
        "status": "ok",
        "title": {"en": "Electricity generation", "ar": "توليد الكهرباء"},
        "question": {"en": "How has it changed?", "ar": "كيف تغيّر؟"},
        "params": {"indicator": "ELEC_GENERATION"},
        "data_mode": "synthetic",
        "dataset_versions": ["v1"],
        "periods": {"from": "2001-01-01", "to": "2002-12-31", "kind": "annual"},
        "findings": [{"text": {"en": "Latest 110.", "ar": "الأحدث 110."}, "evidence": ["S2"]}],
        "table": {
            "columns": [
                {"key": "period", "label": {"en": "Period", "ar": "الفترة"}, "kind": "period"},
                {
                    "key": "value",
                    "label": {"en": "Value", "ar": "القيمة"},
                    "kind": "number",
                    "unit": UNIT,
                },
            ],
            "rows": [{"period": "2001", "value": "100"}, {"period": "2002", "value": None}],
        },  # fmt: skip
        "charts": [
            {
                "type": "line",
                "title": {"en": "Generation", "ar": "التوليد"},
                "x": "period",
                "series": [
                    {"column": "value", "label": {"en": "v", "ar": "ق"}, "nature": "observed"}
                ],
            }
        ],
        "evidence": [
            {
                "id": f"S{n}",
                "indicator": "ELEC_GENERATION",
                "area": "OM",
                "period_start": f"200{n}-01-01",
                "period_end": f"200{n}-12-31",
                "value": "1",
                "unit": "GWh",
                "source_title": "t",
                "dataset_version": "v1",
            }
            for n in (1, 2)
        ],  # fmt: skip
        "method": {"en": "m", "ar": "م"},
    }
    out = copy.deepcopy(base)
    out.update(changes)
    return out


def test_a_consistent_document_validates_and_keeps_missing_as_none() -> None:
    result = schema.validate(doc())
    assert result["schema"] == "osrip.study/1"
    assert result["table"]["rows"][1]["value"] is None  # missing stays missing, never zero


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["table"]["columns"][1].pop("unit"), "needs a unit"),
        (lambda d: d["table"]["rows"].append({"period": "2003", "value": "n/a"}), "not a decimal"),
        (lambda d: d["table"]["rows"].append({"period": "2003", "extra": "1"}), "unknown columns"),
        (lambda d: d["charts"][0].update(x="year"), "unknown column"),
        (lambda d: d["charts"][0].update(type="pie"), "line"),
        (lambda d: d["charts"][0].update(type="heatmap"), "heatmap needs"),
        (lambda d: d["charts"][0]["series"][0].update(nature="guess"), "observed"),
        (lambda d: d["findings"][0].update(evidence=["S9"]), "unknown evidence"),
        (lambda d: d["evidence"].append(dict(d["evidence"][0])), "duplicate evidence"),
        (lambda d: d["table"].update(rows=[]), "at least one table row"),
        (lambda d: d.update(status="not_available"), "must say why"),
        (lambda d: d.update(kind="free_sql"), "kind"),
        (lambda d: d.update(schema="osrip.study/2"), "schema"),
        (lambda d: d.update(html="<script>"), "Extra inputs"),
    ],
)
def test_inconsistent_documents_are_refused(mutate, message: str) -> None:  # noqa: ANN001
    d = doc()
    mutate(d)
    with pytest.raises(ValidationError, match=message):
        schema.validate(d)


def test_every_study_kind_has_parameters_and_a_title() -> None:
    assert set(studies.PARAMS) == set(schema.STUDY_KINDS) == set(studies.BUILDERS)
    assert set(studies.CATALOG) == set(schema.STUDY_KINDS)
    for title in studies.CATALOG.values():
        assert title["en"] and title["ar"]


@pytest.mark.parametrize(
    ("kind", "params"),
    [
        ("trend", {"indicator": "ELEC_GENERATION; DROP TABLE observation"}),
        ("trend", {"indicator": "elec_generation"}),
        ("trend", {"indicator": "ELEC_GENERATION", "area": "OM' OR '1'='1"}),
        ("trend", {"indicator": "ELEC_GENERATION", "sql": "SELECT 1"}),
        ("trend", {"indicator": "ELEC_GENERATION", "period_kind": "weekly"}),
        ("growth", {"indicator": "ELEC_GENERATION", "from_year": 1800, "to_year": 2002}),
        ("scenario", {"indicator": "ELEC_GENERATION", "growth_pct": "900", "years": 3}),
        ("scenario", {"indicator": "ELEC_GENERATION", "growth_pct": "5", "years": 50}),
        ("import_dependence", {"commodity": "__import__('os').system('x')"}),
        ("programme_assessment", {"indicator": "ELEC_GENERATION", "objective": "x" * 400,
                                  "baseline_year": 2022, "target_value": "1", "target_year": 2030}),
    ],
)  # fmt: skip
def test_parameters_outside_the_allowlist_are_refused(kind: str, params: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        studies.PARAMS[kind].model_validate(params)


def test_period_keys_find_the_period_immediately_before() -> None:
    def o(start: str, end: str) -> dict[str, str]:
        return {"period_start": start, "period_end": end}

    key = studies._period_key
    assert key(o("2003-01-01", "2003-12-31"), "annual", back=True) == (2002,)
    assert key(o("2003-01-01", "2003-03-31"), "year_to_date", back=True) == (2002, 3)
    assert key(o("2003-01-01", "2003-01-31"), "monthly", back=True) == (2002, 12)
    assert key(o("2003-04-01", "2003-06-30"), "quarterly", back=True) == (2003, 1)
    assert key(o("2003-01-01", "2003-03-31"), "quarterly", back=True) == (2002, 10)


def test_csv_export_writes_the_table_as_shown_with_provenance() -> None:
    text = studies.export_csv(schema.validate(doc()), "ar")
    lines = text.splitlines()
    assert lines[0] == "# توليد الكهرباء"
    assert "data_mode=synthetic" in lines[1]
    assert any("SYNTHETIC" in line for line in lines)
    header = next(line for line in lines if not line.startswith("#"))
    assert header == "الفترة,القيمة (غيغاواط ساعة)"
    assert lines[-2:] == ["2001,100", "2002,"]  # missing is an empty cell, not 0
