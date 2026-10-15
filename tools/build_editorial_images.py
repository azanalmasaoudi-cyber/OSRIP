"""Build OSRIP's editorial images: masters, responsive derivatives and the asset manifest.

    backend\\.venv\\Scripts\\python.exe tools\\build_editorial_images.py

Run during development (never on a page request). Needs Pillow (a development tool;
it is not a runtime dependency of the API).

1. Masters: the four illustrations supplied in the academic booklet (Appendix F) are
   extracted unchanged from the Word file and kept in frontend/assets/editorial/masters
   (not served to browsers). They are identified by SHA-256, so a different file is
   never silently substituted. Canva exports, once saved, go in the same folder and are
   listed in frontend/assets/editorial/sources.json.
2. Derivatives: AVIF, WebP and JPEG at widths no larger than the master (nothing is
   upscaled), written to frontend/public/images/editorial.
3. Manifest: frontend/public/images/editorial/manifest.json records, for every asset,
   its origin, generator, date, prompt (when known), source dimensions, transformations
   and each derivative's real pixel size and byte size. A TypeScript copy of the
   derivative list is written for the <picture> component.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BOOKLET = ROOT / "docs" / "OSRIP_Academic_Booklet_English (2).docx"
MASTERS = ROOT / "frontend" / "assets" / "editorial" / "masters"
SOURCES = ROOT / "frontend" / "assets" / "editorial" / "sources.json"
OUT = ROOT / "frontend" / "public" / "images" / "editorial"
TS_OUT = ROOT / "frontend" / "src" / "content" / "editorial.generated.ts"

LANDSCAPE_WIDTHS = (480, 800, 1200, 1536, 1920, 2560, 3840)
PORTRAIT_WIDTHS = (360, 640, 1024, 1440)
QUALITY = {"avif": 55, "webp": 78, "jpg": 82}
IVORY = (250, 246, 238)  # JPEG has no alpha; transparent pixels sit on the page colour


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_masters(sources: list[dict]) -> None:
    """Copy booklet images whose hashes the source list names, unchanged."""
    wanted = {s["sha256"]: s for s in sources if s.get("origin") == "booklet_appendix_f"}
    if not wanted:
        return
    MASTERS.mkdir(parents=True, exist_ok=True)
    missing = [s for s in wanted.values() if not (MASTERS / s["master"]).exists()]
    if not missing:
        return
    if not BOOKLET.exists():
        sys.exit(f"Masters missing and the booklet is not at {BOOKLET}")
    with zipfile.ZipFile(BOOKLET) as z:
        for info in z.infolist():
            if not info.filename.startswith("word/media/"):
                continue
            data = z.read(info)
            entry = wanted.get(sha256(data))
            if entry and not (MASTERS / entry["master"]).exists():
                (MASTERS / entry["master"]).write_bytes(data)
                print(f"extracted {info.filename} -> {entry['master']}")
    still = [s["master"] for s in wanted.values() if not (MASTERS / s["master"]).exists()]
    if still:
        sys.exit(f"Not found in the booklet (hash mismatch): {', '.join(still)}")


def derivatives(entry: dict) -> list[dict]:
    path = MASTERS / entry["master"]
    data = path.read_bytes()
    if sha256(data) != entry["sha256"]:
        sys.exit(f"{entry['master']}: hash differs from sources.json; refusing to use it")
    image = Image.open(path)
    width, height = image.size
    entry["source_width"], entry["source_height"] = width, height
    widths = PORTRAIT_WIDTHS if height > width else LANDSCAPE_WIDTHS
    targets = [w for w in widths if w <= width] or [width]
    if width not in targets and width < widths[-1]:
        targets.append(width)  # the master's own width, so nothing is upscaled
    rgba = image.convert("RGBA")
    flat = Image.new("RGB", rgba.size, IVORY)
    flat.paste(rgba, mask=rgba.getchannel("A"))
    out = []
    OUT.mkdir(parents=True, exist_ok=True)
    for w in sorted(set(targets)):
        h = round(height * w / width)
        resized = flat.resize((w, h), Image.Resampling.LANCZOS) if w != width else flat
        for fmt in ("avif", "webp", "jpg"):
            name = f"{entry['id']}-{w}.{fmt}"
            target = OUT / name
            save_format = {"jpg": "JPEG", "webp": "WEBP", "avif": "AVIF"}[fmt]
            options = {"quality": QUALITY[fmt]}
            if fmt == "jpg":
                options.update(optimize=True, progressive=True)
            resized.save(target, save_format, **options)
            check = Image.open(target)
            out.append(
                {
                    "file": f"/images/editorial/{name}",
                    "format": fmt,
                    "width": check.size[0],
                    "height": check.size[1],
                    "bytes": target.stat().st_size,
                }
            )
    return out


def main() -> None:
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    extract_masters(sources["assets"])
    manifest = {"generated_on": date.today().isoformat(), "note": sources["note"], "assets": []}
    ts_entries = []
    for entry in sources["assets"]:
        record = dict(entry)
        if entry.get("master") and (MASTERS / entry["master"]).exists():
            record["derivatives"] = derivatives(record)
            record["native_4k"] = record["source_width"] >= 3840 and record["source_height"] >= 2160
            ts_entries.append(
                {
                    "id": record["id"],
                    "width": record["source_width"],
                    "height": record["source_height"],
                    "widths": sorted({d["width"] for d in record["derivatives"]}),
                }
            )
        else:
            record["derivatives"] = []
        manifest["assets"].append(record)
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    (OUT / "manifest.json").write_text(manifest_text, encoding="utf-8", newline="\n")
    lines = [
        "// Generated by tools/build_editorial_images.py from the asset manifest. Do not edit.",
        "export interface EditorialAsset { "
        "id: string; width: number; height: number; widths: readonly number[] }",
        "export const EDITORIAL_ASSETS = {",
    ]
    for e in ts_entries:
        lines.append(
            f"  '{e['id']}': {{ id: '{e['id']}', width: {e['width']}, "
            f"height: {e['height']}, widths: {e['widths']} }},"
        )
    lines.append("} as const satisfies Record<string, EditorialAsset>;")
    lines.append("export type EditorialId = keyof typeof EDITORIAL_ASSETS;")
    TS_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for record in manifest["assets"]:
        size = f"{record.get('source_width', '?')}x{record.get('source_height', '?')}"
        count = len(record["derivatives"])
        print(f"{record['id']}: source {size}, {count} derivatives, status {record['status']}")


if __name__ == "__main__":
    main()
