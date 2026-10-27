"""A TrueType font for PDF reports: glyph lookup, widths and a subset to embed (standard
library only).

The font is chosen from ``OSRIP_REPORT_FONT_PATH`` or common system locations, and must
cover Latin letters and the Arabic presentation forms that shaped Arabic text uses (Arial,
Tahoma and Segoe UI on Windows; DejaVu Sans on Linux, package fonts-dejavu-core). A font
whose licence forbids embedding (OS/2 fsType restricted or bitmap-only) is refused.

The subset keeps every table the glyphs need (hinting programs included) and empties the
outlines of glyphs the document does not use, so a report embeds a few tens of kilobytes
instead of the whole font; glyph ids are unchanged, which keeps the PDF's Identity mapping
simple. A font that forbids subsetting is embedded whole.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)
# Tables that only shaping engines or printers use; the PDF draws glyphs by id.
DROPPED = {b"DSIG", b"GSUB", b"GPOS", b"GDEF", b"BASE", b"JSTF", b"MATH", b"kern", b"morx",
           b"hdmx", b"LTSH", b"VDMX", b"PCLT", b"EBDT", b"EBLC", b"EBSC"}  # fmt: skip
REQUIRED_CODEPOINTS = (ord("A"), ord("0"), 0xFE8D, 0xFEDF)  # A, 0, alef, initial lam


class FontError(Exception):
    """No usable font: ``str`` is a short code."""


@dataclass
class Font:
    path: str
    data: bytes
    tables: dict[bytes, tuple[int, int]]
    units_per_em: int
    bbox: tuple[int, int, int, int]
    ascent: int
    descent: int
    cap_height: int
    italic_angle: float
    num_glyphs: int
    advances: list[int]
    cmap: dict[int, int]
    long_loca: bool
    may_subset: bool
    name: str = "OSRIPReportFont"
    _missing: set[int] = field(default_factory=set)

    def table(self, tag: bytes) -> bytes:
        offset, length = self.tables[tag]
        return self.data[offset : offset + length]

    def glyph(self, codepoint: int) -> int:
        return self.cmap.get(codepoint, 0)

    def has(self, codepoint: int) -> bool:
        return codepoint in self.cmap

    def advance(self, gid: int) -> int:
        """Advance width in font units."""
        return self.advances[gid] if gid < len(self.advances) else self.advances[-1]

    def width(self, gids: list[int], size: float) -> float:
        return sum(self.advance(g) for g in gids) * size / self.units_per_em

    # ------------------------------------------------------------------ subsetting

    def _loca(self) -> list[int]:
        raw = self.table(b"loca")
        if self.long_loca:
            return list(struct.unpack(f">{self.num_glyphs + 1}I", raw[: 4 * (self.num_glyphs + 1)]))
        return [
            2 * v
            for v in struct.unpack(f">{self.num_glyphs + 1}H", raw[: 2 * (self.num_glyphs + 1)])
        ]

    def _closure(self, used: set[int], loca: list[int], glyf: bytes) -> set[int]:
        """The used glyphs with the components of composite glyphs."""
        keep = {0} | {g for g in used if g < self.num_glyphs}
        todo = list(keep)
        while todo:
            gid = todo.pop()
            start, end = loca[gid], loca[gid + 1]
            if end - start < 10 or struct.unpack(">h", glyf[start : start + 2])[0] >= 0:
                continue
            pos = start + 10
            while True:
                flags, component = struct.unpack(">HH", glyf[pos : pos + 4])
                pos += 4 + (4 if flags & 0x0001 else 2)
                pos += 2 if flags & 0x0008 else 4 if flags & 0x0040 else 8 if flags & 0x0080 else 0
                if component not in keep and component < self.num_glyphs:
                    keep.add(component)
                    todo.append(component)
                if not flags & 0x0020:
                    break
        return keep

    def subset(self, used: set[int]) -> bytes:
        """The font file to embed: unused glyph outlines emptied, shaping tables dropped."""
        if not self.may_subset or b"glyf" not in self.tables:
            return self.data
        loca = self._loca()
        glyf = self.table(b"glyf")
        keep = self._closure(used, loca, glyf)
        new_glyf = bytearray()
        offsets = []
        for gid in range(self.num_glyphs):
            offsets.append(len(new_glyf))
            if gid in keep:
                new_glyf += glyf[loca[gid] : loca[gid + 1]]
                new_glyf += b"\0" * (-len(new_glyf) % 4)
        offsets.append(len(new_glyf))
        head = bytearray(self.table(b"head"))
        head[8:12] = b"\0\0\0\0"  # checkSumAdjustment, not used by PDF viewers
        head[50:52] = struct.pack(">h", 1)  # long loca offsets
        replaced = {
            b"glyf": bytes(new_glyf),
            b"loca": struct.pack(f">{len(offsets)}I", *offsets),
            b"head": bytes(head),
        }
        tags = sorted(t for t in self.tables if t not in DROPPED)
        return _assemble({t: replaced.get(t, self.table(t)) for t in tags})


def _checksum(data: bytes) -> int:
    padded = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF


def _assemble(tables: dict[bytes, bytes]) -> bytes:
    n = len(tables)
    entry_selector = max(0, n.bit_length() - 1)
    search_range = (1 << entry_selector) * 16
    header = struct.pack(
        ">IHHHH", 0x00010000, n, search_range, entry_selector, n * 16 - search_range
    )
    offset = 12 + 16 * n
    directory = b""
    body = b""
    for tag, data in tables.items():
        directory += struct.pack(">4sIII", tag, _checksum(data), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return header + directory + body


def _cmap(data: bytes, offset: int) -> dict[int, int]:
    """Unicode to glyph from the best subtable: format 12 (full Unicode) or format 4 (BMP)."""
    count = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
    subtables: dict[tuple[int, int], int] = {}
    for i in range(count):
        platform, encoding, sub = struct.unpack(
            ">HHI", data[offset + 4 + 8 * i : offset + 12 + 8 * i]
        )
        subtables[(platform, encoding)] = offset + sub
    out: dict[int, int] = {}
    for key in ((3, 10), (0, 4), (3, 1), (0, 3)):
        if key not in subtables:
            continue
        at = subtables[key]
        fmt = struct.unpack(">H", data[at : at + 2])[0]
        if fmt == 12:
            groups = struct.unpack(">I", data[at + 12 : at + 16])[0]
            for g in range(groups):
                start, end, glyph = struct.unpack(">III", data[at + 16 + 12 * g : at + 28 + 12 * g])
                for cp in range(start, min(end, start + 0x10000) + 1):
                    out.setdefault(cp, glyph + cp - start)
            return out
        if fmt == 4:
            segs = struct.unpack(">H", data[at + 6 : at + 8])[0] // 2
            ends = struct.unpack(f">{segs}H", data[at + 14 : at + 14 + 2 * segs])
            base = at + 16 + 2 * segs
            starts = struct.unpack(f">{segs}H", data[base : base + 2 * segs])
            deltas = struct.unpack(f">{segs}h", data[base + 2 * segs : base + 4 * segs])
            range_at = base + 4 * segs
            ranges = struct.unpack(f">{segs}H", data[range_at : range_at + 2 * segs])
            for s in range(segs):
                for cp in range(starts[s], ends[s] + 1):
                    if cp == 0xFFFF:
                        continue
                    if ranges[s] == 0:
                        glyph = (cp + deltas[s]) & 0xFFFF
                    else:
                        where = range_at + 2 * s + ranges[s] + 2 * (cp - starts[s])
                        glyph = struct.unpack(">H", data[where : where + 2])[0]
                        glyph = (glyph + deltas[s]) & 0xFFFF if glyph else 0
                    if glyph:
                        out.setdefault(cp, glyph)
            return out
    raise FontError("font_has_no_unicode_cmap")


def load(path: str) -> Font:
    data = Path(path).read_bytes()
    if data[:4] not in (b"\x00\x01\x00\x00", b"true"):
        raise FontError("not_a_truetype_font")  # .ttc collections and CFF (.otf) fonts are not used
    count = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for i in range(count):
        tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
        tables[tag] = (offset, length)
    for tag in (b"head", b"hhea", b"hmtx", b"maxp", b"cmap", b"loca", b"glyf"):
        if tag not in tables:
            raise FontError("font_table_missing")

    def t(tag: bytes) -> bytes:
        o, n = tables[tag]
        return data[o : o + n]

    head, hhea, maxp = t(b"head"), t(b"hhea"), t(b"maxp")
    units = struct.unpack(">H", head[18:20])[0]
    bbox = struct.unpack(">hhhh", head[36:44])
    long_loca = struct.unpack(">h", head[50:52])[0] == 1
    ascent, descent = struct.unpack(">hh", hhea[4:8])
    metrics = struct.unpack(">H", hhea[34:36])[0]
    num_glyphs = struct.unpack(">H", maxp[4:6])[0]
    hmtx = t(b"hmtx")
    advances = [struct.unpack(">H", hmtx[4 * i : 4 * i + 2])[0] for i in range(metrics)]
    advances += [advances[-1]] * (num_glyphs - metrics)
    cap_height, fs_type = ascent, 0
    if b"OS/2" in tables:
        os2 = t(b"OS/2")
        fs_type = struct.unpack(">H", os2[8:10])[0]
        version = struct.unpack(">H", os2[0:2])[0]
        if version >= 2 and len(os2) >= 90:
            cap_height = struct.unpack(">h", os2[88:90])[0]
    if fs_type & 0x000F == 0x0002 or fs_type & 0x0200:
        raise FontError("font_licence_forbids_embedding")
    italic = struct.unpack(">i", t(b"post")[4:8])[0] / 65536 if b"post" in tables else 0.0
    return Font(
        path=path, data=data, tables=tables, units_per_em=units, bbox=bbox, ascent=ascent,
        descent=descent, cap_height=cap_height, italic_angle=italic, num_glyphs=num_glyphs,
        advances=advances, cmap=_cmap(data, tables[b"cmap"][0]), long_loca=long_loca,
        may_subset=not fs_type & 0x0100,
    )  # fmt: skip


@lru_cache(maxsize=4)
def _load_checked(path: str) -> Font:
    font = load(path)
    if not all(font.has(cp) for cp in REQUIRED_CODEPOINTS):
        raise FontError("font_lacks_arabic_or_latin")
    return font


def report_font() -> Font:
    """The configured font, or the first usable one found on this system."""
    configured = get_settings().report_font_path
    for path in [configured] if configured else CANDIDATES:
        if path and Path(path).is_file():
            try:
                return _load_checked(path)
            except (FontError, OSError, struct.error):
                if configured:
                    raise
    raise FontError("no_report_font")
