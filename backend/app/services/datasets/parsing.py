"""Reading an uploaded dataset (CSV, Excel .xlsx, JSON) into a header and rows of text.

Every file is untrusted input. Nothing in it is executed or evaluated: no formulas, macros,
links or external entities (the .xlsx reader is ``app.services.sync.xlsx``); limits on size,
rows, columns and cell length are checked while reading. Values are kept as the text the
file holds (a JSON number keeps its digits; an Excel number is shown as its format shows it;
an Excel date becomes an ISO date). An empty cell is missing (None), never zero.

* CSV: UTF-8 (with or without a byte-order mark), or Windows-1256 (Arabic Excel exports) when
  the file is not UTF-8; the delimiter (comma, semicolon, tab or bar) is detected.
* Excel: the first sheet with values, or the sheet named.
* JSON: an array of objects, ``{"columns": [...], "rows": [[...]]}``, an object holding one
  such array (``data``, ``rows``, ``records``, ``items``), or columns as equal-length arrays.

The first non-empty row (CSV, Excel) is the header. Empty or repeated column names are
renamed (``column_3``, ``Value (2)``) and every change is listed in ``notes``.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from app.services.sync.xlsx import Workbook, WorkbookError

MAX_CELL_CHARS = 1000
MAX_NAME_CHARS = 120
FILE_TYPES = {".csv": "csv", ".txt": "csv", ".xlsx": "xlsx", ".json": "json"}
_DELIMITERS = ",;\t|"
_ROW_KEYS = ("data", "rows", "records", "items")


class DatasetError(ValueError):
    """The file cannot be read as a dataset; ``str`` is a short code for the interface."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.params = params


@dataclass
class Parsed:
    file_type: str
    columns: list[str]
    rows: list[list[str | None]]
    sheet: str | None = None
    sheets: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)


def file_type(filename: str) -> str:
    kind = FILE_TYPES.get(PurePath(filename or "").suffix.lower())
    if kind is None:
        raise DatasetError("unsupported_file_type")
    return kind


def _cell(value: Any, notes: dict[str, Any]) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    if not text:
        return None
    if len(text) > MAX_CELL_CHARS:
        notes["cells_truncated"] = notes.get("cells_truncated", 0) + 1
        text = text[:MAX_CELL_CHARS]
    return text


def _header(names: list[Any], notes: dict[str, Any]) -> list[str]:
    out: list[str] = []
    renamed: list[dict[str, str]] = []
    for i, raw in enumerate(names, start=1):
        name = re.sub(r"\s+", " ", str(raw or "")).strip()[:MAX_NAME_CHARS] or f"column_{i}"
        base, n = name, 2
        while name in out:
            name = f"{base} ({n})"
            n += 1
        if name != str(raw or "").strip():
            renamed.append({"from": str(raw or "")[:MAX_NAME_CHARS], "to": name})
        out.append(name)
    if renamed:
        notes["columns_renamed"] = renamed
    return out


def _table(
    header: list[Any], body: list[list[Any]], max_rows: int, max_columns: int, notes: dict
) -> tuple[list[str], list[list[str | None]]]:
    if not header:
        raise DatasetError("no_header")
    if len(header) > max_columns:
        raise DatasetError("too_many_columns", limit=max_columns, found=len(header))
    columns = _header(header, notes)
    rows: list[list[str | None]] = []
    ragged = 0
    for raw in body:
        cells = [_cell(v, notes) for v in raw]
        if not any(c is not None for c in cells):
            continue  # an empty line is not an observation
        if len(cells) != len(columns):
            ragged += 1
            if len(cells) > len(columns) and any(c is not None for c in cells[len(columns) :]):
                raise DatasetError("row_longer_than_header", row=len(rows) + 2)
            cells = (cells + [None] * len(columns))[: len(columns)]
        rows.append(cells)
        if len(rows) > max_rows:
            raise DatasetError("too_many_rows", limit=max_rows)
    if not rows:
        raise DatasetError("no_rows")
    if ragged:
        notes["rows_padded"] = ragged
    return columns, rows


def _decode(data: bytes, notes: dict[str, Any]) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1256")
    except UnicodeDecodeError as exc:
        raise DatasetError("unknown_text_encoding") from exc
    notes["encoding"] = "windows-1256"
    return text


