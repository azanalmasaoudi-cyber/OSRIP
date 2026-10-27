"""PDF reports written directly (standard library only): A4 pages, an embedded subset of a
TrueType font, Arabic and English text, tables and vector charts.

Text is shaped and ordered by ``documents.text`` and drawn as glyph ids (Type 0 font,
Identity-H), with a ToUnicode map so the text can be searched and copied. Arabic reports run
right to left: paragraphs are right-aligned, table columns start on the right, and the time
axis of line and column charts runs right to left, as on the website. Charts are drawn from
the same table the report shows, never from other values. The file holds no scripts, forms
or external resources; reference links are plain URI links.
"""

from __future__ import annotations

import math
import zlib
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.documents import text as tx
from app.services.documents.fonts import Font
from app.services.documents.model import Document

PAGE_W, PAGE_H = 595.28, 841.89
MARGIN = 50.0
BODY = PAGE_W - 2 * MARGIN
TOP = PAGE_H - MARGIN
BOTTOM = MARGIN + 24  # room for the footer
INK = (0.10, 0.10, 0.11)
MUTED = (0.38, 0.38, 0.42)
ACCENT = (0.02, 0.45, 0.33)
GRID = (0.86, 0.86, 0.88)
HEADER_FILL = (0.94, 0.95, 0.95)
PALETTE = [(0.02, 0.59, 0.41), (0.15, 0.39, 0.92), (0.72, 0.42, 0.23), (0.45, 0.78, 0.65),
           (0.55, 0.69, 0.96), (0.86, 0.66, 0.53), (0.70, 0.88, 0.80), (0.77, 0.84, 0.98)]  # fmt: skip
LABELS = {
    "en": {"page": "Page {n} of {total}", "missing": "—", "chart_values": "Values: see the table."},
    "ar": {"page": "الصفحة {n} من {total}", "missing": "—", "chart_values": "القيم: انظر الجدول."},
}


