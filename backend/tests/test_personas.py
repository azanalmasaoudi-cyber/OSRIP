"""Two selectable assistant personas, Al Mulhim (male) and Ilham (female), in profile
version 3. Each has its own name, introduction, portrait and configured voices (real Azure
voice ids of the matching gender, never a renamed label); knowledge, tools, permissions,
sources, conversation history, factual results and the guest allowance are shared. Persona
configuration is a stored profile, not model training."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.services.assistant import profile
from tests.workflow_helpers import API

ROOT = Path(__file__).resolve().parents[2]
V3 = profile.load_file(profile.profile_file(3))
SALAM_REPLY = "وعليكم السلام ورحمة الله وبركاته"
NO_SERVICES = {"answers": False, "web_research": False, "voice": False, "realtime_voice": False}


def _v3_data() -> dict[str, Any]:
    return json.loads(profile.profile_file(3).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the stored profile


def test_version_3_has_the_two_personas_with_matching_real_voices() -> None:
    mulhim, ilham = profile.persona(V3, "mulhim"), profile.persona(V3, "ilham")
    assert profile.persona(V3, None).code == "mulhim", "Al Mulhim stays the default"
    assert (mulhim.gender, mulhim.name.ar, mulhim.name.en) == ("male", "المُلْهِم", "Al Mulhim")
    assert (ilham.gender, ilham.name.ar, ilham.name.en) == ("female", "إلهام", "Ilham")
    assert dict(mulhim.voices.azure) == {"ar": "ar-OM-AbdullahNeural", "en": "en-GB-RyanNeural"}
    assert dict(ilham.voices.azure) == {"ar": "ar-OM-AyshaNeural", "en": "en-GB-SoniaNeural"}
    for who in (mulhim, ilham):
        for language, voice in who.voices.azure.items():
            locale, gender = profile.AZURE_VOICES[voice]
            assert gender == who.gender and locale.startswith(language)
        # Real-time voices and live avatars are chosen only after live tests: none yet.
        assert set(who.voices.realtime.values()) == {None} and who.avatar.live_avatar_id is None


def test_portraits_exist_and_are_recorded_with_their_source() -> None:
    sources = json.loads(
        (ROOT / "frontend/assets/editorial/sources.json").read_text(encoding="utf-8")
    )
    recorded = {d["file"] for a in sources["assets"] for d in a.get("derivatives", [])}
    for who in profile.personas(V3):
        for path in (who.avatar.portrait, who.avatar.figure):
            assert path and (ROOT / "frontend/public" / path.lstrip("/")).is_file()
            assert f"frontend/public{path}" in recorded
        assert "Not a real person" in who.avatar.alt.en
    masters = {a["id"]: a for a in sources["assets"]}
    for asset in ("persona-mulhim", "persona-ilham"):
        entry = masters[asset]
        data = (ROOT / "frontend/assets/editorial/masters" / entry["master"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def _voice(index: int, **voice: str) -> Any:
    return lambda d: d["personas"][index]["voices"]["azure"].update(**voice)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_voice(1, ar="ar-OM-AbdullahNeural"), "male voice"),  # Ilham given a man's voice
        (_voice(0, en="en-GB-SoniaNeural"), "female voice"),  # Al Mulhim given a woman's
        (_voice(1, ar="ar-OM-InventedNeural"), "not a documented"),
        (_voice(1, ar="en-GB-SoniaNeural"), "not a ar voice"),
        (lambda d: d["personas"][1].update(default=True), "exactly one persona"),
        (lambda d: d["personas"][1].update(code="mulhim"), "unique codes"),
        (lambda d: d["personas"][0]["introduction"].update(en="Someone."), "repeat the profile"),
    ],
)
def test_invalid_personas_are_refused(change: Any, message: str) -> None:
    data = _v3_data()
    change(data)
    with pytest.raises(ValidationError, match=message):
        profile.AssistantProfile.model_validate(data)


def test_earlier_versions_keep_their_checksums_and_have_one_persona() -> None:
    v2 = profile.load_file(profile.profile_file(2))
    assert "personas" not in profile.document(v2)
    (only,) = profile.personas(v2)
    assert only.code == "mulhim" and only.introduction == v2.introduction
    assert profile.persona(V3, "mulhim").introduction == v2.introduction


# ------------------------------------------------------------------ replies and the prompt


def test_greetings_and_identity_answers_use_the_chosen_persona() -> None:
    ilham = profile.persona(V3, "ilham")
    first = profile.reply(V3, "salam", "ar", first_turn=True, availability=NO_SERVICES, who=ilham)
    assert first.startswith(SALAM_REPLY) and "أنا إلهام، مساعدة OSRIP" in first
    assert "المُلْهِم" not in first
    who = profile.reply(V3, "identity", "en", first_turn=False, availability=NO_SERVICES, who=ilham)
    assert "I am Ilham" in who and "“inspiration”" in who and "not a person" in who
    mulhim = profile.reply(V3, "salam", "ar", first_turn=True, availability=NO_SERVICES)
    assert "أنا المُلْهِم، مساعد OSRIP" in mulhim
    # The purpose and the three domains are the same whoever answers.
    about = {
        code: profile.reply(
            V3, "about", "en", first_turn=False, availability=NO_SERVICES,
            who=profile.persona(V3, code),
        )
        for code in ("mulhim", "ilham")
    }  # fmt: skip
    assert about["mulhim"] == about["ilham"]
    assert (
        "OSRIP covers three main domains:\n- Energy and Essential Services (Electricity, Water)"
        in about["ilham"]
    )
    assert "- Food Security\n- Trade" in about["ilham"]
    assert profile.classify("ما معنى إلهام؟") == "identity"
    assert profile.classify("What does Ilham mean?") == "identity"


def test_the_prompt_differs_only_in_who_is_speaking() -> None:
    mulhim = profile.prompt_block(V3, 3, profile.persona(V3, "mulhim"))
    ilham = profile.prompt_block(V3, 3, profile.persona(V3, "ilham"))
    assert mulhim.startswith("You are Al Mulhim (المُلْهِم)") and "masculine" in mulhim
    assert ilham.startswith("You are Ilham (إلهام)") and "feminine" in ilham
    assert "never change your name" in ilham
    shared = " OSRIP: "
    assert mulhim[mulhim.index(shared) :] == ilham[ilham.index(shared) :]
    assert "Energy and Essential Services (Electricity, Water); Food Security; Trade" in ilham


# ------------------------------------------------------------------ voices


def test_speech_requests_name_the_persona_voice(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings
    from app.services import speech

    sent: list[bytes] = []

    class Client:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, **kwargs: Any):  # noqa: ANN201
            sent.append(kwargs["content"])
            import httpx

            return httpx.Response(200, content=b"ID3", request=httpx.Request("POST", url))

    s = get_settings()
    monkeypatch.setattr(s, "speech_provider", "azure")
    monkeypatch.setattr(s, "speech_key", SecretStr("test-only-not-a-key"))
    monkeypatch.setattr(s, "speech_region", "testregion")
    monkeypatch.setattr(speech, "http_client_factory", lambda timeout: Client())
    for language, code in (("ar", "ilham"), ("en", "ilham"), ("ar", "mulhim")):
        voice = profile.persona(V3, code).voices.azure[language]
        audio, media = speech.synthesize("مسقط وصلالة & <Nizwa>", language, voice)
        assert (audio, media) == (b"ID3", "audio/mpeg")
        body = sent[-1].decode("utf-8")
        assert f"name='{voice}'" in body
        assert f"xml:lang='{'ar-OM' if language == 'ar' else 'en-GB'}'" in body
        assert "&amp; &lt;Nizwa&gt;" in body, "reply text is escaped, never markup"


def test_voice_status_lists_each_persona_voice() -> None:
    from app.services import speech

    status = speech.status(
        [
            {
                "code": p.code,
                "default": p.default,
                "gender": p.gender,
                "voices": dict(p.voices.azure),
            }
            for p in profile.personas(V3)
        ]
    )
    assert status["languages"]["ar"]["voice"] == "ar-OM-AbdullahNeural"
    assert {p["code"]: p["voices"]["ar"] for p in status["personas"]} == {
        "mulhim": "ar-OM-AbdullahNeural",
        "ilham": "ar-OM-AyshaNeural",
    }


def test_the_live_voice_check_covers_omani_places_and_refuses_without_a_service(
    capsys,  # noqa: ANN001
) -> None:
    from scripts import voice_acceptance as check

    places = ["مسقط", "نزوى", "صحار", "صلالة", "الدقم", "ظفار", "مسندم"]
    arabic = " ".join(s for s, _ in check.TEST_SET["ar"])
    english = " ".join(s for s, _ in check.TEST_SET["en"]).lower()
    assert all(p in arabic for p in places)
    assert all(p in english for p in ("muscat", "nizwa", "sohar", "salalah", "duqm", "dhofar"))
    assert check.recognised(["مسقط", "صلالة"], "مَسقط وصلاله") == {"مسقط": True, "صلالة": True}
    assert check.recognised(["duqm"], "the port of doc") == {"duqm": False}
    # The tests run with speech set to the scripted provider: the check refuses to call that
    # a live verification and sends nothing.
    assert check.main(["--out", "unused"]) == 2
    assert "live voice verification remains pending" in capsys.readouterr().out


# ------------------------------------------------------------------ real-time calls


def _livekit(monkeypatch) -> list[str]:  # noqa: ANN001
    from app.core.config import get_settings
    from app.services import voice_realtime

    s = get_settings()
    for name, value in (
        ("voice_realtime_enabled", True),
        ("livekit_url", "wss://example.invalid"),
        ("livekit_api_key", "test-key"),
        ("livekit_api_secret", SecretStr("test-secret-" + "y" * 32)),
        ("voice_stt_model", "test/stt"),
    ):
        monkeypatch.setattr(s, name, value)
    deleted: list[str] = []
    monkeypatch.setattr(voice_realtime, "room_deleter", deleted.append)
    return deleted


def test_end_call_deletes_only_the_callers_room(monkeypatch) -> None:  # noqa: ANN001
    from app.core.errors import ApiError
    from app.services import voice_realtime

    deleted = _livekit(monkeypatch)
    room, me = "osrip-0123456789abcdef", f"guest:{uuid.uuid4()}"
    key = voice_realtime._end_key(room, me)
    assert voice_realtime.end_session(room=room, end_key=key, identity=me)["ended"] is True
    assert deleted == [room]
    for identity, end_key in ((f"guest:{uuid.uuid4()}", key), (me, "0" * 64)):
        with pytest.raises(ApiError) as refused:
            voice_realtime.end_session(room=room, end_key=end_key, identity=identity)
        assert refused.value.status_code == 404
    assert deleted == [room], "nobody else can end the call"


def test_the_call_persona_comes_only_from_the_signed_metadata() -> None:
    from app.voice import bridge

    assert bridge.parse_persona(json.dumps({"language": "ar", "persona": "ilham"})) == "ilham"
    for bad in ("{}", "not json", json.dumps({"persona": "Ilham; drop"}), json.dumps(["ilham"])):
        assert bridge.parse_persona(bad) is None


def test_the_agent_starts_only_documented_avatar_plugins() -> None:
    from app.voice import agent

    with pytest.raises(ValueError, match="not supported"):
        agent.avatar_session("unknown", "face-1", "Ilham")


# ------------------------------------------------------------------ through the API


@pytest.fixture(autouse=True)
def _providers(request, monkeypatch):  # noqa: ANN001, ANN202
    from app.core import ratelimit
    from app.core.config import get_settings

    if "integration" in request.keywords:
        from app.db.session import session_factory
        from app.services.fixtures import seed_booklet_fixtures

        request.getfixturevalue("database_url")
        with session_factory()() as session:
            seed_booklet_fixtures(session)
    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "research_provider", "")
    monkeypatch.setattr(s, "speech_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "assistant_max_per_minute", 1000)
    ratelimit.reset()


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _ask(client, content: str, language: str, persona: str | None, conversation_id=None):  # noqa: ANN001, ANN202
    return client.post(
        f"{API}/assistant/guest/messages",
        json={
            "content": content,
            "language": language,
            "request_id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "data_mode": "synthetic",
            **({"persona": persona} if persona else {}),
        },
    )


@pytest.mark.integration
def test_profile_and_voice_status_publish_both_personas(app) -> None:  # noqa: ANN001
    client = _guest(app)
    body = client.get(f"{API}/assistant/profile").json()
    assert body["version"] == 3
    personas = {p["code"]: p for p in body["personas"]}
    assert personas["ilham"]["avatar"]["portrait"] == "/images/assistant/ilham-portrait-432.jpg"
    assert personas["ilham"]["voices"]["azure"]["en"] == "en-GB-SoniaNeural"
    voice = client.get(f"{API}/assistant/voice").json()
    assert {p["code"]: p["gender"] for p in voice["personas"]} == {
        "mulhim": "male",
        "ilham": "female",
    }


@pytest.mark.integration
def test_switching_persona_keeps_the_conversation_allowance_and_facts(app, monkeypatch) -> None:  # noqa: ANN001
    from app.services.assistant.provider import FakeProvider

    systems: list[str] = []
    original = FakeProvider.complete

    def recording(self, system, messages, tools):  # noqa: ANN001, ANN202
        systems.append(system)
        return original(self, system, messages, tools)

    monkeypatch.setattr(FakeProvider, "complete", recording)
    client = _guest(app)
    hello = _ask(client, "السلام عليكم", "ar", "ilham").json()
    conv = hello["conversation_id"]
    assert hello["message"]["persona"] == "ilham" and "أنا إلهام" in hello["message"]["content"]
    assert hello["message"]["content"].startswith(SALAM_REPLY)
    assert hello["allowance"]["used"] == 0, "greetings are never charged"

    question = "What is the latest electricity generation?"
    as_ilham = _ask(client, question, "en", "ilham", conv).json()
    as_mulhim = _ask(client, question, "en", "mulhim", conv).json()
    assert as_ilham["conversation_id"] == as_mulhim["conversation_id"] == conv
    assert (as_ilham["allowance"]["used"], as_mulhim["allowance"]["used"]) == (1, 2)
    a, b = as_ilham["message"], as_mulhim["message"]
    assert (a["persona"], b["persona"]) == ("ilham", "mulhim")
    for key in ("status", "content", "evidence", "calculations", "citations"):
        assert a[key] == b[key], f"{key} must not depend on the persona"
    # Only the identity block of the system prompt changed.
    ilham_prompt, mulhim_prompt = systems[0], systems[-1]
    assert ilham_prompt.startswith("You are Ilham") and mulhim_prompt.startswith(
        "You are Al Mulhim"
    )
    rules = "Rules you must follow:"
    assert ilham_prompt[ilham_prompt.index(rules) :] == mulhim_prompt[mulhim_prompt.index(rules) :]

    history = client.get(f"{API}/assistant/guest/conversations/{conv}").json()["messages"]
    assert [m["persona"] for m in history if m["role"] == "assistant"] == [
        "ilham",
        "ilham",
        "mulhim",
    ]
    refused = _ask(client, "hello", "en", "someone", conv)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "unknown_persona"
    bad = _ask(client, "hello", "en", "Ilham!", conv)
    assert bad.status_code == 422


@pytest.mark.integration
def test_read_aloud_uses_the_voice_of_the_persona_that_replied(app) -> None:  # noqa: ANN001
    client = _guest(app)
    conv = None
    voices = {}
    for code in ("ilham", "mulhim"):
        body = _ask(client, "hello", "en", code, conv).json()
        conv = body["conversation_id"]
        for language in ("ar", "en"):
            spoken = client.post(
                f"{API}/assistant/voice/speak",
                json={"message_id": body["message"]["id"], "language": language},
            )
            assert spoken.status_code == 200, spoken.text
            voices[(code, language)] = spoken.headers["X-Voice"]
    assert voices == {
        ("ilham", "ar"): "ar-OM-AyshaNeural",
        ("ilham", "en"): "en-GB-SoniaNeural",
        ("mulhim", "ar"): "ar-OM-AbdullahNeural",
        ("mulhim", "en"): "en-GB-RyanNeural",
    }


@pytest.mark.integration
def test_a_signed_in_choice_is_saved_on_the_account(app, make_user, login) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    from app.domain.enums import Role
    from app.main import create_app

    person = make_user(Role.VIEWER)
    user = login(person)
    assert user.get(f"{API}/assistant/persona").json() == {"persona": None, "stored": "account"}
    saved = user.put(f"{API}/assistant/persona", json={"persona": "ilham"})
    assert saved.status_code == 200 and saved.json()["persona"] == "ilham"
    assert user.put(f"{API}/assistant/persona", json={"persona": "nobody"}).status_code == 422
    conv = user.post(
        f"{API}/assistant/conversations", json={"language": "ar", "data_mode": "synthetic"}
    ).json()["id"]
    reply = user.post(
        f"{API}/assistant/conversations/{conv}/messages",
        json={"content": "من أنتِ؟", "language": "ar"},
    ).json()
    assert reply["persona"] == "ilham" and "أنا إلهام" in reply["content"], "the saved choice"
    # Another session (a restart, another device) gets the same choice.
    again = TestClient(create_app())
    again.cookies.update(user.cookies)
    assert again.get(f"{API}/assistant/persona").json()["persona"] == "ilham"
    # Visitors keep the choice in their browser only.
    assert _guest(app).get(f"{API}/assistant/persona").json() == {
        "persona": None,
        "stored": "browser",
    }
    anonymous = TestClient(app)
    assert anonymous.put(f"{API}/assistant/persona", json={"persona": "ilham"}).status_code in (
        401,
        403,
    )


@pytest.mark.integration
def test_end_call_route_checks_the_room_belongs_to_the_caller(app, monkeypatch) -> None:  # noqa: ANN001
    deleted = _livekit(monkeypatch)
    from tests.test_mulhim_identity import _realtime_voices

    _realtime_voices(monkeypatch)
    client = _guest(app)
    issued = client.post(
        f"{API}/assistant/voice/realtime/session", json={"language": "en", "persona": "mulhim"}
    ).json()
    other = _guest(app)
    stolen = other.post(
        f"{API}/assistant/voice/realtime/end",
        json={"room": issued["room"], "end_key": issued["end_key"]},
    )
    assert stolen.status_code == 404 and deleted == []
    ended = client.post(
        f"{API}/assistant/voice/realtime/end",
        json={"room": issued["room"], "end_key": issued["end_key"]},
    )
    assert ended.status_code == 200 and ended.json()["ended"] is True
    assert deleted == [issued["room"]]
