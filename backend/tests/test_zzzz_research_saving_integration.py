"""Research that saves figures (research/saving.py), against a real database and a scripted
page: a figure written in an official document read in full is saved as a published
observation through the import workflow; repeating it saves nothing twice; a different value
for the same period is kept as a conflict; secondary sources, search snippets, figures not in
the text and people without research.submit never save; pending figures are not observations."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

pytestmark = pytest.mark.integration

PAGE = """<html><head><title>Water statistics 2024 (test fixture)</title>
<meta name="date" content="2025-04-10"></head><body>
<p>Total water production in the Sultanate of Oman reached 512.3 million m³ in 2024, according
to the National Centre for Statistics and Information.</p></body></html>"""


# Each test saves figures for its own copy of the water production indicator (same unit and
# section), so nothing it publishes changes what other tests count for the real indicator.
CODE = "WATER_PRODUCTION"


@pytest.fixture(autouse=True)
def own_indicator(db: Any) -> None:
    global CODE
    from sqlalchemy import inspect, select

    from app.models import Indicator

    with db.begin():
        model = db.scalar(select(Indicator).where(Indicator.code == "WATER_PRODUCTION"))
        CODE = f"TESTW_{uuid.uuid4().hex[:8].upper()}"
        columns = {c.key: getattr(model, c.key) for c in inspect(Indicator).column_attrs}
        columns.pop("id", None)
        db.add(Indicator(**{**columns, "code": CODE}))


@pytest.fixture
def pages(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Scripted pages by address; reads are recorded (research_document) as in production."""
    from app.services.research import fetching, safe_fetch

    served: dict[str, str] = {}

    def fetch(url: str, **_: Any) -> safe_fetch.Fetched:
        if url not in served:
            raise safe_fetch.FetchFailed("http_404")
        body = served[url].encode()
        return safe_fetch.Fetched(
            url, 200, "text/html; charset=utf-8", served[url], False, raw=body
        )

    monkeypatch.setattr(safe_fetch, "fetch", fetch)
    monkeypatch.setattr(fetching, "persist", True)
    return served


def _read(url: str, text: str, pages: dict[str, str]) -> tuple[Any, str]:
    from app.domain.enums import DataMode
    from app.services.assistant.tools import Ledger
    from app.services.research import service as research

    pages[url] = text
    ledger = Ledger(DataMode.VERIFIED_SOURCE)
    ledger.add({"kind": "web", "url": url, "title": "Water", "query": "water production 2024",
                "content_kind": "search_snippet", "text": "512.3 million m³"})  # fmt: skip
    out = research.read_web_page(ledger, "E1", focus="water production")
    assert out["status"] == "ok", out
    return ledger, out["evidence_id"]


def _figure(evidence_id: str, value: str = "512.3", **extra: Any) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id, "indicator_code": CODE, "area_code": "OM",
        "value_text": value, "unit": "million m³", "period_kind": "annual",
        "period_start": "2024-01-01", "period_end": "2024-12-31", **extra,
    }  # fmt: skip


def _principal(db: Any, person_id: uuid.UUID) -> Any:
    from app.models import AppUser
    from app.services import accounts

    with db.begin():
        return accounts.load_principal(db, db.get(AppUser, person_id))


def _published(db: Any, value: str) -> int:
    from sqlalchemy import func, select

    from app.domain.enums import DatasetVersionStatus
    from app.models import DatasetVersion, Indicator, Observation

    with db.begin():
        return db.scalar(
            select(func.count())
            .select_from(Observation)
            .join(Indicator, Indicator.id == Observation.indicator_id)
            .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
            .where(
                Indicator.code == CODE,
                Observation.value == Decimal(value),
                Observation.period_start == date(2024, 1, 1),
                DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
            )
        )


def test_a_checked_official_figure_is_saved_once_and_a_conflict_is_kept_apart(
    db: Any, make_user: Any, pages: dict[str, str]
) -> None:
    from app.domain.enums import Role
    from app.models import ResearchCandidate, Source
    from app.services.research import saving

    analyst = _principal(db, make_user(Role.ANALYST).id)
    url = f"https://www.ncsi.gov.om/test/{uuid.uuid4().hex[:8]}/water"
    ledger, ev = _read(url, PAGE, pages)

    saved = saving.submit(db, [_figure(ev)], ledger.items, submitter=analyst, language="en")
    assert [o.status for o in saved] == ["approved"], saved[0].reasons
    assert saved[0].observation_id is not None and saved[0].dataset_version
    assert _published(db, "512.3") == 1
    with db.begin():
        c = db.get(ResearchCandidate, saved[0].candidate_id)
        assert c.decided_by == "validation" and c.observation_id == saved[0].observation_id
        assert "512.3" in c.excerpt and c.document_id is not None
        assert [h["status"] for h in c.history] == ["pending", "approved"]
        source = db.get(Source, _version_source(db, c.dataset_version_id))
        assert source.url == url and source.publisher.startswith("National Centre")

    # The same figure again: nothing new (idempotent), still one observation.
    again = saving.submit(db, [_figure(ev)], ledger.items, submitter=analyst, language="en")
    assert again[0].already_submitted and again[0].status == "duplicate"  # nothing saved now
    assert again[0].observation_id == saved[0].observation_id  # the record it became earlier
    assert _published(db, "512.3") == 1

    # The same period from another official page with another value: a conflict, not saved.
    other, ev2 = _read(f"{url}-revised", PAGE.replace("512.3", "530.0"), pages)
    conflict = saving.submit(
        db, [_figure(ev2, "530.0")], other.items, submitter=analyst, language="en"
    )
    assert conflict[0].status == "conflict" and conflict[0].observation_id is None
    assert any(r.startswith("differs_from_published") for r in conflict[0].reasons)
    assert _published(db, "530.0") == 0  # pending figures are not observations

    # A reviewer approves the conflicting figure: saved beside the first, never in its place.
    from app.domain.enums import Permission

    reviewer = _principal(db, make_user(Role.DATA_MANAGER, grants=(Permission.RESEARCH_REVIEW,)).id)
    with pytest.raises(Exception, match="Record what you checked"):
        saving.save_reviewed(db, reviewer, conflict[0].candidate_id, "")
    reviewed = saving.save_reviewed(
        db, reviewer, conflict[0].candidate_id, "Checked the revised table on the NCSI page."
    )
    assert reviewed.status == "approved" and reviewed.observation_id is not None
    assert _published(db, "530.0") == 1 and _published(db, "512.3") == 1
    with db.begin():
        c = db.get(ResearchCandidate, conflict[0].candidate_id)
        assert c.decided_by == "reviewer" and c.review_note.startswith("Checked")
        assert [h["status"] for h in c.history] == ["conflict", "approved"]


