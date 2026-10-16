"""Build the assistant personas' portraits from their masters.

    backend\\.venv\\Scripts\\python.exe tools\\build_persona_portraits.py

Run during development (never on a page request). Needs Pillow.

The masters, chosen by the project owner:
- Al Mulhim (16 October 2026): the man in a dishdasha and kumma in a courtyard, from the
  owner's introduction (docs/OSRIP_Intro_Single_File.html), stored unchanged as
  omani-man-courtyard.png. It matches Ilham's setting; it replaces the earlier master
  omani-professional.png (10 October, from the booklet), which stays for the editorial images.
- Ilham (10 October 2026): the woman in a headscarf and an abaya with embroidered sleeves, from
  docs/Oman_Statistics_References_and_Images_English.docx, stored unchanged as
  omani-woman-professional.jpg (the same artwork appears in the introduction).
Both are generated artwork of fictional people ("no endorsement or real-person identity is
implied").

Masters are checked by SHA-256 so a different file is never substituted. Two crops per persona,
downscaled only: a square head-and-shoulders portrait (avatar) and a 3:4 half-length figure (the
Talk workspace). The crops and their real sizes are recorded in frontend/assets/editorial/
sources.json.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASTERS = ROOT / "frontend" / "assets" / "editorial" / "masters"
SOURCES = ROOT / "frontend" / "assets" / "editorial" / "sources.json"
OUT = ROOT / "frontend" / "public" / "images" / "assistant"
QUALITY = 84

PERSONAS = [
    {
        "id": "persona-mulhim",
        "persona": "mulhim",
        "subject": "Al Mulhim's portrait: fictional, generated image of an adult Omani man in "
        "a white dishdasha with furakha and an embroidered kumma, in a courtyard",
        "master": "omani-man-courtyard.png",
        "sha256": "3e02f5aa9f48a19fa1ab4994f99e07a1483e02387081e8845924c2022c9ff6f0",
        "origin": "owner_supplied_introduction",
        "document": "docs/OSRIP_Intro_Single_File.html",
        "chosen": "2026-10-16, by the project owner, matching Ilham's portrait",
        # (left, top, right, bottom) in master pixels
        "portrait": (330, 50, 810, 530),
        "figure": (150, 40, 990, 1160),
    },
    {
        "id": "persona-ilham",
        "persona": "ilham",
        "subject": "Ilham's portrait: fictional, generated image of an adult Omani woman in a dark "
        "teal headscarf and an abaya with gold-embroidered sleeves, in a courtyard",
        "master": "omani-woman-professional.jpg",
        "sha256": "529d559d961841f45953899521ea52803259b5e50a1a5424733dcb82a82c31e0",
        "origin": "owner_supplied_document",
        "document": "docs/Oman_Statistics_References_and_Images_English.docx",
        "chosen": "2026-10-10, by the project owner, for the assistant personas",
        "portrait": (300, 64, 820, 584),
        "figure": (152, 40, 992, 1160),
    },
]
# The man's head-and-shoulders area is 436 px wide in its master, so the portrait is 432 px.
SIZES = {"portrait": (432, 432), "figure": (600, 800)}


def build(entry: dict) -> list[dict]:
    path = MASTERS / entry["master"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{entry['master']}: SHA-256 differs; refusing to use it")
    image = Image.open(path)
    if image.mode != "RGB":
        background = Image.new("RGB", image.size, (0, 0, 0))
        background.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
        image = background
    outputs = []
    for kind, size in SIZES.items():
        box = entry[kind]
        crop = image.crop(box)
        if crop.width < size[0] or crop.height < size[1]:
            raise SystemExit(f"{entry['id']} {kind}: crop smaller than {size}; no upscaling")
        crop = crop.resize(size, Image.LANCZOS)
        name = f"{entry['persona']}-{kind}-{size[0]}.jpg"
        target = OUT / name
        crop.save(target, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        outputs.append(
            {
                "file": f"frontend/public/images/assistant/{name}",
                "crop": list(box),
                "width": size[0],
                "height": size[1],
                "bytes": target.stat().st_size,
            }
        )
        print(f"{name}: {size[0]}x{size[1]}, {target.stat().st_size} bytes")
    return outputs


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    assets = [a for a in sources["assets"] if a["id"] not in {p["id"] for p in PERSONAS}]
    for entry in PERSONAS:
        width, height = Image.open(MASTERS / entry["master"]).size
        assets.append(
            {
                "id": entry["id"],
                "subject": entry["subject"],
                "origin": entry["origin"],
                "document": entry["document"],
                "master": entry["master"],
                "sha256": entry["sha256"],
                "source_width": width,
                "source_height": height,
                "generator": "Not recorded; the document describes its illustrations as generated "
                "artwork of a fictional Omani professional with no real-person identity implied",
                "chosen": entry["chosen"],
                "transformations": "Cropped and downscaled only (no retouching or upscaling); "
                "JPEG quality 84.",
                "derivatives": build(entry),
                "status": "in_use",
                "usage": f"Assistant persona '{entry['persona']}': avatar (portrait) and Talk "
                "workspace (figure); listed in the assistant profile",
            }
        )
    sources["assets"] = assets
    SOURCES.write_text(
        json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
