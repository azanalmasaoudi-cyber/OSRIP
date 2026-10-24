"""A small, defensive reader for official .xlsx workbooks (standard library only).

Reads cell values of the sheets it is asked for, nothing else: no formulas are evaluated,
no external links followed, no macros. The workbook is untrusted input, so the archive's
entry count and total uncompressed size are limited before anything is read, XML with a
document type or entity declaration is refused.

Numbers are returned as the publisher displays them: the stored binary value is first written
as the shortest decimal that round-trips it (4811.0879999999997 is 4811.088), then given the
number of decimals of the cell's own number format (a cell formatted
``#,##0.0`` holding 571.32553376831106 is published as 571.3). A cell in the General format,
or a format the reader does not recognise, keeps the shortest round-trip decimal.
"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree as ET

MAX_ARCHIVE_BYTES = 30_000_000
MAX_UNCOMPRESSED_BYTES = 150_000_000
MAX_ENTRIES = 3_000
MAX_SHEET_BYTES = 40_000_000

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REF = re.compile(r"^([A-Z]{1,3})(\d{1,7})$")


class WorkbookError(ValueError):
    """The file is not a readable, safe .xlsx workbook."""


def _xml(data: bytes) -> ET.Element:
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise WorkbookError("xml_declarations_not_allowed")
    try:
        # Document types and entities are refused above; expat resolves no external entity.
        return ET.fromstring(data)  # noqa: S314
    except ET.ParseError as exc:
        raise WorkbookError("xml_unreadable") from exc


def number_text(raw: str) -> str:
    """The shortest decimal text for a stored number (binary noise removed, nothing rounded)."""
    try:
        return format(Decimal(repr(float(raw))).normalize(), "f")
    except (ValueError, InvalidOperation) as exc:
        raise WorkbookError("number_unreadable") from exc


# Built-in number formats (ECMA-376 18.8.30) with a fixed number of decimals.
BUILTIN_DECIMALS = {1: 0, 2: 2, 3: 0, 4: 2, 37: 0, 38: 0, 39: 2, 40: 2}


def format_decimals(code: str) -> int | None:
    """Decimals shown by a custom number format such as '#,##0.0' (None: not a plain number)."""
    # Quoted text, backslash-escaped characters and [colour]/[condition] parts are not digits.
    section = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", code.split(";", 1)[0])
    if "%" in section or "E" in section.upper() or not re.search(r"[0#]", section):
        return None
    if "." not in section:
        return 0
    return len(re.findall(r"[0#]", section.split(".", 1)[1]))


def displayed(text: str, decimals: int | None) -> str:
    if decimals is None:
        return text
    return format(Decimal(text).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP), "f")


def column_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def column_letters(index: int) -> str:
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


@dataclass(frozen=True, slots=True)
class Sheet:
    name: str
    cells: dict[tuple[int, int], str]  # (row, column) -> text; empty cells are absent

    def get(self, row: int, column: int) -> str | None:
        return self.cells.get((row, column))

    def rows(self) -> list[int]:
        return sorted({r for r, _ in self.cells})

    def row(self, row: int) -> dict[int, str]:
        return {c: v for (r, c), v in self.cells.items() if r == row}

    def column(self, column: int) -> dict[int, str]:
        return {r: v for (r, c), v in self.cells.items() if c == column}


class Workbook:
    def __init__(self, data: bytes) -> None:
        if len(data) > MAX_ARCHIVE_BYTES:
            raise WorkbookError("file_too_large")
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise WorkbookError("not_an_xlsx_file") from exc
        infos = self._zip.infolist()
        if len(infos) > MAX_ENTRIES:
            raise WorkbookError("too_many_entries")
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            raise WorkbookError("uncompressed_size_too_large")
        names = set(self._zip.namelist())
        if "xl/workbook.xml" not in names:
            raise WorkbookError("not_an_xlsx_file")
        self._shared = self._shared_strings() if "xl/sharedStrings.xml" in names else []
        self._decimals = self._style_decimals() if "xl/styles.xml" in names else []
        workbook = _xml(self._read("xl/workbook.xml"))
        rels = _xml(self._read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") or "" for r in rels}
        self.sheet_paths: dict[str, str] = {}
        sheets = workbook.find(f"{_M}sheets")
        for s in sheets if sheets is not None else []:
            target = targets.get(s.get(f"{_R}id"), "")
            path = target.lstrip("/")
            path = path if path.startswith("xl/") else f"xl/{path}"
            if path in names:
                self.sheet_paths[s.get("name") or ""] = path

    def _read(self, name: str) -> bytes:
        try:
            return self._zip.read(name)
        except (zipfile.BadZipFile, zlib.error, KeyError, EOFError) as exc:
            raise WorkbookError("file_damaged") from exc

    def _style_decimals(self) -> list[int | None]:
        root = _xml(self._read("xl/styles.xml"))
        custom = {
            int(f.get("numFmtId") or -1): f.get("formatCode") or ""
            for f in root.iter(f"{_M}numFmt")
        }
        xfs = root.find(f"{_M}cellXfs")
        out: list[int | None] = []
        for xf in xfs if xfs is not None else []:
            fid = int(xf.get("numFmtId") or 0)
            out.append(format_decimals(custom[fid]) if fid in custom else BUILTIN_DECIMALS.get(fid))
        return out

    def _shared_strings(self) -> list[str]:
        root = _xml(self._read("xl/sharedStrings.xml"))
        return ["".join(t.text or "" for t in si.iter(f"{_M}t")) for si in root.findall(f"{_M}si")]

    @property
    def sheet_names(self) -> list[str]:
        return list(self.sheet_paths)

    def sheet(self, name: str) -> Sheet:
        path = self.sheet_paths.get(name)
        if path is None:
            raise WorkbookError(f"sheet_missing:{name}")
        info = self._zip.getinfo(path)
        if info.file_size > MAX_SHEET_BYTES:
            raise WorkbookError("sheet_too_large")
        root = _xml(self._read(path))
        data = root.find(f"{_M}sheetData")
        cells: dict[tuple[int, int], str] = {}
        for row in data if data is not None else []:
            for c in row:
                m = _REF.match(c.get("r") or "")
                if not m:
                    continue
                kind = c.get("t")
                v = c.find(f"{_M}v")
                if kind == "s" and v is not None and v.text is not None:
                    idx = int(v.text)
                    text = self._shared[idx] if 0 <= idx < len(self._shared) else ""
                elif kind == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{_M}t"))
                elif kind in ("str", "b", "e") and v is not None:
                    text = v.text or ""
                elif v is not None and v.text is not None:
                    style = int(c.get("s") or 0)
                    decimals = self._decimals[style] if 0 <= style < len(self._decimals) else None
                    text = displayed(number_text(v.text), decimals)
                else:
                    continue
                text = text.strip()
                if text:
                    cells[(int(m.group(2)), column_index(m.group(1)))] = text
        return Sheet(name, cells)
