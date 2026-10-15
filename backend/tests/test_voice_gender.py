"""Al Mulhim speaks with a man's voice: the server's default speech voices are male in both
languages, and the voice-status route reports them. (The browser fallback, which picks only
male voices, is tested in frontend/e2e-api/voice-gender.spec.ts.)"""

from __future__ import annotations

from app.core.config import Settings

# Azure AI Speech neural voices that are male (Microsoft's published voice list).
MALE_AZURE_VOICES = {
    "ar-OM-AbdullahNeural",
    "ar-SA-HamedNeural",
    "en-GB-RyanNeural",
    "en-GB-ThomasNeural",
}


def test_default_speech_voices_are_male() -> None:
    s = Settings(_env_file=None)
    assert s.speech_voice_ar == "ar-OM-AbdullahNeural"
    assert s.speech_voice_en == "en-GB-RyanNeural"
    assert {s.speech_voice_ar, s.speech_voice_en} <= MALE_AZURE_VOICES


def test_voice_status_reports_the_male_voices(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings
    from app.services import speech

    s = get_settings()
    monkeypatch.setattr(s, "speech_provider", "fake")
    status = speech.status()
    assert status["languages"]["ar"]["voice"] == "ar-OM-AbdullahNeural"
    assert status["languages"]["en"]["voice"] == "en-GB-RyanNeural"
