"""Store the Anthropic, OpenAI, Gemini and Brave Search keys in backend/.env and test them.

Run it yourself in a terminal, from backend\\:
    .venv\\Scripts\\python.exe scripts\\set_provider_keys.py

* Each key is typed or pasted at a hidden prompt; nothing is echoed or printed.
* Press Enter without typing to keep the key already in the file.
* Only the key lines in backend/.env are written; other lines are kept.
* Each key is then tested with one free request (the provider's model list, or a one-result
  Brave search); only the outcome is shown. For OpenAI and Gemini it also says whether the
  model ids set in the file (OSRIP_OPENAI_MODEL, OSRIP_GEMINI_SEARCH_MODEL, ...) are in that
  account's model list. Model ids are not secret: set them in the file yourself.
* A ChatGPT, Gemini or Claude app subscription is not API access: each key comes from the
  provider's developer console, with API billing set up there.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

import httpx

ENV = Path(__file__).resolve().parents[1] / ".env"
NAMES = {
    "anthropic": "OSRIP_ANTHROPIC_API_KEY",
    "openai": "OSRIP_OPENAI_API_KEY",
    "gemini": "OSRIP_GEMINI_API_KEY",
    "brave": "OSRIP_RESEARCH_API_KEY",
}
MODELS = {
    "openai": ("OSRIP_OPENAI_MODEL", "OSRIP_OPENAI_SEARCH_MODEL"),
    "gemini": ("OSRIP_GEMINI_MODEL", "OSRIP_GEMINI_SEARCH_MODEL"),
}


def read_lines() -> list[str]:
    return ENV.read_text(encoding="utf-8-sig").splitlines() if ENV.exists() else []


def current(lines: list[str], name: str) -> str:
    for line in lines:
        if line.split("=", 1)[0].strip() == name and "=" in line:
            return line.split("=", 1)[1].strip()
    return ""


def ask(label: str, check) -> str | None:  # noqa: ANN001
    while True:
        value = getpass.getpass(f"{label} (hidden; Enter keeps the current one): ").strip()
        if not value:
            return None
        value = value.strip("'\"")
        problem = check(value)
        if not problem:
            return value
        print(f"  That does not look right: {problem}. Try again, or press Enter to skip.")


def masked(v: str) -> bool:
    return "..." in v or "…" in v or "*" in v


def anthropic_problem(v: str) -> str | None:
    if masked(v):
        return "this is the shortened preview the dashboard shows, not the full key"
    if not v.startswith("sk-ant-"):
        return "Anthropic API keys start with 'sk-ant-'"
    if v.startswith("sk-ant-admin"):
        return "this is an Admin key; create a normal API key instead"
    if len(v) < 60 or any(c.isspace() for c in v):
        return "it is too short or contains spaces (copy the whole key)"
    return None


def brave_problem(v: str) -> str | None:
    if masked(v):
        return "this is the shortened preview the dashboard shows, not the full token"
    if len(v) < 20 or any(c.isspace() for c in v):
        return "it is too short or contains spaces (copy the whole token)"
    return None


def openai_problem(v: str) -> str | None:
    if masked(v):
        return "this is the shortened preview the dashboard shows, not the full key"
    if not v.startswith("sk-"):
        return "OpenAI API keys start with 'sk-'"
    if len(v) < 40 or any(c.isspace() for c in v):
        return "it is too short or contains spaces (copy the whole key)"
    return None


def gemini_problem(v: str) -> str | None:
    if masked(v):
        return "this is the shortened preview the console shows, not the full key"
    if len(v) < 30 or any(c.isspace() for c in v):
        return "it is too short or contains spaces (copy the whole key)"
    return None


def write(lines: list[str], values: dict[str, str]) -> None:
    out, done = [], set()
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line else ""
        if name in values:
            out.append(f"{name}={values[name]}")
            done.add(name)
        else:
            out.append(line)
    out += [f"{name}={value}" for name, value in values.items() if name not in done]
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def test_anthropic(key: str) -> str:
    try:
        r = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return f"could not reach Anthropic ({exc.__class__.__name__})"
    if r.status_code == 200:
        return "OK, Anthropic accepted the key"
    return f"REJECTED (HTTP {r.status_code}: {r.json().get('error', {}).get('type', '?')})"


def test_brave(token: str) -> str:
    try:
        r = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": "Oman", "count": 1},
            headers={"X-Subscription-Token": token, "Accept": "application/json"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return f"could not reach Brave ({exc.__class__.__name__})"
    if r.status_code == 200:
        return "OK, Brave accepted the token"
    return f"REJECTED (HTTP {r.status_code}: {r.json().get('error', {}).get('code', '?')})"


def _models(lines: list[str], provider: str, available: set[str]) -> str:
    """Whether the model ids set in the file are in the account's model list (ids only)."""
    notes = []
    for setting in MODELS[provider]:
        model = current(lines, setting)
        if not model:
            notes.append(f"{setting} not set")
        else:
            notes.append(
                f"{setting}={model} {'listed' if model in available else 'NOT in the list'}"
            )
    return "; ".join(notes)


def test_openai(key: str, lines: list[str]) -> str:
    try:
        r = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return f"could not reach OpenAI ({exc.__class__.__name__})"
    if r.status_code != 200:
        return f"REJECTED (HTTP {r.status_code})"
    ids = {str(m.get("id")) for m in r.json().get("data", [])}
    return f"OK, OpenAI accepted the key. {_models(lines, 'openai', ids)}"


def test_gemini(key: str, lines: list[str]) -> str:
    try:
        r = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"pageSize": 1000},
            headers={"x-goog-api-key": key},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return f"could not reach the Gemini API ({exc.__class__.__name__})"
    if r.status_code != 200:
        return f"REJECTED (HTTP {r.status_code})"
    ids = {str(m.get("name", "")).removeprefix("models/") for m in r.json().get("models", [])}
    return f"OK, the Gemini API accepted the key. {_models(lines, 'gemini', ids)}"


def main() -> None:
    lines = read_lines()
    new = {}
    for provider, label, check in (
        ("anthropic", "Anthropic API key", anthropic_problem),
        ("openai", "OpenAI API key", openai_problem),
        ("gemini", "Gemini API key (Google AI Studio)", gemini_problem),
        ("brave", "Brave Search API token", brave_problem),
    ):
        value = ask(label, check)
        if value:
            new[NAMES[provider]] = value
    if new:
        write(lines, new)
        print(f"Saved to {ENV}")
    lines = read_lines()
    keys = {p: current(lines, name) for p, name in NAMES.items()}
    filled = [v for v in keys.values() if v]
    if len(filled) != len(set(filled)):
        print("Warning: two lines hold the same value; each service needs its own key.")
    if any(masked(v) for v in filled):
        print("Warning: the file holds a shortened key preview ('...' or '*'); paste the full key.")
    print(
        "Anthropic:",
        test_anthropic(keys["anthropic"]) if keys["anthropic"] else "no key in the file",
    )
    print("OpenAI:", test_openai(keys["openai"], lines) if keys["openai"] else "no key in the file")
    print("Gemini:", test_gemini(keys["gemini"], lines) if keys["gemini"] else "no key in the file")
    print("Brave Search:", test_brave(keys["brave"]) if keys["brave"] else "no token in the file")
    stray = [
        n
        for n, line in enumerate(lines, 1)
        if line.strip() and not line.lstrip().startswith("#") and "=" not in line
    ]
    if stray:
        print(f"Note: lines {', '.join(map(str, stray))} are not settings (no '='); delete them.")
    print("Restart the API afterwards so it reads the new keys.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
