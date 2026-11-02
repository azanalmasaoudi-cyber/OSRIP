"""WhatsApp verification (Meta Cloud API) setup for OSRIP, using backend/.env.

Run it yourself in a terminal, from backend\\:
    .venv\\Scripts\\python.exe scripts\\whatsapp_setup.py configure        # store the settings
    .venv\\Scripts\\python.exe scripts\\whatsapp_setup.py create-template  # en and ar template
    .venv\\Scripts\\python.exe scripts\\whatsapp_setup.py status           # check everything

* ``configure`` asks for the access token at a hidden prompt (nothing is echoed or
  printed), then for the phone number ID, the WhatsApp Business Account ID and the
  approved test recipients. It writes those lines to backend/.env, with
  OSRIP_SMS_PROVIDER=whatsapp and OSRIP_WHATSAPP_MODE=test; other lines are kept. Press
  Enter to keep a value already in the file. It does not switch phone verification on.
* ``create-template`` creates the authentication template (Meta's preset text, a
  security note, the expiry footer and a copy-code button) in English and Arabic.
* ``status`` reads the sender number and the template's review status.

None of these sends a WhatsApp message or costs anything. Production mode (charged per
delivered code) is never set by this script.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
ENV = BACKEND / ".env"
GRAPH = "https://graph.facebook.com"


def read_lines() -> list[str]:
    return ENV.read_text(encoding="utf-8-sig").splitlines() if ENV.exists() else []


def current(lines: list[str], name: str) -> str:
    for line in lines:
        if line.split("=", 1)[0].strip() == name and "=" in line:
            return line.split("=", 1)[1].strip()
    return ""


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


def settings():  # noqa: ANN201
    os.chdir(BACKEND)  # the settings read .env from the working directory
    sys.path.insert(0, str(BACKEND))
    from app.core.config import get_settings

    get_settings.cache_clear()
    return get_settings()


def configure() -> None:
    lines = read_lines()
    new: dict[str, str] = {}
    token = getpass.getpass("Access token (hidden; Enter keeps the current one): ").strip()
    if token:
        if "..." in token or "…" in token or any(c.isspace() for c in token) or len(token) < 50:
            print("That does not look like a whole access token; nothing was saved for it.")
        else:
            new["OSRIP_WHATSAPP_ACCESS_TOKEN"] = token
    for name, label in (
        ("OSRIP_WHATSAPP_PHONE_NUMBER_ID", "Phone number ID (digits, from API Setup)"),
        ("OSRIP_WHATSAPP_BUSINESS_ACCOUNT_ID", "WhatsApp Business Account ID (digits)"),
    ):
        value = input(f"{label} [{current(lines, name) or 'not set'}]: ").strip()
        if value and not value.isdigit():
            print(f"  {name} must be digits only; not saved.")
        elif value:
            new[name] = value
    recipients = input(
        "Approved test recipients, comma-separated, e.g. +96891234567"
        " (Enter keeps the current list): "
    ).strip()
    if recipients:
        new["OSRIP_WHATSAPP_TEST_RECIPIENTS"] = recipients
    new["OSRIP_SMS_PROVIDER"] = "whatsapp"
    new["OSRIP_WHATSAPP_MODE"] = "test"
    write(lines, new)
    print(f"Saved to {ENV} (test mode). Phone verification is switched on only by")
    print("OSRIP_SMS_ENABLED=true; set it after 'status' shows an APPROVED template.")


def _get(path: str, token: str, version: str, params: dict[str, str]) -> tuple[int, dict]:
    try:
        r = httpx.get(
            f"{GRAPH}/{version}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return 0, {"error": {"message": exc.__class__.__name__}}
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def _error(body: dict) -> str:
    e = body.get("error") or {}
    return f"Meta error {e.get('code', '?')}: {e.get('message', 'no details')}"


def status() -> int:
    s = settings()
    from app.services import sms

    token = s.whatsapp_access_token.get_secret_value() if s.whatsapp_access_token else ""
    ok = True
    print(f"OSRIP_SMS_ENABLED={s.sms_enabled}  OSRIP_SMS_PROVIDER={s.sms_provider or '(empty)'}")
    print(f"OSRIP_WHATSAPP_MODE={s.whatsapp_mode}")
    missing = sms.whatsapp_missing()
    if missing:
        print("Missing:", "; ".join(missing))
        ok = False
    recipients = sms.parse_recipients(s.whatsapp_test_recipients)
    print(f"Approved test recipients in the file: {len(recipients)} (Meta allows up to 5)")
    if not token or not s.whatsapp_phone_number_id:
        return 1
    code, body = _get(
        s.whatsapp_phone_number_id,
        token,
        s.whatsapp_api_version,
        {"fields": "display_phone_number,verified_name,quality_rating"},
    )
    if code == 200:
        print(
            f"Sender: {body.get('display_phone_number')} ({body.get('verified_name')}), "
            f"quality {body.get('quality_rating', 'unknown')}"
        )
    else:
        print("Sender check FAILED:", _error(body))
        ok = False
    if not s.whatsapp_business_account_id:
        print("Template: OSRIP_WHATSAPP_BUSINESS_ACCOUNT_ID is not set, so it cannot be checked")
        return 1
    code, body = _get(
        f"{s.whatsapp_business_account_id}/message_templates",
        token,
        s.whatsapp_api_version,
        {"name": s.whatsapp_template_name, "fields": "name,language,status,category"},
    )
    if code != 200:
        print("Template check FAILED:", _error(body))
        return 1
    found = {
        t.get("language"): t
        for t in body.get("data", [])
        if t.get("name") == s.whatsapp_template_name
    }
    for language in sms.WHATSAPP_LANGUAGES.values():
        t = found.get(language)
        state = f"{t.get('status')} ({t.get('category')})" if t else "NOT CREATED"
        print(f"Template {s.whatsapp_template_name} [{language}]: {state}")
        ok = ok and bool(t) and t.get("status") == "APPROVED"
    print("Ready for the test-mode demonstration." if ok else "Not ready yet (see above).")
    return 0 if ok else 1


def create_template() -> int:
    s = settings()
    from app.services import sms

    if not (s.whatsapp_access_token and s.whatsapp_business_account_id):
        print("Set the access token and the WhatsApp Business Account ID first (configure).")
        return 1
    minutes = max(1, min(90, s.sms_code_minutes))
    failed = False
    for language in sms.WHATSAPP_LANGUAGES.values():
        payload = {
            "name": s.whatsapp_template_name,
            "language": language,
            "category": "authentication",
            "message_send_ttl_seconds": max(30, min(900, minutes * 60)),
            "components": [
                {"type": "body", "add_security_recommendation": True},
                {"type": "footer", "code_expiration_minutes": minutes},
                {"type": "buttons", "buttons": [{"type": "otp", "otp_type": "copy_code"}]},
            ],
        }
        try:
            r = httpx.post(
                f"{GRAPH}/{s.whatsapp_api_version}/{s.whatsapp_business_account_id}/message_templates",
                json=payload,
                headers={"Authorization": f"Bearer {s.whatsapp_access_token.get_secret_value()}"},
                timeout=20,
            )
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            print(f"[{language}] could not reach Meta ({exc.__class__.__name__})")
            failed = True
            continue
        if r.status_code == 200:
            print(f"[{language}] created: status {body.get('status', 'PENDING')}")
        else:
            print(f"[{language}] refused: {_error(body)}")
            failed = True
    print(
        "Run 'status' to follow the review; authentication templates are usually reviewed quickly."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if command == "configure":
            configure()
        elif command == "create-template":
            sys.exit(create_template())
        elif command == "status":
            sys.exit(status())
        else:
            print(__doc__)
            sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(1)
