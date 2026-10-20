# ruff: noqa: E501 - the fixture document and bilingual examples keep one item per line
"""Shortage and surplus analysis without a database: the arithmetic, the classification and
priority rules, the document's validation, the exports' safety, and speech pronunciation."""

from __future__ import annotations

import copy
import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain import balance as schema
from app.domain import calculations as calc
from app.domain.enums import PhysicalDimension
from app.domain.quantities import GWH, MILLION_M3, Measurement, Period, Unit
from app.domain.results import CalcStatus, ReasonCode
from app.services import speech, studies
from app.services.analysis import balance, balance_export

Y2025 = Period(date(2025, 1, 1), date(2025, 12, 31))
Y2024 = Period(date(2024, 1, 1), date(2024, 12, 31))
PERCENT = Unit("percent", PhysicalDimension.RATIO)


def m(value: str | None, unit: Unit = GWH, period: Period = Y2025, area: str = "OM") -> Measurement:
    return Measurement(None if value is None else Decimal(value), unit, period, area)


# ------------------------------------------------------------------ arithmetic


def test_gap_is_supply_minus_demand_for_the_same_frame() -> None:
    r = calc.supply_demand_gap(m("120.5"), m("100"))
    assert r.status is CalcStatus.OK and r.value == Decimal("20.5")
    share = calc.gap_share_of_demand(r, m("100"))
    assert share.value == Decimal("20.5")


@pytest.mark.parametrize(
    ("supply", "demand", "status", "reason"),
    [
        (m(None), m("100"), CalcStatus.MISSING, ReasonCode.INPUT_MISSING),
        (m("100"), m(None), CalcStatus.MISSING, ReasonCode.INPUT_MISSING),
        (m("100"), m("90", MILLION_M3), CalcStatus.INCOMPATIBLE, ReasonCode.DIMENSION_MISMATCH),
        (
            m("100"),
            m("90", period=Y2024),
            CalcStatus.INCOMPATIBLE,
            ReasonCode.PERIOD_NOT_COMPARABLE,
        ),
        (
            m("100"),
            m("90", area="OM-MA"),
            CalcStatus.INCOMPATIBLE,
            ReasonCode.COVERAGE_NOT_COMPARABLE,
        ),
    ],
)
def test_missing_or_incompatible_inputs_never_produce_a_gap(supply, demand, status, reason) -> None:  # noqa: ANN001
    r = calc.supply_demand_gap(supply, demand)
    assert (r.status, r.reason, r.value) == (status, reason, None)
    # A missing gap never becomes a zero share either.
    assert calc.gap_share_of_demand(r, demand).value is None


def test_gap_share_needs_a_positive_demand() -> None:
    r = calc.supply_demand_gap(m("5"), m("0"))
    assert calc.gap_share_of_demand(r, m("0")).reason is ReasonCode.NON_POSITIVE_DENOMINATOR


def test_self_sufficiency_gap_is_ratio_minus_100_in_points() -> None:
    assert calc.self_sufficiency_gap(m("146", PERCENT)).value == Decimal("46")
    assert calc.self_sufficiency_gap(m("62", PERCENT)).value == Decimal("-38")
    assert calc.self_sufficiency_gap(m(None, PERCENT)).status is CalcStatus.MISSING
    assert calc.self_sufficiency_gap(m("-3", PERCENT)).reason is ReasonCode.NEGATIVE_RATIO
    assert calc.self_sufficiency_gap(m("90", GWH)).reason is ReasonCode.NOT_A_RATIO


def test_scenario_projection_compounds_the_stated_rate() -> None:
    assert calc.compound_projection(Decimal("100"), Decimal("10"), 2) == [
        Decimal("110.0"),
        Decimal("121.00"),
    ]
    assert calc.compound_projection(Decimal("100"), Decimal("0"), 1) == [Decimal("100")]


# ------------------------------------------------------------------ rules


@pytest.mark.parametrize(
    ("gap", "operator", "status"),
    [
        (Decimal("46"), None, "surplus"),
        (Decimal("-38"), None, "shortfall"),
        (Decimal("0"), None, "balanced"),
        (None, None, "not_determinable"),
        # "More than 95%" could be 96% or 130%: the direction is unknown.
        (Decimal("-5"), ">", "not_determinable"),
        (Decimal("5"), ">", "surplus"),
        (Decimal("-10"), "<", "shortfall"),
        (Decimal("2"), "~", "not_determinable"),
    ],
)
def test_self_sufficiency_status_respects_inequalities(gap, operator, status) -> None:  # noqa: ANN001
    assert balance._ssr_status(gap, operator) == status


