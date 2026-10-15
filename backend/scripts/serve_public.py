"""Temporary public demonstration from this machine, in production mode.

    python scripts/serve_public.py setup                 # once: database, migrations, synthetic seed, app role
    python scripts/serve_public.py serve --url https://<name>.trycloudflare.com [--port 8090]

Serves the built interface and the API from one local port (127.0.0.1 only) for a
tunnel such as ``cloudflared tunnel --url http://127.0.0.1:8090``. It uses its own
database ``osrip_public`` (labelled synthetic demonstration data and the curated
reference pack of official figures, checked to 2026-09-27) and a login role that
can read and write rows but cannot change the schema. Secrets are generated once
into %LOCALAPPDATA%\\OSRIP-dev\\public.env, outside the repository, and never printed.

Production settings apply: Secure cookies, no development mail outbox, no assistant
test double, a random client-hash key, the same security headers as deploy/Caddyfile.
E-mail is switched off (no SMTP relay). The assistant, web search and speech are used
only if their keys are set in the terminal environment before ``serve``.
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
os.chdir(BACKEND)

from devdb import PORT, admin_url, createdb, dev_home  # noqa: E402

DATABASE = "osrip_public"
ROLE = "osrip_public_app"
ENV_FILE = dev_home() / "public.env"
WEB_DIR = dev_home() / "public-web"

HEADERS = [
    (b"strict-transport-security", b"max-age=31536000"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-frame-options", b"DENY"),
    (
        b"content-security-policy",
        b"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; img-src 'self' data: blob: "
        b"https://tiles.openfreemap.org; media-src 'self' blob:; connect-src 'self' https://tiles.openfreemap.org; "
        b"worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; frame-ancestors 'none'",
    ),
    (b"permissions-policy", b"microphone=(self), camera=(), geolocation=()"),
]


def load_secrets() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                values[k] = v
    changed = False
    for key in ("CLIENT_HASH_KEY", "DB_PASSWORD"):
        if not values.get(key):
            values[key] = secrets.token_urlsafe(48)
            changed = True
    if changed:
        ENV_FILE.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return values


def app_url(password: str) -> str:
    return f"postgresql+psycopg://{ROLE}:{password}@localhost:{PORT}/{DATABASE}"


def setup() -> None:
    from sqlalchemy import create_engine, text

    values = load_secrets()
    server = create_engine(admin_url("postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        if not conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": DATABASE}
        ).first():
            createdb(DATABASE)
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
        ).first()
        verb = "ALTER" if exists else "CREATE"
        pw = values["DB_PASSWORD"].replace("'", "''")
        conn.execute(
            text(f"{verb} ROLE {ROLE} LOGIN PASSWORD '{pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE")
        )
    server.dispose()

    env = {**os.environ, "OSRIP_DATABASE_URL": admin_url(DATABASE)}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    subprocess.run([sys.executable, "-m", "app.cli", "seed-synthetic"], check=True, env=env)
    # The curated, source-referenced reference pack (verified-source mode); idempotent.
    subprocess.run(
        [sys.executable, "-m", "app.cli", "import-reference-pack", "--publish"], check=True, env=env
    )

    grant_app_role()
    print(f"setup complete: database {DATABASE}, role {ROLE} (secrets in {ENV_FILE})")


def grant_app_role() -> None:
    """Row access (no schema changes) for the app role, including tables added by later
    migrations."""
    from sqlalchemy import create_engine, text

    db = create_engine(admin_url(DATABASE), isolation_level="AUTOCOMMIT")
    with db.connect() as conn:
        for stmt in (
            f"REVOKE CREATE ON SCHEMA public FROM {ROLE}",
            f"GRANT CONNECT ON DATABASE {DATABASE} TO {ROLE}",
            f"GRANT USAGE ON SCHEMA public TO {ROLE}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}",
            f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {ROLE}",
        ):
            conn.execute(text(stmt))
    db.dispose()


def build_web() -> None:
    frontend = BACKEND.parent / "frontend"
    env = {**os.environ, "VITE_DATA_ADAPTER": "http", "VITE_API_BASE_URL": "/api/v1"}
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run(
        [npm, "run", "build", "--", "--outDir", str(WEB_DIR), "--emptyOutDir"],
        check=True,
        cwd=frontend,
        env=env,
    )


def make_site(api):  # noqa: ANN001, ANN201
    from starlette.responses import FileResponse
    from starlette.staticfiles import StaticFiles

    static = StaticFiles(directory=WEB_DIR)
    # The app shell must be revalidated on every visit so new builds and headers reach visitors;
    # the hashed files under /assets can be cached.
    index = FileResponse(WEB_DIR / "index.html", headers={"cache-control": "no-cache"})

    async def site(scope, receive, send):  # noqa: ANN001, ANN202
        async def with_headers(message):  # noqa: ANN001, ANN202
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], *HEADERS]
            await send(message)

        if scope["type"] != "http":
            await api(scope, receive, send)
        elif scope["path"].startswith("/api/"):
            await api(scope, receive, with_headers)
        else:
            path = scope["path"].lstrip("/")
            target = (WEB_DIR / path).resolve()
            if path and target.is_file() and WEB_DIR.resolve() in target.parents:
                await static(scope, receive, with_headers)
            else:  # client-side route: serve the app shell
                await index(scope, receive, with_headers)

    return site


def serve(url: str, port: int, skip_build: bool) -> None:
    if not url.startswith("https://") or "localhost" in url:
        raise SystemExit("--url must be the public https:// address of the tunnel")
    url = url.rstrip("/")
    values = load_secrets()
    # Forward-only migrations first (additive; nothing is reset), with the owner account,
    # because the app's own role cannot change the schema.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env={**os.environ, "OSRIP_DATABASE_URL": admin_url(DATABASE)},
    )
    grant_app_role()
    os.environ.update(
        {
            "OSRIP_ENVIRONMENT": "production",
            "OSRIP_DATABASE_URL": app_url(values["DB_PASSWORD"]),
            "OSRIP_CLIENT_HASH_KEY": values["CLIENT_HASH_KEY"],
            "OSRIP_SESSION_COOKIE_SECURE": "true",
            "OSRIP_PUBLIC_BASE_URL": url,
            "OSRIP_CORS_ORIGINS": f'["{url}"]',
            "OSRIP_EMAIL_BACKEND": "disabled",
            # The assistant, web search and speech run only when their keys are set in this
            # terminal (server side); otherwise the interface says they are unavailable.
            "OSRIP_ASSISTANT_PROVIDER": "anthropic"
            if os.environ.get("OSRIP_ANTHROPIC_API_KEY")
            else "disabled",
            # No SMS provider is selected; phone registration is shown as unavailable.
            "OSRIP_SMS_ENABLED": "false",
            "OSRIP_SMS_PROVIDER": "",
        }
    )
    if not skip_build or not (WEB_DIR / "index.html").exists():
        build_web()

    import uvicorn

    from app.main import app

    uvicorn.run(
        make_site(app),
        host="127.0.0.1",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        log_level="info",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup")
    s = sub.add_parser("serve")
    s.add_argument("--url", required=True)
    s.add_argument("--port", type=int, default=8090)
    s.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if args.command == "setup":
        setup()
    else:
        serve(args.url, args.port, args.skip_build)


if __name__ == "__main__":
    main()
