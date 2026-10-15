"""Test configuration.

Unit tests need nothing. Integration tests (``-m integration``) need a PostgreSQL
15+ server: set OSRIP_RUN_DB_TESTS=1 and OSRIP_TEST_ADMIN_URL (a superuser URL,
e.g. from ``python scripts/devdb.py url``). Each pytest session creates a fresh,
uniquely named database, migrates it with Alembic to head, and drops it at the end.
Nothing touches a developer's own database.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

RUN_DB = os.environ.get("OSRIP_RUN_DB_TESTS") == "1"

# Hermetic settings: tests never read backend/.env or OSRIP_* values from the shell (which
# may hold real model, search, speech, mail or SMS credentials), so no test can reach a
# real provider. Each test sets what it needs.
for _name in [n for n in os.environ if n.startswith("OSRIP_")]:
    if _name not in ("OSRIP_RUN_DB_TESTS", "OSRIP_TEST_ADMIN_URL"):
        del os.environ[_name]
os.environ["OSRIP_ENV_FILE"] = "none"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if RUN_DB:
        return
    skip = pytest.mark.skip(
        reason="set OSRIP_RUN_DB_TESTS=1 and OSRIP_TEST_ADMIN_URL to run integration tests"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    import psycopg
    from sqlalchemy.engine import make_url

    admin = make_url(os.environ["OSRIP_TEST_ADMIN_URL"])
    name = f"osrip_test_{uuid.uuid4().hex[:10]}"
    plain = admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = admin.set(database=name).render_as_string(hide_password=False)

    os.environ["OSRIP_DATABASE_URL"] = url
    os.environ["OSRIP_SESSION_COOKIE_SECURE"] = "false"  # the test client talks plain HTTP
    _reset_caches()

    from alembic.config import Config

    from alembic import command

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.upgrade(cfg, "head")
    try:
        yield url
    finally:
        from app.db.session import get_engine

        get_engine().dispose()
        with psycopg.connect(plain, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _reset_caches() -> None:
    from app.core.config import get_settings
    from app.db.session import get_engine, session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    session_factory.cache_clear()


@pytest.fixture(scope="session")
def app(database_url: str):  # noqa: ANN201
    from app.main import create_app

    return create_app()


@pytest.fixture
def db(database_url: str):  # noqa: ANN201
    from app.db.session import session_factory

    with session_factory()() as session:
        yield session


# ------------------------------------------------------------------ people


@dataclass
class Person:
    email: str
    password: str
    id: uuid.UUID


@pytest.fixture
def make_user(database_url: str):  # noqa: ANN201
    """Create an account with roles and explicit grants; returns a Person."""
    from app.db.session import session_factory
    from app.domain.enums import Permission, Role
    from app.services import accounts
    from app.services.principal import Principal

    def make(*roles: Role, grants: tuple[Permission, ...] = ()) -> Person:
        email = f"user-{uuid.uuid4().hex[:8]}@test.invalid"
        password = f"pw-{uuid.uuid4().hex}"
        system = Principal(None, "system:test")
        with session_factory()() as session, session.begin():
            user = accounts.create_user(
                session,
                system,
                email=email,
                display_name="Test user",
                password=password,
                roles=list(roles),
            )
            session.flush()
            for permission in grants:
                accounts.grant_permission(session, system, user.id, permission)
            return Person(email, password, user.id)

    return make


@pytest.fixture
def login(app):  # noqa: ANN001, ANN201
    """Return a TestClient signed in as the person, sending the CSRF header."""
    from fastapi.testclient import TestClient

    def sign_in(person: Person) -> TestClient:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login", json={"email": person.email, "password": person.password}
        )
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
        return client

    return sign_in


@pytest.fixture
def anonymous(app):  # noqa: ANN001, ANN201
    from fastapi.testclient import TestClient

    return TestClient(app)