@pytest.mark.parametrize(
    ("shortfall", "magnitude", "level"),
    [(True, Decimal("-76"), "high"), (True, Decimal("-23"), "high"), (True, Decimal("-4"), "medium"),
     (False, Decimal("46"), "medium"), (False, Decimal("4"), "low"), (False, None, "low")],
)  # fmt: skip
def test_priority_follows_the_documented_rule(
    shortfall: bool, magnitude: Decimal | None, level: str
) -> None:
    got, basis = balance._priority(shortfall, magnitude)
    assert got == level
    assert basis["en"].startswith("Score") and basis["ar"]


def test_scenario_parameters_must_come_together() -> None:
    with pytest.raises(ValidationError):
        balance.BalanceParams.model_validate({"sector": "trade", "years": 3})
    with pytest.raises(ValidationError):
        balance.BalanceParams.model_validate(
            {"sector": "trade", "supply_growth_pct": "99", "demand_growth_pct": "1", "years": 3}
        )
    with pytest.raises(ValidationError):
        balance.BalanceParams.model_validate({"sector": "fisheries"})
    p = balance.BalanceParams.model_validate(
        {"sector": "trade", "supply_growth_pct": "2", "demand_growth_pct": "4", "years": 3}
    )
    assert p.scenario


def test_ratio_scenario_is_labelled_and_never_observed() -> None:
    out = balance.SectorOut(
        scenario_base=("ratio", "B1", "2025", Decimal("146"), {"en": "Fish", "ar": "الأسماك"})
    )
    p = balance.BalanceParams.model_validate(
        {"sector": "food_security", "supply_growth_pct": "0", "demand_growth_pct": "10", "years": 2}
    )
    sc = balance._scenario(p, out)
    assert sc["status"] == "ok" and sc["balance"] == "B1"
    rows = sc["table"]["rows"]
    assert [r["basis"] for r in rows] == ["base", "scenario", "scenario"]
    # 146 x (1/1.1)^n: the stated assumption, unrounded arithmetic quantised to 4 places.
    assert rows[1]["ratio"] == "132.7273" and rows[2]["ratio"] == "120.6612"
    assert all(s["nature"] == "scenario" for c in sc["charts"] for s in c["series"])
    assert "not a forecast" in sc["assumptions"][0]["en"]


def test_scenario_without_a_determined_balance_says_why() -> None:
    out = balance.SectorOut(scenario_reason={"en": "No electricity balance.", "ar": "لا ميزان."})
    p = balance.BalanceParams.model_validate(
        {"sector": "electricity", "supply_growth_pct": "1", "demand_growth_pct": "2", "years": 1}
    )
    assert balance._scenario(p, out) == {"status": "not_applicable", "reason": out.scenario_reason}
    q = balance.BalanceParams.model_validate({"sector": "electricity"})
    assert balance._scenario(q, out)["status"] == "not_requested"


# ------------------------------------------------------------------ the document


def T(en: str, ar: str = "ع") -> dict[str, str]:  # noqa: N802
    return {"en": en, "ar": ar}


UNIT = {"code": "million_OMR", "label_en": "million OMR", "label_ar": "مليون ريال عماني"}


def doc() -> dict[str, Any]:
    source = {
        "id": "S1", "indicator": "TRADE_MERCH_EXPORTS", "indicator_name": T("Exports"), "area": "OM",
        "area_name": T("Oman"), "period_start": "2025-01-01", "period_end": "2025-12-31", "period_label": "2025",
        "period_kind": "annual", "value": "23264", "unit": UNIT, "publisher": "NCSI", "title": "Monthly bulletin",
        "url": "https://www.ncsi.gov.om/", "dataset_version": "v1", "data_status": "approved_official",
    }  # fmt: skip
    return {
        "schema": schema.SCHEMA, "kind": "supply_balance", "sector": "trade", "status": "ok",
        "title": T("Shortage and surplus: Trade"), "question": T("Where?"), "params": {"sector": "trade"},
        "data_mode": "verified_source", "dataset_versions": ["v1"], "summary": [T("Surplus.")],
        "balances": [{
            "id": "B1", "code": "TRADE_MERCHANDISE", "title": T("Merchandise trade balance"), "status": "surplus",
            "status_label": T("Trade surplus"), "reason": T("Exports minus imports."), "interpretation": T("Not profit."),
            "period": "2025", "period_kind": "annual", "gap": "6103", "gap_unit": UNIT,
            "table": {"columns": [
                {"key": "period", "label": T("Period"), "kind": "period"},
                {"key": "balance", "label": T("Balance"), "kind": "number", "unit": UNIT},
                {"key": "note", "label": T("Note"), "kind": "text"},
            ], "rows": [{"period": "2025", "balance": "6103", "note": "ok"}, {"period": "2024", "balance": None, "note": None}]},
            "charts": [], "evidence": ["S1"],
        }],
        "recommendations": [{
            "id": "R1", "balance": "B1", "problem": T("A surplus"), "evidence": T("6103"), "evidence_ids": ["S1"],
            "action": T("Widen non-oil exports"), "quantity": None, "quantity_unit": None,
            "quantity_note": T("Not quantified."), "horizon": "long", "constraints": T("Market access."),
            "cost": balance.COST_UNKNOWN, "outcome": T("Less exposure."), "priority": "high",
            "priority_basis": T("Rule."), "kpi": T("Non-oil share"), "nature": "recommendation",
        }],
        "prioritization": balance.PRIORITIZATION, "data_gaps": [{"id": "G1", "balance": "B1", "missing": T("Demand"), "blocks": T("Product view")}],
        "scenario": {"status": "not_requested", "reason": T("No assumptions.")},
        "forecast": {"status": "withheld", "indicator": "TRADE_MERCH_IMPORTS", "text": T("Withheld.")},
        "sources": [source], "method": T("Exports minus imports."), "assumptions": [], "limitations": [],
    }  # fmt: skip


