"""Live acceptance check of the personas' voices: Arabic, English and Omani place names.

    backend\\.venv\\Scripts\\python.exe scripts\\voice_acceptance.py [--out DIR]

Needs Azure AI Speech configured on the server (OSRIP_SPEECH_PROVIDER=azure, OSRIP_SPEECH_KEY
and OSRIP_SPEECH_REGION or OSRIP_SPEECH_ENDPOINT in backend/.env). Keys are read by the
settings and never printed. Without them the script stops before sending anything.

For each persona in the active profile and each language it:
1. synthesises the test sentences with the persona's configured voice (as WAV);
2. sends that audio back to speech recognition in the same locale and checks which place names
   and terms are recognised (a machine round trip: it finds clear mispronunciations, it cannot
   judge naturalness or accent);
3. saves every recording and writes results.json and listening-sheet.md, where a listener who
   knows Omani Arabic records whether each name sounds right and what the accent sounds like.

An Omani accent is claimed only after that listening review says so; the voices are Microsoft's
Arabic (Oman) locale voices, which is a locale, not a tested accent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Sentences and the names each must contain (checked in the recognised text).
TEST_SET: dict[str, list[tuple[str, list[str]]]] = {
    "ar": [
        ("السلام عليكم. أهلاً بكم في منصة عُمان الذكية لمعلومات الموارد.", ["عمان"]),
        ("مسقط ونزوى وصحار وصلالة من مدن سلطنة عُمان.", ["مسقط", "نزوى", "صحار", "صلالة"]),
        ("ميناء الدقم وولاية صور وعبري والبريمي وخصب.", ["الدقم", "صور", "عبري", "البريمي", "خصب"]),
        (
            "محافظة ظفار ومحافظة مسندم والجبل الأخضر وجزيرة مصيرة.",
            ["ظفار", "مسندم", "الأخضر", "مصيرة"],
        ),
        (
            "بلغ توليد الكهرباء خمسين ألفاً ومئة جيجاواط ساعة في عام ألفين وثلاثة وعشرين.",
            ["الكهرباء"],
        ),
    ],
    "en": [
        ("Welcome to the Oman Smart Resource Intelligence Platform.", ["oman"]),
        (
            "Muscat, Nizwa, Sohar and Salalah are cities in Oman.",
            ["muscat", "nizwa", "sohar", "salalah"],
        ),
        (
            "The port of Duqm, Sur, Ibri, Al Buraimi and Khasab.",
            ["duqm", "sur", "ibri", "buraimi", "khasab"],
        ),
        (
            "Dhofar, Musandam, Jebel Akhdar and Masirah Island.",
            ["dhofar", "musandam", "akhdar", "masirah"],
        ),
        (
            "Electricity generation reached fifty thousand one hundred gigawatt hours.",
            ["electricity"],
        ),
    ],
}

_MARKS = re.compile(r"[ً-ْٰـ]")


def normalise(text: str) -> str:
    t = _MARKS.sub("", text.lower())
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def recognised(expected: list[str], heard: str) -> dict[str, bool]:
    said = normalise(heard)
    return {name: normalise(name) in said for name in expected}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "voice-acceptance")
    args = parser.parse_args(argv)

    from app.services import speech
    from app.services.assistant import profile

    if speech.provider_name() != "azure":
        print(
            "Azure AI Speech is not configured on this server (OSRIP_SPEECH_PROVIDER=azure, "
            "OSRIP_SPEECH_KEY, and OSRIP_SPEECH_REGION or OSRIP_SPEECH_ENDPOINT). Nothing was "
            "sent; live voice verification remains pending."
        )
        return 2
    current = profile.active_now()
    if current is None:
        print("No assistant profile is active; run the migrations first.")
        return 2

    run = args.out / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run.mkdir(parents=True, exist_ok=True)
    results = []
    for who in profile.personas(current.profile):
        for language, sentences in TEST_SET.items():
            voice = who.voices.azure[language]
            for i, (sentence, names) in enumerate(sentences, start=1):
                row = {"persona": who.code, "language": language, "voice": voice, "text": sentence}
                try:
                    audio, _ = speech.synthesize(sentence, language, voice, speech.WAV_FORMAT)
                    path = run / f"{who.code}-{language}-{i}.wav"
                    path.write_bytes(audio)
                    heard = speech.transcribe(audio, language)
                    row |= {"audio": path.name, "heard": heard, "names": recognised(names, heard)}
                except speech.SpeechError as exc:
                    row |= {"error": str(exc)}
                results.append(row)
                print(f"{who.code} {language} {i}: {row.get('names') or row.get('error')}")
    (run / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Voice listening sheet",
        "",
        f"Profile version {current.version}. Machine round trip: recognised names below.",
        "A listener",
        "fills in the last two columns; only then may a pronunciation or accent be described.",
        "",
        "| Persona | Language | Voice | Recording | Names recognised | Sounds right? "
        "| Accent notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        names = ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in (r.get("names") or {}).items())
        lines.append(
            f"| {r['persona']} | {r['language']} | {r['voice']} | {r.get('audio', r.get('error'))} "
            f"| {names} |  |  |"
        )
    (run / "listening-sheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    missed = sum(1 for r in results for v in (r.get("names") or {}).values() if not v)
    failed = sum(1 for r in results if "error" in r)
    print(f"Saved in {run}. Names not recognised: {missed}. Failed requests: {failed}.")
    return 0 if not missed and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