def _num(value: str | None) -> float | None:
    try:
        return float(Decimal(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def _rgb(c: tuple[float, float, float]) -> str:
    return f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f}"


def _pdf_string(value: str) -> str:
    """A PDF text string: UTF-16BE with a byte order mark, as hex."""
    return "<FEFF" + value.encode("utf-16-be").hex().upper() + ">"


def _scale(values: list[float]) -> tuple[float, float, list[float]]:
    """0 or the minimum (if negative) to a rounded maximum, about four steps."""
    top = max([0.0, *values])
    low = min([0.0, *values])
    span = top - low or 1.0
    rough = span / 4
    magnitude = 10 ** math.floor(math.log10(rough))
    step = next((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= rough), rough)
    lo = math.floor(low / step) * step
    hi = math.ceil(top / step) * step or step
    ticks = []
    v = lo
    while v <= hi + step / 2:
        ticks.append(round(v, 10))
        v += step
    return lo, hi, ticks


def _range_scale(values: list[float]) -> tuple[float, float, list[float]]:
    low, top = min(values), max(values)
    span = top - low or abs(top) or 1.0
    rough = span / 4
    magnitude = 10 ** math.floor(math.log10(rough))
    step = next((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= rough), rough)
    lo = math.floor(low / step) * step
    hi = math.ceil(top / step) * step
    hi = hi if hi > lo else lo + step
    ticks = []
    v = lo
    while v <= hi + step / 2:
        ticks.append(round(v, 10))
        v += step
    return lo, hi, ticks


def _tick(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.3g}B"
    if a >= 1e6:
        return f"{v / 1e6:.3g}M"
    if a >= 1e4:
        return f"{v / 1e3:.3g}k"
    return f"{v:,.10g}" if a >= 1 or v == 0 else f"{v:.3g}"


class _Writer:
    def __init__(self, font: Font, language: str) -> None:
        self.font = font
        self.rtl = language == "ar"
        self.labels = LABELS[language]
        self.pages: list[list[str]] = []
        self.links: list[list[tuple[tuple[float, float, float, float], str]]] = []
        self.used: dict[int, str] = {0: ""}
        self.current = 0
        self.y = TOP
        self.new_page()

    # ------------------------------------------------------------------ pages and text

    def new_page(self) -> None:
        self.pages.append([])
        self.links.append([])
        self.current = len(self.pages) - 1
        self.y = TOP

    @property
    def ops(self) -> list[str]:
        return self.pages[self.current]

    def ensure(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self.new_page()

    def glyphs(self, logical: str, rtl: bool) -> list[int]:
        """Glyph ids in drawing order for one line, recording each glyph's text."""
        out = []
        for ch in tx.visual(tx.shape(logical), rtl):
            cp = ord(ch)
            gid = self.font.glyph(cp)
            source = tx.BASE_TEXT.get(cp, ch)
            if gid == 0 and cp in tx.BASE_TEXT:  # no presentation form: the base letter
                gid = self.font.glyph(ord(tx.BASE_TEXT[cp][0]))
            self.used.setdefault(gid, source)
            out.append(gid)
        return out

    def measure(self, logical: str, size: float) -> float:
        shaped = tx.shape(logical)
        return self.font.width([self.font.glyph(ord(c)) for c in shaped], size)

    def draw(
        self, x: float, y: float, gids: list[int], size: float, color=INK, bold: bool = False
    ) -> None:
        hexed = "".join(f"{g:04X}" for g in gids)
        style = f"2 Tr {size * 0.035:.3f} w {_rgb(color)} RG " if bold else ""
        self.ops.append(
            f"BT /F1 {size:.2f} Tf {style}{_rgb(color)} rg {x:.2f} {y:.2f} Td <{hexed}> Tj ET"
            + (" 0 Tr" if bold else "")
        )

    def line_text(self, logical: str, x0: float, width: float, y: float, size: float, *,
                  color=INK, bold: bool = False, align: str = "start", rtl: bool | None = None) -> float:  # fmt: skip
        """Draw one line within [x0, x0 + width]; returns the drawn width. ``align`` is left,
        right, center, or start / end of the document's reading direction."""
        rtl = tx.direction(logical, self.rtl) if rtl is None else rtl
        gids = self.glyphs(logical, rtl)
        w = self.font.width(gids, size)
        side = {
            "start": "right" if self.rtl else "left",
            "end": "left" if self.rtl else "right",
        }.get(align, align)
        x = x0 + (width - w) / 2 if side == "center" else x0 + width - w if side == "right" else x0
        self.draw(x, y, gids, size, color, bold)
        return w

    def paragraph(self, text: str, size: float = 10, *, color=INK, bold: bool = False,
                  indent: float = 0, leading: float = 1.45, gap: float = 6) -> None:  # fmt: skip
        width = BODY - indent
        line_h = size * leading
        for line in tx.wrap(text, width, lambda s: self.measure(s, size)):
            self.ensure(line_h)
            self.y -= line_h
            x0 = MARGIN if self.rtl else MARGIN + indent
            rtl = tx.direction(text, self.rtl)
            gids = self.glyphs(line, rtl)
            w = self.font.width(gids, size)
            x = x0 + width - w if self.rtl else x0
            self.draw(x, self.y + size * 0.25, gids, size, color, bold)
        self.y -= gap

    def rule(self, color=GRID, weight: float = 0.6) -> None:
        self.ops.append(
            f"{_rgb(color)} RG {weight} w {MARGIN:.2f} {self.y:.2f} m {PAGE_W - MARGIN:.2f} {self.y:.2f} l S"
        )

    # ------------------------------------------------------------------ blocks

    def bullets(self, items: list[str], size: float = 10) -> None:
        for item in items:
            line_h = size * 1.45
            self.ensure(line_h)
            dot_y = self.y - line_h + size * 0.25 + size * 0.3
            dot_x = PAGE_W - MARGIN - 4 if self.rtl else MARGIN + 4
            self.ops.append(f"{_rgb(ACCENT)} rg {dot_x - 1.6:.2f} {dot_y - 1.6:.2f} 3.2 3.2 re f")
            self.paragraph(item, size, indent=14, gap=2)
        self.y -= 4

    def table(self, title: str | None, columns: list[dict[str, Any]], rows: list[list[str | None]],
              note: str | None = None, size: float = 8.5) -> None:  # fmt: skip
        if title:
            self.ensure(40)
            self.paragraph(title, 10, bold=True, gap=2)
        pad = 4.0
        n = len(columns)
        natural = []
        for i, c in enumerate(columns):
            cells = [c["label"]] + [r[i] or "—" for r in rows[:200]]
            natural.append(max(self.measure(str(v), size) for v in cells) + 2 * pad)
        total = sum(natural)
        if total > BODY:
            floor = [min(w, 70.0) for w in natural]
            spare = BODY - sum(floor)
            extra = [w - f for w, f in zip(natural, floor, strict=True)]
            share = sum(extra) or 1.0
            widths = [f + spare * e / share for f, e in zip(floor, extra, strict=True)]
        else:
            widths = [w * BODY / total for w in natural]
        lefts = []
        x = MARGIN
        for w in widths:
            lefts.append(x)
            x += w
        if self.rtl:  # the first column on the right
            lefts = [PAGE_W - MARGIN - (lefts[i] - MARGIN) - widths[i] for i in range(n)]
        line_h = size * 1.35

        def cell_lines(value: str, i: int) -> list[str]:
            return tx.wrap(value, widths[i] - 2 * pad, lambda s: self.measure(s, size))

        def draw_row(values: list[str], header: bool) -> None:
            wrapped = [cell_lines(v, i) for i, v in enumerate(values)]
            height = max(len(w) for w in wrapped) * line_h + 2 * pad
            if self.y - height < BOTTOM:
                self.new_page()
                if not header:
                    draw_row([c["label"] for c in columns], True)
            top = self.y
            if header:
                self.ops.append(
                    f"{_rgb(HEADER_FILL)} rg {MARGIN:.2f} {top - height:.2f} {BODY:.2f} {height:.2f} re f"
                )
            for i, lines in enumerate(wrapped):
                numeric = columns[i].get("numeric")
                for k, line in enumerate(lines):
                    y = top - pad - (k + 1) * line_h + size * 0.3
                    align = "end" if numeric else "start"
                    self.line_text(line, lefts[i] + pad, widths[i] - 2 * pad, y, size,
                                   bold=header, color=INK, align=align,
                                   rtl=False if numeric and not header else None)  # fmt: skip
            self.y = top - height
            self.ops.append(
                f"{_rgb(GRID)} RG 0.5 w {MARGIN:.2f} {self.y:.2f} m {PAGE_W - MARGIN:.2f} {self.y:.2f} l S"
            )

        self.ensure(line_h * 3)
        draw_row([c["label"] for c in columns], True)
        for r in rows:
            draw_row([self.labels["missing"] if v is None else str(v) for v in r], False)
        self.y -= 6
        if note:
            self.paragraph(note, 8, color=MUTED)
        self.y -= 4

    # ------------------------------------------------------------------ charts

    def _poly(self, points: list[tuple[float, float]], color, width: float = 1.6) -> None:
        if len(points) < 2:
            return
        path = " ".join(
            f"{x:.2f} {y:.2f} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(points)
        )
        self.ops.append(f"{_rgb(color)} RG {width} w 1 J 1 j {path} S")

    def _dot(self, x: float, y: float, color, r: float = 2.0) -> None:
        k = 0.5523 * r
        self.ops.append(
            f"{_rgb(color)} rg {x + r:.2f} {y:.2f} m {x + r:.2f} {y + k:.2f} {x + k:.2f} {y + r:.2f} {x:.2f} {y + r:.2f} c "
            f"{x - k:.2f} {y + r:.2f} {x - r:.2f} {y + k:.2f} {x - r:.2f} {y:.2f} c "
            f"{x - r:.2f} {y - k:.2f} {x - k:.2f} {y - r:.2f} {x:.2f} {y - r:.2f} c "
            f"{x + k:.2f} {y - r:.2f} {x + r:.2f} {y - k:.2f} {x + r:.2f} {y:.2f} c f"
        )

    def _legend(
        self, entries: list[tuple[str, tuple[float, float, float]]], size: float = 8
    ) -> None:
        if len(entries) < 2:
            return
        self.ensure(size * 1.6)
        self.y -= size * 1.6
        x = PAGE_W - MARGIN if self.rtl else MARGIN
        for label, color in entries:
            w = self.measure(label, size) + 16
            if self.rtl:
                self.ops.append(f"{_rgb(color)} rg {x - 8:.2f} {self.y + 1:.2f} 7 7 re f")
                self.line_text(label, x - w, w - 12, self.y + 1, size, color=MUTED, align="right")
                x -= w + 10
            else:
                self.ops.append(f"{_rgb(color)} rg {x:.2f} {self.y + 1:.2f} 7 7 re f")
                self.line_text(label, x + 11, w, self.y + 1, size, color=MUTED, align="left")
                x += w + 10

    def chart(
        self, title: str, table: dict[str, Any], chart: dict[str, Any], note: str | None
    ) -> None:
        kind = chart["type"]
        rows = table["rows"]
        language = "ar" if self.rtl else "en"
        series = chart.get("series") or []
        unit = chart.get("unit")
        unit_label = (
            f" ({unit['label_ar' if self.rtl else 'label_en']})"
            if unit and kind != "scatter"
            else ""
        )
        by_category = (
            kind == "bar"
            and len(series) == 1
            and not any(c["key"] == chart["x"] and c["kind"] == "period" for c in table["columns"])
        )
        if by_category:
            height = min(190.0, 18.0 * len(rows) + 6)
        elif kind == "pie":
            height = max(150.0, 14.0 * len(rows) + 20)
        else:
            height = 190.0
        self.ensure(height + 50)
        self.paragraph(title + unit_label, 10, bold=True, gap=4)
        top = self.y
        bottom = top - height
        label_of = {c["key"]: c["label"][language] for c in table["columns"]}
        if kind == "pie" and series:
            self._pie(rows, chart, series[0], top, min(height, 150.0))
        elif kind == "scatter" and series:
            self._scatter(rows, chart, series[0], top, bottom, label_of)
        elif by_category:
            self._hbars(rows, chart, series[0], top, height)
        elif kind in ("line", "bar"):
            self._xy(rows, chart, series, top, bottom, columns=kind == "bar")
        self.y = bottom - 14
        if kind in ("line", "bar") and len(series) > 1:
            self._legend(
                [(s["label"][language], PALETTE[i % len(PALETTE)]) for i, s in enumerate(series)]
            )
        if note:
            self.paragraph(note, 8, color=MUTED)
        self.y -= 8

    def _xy(self, rows, chart, series, top, bottom, columns: bool) -> None:  # noqa: ANN001
        values = [v for s in series for r in rows if (v := _num(r.get(s["column"]))) is not None]
        if not values:
            return
        lo, hi, ticks = _scale(values)
        axis_w = 40.0
        left, right = (
            (MARGIN, PAGE_W - MARGIN - axis_w) if self.rtl else (MARGIN + axis_w, PAGE_W - MARGIN)
        )
        plot_bottom = bottom + 16

        def y_at(v: float) -> float:
            return plot_bottom + (v - lo) / ((hi - lo) or 1) * (top - plot_bottom)

        for tick in ticks:
            y = y_at(tick)
            self.ops.append(
                f"{_rgb(GRID)} RG {1.0 if tick == 0 else 0.5} w {left:.2f} {y:.2f} m {right:.2f} {y:.2f} l S"
            )
            label_x = right + 4 if self.rtl else MARGIN
            self.line_text(_tick(tick), label_x, axis_w - 6, y - 2.5, 7, color=MUTED,
                           align="left" if self.rtl else "right", rtl=False)  # fmt: skip
        n = max(1, len(rows))
        slot = (right - left) / n

        def x_center(i: int) -> float:
            offset = (i + 0.5) * slot if columns or n == 1 else i / (n - 1) * (right - left)
            return right - offset if self.rtl else left + offset

        every = max(1, math.ceil(n / 10))
        for i, r in enumerate(rows):
            if i % every == 0 or i == n - 1:
                label = str(r.get(chart["x"]) or "")
                self.line_text(
                    label,
                    x_center(i) - slot / 2 - 20,
                    slot + 40,
                    bottom + 4,
                    7,
                    color=MUTED,
                    align="center",
                )
        if columns:
            bar_w = max(1.5, slot * 0.72 / max(1, len(series)))
            for si, s in enumerate(series):
                color = PALETTE[si % len(PALETTE)]
                for i, r in enumerate(rows):
                    v = _num(r.get(s["column"]))
                    if v is None:
                        continue
                    offset = i * slot + slot * 0.14 + si * bar_w
                    x = right - offset - bar_w if self.rtl else left + offset
                    y0, y1 = sorted((y_at(0), y_at(v)))
                    fill = PALETTE[2] if v < 0 else color
                    self.ops.append(
                        f"{_rgb(fill)} rg {x:.2f} {y0:.2f} {bar_w:.2f} {max(0.8, y1 - y0):.2f} re f"
                    )
        else:
            for si, s in enumerate(series):
                color = PALETTE[si % len(PALETTE)]
                segment: list[tuple[float, float]] = []
                for i, r in enumerate(rows):
                    v = _num(r.get(s["column"]))
                    if v is None:  # a missing value breaks the line
                        self._poly(segment, color)
                        segment = []
                        continue
                    point = (x_center(i), y_at(v))
                    segment.append(point)
                    self._dot(*point, color)
                self._poly(segment, color)

    def _hbars(self, rows, chart, s, top, height) -> None:  # noqa: ANN001
        values = [_num(r.get(s["column"])) for r in rows]
        biggest = max([abs(v) for v in values if v is not None] or [1.0]) or 1.0
        row_h = min(18.0, height / max(1, len(rows)))
        label_w, value_w = 110.0, 70.0
        bar_w = BODY - label_w - value_w - 12
        for i, r in enumerate(rows):
            y = top - (i + 1) * row_h + 4
            v = values[i]
            label = str(r.get(chart["x"]) or "")
            raw = r.get(s["column"])
            if self.rtl:
                self.line_text(label, PAGE_W - MARGIN - label_w, label_w, y, 8, align="start")
                bar_right = PAGE_W - MARGIN - label_w - 6
                if v is not None:
                    w = abs(v) / biggest * bar_w
                    self.ops.append(
                        f"{_rgb(PALETTE[2] if v < 0 else PALETTE[0])} rg {bar_right - w:.2f} {y - 1:.2f} {w:.2f} {row_h * 0.6:.2f} re f"
                    )
                self.line_text(
                    raw or self.labels["missing"],
                    MARGIN,
                    value_w,
                    y,
                    8,
                    color=MUTED,
                    align="left",
                    rtl=False,
                )
            else:
                self.line_text(label, MARGIN, label_w, y, 8, align="start")
                if v is not None:
                    w = abs(v) / biggest * bar_w
                    self.ops.append(
                        f"{_rgb(PALETTE[2] if v < 0 else PALETTE[0])} rg {MARGIN + label_w + 6:.2f} {y - 1:.2f} {w:.2f} {row_h * 0.6:.2f} re f"
                    )
                self.line_text(
                    raw or self.labels["missing"],
                    PAGE_W - MARGIN - value_w,
                    value_w,
                    y,
                    8,
                    color=MUTED,
                    align="right",
                    rtl=False,
                )

    def _arc(self, cx: float, cy: float, r: float, a0: float, a1: float, first: bool) -> str:
        parts = []
        steps = max(1, math.ceil(abs(a1 - a0) / (math.pi / 2)))
        delta = (a1 - a0) / steps
        k = 4 / 3 * math.tan(delta / 4)
        for i in range(steps):
            s, e = a0 + i * delta, a0 + (i + 1) * delta
            p0 = (cx + r * math.cos(s), cy + r * math.sin(s))
            p3 = (cx + r * math.cos(e), cy + r * math.sin(e))
            p1 = (p0[0] - k * r * math.sin(s), p0[1] + k * r * math.cos(s))
            p2 = (p3[0] + k * r * math.sin(e), p3[1] - k * r * math.cos(e))
            if i == 0:
                parts.append(f"{p0[0]:.2f} {p0[1]:.2f} {'m' if first else 'l'}")
            parts.append(
                f"{p1[0]:.2f} {p1[1]:.2f} {p2[0]:.2f} {p2[1]:.2f} {p3[0]:.2f} {p3[1]:.2f} c"
            )
        return " ".join(parts)

    def _pie(self, rows, chart, s, top, height) -> None:  # noqa: ANN001
        values = [_num(r.get(s["column"])) for r in rows]
        total = sum(v for v in values if v and v > 0)
        if total <= 0:
            return
        r_out, r_in = height / 2 - 6, height / 2 - 34
        cx = PAGE_W - MARGIN - r_out - 4 if self.rtl else MARGIN + r_out + 4
        cy = top - height / 2
        angle = math.pi / 2
        legend_y = top - 12
        for i, row in enumerate(rows):
            v = values[i]
            if not v or v <= 0:
                continue
            sweep = v / total * 2 * math.pi
            color = PALETTE[i % len(PALETTE)]
            end = angle - sweep
            path = (
                self._arc(cx, cy, r_out, angle, end, True)
                + " "
                + self._arc(cx, cy, r_in, end, angle, False)
            )
            self.ops.append(f"{_rgb(color)} rg 1 1 1 RG 1 w {path} h B")
            angle = end
            label = f"{row.get(chart['x']) or ''}: {row.get(s['column'])} · {v / total * 100:.1f}%"
            if self.rtl:
                self.ops.append(f"{_rgb(color)} rg {cx - r_out - 30:.2f} {legend_y:.2f} 7 7 re f")
                self.line_text(
                    label, MARGIN, cx - r_out - 40 - MARGIN, legend_y, 8.5, align="start"
                )
            else:
                self.ops.append(f"{_rgb(color)} rg {cx + r_out + 24:.2f} {legend_y:.2f} 7 7 re f")
                self.line_text(
                    label,
                    cx + r_out + 36,
                    PAGE_W - MARGIN - cx - r_out - 36,
                    legend_y,
                    8.5,
                    align="start",
                    rtl=False,
                )
            legend_y -= 14

    def _scatter(self, rows, chart, s, top, bottom, label_of) -> None:  # noqa: ANN001
        points = [
            (x, y)
            for r in rows
            if (x := _num(r.get(chart["x"]))) is not None
            and (y := _num(r.get(s["column"]))) is not None
        ]
        if not points:
            return
        xlo, xhi, xticks = _range_scale([p[0] for p in points])
        ylo, yhi, yticks = _range_scale([p[1] for p in points])
        left, right, plot_bottom = MARGIN + 40, PAGE_W - MARGIN, bottom + 26

        def at(x: float, y: float) -> tuple[float, float]:
            return (left + (x - xlo) / ((xhi - xlo) or 1) * (right - left),
                    plot_bottom + (y - ylo) / ((yhi - ylo) or 1) * (top - plot_bottom))  # fmt: skip

        for tick in yticks:
            y = at(xlo, tick)[1]
            self.ops.append(f"{_rgb(GRID)} RG 0.5 w {left:.2f} {y:.2f} m {right:.2f} {y:.2f} l S")
            self.line_text(
                _tick(tick), MARGIN, 34, y - 2.5, 7, color=MUTED, align="right", rtl=False
            )
        for tick in xticks:
            x = at(tick, ylo)[0]
            self.line_text(
                _tick(tick), x - 30, 60, plot_bottom - 12, 7, color=MUTED, align="center", rtl=False
            )
        self.line_text(
            label_of.get(chart["x"], ""),
            left,
            right - left,
            bottom,
            7.5,
            color=MUTED,
            align="center",
        )
        for x, y in points:
            self._dot(*at(x, y), PALETTE[1], 2.2)

    # ------------------------------------------------------------------ assembly

    def footer(self, title: str) -> None:
        """The title and "page n of total" at the foot of every page (drawn last)."""
        total = len(self.pages)
        for n in range(total):
            self.current = n
            self.ops.append(
                f"{_rgb(GRID)} RG 0.5 w {MARGIN:.2f} {MARGIN + 12:.2f} m {PAGE_W - MARGIN:.2f} {MARGIN + 12:.2f} l S"
            )
            self.line_text(
                self.labels["page"].format(n=n + 1, total=total),
                MARGIN,
                BODY,
                MARGIN,
                7.5,
                color=MUTED,
                align="end",
            )
            self.line_text(
                title[:90],
                MARGIN + (BODY / 2 if self.rtl else 0),
                BODY / 2,
                MARGIN,
                7.5,
                color=MUTED,
                align="start",
            )
        self.current = total - 1

    def build(self, title: str, language: str) -> bytes:
        font = self.font
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        def stream(data: bytes, extra: str = "") -> bytes:
            packed = zlib.compress(data, 9)
            return (
                f"<< /Length {len(packed)} /Filter /FlateDecode{extra} >>\nstream\n".encode()
                + packed
                + b"\nendstream"
            )

        catalog = add(b"")  # filled in at the end
        pages_id = add(b"")
        subset = font.subset(set(self.used))
        file_id = add(stream(subset, f" /Length1 {len(subset)}"))
        scale = 1000 / font.units_per_em
        bbox = " ".join(str(round(v * scale)) for v in font.bbox)
        descriptor = add(
            f"<< /Type /FontDescriptor /FontName /{font.name} /Flags 32 /FontBBox [{bbox}] "
            f"/ItalicAngle {font.italic_angle:.1f} /Ascent {round(font.ascent * scale)} "
            f"/Descent {round(font.descent * scale)} /CapHeight {round(font.cap_height * scale)} "
            f"/StemV 80 /FontFile2 {file_id} 0 R >>".encode()
        )
        widths = " ".join(f"{g} [{round(font.advance(g) * scale)}]" for g in sorted(self.used))
        cid = add(
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{font.name} "
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {descriptor} 0 R /W [{widths}] /DW 500 /CIDToGIDMap /Identity >>".encode()
        )
        entries = [(g, t) for g, t in sorted(self.used.items()) if t]
        cmap = [
            "/CIDInit /ProcSet findresource begin 12 dict begin begincmap",
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
            "/CMapName /Adobe-Identity-UCS def /CMapType 2 def",
            "1 begincodespacerange <0000> <FFFF> endcodespacerange",
        ]
        for i in range(0, len(entries), 100):
            chunk = entries[i : i + 100]
            cmap.append(f"{len(chunk)} beginbfchar")
            cmap += [f"<{g:04X}> <{t.encode('utf-16-be').hex().upper()}>" for g, t in chunk]
            cmap.append("endbfchar")
        cmap.append("endcmap CMapName currentdict /CMap defineresource pop end end")
        to_unicode = add(stream("\n".join(cmap).encode()))
        font_id = add(
            f"<< /Type /Font /Subtype /Type0 /BaseFont /{font.name} /Encoding /Identity-H "
            f"/DescendantFonts [{cid} 0 R] /ToUnicode {to_unicode} 0 R >>".encode()
        )
        page_ids = []
        for ops, links in zip(self.pages, self.links, strict=True):
            content = add(stream("\n".join(ops).encode()))
            annots = ""
            if links:
                ids = []
                for (x0, y0, x1, y1), url in links:
                    safe = url.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                    ids.append(add(
                        f"<< /Type /Annot /Subtype /Link /Rect [{x0:.2f} {y0:.2f} {x1:.2f} {y1:.2f}] "
                        f"/Border [0 0 0] /A << /S /URI /URI ({safe}) >> >>".encode()
                    ))  # fmt: skip
                annots = " /Annots [" + " ".join(f"{i} 0 R" for i in ids) + "]"
            page_ids.append(add(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content} 0 R{annots} >>".encode()
            ))  # fmt: skip
        objects[pages_id - 1] = (
            f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>".encode()
        )
        direction = (
            " /ViewerPreferences << /DisplayDocTitle true /Direction /R2L >>"
            if self.rtl
            else " /ViewerPreferences << /DisplayDocTitle true >>"
        )
        objects[catalog - 1] = (
            f"<< /Type /Catalog /Pages {pages_id} 0 R /Lang ({language}){direction} >>".encode()
        )
        stamp = datetime.now(UTC).strftime("D:%Y%m%d%H%M%SZ")
        info = add(
            f"<< /Title {_pdf_string(title)} /Producer (OSRIP) /Creator (OSRIP) /CreationDate ({stamp}) >>".encode()
        )
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
        out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
        out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


def render(document: Document, font: Font) -> bytes:
    """The report as a PDF file."""
    w = _Writer(font, document.language)
    language = document.language
    w.paragraph(document.title, 18, bold=True, color=ACCENT, gap=2)
    if document.subtitle:
        w.paragraph(document.subtitle, 10, color=MUTED, gap=2)
    for label, value in document.meta:
        w.paragraph(f"{label}: {value}", 8.5, color=MUTED, gap=0)
    w.y -= 6
    w.rule(ACCENT, 1.2)
    w.y -= 10
    for section in document.sections:
        w.ensure(60)
        w.paragraph(section.heading, 13, bold=True, color=ACCENT, gap=4)
        for block in section.blocks:
            if block.type == "paragraph":
                w.paragraph(
                    block.text, 8.5 if block.note else 10, color=MUTED if block.note else INK
                )
            elif block.type == "bullets":
                w.bullets(block.items)
            elif block.type == "table":
                w.table(
                    block.title, [c.model_dump() for c in block.columns], block.rows, block.note
                )
            else:
                w.chart(
                    block.title,
                    block.table.model_dump(mode="json"),
                    block.chart.model_dump(mode="json"),
                    block.note,
                )
        w.y -= 6
    if document.references:
        w.ensure(60)
        w.paragraph(
            "المراجع" if language == "ar" else "References", 13, bold=True, color=ACCENT, gap=4
        )
        for n, ref in enumerate(document.references, start=1):
            parts = [ref.title, ref.publisher, ref.published, ref.note]
            line = f"{n}. " + " · ".join(p for p in parts if p)
            w.paragraph(line, 9, gap=1)
            if ref.url:
                w.ensure(12)
                w.y -= 11
                x0 = MARGIN + 14 if not w.rtl else MARGIN
                width = w.line_text(
                    ref.url, x0, BODY - 14, w.y + 2, 8, color=ACCENT, align="start", rtl=False
                )
                if ref.url.startswith(("https://", "http://")):
                    start = x0 if not w.rtl else MARGIN + BODY - 14 - width
                    w.links[-1].append(((start, w.y, start + width, w.y + 10), ref.url))
            if ref.retrieved:
                w.paragraph(ref.retrieved, 8, color=MUTED, gap=4)
    if document.notice:
        w.y -= 6
        w.paragraph(document.notice, 8, color=MUTED)
    w.footer(document.title)
    return w.build(document.title, language)
