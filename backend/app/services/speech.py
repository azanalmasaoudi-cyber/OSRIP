"""Speech to text and text to speech for the assistant, on the server.

Provider: Azure AI Speech REST APIs (key and region, or a resource endpoint, stay on the
server: ``OSRIP_SPEECH_KEY``, ``OSRIP_SPEECH_REGION`` / ``OSRIP_SPEECH_ENDPOINT``).
* Recognition: the short-audio REST API, WAV PCM 16 kHz mono, at most 60 s, locales
  ar-OM and en-GB (both listed as supported by the provider).
* Synthesis: the neural voice configured for the persona in the assistant profile (version 3:
  Al Mulhim ar-OM-AbdullahNeural / en-GB-RyanNeural, Ilham ar-OM-AyshaNeural /
  en-GB-SoniaNeural; Arabic (Oman) voices exist, so Arabic is never read with a foreign voice).
  ``OSRIP_SPEECH_VOICE_AR``/``_EN`` apply only to a profile without personas.
Audio is passed through in memory and never stored or logged by OSRIP. ``fake`` is a
scripted provider for automated tests and is refused in production.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Callable
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app.core.config import get_settings
from app.services import monitoring

OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MAX_SPEAK_CHARS = 3000


class SpeechError(Exception):
    """Code (str): not_configured, invalid_audio, too_long, no_speech, timeout, network, http_NNN."""


http_client_factory: Callable[[float], httpx.Client] = lambda timeout: httpx.Client(timeout=timeout)  # noqa: E731


def provider_name() -> str | None:
    s = get_settings()
    if s.speech_provider == "fake" and s.environment != "production":
        return "fake"
    if s.speech_provider == "azure" and s.speech_key and (s.speech_region or s.speech_endpoint):
        return "azure"
    return None


def configured() -> bool:
    return provider_name() is not None


def status(personas: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Public state. ``personas``: code, default flag, gender and configured voice per language
    for each persona (from the active profile); ``languages`` give the default persona's."""
    s = get_settings()
    name = provider_name()
    default = next((p["voices"] for p in personas or [] if p.get("default")), None)
    voice = {
        "en": default["en"] if default else s.speech_voice_en,
        "ar": default["ar"] if default else s.speech_voice_ar,
    }
    return {
        "configured": name is not None,
        "provider": name,
        "max_seconds": s.speech_max_seconds,
        "languages": {
            "en": {"locale": s.speech_locale_en, "voice": voice["en"]},
            "ar": {"locale": s.speech_locale_ar, "voice": voice["ar"]},
        },
        "personas": personas or [],
        "stores_audio": False,
    }


def check_wav(audio: bytes, max_seconds: int) -> float:
    """Validate a PCM WAV (16 kHz, mono, 16-bit); returns its duration in seconds."""
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise SpeechError("invalid_audio")
    pos, fmt, data_len = 12, None, None
    while pos + 8 <= len(audio):
        chunk_id, size = audio[pos : pos + 4], struct.unpack("<I", audio[pos + 4 : pos + 8])[0]
        body = pos + 8
        if chunk_id == b"fmt " and size >= 16:
            fmt = struct.unpack("<HHIIHH", audio[body : body + 16])
        elif chunk_id == b"data":
            data_len = min(size, len(audio) - body)
            break
        pos = body + size + (size & 1)
    if fmt is None or data_len is None:
        raise SpeechError("invalid_audio")
    audio_format, channels, rate, _, _, bits = fmt
    if audio_format != 1 or channels != 1 or rate != 16000 or bits != 16:
        raise SpeechError("invalid_audio")
    seconds = data_len / (rate * 2)
    if seconds > max_seconds + 0.5:
        raise SpeechError("too_long")
    if seconds < 0.3:
        raise SpeechError("no_speech")
    return seconds


def _base(kind: str) -> str:
    s = get_settings()
    if s.speech_endpoint:
        root = s.speech_endpoint.rstrip("/")
        return (
            f"{root}/stt/speech/recognition/conversation/cognitiveservices/v1"
            if kind == "stt"
            else f"{root}/tts/cognitiveservices/v1"
        )
    region = (s.speech_region or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]+", region):
        raise SpeechError("not_configured")
    return (
        f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        if kind == "stt"
        else f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    )


def _post(url: str, **kwargs: Any) -> httpx.Response:
    s = get_settings()
    try:
        with http_client_factory(s.speech_timeout_seconds) as client:
            response = client.post(url, **kwargs)
    except httpx.TimeoutException as exc:
        monitoring.external_failure("speech", "timeout")
        raise SpeechError("timeout") from exc
    except httpx.HTTPError as exc:
        monitoring.external_failure("speech", "network")
        raise SpeechError("network") from exc
    if response.status_code != 200:
        monitoring.external_failure("speech", f"http_{response.status_code}")
        raise SpeechError(f"http_{response.status_code}")
    monitoring.external_success("speech")
    return response


