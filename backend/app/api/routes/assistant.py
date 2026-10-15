"""In-app assistant (replies only to messages submitted inside OSRIP).

Signed-in users: ``/assistant/conversations`` (``assistant.use``, per-minute, per-hour
and daily fair-use limits). Visitors without an account: ``/assistant/guest``, five
successful answers per guest session (booklet 3.35).
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, DbSession, require, require_authenticated
from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import ApiError
from app.domain.enums import DataMode, Permission
from app.models import AppUser, AssistantConversation, AssistantMessage
from app.services import speech, voice_realtime
from app.services.assistant import guest, profile, service
from app.services.principal import Principal

router = APIRouter(prefix="/assistant", tags=["assistant"])
User = Annotated[Principal, Depends(require(Permission.ASSISTANT_USE))]


@router.get("/status")
def assistant_status() -> dict[str, Any]:
    """Public: whether the assistant is configured, its limits and suggested questions."""
    return service.status()


@router.get("/profile")
def assistant_profile(session: DbSession) -> dict[str, Any]:
    """Public, read-only: the active version of the assistant's identity, personas and
    approved project knowledge. There is deliberately no write route; new versions are
    published by an operator (``python -m app.cli assistant-profile publish FILE``)."""
    with session.begin():
        current = profile.active(session)
        if current is None:
            raise ApiError(503, "assistant_profile_missing", "No assistant profile is active.")
        view = profile.public_view(current)
        view["personas"] = [
            p.model_dump(mode="json", exclude_none=True) for p in profile.personas(current.profile)
        ]
        return view


PERSONA_CODE = r"^[a-z][a-z0-9_]{0,31}$"


class PersonaIn(BaseModel):
    persona: str = Field(pattern=PERSONA_CODE)


@router.get("/persona")
def persona_choice(session: DbSession, principal: CurrentPrincipal) -> dict[str, Any]:
    """The signed-in person's saved persona (null: the default). Visitors without an account
    keep their choice in this browser only, so nothing is stored for them here."""
    with session.begin():
        if not principal.is_authenticated:
            return {"persona": None, "stored": "browser"}
        user = session.get(AppUser, principal.user_id)
        return {"persona": user.assistant_persona if user else None, "stored": "account"}


@router.put("/persona")
def save_persona_choice(
    body: PersonaIn,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> dict[str, Any]:
    """Save the signed-in person's persona (a preference: it changes who speaks, never the
    knowledge, tools, permissions, sources, history or limits)."""
    with session.begin():
        code = service.resolve_persona(session, body.persona)
        user = session.get(AppUser, principal.user_id)
        if user is None:
            raise ApiError(401, "authentication_required", "Sign in to continue.")
        user.assistant_persona = code
        return {"persona": code, "stored": "account"}


class ConversationIn(BaseModel):
    language: Literal["en", "ar"] = "en"
    data_mode: DataMode = DataMode.VERIFIED_SOURCE


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    language: Literal["en", "ar"] = "en"
    # Optional idempotency key: a repeated submission returns the stored reply.
    request_id: uuid.UUID | None = None
    # The reader may switch internet search off for a question.
    web_research: bool = True
    # Ask, Analyze, Research (web search when configured), Compare or Scenario.
    mode: Literal["ask", "analyze", "research", "compare", "scenario"] = "ask"
    # Who replies (a persona code from the profile); default: the saved choice, then the
    # profile's default persona.
    persona: str | None = Field(default=None, pattern=PERSONA_CODE)
    # Research mode only: also search with the second search route, as a cross-check the
    # person asked for (never automatic).
    cross_check: bool = False


@router.get("/conversations")
def conversations(session: DbSession, principal: User) -> list[dict[str, Any]]:
    with session.begin():
        return service.list_conversations(session, principal)


@router.post("/conversations", status_code=201)
def create(body: ConversationIn, session: DbSession, principal: User) -> dict[str, Any]:
    with session.begin():
        return service.create_conversation(session, principal, body.language, body.data_mode)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: uuid.UUID, session: DbSession, principal: User) -> dict[str, Any]:
    with session.begin():
        return service.get_conversation(session, principal, conversation_id)


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def ask(
    conversation_id: uuid.UUID,
    body: MessageIn,
    request: Request,
    session: DbSession,
    principal: User,
) -> dict[str, Any]:
    return service.ask(
        session,
        principal,
        conversation_id,
        body.content,
        body.language,
        body.request_id,
        web=body.web_research,
        client_key=guest._client_hash(_client(request)),
        mode=body.mode,
        persona=body.persona,
        cross_check=body.cross_check,
    )


@router.get("/requests/{request_id}/progress")
def request_progress(request_id: uuid.UUID, session: DbSession, principal: User) -> dict[str, Any]:
    """The stages reached so far by one of the caller's questions (polled while it runs)."""
    with session.begin():
        return service.request_progress(session, request_id, user_id=principal.user_id)