def test_a_consistent_analysis_validates_and_keeps_missing_as_none() -> None:
    out = schema.validate(doc())
    assert out["balances"][0]["table"]["rows"][1]["balance"] is None
    assert out["recommendations"][0]["cost_known"] is False


def _set(path: list[Any], value: Any):  # noqa: ANN202, ANN401
    def mutate(d: dict[str, Any]) -> None:
        target = d
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_set(["balances", 0, "gap"], None), "needs its gap"),
        (_set(["balances", 0, "evidence"], []), "needs its evidence"),
        (_set(["balances", 0, "status"], "not_determinable"), "carries no gap"),
        (_set(["balances", 0, "evidence"], ["S9"]), "unknown evidence"),
        (_set(["recommendations", 0, "evidence_ids"], ["S9"]), "unknown evidence"),
        (_set(["recommendations", 0, "quantity"], "12"), "needs its unit"),
        (_set(["recommendations", 0, "cost_known"], True), "False"),
        (_set(["balances", 0, "table", "rows", 0, "balance"], "lots"), "not a decimal"),
        (_set(["status"], "partial"), "status must be"),
        (_set(["data_gaps", 0, "balance"], "B7"), "unknown balance"),
    ],
)
def test_inconsistent_analyses_are_refused(mutate, message: str) -> None:  # noqa: ANN001
    d = copy.deepcopy(doc())
    mutate(d)
    with pytest.raises(ValidationError, match=message):
        schema.validate(d)


def test_a_scenario_chart_may_not_draw_an_observed_series() -> None:
    d = copy.deepcopy(doc())
    d["scenario"] = {
        "status": "ok", "assumptions": [T("Stated.")], "balance": "B1",
        "table": {"columns": [{"key": "period", "label": T("Year"), "kind": "period"},
                              {"key": "gap", "label": T("Gap"), "kind": "number", "unit": UNIT}],
                  "rows": [{"period": "2026", "gap": "1"}]},
        "charts": [{"type": "line", "title": T("Gap"), "x": "period", "unit": UNIT,
                    "series": [{"column": "gap", "label": T("Gap"), "nature": "observed"}]}],
    }  # fmt: skip
    with pytest.raises(ValidationError, match="scenario series"):
        schema.validate(d)


# ------------------------------------------------------------------ exports


HOSTILE = ['=HYPERLINK("http://x")', "+SUM(A1)", "@cmd", "-2+3", "\tTAB"]


def test_csv_neutralises_formulas_but_keeps_numbers() -> None:
    d = copy.deepcopy(doc())
    d["balances"][0]["table"]["rows"] = [
        {"period": "2025", "balance": "-219", "note": h} for h in HOSTILE
    ] + [{"period": "2024", "balance": None, "note": None}]
    d["recommendations"][0]["action"] = T("=1+1", "=1+1")
    text = balance_export.export_csv(schema.validate(d), "en")
    rows = list(csv.reader(io.StringIO(text)))
    cells = [c for r in rows for c in r]
    for h in HOSTILE:
        assert "'" + h in cells, h
        assert h not in cells
    assert "'=1+1" in cells
    assert "-219" in cells, "a negative number stays a number"
    assert ["2024", "", ""] in rows, "a missing value is an empty cell, never zero"
    # Every cell that a spreadsheet would treat as a formula is prefixed.
    assert not [c for c in cells if c[:1] in ("=", "+", "@", "\t")]


