"""Parse an uploaded CSV as untrusted input (booklet 3.15).

Only UTF-8 text in CSV format is accepted. Cells are read as plain strings by the
standard-library ``csv`` module: nothing is evaluated, no type is inferred, and
spreadsheet formulas are just text. Size and row limits are enforced before the
file is stored.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import ApiError, unprocessable


@dataclass(frozen=True, slots=True)
class ParsedCsv:
    header: list[str]
    rows: list[dict[str, str]]  # data rows keyed by header; CSV row number = index + 2
    checksum_sha256: str


def parse_csv(data: bytes, filename: str) -> ParsedCsv:
    settings = get_settings()
    if not filename.lower().endswith(".csv"):
        raise unprocessable("unsupported_format", "Only .csv files are accepted.")
    if len(data) == 0:
        raise unprocessable("empty_file", "The file is empty.")
    if len(data) > settings.upload_max_bytes:
        raise ApiError(
            413,
            "file_too_large",
            f"The file is larger than {settings.upload_max_bytes // (1024 * 1024)} MB.",
        )
    try:
        text = data.decode("utf-8-sig")  # tolerate a UTF-8 byte-order mark
    except UnicodeDecodeError as exc:
        raise unprocessable("invalid_encoding", "The file must be UTF-8 encoded text.") from exc
    if "\x00" in text:
        raise unprocessable("invalid_encoding", "The file contains binary content, not CSV text.")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration as exc:
        raise unprocessable("empty_file", "The file has no header row.") from exc
    except csv.Error as exc:
        raise unprocessable("malformed_csv", f"The header row could not be read: {exc}.") from exc

    if not any(header):
        raise unprocessable("missing_header", "The first row must name the columns.")
    if any(not h for h in header):
        raise unprocessable("blank_column_name", "Every column in the header row needs a name.")
    duplicates = sorted({h for h in header if header.count(h) > 1})
    if duplicates:
        raise unprocessable(
            "duplicate_column_name", "Column names must be unique.", {"columns": duplicates}
        )

    rows: list[dict[str, str]] = []
    try:
        for line in reader:
            if not any(cell.strip() for cell in line):
                continue  # blank line
            if len(line) != len(header):
                raise unprocessable(
                    "ragged_row",
                    f"CSV row {reader.line_num} has {len(line)} cells "
                    f"but the header has {len(header)}.",
                    {"row_number": reader.line_num},
                )
            rows.append(dict(zip(header, line, strict=True)))
            if len(rows) > settings.upload_max_rows:
                raise unprocessable(
                    "too_many_rows", f"The file has more than {settings.upload_max_rows} rows."
                )
    except csv.Error as exc:
        raise unprocessable(
            "malformed_csv", f"CSV row {reader.line_num} could not be read: {exc}."
        ) from exc

    if not rows:
        raise unprocessable("no_data_rows", "The file has a header but no data rows.")
    return ParsedCsv(header, rows, hashlib.sha256(data).hexdigest())


def safe_cell(value: str) -> str:
    """Neutralise spreadsheet formula injection in CSV *exports* (OWASP)."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
