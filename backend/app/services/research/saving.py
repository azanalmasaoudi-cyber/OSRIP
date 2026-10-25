"""Figures read from official documents: backend validation, and saving the ones it can check.

The model proposes; this module decides. A submitted figure is saved automatically only when
every check passes:
1. it cites a document read in full in this answer or job (``read_web_page``: a stored
   ``research_document`` with its text), never a search snippet or a search summary;
2. that document's address is an official Omani source (``sources.OFFICIAL``);
3. the value as written appears in the document's text (digits and separators normalised),
   and the passage around it is kept as the supporting excerpt;
4. the indicator and area are platform codes; the unit is one the indicator is already
   published in (or its display unit), so nothing is rescaled; the period's dates match its
   kind (a calendar month, quarter or year, or January to a month end for a year-to-date
   total), start in 2022 or later and ended by the date the document was read;
5. it is not already published (same series, period and value at the precision both give:
   "duplicate", skipped) and it does not conflict with a published figure or another
   submission (a different value, or the period published in another unit: "conflict", kept
   for a reviewer and never written over);
6. automatic saving is switched on (``OSRIP_RESEARCH_AUTO_SAVE``).
Anything uncertain is stored as "pending" with its reasons; a figure that can never be saved
(not from a read document, a value missing from the text, impossible dates) is "rejected".
A model's confidence is never a check, and pending figures are not observations: charts,
summaries and answers cannot use them until a reviewer approves them.

Saving goes through the import workflow, as the official feeds do: per document, a source is
registered (publisher, title, address, publication date, retrieval date), the figures are
staged as one import, validated by the same rules as any import, approved and published by
the research service account, all or nothing. Nothing published is replaced: a revision is a
new observation with its own source. A figure is "approved" (saved) only after that
publication commits, with the observation it became. Saves are serialised by an advisory
lock, and the same figure from the same document is submitted once (a unique index), so a
repeated run creates no duplicate.
"""

from __future__ import annotations

import calendar
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import DataMode, DatasetVersionStatus, Permission, Role
from app.models import (
    AppUser,
    Area,
    DatasetVersion,
    Indicator,
    Observation,
    ResearchCandidate,
    ResearchDocument,
    Unit,
)
from app.services import accounts, audit
from app.services.imports import workflow
from app.services.principal import Principal
from app.services.research import sources
from app.services.sync.ncsi_msb import Record
from app.services.sync.service import records_csv, same_figure

RESEARCH_EMAIL = "research-assistant@osrip.invalid"
SYSTEM = Principal(user_id=None, label="system:research")
SCOPE_START = date(2022, 1, 1)
KINDS = ("monthly", "quarterly", "annual", "year_to_date")
SCALES = ("one", "thousand", "million", "billion")
SECTIONS = ("electricity", "water", "food_security", "trade")
LICENCE = (
    "Official statistics published by the source named; cited with attribution as the "
    "publisher's terms allow (Open Government License - Sultanate of Oman for NCSI)."
)
EXCERPT_CHARS = 300

# Unit as written (lower case, scale folded in) -> platform unit code. Only units the platform
# already has; anything else is "not mapped" and waits for a reviewer.
UNIT_WORDS: dict[str, str] = {
    "gwh": "GWh", "gigawatt hours": "GWh", "gigawatt-hours": "GWh", "gigawatt hour": "GWh",
    "جيجاواط ساعة": "GWh", "غيغاواط ساعة": "GWh", "جيجا واط ساعة": "GWh", "ج.و.س": "GWh",
    "mw": "MW", "megawatts": "MW", "megawatt": "MW", "ميجاواط": "MW", "ميغاواط": "MW",
    "million m3": "million_m3", "million m³": "million_m3", "million cubic metres": "million_m3",
    "million cubic meters": "million_m3", "mcm": "million_m3", "مليون متر مكعب": "million_m3",
    "مليون م3": "million_m3", "مليون م³": "million_m3",
    "thousand m3": "thousand_m3", "thousand m³": "thousand_m3", "000 m3": "thousand_m3",
    "thousand cubic metres": "thousand_m3", "thousand cubic meters": "thousand_m3",
    "ألف متر مكعب": "thousand_m3", "ألف م3": "thousand_m3", "ألف م³": "thousand_m3",
    "tonne": "tonne", "tonnes": "tonne", "ton": "tonne", "tons": "tonne", "طن": "tonne",
    "thousand tonnes": "thousand_tonnes", "ألف طن": "thousand_tonnes",
    "million tonnes": "million_tonnes", "مليون طن": "million_tonnes",
    "omr": "OMR", "rial omani": "OMR", "ريال عماني": "OMR", "ر.ع": "OMR",
    "million omr": "million_OMR", "omr million": "million_OMR", "million rial omani": "million_OMR",
    "مليون ريال عماني": "million_OMR", "مليون ر.ع": "million_OMR",
    "thousand omr": "thousand_OMR", "omr thousand": "thousand_OMR", "ألف ريال عماني": "thousand_OMR",
    "percent": "percent", "%": "percent", "per cent": "percent", "٪": "percent",
}  # fmt: skip
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_NUMBER_IN_TEXT = re.compile(
    r"(?<![\d.])\d{1,3}(?:[,٬  ]\d{3})+(?:\.\d+)?(?![\d])|(?<![\d.])\d+(?:\.\d+)?(?![\d])"
)


