"""The link between a real-time voice call and the assistant's ordinary answer service.

Nothing here imports LiveKit, so it can be tested without a media server. The voice agent
(``app/voice/agent.py``) passes each finished spoken question to ``answer``, which uses the
same conversation service, tools, evidence checks, profile replies and guest allowance as a
typed question; the reply's text is then made speakable (``spoken``).

The caller is identified only by the room token's identity, which the API signed when it
issued the token (``user:<uuid>`` or ``guest:<uuid>``); nothing the caller says can change
it. Each spoken question gets its own request id, so a retry is never charged twice.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.errors import ApiError
from app.domain.enums import AccountStatus, DataMode, Permission

Language = Literal["en", "ar"]


@dataclass(frozen=True)
class Caller:
    kind: Literal["user", "guest"]
    id: uuid.UUID


def parse_identity(identity: str) -> Caller:
    """``user:<uuid>`` or ``guest:<uuid>`` from the signed room token; anything else is refused."""
    kind, _, raw = identity.partition(":")
    if kind not in ("user", "guest"):
        raise ValueError("unknown participant identity")
    return Caller(kind, uuid.UUID(raw))  # type: ignore[arg-type]


def _metadata(metadata: str | None) -> dict[str, Any]:
    try:
        value = json.loads(metadata or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def parse_language(metadata: str | None) -> Language:
    return "ar" if _metadata(metadata).get("language") == "ar" else "en"


def parse_persona(metadata: str | None) -> str | None:
    """The persona code the API put in the signed token (checked against the profile later)."""
    value = _metadata(metadata).get("persona")
    return (
        value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value) else None
    )


_MARKER = re.compile(r"\s*\[(?:E|S)\d+(?:,\s*(?:E|S)\d+)*\]")
_MARKUP = re.compile(r"[*_`#>|]+")

ON_SCREEN = {
    "en": "The sources are shown on screen.",
    "ar": "المصادر معروضة على الشاشة.",
}


def spoken(text: str, language: Language, *, cited: bool) -> str:
    """Reply text for speech: citation markers and markup removed (they stay on screen),
    plus one short pointer to the on-screen sources when the reply cites any."""
    clean = _MARKUP.sub("", _MARKER.sub("", text))
    clean = re.sub(r"\s+", " ", clean).strip()
    return f"{clean} {ON_SCREEN[language]}" if cited and clean else clean


REFUSALS = {
    "guest_allowance_exhausted": {
        "en": "You have used the free answers for this browser. "
        "Sign in or create an account to keep asking.",
        "ar": "استخدمتَ الإجابات المجانية لهذا المتصفح. سجّل الدخول أو أنشئ حساباً لمواصلة الأسئلة.",
    },
    "permission_denied": {
        "en": "Your account cannot use the assistant.",
        "ar": "لا يستطيع حسابك استخدام المساعد.",
    },
    "authentication_required": {
        "en": "Your session has ended. Sign in again to continue.",
        "ar": "انتهت جلستك. سجّل الدخول مجدداً للمتابعة.",
    },
    "guest_session_required": {
        "en": "Your guest session has expired. Reload the page to continue.",
        "ar": "انتهت جلسة الزائر. أعد تحميل الصفحة للمتابعة.",
    },
}
UNAVAILABLE = {
    "en": "I cannot answer right now. Please try again in a moment.",
    "ar": "لا أستطيع الإجابة الآن. حاول مرة أخرى بعد قليل.",
}


def refusal(code: str, language: Language) -> str:
    """What the agent says when the service refuses a question (the same refusal a typed
    question gets, spoken)."""
    return REFUSALS.get(code, UNAVAILABLE)[language]


def call_persona(code: str | None) -> Any:
    """The persona for a call (the default one when the code is missing or unknown)."""
    from app.services.assistant import profile

    current = profile.active_now()
    if current is None:
        return None
    codes = {p.code for p in profile.personas(current.profile)}
    return profile.persona(current.profile, code if code in codes else None)


def greeting(language: Language, persona: str | None = None) -> str:
    """The approved introduction of the call's persona from the active profile (never
    generated)."""
    who = call_persona(persona)
    if who is None:
        return "مرحباً." if language == "ar" else "Hello."
    return str(getattr(who.introduction, language))


@dataclass
class Call:
    """One voice call: who is calling, in which language and data mode, with which persona,
    and the conversation the spoken questions and answers are kept in."""

    caller: Caller
    language: Language
    data_mode: DataMode = DataMode.VERIFIED_SOURCE
    conversation_id: uuid.UUID | None = None
    answers: list[dict[str, Any]] = field(default_factory=list)
    persona: str | None = None


def answer(call: Call, question: str, *, client: str = "voice-agent") -> dict[str, Any]:
    """Answer one spoken question through the ordinary service and return the stored
    message. Refusals (no permission, allowance used up) come back as ``ApiError`` with the
    same codes a typed question would get."""
    from app.db.session import session_factory
    from app.models import AppUser
    from app.services import accounts
    from app.services.assistant import guest, service

    request_id = uuid.uuid4()
    with session_factory()() as session:
        if call.caller.kind == "guest":
            result = guest.ask(
                session,
                None,
                None,
                client,
                content=question,
                language=call.language,
                request_id=request_id,
                conversation_id=call.conversation_id,
                data_mode=call.data_mode,
                web=False,
                verified_guest_id=call.caller.id,
                persona=call.persona,
            )
            call.conversation_id = uuid.UUID(result["conversation_id"])
            message = result["message"]
        else:
            with session.begin():
                user = session.get(AppUser, call.caller.id)
                if user is None or user.status != AccountStatus.ACTIVE:
                    raise ApiError(401, "authentication_required", "Sign in to continue.")
                principal = accounts.load_principal(session, user)
                if principal.password_change_required or not principal.has(
                    Permission.ASSISTANT_USE
                ):
                    raise ApiError(
                        403, "permission_denied", "Your account cannot use the assistant."
                    )
                if call.conversation_id is None:
                    created = service.create_conversation(
                        session, principal, call.language, call.data_mode
                    )
                    call.conversation_id = uuid.UUID(created["id"])
            message = service.ask(
                session,
                principal,
                call.conversation_id,
                question,
                call.language,
                request_id,
                web=False,
                client_key=client,
                persona=call.persona,
            )
    call.answers.append(message)
    return message
