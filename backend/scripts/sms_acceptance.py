"""Live SMS delivery acceptance test, for ONE authorized phone number.

Run it against a running OSRIP API whose SMS provider is a real one (not "test"),
with the owner of the number present to read the message:

    python scripts/sms_acceptance.py --url http://127.0.0.1:8010

The number is typed at the prompt (or set in OSRIP_SMS_ACCEPTANCE_NUMBER for the
current shell only). The script:

1. asks the API to send a code (POST /auth/phone/request) and times the call;
2. asks the operator to type the code that arrived, and how long it took;
3. submits a deliberately wrong code first and expects "sms_code_incorrect";
4. submits the real code and expects "registered" or "signed_in";
5. replays the same code and expects "sms_challenge_invalid" (single use).

It writes docs/sms/acceptance-<UTC time>.json with the outcomes, the provider name
and the number MASKED (country code and last two digits). The code itself is never
written anywhere and never printed. Verifying signs in (or creates an ordinary
account) for that number on the target database; use a test deployment.

SMS must not be reported as active until this script has passed for the provider.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.phone_numbers import mask, normalize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", required=True, help="API origin, e.g. https://osrip.example.org")
    parser.add_argument("--country", default="+968")
    args = parser.parse_args()
    api = args.url.rstrip("/") + "/api/v1"
    result: dict[str, object] = {"started_at": datetime.now(UTC).isoformat(), "api": args.url}

    with httpx.Client(timeout=30) as client:
        status = client.get(f"{api}/auth/providers").json()["sms"]
        result["provider"] = status.get("provider")
        result["provider_status"] = status.get("status")
        if status.get("status") != "configured":
            print(
                f"Refused: SMS status is '{status.get('status')}'. Acceptance needs a real, configured provider."
            )
            return 2

        raw = os.environ.get("OSRIP_SMS_ACCEPTANCE_NUMBER") or input(
            "Authorized mobile number (national digits): "
        )
        e164 = normalize(args.country, raw)
        result["phone"] = mask(e164)

        t0 = time.monotonic()
        sent = client.post(
            f"{api}/auth/phone/request",
            json={"country_code": args.country, "number": raw, "purpose": "sign_in"},
        )
        result["request_status"] = sent.status_code
        result["request_seconds"] = round(time.monotonic() - t0, 2)
        if sent.status_code != 202:
            result["request_error"] = sent.json().get("error", {}).get("code")
            return _finish(result, passed=False)
        challenge = sent.json()["challenge_id"]

        code = getpass.getpass("Code received by SMS (not shown): ").strip()
        result["delivered"] = bool(code)
        seconds = input("About how many seconds until the SMS arrived? ").strip()
        result["delivery_seconds_reported"] = (
            float(seconds) if seconds.replace(".", "", 1).isdigit() else None
        )

        wrong = "".join(str((int(c) + 1) % 10) for c in code) if code.isdigit() else "000000"
        bad = client.post(
            f"{api}/auth/phone/verify", json={"challenge_id": challenge, "code": wrong}
        )
        result["wrong_code_error"] = bad.json().get("error", {}).get("code")

        good = client.post(
            f"{api}/auth/phone/verify", json={"challenge_id": challenge, "code": code}
        )
        result["verify_status"] = good.status_code
        result["verify_outcome"] = (
            good.json().get("status")
            if good.status_code == 200
            else good.json().get("error", {}).get("code")
        )

        replay = client.post(
            f"{api}/auth/phone/verify", json={"challenge_id": challenge, "code": code}
        )
        result["replay_error"] = replay.json().get("error", {}).get("code")
        del code, wrong

    passed = (
        result.get("wrong_code_error") == "sms_code_incorrect"
        and result.get("verify_outcome") in ("registered", "signed_in")
        and result.get("replay_error") == "sms_challenge_invalid"
    )
    return _finish(result, passed=passed)


def _finish(result: dict[str, object], *, passed: bool) -> int:
    result["passed"] = passed
    result["finished_at"] = datetime.now(UTC).isoformat()
    out = ROOT / "docs" / "sms"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"acceptance-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"{'PASSED' if passed else 'FAILED'}: results in {path.relative_to(ROOT)} (number masked, no code stored)"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