def test_csv_is_bilingual() -> None:
    text = balance_export.export_csv(schema.validate(doc()), "ar")
    assert "الإجراء المقترح" in text and "مؤشر المتابعة" in text


def test_report_escapes_everything_and_runs_nothing() -> None:
    d = copy.deepcopy(doc())
    d["title"] = T("<script>alert(1)</script>", "<img src=x onerror=alert(1)>")
    d["sources"][0]["url"] = "javascript:alert(1)"
    d["balances"][0]["table"]["rows"][0]["note"] = "<b>bold</b>"
    for language in ("en", "ar"):
        html = balance_export.export_html(schema.validate(d), language)
        assert "<script" not in html.lower() and "<img" not in html.lower()
        assert "&lt;script&gt;" in html or "&lt;img" in html
        assert 'href="javascript' not in html, "only http(s) source links become links"
        assert "&lt;b&gt;bold&lt;/b&gt;" in html
    ar = balance_export.export_html(schema.validate(d), "ar")
    assert '<html lang="ar" dir="rtl">' in ar


def test_study_csv_neutralises_text_cells_too() -> None:
    from tests.test_study_schema import doc as study_doc

    d = study_doc()
    text_col = next(c for c in d["table"]["columns"] if c["kind"] != "number")
    d["table"]["rows"][0][text_col["key"]] = "=cmd|' /C calc'!A0"
    out = studies.export_csv(d, "en")
    assert "'=cmd" in out and "\n=cmd" not in out and ",=cmd" not in out


# ------------------------------------------------------------------ speech


@pytest.mark.parametrize(
    ("language", "text", "spoken"),
    [
        ("en", "Exports 23,264 million OMR [E3].", "Exports 23264 million Omani rials."),
        (
            "en",
            "Consumption +23.6% between 2022–2025",
            "Consumption plus 23.6 percent between 2022 to 2025",
        ),
        ("en", "41,234 GWh and 812 MW", "41234 gigawatt hours and 812 megawatts"),
        ("en", "1,050 million m³ [S2]", "1050 million cubic metres"),
        ("ar", "بلغ 41,234 GWh بزيادة 3.5٪ [E1]", "بلغ 41234 غيغاواط ساعة بزيادة 3.5 بالمئة"),
        (
            "ar",
            "6,103 مليون ريال عماني و-219 million_OMR",
            "6103 مليون ريال عماني و-219 مليون ريال عماني",
        ),
        ("ar", "46 percentage_points", "46 نقطة مئوية"),
    ],
)
def test_numbers_and_units_are_written_as_they_are_said(
    language: str, text: str, spoken: str
) -> None:
    assert speech.speakable(text, language) == spoken


def test_reading_without_a_language_only_drops_markers() -> None:
    assert speech.speakable("Up 3% [E2] in 2025–2026.") == "Up 3% in 2025–2026."


def test_voice_check_without_a_service_verifies_nothing(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "speech_provider", "")
    out = speech.voice_check({"ar": "ar-OM-AyshaNeural", "en": "en-GB-SoniaNeural"})
    assert out["configured"] is False
    assert {v["verified"] for v in out["voices"].values()} == {None}


def test_voice_check_reads_the_provider_list(monkeypatch) -> None:  # noqa: ANN001
    import httpx
    from pydantic import SecretStr

    from app.core.config import get_settings

    class Client:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, url: str, **kwargs: Any):  # noqa: ANN201, ANN401
            assert url.endswith("/cognitiveservices/voices/list")
            assert kwargs["headers"]["Ocp-Apim-Subscription-Key"] == "test-only-not-a-key"
            voices = [{"ShortName": "ar-OM-AyshaNeural", "Locale": "ar-OM", "Gender": "Female"},
                      {"ShortName": "en-GB-SoniaNeural", "Locale": "en-GB", "Gender": "Female"}]  # fmt: skip
            return httpx.Response(200, json=voices, request=httpx.Request("GET", url))

    s = get_settings()
    monkeypatch.setattr(s, "speech_provider", "azure")
    monkeypatch.setattr(s, "speech_key", SecretStr("test-only-not-a-key"))
    monkeypatch.setattr(s, "speech_region", "testregion")
    monkeypatch.setattr(speech, "http_client_factory", lambda timeout: Client())
    monkeypatch.setitem(speech._VOICES_CACHE, "voices", None)
    out = speech.voice_check({"ar": "ar-OM-AyshaNeural", "en": "en-US-NotAVoice"})
    assert out["voices"]["ar"] == {
        "name": "ar-OM-AyshaNeural",
        "verified": True,
        "locale": "ar-OM",
        "gender": "Female",
    }
    assert out["voices"]["en"]["verified"] is False
    monkeypatch.setitem(speech._VOICES_CACHE, "voices", None)
