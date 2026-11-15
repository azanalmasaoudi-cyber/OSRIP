"""API smoke tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_ok_without_database() -> None:
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_every_answer_is_marked_as_the_osrip_api() -> None:
    """Success, an unknown path and a refused request all carry X-OSRIP-API and X-Request-ID, so the
    interface can tell this API from a static host answering in its place. (None of these needs
    the database.)"""
    from app.services import monitoring

    client = TestClient(create_app())
    answers = (
        ("/api/v1/health", 200),
        ("/api/v1/no-such-route", 404),
        ("/api/v1/observations", 422),
    )
    for path, status in answers:
        response = client.get(path)
        assert response.status_code == status, path
        assert response.headers["X-OSRIP-API"] == monitoring.RELEASE, path
        assert response.headers["X-Request-ID"], path


def test_a_refused_write_is_a_server_fault_and_an_outage_is_database_unavailable(
    monkeypatch,
) -> None:  # noqa: ANN001
    """IntegrityError (a rule of the database refused the data) is OSRIP's fault: 500, recorded
    by constraint name only. OperationalError (the database cannot be reached) is the outage the
    interface reports as "database unavailable": 503."""
    from sqlalchemy.exc import IntegrityError, OperationalError

    from app.services import monitoring

    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        monitoring,
        "record_error",
        lambda source, kind, message, *_: recorded.append((kind, message)),
    )
    app = create_app()

    @app.get("/api/v1/__refused")
    def refused() -> None:
        raise IntegrityError("INSERT INTO research_candidate ...", {}, Exception("violates check"))

    @app.get("/api/v1/__outage")
    def outage() -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    client = TestClient(app)
    response = client.get("/api/v1/__refused")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert recorded == [("IntegrityError", "constraint unknown")]
    response = client.get("/api/v1/__outage")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_cross_origin_clients_may_read_the_marker() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    exposed = response.headers.get("access-control-expose-headers", "")
    if response.headers.get("access-control-allow-origin"):
        assert "X-OSRIP-API" in exposed and "X-Request-ID" in exposed


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
