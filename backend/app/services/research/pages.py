"""Turning a fetched HTML page into plain text plus its dates. Pure: no I/O.

Only text is kept; scripts, styles, forms and embedded content are dropped. The text
is evidence to quote, never instructions (the assistant is told so).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser

SKIP = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "object",
    "form",
    "button",
    "select",
}
BLOCK = {
    "p",
    "div",
    "li",
    "tr",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "section",
    "article",
    "td",
    "th",
    "table",
    "ul",
    "ol",
}
DATE_META = (
    "article:published_time",
    "og:published_time",
    "datepublished",
    "dc.date",
    "dc.date.issued",
    "dcterms.issued",
    "publication_date",
    "pubdate",
    "date",
    "citation_publication_date",
    "article:modified_time",
)
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


@dataclass
class Page:
    title: str = ""
    text: str = ""
    published: str | None = None  # ISO date when the page states one
    meta: dict[str, str] = field(default_factory=dict)


class _Extractor(HTMLParser):
    """Text in reading order. Table rows are kept as one line each, cells joined by " | "
    and prefixed with the table caption, so a figure stays next to its row and column
    labels instead of being scattered over separate lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title: list[str] = []
        self.parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.table_depth = 0
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.caption: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP:
            self.skip_depth += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            a = {k.lower(): (v or "") for k, v in attrs}
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"][:200])
        elif tag == "time":
            a = {k.lower(): (v or "") for k, v in attrs}
            if a.get("datetime"):
                self.meta.setdefault("time", a["datetime"][:40])
        elif tag == "table":
            self.table_depth += 1
            self.parts.append("\n")
        elif tag == "caption" and self.table_depth:
            self.caption = []
        elif tag == "tr" and self.table_depth:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        if tag in BLOCK and self.cell is None and tag not in ("tr", "table"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self.in_title = False
        elif tag == "caption" and self.caption is not None:
            text = " ".join("".join(self.caption).split())
            if text:
                self.parts.append(f"\nTable: {text}\n")
            self.caption = None
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            cells = [c for c in self.row if c]
            if cells:
                self.parts.append("\n" + " | ".join(cells) + "\n")
            self.row = None
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1
            self.parts.append("\n")
        if tag in BLOCK and self.cell is None and tag not in ("tr", "td", "th", "table"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title.append(data)
        elif self.caption is not None:
            self.caption.append(data)
        elif self.cell is not None:
            self.cell.append(data)
        else:
            self.parts.append(data)


def first_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    m = _ISO_DATE.search(value)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def extract(html: str, *, max_chars: int = 60_000) -> Page:
    parser = _Extractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001, S110 - malformed markup: keep what was parsed
        pass
    text = "".join(parser.parts)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    published = None
    for key in (*DATE_META, "time"):
        published = first_iso_date(parser.meta.get(key))
        if published:
            break
    return Page(
        title=re.sub(r"\s+", " ", "".join(parser.title)).strip()[:300],
        text=text[:max_chars],
        published=published,
        meta=parser.meta,
    )


class PdfUnavailable(Exception):
    """PDF text extraction needs the optional ``pypdf`` package, which is not installed."""


def extract_pdf(data: bytes, *, max_pages: int = 40, max_chars: int = 60_000) -> Page:
    """Text of a PDF (statistical bulletins are often PDFs), page by page. Needs the
    optional ``pypdf`` package; without it ``PdfUnavailable`` is raised and reported."""
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError as exc:
        raise PdfUnavailable from exc
    import io

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for number, page in enumerate(reader.pages[:max_pages], start=1):
        text = page.extract_text() or ""
        parts.append(f"\n[page {number}]\n{text}")
        if sum(len(p) for p in parts) > max_chars:
            break
    meta = reader.metadata or {}
    raw_date = str(meta.get("/CreationDate", "") or "")
    published = None
    if raw_date.startswith("D:") and len(raw_date) >= 10:
        published = first_iso_date(f"{raw_date[2:6]}-{raw_date[6:8]}-{raw_date[8:10]}")
    return Page(
        title=str(meta.get("/Title", "") or "")[:300],
        text="".join(parts)[:max_chars],
        published=published,
    )


def excerpt_pages(text: str, excerpt: str) -> list[int]:
    """The PDF page numbers ("[page N]" markers in ``text``) that the excerpt's lines come
    from, so a quoted figure can be found again in the document."""
    page_of: dict[str, int] = {}
    current = 0
    for line in (ln.strip() for ln in text.split("\n")):
        marker = re.fullmatch(r"\[page (\d+)\]", line)
        if marker:
            current = int(marker.group(1))
        elif line and current:
            page_of.setdefault(line[:600], current)
    found = {page_of[ln] for ln in excerpt.split("\n") if ln in page_of}
    return sorted(found)


def relevant_passages(text: str, terms: list[str], *, limit: int = 6000) -> str:
    """Lines that mention a query term or contain a number, in page order, up to
    ``limit`` characters; the page start is used when nothing matches."""
    lowered = [t.lower() for t in terms if len(t) > 2]
    lines = []
    for ln in (ln.strip() for ln in text.split("\n")):
        if len(ln) <= 600:
            lines += [ln] if ln else []
        else:  # a long paragraph: its sentences, so a figure late in it is not cut off
            lines += [x.strip() for x in re.split(r"(?<=[.!?؟])\s+", ln) if x.strip()]
    picked: list[str] = []
    size = 0
    for line in lines:
        low = line.lower()
        if (lowered and any(t in low for t in lowered)) or (
            re.search(r"\d", line) and len(line) > 25
        ):
            picked.append(line[:600])
            size += len(picked[-1]) + 1
            if size >= limit:
                break
    if not picked:
        return text[:limit]
    return "\n".join(picked)[:limit]
