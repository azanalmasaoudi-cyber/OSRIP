"""A live check of the website assistant against a running API that uses backend/.env.

    .venv\\Scripts\\python.exe scripts\\live_assistant_check.py --api http://127.0.0.1:8010/api/v1

1. Project data on its own (no model): the assistant's data tools read the published data in
   the local development database (osrip_dev, as serve_dev.py uses), exactly as the model reads
   them through its tools.
2. The answer service the website reports (provider and model names, state).
3. The chat endpoint the website uses (POST /assistant/guest/messages, mode "auto"), as one
   guest: an English question, a follow-up that only makes sense with the conversation
   ("Compare it with the previous year."), and an Arabic question. For each: status, the
   provider and model that answered (from the reply's own record), the indicators cited, the
   time, and the guest's remaining answers before and after.

Prints no key and at most the first 140 characters of an answer. Uses up to three of one new
guest's five answers (a failed answer is not counted). Exit code 0 only if every question was
answered by the configured provider.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
os.chdir(BACKEND)

QUESTIONS = (
    ("en", "What is the latest published gross electricity generation in Oman?"),
    ("en", "Compare it with the previous year."),
    ("ar", "ما آخر قيمة منشورة لإنتاج المياه في عُمان؟"),
)


def project_data() -> dict[str, Any]:
    """The assistant's own data tools, without any model."""
    from devdb import admin_url

    os.environ.setdefault("OSRIP_DATABASE_URL", admin_url("osrip_dev"))
    from app.db.session import session_factory
    from app.domain.enums import DataMode
    from app.services.assistant.tools import Ledger, Tools

    with session_factory()() as session:
        tools = Tools(session, Ledger(DataMode.VERIFIED_SOURCE))
        found = tools.latest_period("ELEC_GROSS_GENERATION")
    latest = (found.get("latest_by_series") or [{}])[0]
    return {
        "status": found.get("status"),
        "indicator": "ELEC_GROSS_GENERATION",
        "period_start": latest.get("period_start"),
        "value": latest.get("value"),
        "unit": latest.get("unit"),
        "evidence_id": latest.get("id"),
    }


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf: str | None = None

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.csrf:
            headers["X-Guest-CSRF"] = self.csrf
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(  # noqa: S310 - http(s) only, checked in main()
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=180) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"error: {method} {path} answered HTTP {exc.code}") from exc

    def guest(self) -> dict[str, Any]:
        """A guest session (its cookie) and the token its requests must carry."""
        status = self.call("GET", "/assistant/guest")
        self.csrf = next((c.value for c in self.jar if c.name == "osrip_guest_csrf"), None)
        return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--api", default="http://127.0.0.1:8010/api/v1")
    args = parser.parse_args()
    if not args.api.startswith(("http://", "https://")):
        raise SystemExit("error: --api must be an http(s) address")

    print("1. Project data, without a model:")
    print("   " + json.dumps(project_data(), ensure_ascii=False))

    api = Api(args.api)
    status = api.call("GET", "/assistant/status")
    health = (status.get("health") or {}).get("state")
    print(
        f"2. Answer service: provider {status.get('provider')}, model {status.get('model')}, "
        f"configured {status.get('configured')}, state {health}"
    )
    expected = status.get("provider")

    guest = api.guest()
    remaining = (guest.get("allowance") or {}).get("remaining")
    print(f"3. Chat endpoint as a guest ({remaining} answers left):")
    conversation = None
    ok = True
    for language, question in QUESTIONS:
        started = time.monotonic()
        result = api.call("POST", "/assistant/guest/messages", {
            "content": question, "language": language, "request_id": str(uuid.uuid4()),
            "conversation_id": conversation, "data_mode": "verified_source", "mode": "auto",
        })  # fmt: skip
        seconds = time.monotonic() - started
        conversation = result["conversation_id"]
        message = result["message"]
        method = (message.get("structured") or {}).get("method") or {}
        cited = sorted(
            {e.get("indicator") for e in message.get("evidence", []) if e.get("indicator")}
        )
        left = (result.get("allowance") or {}).get("remaining")
        answered = message.get("status") == "answered" and method.get("answer_provider") == expected
        ok = ok and answered
        print(f"   [{language}] {question}")
        print(
            f"      status {message.get('status')}, mode {message.get('mode')}, by "
            f"{method.get('answer_provider')} / {method.get('answer_model')}, "
            f"{len(message.get('citations') or [])} citations, indicators {cited}, "
            f"{seconds:.1f} s, answers left {remaining} -> {left}"
        )
        print(f"      {message.get('content', '')[:140]!r}")
        remaining = left
    print(
        "Result: all answered by " + str(expected)
        if ok
        else "Result: NOT all answered by the provider"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
