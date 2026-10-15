"""The assistant's real-time voice worker (LiveKit Agents 1.8), for either persona.

Proposed orchestration, not yet run against a LiveKit project: no LiveKit URL, keys, speech
models, real-time voices or avatar provider are configured on this machine, so the worker has
only been checked to import and to wire the bridge correctly (``tests/test_voice_bridge.py``,
``tests/test_personas.py``).

How a call works once configured:
1. The browser asks the API for a short-lived room token (``POST /assistant/voice/realtime/
   session``). The token names one new room, allows publishing the microphone only, carries
   the language and the chosen persona in its signed metadata, and dispatches this agent.
2. This worker joins, reads the caller's identity, language and persona from the token, greets
   with that persona's approved introduction and listens. Speech-to-text uses
   ``OSRIP_VOICE_STT_MODEL``; text-to-speech uses the persona's real-time voice from the
   assistant profile (``voices.realtime``), so Al Mulhim and Ilham speak with the voices
   configured for them, never a renamed one.
3. Each finished question is answered by ``bridge.answer``: the same conversation service,
   tools, evidence checks and guest allowance as typed questions, whichever persona speaks.
4. With an avatar provider configured (``OSRIP_VOICE_AVATAR_PROVIDER``, the plugin installed and
   the persona's ``live_avatar_id`` in the profile), an avatar worker joins and publishes
   lip-synchronised video and the audio; otherwise the call is voice only.
5. The call ends when the caller leaves (the session closes and the room is deleted, which
   also removes the avatar worker), when the API's End call deletes the room, or after
   ``OSRIP_VOICE_MAX_CALL_MINUTES``.

Run (after configuring LiveKit):  python -m app.voice.agent dev
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, llm
from livekit.agents.voice import room_io

from app.core.config import get_settings
from app.core.errors import ApiError
from app.services import voice_realtime
from app.voice import bridge

log = logging.getLogger("osrip.voice")
server = AgentServer()


def latest_question(chat_ctx: llm.ChatContext) -> str:
    """The caller's most recent finished utterance."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and getattr(item, "role", None) == "user":
            return (item.text_content or "").strip()
    return ""


def avatar_session(provider: str, avatar_id: str, name: str) -> Any:
    """The provider's AvatarSession, as each plugin's guide documents it
    (docs.livekit.io/agents/models/avatar/, checked 10 October 2026)."""
    if provider not in voice_realtime.AVATAR_PROVIDERS:
        raise ValueError(f"avatar provider {provider} is not supported")
    module = importlib.import_module(f"livekit.plugins.{provider}")
    if provider == "anam":
        return module.AvatarSession(
            persona_config=module.PersonaConfig(name=name, avatarId=avatar_id)
        )
    return module.AvatarSession(avatar_id=avatar_id)  # liveavatar, bithuman, avatario


class AssistantVoice(Agent):
    """Replaces the agent's language model with OSRIP's own answer service."""

    def __init__(self, call: bridge.Call) -> None:
        super().__init__(
            instructions="Answers come from the OSRIP answer service; no text is generated here."
        )
        self.call = call

    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[Any], model_settings: Any
    ) -> str:  # type: ignore[override]
        question = latest_question(chat_ctx)
        if not question:
            return ""
        try:
            message = await asyncio.to_thread(bridge.answer, self.call, question)
        except ApiError as exc:
            return bridge.refusal(exc.code, self.call.language)
        except Exception:  # noqa: BLE001 - a failed answer is spoken as unavailable, and logged
            log.exception("voice answer failed")
            return bridge.UNAVAILABLE[self.call.language]
        return bridge.spoken(
            str(message.get("content", "")),
            self.call.language,
            cited=bool(message.get("citations")),
        )


@server.rtc_session(agent_name=voice_realtime.AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    s = get_settings()
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    try:
        caller = bridge.parse_identity(participant.identity)
    except ValueError:
        log.warning("refusing a participant without an OSRIP identity")
        ctx.shutdown("unknown participant")
        return
    language = bridge.parse_language(participant.metadata)
    who = await asyncio.to_thread(bridge.call_persona, bridge.parse_persona(participant.metadata))
    voice = who.voices.realtime.get(language) if who is not None else None
    if who is None or not voice:
        log.warning("no real-time voice configured for this persona and language")
        ctx.shutdown("voice_not_configured")
        return
    call = bridge.Call(caller, language, persona=who.code)
    session = AgentSession(stt=s.voice_stt_model, tts=voice, turn_detection="stt")

    # Whatever ends the job (caller left, End call, time limit), the room goes with it, so no
    # agent or avatar session keeps running (or billing) after the call.
    async def _delete_room() -> None:
        try:
            await ctx.delete_room()
        except Exception:  # noqa: BLE001 - already deleted by End call or the session
            log.info("room already closed")

    ctx.add_shutdown_callback(_delete_room)
    asyncio.get_running_loop().call_later(
        s.voice_max_call_minutes * 60, lambda: ctx.shutdown("max_call_minutes")
    )

    avatar = None
    if s.voice_avatar_provider and who.avatar.live_avatar_id:
        try:
            avatar = avatar_session(s.voice_avatar_provider, who.avatar.live_avatar_id, who.name.en)
            await avatar.start(session, room=ctx.room)
        except Exception:  # noqa: BLE001 - the call continues as voice only, and says so in logs
            log.exception("avatar could not start; continuing with voice only")
            avatar = None

    await session.start(
        agent=AssistantVoice(call),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            close_on_disconnect=True,  # the caller hanging up ends the session
            delete_room_on_close=True,  # and the room, with any avatar worker in it
            audio_output=avatar is None,  # with an avatar, its worker publishes the audio
        ),
    )
    session.say(bridge.greeting(language, who.code), allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(server)