def transcribe(audio: bytes, language: str) -> str:
    s = get_settings()
    name = provider_name()
    if name is None:
        raise SpeechError("not_configured")
    check_wav(audio, s.speech_max_seconds)
    if name == "fake":
        return (
            "ما آخر رقم لتوليد الكهرباء؟"
            if language == "ar"
            else "What is the latest electricity generation figure?"
        )
    response = _post(
        _base("stt"),
        params={
            "language": s.speech_locale_ar if language == "ar" else s.speech_locale_en,
            "format": "simple",
            "profanity": "masked",
        },
        content=audio,
        headers={
            "Ocp-Apim-Subscription-Key": s.speech_key.get_secret_value(),  # type: ignore[union-attr]
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
        },
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise SpeechError("invalid_response") from exc
    state = body.get("RecognitionStatus")
    if state == "Success" and str(body.get("DisplayText", "")).strip():
        return str(body["DisplayText"]).strip()
    if state in ("NoMatch", "InitialSilenceTimeout", "BabbleTimeout", "Success"):
        raise SpeechError("no_speech")
    raise SpeechError("recognition_failed")


def speakable(text: str, language: str | None = None) -> str:
    """Reply text as it should be read: evidence markers such as [E3] are dropped and, when the
    language is given, units and numbers are written the way they are said."""
    text = re.sub(r"\s*\[[ES]\d+\]", "", text)
    if language is not None:
        text = pronounce(text, language)
    return re.sub(r"\s+", " ", text).strip()[:MAX_SPEAK_CHARS]


# Units as they are said, longest first so "million m³" wins over "m³". Arabic uses the
# usual spoken forms; neural voices read the Western digits OSRIP displays in either language.
UNITS_SPOKEN: dict[str, list[tuple[str, str]]] = {
    "ar": [
        (r"million\s*m3|million\s*m³|million_m3|مليون\s*م³", "مليون متر مكعب"),
        (r"m³|m3|م³", "متر مكعب"),
        (r"GWh|غيغاواط\s*ساعة", "غيغاواط ساعة"),
        (r"MWh", "ميغاواط ساعة"),
        (r"MW|ميغاواط", "ميغاواط"),
        (r"million\s*OMR|million_OMR|مليون\s*ر\.ع\.?", "مليون ريال عماني"),
        (r"thousand\s*OMR|thousand_OMR", "ألف ريال عماني"),
        (r"OMR|ر\.ع\.?", "ريال عماني"),
        (r"percentage\s*points|percentage_points|نقطة\s*مئوية", "نقطة مئوية"),
        (r"%|٪", " بالمئة"),
        (r"tonnes?|tons?", "طن"),
    ],
    "en": [
        (r"million\s*m3|million\s*m³|million_m3", "million cubic metres"),
        (r"m³|m3", "cubic metres"),
        (r"GWh", "gigawatt hours"),
        (r"MWh", "megawatt hours"),
        (r"MW", "megawatts"),
        (r"million\s*OMR|million_OMR", "million Omani rials"),
        (r"thousand\s*OMR|thousand_OMR", "thousand Omani rials"),
        (r"OMR", "Omani rials"),
        (r"percentage_points", "percentage points"),
        (r"%|٪", " percent"),
    ],
}


def pronounce(text: str, language: str) -> str:
    """Numbers and units for speech: thousands separators are removed (so 23,264 is one
    number, not two), a leading + is said as "plus"/"زائد", a range's en dash (2022–2025) is
    said as "to"/"إلى" (hyphens are left alone: they are minus signs or dates), and unit
    symbols are spelled out in the voice's language."""
    lang = "ar" if language == "ar" else "en"
    text = re.sub(r"(?<=\d)[,٬](?=\d{3}\b)", "", text)
    text = re.sub(r"(?<![\w.])\+(?=\d)", "زائد " if lang == "ar" else "plus ", text)
    text = re.sub(r"(?<=\d)\s*–\s*(?=\d)", " إلى " if lang == "ar" else " to ", text)
    for pattern, spoken in UNITS_SPOKEN[lang]:
        boundary = r"(?<![A-Za-z])(?:" + pattern + r")(?![A-Za-z])"
        text = re.sub(boundary, f" {spoken.strip()}" if spoken.startswith(" ") else spoken, text)
    return text


TEST_PHRASES = {
    "ar": "مرحباً، أنا {name}. هذا اختبار للصوت: بلغ الاستهلاك 41,234 غيغاواط ساعة في 2025، بزيادة 3.5٪.",
    "en": "Hello, I am {name}. This is a voice test: consumption reached 41,234 GWh in 2025, up 3.5%.",
}


def voice_check(voices: dict[str, str]) -> dict[str, Any]:
    """Whether each configured voice name exists for this speech resource, from the provider's
    own voice list (cached for an hour). ``verified`` is None when the list cannot be read."""
    name = provider_name()
    if name is None:
        return {
            "configured": False,
            "voices": {k: {"name": v, "verified": None} for k, v in voices.items()},
        }
    available = _voice_list()
    result = {}
    for lang, voice in voices.items():
        if available is None:
            result[lang] = {"name": voice, "verified": None}
            continue
        found = available.get(voice)
        result[lang] = {
            "name": voice,
            "verified": found is not None,
            "locale": (found or {}).get("Locale"),
            "gender": (found or {}).get("Gender"),
        }
    return {"configured": True, "voices": result}


_VOICES_CACHE: dict[str, Any] = {"at": 0.0, "voices": None}


def _voice_list() -> dict[str, dict[str, Any]] | None:
    import time

    if _VOICES_CACHE["voices"] is not None and time.monotonic() - _VOICES_CACHE["at"] < 3600:
        return _VOICES_CACHE["voices"]
    name = provider_name()
    if name == "fake":
        voices = {
            v: {"ShortName": v, "Locale": v[:5], "Gender": g}
            for v, g in (
                ("ar-OM-AbdullahNeural", "Male"), ("ar-OM-AyshaNeural", "Female"),
                ("en-GB-RyanNeural", "Male"), ("en-GB-SoniaNeural", "Female"),
            )
        }  # fmt: skip
    else:
        s = get_settings()
        url = _base("tts").replace("/cognitiveservices/v1", "/cognitiveservices/voices/list")
        try:
            with http_client_factory(s.speech_timeout_seconds) as client:
                response = client.get(
                    url,
                    headers={"Ocp-Apim-Subscription-Key": s.speech_key.get_secret_value()},  # type: ignore[union-attr]
                )
        except httpx.HTTPError:
            monitoring.external_failure("speech", "voices_network")
            return None
        if response.status_code != 200:
            monitoring.external_failure("speech", f"voices_http_{response.status_code}")
            return None
        try:
            voices = {
                v["ShortName"]: v
                for v in response.json()
                if isinstance(v, dict) and "ShortName" in v
            }
        except ValueError:
            return None
    _VOICES_CACHE.update(at=time.monotonic(), voices=voices)
    return voices


def _test_tone(seconds: float = 1.5, rate: int = 16000) -> bytes:
    """A real, playable WAV (a rising and falling 220 Hz tone) for the test provider, so
    playback and the loudness-driven animation can be exercised without a speech service."""
    import math

    frames = int(seconds * rate)
    samples = bytearray()
    for i in range(frames):
        envelope = math.sin(math.pi * i / frames)
        samples += struct.pack("<h", int(12000 * envelope * math.sin(2 * math.pi * 220 * i / rate)))
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data"
    body += struct.pack("<I", len(samples)) + bytes(samples)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def ssml(text: str, locale: str, voice: str) -> str:
    """The SSML request for one reply: the text escaped, the locale and voice named."""
    return (
        f"<speak version='1.0' xml:lang='{escape(locale)}'>"
        f"<voice xml:lang='{escape(locale)}' name='{escape(voice)}'>{escape(text)}</voice></speak>"
    )


WAV_FORMAT = "riff-16khz-16bit-mono-pcm"  # what recognition accepts (acceptance round trips)


def synthesize(
    text: str, language: str, voice: str | None = None, output_format: str = OUTPUT_FORMAT
) -> tuple[bytes, str]:
    """Audio bytes and their media type, spoken by ``voice`` (the persona's configured voice;
    the speech settings' voice for the language when not given)."""
    s = get_settings()
    name = provider_name()
    if name is None:
        raise SpeechError("not_configured")
    text = speakable(text, language)
    if not text:
        raise SpeechError("empty_text")
    if name == "fake":
        return _test_tone(), "audio/wav"
    locale = s.speech_locale_ar if language == "ar" else s.speech_locale_en
    voice = voice or (s.speech_voice_ar if language == "ar" else s.speech_voice_en)
    request = ssml(text, locale, voice)
    response = _post(
        _base("tts"),
        content=request.encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": s.speech_key.get_secret_value(),  # type: ignore[union-attr]
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": output_format,
            "User-Agent": "OSRIP",
        },
    )
    return response.content, "audio/wav" if output_format == WAV_FORMAT else "audio/mpeg"
