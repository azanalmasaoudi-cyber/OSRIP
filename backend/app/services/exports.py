"""CSV exports that carry their data mode, assumptions and provenance (booklet 3.4, 3.12; T07, T12).

Missing values are empty cells, never zero. Values are unrounded. Text cells are
neutralised against spreadsheet formula injection.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Any

from app.domain.enums import DataMode
from app.services.imports.csv_file import safe_cell

SYNTHETIC_LABEL = "SYNTHETIC DEMONSTRATION DATA - declared test inputs; not Omani statistics"
VERIFIED_LABEL = "Verified-source data (published snapshots)"


def mode_label(data_mode: DataMode | str) -> str:
    return SYNTHETIC_LABEL if str(data_mode) == DataMode.SYNTHETIC.value else VERIFIED_LABEL


def _inputs_text(inputs: Iterable[dict[str, Any]]) -> str:
    parts = []
    for i in inputs:
        value = "missing" if i["value"] is None else i["value"]
        who = "/".join(x for x in (i["commodity"], i["partner"], i["flow"]) if x)
        label = f"{i['indicator']['code']} {who}".strip()
        period = f"{i['period_start']}..{i['period_end']}"
        provenance = f"[version {i['dataset_version']['label']}; {i['source_row']}]"
        parts.append(
            f"{i['role']}: {label} {period} {i['area']['code']} = {value} {i['unit']['code']} "
            f"{provenance}"
        )
    return " | ".join(parts)


CALC_HEADER = [
    "data_mode",
    "section",
    "calculation",
    "formula",
    "status",
    "value",
    "unit",
    "reason",
    "caveats",
    "notes",
    "inputs",
]


def calculation_rows(data_mode: str, calcs: Iterable[dict[str, Any]]) -> list[list[str]]:
    rows = []
    for c in calcs:
        r = c["result"]
        rows.append(
            [
                data_mode,
                c["section"],
                c["title"]["en"],
                c["formula"]["en"],
                r["status"],
                "" if r["value"] is None else r["value"],
                (r["unit"] or {}).get("code", ""),
                (c["reason"] or {}).get("en", "") if c["reason"] else "",
                " ".join(x["en"] for x in c["caveats"]),
                " ".join(n["en"] for n in c["notes"]),
                _inputs_text(c["inputs"]),
            ]
        )
    return rows


def write_csv(preamble: list[str], sections: list[tuple[list[str], list[list[str]]]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for line in preamble:
        writer.writerow([f"# {line}"])
    for header, rows in sections:
        writer.writerow([])
        writer.writerow(header)
        for row in rows:
            writer.writerow(
                [safe_cell(str(cell)) if not _is_number(cell) else cell for cell in row]
            )
    return buffer.getvalue()


def _is_number(cell: Any) -> bool:
    if not isinstance(cell, str) or not cell:
        return False
    try:
        float(cell)
    except ValueError:
        return False
    return True
