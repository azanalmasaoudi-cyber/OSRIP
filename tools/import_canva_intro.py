"""Add a persona's recorded Arabic introduction (Canva AI Voice) to the website.

    backend\\.venv\\Scripts\\python.exe tools\\import_canva_intro.py --persona mulhim ^
        --input "C:\\path\\Mulhim intro.mp4" --voice "<the voice name shown in Canva>"

Canva's AI Voice is downloaded inside a video (MP4); Canva does not offer the voice as an audio
file on its own. This tool takes that MP4 and:

1. finds its audio track and copies it out without re-encoding: AAC (what Canva's MP4 videos
   carry) becomes ``<persona>-intro-ar.m4a``, MP3 becomes ``.mp3``; any other codec is encoded
   once to AAC and the report says so. A video file is never just renamed;
2. checks the result: it decodes the whole file, and refuses one that is shorter than 3 s,
   longer than 90 s, silent or nearly silent (speech must be audible in at least a fifth of the
   file), so a broken or empty export never reaches the site;
3. writes it to ``frontend/public/audio/intro/`` and names it, with its exact words (the
   approved script) and where it came from (Canva AI Voice, the voice chosen, the date), in
   ``manifest.json`` there. The website then offers it; until then the introduction is hidden.

Canva's terms allow this use on OSRIP's own website; the clip may not be sold or redistributed
on its own (Canva AI Product Terms and Content License Agreement). Uses PyAV, installed in the
backend environment. The input is treated as untrusted media: it is only demuxed and decoded.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import av

ROOT = Path(__file__).resolve().parents[1]
# OSRIP_INTRO_DIR is for testing this tool against a copy of the folder.
INTRO = Path(os.environ.get("OSRIP_INTRO_DIR") or ROOT / "frontend" / "public" / "audio" / "intro")
MANIFEST = INTRO / "manifest.json"

SCRIPTS = {
    "mulhim": (
        "السلام عليكم، أنا مُلهم، مساعدك في منصة عُمان الذكية لذكاء الموارد. أساعدك على فهم بيانات "
        "الكهرباء والمياه والأمن الغذائي والتجارة، واستكشاف النتائج والفرص استنادًا إلى المصادر "
        "المتاحة. اختر المحور الذي تريد البدء به."
    ),
    "ilham": (
        "مرحبًا بك، أنا إلهام، مساعدتك في منصة عُمان الذكية لذكاء الموارد. أساعدك على قراءة "
        "المؤشرات ومقارنة البيانات وعرض النتائج في جداول ورسوم بيانية واضحة. أخبرني بما تريد "
        "دراسته، ولنبدأ."
    ),
}

MIN_SECONDS, MAX_SECONDS = 3.0, 90.0
SPEECH_DBFS = -40.0  # a 50 ms window louder than this counts as sound
MIN_SOUND_SHARE = 0.20  # at least a fifth of the clip must be audible


class Refused(Exception):
    pass


def extract(source: Path, persona: str) -> tuple[Path, Path, str]:
    """Copy (or, for an unusual codec, encode once) the audio track into a temporary file in
    the site folder; returns (temporary file, final name, how). The clip already on the site
    is replaced only after the new one has passed the checks."""
    with av.open(str(source)) as inp:
        streams = [s for s in inp.streams if s.type == "audio"]
        if not streams:
            raise Refused("the file has no audio track (was AI Voice added before downloading?)")
        stream = streams[0]
        codec = stream.codec_context.name
        if codec in ("aac", "mp3"):
            ext, fmt = (".m4a", "ipod") if codec == "aac" else (".mp3", "mp3")
            target = INTRO / f"{persona}-intro-ar{ext}"
            part = INTRO / f".{target.name}.part"
            with av.open(str(part), "w", format=fmt) as out:
                copy = out.add_stream_from_template(stream)
                for packet in inp.demux(stream):
                    if packet.dts is None:
                        continue
                    packet.stream = copy
                    out.mux(packet)
            return part, target, f"copied the {codec.upper()} track without re-encoding"
        target = INTRO / f"{persona}-intro-ar.m4a"
        part = INTRO / f".{target.name}.part"
        with av.open(str(part), "w", format="ipod") as out:
            enc = out.add_stream("aac", rate=stream.codec_context.sample_rate or 44100)
            enc.bit_rate = 128_000
            for frame in inp.decode(stream):
                for packet in enc.encode(frame):
                    out.mux(packet)
            for packet in enc.encode(None):
                out.mux(packet)
        return part, target, f"encoded the {codec} track once to AAC (128 kbit/s)"


def measure(path: Path) -> dict[str, float]:
    """Duration, loudness and the share of the clip that is audible, from the decoded audio."""
    import numpy as np

    windows: list[float] = []
    peak = 0.0
    total_sq, total_n = 0.0, 0
    with av.open(str(path)) as inp:
        stream = inp.streams.audio[0]
        rate = stream.codec_context.sample_rate
        buffer = np.zeros(0, dtype=np.float64)
        size = max(1, int(rate * 0.05))
        for frame in inp.decode(stream):
            data = frame.to_ndarray().astype(np.float64)
            if data.ndim > 1:
                data = data.mean(axis=0)
            if frame.format.name.startswith(("s16",)):
                data = data / 32768.0
            elif frame.format.name.startswith(("s32",)):
                data = data / 2147483648.0
            peak = max(peak, float(np.abs(data).max(initial=0.0)))
            total_sq += float((data * data).sum())
            total_n += data.size
            buffer = np.concatenate([buffer, data])
            while buffer.size >= size:
                chunk, buffer = buffer[:size], buffer[size:]
                windows.append(math.sqrt(float((chunk * chunk).mean())))
    if not total_n:
        raise Refused("no audio could be decoded from the extracted file")

    def dbfs(x: float) -> float:
        return 20 * math.log10(x) if x > 0 else -120.0

    loud = sum(1 for w in windows if dbfs(w) > SPEECH_DBFS)
    return {
        "duration_seconds": round(total_n / rate, 2),
        "rms_dbfs": round(dbfs(math.sqrt(total_sq / total_n)), 1),
        "peak_dbfs": round(dbfs(peak), 1),
        "audible_share": round(loud / len(windows), 2) if windows else 0.0,
        "sample_rate": rate,
    }


def check(stats: dict[str, float]) -> None:
    if not MIN_SECONDS <= stats["duration_seconds"] <= MAX_SECONDS:
        raise Refused(
            f"duration {stats['duration_seconds']} s is outside {MIN_SECONDS}-{MAX_SECONDS} s"
        )
    if stats["audible_share"] < MIN_SOUND_SHARE or stats["peak_dbfs"] < -30:
        raise Refused(f"the clip is silent or nearly silent ({stats})")


def record(
    persona: str, target: Path, voice: str, design: str | None, stats: dict[str, float]
) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest.setdefault("clips", {}).setdefault(persona, {})["ar"] = {
        "src": target.name,
        "transcript": SCRIPTS[persona],
        "provenance": {
            "tool": "Canva AI Voice",
            "voice": voice,
            "design": design,
            "imported": datetime.now(UTC).date().isoformat(),
            "duration_seconds": stats["duration_seconds"],
            "licence": (
                "Canva AI Product Terms and Content License Agreement: use on this website; "
                "not sold or redistributed on its own."
            ),
        },
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--persona", choices=sorted(SCRIPTS), required=True)
    parser.add_argument("--input", type=Path, required=True, help="the MP4 downloaded from Canva")
    parser.add_argument(
        "--voice", required=True, help="the AI Voice name exactly as Canva shows it"
    )
    parser.add_argument("--design", help="the Canva design link (kept for provenance)")
    args = parser.parse_args()
    if not args.input.is_file():
        print(f"not found: {args.input}", file=sys.stderr)
        return 2
    INTRO.mkdir(parents=True, exist_ok=True)
    part: Path | None = None
    try:
        part, target, how = extract(args.input, args.persona)
        stats = measure(part)
        check(stats)
    except (Refused, av.error.FFmpegError) as exc:
        if part is not None:
            part.unlink(missing_ok=True)
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    # Only now does the new clip replace the one on the site (another extension included).
    for old in INTRO.glob(f"{args.persona}-intro-ar.*"):
        if old != target:
            old.unlink()
    os.replace(part, target)
    record(args.persona, target, args.voice, args.design, stats)
    print(f"{args.persona}: {target} ({how})")
    audible = int(stats["audible_share"] * 100)
    print(
        f"  duration {stats['duration_seconds']} s, {stats['sample_rate']} Hz, "
        f"RMS {stats['rms_dbfs']} dBFS, peak {stats['peak_dbfs']} dBFS, "
        f"audible {audible}% of the clip"
    )
    print(f"  listed in {MANIFEST} with the approved script and voice '{args.voice}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
