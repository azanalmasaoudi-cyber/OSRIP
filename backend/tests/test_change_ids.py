"""Change calculations have one id per series (the interface uses the id as its list key).

Regression: partner slices of one indicator (merchandise imports from five partners, full
years and year-to-date totals) produced the same id for every partner.
"""

from typing import Any

from app.domain.enums import Section
from app.services.analysis.evidence import Evidence
from app.services.analysis.sections import _changes

VERSION = "cbc60eaf-0000-4000-8000-000000000001"


def evidence(partner: str | None, start: str, end: str, complete: bool, value: str) -> Evidence:
    ytd = not complete
    meta: dict[str, Any] = {
        "indicator": {"code": "TRADE_MERCH_IMPORTS", "name_en": "Imports", "name_ar": "الواردات"},
        "unit": {
            "code": "million_OMR",
            "dimension": "currency",
            "label_en": "OMR m",
            "label_ar": "م ر.ع",
        },
        "frequency": "annual",
        "period_kind": "year_to_date" if ytd else "annual",
        "ytd_end_month": int(end[5:7]) if ytd else None,
        "area": {"code": "OM", "level": "national"},
        "commodity": None,
        "partner": None if partner is None else {"code": partner},
        "flow": "import",
        "dataset_version": {"id": VERSION, "label": "pack-1"},
        "source": {"dataset_title": "Reference pack"},
    }
    obs = {
        "period_start": start,
        "period_end": end,
        "period_complete": complete,
        "value": value,
        "quality_status": "accepted",
        "source_row": f"{partner}:{start}",
    }
    return Evidence(meta, obs)


def test_partner_series_have_their_own_change_ids() -> None:
    items = []
    for partner in (None, "ARE", "CHN", "TUR"):
        items += [
            evidence(partner, "2025-01-01", "2025-12-31", True, "100"),  # one full year: no pair
            evidence(partner, "2025-01-01", "2025-07-31", False, "60"),
            evidence(partner, "2026-01-01", "2026-07-31", False, "66"),
        ]
    calcs = _changes(Section.TRADE, items)
    ids = [c["id"] for c in calcs]
    # Per series: one "no comparable period" record (full year) and absolute + percentage
    # change (year to date), each with an id of its own.
    assert len(calcs) == 4 * 3
    assert len(set(ids)) == len(ids)
    assert any(":ARE:" in i and i.endswith(":absolute") for i in ids)
    assert any(":CHN:" in i and i.endswith(":change") for i in ids)
