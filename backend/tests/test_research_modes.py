"""The three assistant modes without a database: each mode's tools (Internet research never
reaches OSRIP's datasets unless the person asks for them, and run_tool refuses them even if the
model asks), the model per mode, the analysis of web figures (calculations, tables, charts and
diagrams only from cited figures), the routing phrases in Arabic and English, and the image
service being off unless configured."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import get_settings
from app.domain.enums import DataMode
from app.services import images
from app.services.assistant import routing, web_analysis
from app.services.assistant.provider import FakeProvider, get_provider
from app.services.assistant.tools import Ledger, Tools, allowed_tools, run_tool, tool_specs

# OSRIP's own datasets and functions: never offered to the internet modes by default.
INTERNAL = {
    "list_indicators", "list_areas", "get_observations", "latest_period", "compare_periods",
    "explain_calculation", "get_forecast", "make_table", "balance_analysis", "growth_rate",
    "share_of_total", "compare_areas", "run_study", "data_quality_notes",
}  # fmt: skip


def names(specs: list[dict[str, Any]]) -> set[str]:
    return {t["name"] for t in specs}


@pytest.mark.parametrize("mode", ["quick", "research"])
def test_internet_modes_offer_the_web_and_no_internal_data(mode: str) -> None:
    offered = names(tool_specs(False, mode))
    assert {"web_search", "read_web_page", "calculate", "research_table", "final_answer"} <= offered
    assert not offered & INTERNAL
    # The research plan belongs to Deep research only.
    assert ("plan_research" in offered) is (mode == "research")
    # The platform's own data only when the person asks for it.
    assert INTERNAL - {"make_table"} <= names(tool_specs(False, mode, project_data=True)) | {
        "scenario_projection"
    }


@pytest.mark.parametrize("mode", ["ask", "analyze", "compare", "scenario"])
def test_data_modes_work_from_osrip_data(mode: str) -> None:
    offered = names(tool_specs(False, mode))
    assert {"get_observations", "make_table", "diagram"} <= offered
    assert "plan_research" not in offered and "web_search" not in offered
    assert ("scenario_projection" in offered) is (mode == "scenario")
    # With web research switched on, the web tools are added; the data tools stay.
    assert {"web_search", "calculate", "get_observations"} <= names(tool_specs(True, mode))


def test_illustrations_only_when_asked_for_and_available() -> None:
    assert "generate_image" not in names(tool_specs(False, "research"))
    assert "generate_image" in names(tool_specs(False, "research", images=True))


def test_run_tool_refuses_a_tool_outside_the_mode() -> None:
    allowed = allowed_tools(tool_specs(False, "research"))
    ledger = Ledger(DataMode.VERIFIED_SOURCE)
    result = run_tool(Tools(None, ledger), "get_observations", {"indicator": "X"}, allowed)  # type: ignore[arg-type]
    assert result["error"] == "not_allowed"
    assert ledger.items == [], "nothing was looked up"


def test_routing_phrases_in_both_languages() -> None:
    assert routing.asks_for_project_data("Compare this with OSRIP data")
    assert routing.asks_for_project_data("قارن ذلك ببيانات المنصة")
    assert not routing.asks_for_project_data("What did Oman export in 2024?")
    assert routing.asks_for_image("Make an illustration of Sohar port")
    assert routing.asks_for_image("أنشئ صورة توضيحية لميناء صحار")
    assert not routing.asks_for_image("What were the imports in 2023?")
    assert routing.INTERNET_MODES == {"quick", "research"}


def test_the_model_is_chosen_per_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        "app.services.assistant.provider.build_provider",
        lambda name, model=None, effort=None: built.append((name, model, effort)) or FakeProvider(),
    )
    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "openai")
    monkeypatch.setattr(s, "assistant_quick_model", "gpt-6-luna")
    monkeypatch.setattr(s, "assistant_deep_model", "gpt-6-astra")
    monkeypatch.setattr(s, "assistant_deep_reasoning_effort", "high")
    get_provider("quick"), get_provider("research"), get_provider("analyze")
    assert built == [
        ("openai", "gpt-6-luna", None),
        ("openai", "gpt-6-astra", "high"),
        ("openai", None, None),
    ]


# ------------------------------------------------------------------ analysis of web figures


def _pair(a: str, b: str, first: str = "1,200") -> list[dict[str, str]]:
    return [{"evidence_id": a, "value": first}, {"evidence_id": b, "value": "1,500"}]


def _ledger() -> tuple[Ledger, str, str]:
    ledger = Ledger(DataMode.SYNTHETIC, web_enabled=True)
    a = ledger.add({"kind": "web", "text": "Imports reached 1,200 million in 2022."})["id"]
    b = ledger.add({"kind": "web", "text": "Imports were 1,500 million in 2023."})["id"]
    return ledger, a, b


def test_calculations_use_only_cited_figures() -> None:
    ledger, a, b = _ledger()
    change = web_analysis.calculate(ledger, "percent_change", _pair(a, b))
    assert change["status"] == "ok" and change["value"] == "25" and change["unit"] == "percent"
    item = ledger.by_id()[change["evidence_id"]]
    assert item["kind"] == "calculation" and item["inputs"] == [a, b] and item["basis"] == "web"
    # A value the source does not give is refused, and nothing is recorded.
    count = len(ledger.items)
    refused = web_analysis.calculate(ledger, "difference", _pair(a, b, "1,300"))
    assert refused["status"] == "refused" and "not written" in refused["message"]
    assert len(ledger.items) == count
    cagr = web_analysis.calculate(ledger, "cagr", _pair(a, b), years=1)
    assert cagr["value"] == "25"
    hhi = web_analysis.calculate(ledger, "hhi", _pair(a, b))
    # Shares 44.44% and 55.56%: 1975.3 + 3086.4.
    assert 5061 < float(hhi["value"]) < 5062


def test_tables_keep_supported_rows_and_charts_draw_them() -> None:
    ledger, a, b = _ledger()
    table = web_analysis.research_table(
        ledger,
        "Imports",
        ["Year", "Imports (million)"],
        [
            {"cells": ["2022", "1,200"], "citations": [a]},
            {"cells": ["2023", "1,500"], "citations": [b]},
            {"cells": ["2024", "1,900"], "citations": [b]},  # not in its source: left out
        ],
    )
    assert table == {"status": "ok", "table_id": "RT1", "rows": 2, "dropped": 1}
    chart = web_analysis.research_chart(
        ledger, "RT1", value_columns=[1], kind="line", title="Imports", unit="million"
    )
    assert chart["status"] == "ok"
    [drawn] = ledger.research_charts
    assert drawn["labels"] == ["2022", "2023"] and drawn["series"][0]["values"] == [1200, 1500]
    assert web_analysis.research_chart(ledger, "RT9", value_columns=[1])["status"] == "refused"


def test_diagrams_carry_no_unsupported_figures() -> None:
    ledger, *_ = _ledger()
    ok = web_analysis.diagram(
        ledger, "flowchart", "Supply chain",
        [{"id": "port", "label": "Sohar port"}, {"id": "market", "label": "Local market"}],
        [{"from": "port", "to": "market"}],
    )  # fmt: skip
    assert ok["status"] == "ok" and ledger.diagrams[0]["nodes"][0]["label"] == "Sohar port"
    refused = web_analysis.diagram(
        ledger, "flowchart", "Supply chain",
        [{"id": "port", "label": "Sohar handles 9,999 containers"}, {"id": "m", "label": "M"}], [],
    )  # fmt: skip
    assert refused["status"] == "refused"


def test_the_research_plan_is_recorded() -> None:
    ledger, *_ = _ledger()
    assert web_analysis.plan(ledger, ["What did Oman import?", " ", "From whom?"])["questions"] == 2
    assert ledger.meta["plan"] == ["What did Oman import?", "From whom?"]
    assert web_analysis.plan(ledger, [])["status"] == "refused"


# ------------------------------------------------------------------ illustrations


def test_no_image_service_unless_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "images_provider", None)
    assert images.generator() is None and not images.available()
    monkeypatch.setattr(s, "images_provider", "openai")
    monkeypatch.setattr(s, "openai_api_key", None)
    assert images.generator() is None, "OpenAI images need a configured key"
    monkeypatch.setattr(s, "images_provider", "fake")
    assert isinstance(images.generator(), images.FakeImages)
    monkeypatch.setattr(s, "environment", "production")
    assert images.generator() is None, "the stand-in never runs in production"


def test_images_are_refused_for_guests_and_beyond_two(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "images_provider", "fake")
    ledger = Ledger(DataMode.SYNTHETIC)
    guest = images.generate_for_answer(ledger, "A port", "illustration", "fast")
    assert guest["status"] == "refused"
    ledger.image_owner = object()
    ledger.images = [{"id": "1"}, {"id": "2"}]
    refused = images.generate_for_answer(ledger, "A port", "illustration", "fast")
    assert refused["status"] == "refused" and "Two" in refused["message"]


def test_the_stand_in_draws_a_png() -> None:
    data, mime = images.FakeImages().generate("x", "gpt-image-2.5-flare", "1024x1024")
    assert mime == "image/png" and data.startswith(b"\x89PNG")


def test_production_refuses_the_image_stand_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import _check_production_settings

    s = get_settings()
    monkeypatch.setattr(s, "environment", "production")
    monkeypatch.setattr(s, "images_provider", "fake")
    with pytest.raises(RuntimeError, match="OSRIP_IMAGES_PROVIDER=fake"):
        _check_production_settings()
