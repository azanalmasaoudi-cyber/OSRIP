"""Real-time voice for "Talk": readiness, short-lived LiveKit room tokens and ending a call.

The browser never holds a service credential. When the feature flag and a LiveKit project
are configured, ``issue_session`` returns a token that lets one participant join one new room
for a few minutes, publish microphone audio only and subscribe to the agent. The token's
metadata names the language and the chosen persona; the agent worker (``app/voice/agent.py``)
speaks with that persona's real-time voice from the assistant profile and answers through the
same conversation service, tools, evidence checks and guest allowance as typed questions.

``end_session`` deletes the room through the LiveKit server API when the caller ends the call,
which disconnects the agent and any avatar worker at once, so no paid session keeps running.
The agent also closes and deletes the room itself when the caller leaves (belt and braces).

Missing pieces are reported precisely (``readiness``) instead of being simulated.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.errors import ApiError

AGENT_NAME = "al-mulhim"
# Avatar plugins whose Python AvatarSession takes the avatar id in a documented argument
# (docs.livekit.io/agents/models/avatar/, checked 10 October 2026). Another provider needs its
# own entry in app/voice/agent.py before it can be used.
AVATAR_PROVIDERS = ("anam", "liveavatar", "bithuman", "avatario")


def _missing_service() -> list[str]:
    s = get_settings()
    missing = []
    if not s.voice_realtime_enabled:
        missing.append("OSRIP_VOICE_REALTIME_ENABLED=true")
    if not s.livekit_url or not s.livekit_url.startswith(("wss://", "ws://")):
        missing.append("OSRIP_LIVEKIT_URL (wss://…)")
    if not s.livekit_api_key:
        missing.append("OSRIP_LIVEKIT_API_KEY")
    if not s.livekit_api_secret:
        missing.append("OSRIP_LIVEKIT_API_SECRET")
    if not s.voice_stt_model:
        missing.append("OSRIP_VOICE_STT_MODEL")
    return missing


def _missing_voices(personas: list[Any]) -> list[str]:
    """Real-time voices not yet chosen in the assistant profile (named per persona)."""
    return [
        f"profile: real-time voice for {p.name.en} ({language})"
        for p in personas
        for language in ("ar", "en")
        if not p.voices.realtime.get(language)
    ]


def configured(personas: list[Any] | None = None) -> bool:
    if _missing_service():
        return False
    return not _missing_voices(personas or _active_personas())


def _active_personas() -> list[Any]:
    from app.services.assistant import profile

    current = profile.active_now()
    return profile.personas(current.profile) if current else []


def _sdk_installed() -> bool:
    try:
        import livekit.agents  # noqa: F401
        import livekit.api  # noqa: F401
    except ImportError:
        return False
    return True


def _avatar(personas: list[Any]) -> dict[str, Any]:
    s = get_settings()
    name = s.voice_avatar_provider
    ids = {p.code: bool(p.avatar.live_avatar_id) for p in personas}
    base = {"provider": name, "personas": ids}
    if not name:
        return {**base, "configured": False, "reason": "no avatar provider selected"}
    if name not in AVATAR_PROVIDERS:
        return {
            **base,
            "configured": False,
            "reason": f"avatar provider {name} is not supported yet",
        }
    try:
        __import__(f"livekit.plugins.{name}")
    except ImportError:
        return {
            **base,
            "configured": False,
            "reason": f"plugin livekit-agents[{name}] is not installed",
        }
    if not all(ids.values()):
        return {
            **base,
            "configured": False,
            "reason": "profile: live avatar id missing for "
            + ", ".join(p.name.en for p in personas if not p.avatar.live_avatar_id),
        }
    return {**base, "configured": True, "reason": None}


def readiness(personas: list[Any]) -> dict[str, Any]:
    """Public status: what works, what is missing (names of settings, never values)."""
    missing = _missing_service() + _missing_voices(personas)
    return {
        "configured": not missing,
        "agent_sdk_installed": _sdk_installed(),
        "missing": missing,
        "avatar": _avatar(personas),
        "fallback": "push_to_talk",
        "note": {
            "en": "Without a configured LiveKit project, Talk uses push-to-talk: you speak, check "
            "the transcript and send it. A still portrait of the chosen assistant is shown; it "
            "does not move its lips.",
            "ar": "عند عدم إعداد مشروع LiveKit، تعمل «تحدّث» بطريقة الضغط للتحدث: تتكلم ثم تراجع "
            "النص وترسله. تُعرض صورة ثابتة للمساعد المختار لا تحرّك شفتيها.",
        },
    }


def _end_key(room: str, identity: str) -> str:
    """Proof that this caller was given this room (so only they can end it)."""
    secret = get_settings().livekit_api_secret
    key = secret.get_secret_value().encode() if secret else b""
    return hmac.new(key, f"{room}|{identity}".encode(), hashlib.sha256).hexdigest()


def issue_session(
    *, identity: str, display_name: str, language: str, persona: Any
) -> dict[str, Any]:
    """A short-lived token for one new room, scoped to that room. ``identity`` is the
    server-side owner reference (``user:<id>`` or ``guest:<id>``) that the agent uses to
    charge answers to the right allowance; the client cannot choose it. ``persona`` (a profile
    persona) decides the agent's name, introduction, voice and avatar for this call."""
    lang = "ar" if language == "ar" else "en"
    missing = _missing_service() + _missing_voices([persona])
    if missing:
        raise ApiError(
            503,
            "voice_realtime_not_configured",
            "Real-time voice is not configured on this server.",
            {"missing": missing},
        )
    if not _sdk_installed():
        raise ApiError(503, "voice_realtime_unavailable", "The LiveKit SDK is not installed.")
    from livekit import api

    s = get_settings()
    room = f"osrip-{secrets.token_hex(8)}"
    ttl = timedelta(minutes=s.voice_token_minutes)
    token = (
        api.AccessToken(s.livekit_api_key, s.livekit_api_secret.get_secret_value())
        .with_identity(identity)
        .with_name(display_name)
        .with_ttl(ttl)
        .with_metadata(json.dumps({"language": lang, "persona": persona.code}))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_publish_sources=["microphone"],
                can_subscribe=True,
                can_publish_data=True,
                room_create=False,
                room_admin=False,
                room_list=False,
                room_record=False,
            )
        )
        .with_room_config(
            api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)])
        )
        .to_jwt()
    )
    return {
        "url": s.livekit_url,
        "room": room,
        "token": token,
        "end_key": _end_key(room, identity),
        "persona": persona.code,
        "expires_at": (datetime.now(UTC) + ttl).isoformat(),
        "max_call_minutes": s.voice_max_call_minutes,
    }


