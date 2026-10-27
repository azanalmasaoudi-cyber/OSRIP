"""Pre-publication checks for an OSRIP deployment. Standard library only.

    python deploy/predeploy_check.py                       # checks deploy/.env and the repository
    python deploy/predeploy_check.py --env path/to/.env
    python deploy/predeploy_check.py --url https://osrip.example.org   # also probes a running deployment

Exit code 0 when every check passes, 1 otherwise. Nothing is sent anywhere except,
with --url, plain GET/POST requests to the address you give. Secret values are
never printed; findings name the file, line and rule only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"replace|example\.(org|com)|changeme|change-me|^$", re.I)
SECRET_KEYS = ("POSTGRES_PASSWORD", "OSRIP_CLIENT_HASH_KEY")
OPTIONAL_SECRETS = (
    "OSRIP_SMTP_PASSWORD",
    "OSRIP_GOOGLE_CLIENT_SECRET",
    "OSRIP_MICROSOFT_CLIENT_SECRET",
    "OSRIP_ANTHROPIC_API_KEY",
)

# Patterns for credentials that must never be in the source tree.
SECRET_PATTERNS = {
    "anthropic-key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private-key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "google-client-secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),
    "slack-token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "db-url-with-password": re.compile(
        r"postgres(ql)?(\+psycopg)?://[^:\s/]+:(?!\$\{|<|osrip@|\*\*\*|(?i:password)@)[^@\s]{6,}@(?!localhost|127\.0\.0\.1|db:)"
    ),
}
SKIP_DIRS = {
    "node_modules",
    ".venv",
    "dist",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "test-results",
    "playwright-report",
    ".vs",
    ".vscode",
    ".claude",
}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".sql",
    ".txt",
    ".env",
    ".example",
    ".html",
    ".css",
    "",
}


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.passed = 0

    def check(self, ok: bool, message: str, *, warn: bool = False) -> None:
        if ok:
            self.passed += 1
            print(f"  ok    {message}")
        elif warn:
            self.warnings.append(message)
            print(f"  WARN  {message}")
        else:
            self.failures.append(message)
            print(f"  FAIL  {message}")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_env(env: dict[str, str], r: Report) -> None:
    print("\nConfiguration")
    r.check(env.get("OSRIP_ENVIRONMENT") == "production", "OSRIP_ENVIRONMENT=production")
    for key in SECRET_KEYS:
        value = env.get(key, "")
        r.check(
            not PLACEHOLDER.search(value) and len(value) >= 32,
            f"{key} is set, not a placeholder, and at least 32 characters",
        )
    domain = env.get("OSRIP_DOMAIN", "")
    r.check(
        bool(domain) and not PLACEHOLDER.search(domain) and domain not in {"localhost", "127.0.0.1"},
        "OSRIP_DOMAIN is a real public DNS name",
    )
    base = env.get("OSRIP_PUBLIC_BASE_URL", "")
    r.check(
        base.startswith("https://") and "localhost" not in base and not PLACEHOLDER.search(base),
        "OSRIP_PUBLIC_BASE_URL is https:// and not localhost or a placeholder",
    )
    r.check(base.rstrip("/") == f"https://{domain}", "OSRIP_PUBLIC_BASE_URL matches OSRIP_DOMAIN")
    try:
        origins = json.loads(env.get("OSRIP_CORS_ORIGINS", "[]"))
    except json.JSONDecodeError:
        origins = []
    r.check(origins == [base.rstrip("/")], "OSRIP_CORS_ORIGINS lists exactly the public address")
    r.check(env.get("OSRIP_SESSION_COOKIE_SECURE", "true").lower() == "true", "session cookies are Secure")
    email = env.get("OSRIP_EMAIL_BACKEND", "outbox")
    r.check(
        email in {"smtp", "disabled"},
        "OSRIP_EMAIL_BACKEND is smtp or disabled (the development outbox is refused)",
    )
    if email == "smtp":
        for key in ("OSRIP_SMTP_HOST", "OSRIP_SMTP_USERNAME", "OSRIP_SMTP_PASSWORD", "OSRIP_SMTP_FROM"):
            r.check(not PLACEHOLDER.search(env.get(key, "")), f"{key} is set")
    provider = env.get("OSRIP_ASSISTANT_PROVIDER", "anthropic")
    r.check(
        provider in {"anthropic", "disabled"},
        "OSRIP_ASSISTANT_PROVIDER is anthropic or disabled (the test double is refused)",
    )
    if provider == "anthropic":
        r.check(
            bool(env.get("OSRIP_ANTHROPIC_API_KEY")),
            "OSRIP_ANTHROPIC_API_KEY is set (otherwise the assistant shows 'not configured')",
            warn=True,
        )
    sms_provider = env.get("OSRIP_SMS_PROVIDER", "")
    r.check(sms_provider != "test", "OSRIP_SMS_PROVIDER is not the scripted test provider")
    if env.get("OSRIP_SMS_ENABLED", "false").lower() in {"1", "true", "yes"}:
        r.check(
            sms_provider in {"twilio_verify", "whatsapp"},
            "SMS is enabled with a provider (twilio_verify or whatsapp; otherwise phone sign-in shows 'unavailable')",
            warn=True,
        )
        if sms_provider == "whatsapp":
            mode = env.get("OSRIP_WHATSAPP_MODE", "test")
            r.check(
                bool(env.get("OSRIP_WHATSAPP_ACCESS_TOKEN")) and bool(env.get("OSRIP_WHATSAPP_PHONE_NUMBER_ID")),
                "WhatsApp: access token and phone number ID are set",
                warn=True,
            )
            r.check(
                mode == "test",
                "OSRIP_WHATSAPP_MODE is test (production sends to anyone and Meta charges each delivered code)",
                warn=True,
            )
            if mode == "test":
                r.check(
                    bool(env.get("OSRIP_WHATSAPP_TEST_RECIPIENTS", "").strip()),
                    "WhatsApp test mode: OSRIP_WHATSAPP_TEST_RECIPIENTS lists the approved numbers",
                    warn=True,
                )
        if sms_provider == "twilio_verify":
            key = env.get("OSRIP_TWILIO_API_KEY_SID") and env.get("OSRIP_TWILIO_API_KEY_SECRET")
            token = env.get("OSRIP_TWILIO_ACCOUNT_SID") and env.get("OSRIP_TWILIO_AUTH_TOKEN")
            r.check(
                bool(env.get("OSRIP_TWILIO_VERIFY_SERVICE_SID")) and bool(key or token),
                "Twilio Verify: service SID and an API key (or account SID and auth token) are set",
                warn=True,
            )
    for name in ("GOOGLE", "MICROSOFT"):
        cid, secret = env.get(f"OSRIP_{name}_CLIENT_ID", ""), env.get(f"OSRIP_{name}_CLIENT_SECRET", "")
        r.check(
            bool(cid) == bool(secret),
            f"{name.title()} sign-in: client ID and secret are both set or both empty",
        )
        if cid:
            print(
                f"        register this redirect URI with {name.title()}: {base.rstrip('/')}/api/v1/auth/oidc/{name.lower()}/callback"
            )
    for key, label in (("OSRIP_RESEARCH_PROVIDER", "web search"), ("OSRIP_SPEECH_PROVIDER", "speech")):
        r.check(env.get(key, "") != "fake", f"{key} is not the scripted test provider ({label})")
    if env.get("OSRIP_RESEARCH_PROVIDER", "brave") == "brave" and not env.get("OSRIP_RESEARCH_API_KEY"):
        r.check(False, "web search has no OSRIP_RESEARCH_API_KEY: the assistant will say web search is unavailable", warn=True)
    if not env.get("OSRIP_SPEECH_KEY") or not (env.get("OSRIP_SPEECH_REGION") or env.get("OSRIP_SPEECH_ENDPOINT")):
        r.check(False, "server speech is not configured: voice falls back to the browser or text only", warn=True)
    # Anything named VITE_* is compiled into the public JavaScript bundle.
    leaky = [k for k in env if k.startswith("VITE_") and re.search(r"KEY|SECRET|TOKEN|PASSWORD", k)]
    r.check(
        not leaky,
        "no key, secret, token or password in a browser-exposed VITE_ variable"
        + (f" ({', '.join(leaky)})" if leaky else ""),
    )
    map_url = env.get("VITE_MAP_STYLE_URL", "")
    r.check(map_url == "none" or map_url.startswith("https://"), "VITE_MAP_STYLE_URL is https:// or 'none'")
    if map_url.startswith("https://") and "openfreemap.org" not in map_url:
        r.check(
            False,
            "the Caddyfile Content-Security-Policy allows only tiles.openfreemap.org; add the new map host",
            warn=True,
        )


def iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if (
            path.is_file()
            and (path.suffix in TEXT_SUFFIXES or path.name.startswith(".env"))
            and path.stat().st_size < 2_000_000
        ):
            yield path


def check_repository(r: Report, env_path: Path) -> None:
    print("\nRepository")
    findings: list[str] = []
    for path in iter_files(ROOT):
        if path.resolve() == env_path.resolve() or path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for rule, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{lineno} ({rule})")
    for finding in findings[:20]:
        print(f"        {finding}")
    r.check(not findings, f"no credentials in the source tree ({len(findings)} findings)")

    env_files = [
        p
        for p in ROOT.rglob(".env*")
        if not any(s in p.parts for s in SKIP_DIRS) and not p.name.endswith(".example")
    ]
    ignore = ROOT / ".dockerignore"
    ignored = ignore.exists() and "**/.env" in ignore.read_text(encoding="utf-8")
    r.check(ignored, ".dockerignore keeps every .env file out of the image build context")
    if env_files:
        print(
            "        local .env files (must never be committed or copied into images): "
            + ", ".join(str(p.relative_to(ROOT)) for p in env_files)
        )
    gitignore = ROOT / ".gitignore"
    r.check(
        gitignore.exists() and ".env" in gitignore.read_text(encoding="utf-8"), ".gitignore excludes .env"
    )

    web = (ROOT / "deploy" / "Dockerfile.web").read_text(encoding="utf-8")
    r.check(
        "VITE_DATA_ADAPTER=http" in web and "VITE_API_BASE_URL=/api/v1" in web,
        "web image uses the API adapter and a same-origin API path",
    )
    for path in (ROOT / "frontend" / "src").rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"https?://localhost:\d+", text) and "test" not in path.name:
            r.check(False, f"no hard-coded localhost address in frontend source ({path.relative_to(ROOT)})")
            break
    else:
        r.check(True, "no hard-coded localhost address in frontend source")
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    r.check(
        "migrate:" in compose and "service_completed_successfully" in compose,
        "migrations run before the API starts",
    )
    r.check("backup:" in compose, "a scheduled database backup service is defined")
    r.check(
        "healthcheck" in compose.split("api:")[1] if "api:" in compose else False,
        "the API container has a health check",
    )


def request(url: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(
        url,
        method=method,
        data=b"{}" if method == "POST" else None,
        headers={"Content-Type": "application/json", "User-Agent": "osrip-predeploy-check"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - operator-supplied https URL
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()


def check_live(base: str, r: Report) -> None:
    print(f"\nRunning deployment at {base}")
    if not base.startswith("https://"):
        r.check(False, "the address is https://")
        return
    try:
        status, headers, body = request(f"{base}/api/v1/health/ready")
    except (urllib.error.URLError, TimeoutError) as err:
        r.check(False, f"deployment reachable ({type(err).__name__})")
        return
    r.check(
        status == 200 and json.loads(body or b"{}").get("ready") is True,
        "readiness: database reachable and migrations current",
    )
    status, headers, _ = request(f"{base}/")
    r.check("strict-transport-security" in headers, "HSTS header present")
    r.check("content-security-policy" in headers, "Content-Security-Policy header present")
    r.check(headers.get("x-frame-options", "").upper() == "DENY", "framing denied")
    for path in (
        "/api/v1/imports",
        "/api/v1/admin/users",
        "/api/v1/admin/monitoring",
        "/api/v1/admin/audit-events",
    ):
        status, _, _ = request(f"{base}{path}")
        r.check(status in {401, 403}, f"{path} refuses anonymous access ({status})")
    status, _, _ = request(f"{base}/api/v1/dev/outbox")
    r.check(status in {403, 404}, f"development mail outbox is not available ({status})")
    status, _, _ = request(f"{base}/api/v1/dev/sms-outbox")
    r.check(status in {403, 404}, f"SMS test outbox (verification codes) is not available ({status})")
    status, _, body = request(f"{base}/api/v1/auth/providers")
    if status == 200:
        sms_status = json.loads(body or b"{}").get("sms", {}).get("status")
        r.check(sms_status != "test", f"SMS is not in test mode ({sms_status})")
    r.check(status == 200, "sign-in provider list reachable")
    status, headers, _ = request(f"{base}/api/v1/auth/login", "POST")
    cookie = headers.get("set-cookie", "")
    r.check(
        not cookie or ("secure" in cookie.lower() and "httponly" in cookie.lower()),
        "cookies set by the API are Secure and HttpOnly",
    )
    status, _, body = request(f"{base}/api/v1/observations?data_mode=synthetic")
    r.check(status != 200 or b"SYNTHETIC" in body.upper(), "synthetic data is labelled in API responses")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--env", default=str(ROOT / "deploy" / ".env"))
    parser.add_argument("--url", help="probe a running deployment at this https:// address")
    args = parser.parse_args()
    r = Report()
    env_path = Path(args.env)
    if env_path.exists():
        check_env(read_env(env_path), r)
    else:
        print(f"\nConfiguration\n  FAIL  {env_path} not found (copy deploy/.env.example and fill it in)")
        r.failures.append("env file missing")
    check_repository(r, env_path)
    if args.url:
        check_live(args.url.rstrip("/"), r)
    print(f"\n{r.passed} passed, {len(r.warnings)} warnings, {len(r.failures)} failed")
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())
