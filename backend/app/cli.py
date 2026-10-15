"""Operator commands. Run from backend/: ``python -m app.cli <command>``.

create-user --email E --name N [--role R ...] [--grant P ...]
    Password is read from OSRIP_NEW_USER_PASSWORD or prompted (never an argument,
    so it does not land in shell history).
ensure-user --username U [--name N]
    Idempotently create a standard (viewer) account identified by a username, with a
    temporary password (OSRIP_NEW_USER_PASSWORD or prompted) that must be changed at
    first sign-in. An existing account is never modified.
seed-synthetic
    Load the booklet's synthetic fixtures through the import workflow.
build-reference-pack DOCX [--out FILE]
    Extract the curated reference pack (records, references, notes) from the English
    reference document into a versioned JSON file (default: fixtures/reference/...).
import-reference-pack [FILE] [--publish]
    Register the pack's sources and load each source's records through the import
    workflow. Without --publish the imports stop after validation, for a data manager
    to review and approve in Data Management. Repeatable: nothing is duplicated.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from app.db.session import session_factory
from app.domain.enums import Permission, Role
from app.services import accounts, reference_pack
from app.services.fixtures import seed_booklet_fixtures
from app.services.principal import Principal

CLI = Principal(user_id=None, label="system:cli")


def create_user(args: argparse.Namespace) -> None:
    password = os.environ.get("OSRIP_NEW_USER_PASSWORD") or getpass.getpass(
        "Password (12+ characters): "
    )
    with session_factory()() as session, session.begin():
        user = accounts.create_user(
            session,
            CLI,
            email=args.email,
            display_name=args.name,
            password=password,
            roles=[Role(r) for r in args.role],
        )
        session.flush()
        for permission in args.grant:
            accounts.grant_permission(session, CLI, user.id, Permission(permission))
        print(f"Created {user.email} ({user.id}) roles={args.role} grants={args.grant}")


def ensure_username_user(args: argparse.Namespace) -> None:
    """Idempotent: creates the account once; if the username exists, nothing changes."""
    with session_factory()() as session, session.begin():
        existing = accounts.find_by_username(session, args.username)
        if existing is not None:
            print(
                f"Account '{existing.username}' already exists ({existing.id}); "
                "left unchanged (password, roles and grants were not modified)."
            )
            return
    password = os.environ.get("OSRIP_NEW_USER_PASSWORD")
    if not password:
        if not sys.stdin.isatty():
            raise SystemExit(
                "error: no password supplied. Set OSRIP_NEW_USER_PASSWORD in this terminal "
                "session, or run the command in an interactive terminal to be prompted."
            )
        password = getpass.getpass("Temporary password (8+ characters, not echoed): ")
        if getpass.getpass("Repeat it: ") != password:
            raise SystemExit("error: the two passwords differ; nothing was created.")
    with session_factory()() as session, session.begin():
        result = accounts.ensure_username_account(
            session,
            CLI,
            username=args.username,
            display_name=args.name or args.username,
            password=password,
        )
        if result.created:
            print(
                f"Created standard account '{result.user.username}' ({result.user.id}) with the "
                "viewer role. The password is temporary: it must be changed at first sign-in. "
                "No e-mail address or phone number is recorded."
            )
        else:  # created concurrently between the check above and here
            print(f"Account '{result.user.username}' already exists; left unchanged.")


def seed_synthetic(_: argparse.Namespace) -> None:
    with session_factory()() as session:
        result = seed_booklet_fixtures(session)
    state = "published" if result.created else "already published"
    print(
        f"Synthetic fixtures {state}: source={result.source_id} "
        f"version={result.dataset_version_id} "
        f"rejected_rows={result.rejected_rows}"
    )


def build_reference_pack(args: argparse.Namespace) -> None:
    pack = reference_pack.build_pack(Path(args.docx))
    path = reference_pack.write_pack(pack, Path(args.out) if args.out else reference_pack.PACK_FILE)
    print(
        f"Pack {pack['code']}: {pack['record_count']} records, {len(pack['sources'])} references, "
        f"{len(pack['notes'])} notes -> {path}"
    )


def import_reference_pack(args: argparse.Namespace) -> None:
    pack = reference_pack.load_pack(Path(args.file) if args.file else reference_pack.PACK_FILE)
    with session_factory()() as session:
        results = reference_pack.import_pack(session, pack, publish=args.publish)
    for r in results:
        print(
            f"{r.code}: {r.rows} rows, {r.rejected} rejected, "
            f"{r.warnings} with warnings -> {r.status}"
        )
    total = sum(r.rows for r in results)
    print(f"Pack {pack['code']}: {total} of {pack['record_count']} records staged or published.")


def assistant_profile_command(args: argparse.Namespace) -> None:
    """Show the active Al Mulhim profile, publish a reviewed file as the next version, or
    re-activate an earlier version. Stored versions are never edited."""
    from app.services.assistant import profile

    with session_factory()() as session, session.begin():
        if args.action == "publish":
            version = profile.publish(session, Path(args.target))
            print(f"Published assistant profile v{version} and made it active.")
        elif args.action == "activate":
            profile.activate(session, int(args.target))
            print(f"Assistant profile v{args.target} is active.")
        current = profile.active(session)
        if current is None:
            print("No assistant profile is active.")
        else:
            name = current.profile.name
            print(f"Active: v{current.version} {name.en} / {name.ar} sha256={current.sha256}")


def purge_grounded_command(args: argparse.Namespace) -> None:
    """Remove Google Search grounded results older than OSRIP_GROUNDED_RETENTION_DAYS (at most
    two years under the Gemini API terms) from stored replies."""
    from app.services.assistant import service

    with session_factory()() as session, session.begin():
        removed = service.purge_grounded(session)
    print(f"Removed {removed} expired grounded results.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("create-user")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--role", action="append", default=[], choices=[r.value for r in Role])
    p.add_argument("--grant", action="append", default=[], choices=[p.value for p in Permission])
    p.set_defaults(func=create_user)

    p = commands.add_parser("ensure-user")
    p.add_argument("--username", required=True)
    p.add_argument("--name", help="display name (defaults to the username)")
    p.set_defaults(func=ensure_username_user)

    commands.add_parser("seed-synthetic").set_defaults(func=seed_synthetic)

    p = commands.add_parser("build-reference-pack")
    p.add_argument("docx")
    p.add_argument("--out")
    p.set_defaults(func=build_reference_pack)

    p = commands.add_parser("import-reference-pack")
    p.add_argument("file", nargs="?")
    p.add_argument("--publish", action="store_true")
    p.set_defaults(func=import_reference_pack)

    p = commands.add_parser("assistant-profile")
    p.add_argument("action", choices=["show", "publish", "activate"])
    p.add_argument("target", nargs="?", help="profile JSON file (publish) or version (activate)")
    p.set_defaults(func=assistant_profile_command)

    commands.add_parser("purge-grounded").set_defaults(func=purge_grounded_command)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:  # noqa: BLE001 - print a clean message for operators
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
