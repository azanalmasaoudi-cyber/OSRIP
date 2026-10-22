"""Failure diagnosis and the data-based report's pure parts: the provider's error type is
kept only as a short safe token, failures map to one category, and the report picks its
indicators and formats its numbers without inventing anything."""

from __future__ import annotations

import pytest

from app.domain.enums import DataMode
from app.services.assistant import data_report
from app.services.assistant.provider import error_type, failure_category


def test_error_type_keeps_only_a_short_safe_token() -> None:
    anthropic = {
        "type": "error",
        "error": {"type": "authentication_error", "message": "invalid x-api-key sk-ant-abc"},
    }
    assert error_type(anthropic) == "authentication_error"
    assert error_type({"error": {"code": "invalid_api_key", "type": None}}) == "invalid_api_key"
    assert error_type({"error": {"code": 401, "status": "UNAUTHENTICATED"}}) == "UNAUTHENTICATED"
    # Anything that is not a plain token (a sentence, a key with spaces, a long value) is dropped.
    assert error_type({"error": {"type": "key sk-ant-123 rejected"}}) is None
    assert error_type({"error": {"type": "x" * 41}}) is None
    assert error_type({"error": "overloaded"}) is None
    assert error_type(["not", "a", "dict"]) is None


@pytest.mark.parametrize(
    ("code", "detail", "category"),
    [
        ("http_401", "authentication_error", "authentication"),
        ("http_403", None, "authentication"),
        ("http_400", "UNAUTHENTICATED", "authentication"),
        ("http_404", "not_found_error", "model_unavailable"),
        ("http_400", "invalid_model", "model_unavailable"),
        ("http_429", "rate_limit_error", "rate_limited"),
        ("http_529", "overloaded_error", "rate_limited"),
        ("http_503", None, "server_error"),
        ("timeout", None, "timeout"),
        ("network", None, "network"),
        ("daily_limit", None, "budget"),
        ("budget_exhausted", None, "budget"),
        ("invalid_json", None, "invalid_response"),
        ("no_tool_call", None, "invalid_response"),
        ("status_failed", None, "invalid_response"),
        ("not_configured", None, "not_configured"),
        ("simulated_failure", None, "other"),
    ],
)
def test_failure_categories(code: str, detail: str | None, category: str) -> None:
    assert failure_category(code, detail) == category


def test_numbers_are_formatted_as_published_or_rounded() -> None:
    assert data_report.fmt("41234") == "41,234"
    assert data_report.fmt("4305.50") == "4,305.5"
    assert data_report.fmt("-205.25") == "205.25"  # the sign is said in words
    assert data_report.fmt("5.00579", 1) == "5"
    assert data_report.fmt("12.345", 1) == "12.3"
    assert data_report.fmt(None) == "None"


def test_indicators_follow_the_question_then_the_headlines() -> None:
    picked = data_report.candidates(
        "electricity generation and water", ["electricity", "water"], DataMode.VERIFIED_SOURCE
    )
    assert picked["electricity"][0] == "ELEC_GROSS_GENERATION"
    assert "ELEC_CONSUMPTION" in picked["electricity"]
    assert picked["water"][0] == "WATER_PRODUCTION"
    # Consumption is never reported as generation, and topics are not mixed.
    consumption = data_report.candidates(
        "استهلاك الكهرباء", ["electricity"], DataMode.VERIFIED_SOURCE
    )
    assert consumption["electricity"][0] == "ELEC_CONSUMPTION"
    assert all(c.startswith("ELEC_") for c in consumption["electricity"])
    synthetic = data_report.candidates("trade", ["trade"], DataMode.SYNTHETIC)
    assert synthetic == {"trade": ["TRADE_VALUE"]}


def test_shortage_questions_add_the_balance_analysis() -> None:
    assert data_report.wants_balance("Is there a water shortage?")
    assert data_report.wants_balance("هل يوجد عجز في الكهرباء؟")
    assert data_report.wants_balance("فائض الأسماك")
    assert not data_report.wants_balance("latest electricity generation")