@router.post("/requests/{request_id}/cancel", status_code=202)
def cancel_request(request_id: uuid.UUID, session: DbSession, principal: User) -> dict[str, Any]:
    """Stop one of the caller's running questions; it ends unanswered and is not counted."""
    with session.begin():
        return service.cancel_request(session, request_id, user_id=principal.user_id)


# ------------------------------------------------------------------ live study events

STREAM_WAIT_SECONDS = 20  # for a request that has not reached the database yet
STREAM_MAX_SECONDS = 600
STREAM_POLL_SECONDS = 0.3


def _sse(event: dict[str, Any]) -> str:
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n"


async def _study_stream(
    request: Request, request_id: uuid.UUID, user_id: uuid.UUID | None,
    guest_id: uuid.UUID | None, after: int,
) -> AsyncIterator[str]:  # fmt: skip
    """Server-sent events of one study: everything after ``after`` (a reconnect resumes),
    then new events as they are written, until the study ends."""
    from app.services.assistant import study_events

    yield "retry: 2000\n\n"
    started = time.monotonic()
    last_ping = started
    pk: int | None = None
    last_type: str | None = None
    settled_at: float | None = None
    while not await request.is_disconnected():
        now = time.monotonic()
        if now - started > STREAM_MAX_SECONDS:
            break
        if pk is None:
            pk, _ = await asyncio.to_thread(
                study_events.find_request, request_id, user_id, guest_id
            )
            if pk is None:
                if now - started > STREAM_WAIT_SECONDS:
                    yield 'event: end\ndata: {"reason":"unknown"}\n\n'
                    return
                await asyncio.sleep(STREAM_POLL_SECONDS)
                continue
        rows, state = await asyncio.to_thread(study_events.read_after, pk, after)
        for e in rows:
            yield _sse(e)
            after, last_type = e["seq"], e["type"]
        if rows or state == "reserved":
            settled_at = None
        elif settled_at is None:
            settled_at = now
        # The study ended (a retry of the same request starts a new attempt while reserved),
        # the request finished without a study (an approved greeting reply), or it finished
        # and no closing event followed within a few seconds.
        if settled_at is not None and (
            last_type in study_events.TERMINAL or last_type is None or now - settled_at > 5
        ):
            yield 'event: end\ndata: {"reason":"finished"}\n\n'
            return
        if now - last_ping > 15:
            last_ping = now
            yield ": keep-alive\n\n"
        await asyncio.sleep(STREAM_POLL_SECONDS)


