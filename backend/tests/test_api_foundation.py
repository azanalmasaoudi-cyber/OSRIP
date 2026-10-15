"""API smoke tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_ok_without_database() -> None:
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_refuses_development_security_settings_in_production(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OSRIP_ENVIRONMENT", "production")
    monkeypatch.setenv("OSRIP_SESSION_COOKIE_SECURE", "false")
    try:
        with pytest.raises(RuntimeError, match="OSRIP_CLIENT_HASH_KEY.*SECURE is false"):
            create_app()
    finally:
        get_settings.cache_clear()


def test_app_refuses_scripted_ai_and_search_routes_in_production(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OSRIP_ENVIRONMENT", "production")
    monkeypatch.setenv("OSRIP_ASSISTANT_FALLBACK_PROVIDER", "fake")
    monkeypatch.setenv("OSRIP_RESEARCH_FALLBACK_PROVIDER", "fake-gemini")
    try:
        with pytest.raises(RuntimeError) as refused:
            create_app()
        assert "OSRIP_ASSISTANT_FALLBACK_PROVIDER=fake is" in str(refused.value)
        assert "OSRIP_RESEARCH_FALLBACK_PROVIDER=fake-gemini is" in str(refused.value)
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
def test_indicators_expose_units_of_the_same_dimension_only(anonymous: TestClient) -> None:
    response = anonymous.get("/api/v1/indicators")
    assert response.status_code == 200
    by_code = {item["code"]: item for item in response.json()}
    generation_units = {u["code"] for u in by_code["ELEC_GENERATION"]["compatible_units"]}
    assert generation_units == {"GWh"}
    assert "MW" not in generation_units  # T03 at the metadata level
    assert by_code["TRADE_QUANTITY"]["requires_flow"] is True
