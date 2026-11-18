"""Al Mulhim recognises in Arabic and English what a sentence asks OSRIP to run: a study, a
forecast, a scenario, a comparison or an analysis, so nobody has to open a Studies, Forecasts or
Scenarios page first. Rules only (routing.py); no model and no database."""

from __future__ import annotations

import pytest

from app.services.assistant import routing
from app.services.assistant.service import INTENT_RULES, MODE_RULES
from app.services.assistant.tools import tool_specs


@pytest.mark.parametrize(
    ("question", "mode", "wanted"),
    [
        # The owner's examples, 2026-11-18.
        ("Create a detailed study of electricity consumption in Oman.", "analyze", "study"),
        ("Forecast electricity demand in Oman.", "analyze", "forecast"),
        ("What happens if water demand increases by 15% over five years?", "scenario", "scenario"),
        ("حلل إنتاج الكهرباء في عمان", "analyze", None),
        ("أنشئ دراسة عن الأمن الغذائي", "analyze", "study"),
        ("تنبأ باستهلاك المياه", "analyze", "forecast"),
        ("اعمل سيناريو إذا زادت الواردات 20%", "scenario", "scenario"),
        ("قارن التجارة بين عامي 2024 و2025", "compare", None),
        ("Analyze electricity production in Oman.", "analyze", None),
        ("Create a food security study.", "analyze", "study"),
        ("Forecast water consumption.", "analyze", "forecast"),
        ("Create a scenario where imports increase by 20%.", "scenario", "scenario"),
        ("Compare trade in 2024 and 2025.", "compare", None),
        # Other wordings.
        ("Predict electricity generation for the next years", "analyze", "forecast"),
        ("ما توقعات إنتاج المياه في السنوات القادمة؟", "analyze", "forecast"),
        ("If demand grows 3% a year, what would generation need to be?", "scenario", "scenario"),
        ("ماذا يحدث إذا انخفضت الصادرات 10٪؟", "scenario", "scenario"),
        # Not a study, forecast or scenario.
        ("What was electricity generation in 2023?", "ask", None),
        ("How is percentage change calculated?", "ask", None),
        # «لماذا» (why) holds «اذا» (if): a question about the past, not a scenario.
        ("لماذا تضاعف توليد الكهرباء بين 2001 و2002؟", "analyze", None),
    ],
)
def test_the_request_picks_its_mode_and_what_to_run(
    question: str, mode: str, wanted: str | None
) -> None:
    assert routing.answer_mode(question, "auto") == mode
    assert routing.intent(question) == wanted


def test_a_mode_chosen_by_the_person_is_kept() -> None:
    assert routing.answer_mode("Forecast water consumption.", "quick") == "quick"
    assert routing.answer_mode("Create a food security study.", "research") == "research"


def test_a_stated_assumption_makes_a_scenario_even_with_the_word_forecast() -> None:
    assert routing.intent("Forecast what happens if imports increase by 20%") == "scenario"


def test_every_intent_has_its_rules_and_the_scenario_tool_follows_the_request() -> None:
    assert set(INTENT_RULES) == {"study", "forecast", "scenario"}
    assert "run_study" in INTENT_RULES["study"] and "Limitations" in INTENT_RULES["study"]
    assert (
        "get_forecast" in INTENT_RULES["forecast"] and "Never estimate" in INTENT_RULES["forecast"]
    )
    assert (
        "hypothetical" in INTENT_RULES["scenario"] and "clarification" in INTENT_RULES["scenario"]
    )
    names = lambda specs: {t["name"] for t in specs}  # noqa: E731
    plain = names(tool_specs(False, "analyze"))
    assert {"run_study", "get_forecast", "balance_analysis"} <= plain
    assert "scenario_projection" not in plain  # hypothetical arithmetic only when asked for
    assert "scenario_projection" in names(tool_specs(False, "analyze", scenario=True))
    assert "scenario_projection" in names(tool_specs(False, "scenario"))
    assert set(MODE_RULES) >= {"ask", "analyze", "compare", "scenario"}


def test_one_forecast_is_shown_per_series_the_most_informative() -> None:
    from app.services.assistant.service import shown_forecasts

    mistyped = {"id": "E1", "indicator": "water_consumption", "area": "OM", "status": "no_series"}
    withheld = {"id": "E2", "indicator": "WATER_CONSUMPTION", "area": "OM", "status": "withheld"}
    assert shown_forecasts([mistyped, withheld]) == [withheld]
    estimated = {"id": "E3", "indicator": "WATER_CONSUMPTION", "area": "OM", "status": "ok"}
    assert shown_forecasts([withheld, estimated]) == [estimated]
    other = {"id": "E4", "indicator": "ELEC_CONSUMPTION", "area": "OM-MU", "status": "withheld"}
    assert shown_forecasts([estimated, other]) == [estimated, other]
    # Nothing found at all: the one lookup is shown, so the reply can say no series matched.
    assert shown_forecasts([mistyped]) == [mistyped]
