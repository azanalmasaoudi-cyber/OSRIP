"""Evidence validation of the model's reply. Pure: no I/O.

A reply is accepted only if
* every citation names evidence gathered for this message;
* a reply that states any number cites evidence;
* every number in the text matches a number in the cited evidence (values,
  calculation results and their inputs, the components of cited periods, a number in the
  cited publication's title, reference period or table locator, or a number written in the
  text of a cited web result or page excerpt), allowing only rounding of
  the evidence value to the digits shown;
* every ISO date (2026-09-27) appears in the cited evidence (a period, a source's access
  date, a publication date, a date written in a cited text).
Otherwise the reply is withheld and the reader sees the evidence instead. This does
not prove the wording is correct; it prevents invented or unsupported figures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

# Latin and Arabic-Indic digits, thousands separators (",", "٬") and decimal points (".", "٫").
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# Arabic writes some words onto a number ("و49,132.0", and 49,132.0), so only Latin letters,
# digits, underscores and points around it mean it is part of a code (CO2, Q3), not a figure.
_NUMBER = re.compile(r"(?<![\dA-Za-z_.])(\d{1,3}(?:[,٬]\d{3})+|\d+)(?:[.٫](\d+))?(?![\dA-Za-z_])")
# The number of a list item or section ("1.", "**2. Full year**", "3)", "١-") at the start of a
# line counts the reply's own parts; it is not a figure.
_LIST_MARKER = re.compile(r"^([\s>#*_-]*)\d{1,2}[.)-](?=\s)", re.MULTILINE)
# One date, not three numbers.
_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_EVIDENCE_ID = re.compile(r"\[?E\d+\]?")


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    problems: tuple[str, ...]


def numbers_in(text: str) -> list[tuple[Decimal, int]]:
    """(value, decimals shown) for every number in the text, evidence ids and list numbers
    excluded."""
    cleaned = _EVIDENCE_ID.sub(" ", text.translate(_ARABIC_DIGITS))
    cleaned = _LIST_MARKER.sub(r"\1 ", cleaned)
    out = []
    for whole, frac in _NUMBER.findall(cleaned):
        raw = whole.replace(",", "").replace("٬", "") + (f".{frac}" if frac else "")
        try:
            out.append((Decimal(raw), len(frac)))
        except InvalidOperation:
            continue
    return out


def _evidence_numbers(item: dict[str, Any], ledger: dict[str, dict[str, Any]]) -> set[Decimal]:
    found: set[Decimal] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return
        found.add(abs(number))

    add(item.get("value"))
    for key in ("period_start", "period_end"):
        if isinstance(item.get(key), str):
            y, m, d = item[key].split("-")
            for part in (y, m, d):
                add(part)
    source = item.get("source")
    if isinstance(source, dict):
        # The publication named with the figure ("Statistical Year Book 2026, Issue 54").
        for key in ("title", "reference_period", "locator"):
            for number, _ in numbers_in(str(source.get(key) or "")):
                add(number)
    for output in item.get("outputs", []) or []:
        for key in ("estimate", "lower80", "upper80", "lower95", "upper95"):
            add(output.get(key))
        for key in ("period_start", "period_end"):
            if isinstance(output.get(key), str):
                for part in output[key].split("-"):
                    add(part)
    for metric in (item.get("metrics") or {}).values():
        for key in ("mae", "rmse", "n"):
            add(metric.get(key))
    if item.get("kind") == "forecast":
        add(80)  # interval levels named in the reply
        add(95)
    if isinstance(item.get("training_cutoff"), str):
        for part in item["training_cutoff"].split("-"):
            add(part)
    if item.get("kind") == "scenario":
        for key in ("growth_pct", "years", "one_off_pct"):
            add((item.get("assumptions") or {}).get(key))
        for point in item.get("points", []) or []:
            add(point.get("value"))
            add(point.get("year"))
            add(point.get("step"))
    if item.get("kind") in ("web", "note"):
        # Only numbers written in the retrieved text itself (snippet, page excerpt, or the
        # documented note), in either language.
        for key in ("text", "text_ar"):
            for number, _ in numbers_in(str(item.get(key, ""))):
                add(number)
        if isinstance(item.get("published"), str):
            for part in item["published"].split("-"):
                add(part)
    if (
        item.get("kind") == "study"
        and isinstance(item.get("study"), dict)
        and item["study"].get("kind") == "supply_balance"
    ):
        # A shortage and surplus analysis: its balance tables, gaps, summary sentences,
        # recommendation quantities and evidence, scenario rows and source values and periods.
        doc = item["study"]
        texts: list[str] = []
        for b in doc.get("balances", []):
            for row in b["table"]["rows"]:
                texts += [str(c or "") for c in row.values()]
            texts += [
                str(b.get("gap") or ""),
                str(b.get("gap_share") or ""),
                str(b.get("period") or ""),
            ]
            texts += [b["reason"][lang] for lang in ("en", "ar")]
        for s in doc.get("summary", []):
            texts += [s["en"], s["ar"]]
        for r in doc.get("recommendations", []):
            texts += [str(r.get("quantity") or ""), r["evidence"]["en"], r["evidence"]["ar"]]
        scenario = doc.get("scenario") or {}
        for row in (scenario.get("table") or {}).get("rows", []):
            texts += [str(c or "") for c in row.values()]
        for a in scenario.get("assumptions", []):
            texts += [a["en"], a["ar"]]
        for s in doc.get("sources", []):
            texts += [str(s.get("value") or ""), s.get("period_start", ""), s.get("period_end", "")]
        for text in texts:
            for number, _ in numbers_in(text):
                add(number)
    elif item.get("kind") == "study" and isinstance(item.get("study"), dict):
        # A deterministic study: its table cells, cards, findings and periods.
        doc = item["study"]
        for row in doc.get("table", {}).get("rows", []):
            for cell in row.values():
                for number, _ in numbers_in(str(cell or "")):
                    add(number)
        for card in doc.get("cards", []):
            add(card.get("value"))
            for number, _ in numbers_in(str(card.get("period") or "")):
                add(number)
        for finding in doc.get("findings", []):
            for lang in ("en", "ar"):
                for number, _ in numbers_in(finding.get("text", {}).get(lang, "")):
                    add(number)
        for key in ("from", "to"):
            for number, _ in numbers_in(str((doc.get("periods") or {}).get(key) or "")):
                add(number)
    if item.get("kind") in ("calculation", "scenario"):
        for input_id in item.get("inputs", []):
            if input_id in ledger:
                found |= _evidence_numbers(ledger[input_id], ledger)
    return found


def _matches(shown: Decimal, decimals: int, allowed: set[Decimal]) -> bool:
    shown = abs(shown)
    tolerance = Decimal(1).scaleb(-decimals) / 2
    return any(abs(shown - v) <= tolerance for v in allowed)


_MARKER = re.compile(r"\[(E\d+)\]")
_SENTENCE = re.compile(r"(?<=[.!?؟])\s+")


def inline_markers(text: str) -> list[str]:
    """Evidence ids written next to claims, e.g. ``[E3]``."""
    return _MARKER.findall(text)


def _is_year(number: Decimal, decimals: int) -> bool:
    return decimals == 0 and 1990 <= number <= 2100


def _dates_in(value: Any, found: set[str]) -> None:
    if isinstance(value, str):
        found.update(_ISO_DATE.findall(value.translate(_ARABIC_DIGITS)))
    elif isinstance(value, dict):
        for v in value.values():
            _dates_in(v, found)
    elif isinstance(value, list | tuple):
        for v in value:
            _dates_in(v, found)


def _evidence_dates(ids: list[str], ledger: dict[str, dict[str, Any]]) -> set[str]:
    """ISO dates anywhere in the cited evidence, and in the inputs of a cited calculation."""
    found: set[str] = set()
    for c in ids:
        item = ledger.get(c)
        if item is None:
            continue
        _dates_in(item, found)
        if item.get("kind") in ("calculation", "scenario"):
            found |= _evidence_dates(list(item.get("inputs", []) or []), ledger)
    return found


def _allowed(ids: list[str] | set[str], ledger: dict[str, dict[str, Any]]) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for c in ids:
        if c in ledger:
            allowed |= _evidence_numbers(ledger[c], ledger)
    return allowed


def validate(text: str, citations: list[str], ledger_items: list[dict[str, Any]]) -> Verdict:
    """Every cited id must exist; every number must match cited evidence; and statistical
    numbers must be cited next to the claim: by an ``[E#]`` marker in the same sentence or,
    failing that, in the same paragraph. Plain years (labels of periods) and ISO dates only
    need support somewhere in the reply's citations."""
    ledger = {i["id"]: i for i in ledger_items}
    problems: list[str] = []
    markers = inline_markers(text)
    cited = list(dict.fromkeys([*citations, *markers]))
    unknown = [c for c in cited if c not in ledger]
    if unknown:
        problems.append(f"unknown citations: {', '.join(unknown)}")
    plain = text.translate(_ARABIC_DIGITS)
    dates = list(dict.fromkeys(_ISO_DATE.findall(plain)))
    if dates:
        known = _evidence_dates(cited, ledger)
        missing = [d for d in dates if d not in known]
        if missing:
            problems.append(f"dates not in cited evidence: {', '.join(missing[:5])}")
        plain = _ISO_DATE.sub(" ", plain)
    # Whole lines: the sentence split below would cut "**1." off from its line.
    text = _LIST_MARKER.sub(r"\1 ", plain)
    numbers = numbers_in(text)
    if numbers and not cited:
        problems.append("numbers without citations")
    everywhere = _allowed(cited, ledger)
    unsupported: list[str] = []
    uncited: list[str] = []
    for paragraph in [p for p in text.split("\n") if p.strip()]:
        paragraph_ids = inline_markers(paragraph)
        for sentence in _SENTENCE.split(paragraph):
            local_ids = inline_markers(sentence) or paragraph_ids
            local = _allowed(local_ids, ledger) if local_ids else set()
            for number, decimals in numbers_in(sentence):
                if _is_year(number, decimals):
                    if not _matches(number, decimals, everywhere):
                        unsupported.append(str(number))
                elif not local_ids:
                    uncited.append(str(number))
                elif not _matches(number, decimals, local):
                    unsupported.append(str(number))
    if unsupported:
        problems.append(f"numbers not in cited evidence: {', '.join(unsupported[:5])}")
    if uncited:
        problems.append(f"numbers without an inline citation: {', '.join(uncited[:5])}")
    return Verdict(not problems, tuple(problems))


# ------------------------------------------------------------------ structured parts

DRIVERS = (
    "weather",
    "population",
    "industrial_activity",
    "desalination",
    "renewable_energy",
    "irrigation",
    "agricultural_productivity",
    "commodity_prices",
    "logistics",
    "trading_partners",
)
CARD_FIELDS = (
    "finding",
    "evidence",
    "action",
    "expected_benefit",
    "prerequisites",
    "uncertainty",
)
MAX_FIELD = 700


def _clean(value: Any, limit: int = MAX_FIELD) -> str:
    return " ".join(str(value or "").split())[:limit]


def _ids(value: Any, ledger: dict[str, dict[str, Any]]) -> list[str] | None:
    """The cited ids, or None when one of them does not exist."""
    ids = [str(c) for c in (value or [])][:10] if isinstance(value, list) else []
    return ids if all(c in ledger for c in ids) else None


def _numbers_supported(
    texts: list[str], ids: list[str], ledger: dict[str, dict[str, Any]], extra: set[Decimal]
) -> bool:
    allowed = _allowed(ids, ledger) | extra
    return all(_matches(n, d, allowed) for t in texts for n, d in numbers_in(t))


def validate_structured(
    final: dict[str, Any], ledger_items: list[dict[str, Any]], *, question: str, mode: str
) -> dict[str, Any]:
    """Check each structured part on its own and keep only what the evidence supports.

    * Recommendation cards (Analyze and Research): every field present, at least one
      citation, and every number in every field found in the card's cited evidence. Expected
      benefits therefore cannot contain invented savings, costs or percentage improvements.
    * Drivers: one of the ten named drivers; 'evidence' needs citations; any number must be
      in the cited evidence.
    * Evidence points need citations; hypotheses and assumptions are labelled as such, and
      may contain only numbers found in cited evidence or (assumptions) stated by the user.
    * Conflicts: each value must be written in the evidence it cites.
    Unsupported parts are dropped and counted, never shown.
    """
    ledger = {i["id"]: i for i in ledger_items}
    user_numbers = {n for n, _ in numbers_in(question)}
    out: dict[str, Any] = {"withheld": {}}

    def withheld(part: str) -> None:
        out["withheld"][part] = out["withheld"].get(part, 0) + 1

    if mode in ("analyze", "research"):
        cards = []
        for raw in (final.get("recommendations") or [])[:5]:
            if not isinstance(raw, dict):
                withheld("recommendations")
                continue
            card = {f: _clean(raw.get(f)) for f in CARD_FIELDS}
            ids = _ids(raw.get("citations"), ledger)
            if (
                not ids
                or not all(card.values())
                or not _numbers_supported(list(card.values()), ids, ledger, set())
            ):
                withheld("recommendations")
                continue
            cards.append({**card, "citations": ids})
        if cards:
            out["recommendations"] = cards

    drivers = []
    for raw in (final.get("drivers") or [])[:10]:
        if not isinstance(raw, dict) or raw.get("driver") not in DRIVERS:
            withheld("drivers")
            continue
        basis = raw.get("basis")
        relation = _clean(raw.get("relation"))
        ids = _ids(raw.get("citations"), ledger)
        if (
            basis not in ("evidence", "hypothesis", "assumption")
            or not relation
            or ids is None
            or (basis == "evidence" and not ids)
            or not _numbers_supported(
                [relation], ids, ledger, user_numbers if basis == "assumption" else set()
            )
        ):
            withheld("drivers")
            continue
        drivers.append(
            {"driver": raw["driver"], "basis": basis, "relation": relation, "citations": ids}
        )
    if drivers:
        out["drivers"] = drivers

    for part, needs_citation, extra in (
        ("evidence_points", True, set()),
        ("hypotheses", False, set()),
        ("assumptions", False, user_numbers),
    ):
        kept = []
        for raw in (final.get(part) or [])[:8]:
            statement = _clean(raw.get("statement") if isinstance(raw, dict) else raw)
            ids = _ids(raw.get("citations"), ledger) if isinstance(raw, dict) else []
            if (
                not statement
                or ids is None
                or (needs_citation and not ids)
                or not _numbers_supported([statement], ids, ledger, extra)
            ):
                withheld(part)
                continue
            kept.append({"statement": statement, "citations": ids})
        if kept:
            out[part] = kept

    conflicts = []
    for raw in (final.get("conflicts") or [])[:5]:
        if not isinstance(raw, dict):
            withheld("conflicts")
            continue
        values = []
        for v in (raw.get("values") or [])[:4]:
            ev = ledger.get(str(v.get("evidence_id", ""))) if isinstance(v, dict) else None
            text = _clean(v.get("value_text"), 60) if isinstance(v, dict) else ""
            nums = numbers_in(text)
            if ev and nums and all(_matches(n, d, _evidence_numbers(ev, ledger)) for n, d in nums):
                values.append({"evidence_id": ev["id"], "value_text": text})
        topic = _clean(raw.get("topic"), 200)
        if topic and len(values) >= 2:
            conflicts.append({"topic": topic, "values": values, "note": _clean(raw.get("note"))})
        else:
            withheld("conflicts")
    if conflicts:
        out["conflicts"] = conflicts
    if not out["withheld"]:
        del out["withheld"]
    return out