def _stream_response(
    request: Request, request_id: uuid.UUID, user_id: uuid.UUID | None,
    guest_id: uuid.UUID | None, after: int,
) -> StreamingResponse:  # fmt: skip
    resume = request.headers.get("last-event-id", "")
    start = max(after, int(resume) if resume.isdigit() else 0)
    return StreamingResponse(
        _study_stream(request, request_id, user_id, guest_id, start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/requests/{request_id}/events")
def request_events(
    request_id: uuid.UUID, request: Request, principal: User, after: int = 0
) -> StreamingResponse:
    """The live study of one of the caller's questions, as server-sent events (another
    person's request is never found: its stream ends at once with ``end``)."""
    return _stream_response(request, request_id, principal.user_id, None, after)


@router.get("/requests/{request_id}/study")
def request_study(request_id: uuid.UUID, session: DbSession, principal: User) -> dict[str, Any]:
    """Every event of one of the caller's studies, to return to it later."""
    with session.begin():
        return service.study_events(session, request_id, user_id=principal.user_id)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete(conversation_id: uuid.UUID, session: DbSession, principal: User) -> Response:
    with session.begin():
        service.delete_conversation(session, principal, conversation_id)
    return Response(status_code=204)


@router.delete("/conversations")
def delete_all(session: DbSession, principal: User) -> dict[str, int]:
    """Delete every conversation of the signed-in user (saved research is kept separately)."""
    with session.begin():
        return {"deleted": service.delete_all_conversations(session, principal)}


@router.get("/memory")
def memory(
    session: DbSession, principal: Annotated[Principal, Depends(require_authenticated)]
) -> dict[str, Any]:
    """What Al Mulhim keeps for this account, by kind, with the retention rule."""
    with session.begin():
        return service.memory_summary(session, principal)


# ------------------------------------------------------------------ guests


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_guest_cookies(response: Response, issued: guest.Issued) -> None:
    settings = get_settings()
    max_age = settings.guest_session_days * 86400
    if issued.token:
        response.set_cookie(
            guest.GUEST_COOKIE,
            issued.token,
            max_age=max_age,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="strict",
            path="/",
        )
    if issued.csrf:
        # Readable by the app's scripts and echoed in X-Guest-CSRF (double submit).
        response.set_cookie(
            guest.GUEST_CSRF_COOKIE,
            issued.csrf,
            max_age=max_age,
            httponly=False,
            secure=settings.session_cookie_secure,
            samesite="strict",
            path="/",
        )
    response.headers["Cache-Control"] = "no-store"


class GuestMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    language: Literal["en", "ar"] = "en"
    request_id: uuid.UUID  # required: retries must not be charged twice
    conversation_id: uuid.UUID | None = None
    data_mode: DataMode = DataMode.VERIFIED_SOURCE
    web_research: bool = True
    mode: Literal["ask", "analyze", "research", "compare", "scenario"] = "ask"
    persona: str | None = Field(default=None, pattern=PERSONA_CODE)
    cross_check: bool = False


@router.get("/guest")
def guest_status(
    request: Request, response: Response, session: DbSession, principal: CurrentPrincipal
) -> dict[str, Any]:
    """The visitor's guest allowance, issuing the anonymous cookie on first use. Signed-in
    users get ``authenticated: true`` and whether guest history can be linked."""
    token = request.cookies.get(guest.GUEST_COOKIE)
    if principal.is_authenticated:
        with session.begin():
            found = guest._find(session, token)
            linkable = found is not None and bool(guest.status(session, found)["conversations"])
        response.headers["Cache-Control"] = "no-store"
        return {"authenticated": True, "linkable_history": linkable, "notice": guest.NOTICE}
    with session.begin():
        issued = guest.ensure(
            session, token, request.cookies.get(guest.GUEST_CSRF_COOKIE), _client(request)
        )
        body = {"authenticated": False, **guest.status(session, issued.guest)}
    _set_guest_cookies(response, issued)
    return body


@router.get("/guest/conversations/{conversation_id}")
def guest_conversation(
    conversation_id: uuid.UUID, request: Request, session: DbSession
) -> dict[str, Any]:
    with session.begin():
        return guest.get_conversation(
            session,
            request.cookies.get(guest.GUEST_COOKIE),
            request.headers.get(guest.GUEST_CSRF_HEADER)
            or request.cookies.get(guest.GUEST_CSRF_COOKIE),
            conversation_id,
        )


@router.delete("/guest/conversations/{conversation_id}", status_code=204)
def guest_delete_conversation(
    conversation_id: uuid.UUID, request: Request, session: DbSession
) -> Response:
    """A guest deletes one of this browser's conversations. The allowance already used is
    unchanged (deleting history never returns answers)."""
    with session.begin():
        guest.delete_conversation(
            session,
            request.cookies.get(guest.GUEST_COOKIE),
            request.headers.get(guest.GUEST_CSRF_HEADER),
            conversation_id,
        )
    return Response(status_code=204)


@router.get("/guest/requests/{request_id}/progress")
def guest_request_progress(
    request_id: uuid.UUID, request: Request, session: DbSession
) -> dict[str, Any]:
    with session.begin():
        g = guest._require(
            session,
            request.cookies.get(guest.GUEST_COOKIE),
            request.headers.get(guest.GUEST_CSRF_HEADER)
            or request.cookies.get(guest.GUEST_CSRF_COOKIE),
            lock=False,
        )
        return service.request_progress(session, request_id, guest_session_id=g.id)


def _guest_id(session: Any, request: Request) -> uuid.UUID:
    with session.begin():
        return guest._require(
            session,
            request.cookies.get(guest.GUEST_COOKIE),
            request.headers.get(guest.GUEST_CSRF_HEADER)
            or request.cookies.get(guest.GUEST_CSRF_COOKIE),
            lock=False,
        ).id


@router.get("/guest/requests/{request_id}/events")
def guest_request_events(
    request_id: uuid.UUID, request: Request, session: DbSession, after: int = 0
) -> StreamingResponse:
    """A guest's live study, as server-sent events (this browser's requests only)."""
    return _stream_response(request, request_id, None, _guest_id(session, request), after)


@router.get("/guest/requests/{request_id}/study")
def guest_request_study(
    request_id: uuid.UUID, request: Request, session: DbSession
) -> dict[str, Any]:
    gid = _guest_id(session, request)
    with session.begin():
        return service.study_events(session, request_id, guest_session_id=gid)


@router.post("/guest/requests/{request_id}/cancel", status_code=202)
def guest_cancel_request(
    request_id: uuid.UUID, request: Request, session: DbSession
) -> dict[str, Any]:
    """A guest stops a running question: it is not counted against the allowance."""
    with session.begin():
        g = guest._require(
            session,
            request.cookies.get(guest.GUEST_COOKIE),
            request.headers.get(guest.GUEST_CSRF_HEADER),
            lock=False,
        )
        return service.cancel_request(session, request_id, guest_session_id=g.id)


@router.post("/guest/messages", status_code=201)
def guest_ask(
    body: GuestMessageIn, request: Request, session: DbSession, principal: CurrentPrincipal
) -> dict[str, Any]:
    if principal.is_authenticated:
        raise ApiError(
            409, "use_account_conversations", "You are signed in; ask from your account."
        )
    return guest.ask(
        session,
        request.cookies.get(guest.GUEST_COOKIE),
        request.headers.get(guest.GUEST_CSRF_HEADER),
        _client(request),
        content=body.content,
        language=body.language,
        request_id=body.request_id,
        conversation_id=body.conversation_id,
        data_mode=body.data_mode,
        web=body.web_research,
        answer_mode=body.mode,
        persona=body.persona,
        cross_check=body.cross_check,
    )


# ------------------------------------------------------------------ voice (server speech)

AUDIO_LIMIT_BYTES = 16000 * 2 * 61 + 4096  # 61 s of 16 kHz mono 16-bit PCM plus headers


def _voice_caller(request: Request, session: DbSession, principal: Principal) -> Principal | None:
    """A signed-in user with assistant.use (returned), or a guest whose cookie and CSRF
    token check out (None). Guests who have used their allowance are sent to sign in."""
    if principal.is_authenticated:
        return require(Permission.ASSISTANT_USE)(request, principal)
    with session.begin():
        g = guest._require(
            session,
            request.cookies.get(guest.GUEST_COOKIE),
            request.headers.get(guest.GUEST_CSRF_HEADER),
            lock=False,
        )
        if service.answering_available() and guest.allowance(g)["authentication_required"]:
            raise guest.exhausted(g)
    return None


def _voice_limit(request: Request) -> None:
    ratelimit.check(
        f"speech:{guest._client_hash(_client(request))}",
        get_settings().speech_per_client_hour,
        3600,
    )


def _speech_failure(exc: speech.SpeechError) -> ApiError:
    code = str(exc)
    if code == "not_configured":
        return ApiError(503, "speech_not_configured", "Voice is not configured on this server.")
    if code in ("invalid_audio", "too_long", "empty_text"):
        return ApiError(
            422, f"speech_{code}", "The recording could not be used. Try again (up to one minute)."
        )
    if code == "no_speech":
        return ApiError(
            422, "speech_no_speech", "No speech was recognised. Try again closer to the microphone."
        )
    return ApiError(
        502,
        "speech_unavailable",
        "The speech service is not available right now. Type your question instead.",
    )


def _personas(session: DbSession) -> list[profile.Persona]:
    with session.begin():
        current = profile.active(session)
        return profile.personas(current.profile) if current else []


@router.get("/voice")
def voice_status(session: DbSession) -> dict[str, Any]:
    """Public: whether server speech is configured, each persona's configured voice per
    language, and the limits (no secrets)."""
    return speech.status(
        [
            {
                "code": p.code,
                "default": p.default,
                "gender": p.gender,
                "voices": dict(p.voices.azure),
            }
            for p in _personas(session)
        ]
    )


@router.post("/voice/transcribe")
def voice_transcribe(
    request: Request,
    session: DbSession,
    principal: CurrentPrincipal,
    audio: Annotated[bytes, Body(media_type="audio/wav")],
    language: Literal["en", "ar"] = "en",
) -> dict[str, Any]:
    """Speech to text for one question (WAV PCM 16 kHz mono). The audio is not stored;
    the text is returned for the user to review before anything is asked."""
    _voice_caller(request, session, principal)
    _voice_limit(request)
    if len(audio) > AUDIO_LIMIT_BYTES:
        raise ApiError(413, "speech_too_long", "Recordings can be up to one minute long.")
    try:
        text = speech.transcribe(audio, language)
    except speech.SpeechError as exc:
        raise _speech_failure(exc) from exc
    finally:
        del audio  # nothing is kept
    return {"text": text, "language": language, "stored_audio": False}


class SpeakIn(BaseModel):
    message_id: int
    language: Literal["en", "ar"] = "en"
    # One narration segment of the reply's live study (N1, N2, ...), so playback can follow
    # the explanation segment by segment; without it the whole reply is read.
    segment_id: str | None = Field(default=None, pattern=r"^N\d{1,3}$")


@router.post("/voice/speak")
def voice_speak(
    body: SpeakIn, request: Request, session: DbSession, principal: CurrentPrincipal
) -> Response:
    """Text to speech of an assistant reply the caller owns (not arbitrary text)."""
    user = _voice_caller(request, session, principal)
    _voice_limit(request)
    with session.begin():
        message = session.get(AssistantMessage, body.message_id)
        conv = session.get(AssistantConversation, message.conversation_id) if message else None
        owned = conv is not None and (
            (user is not None and conv.user_id == user.user_id)
            or (
                user is None
                and conv.guest_session_id is not None
                and (found := guest._find(session, request.cookies.get(guest.GUEST_COOKIE)))
                is not None
                and found.id == conv.guest_session_id
            )
        )
        if not owned or message is None or message.role != "assistant":
            raise ApiError(404, "not_found", "Message not found.")
        content = message.content
        if body.segment_id is not None:
            content = service.narration_segment(session, message.id, body.segment_id)
        # Read in the voice of the persona that gave the reply (replies from before
        # personas existed were the default persona's).
        current = profile.active(session)
        voice = None
        if current is not None:
            codes = {p.code for p in profile.personas(current.profile)}
            who = profile.persona(
                current.profile, message.persona if message.persona in codes else None
            )
            voice = who.voices.azure[body.language]
    try:
        audio, media_type = speech.synthesize(content, body.language, voice)
    except speech.SpeechError as exc:
        raise _speech_failure(exc) from exc
    return Response(
        audio, media_type=media_type, headers={"Cache-Control": "no-store", "X-Voice": voice or ""}
    )


@router.get("/voice/realtime")
def voice_realtime_status(session: DbSession) -> dict[str, Any]:
    """Public: whether real-time voice (LiveKit) is ready, and which settings are missing
    (names only). Without it, Talk uses push-to-talk with a still portrait."""
    return voice_realtime.readiness(_personas(session))


class RealtimeIn(BaseModel):
    language: Literal["en", "ar"] = "en"
    persona: str | None = Field(default=None, pattern=PERSONA_CODE)


def _voice_identity(
    request: Request, session: DbSession, user: Principal | None
) -> tuple[str, str]:
    if user is not None:
        return f"user:{user.user_id}", "OSRIP user"
    with session.begin():
        g = guest._find(session, request.cookies.get(guest.GUEST_COOKIE))
        if g is None:
            raise ApiError(403, "guest_session_required", "Reload the page to continue.")
        return f"guest:{g.id}", "OSRIP guest"


@router.post("/voice/realtime/session")
def voice_realtime_session(
    body: RealtimeIn, request: Request, session: DbSession, principal: CurrentPrincipal
) -> dict[str, Any]:
    """A short-lived token for one new LiveKit room. The participant identity is set here
    (account or guest session), so the agent charges answers to the right allowance; guests
    who have used their five answers are asked to sign in first. The chosen persona decides
    the agent's voice and avatar for the call."""
    user = _voice_caller(request, session, principal)
    _voice_limit(request)
    identity, name = _voice_identity(request, session, user)
    with session.begin():
        code = service.resolve_persona(
            session, body.persona, user_id=user.user_id if user is not None else None
        )
        current = profile.active(session)
        if current is None:
            raise ApiError(503, "assistant_profile_missing", "No assistant profile is active.")
        who = profile.persona(current.profile, code)
    return voice_realtime.issue_session(
        identity=identity, display_name=name, language=body.language, persona=who
    )


class RealtimeEndIn(BaseModel):
    room: str = Field(pattern=r"^osrip-[0-9a-f]{16}$")
    end_key: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/voice/realtime/end")
def voice_realtime_end(
    body: RealtimeEndIn, request: Request, session: DbSession, principal: CurrentPrincipal
) -> dict[str, Any]:
    """End call: the caller's room is deleted on the media server, which disconnects the
    agent and any avatar worker immediately, so no paid session keeps running."""
    user = principal if principal.is_authenticated else None
    identity, _ = _voice_identity(request, session, user)
    return voice_realtime.end_session(room=body.room, end_key=body.end_key, identity=identity)


@router.post("/guest/link")
def guest_link(
    request: Request,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> dict[str, Any]:
    """Explicitly moves this browser's guest conversations into the signed-in account."""
    return guest.link(session, principal, request.cookies.get(guest.GUEST_COOKIE))
