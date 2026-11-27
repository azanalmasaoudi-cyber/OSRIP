"""The central-hosting tools (no network, no database):

* deploy/predeploy_check.py accepts the answering providers the backend really supports
  (anthropic, openai, gemini, deepseek, disabled), refuses the scripted test double, and warns
  when a provider's key, model or DeepSeek's billing acknowledgement is missing;
* tools/check_public_osrip.py refuses local and plain-HTTP addresses, and passes only when the
  page, HSTS and OSRIP's own API (X-OSRIP-API, ready=true) all answer: a static host with no
  API behind it (Vercel's 404) fails.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


predeploy = _load("predeploy_check", REPO / "deploy" / "predeploy_check.py")
public = _load("check_public_osrip", REPO / "tools" / "check_public_osrip.py")


def _assistant(env: dict[str, str]):  # noqa: ANN202
    report = predeploy.Report()
    predeploy.check_assistant(env, report)
    return report


@pytest.mark.parametrize("provider", ["anthropic", "openai", "gemini", "deepseek", "disabled"])
def test_every_supported_provider_is_accepted(provider: str) -> None:
    complete = {
        "OSRIP_ANTHROPIC_API_KEY": "k",
        "OSRIP_OPENAI_API_KEY": "k",
        "OSRIP_OPENAI_MODEL": "m",
        "OSRIP_GEMINI_API_KEY": "k",
        "OSRIP_GEMINI_MODEL": "m",
        "OSRIP_DEEPSEEK_API_KEY": "k",
        "OSRIP_DEEPSEEK_MODEL": "m",
        "OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED": "true",
    }
    report = _assistant({"OSRIP_ASSISTANT_PROVIDER": provider, **complete})
    assert report.failures == [] and report.warnings == []


@pytest.mark.parametrize("provider", ["fake", "chatgpt-app", "test"])
def test_the_test_double_and_unknown_providers_are_refused(provider: str) -> None:
    assert _assistant({"OSRIP_ASSISTANT_PROVIDER": provider}).failures
    assert _assistant(
        {"OSRIP_ASSISTANT_PROVIDER": "disabled", "OSRIP_ASSISTANT_FALLBACK_PROVIDER": provider}
    ).failures


def test_missing_settings_are_warnings_naming_what_is_missing() -> None:
    report = _assistant({"OSRIP_ASSISTANT_PROVIDER": "deepseek", "OSRIP_DEEPSEEK_API_KEY": "k"})
    assert report.failures == []
    assert any("OSRIP_DEEPSEEK_MODEL" in w for w in report.warnings)
    assert any("BILLING_ACKNOWLEDGED" in w and "owner's approval" in w for w in report.warnings)
    report = _assistant({"OSRIP_ASSISTANT_PROVIDER": "anthropic"})
    assert report.failures == [] and any("OSRIP_ANTHROPIC_API_KEY" in w for w in report.warnings)


def test_the_example_env_file_is_accepted_for_the_assistant() -> None:
    env = predeploy.read_env(REPO / "deploy" / ".env.example")
    assert env["OSRIP_ASSISTANT_PROVIDER"] == "disabled", (
        "no paid service is switched on by default"
    )
    assert env["OSRIP_EMAIL_BACKEND"] == "disabled", "username and password accounts need no e-mail"
    assert _assistant(env).failures == []


@pytest.mark.parametrize(
    "url",
    [
        "http://osrip.example.org",
        "https://localhost",
        "https://127.0.0.1:8443",
        "https://app.localhost",
        "https://user:secret@osrip.example.org",
        "osrip.example.org",
    ],  # fmt: skip
)
def test_the_public_check_refuses_local_and_insecure_addresses(url: str) -> None:
    assert public.base_url(url) is None


def _site(api_headers: dict[str, str], api_status: int, api_body: dict | None):  # noqa: ANN202
    def get(url: str):  # noqa: ANN202
        if url.endswith("/api/v1/health/ready"):
            return api_status, api_headers, json.dumps(api_body or {}).encode()
        return (
            200,
            {"strict-transport-security": "max-age=63072000"},
            b"<html><title>OSRIP</title></html>",
        )

    return get


def test_a_static_host_without_the_api_fails() -> None:
    # What osrip.vercel.app answers today: the page, and Vercel's own 404 for /api/v1/...
    passed, failed = public.check(
        "https://osrip.example.org", _site({"server": "Vercel"}, 404, {"error": {"code": "404"}})
    )
    assert any("interface answers" in p for p in passed)
    assert any("No OSRIP API" in f and "404" in f and "Vercel" in f for f in failed)


def test_an_api_that_is_not_ready_fails_and_a_ready_one_passes() -> None:
    _, failed = public.check(
        "https://osrip.example.org", _site({"x-osrip-api": "0.8.0"}, 503, {"ready": False})
    )
    assert any("not ready" in f for f in failed)
    passed, failed = public.check(
        "https://osrip.example.org", _site({"x-osrip-api": "0.8.0"}, 200, {"ready": True})
    )
    assert failed == [] and any("API is ready" in p for p in passed)


def test_the_compose_file_keeps_the_database_private_and_persistent() -> None:
    import yaml

    text = (REPO / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(text)
    services = compose["services"]
    assert set(services) == {"db", "migrate", "api", "web", "backup"}
    assert "ports" not in services["db"] and "ports" not in services["api"], (
        "only Caddy is reachable"
    )
    assert services["web"]["ports"] == ["80:80", "443:443"]
    assert (
        "pgdata:/var/lib/postgresql/data" in services["db"]["volumes"]
        and "pgdata" in compose["volumes"]
    )
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    # The checker's own reading of the file agrees with the YAML.
    assert "ports:" not in predeploy.compose_service(text, "db")
    assert "ports:" in predeploy.compose_service(text, "web")
    assert predeploy.compose_service(text, "nothing") == ""


def test_backups_never_enter_git_or_an_image() -> None:
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (REPO / ".dockerignore").read_text(encoding="utf-8")
    assert all(
        p in gitignore for p in ("*.backup", "*.dump", "OSRIP-Backups/", ".osrip-local.json")
    )
    assert all(
        p in dockerignore for p in ("**/*.backup", "**/*.dump", ".osrip-local.json", "**/.env")
    )


def test_the_server_start_loads_no_demo_data_unless_asked() -> None:
    script = (REPO / "deploy" / "remote_up.sh").read_text(encoding="utf-8")
    seed = script.index("seed-synthetic")
    assert 'if [ "${OSRIP_LOAD_SYNTHETIC_DEMO_DATA:-0}" = "1" ]' in script[:seed]


def test_restore_counts_are_compared_table_by_table() -> None:
    counts = _load("compare_restore_counts", REPO / "tools" / "compare_restore_counts.py")
    manifest = {"migration": "0034_x", "rows": {"app_user": 13, "observation": 362}}
    same, migration = counts.read_counts(
        "app_user|13\nobservation|362\nalembic_version_num|0034_x\n"
    )
    assert counts.compare(manifest, same, migration) == []
    short, migration = counts.read_counts("app_user|12\nextra|1\nalembic_version_num|0036_y\n")
    problems = counts.compare(manifest, short, migration)
    assert "app_user: backup 13, restored 12" in problems
    assert "observation: backup 362, restored None" in problems
    assert "extra: not in the backup" in problems
    assert any(p.startswith("migration:") for p in problems)
