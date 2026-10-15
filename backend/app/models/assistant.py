"""Assistant conversations, messages and usage records (migration 0006), guest
sessions and idempotent requests (migration 0010), and the versioned assistant profile
(migration 0013)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import DataMode
from app.models.types import DATA_MODE

NOW = {"server_default": func.now()}


class AssistantConversation(Base):
    __tablename__ = "assistant_conversation"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Exactly one owner: an account or a guest session (migration 0010).
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("guest_session.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class AssistantMessage(Base):
    __tablename__ = "assistant_message"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_conversation.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    calculations: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    citations: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    suggestions: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    model: Mapped[str | None] = mapped_column(Text)
    # ask | analyze | research | compare | scenario (migration 0012); NULL before.
    mode: Mapped[str | None] = mapped_column(Text)
    # Validated recommendation cards, drivers, evidence/hypotheses/assumptions, conflicts.
    structured: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # The persona that gave an assistant reply (migration 0017); NULL for user messages and
    # for replies stored before personas existed (they were Al Mulhim's).
    persona: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class AssistantUsage(Base):
    __tablename__ = "assistant_usage"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    outcome: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class GuestSession(Base):
    """An anonymous visitor's allowance (migration 0010). Identified only by the digest
    of a random HttpOnly cookie value; clearing cookies starts a new session."""

    __tablename__ = "guest_session"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    csrf_hash: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    answer_limit: Mapped[int] = mapped_column(Integer)
    answers_used: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    answers_reserved: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    client_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    linked_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssistantRequest(Base):
    """One logical question, keyed by the client's idempotency key (migration 0010)."""

    __tablename__ = "assistant_request"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("guest_session.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    idempotency_key: Mapped[uuid.UUID]
    question_digest: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)  # reserved | completed | released | cancelled
    charged: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Stages reached while answering, and the time the person stopped it (migration 0016).
    progress: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assistant_conversation.id", ondelete="SET NULL")
    )
    response_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_message.id", ondelete="SET NULL")
    )
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    reserved_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderCall(Base):
    """One call to an external AI or search provider (migration 0018). Outcome and cost only:
    no prompt, question, query or answer is stored."""

    __tablename__ = "provider_call"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    capability: Mapped[str] = mapped_column(Text)  # answer | search | test_answer | test_search
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # ok, or the failure code
    duration_ms: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    searches: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class StudyEvent(Base):
    """One validated step of a live assistant study (migration 0019), streamed to the person
    asking and replayed when they return to the study."""

    __tablename__ = "study_event"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("assistant_request.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assistant_conversation.id", ondelete="CASCADE")
    )
    study_id: Mapped[uuid.UUID]
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(Text)
    result_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class AssistantProfileVersion(Base):
    """One reviewed version of Al Mulhim's identity and project knowledge (migration 0013).
    Content is immutable in the database; only the status moves between active and retired."""

    __tablename__ = "assistant_profile"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(Text)  # active | retired
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_sha256: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