@dataclass(slots=True)
class Outcome:
    ref: int
    status: str  # approved | duplicate | conflict | pending | rejected
    reasons: list[str] = field(default_factory=list)
    candidate_id: uuid.UUID | None = None
    observation_id: uuid.UUID | None = None
    dataset_version: str | None = None
    already_submitted: bool = False
    figure: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "status": self.status,
            "saved": self.status == "approved",
            "reasons": self.reasons,
            "candidate_id": str(self.candidate_id) if self.candidate_id else None,
            "observation_id": str(self.observation_id) if self.observation_id else None,
            "dataset_version": self.dataset_version,
            "already_submitted": self.already_submitted,
            **self.figure,
        }


# ------------------------------------------------------------------ pure checks


def number_text(text: str) -> Decimal | None:
    cleaned = text.translate(_DIGITS).strip()
    cleaned = re.sub(r"(?<=\d)[,٬  ](?=\d{3}\b)", "", cleaned)
    m = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not m:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def find_value(document_text: str, value: Decimal, value_text: str) -> str | None:
    """The passage of the document where the value is written (the value as a whole number
    token, separators and Arabic digits normalised), or None if the text never states it."""
    text = document_text.translate(_DIGITS)
    for m in _NUMBER_IN_TEXT.finditer(text):
        written = re.sub(r"[,٬  ]", "", m.group(0))
        try:
            found = Decimal(written)
        except InvalidOperation:
            continue
        if found == value and _same_digits(written, value_text):
            start, end = max(0, m.start() - EXCERPT_CHARS), min(len(text), m.end() + EXCERPT_CHARS)
            return document_text[start:end].strip()
    return None


def _same_digits(written: str, value_text: str) -> bool:
    """The figure as the model copied it has the same digits as on the page (49,132.0 is
    49132.0, not 49132)."""
    copied = re.sub(r"[,٬  ]", "", value_text.translate(_DIGITS).strip())
    return copied == written


def unit_code(unit: str, scale: str | None) -> str | None:
    words = " ".join(unit.lower().replace("³", "³").split())
    words = re.sub(r"\s*\(.*?\)\s*", " ", words).strip()
    if scale in ("thousand", "million", "billion") and not words.startswith(scale):
        candidates = [f"{scale} {words}", words]
    else:
        candidates = [words]
    for w in candidates:
        if w in UNIT_WORDS:
            return UNIT_WORDS[w]
    return None


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def period_problems(kind: str, start: date, end: date, read_on: date) -> list[str]:
    out = []
    if kind == "monthly":
        if start.day != 1 or end != _month_end(start.year, start.month):
            out.append("period_not_one_month")
    elif kind == "quarterly":
        if start.day != 1 or start.month not in (1, 4, 7, 10):
            out.append("period_not_a_quarter")
        elif end != _month_end(start.year, start.month + 2):
            out.append("period_not_a_quarter")
    elif kind == "annual":
        if (start.month, start.day) != (1, 1) or end != date(start.year, 12, 31):
            out.append("period_not_a_calendar_year")
    elif kind == "year_to_date":
        if (start.month, start.day) != (1, 1) or end.year != start.year or end.month == 12:
            out.append("period_not_year_to_date")
        elif end != _month_end(end.year, end.month):
            out.append("period_not_year_to_date")
    else:
        out.append("unknown_period_kind")
    if start < SCOPE_START:
        out.append("before_2022")
    if end > read_on:
        out.append("period_not_ended_when_read")
    return out