def _version_source(db: Any, version_id: uuid.UUID) -> uuid.UUID:
    from app.models import DatasetVersion

    return db.get(DatasetVersion, version_id).source_id


def test_figures_that_cannot_be_checked_are_never_saved(
    db: Any, make_user: Any, pages: dict[str, str]
) -> None:
    from app.domain.enums import Role
    from app.services.research import saving

    analyst = _principal(db, make_user(Role.ANALYST).id)
    viewer = _principal(db, make_user(Role.VIEWER).id)
    official = f"https://www.ncsi.gov.om/test/{uuid.uuid4().hex[:8]}/water"
    ledger, ev = _read(official, PAGE.replace("512.3", "498.7"), pages)

    # Not allowed to submit: refused before anything is stored.
    refused = saving.submit(
        db, [_figure(ev, "498.7")], ledger.items, submitter=viewer, language="en"
    )
    assert refused[0].status == "rejected" and refused[0].reasons == ["not_permitted_to_submit"]
    # A search snippet that was never read: refused.
    snippet = saving.submit(
        db, [_figure("E1", "498.7")], ledger.items[:1], submitter=analyst, language="en"
    )
    assert snippet[0].status == "rejected"
    # A value the document does not state: refused.
    invented = saving.submit(
        db, [_figure(ev, "498.8")], ledger.items, submitter=analyst, language="en"
    )
    assert invented[0].reasons == ["value_not_in_document_text"]
    # A secondary source states the figure: kept pending for a reviewer.
    news, ev3 = _read(
        f"https://news.example.com/{uuid.uuid4().hex[:8]}", PAGE.replace("512.3", "498.7"), pages
    )
    pending = saving.submit(
        db, [_figure(ev3, "498.7")], news.items, submitter=analyst, language="en"
    )
    assert pending[0].status == "pending" and pending[0].reasons == [
        "source_not_official:secondary"
    ]
    # A period that does not match its kind: refused.
    wrong = saving.submit(
        db,
        [_figure(ev, "498.7", period_end="2024-06-30")],
        ledger.items,
        submitter=analyst,
        language="en",
    )
    assert wrong[0].status == "rejected" and "period_not_a_calendar_year" in wrong[0].reasons
    assert _published(db, "498.7") == 0


def test_year_to_date_totals_to_different_months_are_never_mixed(
    app: Any, db: Any, make_user: Any, pages: dict[str, str]
) -> None:
    # Saving January-July next to a published January-August total once made the public
    # observations API refuse every year-to-date selection (incompatible_series).
    from fastapi.testclient import TestClient

    from app.domain.enums import Role
    from app.services.research import saving

    analyst = _principal(db, make_user(Role.ANALYST).id)
    for month, end, value in ((7, "2024-07-31", "301.4"), (8, "2024-08-31", "344.9")):
        text = PAGE.replace(
            "reached 512.3 million m³ in 2024",
            f"reached {value} million m³ by the end of month {month} of 2024",
        )
        ledger, ev = _read(f"https://www.ncsi.gov.om/test/{uuid.uuid4().hex[:8]}/ytd", text, pages)
        figure = _figure(ev, value, period_kind="year_to_date", period_end=end)
        assert (
            saving.submit(db, [figure], ledger.items, submitter=analyst, language="en")[0].status
            == "approved"
        )
    client = TestClient(app)
    query = f"/api/v1/observations?data_mode=verified_source&indicator={CODE}&area=OM&period_kind=year_to_date"
    latest = client.get(query)
    assert latest.status_code == 200, latest.text
    ends = {o["period_end"] for s in latest.json()["series"] for o in s["observations"]}
    assert ends == {"2024-08-31"}
    assert latest.json()["series"][0]["ytd_end_months_available"] == [7, 8]
    july = client.get(query + "&ytd_end_month=7").json()
    assert {o["period_end"] for s in july["series"] for o in s["observations"]} == {"2024-07-31"}