def read_csv(data: bytes, max_rows: int, max_columns: int) -> Parsed:
    notes: dict[str, Any] = {}
    text = _decode(data, notes)
    if "\x00" in text[:4096]:
        raise DatasetError("not_a_text_file")
    sample = text[:16384]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=_DELIMITERS)
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    if delimiter != ",":
        notes["delimiter"] = {"\t": "tab"}.get(delimiter, delimiter)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        lines = []
        for line in reader:
            lines.append(line)
            if len(lines) > max_rows + 50:  # header and empty lines included
                break
    except csv.Error as exc:
        raise DatasetError("csv_unreadable") from exc
    while lines and not any(c.strip() for c in lines[0]):
        lines.pop(0)
    if not lines:
        raise DatasetError("no_header")
    columns, rows = _table(lines[0], lines[1:], max_rows, max_columns, notes)
    return Parsed("csv", columns, rows, notes=notes)


def read_xlsx(data: bytes, max_rows: int, max_columns: int, sheet: str | None) -> Parsed:
    notes: dict[str, Any] = {}
    try:
        book = Workbook(data, dates=True)
        names = book.sheet_names
        chosen = None
        for name in [sheet] if sheet else names:
            if name not in names:
                raise DatasetError("sheet_missing", sheet=sheet)
            candidate = book.sheet(name)
            if candidate.cells:
                chosen = candidate
                break
    except WorkbookError as exc:
        raise DatasetError(f"xlsx_{exc}".split(":", 1)[0]) from exc
    if chosen is None:
        raise DatasetError("no_rows")
    row_numbers = chosen.rows()
    if len(row_numbers) > max_rows + 1:
        raise DatasetError("too_many_rows", limit=max_rows)
    width = max(c for _, c in chosen.cells)
    if width > max_columns:
        raise DatasetError("too_many_columns", limit=max_columns, found=width)
    # The width is that of the rightmost cell with a value, so no column is empty everywhere.
    grid = [[chosen.get(r, c) for c in range(1, width + 1)] for r in row_numbers]
    columns, rows = _table(grid[0], grid[1:], max_rows, max_columns, notes)
    return Parsed("xlsx", columns, rows, sheet=chosen.name, sheets=names, notes=notes)


def _json_records(value: Any) -> tuple[list[Any], list[list[Any]]]:
    if isinstance(value, dict):
        if isinstance(value.get("columns"), list) and isinstance(value.get("rows"), list):
            rows = value["rows"]
            if not all(isinstance(r, list) for r in rows):
                raise DatasetError("json_rows_not_lists")
            return value["columns"], rows
        for key in _ROW_KEYS:
            if isinstance(value.get(key), list):
                return _json_records(value[key])
        if value and all(isinstance(v, list) for v in value.values()):
            lengths = {len(v) for v in value.values()}
            if len(lengths) != 1:
                raise DatasetError("json_columns_differ_in_length")
            names = list(value)
            return names, [list(r) for r in zip(*value.values(), strict=True)]
        raise DatasetError("json_not_a_table")
    if isinstance(value, list):
        if not value:
            raise DatasetError("no_rows")
        if not all(isinstance(r, dict) for r in value):
            raise DatasetError("json_not_a_table")
        names: list[str] = []
        for record in value:
            for k in record:
                if k not in names:
                    names.append(k)
        return names, [[record.get(k) for k in names] for record in value]
    raise DatasetError("json_not_a_table")


def _json_text(value: Any) -> str:
    """Compact JSON of a nested value, with its numbers written as the file wrote them."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                f"{json.dumps(k, ensure_ascii=False)}:{_json_text(v)}" for k, v in value.items()
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(_json_text(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def _json_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return _json_text(value)
    return value


def read_json(data: bytes, max_rows: int, max_columns: int) -> Parsed:
    notes: dict[str, Any] = {}
    try:
        # Numbers keep the digits the file wrote (no float rounding).
        value = json.loads(data.decode("utf-8-sig"), parse_float=Decimal, parse_int=Decimal)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise DatasetError("json_unreadable") from exc
    names, body = _json_records(value)
    if len(body) > max_rows:
        raise DatasetError("too_many_rows", limit=max_rows)
    body = [[_json_value(v) for v in row] for row in body]
    columns, rows = _table(names, body, max_rows, max_columns, notes)
    return Parsed("json", columns, rows, notes=notes)


def parse(
    filename: str, data: bytes, *, max_rows: int, max_columns: int, sheet: str | None = None
) -> Parsed:
    kind = file_type(filename)
    if not data:
        raise DatasetError("empty_file")
    if kind == "csv":
        return read_csv(data, max_rows, max_columns)
    if kind == "xlsx":
        return read_xlsx(data, max_rows, max_columns, sheet)
    return read_json(data, max_rows, max_columns)
