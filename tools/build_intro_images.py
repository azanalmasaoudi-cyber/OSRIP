"""Build the introduction's images from the owner's introduction.

    backend\\.venv\\Scripts\\python.exe tools\\build_intro_images.py

Run during development (never on a page request). Needs Pillow.

The owner's introduction (docs/OSRIP_Intro_Single_File.html, 16 October 2026) embeds five
images. They were extracted unchanged into frontend/assets/editorial/masters/ and are checked
here by SHA-256, so a different file is never substituted:
- Al Mulhim's portrait (omani-man-courtyard.png, also the master of his assistant portraits);
- Ilham's portrait (omani-woman-courtyard.jpg; the same picture as omani-woman-professional.jpg,
  encoded differently);
- the electricity, water and trade illustrations on a white background.

Each is downscaled whole (no cropping, no retouching, no upscaling) to
frontend/public/images/intro/. The portraits keep the introduction's framing through CSS (cover,
from the top centre); the illustrations are shown complete (contain). The derivatives are
recorded in frontend/assets/editorial/sources.json.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASTERS = ROOT / "frontend" / "assets" / "editorial" / "masters"
SOURCES = ROOT / "frontend" / "assets" / "editorial" / "sources.json"
OUT = ROOT / "frontend" / "public" / "images" / "intro"
DOCUMENT = "docs/OSRIP_Intro_Single_File.html"
QUALITY = 84
WIDTH = 600

IMAGES = [
    {
        "id": "intro-mulhim",
        "subject": "Al Mulhim in the introduction: fictional, generated image of an adult Omani "
        "man in a white dishdasha and an embroidered kumma, in a courtyard",
        "master": "omani-man-courtyard.png",
        "sha256": "3e02f5aa9f48a19fa1ab4994f99e07a1483e02387081e8845924c2022c9ff6f0",
        "file": "mulhim.jpg",
    },
    {
        "id": "intro-ilham",
        "subject": "Ilham in the introduction: fictional, generated image of an adult Omani woman "
        "in a dark teal headscarf and an abaya with gold-embroidered sleeves, in a courtyard",
        "master": "omani-woman-courtyard.jpg",
        "sha256": "1b021bab4b17ddf74db9495ff46025de1d76ac53b9b24f14a3bc5f230d7b16a4",
        "file": "ilham.jpg",
    },
    {
        "id": "intro-electricity",
        "subject": "Illustration of solar panels and an electricity substation (white background)",
        "master": "intro-electricity.jpg",
        "sha256": "2cac02f7f7b29d0d03ca0275b37fbb69f78bd5549463d0978b2eb4a26ed40fbc",
        "file": "electricity.jpg",
    },
    {
        "id": "intro-water",
        "subject": "Illustration of a water facility and channels (white background)",
        "master": "intro-water.jpg",
        "sha256": "08e6d5cacfd209dcc3fe631c24ca364accd913159d268534969a5ad1e029615f",
        "file": "water.jpg",
    },
    {
        "id": "intro-trade",
        "subject": "Illustration of a port and a container ship (white background)",
        "master": "intro-trade.jpg",
        "sha256": "8eccac68b8cc0460b7b920da1c1ac2a26398289e9fb46d7f74572b426cba912d",
        "file": "trade.jpg",
    },
]


def build(entry: dict) -> dict:
    path = MASTERS / entry["master"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{entry['master']}: SHA-256 differs; refusing to use it")
    image = Image.open(path).convert("RGB")
    if image.width < WIDTH:
        raise SystemExit(f"{entry['id']}: master narrower than {WIDTH} px; no upscaling")
    size = (WIDTH, round(image.height * WIDTH / image.width))
    target = OUT / entry["file"]
    image.resize(size, Image.LANCZOS).save(
        target, "JPEG", quality=QUALITY, optimize=True, progressive=True
    )
    print(f"{entry['file']}: {size[0]}x{size[1]}, {target.stat().st_size} bytes")
    return {
        "id": entry["id"],
        "subject": entry["subject"],
        "origin": "owner_supplied_introduction",
        "document": DOCUMENT,
        "master": entry["master"],
        "sha256": entry["sha256"],
        "source_width": image.width,
        "source_height": image.height,
        "generator": "Not recorded; generated artwork supplied by the project owner "
        "(fictional people; no real-person identity implied)",
        "chosen": "2026-10-16, by the project owner, for the introduction",
        "transformations": f"Downscaled whole to {WIDTH} px wide (no cropping, retouching or "
        f"upscaling); JPEG quality {QUALITY}.",
        "derivatives": [
            {
                "file": f"frontend/public/images/intro/{entry['file']}",
                "width": size[0],
                "height": size[1],
                "bytes": target.stat().st_size,
            }
        ],
        "status": "in_use",
        "usage": "The first-visit introduction (Entrance.tsx)",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in IMAGES}
    sources["assets"] = [a for a in sources["assets"] if a["id"] not in ids]
    sources["assets"].extend(build(entry) for entry in IMAGES)
    SOURCES.write_text(
        json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