def _delete_room(room: str) -> None:
    """Delete a room through the LiveKit server API (disconnects everyone in it)."""
    from livekit import api

    s = get_settings()
    url = (s.livekit_url or "").replace("wss://", "https://").replace("ws://", "http://")

    async def run() -> None:
        async with api.LiveKitAPI(
            url, s.livekit_api_key, s.livekit_api_secret.get_secret_value()
        ) as client:
            await client.room.delete_room(api.DeleteRoomRequest(room=room))

    asyncio.run(run())


# Replaced in tests: no media server is contacted.
room_deleter: Callable[[str], None] = _delete_room


def end_session(*, room: str, end_key: str, identity: str) -> dict[str, Any]:
    """End the caller's call: the room is deleted, so the agent and any avatar worker leave
    and stop at once. Only the caller the room was issued to can end it."""
    if _missing_service():
        raise ApiError(503, "voice_realtime_not_configured", "Real-time voice is not configured.")
    if not room.startswith("osrip-") or not hmac.compare_digest(end_key, _end_key(room, identity)):
        raise ApiError(404, "not_found", "Call not found.")
    try:
        room_deleter(room)
    except Exception as exc:  # noqa: BLE001 - reported, never hidden
        if "not found" in str(exc).lower():
            return {"ended": True, "room": room, "already_closed": True}
        raise ApiError(502, "voice_realtime_end_failed", "The call could not be closed.") from exc
    return {"ended": True, "room": room, "already_closed": False}
