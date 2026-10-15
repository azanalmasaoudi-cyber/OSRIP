"""The voice bridge: who is calling (only from the signed token), what is spoken (no citation
markers, a pointer to the on-screen sources), spoken refusals, and answers that go through
the same service and guest allowance as typed questions. The LiveKit worker's answer step is
exercised with a scripted chat context; no media server is involved."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.core.errors import ApiError
from app.domain.enums import DataMode, Permission, Role
from app.voice import bridge

# ------------------------------------------------------------------ identity and language


def test_only_signed_user_or_guest_identities_are_accepted() -> None:
    uid = uuid.uuid4()
    assert bridge.parse_identity(f"user:{uid}") == bridge.Caller("user", uid)
    assert bridge.parse_identity(f"guest:{uid}") == bridge.Caller("guest", uid)
    for bad in ("admin:1", f"agent:{uid}", "user:not-a-uuid", "", f"guest{uid}"):
        with pytest.raises(ValueError):
            bridge.parse_identity(bad)


def test_language_comes_from_the_token_metadata() -> None:
    assert bridge.parse_language('{"language": "ar"}') == "ar"
    assert bridge.parse_language('{"language": "fr"}') == "en"
    assert bridge.parse_language("not json") == "en"
    assert bridge.parse_language(None) == "en"


# ------------------------------------------------------------------ what is spoken


def test_speech_drops_citation_markers_and_points_to_the_screen() -> None:
    text = "Generation was **50,100 GWh** in 2002 [E1]. It rose 4.375% [E1, E2]."
    assert bridge.spoken(text, "en", cited=True) == (
        "Generation was 50,100 GWh in 2002. It rose 4.375%. The sources are shown on screen."
    )
    arabic = bridge.spoken("بلغ التوليد 50100 جيجاواط ساعة [E1].", "ar", cited=True)
    assert "[E1]" not in arabic and arabic.endswith("المصادر معروضة على الشاشة.")
    assert bridge.spoken("Hello.", "en", cited=False) == "Hello."


def test_refusals_are_spoken_in_the_callers_language() -> None:
    assert "free answers" in bridge.refusal("guest_allowance_exhausted", "en")
    assert "الإجابات المجانية" in bridge.refusal("guest_allowance_exhausted", "ar")
    assert bridge.refusal("something_else", "ar") == bridge.UNAVAILABLE["ar"]


# ------------------------------------------------------------------ the worker's answer step


def _agent_module():  # noqa: ANN202
    return pytest.importorskip("app.voice.agent")


def _chat(*turns: tuple[str, str]):  # noqa: ANN202
    from livekit.agents import llm

    ctx = llm.ChatContext.empty()
    for role, text in turns:
        ctx.add_message(role=role, content=text)
    return ctx


def test_the_worker_answers_the_latest_question_through_the_bridge(monkeypatch) -> None:  # noqa: ANN001
    agent = _agent_module()
    call = bridge.Call(bridge.Caller("guest", uuid.uuid4()), "en")
    asked: list[str] = []

    def fake_answer(c: bridge.Call, question: str) -> dict:
        asked.append(question)
        return {"content": "Generation was 50,100 GWh in 2002 [E1].", "citations": ["E1"]}

    monkeypatch.setattr(bridge, "answer", fake_answer)
    voice = agent.AssistantVoice(call)
    ctx = _chat(("assistant", "Hello."), ("user", "What was generation?"), ("user", "In 2002?"))
    spoken = asyncio.run(voice.llm_node(ctx, [], None))
    assert asked == ["In 2002?"]  # the latest finished utterance only
    assert spoken == "Generation was 50,100 GWh in 2002. The sources are shown on screen."


def test_a_refused_or_failed_answer_is_spoken_not_raised(monkeypatch) -> None:  # noqa: ANN001
    agent = _agent_module()
    call = bridge.Call(bridge.Caller("guest", uuid.uuid4()), "ar")

    def exhausted(*_a: object) -> dict:
        raise ApiError(403, "guest_allowance_exhausted", "used")

    monkeypatch.setattr(bridge, "answer", exhausted)
    voice = agent.AssistantVoice(call)
    said = asyncio.run(voice.llm_node(_chat(("user", "سؤال")), [], None))
    assert said == bridge.refusal("guest_allowance_exhausted", "ar")

    def broken(*_a: object) -> dict:
        raise RuntimeError("provider down")

    monkeypatch.setattr(bridge, "answer", broken)
    assert asyncio.run(voice.llm_node(_chat(("user", "q")), [], None)) == bridge.UNAVAILABLE["ar"]
    # Nothing to answer: silence, not an invented reply.
    assert asyncio.run(voice.llm_node(_chat(("assistant", "Hi")), [], None)) == ""


# ------------------------------------------------------------------ the same service and allowance


@pytest.fixture
def fake_assistant(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "assistant_max_per_minute", 1000)
    monkeypatch.setattr(s, "assistant_max_per_hour", 1000)
    ratelimit.reset()


def _guest_id(app) -> uuid.UUID:  # noqa: ANN001
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.core import security
    from app.db.session import session_factory
    from app.models import GuestSession

    client = TestClient(app)
    client.get("/api/v1/assistant/guest")
    digest = security.token_digest(client.cookies["osrip_guest"])
    with session_factory()() as s:
        return s.scalar(select(GuestSession.id).where(GuestSession.token_hash == digest))


@pytest.mark.integration
def test_voice_answers_use_the_guest_allowance_and_greetings_are_free(app, fake_assistant) -> None:  # noqa: ANN001
    call = bridge.Call(bridge.Caller("guest", _guest_id(app)), "ar", data_mode=DataMode.SYNTHETIC)
    greeting = bridge.answer(call, "السلام عليكم")
    assert greeting["status"] == "profile"  # the approved reply, not charged
    conversation = call.conversation_id
    for _ in range(5):
        msg = bridge.answer(call, "What was the growth of electricity generation?")
        assert msg["status"] in ("answered", "no_evidence")
    assert call.conversation_id == conversation  # one conversation for the whole call
    with pytest.raises(ApiError) as refused:
        bridge.answer(call, "What was the growth of electricity generation?")
    assert refused.value.code == "guest_allowance_exhausted"
    # Greetings still work after the allowance is used, as for typed questions.
    assert bridge.answer(call, "السلام عليكم")["status"] == "profile"


@pytest.mark.integration
def test_voice_needs_the_assistant_permission_and_keeps_one_conversation(
    make_user, fake_assistant
) -> None:  # noqa: ANN001
    without = make_user()
    call = bridge.Call(bridge.Caller("user", without.id), "en", data_mode=DataMode.SYNTHETIC)
    with pytest.raises(ApiError) as denied:
        bridge.answer(call, "What was the growth of electricity generation?")
    assert denied.value.code == "permission_denied"

    allowed = make_user(Role.VIEWER, grants=(Permission.ASSISTANT_USE,))
    call = bridge.Call(bridge.Caller("user", allowed.id), "en", data_mode=DataMode.SYNTHETIC)
    first = bridge.answer(call, "What was the growth of electricity generation?")
    second = bridge.answer(call, "Hello")
    assert first["role"] == "assistant" and second["status"] == "profile"
    assert call.conversation_id is not None and len(call.answers) == 2

    with pytest.raises(ApiError) as unknown:
        bridge.answer(bridge.Call(bridge.Caller("user", uuid.uuid4()), "en"), "Hello")
    assert unknown.value.code == "authentication_required"
