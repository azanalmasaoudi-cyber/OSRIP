"""Objectives before recommendations, in Al Mulhim as in a sector's guided analysis:

* the five objectives are recognised in English and Arabic, and words that name none leave them
  unknown;
* a request for recommendations is recognised (and a report about a report is not one);
* through the API with the scripted model: recommendations asked for without an objective get the
  results first and one question about objectives, with no recommendation; with an objective named,
  the reply records it and the recommendations follow, without asking again.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import objectives
from app.services.assistant import routing
from app.services.assistant.service import GOAL_RULES

API = "/api/v1"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How can Muscat reduce water shortages?", ["reduce_shortages"]),
        ("We want less waste and leakage", ["improve_efficiency"]),
        ("Use the surplus electricity", ["use_surplus"]),
        ("Strengthen production and trade; diversify exports", ["strengthen", "diversify"]),
        ("كيف نقلل العجز في المياه؟", ["reduce_shortages"]),
        ("رفع الكفاءة وتقليل الهدر", ["improve_efficiency"]),
        ("استثمار الفائض والتنويع", ["use_surplus", "diversify"]),
        ("تعزيز الإنتاج", ["strengthen"]),
        ("Show me the latest water production", []),
        ("something nice", []),
    ],
)
def test_objectives_are_recognised_in_both_languages(text: str, expected: list[str]) -> None:
    assert objectives.detect(text) == expected


def test_recommendation_requests_are_recognised() -> None:
    asks = routing.asks_for_recommendations
    assert asks("What do you recommend for water in Muscat?")
    assert asks("What should Oman do about electricity demand?")
    assert asks("ما توصياتك للكهرباء في ظفار؟")
    assert asks("ماذا يجب أن نفعل بشأن المياه؟")
    assert not asks("What did the latest NCSI report say about water?")
    assert not asks("Show the electricity generation for 2024")
    assert objectives.clean(["diversify", "nope", "reduce_shortages", "diversify"]) == [
        "reduce_shortages",
        "diversify",
    ]


def test_the_rules_ask_once_or_recommend_for_the_known_objectives() -> None:
    assert "Do NOT give recommendations yet" in GOAL_RULES["ask"]
    assert "Ask nothing else" in GOAL_RULES["ask"]
    known = GOAL_RULES["known"].format(objectives="Reduce shortages")
    assert "Reduce shortages" in known and "Do not ask about objectives again" in known
    for part in ("rationale", "prerequisites", "risks", "missing"):
        assert part in known


# ------------------------------------------------------------------ through the API


@pytest.fixture
def scripted(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "research_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_answer_limit", 1000, raising=False)
    ratelimit.reset()
    with session_factory()() as session:
        seed_booklet_fixtures(session)


def ask(app, question: str, language: str = "en") -> dict[str, Any]:  # noqa: ANN001
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    r = client.post(
        f"{API}/assistant/guest/messages",
        json={"content": question, "language": language, "request_id": str(uuid.uuid4()),
              "data_mode": "synthetic", "mode": "analyze"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()["message"]


@pytest.mark.integration
def test_without_an_objective_the_results_come_first_then_one_question(app, scripted) -> None:  # noqa: ANN001
    message = ask(app, "What should be done about electricity generation?")
    assert message["status"] == "answered", message["content"]
    structured = message["structured"]
    assert structured["objectives"]["status"] == "ask"
    assert [o["code"] for o in structured["objectives"]["options"]] == list(objectives.OBJECTIVES)
    assert "recommendations" not in structured, "no recommendation before an objective"
    content = message["content"]
    assert content.index("latest published value") < content.index("Which objective")
    assert content.rstrip().endswith("?")


@pytest.mark.integration
def test_in_arabic_the_question_lists_the_five_objectives(app, scripted) -> None:  # noqa: ANN001
    message = ask(app, "ما توصياتك لتوليد الكهرباء؟", language="ar")
    assert message["structured"]["objectives"]["status"] == "ask"
    for name in ("تقليل العجز", "رفع الكفاءة", "استثمار الفائض", "التنويع"):
        assert name in message["content"]


@pytest.mark.integration
def test_with_an_objective_named_the_recommendations_follow(app, scripted) -> None:  # noqa: ANN001
    message = ask(
        app,
        "My objectives: Reduce shortages, Diversify. "
        "Please give the recommendations for electricity generation.",
    )
    assert message["status"] == "answered", message["content"]
    goals = message["structured"]["objectives"]
    assert goals["status"] == "known"
    assert [o["code"] for o in goals["known"]] == ["reduce_shortages", "diversify"]
    assert message["structured"]["recommendations"], "recommendations once the objectives are known"
    assert "Which objective" not in message["content"]
