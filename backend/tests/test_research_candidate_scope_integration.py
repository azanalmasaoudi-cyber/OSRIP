"""Web figures proposed for review (research candidates), against the database: the 2021 start of the
platform's statistical scope is accepted (migration 0034), and a figure the database refuses is
skipped without losing the others or the answer they came with.

Found live on 2026-11-13: an internet answer citing the Ibri II solar plant (560 MW, 2021) could
not be saved, because the database rule still required 2022 while the application uses 2021.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select, text

from app.models import ResearchCandidate
from app.services.imports.validation import STATISTICAL_SCOPE_START
from app.services.research import service as research

pytestmark = pytest.mark.integration

PAGE = "The Ibri II Solar PV plant has an installed capacity of 560 MW and began operating in 2021."


def _web_item(evidence_id: str, url: str) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "kind": "web",
        "url": url,
        "title": "Ibri II Solar PV IPP",
        "text": PAGE,
        "publisher": {
            "en": "Oman Electricity Transmission Company",
            "ar": "الشركة العمانية لنقل الكهرباء",
        },
        "source_class": "official",
        "provider": "deepseek",
        "domain": "electricity",
        "retrieved_at": "2026-11-13T17:47:00+00:00",
    }


def _record(evidence_id: str, period_end: str) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "domain": "electricity",
        "indicator": "Installed capacity of Ibri II Solar PV IPP",
        "value_text": "560",
        "unit": "MW",
        "geography": "Oman (Ibri, Al Dhahirah)",
        "period_label": period_end[:4],
        "period_end": period_end,
    }


def test_the_database_accepts_figures_from_the_platforms_scope_start(db) -> None:  # noqa: ANN001
    assert STATISTICAL_SCOPE_START.isoformat() == "2021-01-01"
    check = db.scalar(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_research_candidate_scope'"
        )
    )
    assert "2021-01-01" in check


def test_a_2021_web_figure_is_queued_for_review(db) -> None:  # noqa: ANN001
    url = "https://www.omangrid.com/en/ibri-ii-2021"
    item = _web_item("w1", url)
    with db.begin():
        stored = research.queue_candidates(
            db, [_record("w1", "2021-12-31")], [item], citations=["w1"],
            message_id=None, proposed_by=None, language="en",  # type: ignore[arg-type]
        )  # fmt: skip
    assert stored == 1
    row = db.scalar(select(ResearchCandidate).where(ResearchCandidate.source_url == url))
    assert row is not None and row.status == "pending" and str(row.period_end) == "2021-12-31"


def test_a_figure_the_database_refuses_is_skipped_and_the_rest_are_kept(db) -> None:  # noqa: ANN001
    good = _web_item("w2", "https://www.omangrid.com/en/ibri-ii-2023")
    # A source address the database refuses (ck_research_candidate_url: http or https only).
    refused = _web_item("w3", "ftp://example.org/ibri-ii")
    with db.begin():
        stored = research.queue_candidates(
            db, [_record("w3", "2023-12-31"), _record("w2", "2023-12-31")], [good, refused],
            citations=["w2", "w3"], message_id=None, proposed_by=None, language="en",  # type: ignore[arg-type]
        )  # fmt: skip
        # The transaction is still usable after the refused figure.
        assert db.scalar(text("SELECT 1")) == 1
    assert stored == 1
    urls = set(
        db.scalars(
            select(ResearchCandidate.source_url).where(ResearchCandidate.value_text == "560")
        )
    )
    assert "https://www.omangrid.com/en/ibri-ii-2023" in urls
    assert "ftp://example.org/ibri-ii" not in urls