def period_label(kind: str, start: date, end: date) -> str:
    if kind == "monthly":
        return start.strftime("%Y-%m")
    if kind == "quarterly":
        return f"{start.year} Q{(start.month - 1) // 3 + 1}"
    if kind == "annual":
        return str(start.year)
    return f"{start.strftime('%b')}–{end.strftime('%b %Y')} (year to date)"


def _iso(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


# ------------------------------------------------------------------ accounts and locking


def research_principal(session: Session) -> Principal:
    """The service account that stages and publishes figures validation has checked."""
    with session.begin():
        user = session.scalar(select(AppUser).where(AppUser.email == RESEARCH_EMAIL))
        if user is None:
            user = accounts.create_user(
                session,
                SYSTEM,
                email=RESEARCH_EMAIL,
                display_name="Research validation",
                password=None,
                roles=[Role.DATA_MANAGER],
                service_account=True,
            )
            session.flush()
            for permission in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
                accounts.grant_permission(session, SYSTEM, user.id, permission)
        session.flush()
        return accounts.load_principal(session, user)


@contextmanager
def save_lock(session: Session, wait_seconds: float = 30.0) -> Iterator[bool]:
    """One save at a time, across workers and requests (a PostgreSQL advisory lock held on
    its own connection), so two runs never stage the same figure."""
    bind = session.get_bind()
    with bind.connect() as conn:  # type: ignore[union-attr]
        key = conn.execute(select(func.hashtext("osrip.research.save"))).scalar_one()
        deadline = time.monotonic() + wait_seconds
        got = False
        while True:
            got = bool(conn.execute(select(func.pg_try_advisory_lock(key))).scalar_one())
            conn.commit()
            if got or time.monotonic() > deadline:
                break
            time.sleep(0.25)
        try:
            yield got
        finally:
            if got:
                conn.execute(select(func.pg_advisory_unlock(key)))
                conn.commit()


# ------------------------------------------------------------------ comparison with published data


def _published(
    session: Session, indicator: str, area: str, start: date, end: date, complete: bool
) -> list[tuple[str, Decimal]]:
    rows = session.execute(
        select(Unit.code, Observation.value)
        .join(Indicator, Indicator.id == Observation.indicator_id)
        .join(Area, Area.id == Observation.area_id)
        .join(Unit, Unit.id == Observation.unit_id)
        .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
        .where(
            Observation.data_mode == DataMode.VERIFIED_SOURCE,
            DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
            Indicator.code == indicator,
            Area.code == area,
            Observation.period_start == start,
            Observation.period_end == end,
            Observation.period_complete == complete,
            Observation.partner_id.is_(None),
            Observation.commodity_id.is_(None),
            Observation.flow.is_(None),
            Observation.value.is_not(None),
        )
    ).all()
    return [(u, v) for u, v in rows]


def _units_in_use(session: Session, indicator: Indicator) -> set[str]:
    used = set(
        session.scalars(
            select(Unit.code)
            .join(Observation, Observation.unit_id == Unit.id)
            .where(
                Observation.indicator_id == indicator.id,
                Observation.data_mode == DataMode.VERIFIED_SOURCE,
            )
            .distinct()
        )
    )
    if indicator.display_unit_code:
        used.add(indicator.display_unit_code)
    return used


def _relation(
    session: Session,
    indicator: str,
    area: str,
    start: date,
    end: date,
    complete: bool,
    unit: str,
    value: Decimal,
    exclude: uuid.UUID | None = None,
) -> tuple[str | None, list[str]]:
    """'duplicate', 'conflict', 'other_unit' or None, with reasons."""
    published = _published(session, indicator, area, start, end, complete)
    same_unit = [v for u, v in published if u == unit]
    if any(same_figure(v, value) for v in same_unit):
        return "duplicate", ["already_published"]
    if same_unit:
        shown = ", ".join(format(v, "f") for v in same_unit[:3])
        return "conflict", [f"differs_from_published:{shown}"]
    if published:
        return "other_unit", ["published_in_another_unit"]
    others = session.scalars(
        select(ResearchCandidate).where(
            ResearchCandidate.indicator_code == indicator,
            ResearchCandidate.area_code == area,
            ResearchCandidate.period_start == start,
            ResearchCandidate.period_end == end,
            ResearchCandidate.unit_code == unit,
            ResearchCandidate.status.in_(("pending", "conflict")),
            *([ResearchCandidate.id != exclude] if exclude else []),
        )
    ).all()
    if any(not same_figure(o.value, value) for o in others):
        return "conflict", ["differs_from_another_submission"]
    return None, []


# ------------------------------------------------------------------ submission


def _entry(status: str, reasons: list[str], by: str) -> dict[str, Any]:
    return {
        "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "status": status,
        "by": by,
        "reasons": reasons,
    }


@dataclass(slots=True)
class _Checked:
    ref: int
    status: str
    reasons: list[str]
    values: dict[str, Any] | None  # the candidate row, None when it cannot be stored
    record: Record | None = None
    document: ResearchDocument | None = None


def _check(
    session: Session, ref: int, r: dict[str, Any], by_id: dict[str, dict[str, Any]], language: str
) -> _Checked:
    s = get_settings()
    reasons: list[str] = []
    ev = by_id.get(str(r.get("evidence_id", "")))
    if not ev or ev.get("kind") != "web":
        return _Checked(ref, "rejected", ["evidence_is_not_a_web_document"], None)
    if ev.get("content_kind") not in ("page_excerpt", "pdf_excerpt"):
        # A search result whose page was read in this answer: the read copy is the evidence.
        read = [
            i
            for i in by_id.values()
            if i.get("kind") == "web"
            and i.get("content_kind") in ("page_excerpt", "pdf_excerpt")
            and i.get("document_id")
            and ev.get("url") in (i.get("url"), i.get("requested_url"))
        ]
        if read:
            ev = read[-1]
    if ev.get("content_kind") not in ("page_excerpt", "pdf_excerpt") or not ev.get("document_id"):
        return _Checked(ref, "rejected", ["read_the_document_first_not_a_search_result"], None)
    doc = session.get(ResearchDocument, uuid.UUID(str(ev["document_id"])))
    if doc is None or doc.status != "ok" or not doc.text_content:
        return _Checked(ref, "rejected", ["document_text_not_stored"], None)
    value_text = str(r.get("value_text", "")).strip()[:60]
    value = number_text(value_text)
    if value is None:
        return _Checked(ref, "rejected", ["value_text_is_not_a_number"], None)
    excerpt = find_value(doc.text_content, value, value_text)
    if excerpt is None:
        return _Checked(ref, "rejected", ["value_not_in_document_text"], None)
    start, end = _iso(r.get("period_start")), _iso(r.get("period_end"))
    kind = str(r.get("period_kind", "")).strip()
    if start is None or end is None or end < start:
        return _Checked(ref, "rejected", ["period_dates_missing_or_reversed"], None)
    read_on = doc.retrieved_at.date()
    problems = period_problems(kind, start, end, read_on)
    if "before_2022" in problems or end < SCOPE_START:
        return _Checked(ref, "rejected", ["before_2022_outside_scope"], None)
    if problems:
        return _Checked(ref, "rejected", problems, None)
    indicator = session.scalar(
        select(Indicator).where(Indicator.code == str(r.get("indicator_code", "")))
    )
    area = session.scalar(select(Area).where(Area.code == str(r.get("area_code", "OM") or "OM")))
    scale = r.get("scale") if r.get("scale") in SCALES else None
    unit_written = str(r.get("unit", "")).strip()[:80] or "unspecified"
    unit = unit_code(unit_written, scale)
    if indicator is None:
        reasons.append("indicator_not_a_platform_code")
    if area is None:
        reasons.append("area_not_a_platform_code")
    if unit is None:
        reasons.append("unit_not_mapped")
    elif indicator is not None:
        in_use = _units_in_use(session, indicator)
        if not in_use:
            reasons.append("indicator_has_no_established_unit")
        elif unit not in in_use:
            reasons.append(f"unit_not_used_for_indicator:{','.join(sorted(in_use))}")
    cls = sources.classify(doc.final_url or doc.url)
    if cls["source_class"] != "official":
        reasons.append(f"source_not_official:{cls['source_class']}")
    complete = kind != "year_to_date"
    status = "approved"
    if not reasons and indicator is not None and area is not None and unit is not None:
        relation, why = _relation(
            session, indicator.code, area.code, start, end, complete, unit, value
        )
        if relation == "duplicate":
            status = "duplicate"
        elif relation == "conflict":
            status = "conflict"
        elif relation == "other_unit":
            status = "pending"
        reasons += why
    if reasons and status == "approved":
        status = "pending"
    if status == "approved" and not s.research_auto_save:
        status, reasons = "pending", ["automatic_saving_switched_off"]
    publication = _iso(r.get("publication_date")) or doc.published
    section = indicator.section.value if indicator is not None else "general"
    values = {
        "domain": section if section in SECTIONS else "general",
        "indicator": (
            str(r.get("indicator", "")).strip()
            or (indicator.name_en if indicator else "unspecified")
        )[:300],
        "indicator_code": indicator.code if indicator else None,
        "value": value,
        "value_text": value_text,
        "unit": unit_written,
        "unit_code": unit,
        "scale": scale,
        "geography": (area.name_en if area else str(r.get("area_code", "")) or "Oman")[:120],
        "area_code": area.code if area else None,
        "period_kind": kind,
        "period_label": period_label(kind, start, end),
        "period_start": start,
        "period_end": end,
        "publication_date": publication,
        "publisher": (doc.publisher or str(cls["host"]))[:300],
        "source_title": (doc.title or doc.url)[:500],
        "source_url": doc.final_url or doc.url,
        "source_class": str(cls["source_class"]),
        "excerpt": excerpt[:2000],
        "retrieved_at": doc.retrieved_at,
        "search_provider": str(ev.get("provider") or "unknown")[:40],
        "language": language if language in ("en", "ar") else "en",
        "document_id": doc.id,
        "validation": {"reasons": reasons, "checked_at": datetime.now(UTC).isoformat()},
    }
    record = None
    if status == "approved":
        assert indicator is not None and area is not None and unit is not None
        record = Record(
            indicator_code=indicator.code,
            area_code=area.code,
            period_start=start,
            period_end=end,
            frequency="annual" if kind == "year_to_date" else kind,
            period_complete=complete,
            unit_code=unit,
            value=value,
            revision_status=None,
            source_locator=f"research_document {doc.id}; passage: {excerpt[:180]}",
            record_ref="",
        )
    return _Checked(ref, status, reasons, values, record, doc)


def submit(
    session: Session,
    records: list[dict[str, Any]],
    ledger_items: list[dict[str, Any]],
    *,
    submitter: Principal,
    language: str,
    job_id: uuid.UUID | None = None,
) -> list[Outcome]:
    """Validate the proposed figures, store each as a candidate, and save the ones every check
    passed. ``session`` must have no open transaction (each step owns one)."""
    s = get_settings()
    if not submitter.is_authenticated or not submitter.has(Permission.RESEARCH_SUBMIT):
        return [Outcome(i, "rejected", ["not_permitted_to_submit"]) for i, _ in enumerate(records)]
    by_id = {i["id"]: i for i in ledger_items}
    outcomes: list[Outcome] = []
    ready: dict[uuid.UUID, list[tuple[uuid.UUID, Record]]] = {}
    documents: dict[uuid.UUID, ResearchDocument] = {}
    validator = research_principal(session)
    with save_lock(session) as locked:
        for ref, r in enumerate(records[: s.research_max_candidates_per_answer]):
            with session.begin():
                checked = _check(session, ref, r, by_id, language)
                if checked.values is None:
                    outcomes.append(Outcome(ref, checked.status, checked.reasons))
                    continue
                v = checked.values
                stored_status = "pending" if checked.status == "approved" else checked.status
                if checked.status == "approved" and not locked:
                    stored_status, checked.reasons = "pending", ["another_save_in_progress"]
                decided = stored_status in ("duplicate", "rejected")
                row = {
                    **v,
                    "status": stored_status,
                    "proposed_by": submitter.user_id,
                    "job_id": job_id,
                    "decided_by": "validation" if decided else None,
                    "reviewed_by": validator.user_id if decided else None,
                    "reviewed_at": datetime.now(UTC) if decided else None,
                    "history": [_entry(stored_status, checked.reasons, "validation")],
                }
                inserted = session.execute(
                    insert(ResearchCandidate).values(**row).on_conflict_do_nothing()
                    .returning(ResearchCandidate.id)
                ).scalar()  # fmt: skip
                figure = {
                    "indicator_code": v["indicator_code"],
                    "area_code": v["area_code"],
                    "period": v["period_label"],
                    "period_kind": v["period_kind"],
                    "value": format(v["value"], "f"),
                    "unit": v["unit_code"] or v["unit"],
                    "source_url": v["source_url"],
                    "publisher": v["publisher"],
                    "source_title": v["source_title"],
                    "publication_date": v["publication_date"].isoformat() if v["publication_date"] else None,
                    "retrieved_at": v["retrieved_at"].isoformat(),
                    "excerpt": v["excerpt"][:400],
                }  # fmt: skip
                if inserted is None:
                    existing = session.scalar(
                        select(ResearchCandidate).where(
                            ResearchCandidate.source_url == v["source_url"],
                            ResearchCandidate.indicator_code == v["indicator_code"],
                            ResearchCandidate.area_code == v["area_code"],
                            ResearchCandidate.period_kind == v["period_kind"],
                            ResearchCandidate.period_start == v["period_start"],
                            ResearchCandidate.period_end == v["period_end"],
                            ResearchCandidate.value == v["value"],
                        )
                    ) or session.scalar(
                        select(ResearchCandidate).where(
                            ResearchCandidate.source_url == v["source_url"],
                            func.lower(ResearchCandidate.indicator) == v["indicator"].lower(),
                            ResearchCandidate.period_label == v["period_label"],
                            ResearchCandidate.value == v["value"],
                        )
                    )
                    # Submitted before: nothing is saved now. A figure saved earlier is now
                    # "already published" (duplicate), with the record it became.
                    earlier = existing.status if existing else checked.status
                    outcomes.append(
                        Outcome(
                            ref,
                            "duplicate" if earlier in ("approved", "duplicate") else earlier,
                            ["submitted_before"],
                            existing.id if existing else None,
                            existing.observation_id if existing else None,
                            already_submitted=True,
                            figure=figure,
                        )
                    )
                    continue
                outcome = Outcome(ref, stored_status, checked.reasons, inserted, figure=figure)
                outcomes.append(outcome)
                if checked.status == "approved" and locked:
                    assert checked.record is not None and checked.document is not None
                    record = replace(checked.record, record_ref=f"rc-{inserted.hex[:16]}")
                    ready.setdefault(checked.document.id, []).append((inserted, record))
                    documents[checked.document.id] = checked.document
        for doc_id, items in ready.items():
            _save_document(session, validator, documents[doc_id], items, outcomes)
    return outcomes


def _save_document(
    session: Session,
    actor: Principal,
    doc: ResearchDocument,
    items: list[tuple[uuid.UUID, Record]],
    outcomes: list[Outcome],
    *,
    reviewer: Principal | None = None,
    note: str | None = None,
) -> None:
    """Stage, validate, approve and publish one document's checked figures as an ordinary
    import; mark the candidates saved only after the publication committed. With
    ``reviewer``, a person approved the figures: a figure that differs from a published one is
    then saved as a revision beside it (its own source), never in its place."""
    by = "reviewer" if reviewer is not None else "validation"
    by_candidate = {o.candidate_id: o for o in outcomes if o.candidate_id}
    # Checked again under the lock: a figure published meanwhile is a duplicate now.
    still: list[tuple[uuid.UUID, Record]] = []
    with session.begin():
        for cid, rec in items:
            relation, why = _relation(
                session, rec.indicator_code, rec.area_code, rec.period_start, rec.period_end,
                rec.period_complete, rec.unit_code, rec.value, exclude=cid,
            )  # fmt: skip
            if relation is None or (reviewer is not None and relation != "duplicate"):
                still.append((cid, rec))
                continue
            status = {"duplicate": "duplicate", "conflict": "conflict"}.get(relation, "pending")
            _decide(session, cid, status, why, reviewer or actor, by=by)
            by_candidate[cid].status, by_candidate[cid].reasons = status, why
    if not still:
        return
    is_pdf = "pdf" in (doc.content_type or "")
    try:
        source = workflow.register_source(
            session,
            actor,
            data_mode=DataMode.VERIFIED_SOURCE,
            dataset_title=f"{doc.title or doc.url} (read by OSRIP research)"[:300],
            publisher=doc.publisher or sources.host_of(doc.url),
            url=doc.final_url or doc.url,
            locator_kind="direct_file" if is_pdf else "web_page",
            access_date=doc.retrieved_at.date(),
            publication_date=doc.published,
            reference_period=", ".join(sorted({r.period_start.isoformat() for _, r in still}))[:200],
            geographic_coverage="Oman",
            definition_note=(
                "Figures read by the OSRIP research assistant from this document and checked "
                f"by {'a reviewer' if reviewer else 'backend validation'} against its text "
                f"(research_document {doc.id})."
            ),
            reuse_conditions=LICENCE,
            source_code=f"research-{doc.id.hex[:12]}",
            source_role="primary",
        )  # fmt: skip
        state = workflow.create_import(
            session,
            actor,
            source_id=source.id,
            version_label=f"research-{doc.id.hex[:8]}-{uuid.uuid4().hex[:6]}",
            filename="research.csv",
            data=records_csv([r for _, r in still]),
        )
        import_id = state.job.id
        state = workflow.validate_import(session, actor, import_id)
        if state.version.status is not DatasetVersionStatus.VALIDATED or (
            state.job.rejected_row_count or 0
        ):
            with session.begin():
                for cid, _ in still:
                    why = ["import_validation_rejected: a data manager reviews the staged import"]
                    _decide(
                        session, cid, "pending", why, actor, by="validation", import_id=import_id
                    )
                    by_candidate[cid].status, by_candidate[cid].reasons = "pending", why
            return
        workflow.approve_import(
            session,
            actor,
            import_id,
            acknowledged_rejected_rows=0,
            note=(
                f"Approved by a reviewer: {note}"[:2000]
                if reviewer is not None
                else "Saved automatically: every figure was found in the official document's "
                "text and passed OSRIP research validation."
            ),
        )
        workflow.publish_import(session, actor, import_id)
    except Exception as exc:  # noqa: BLE001 - nothing was saved: the candidates wait for review
        with session.begin():
            for cid, _ in still:
                why = [f"save_failed:{type(exc).__name__}"]
                _decide(session, cid, "pending", why, actor, by="validation")
                by_candidate[cid].status, by_candidate[cid].reasons = "pending", why
        return
    with session.begin():
        version = session.get(DatasetVersion, state.version.id)
        assert version is not None
        obs = {
            o.record_ref: o.id
            for o in session.scalars(
                select(Observation).where(Observation.dataset_version_id == version.id)
            )
        }
        for cid, rec in still:
            oid = obs.get(rec.record_ref)
            if oid is None:  # pragma: no cover - publication stores every validated row
                continue
            c = session.get(ResearchCandidate, cid, with_for_update=True)
            assert c is not None
            c.status, c.decided_by = "approved", by
            c.reviewed_by, c.reviewed_at = (reviewer or actor).user_id, datetime.now(UTC)
            c.observation_id, c.dataset_version_id, c.import_job_id = oid, version.id, import_id
            if note:
                c.review_note = note[:2000]
            c.history = [*c.history, _entry("approved", [], by)]
            audit.record(
                session, actor, "research.saved", entity_type="research_candidate",
                entity_id=c.id, metadata={"observation_id": str(oid), "source_url": c.source_url},
            )  # fmt: skip
            out = by_candidate[cid]
            out.status, out.observation_id, out.dataset_version = (
                "approved",
                oid,
                version.version_label,
            )


def _decide(
    session: Session,
    candidate_id: uuid.UUID,
    status: str,
    reasons: list[str],
    actor: Principal,
    *,
    by: str,
    import_id: uuid.UUID | None = None,
) -> None:
    c = session.get(ResearchCandidate, candidate_id, with_for_update=True)
    assert c is not None
    c.status = status
    decided = status not in ("pending", "conflict")
    c.reviewed_at = datetime.now(UTC) if decided else None
    c.reviewed_by = actor.user_id if decided else None
    c.decided_by = by if decided else None
    if import_id:
        c.import_job_id = import_id
    c.validation = {**(c.validation or {}), "reasons": reasons}
    c.history = [*c.history, _entry(status, reasons, by)]


def save_reviewed(
    session: Session, reviewer: Principal, candidate_id: uuid.UUID, note: str
) -> Outcome:
    """A reviewer approves a pending or conflicting figure: it is saved through the same
    import workflow (by the research service account, recorded as the reviewer's decision).
    The figure must still be written in its stored document and mapped to platform codes; an
    identical published figure makes it a duplicate instead. ``session``: no open transaction."""
    from app.core.errors import ApiError, not_found, unprocessable

    if not (note and note.strip()):
        raise unprocessable("note_required", "Record what you checked before approving.")
    with session.begin():
        c = session.get(ResearchCandidate, candidate_id)
        if c is None:
            raise not_found("research candidate")
        if c.status not in ("pending", "conflict"):
            raise ApiError(409, "already_reviewed", "This figure has already been decided.")
        doc = session.get(ResearchDocument, c.document_id) if c.document_id else None
        missing = [
            name
            for name, value in (
                ("indicator", c.indicator_code), ("area", c.area_code), ("unit", c.unit_code),
                ("kind_of_period", c.period_kind), ("period", c.period_start and c.period_end),
                ("document_text", doc is not None and doc.text_content),
            )
            if not value
        ]  # fmt: skip
        if missing:
            raise unprocessable(
                "not_mappable",
                "This figure cannot be saved: " + ", ".join(missing) + " missing. Import it "
                "through the normal upload instead.",
                {"missing": missing},
            )
        assert doc is not None and doc.text_content
        if find_value(doc.text_content, c.value, c.value_text) is None:
            raise unprocessable("value_not_in_document", "The stored document does not state it.")
        assert c.period_start and c.period_end and c.period_kind and c.unit_code
        record = Record(
            indicator_code=str(c.indicator_code),
            area_code=str(c.area_code),
            period_start=c.period_start,
            period_end=c.period_end,
            frequency="annual" if c.period_kind == "year_to_date" else c.period_kind,
            period_complete=c.period_kind != "year_to_date",
            unit_code=c.unit_code,
            value=c.value,
            revision_status=None,
            source_locator=f"research_document {doc.id}; passage: {c.excerpt[:180]}",
            record_ref=f"rc-{c.id.hex[:16]}",
        )
        outcome = Outcome(0, c.status, [], c.id)
    actor = research_principal(session)
    with save_lock(session) as locked:
        if not locked:
            raise ApiError(409, "save_in_progress", "Another save is running; try again shortly.")
        _save_document(
            session, actor, doc, [(c.id, record)], [outcome], reviewer=reviewer, note=note.strip()
        )
    with session.begin():
        audit.record(
            session, reviewer, f"research.review_{outcome.status}", entity_type="research_candidate",
            entity_id=candidate_id, metadata={"observation_id": str(outcome.observation_id or "")},
        )  # fmt: skip
    return outcome


# ------------------------------------------------------------------ status of saved results


def status(
    session: Session,
    *,
    candidate_ids: list[uuid.UUID] | None = None,
    indicator_code: str | None = None,
    user_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Saved and waiting figures with their sources, newest first, and per series the latest
    period saved by research."""
    stmt = select(ResearchCandidate).order_by(ResearchCandidate.created_at.desc()).limit(limit)
    if candidate_ids:
        stmt = stmt.where(ResearchCandidate.id.in_(candidate_ids))
    if indicator_code:
        stmt = stmt.where(ResearchCandidate.indicator_code == indicator_code)
    if user_id:
        stmt = stmt.where(ResearchCandidate.proposed_by == user_id)
    if job_id:
        stmt = stmt.where(ResearchCandidate.job_id == job_id)
    rows = session.scalars(stmt).all()
    counts: dict[str, int] = {}
    latest: dict[str, str] = {}
    items = []
    for c in rows:
        counts[c.status] = counts.get(c.status, 0) + 1
        if c.status == "approved" and c.indicator_code and c.period_end:
            key = f"{c.indicator_code}/{c.area_code}/{c.period_kind}"
            latest[key] = max(latest.get(key, ""), c.period_end.isoformat())
        items.append(
            {
                "candidate_id": str(c.id),
                "status": c.status,
                "saved": c.status == "approved",
                "indicator_code": c.indicator_code,
                "area_code": c.area_code,
                "period": c.period_label,
                "period_kind": c.period_kind,
                "period_start": c.period_start.isoformat() if c.period_start else None,
                "period_end": c.period_end.isoformat() if c.period_end else None,
                "value": format(c.value, "f"),
                "unit": c.unit_code or c.unit,
                "observation_id": str(c.observation_id) if c.observation_id else None,
                "source_url": c.source_url,
                "publisher": c.publisher,
                "source_title": c.source_title,
                "publication_date": c.publication_date.isoformat() if c.publication_date else None,
                "retrieved_at": c.retrieved_at.isoformat(),
                "reasons": (c.validation or {}).get("reasons", []),
                "submitted_at": c.created_at.isoformat(),
            }
        )
    return {"counts": counts, "latest_saved_period": latest, "items": items}
