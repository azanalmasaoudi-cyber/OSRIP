"""NCSI Monthly Statistical Bulletin, official Excel workbook: tables 21 (electricity) and 22
(water) as OSRIP import records. Pure: bytes in, records out.

Verified against the October 2026 workbook (retrieved 2026-10-23 from the NCSI publications
list): sheet "21" holds gross and net electricity production by region in GWh, sheet "22"
water production by region in thousand m³. Each table gives the three latest months, the
previous full year and the year-to-date totals of the current and the previous year; years
carry a footnote mark (⁽¹⁾ provisional, ⁽²⁾ preliminary) defined under the table.

The layout is read, not assumed: the table title, the header rows (months, years, the
"Total (End - Sep)" year-to-date columns), the unit and the footnote marks are all located
by their text, and every region label must be in the explicit map below. Anything
unexpected stops the conversion with a reason (``LayoutError``); nothing is guessed. Empty
cells are not published values and produce no record (never zero). Percentage-change
columns are the publisher's derived figures and are not imported.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services.sync.xlsx import Sheet, Workbook, column_letters

SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
YEAR = re.compile(r"^(?:\(?(\d)\)?)?\s*(\d{4})$")
YTD = re.compile(r"total\s*\(\s*end\s*-\s*([a-z]{3})\w*\s*\)", re.IGNORECASE)
FOOTNOTE = re.compile(r"^(\d)\s*-\s*(provisional|preliminary|revised|final)\b", re.IGNORECASE)

UNITS = {
    "gw\\h": "GWh",
    "gwh": "GWh",
    "gw/h": "GWh",
    "(000)m³": "thousand_m3",
    "(000)m3": "thousand_m3",
}


@dataclass(frozen=True, slots=True)
class TableSpec:
    sheet: str
    title: re.Pattern[str]
    blocks: dict[str, str]  # block label -> OSRIP indicator code
    regions: dict[str, str]  # normalised region label -> OSRIP area code
    unit: str


TABLES = (
    TableSpec(
        sheet="21",
        title=re.compile(r"^\s*21\s*-\s*electricity\s*$", re.IGNORECASE),
        blocks={
            "gross production": "ELEC_GROSS_GENERATION",
            "net production": "ELEC_NET_GENERATION",
        },
        regions={
            "muscat": "OM-MA",
            "dhofar": "OM-ZU",
            "musandam": "OM-MU",
            "ad dakhliyah": "OM-DA",
            "al batinah & adh dhahira": "OM-GRP-BATINAH-DHAHIRAH",
            "ash sharqiya": "OM-GRP-SHARQIYAH",
            "al wusta": "OM-WU",
            "others": "OM-GRP-OTHER-ELEC",
            "total": "OM",
        },
        unit="GWh",
    ),
    TableSpec(
        sheet="22",
        title=re.compile(r"^\s*22\s*-\s*water\s*$", re.IGNORECASE),
        blocks={"production": "WATER_PRODUCTION"},
        regions={
            "muscat": "OM-MA",
            "dhofar": "OM-ZU",
            "other governorates": "OM-GRP-OTHER-WATER",
            "total": "OM",
        },
        unit="thousand_m3",
    ),
)


class LayoutError(ValueError):
    """The workbook does not have the layout this converter was verified against."""


@dataclass(frozen=True, slots=True)
class Record:
    indicator_code: str
    area_code: str
    period_start: date
    period_end: date
    frequency: str  # monthly | annual (a year-to-date total is annual with period_complete false)
    period_complete: bool
    unit_code: str
    value: Decimal
    revision_status: str | None
    source_locator: str
    record_ref: str

    def csv_row(self) -> dict[str, str]:
        return {
            "record_ref": self.record_ref,
            "indicator_code": self.indicator_code,
            "area_code": self.area_code,
            "partner_code": "",
            "flow": "",
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_complete": "true" if self.period_complete else "false",
            "frequency": self.frequency,
            "statement_date": "",
            "unit_code": self.unit_code,
            "value": format(self.value, "f"),
            "value_operator": "",
            "revision_status": self.revision_status or "",
            "source_locator": self.source_locator,
        }


@dataclass(slots=True)
class Parsed:
    records: list[Record] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)  # consistency warnings (totals)
    tables: list[str] = field(default_factory=list)


def normalise(label: str) -> str:
    """'-Al Batinah⁽³⁾ & Adh Dhahira' -> 'al batinah & adh dhahira' (marks, dash, spacing)."""
    text = label.translate(SUPERSCRIPT).replace("⁽", "(").replace("⁾", ")")
    text = re.sub(r"\(\d\)", "", text).strip().lstrip("-–").strip()
    return re.sub(r"\s+", " ", text).lower()


def _mark_year(text: str) -> tuple[str | None, int] | None:
    raw = text.translate(SUPERSCRIPT).replace("⁽", "(").replace("⁾", ")").strip()
    m = YEAR.match(raw)
    return (m.group(1), int(m.group(2))) if m else None


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _find(sheet: Sheet, test, rows: range | None = None) -> list[tuple[int, int, str]]:  # noqa: ANN001
    return [
        (r, c, v)
        for (r, c), v in sorted(sheet.cells.items())
        if (rows is None or r in rows) and test(v)
    ]


def parse_table(sheet: Sheet, spec: TableSpec, label: str) -> Parsed:
    out = Parsed()
    if not _find(sheet, lambda v: bool(spec.title.match(v))):
        raise LayoutError(f"table {spec.sheet}: title not found")
    items = _find(sheet, lambda v: v.strip().lower() == "item")
    if not items:
        raise LayoutError(f"table {spec.sheet}: header row 'Item' not found")
    head = items[0][0]
    blocks = [
        r for r in sheet.rows() if r > head and normalise(sheet.get(r, 1) or "") in spec.blocks
    ]
    if not blocks:
        raise LayoutError(f"table {spec.sheet}: no block of rows ({', '.join(spec.blocks)}) found")
    header = range(head, blocks[0])
    # Footnote marks: "1- Provisional", "2-Preliminary".
    marks = {}
    for _, _, v in _find(sheet, lambda v: bool(FOOTNOTE.match(v.strip()))):
        m = FOOTNOTE.match(v.strip())
        assert m is not None
        marks[m.group(1)] = m.group(2).lower()
    # Unit.
    units = {
        UNITS[v.replace(" ", "").lower()]
        for _, _, v in _find(sheet, lambda v: v.replace(" ", "").lower() in UNITS, header)
    }
    if units != {spec.unit}:
        raise LayoutError(
            f"table {spec.sheet}: expected unit {spec.unit}, found {sorted(units) or 'none'}"
        )
    # Months (English abbreviations) and the year above each.
    months = {
        c: MONTHS[v.strip().lower()]
        for _, c, v in _find(sheet, lambda v: v.strip().lower() in MONTHS, header)
    }
    years: dict[int, tuple[str | None, int]] = {}
    for _, c, v in _find(sheet, lambda v: _mark_year(v) is not None, header):
        years.setdefault(c, _mark_year(v))  # type: ignore[arg-type]
    ytd = _find(sheet, lambda v: bool(YTD.search(v)), header)
    if not months or not ytd:
        raise LayoutError(f"table {spec.sheet}: month or year-to-date headers not found")
    ytd_row, ytd_col, ytd_text = ytd[0]
    end_abbr = YTD.search(ytd_text).group(1).lower()  # type: ignore[union-attr]
    if end_abbr not in MONTHS:
        raise LayoutError(f"table {spec.sheet}: year-to-date end month unreadable")
    ytd_end = MONTHS[end_abbr]
    first_month_col = min(months)
    columns: list[
        tuple[int, str, date, date, bool, str | None]
    ] = []  # col, freq, start, end, complete, status
    for col, (mark, year) in sorted(years.items()):
        status = marks.get(mark) if mark else None
        if mark and status is None:
            raise LayoutError(
                f"table {spec.sheet}: footnote mark {mark} is not defined under the table"
            )
        if col in months:
            m = months[col]
            columns.append((col, "monthly", date(year, m, 1), _month_end(year, m), True, status))
        elif ytd_col <= col < first_month_col:
            columns.append(
                (col, "annual", date(year, 1, 1), _month_end(year, ytd_end), False, status)
            )
        elif col > first_month_col:
            columns.append((col, "annual", date(year, 1, 1), date(year, 12, 31), True, status))
    if not any(c[1] == "monthly" for c in columns) or not any(not c[4] for c in columns):
        raise LayoutError(f"table {spec.sheet}: columns could not be identified")
    # Blocks of rows: a block label, its region rows, ending with "Total".
    indicator: str | None = None
    totals: dict[tuple[str, int], tuple[Decimal, Decimal]] = {}
    for row in [r for r in sheet.rows() if r >= blocks[0]]:
        label_text = sheet.get(row, 1)
        if label_text is None:
            continue
        key = normalise(label_text)
        if key in spec.blocks:
            indicator = spec.blocks[key]
            continue
        if indicator is None:
            continue
        if FOOTNOTE.match(label_text.strip()):
            break
        area = spec.regions.get(key)
        if area is None:
            raise LayoutError(f"table {spec.sheet}: region label '{label_text}' is not in the map")
        for col, freq, start, end, complete, status in columns:
            raw = sheet.get(row, col)
            if raw is None:
                continue  # not published: no record, never zero
            try:
                value = Decimal(raw)
            except InvalidOperation:
                continue  # a sign such as "-" or ".." is not a number
            ref = f"{column_letters(col)}{row}"
            out.records.append(
                Record(
                    indicator,
                    area,
                    start,
                    end,
                    freq,
                    complete,
                    spec.unit,
                    value,
                    status,
                    f"Table {spec.sheet}, cell {ref}",
                    f"{label}/T{spec.sheet}/{ref}",
                )
            )
            total, parts = totals.get((indicator, col), (Decimal(0), Decimal(0)))
            if area == "OM":
                totals[(indicator, col)] = (value, parts)
            else:
                totals[(indicator, col)] = (total, parts + value)
        if area == "OM":
            indicator = None  # the block ends at its total
    for (ind, col), (total, parts) in totals.items():
        if total and parts and abs(total - parts) > abs(total) * Decimal("0.005"):
            out.checks.append(
                f"table {spec.sheet} {ind} column {column_letters(col)}: "
                f"regions add up to {parts}, total is {total}"
            )
    out.tables.append(spec.sheet)
    return out


def parse_workbook(data: bytes, label: str) -> Parsed:
    """Records from tables 21 and 22, labelled for their release (e.g. ``MSB-2026-10``)."""
    book = Workbook(data)
    out = Parsed()
    for spec in TABLES:
        if spec.sheet not in book.sheet_names:
            raise LayoutError(f"sheet {spec.sheet} is missing")
        part = parse_table(book.sheet(spec.sheet), spec, label)
        out.records += part.records
        out.checks += part.checks
        out.tables += part.tables
    if not out.records:
        raise LayoutError("no values found")
    return out
