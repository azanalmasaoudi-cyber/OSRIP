"""Serve the API for the full-stack Playwright tests (frontend/e2e-api).

Recreates a throwaway database, migrates it, seeds the booklet's SYNTHETIC
fixtures through the import workflow, creates test accounts and starts
uvicorn. Nothing here is used outside tests.

Environment:
    OSRIP_TEST_ADMIN_URL   superuser URL of a PostgreSQL 15+ server (required)
    OSRIP_E2E_PASSWORD     password for the test accounts (the Playwright config
                           generates a random one per run)
    OSRIP_E2E_PORT         API port (default 8765)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_NAME = "osrip_e2e"
# Never read a developer's backend/.env (real provider keys) in automated tests.
os.environ["OSRIP_ENV_FILE"] = "none"
for _name in (
    "OSRIP_ANTHROPIC_API_KEY", "OSRIP_OPENAI_API_KEY", "OSRIP_GEMINI_API_KEY",
    "OSRIP_RESEARCH_API_KEY", "OSRIP_SPEECH_KEY",
):  # fmt: skip
    os.environ.pop(_name, None)


def main() -> None:
    admin = make_url(os.environ["OSRIP_TEST_ADMIN_URL"])
    password = os.environ["OSRIP_E2E_PASSWORD"]
    port = int(os.environ.get("OSRIP_E2E_PORT", "8765"))

    plain = admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DB_NAME}"')

    os.environ["OSRIP_DATABASE_URL"] = admin.set(database=DB_NAME).render_as_string(
        hide_password=False
    )
    os.environ["OSRIP_SESSION_COOKIE_SECURE"] = "false"  # plain-HTTP localhost only
    # Test doubles and sinks for automated tests only (refused in production):
    # e-mails go to the development outbox; the assistant uses the scripted FakeProvider.
    os.environ.setdefault("OSRIP_EMAIL_BACKEND", "outbox")
    os.environ.setdefault("OSRIP_ASSISTANT_PROVIDER", "fake")
    # Scripted web search and speech (no network; refused in production).
    os.environ.setdefault("OSRIP_RESEARCH_PROVIDER", "fake")
    # A second, Google-style scripted route: the fallback when the first search fails, and
    # the cross-check a person may ask for in Research mode (shown apart from the answer).
    os.environ.setdefault("OSRIP_RESEARCH_FALLBACK_PROVIDER", "fake-gemini")
    os.environ.setdefault("OSRIP_SPEECH_PROVIDER", "fake")
    # Drawn stand-in pictures: never a paid call.
    os.environ.setdefault("OSRIP_IMAGES_PROVIDER", "fake")
    # The scripted answer streams in pieces 25 ms apart, so browser tests see it being written.
    os.environ.setdefault("OSRIP_FAKE_STREAM_DELAY_MS", "25")
    # Desktop and phone runs share one test account; the limit itself is tested in pytest.
    os.environ.setdefault("OSRIP_ASSISTANT_MAX_PER_MINUTE", "200")
    os.environ.setdefault("OSRIP_ASSISTANT_MAX_PER_HOUR", "2000")
    # Guest abuse limits stay on but out of the way of fast automated runs.
    os.environ.setdefault("OSRIP_GUEST_ASKS_PER_MINUTE", "200")
    os.environ.setdefault("OSRIP_GUEST_ASKS_PER_CLIENT_HOUR", "5000")
    os.environ.setdefault("OSRIP_GUEST_SESSIONS_PER_CLIENT_HOUR", "5000")
    os.environ.setdefault(
        "OSRIP_PUBLIC_BASE_URL", os.environ.get("OSRIP_E2E_WEB_ORIGIN", "http://localhost:5174")
    )

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")

    from sqlalchemy import text

    from app.core import security
    from app.db.session import session_factory
    from app.domain.enums import Permission, Role
    from app.models import AppUser, UserRole
    from app.services import accounts
    from app.services.fixtures import seed_booklet_fixtures
    from app.services.principal import Principal

    system = Principal(None, "system:e2e")
    # Usernames of up to 10 characters; the e-mail addresses are the records such accounts
    # kept from before e-mail sign-in was retired (they no longer sign anyone in).
    with session_factory()() as session:
        seed_booklet_fixtures(session)
        with session.begin():
            manager = accounts.create_user(
                session,
                system,
                username="e2emanager",
                email="manager@e2e.invalid",
                display_name="E2E data manager",
                password=password,
                roles=[Role.DATA_MANAGER],
            )
            for permission in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
                accounts.grant_permission(session, system, manager.id, permission)
            accounts.create_user(
                session,
                system,
                username="e2eanalyst",
                email="analyst@e2e.invalid",
                display_name="E2E analyst",
                password=password,
                roles=[Role.ANALYST],
            )
            accounts.create_user(
                session,
                system,
                username="e2eadmin",
                email="admin@e2e.invalid",
                display_name="E2E administrator",
                password=password,
                roles=[Role.ADMINISTRATOR],
            )
            accounts.create_user(
                session,
                system,
                username="e2eviewer",
                email="viewer@e2e.invalid",
                display_name="E2E viewer",
                password=password,
                roles=[Role.VIEWER],
            )
            # A username-only account with a temporary password (must be changed first).
            accounts.ensure_username_account(
                session, system, username="e2etemp", display_name="E2E temporary", password=password
            )
            # An account registered before the 10-character rule (migration 0033) with a longer
            # name: it keeps it and still signs in. Inserted as such an account was, before the
            # rule's trigger existed.
            trigger = "trg_app_user_username_policy"
            session.execute(text(f"ALTER TABLE app_user DISABLE TRIGGER {trigger}"))
            legacy = AppUser(
                username="e2elegacy.user",
                display_name="E2E older account",
                password_hash=security.hash_password(password),
                created_via="self_registration",
            )
            session.add(legacy)
            session.flush()
            session.execute(text(f"ALTER TABLE app_user ENABLE TRIGGER {trigger}"))
            session.add(UserRole(user_id=legacy.id, role_code=Role.VIEWER.value))
            # An account that signed in with its e-mail address before that was retired: it has
            # no username until an administrator gives it one.
            by_email = AppUser(
                email="legacy-email@e2e.invalid",
                display_name="E2E e-mail account",
                password_hash=security.hash_password(password),
                created_via="self_registration",
            )
            session.add(by_email)
            session.flush()
            session.add(UserRole(user_id=by_email.id, role_code=Role.VIEWER.value))
    if os.environ.get("OSRIP_E2E_REFERENCE_PACK") == "1":
        # Demonstration runs only (playwright.demo.config.ts): the curated, source-checked
        # reference pack, published as verified-source data in this throwaway database.
        from app.services import reference_pack

        with session_factory()() as session:
            reference_pack.import_pack(session, reference_pack.load_pack(), publish=True)

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
