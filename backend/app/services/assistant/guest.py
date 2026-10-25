"""Five successful assistant answers for visitors without an account (booklet 3.35).

Identity: a random value in an HttpOnly, SameSite=Strict cookie; only its SHA-256
digest is stored. Nothing else identifies the visitor (no fingerprinting). Clearing
cookies or using another device starts a new guest session; the interface says so.

Accounting, per logical question (the client's request id, an idempotency key):
1. In one transaction, with the guest row locked: abandoned reservations are released,
   a completed request with the same id is replayed without a charge, and otherwise
   one slot is reserved. ``answers_used + answers_reserved <= answer_limit`` is also a
   database constraint, so concurrent requests cannot exceed the limit.
2. The provider runs outside any transaction.
3. In one transaction the reply is stored and the reservation settles: a completed,
   contract-valid reply is charged; a failure, a withheld reply or a timeout releases
   the slot. The reply and the charge commit together, so a stored reply is never
   released and a released slot never has a stored reply.
When the allowance is used up the request is refused before any provider call, with a
machine-readable ``authentication_required`` state. Without a configured provider the
labelled non-AI lookup answers and nothing is reserved or charged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core import ratelimit, security
from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.domain.enums import DataMode
from app.models import AssistantConversation, AssistantMessage, AssistantRequest, GuestSession
from app.services import accounts
from app.services.assistant import service
from app.services.assistant.provider import answering_available
from app.services.principal import Principal

GUEST_COOKIE = "osrip_guest"
GUEST_CSRF_COOKIE = "osrip_guest_csrf"
GUEST_CSRF_HEADER = "X-Guest-CSRF"

NOTICE = {
    "en": "Guest answers are counted for this browser with a cookie. Clearing cookies, a "
    "private window or another device cannot be recognised as the same visitor, so the "
    "count is a fair-use measure, not a guarantee. Public statistics pages need no account.",
    "ar": "تُحسب إجابات الزائر لهذا المتصفح بواسطة ملف تعريف ارتباط. لا يمكن التعرّف على "
    "الزائر نفسه بعد مسح ملفات تعريف الارتباط أو في نافذة خاصة أو على جهاز آخر، لذا فالعدد "
    "مقياس للاستخدام العادل وليس ضماناً. صفحات الإحصاءات العامة لا تتطلب حساباً.",
}


@dataclass
class Issued:
    guest: GuestSession
    token: str | None = None  # set when a new cookie value must be sent
    csrf: str | None = None  # set when a new CSRF token must be sent


def _client_hash(client: str) -> str:
    return security.keyed_digest(get_settings().client_hash_key.get_secret_value(), client)


def _lifetime() -> timedelta:
    return timedelta(days=get_settings().guest_session_days)


def _find(session: Session, token: str | None, *, lock: bool = False) -> GuestSession | None:
    if not token:
        return None
    stmt = select(GuestSession).where(GuestSession.token_hash == security.token_digest(token))
    if lock:
        stmt = stmt.with_for_update()
    guest = session.scalar(stmt)
    if guest is None or guest.expires_at <= accounts.now():
        return None
    return guest


def ensure(session: Session, token: str | None, csrf: str | None, client: str) -> Issued:
    """The visitor's guest session, created on first use (subject to a per-address limit on
    new sessions). A missing or stale CSRF cookie is replaced; the count never resets."""
    s = get_settings()
    now = accounts.now()
    guest = _find(session, token)
    if guest is not None:
        guest.last_seen_at = now
        guest.expires_at = now + _lifetime()
        issued = Issued(guest)
        if not csrf or not security.digests_equal(security.token_digest(csrf), guest.csrf_hash):
            issued.csrf = security.new_token()
            guest.csrf_hash = security.token_digest(issued.csrf)
        return issued
    client_hash = _client_hash(client)
    ratelimit.check(f"guest-new:{client_hash}", s.guest_sessions_per_client_hour, 3600)
    new_token, new_csrf = security.new_token(), security.new_token()
    guest = GuestSession(
        token_hash=security.token_digest(new_token),
        csrf_hash=security.token_digest(new_csrf),
        policy_version=s.guest_policy_version,
        answer_limit=s.guest_answer_limit,
        answers_used=0,
        answers_reserved=0,
        client_hash=client_hash,
        expires_at=now + _lifetime(),
    )
    session.add(guest)
    session.flush()
    return Issued(guest, new_token, new_csrf)


def allowance(guest: GuestSession) -> dict[str, Any]:
    remaining = max(guest.answer_limit - guest.answers_used - guest.answers_reserved, 0)
    return {
        "limit": guest.answer_limit,
        "used": guest.answers_used,
        "in_progress": guest.answers_reserved,
        "remaining": remaining,
        # Machine-readable: the next question needs sign-in or registration.
        "authentication_required": remaining == 0 and guest.answers_reserved == 0,
        "policy_version": guest.policy_version,
    }


def status(session: Session, guest: GuestSession) -> dict[str, Any]:
    conversations = session.scalars(
        select(AssistantConversation)
        .where(AssistantConversation.guest_session_id == guest.id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(20)
    )
    return {
        "allowance": allowance(guest),
        "notice": NOTICE,
        "linked": guest.linked_user_id is not None,
        "expires_at": guest.expires_at.isoformat(),
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "language": c.language,
                "data_mode": c.data_mode.value,
                "updated_at": c.updated_at.isoformat(),
            }
            for c in conversations
        ],
    }


def _require(session: Session, token: str | None, csrf: str | None, *, lock: bool) -> GuestSession:
    guest = _find(session, token, lock=lock)
    if guest is None:
        raise ApiError(
            401,
            "guest_session_required",
            "Your guest session has expired. Reload the page to continue.",
        )
    if not csrf or not security.digests_equal(security.token_digest(csrf), guest.csrf_hash):
        raise ApiError(
            403, "csrf_failed", "The request could not be verified. Reload the page and try again."
        )
    return guest


def _by_id(session: Session, guest_id: uuid.UUID) -> GuestSession:
    """A guest session named by a server-signed credential (the voice room token), locked.
    Only the voice agent uses this; browsers always prove the cookie and CSRF token."""
    guest = session.scalar(
        select(GuestSession).where(GuestSession.id == guest_id).with_for_update()
    )
    if guest is None or guest.expires_at <= accounts.now():
        raise ApiError(
            401,
            "guest_session_required",
            "Your guest session has expired. Reload the page to continue.",
        )
    return guest


def _conversation(
    session: Session, guest: GuestSession, conversation_id: uuid.UUID
) -> AssistantConversation:
    conv = session.get(AssistantConversation, conversation_id)
    if conv is None or conv.guest_session_id != guest.id:
        raise not_found("conversation")
    return conv


def get_conversation(
    session: Session, token: str | None, csrf: str | None, conversation_id: uuid.UUID
) -> dict[str, Any]:
    guest = _require(session, token, csrf, lock=False)
    conv = _conversation(session, guest, conversation_id)
    messages = session.scalars(
        select(AssistantMessage)
        .where(AssistantMessage.conversation_id == conv.id)
        .order_by(AssistantMessage.id)
    )
    return {
        "id": str(conv.id),
        "title": conv.title,
        "language": conv.language,
        "data_mode": conv.data_mode.value,
        "messages": [service._message_out(m) for m in messages],
        "allowance": allowance(guest),
    }


def delete_conversation(
    session: Session, token: str | None, csrf: str | None, conversation_id: uuid.UUID
) -> None:
    """Delete one of this guest session's conversations and its messages. Usage counters
    and request records stay, so deleting never returns answers."""
    guest = _require(session, token, csrf, lock=False)
    conv = _conversation(session, guest, conversation_id)
    session.execute(delete(AssistantMessage).where(AssistantMessage.conversation_id == conv.id))
    session.delete(conv)


def _release_abandoned(session: Session, guest: GuestSession) -> None:
    """Reservations older than the reservation window belong to requests that never
    finished (a crashed worker). Only reservations without a stored reply are released."""
    stale = session.scalars(
        select(AssistantRequest)
        .where(
            AssistantRequest.guest_session_id == guest.id,
            AssistantRequest.state == "reserved",
            AssistantRequest.reserved_until < accounts.now(),
            AssistantRequest.response_message_id.is_(None),
        )
        .with_for_update()
    ).all()
    for request in stale:
        request.state = "released"
        request.outcome = "abandoned"
        guest.answers_reserved = max(guest.answers_reserved - 1, 0)


def exhausted(guest: GuestSession) -> ApiError:
    return ApiError(
        403,
        "guest_allowance_exhausted",
        f"You have used the {guest.answer_limit} free answers for guests. Sign in or create an "
        "account to keep asking; the statistics pages stay open without an account.",
        {"authentication_required": True, "allowance": allowance(guest)},
    )


def ask(
    session: Session,
    token: str | None,
    csrf: str | None,
    client: str,
    *,
    content: str,
    language: str,
    request_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    data_mode: DataMode,
    web: bool = False,
    answer_mode: str = "ask",
    verified_guest_id: uuid.UUID | None = None,
    persona: str | None = None,
    cross_check: bool = False,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A guest's question. ``verified_guest_id`` is used only by the voice agent, whose
    caller identity comes from a server-signed room token instead of the browser cookie;
    the allowance, reservation and charging below are the same for text and voice, and for
    every persona (switching persona never resets or changes the allowance)."""
    s = get_settings()
    question, language = service.validate_question(content, language)
    digest = service.question_digest(question, language)

    with session.begin():
        guest = (
            _by_id(session, verified_guest_id)
            if verified_guest_id is not None
            else _require(session, token, csrf, lock=True)
        )
        persona = service.resolve_persona(session, persona)
        ratelimit.check(f"guest-ask:{guest.id}", s.guest_asks_per_minute, 60)
        ratelimit.check(
            f"guest-ask-client:{_client_hash(client)}", s.guest_asks_per_client_hour, 3600
        )
        _release_abandoned(session, guest)
        request = session.scalar(
            select(AssistantRequest)
            .where(
                AssistantRequest.guest_session_id == guest.id,
                AssistantRequest.idempotency_key == request_id,
            )
            .with_for_update()
        )
        if request is not None:
            if request.question_digest != digest:
                raise service.idempotency_conflict()
            if request.state == "completed" and request.response_message_id is not None:
                stored = session.get(AssistantMessage, request.response_message_id)
                if stored is not None:  # an interrupted delivery: replay, never charge twice
                    return {
                        "message": {**service._message_out(stored), "replayed": True},
                        "conversation_id": str(request.conversation_id),
                        "allowance": allowance(guest),
                    }
            if request.state == "reserved":
                raise service.request_in_progress()

        if conversation_id is not None:
            conv = _conversation(session, guest, conversation_id)
        elif request is not None and request.conversation_id is not None:
            conv = _conversation(session, guest, request.conversation_id)
        else:
            conv = AssistantConversation(
                guest_session_id=guest.id,
                title=question[:80],
                language=language,
                data_mode=data_mode,
            )
            session.add(conv)
            session.flush()

        approved = service.profile_turn(session, conv, question, language, persona)
        if approved is not None:
            # A greeting or a question about the assistant: the approved reply, never charged
            # (a fixed welcome is not an answer) and no provider call.
            if request is None:
                session.add(
                    AssistantMessage(conversation_id=conv.id, role="user", content=question)
                )
            message = approved.message(conv.id)
            session.add(message)
            conv.updated_at = accounts.now()
            session.flush()
            if request is None:
                request = AssistantRequest(
                    guest_session_id=guest.id,
                    idempotency_key=request_id,
                    question_digest=digest,
                    language=language,
                    state="completed",
                    conversation_id=conv.id,
                    reserved_until=accounts.now(),
                )
                session.add(request)
            request.state, request.charged, request.outcome = "completed", False, "profile"
            request.response_message_id, request.completed_at = message.id, accounts.now()
            session.flush()
            return {
                "message": service._message_out(message),
                "conversation_id": str(conv.id),
                "allowance": allowance(guest),
            }

        charged_path = answering_available()
        if charged_path:
            if guest.answers_used + guest.answers_reserved >= guest.answer_limit:
                raise exhausted(guest)  # refused before any provider request
            # Conditional increment on the locked row; the table constraint backs it up.
            reserved = session.execute(
                update(GuestSession)
                .where(
                    GuestSession.id == guest.id,
                    GuestSession.answers_used + GuestSession.answers_reserved
                    < GuestSession.answer_limit,
                )
                .values(answers_reserved=GuestSession.answers_reserved + 1)
                .returning(GuestSession.answers_reserved)
                .execution_options(synchronize_session=False)
            ).scalar_one_or_none()
            if reserved is None:
                raise exhausted(guest)
            session.refresh(guest)
        until = accounts.now() + service.reservation_window()
        retry = request is not None
        if request is None:
            request = AssistantRequest(
                guest_session_id=guest.id,
                idempotency_key=request_id,
                question_digest=digest,
                language=language,
                state="reserved",
                conversation_id=conv.id,
                reserved_until=until,
            )
            session.add(request)
        else:
            request.state, request.reserved_until = "reserved", until
            request.attempts += 1
        service.start_progress(request)
        history = service._history(session, conv)
        if retry and history and history[-1]["role"] == "user":
            history = history[:-1]  # the question itself is sent below, once
        if not retry:  # a retry of the same failed question does not repeat it in the thread
            session.add(AssistantMessage(conversation_id=conv.id, role="user", content=question))
        conv.updated_at = accounts.now()
        session.flush()
        tables = service.previous_tables(session, conv)
        request_pk, conv_id, conv_data_mode, guest_id, attempt = (
            request.id,
            conv.id,
            conv.data_mode,
            guest.id,
            request.attempts,
        )

    tracker = service.study_tracker(
        request_pk, request_id, conv_id, language, conv_data_mode, answer_mode, attempt
    )
    reply = service.generate_reply(
        question,
        history,
        language,
        conv_data_mode,
        web=web,
        client_key=_client_hash(client),
        mode=answer_mode,
        tracker=tracker,
        persona=persona,
        cross_check=cross_check,
        selection=selection,
        # Guests never submit figures: shared statistics change only through validated saves
        # by signed-in research users or reviewers.
        submitter=None,
        previous_tables=tables,
    )
    service.with_study(reply, tracker, request_id)

    with session.begin():
        guest = session.get(GuestSession, guest_id, with_for_update=True)
        row = session.get(
            AssistantRequest, request_pk, with_for_update=True, populate_existing=True
        )
        assert guest is not None and row is not None
        message = reply.message(conv_id)
        session.add(message)
        session.flush()
        reply.store_studies(session, message.id, guest_session_id=guest_id)
        reply.queue_research(session, message.id, None, language)
        was_reserved = row.state == "reserved"
        if charged_path and was_reserved:
            guest.answers_reserved = max(guest.answers_reserved - 1, 0)
        charge = charged_path and reply.chargeable
        if charge and not was_reserved:
            # The reservation was released as abandoned meanwhile; charge only if a slot is free.
            charge = guest.answers_used + guest.answers_reserved < guest.answer_limit
        if charge:
            guest.answers_used += 1
        service.settle(row, reply, message.id, charged=charge)
        session.flush()
        out = {
            "message": service._message_out(message),
            "conversation_id": str(conv_id),
            "allowance": allowance(guest),
        }
    tracker.finish(reply, out["message"]["id"])  # after the reply is stored
    return out


def link(session: Session, principal: Principal, token: str | None) -> dict[str, Any]:
    """Moves the guest session's conversations to the signed-in account. Requires the
    authenticated session (with its CSRF token) and the guest cookie in the same request,
    which proves control of both; nothing is merged by e-mail address or phone number."""
    with session.begin():
        guest = _find(session, token, lock=True)
        if guest is None:
            raise not_found("guest session")
        if guest.linked_user_id is not None and guest.linked_user_id != principal.user_id:
            raise ApiError(
                409, "guest_session_linked", "This guest history belongs to another account."
            )
        moved = session.execute(
            update(AssistantConversation)
            .where(AssistantConversation.guest_session_id == guest.id)
            .values(user_id=principal.user_id, guest_session_id=None)
            .execution_options(synchronize_session=False)
        ).rowcount
        if guest.linked_user_id is None:
            guest.linked_user_id = principal.user_id
            guest.linked_at = accounts.now()
        return {"linked_conversations": moved or 0}
