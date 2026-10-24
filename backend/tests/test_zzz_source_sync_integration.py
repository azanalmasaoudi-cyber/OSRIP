"""Runs last (file name): it publishes test bulletin figures as verified-source data, which
the reference-pack tests must not see.

Official statistics sync against the database, with the publisher's site replaced by a
local stand-in (no network): a check stages only new figures, an approved import publishes
them, a repeated check or re-sent file adds nothing, a later release stages only its revised
figures (both publications are kept and the newer is shown), a failed check changes no
published data and is logged with backoff, the portal that needs access is reported as such,
and only administrators change the schedule or start a check."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from app.domain.enums import DataMode, DatasetVersionStatus, Role
from tests.sync_fixtures import bulletin, listing_page, msb_entry

pytestmark = pytest.mark.integration

API = "/api/v1"
FEED = "ncsi-monthly-bulletin"
LISTING = "https://www.ncsi.gov.om/en/publications"
OCT = "https://api.ncsi.gov.om/uploads/xls/msb_oct_2026_1.xlsx"
NOV = "https://api.ncsi.gov.om/uploads/xls/msb_nov_2026_1.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Site:
    """The publisher's pages as this test sets them; every request is recorded."""

    def __init__(self) -> None:
        self.pages: dict[str, httpx.Response] = {}
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        page = self.pages.get(url)
        if page is None:
            return httpx.Response(404)
        return httpx.Response(page.status_code, headers=page.headers, content=page.content)

    def serve(self, entries: list[dict[str, object]], files: dict[str, bytes]) -> None:
        self.pages = {
            LISTING: httpx.Response(
                200, headers={"content-type": "text/html"}, content=listing_page(entries)
            )
        }
        for url, data in files.items():
            self.pages[url] = httpx.Response(200, headers={"content-type": XLSX}, content=data)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Site:
    from app.services.sync import fetch, service

    s = Site()
    monkeypatch.setattr(
        fetch,
        "client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(s.handler)),
    )
    monkeypatch.setattr(fetch, "sleep", lambda _: None)
    monkeypatch.setattr(service, "fetch_attempts", 2)
    return s


def _published_count(session) -> int:  # noqa: ANN001
    from app.models import DatasetVersion, Observation, Source

    with session.begin():
        return session.scalar(
            select(func.count(Observation.id))
            .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
            .join(Source, Source.id == DatasetVersion.source_id)
            .where(
                DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
                Source.dataset_title.like("Monthly Statistical Bulletin%(official workbook%"),
            )
        )


def _release(session, run: dict):  # noqa: ANN001, ANN202
    from app.models import SourceRelease

    with session.begin():
        return session.get(SourceRelease, run["release_id"])


def test_checks_stage_new_figures_once_and_revisions_later(db, site) -> None:  # noqa: ANN001
    from app.models import SourceFeed
    from app.services.imports import workflow
    from app.services.sync import service

    # 1. The October bulletin: every figure is new to the platform (or already published by
    #    another publication); new ones are staged, nothing is published yet.
    site.serve([msb_entry()], {OCT: bulletin()})
    run = service.run_check(db, FEED, trigger="manual")
    assert run["status"] == "staged", run
    release = _release(db, run)
    assert release.rows_read == 132
    assert release.rows_new + release.rows_revised + release.rows_unchanged == 132
    assert release.rows_new > 0 and release.import_job_id is not None
    assert release.published_at == datetime(2026, 10, 20, 9, 28, 38, tzinfo=UTC)
    assert _published_count(db) == 0  # staged, waiting for a data manager

    # A data manager approves and publishes the staged import.
    actor = service.sync_principal(db)
    workflow.approve_import(
        db, actor, release.import_job_id, acknowledged_rejected_rows=0, note="test"
    )
    workflow.publish_import(db, actor, release.import_job_id)
    published = _published_count(db)
    assert published == release.rows_new + release.rows_revised

    # 2. The same listing again: the release is known, nothing is downloaded or added.
    site.requests.clear()
    again = service.run_check(db, FEED, trigger="schedule")
    assert again["status"] == "no_new_release" and again["releases_seen"] == 1
    assert site.requests == [LISTING]
    assert _published_count(db) == published
    # The same workbook uploaded by hand: every figure is already published.
    upload = service.run_upload(
        db,
        FEED,
        bulletin(),
        title_en="Monthly Statistical Bulletin :October 2026",
        file_url=OCT,
        published_on=None,
        requested_by=None,
    )
    assert upload["status"] == "unchanged" and "already published" in upload["message"]
    assert _published_count(db) == published

    # 3. November revises the national August figures; switched to automatic publication.
    with db.begin():
        feed = db.scalar(select(SourceFeed).where(SourceFeed.code == FEED))
        feed.auto_publish = True
    site.serve(
        [msb_entry(1969, month="November", xls=NOV), msb_entry()],
        {NOV: bulletin(august_total=999.0), OCT: bulletin()},
    )
    revised = service.run_check(db, FEED, trigger="schedule")
    assert revised["status"] == "published", revised
    r = _release(db, revised)
    assert (r.rows_new, r.rows_revised) == (0, 2)  # gross and net, national, August 2026
    assert "regions add up to" in (r.message or "")  # the consistency note is kept
    assert _published_count(db) == published + 2

    # The timeline shows the newer figure and keeps the earlier one with the row.
    from app.services import timeline

    with db.begin():
        doc = timeline.build(db, DataMode.VERIFIED_SOURCE, "ELEC_GROSS_GENERATION", view="monthly")
    august = next(row for row in doc["rows"] if row["period_start"] == "2026-08-01")
    assert Decimal(august["value"]) == Decimal("999") and august["revised"] is True
    assert any(o["value"] for o in august["other_publications"])


def test_a_failed_check_changes_no_published_data_and_backs_off(db, site) -> None:  # noqa: ANN001
    from app.models import SourceFeed, SourceSyncRun
    from app.services.sync import service

    before = _published_count(db)
    site.pages = {LISTING: httpx.Response(503)}
    run = service.run_check(db, FEED, trigger="schedule")
    assert run["status"] == "failed" and run["http_status"] == 503 and run["attempts"] == 2
    assert "could not be read" in run["message"]
    with db.begin():
        feed = db.scalar(select(SourceFeed).where(SourceFeed.code == FEED))
        assert feed.consecutive_failures >= 1 and feed.last_status == "failed"
        assert feed.next_check_at is not None
        assert feed.next_check_at <= datetime.now(UTC) + timedelta(hours=24)
        assert (
            db.scalar(select(func.count(SourceSyncRun.id)).where(SourceSyncRun.status == "failed"))
            >= 1
        )
    # A workbook whose layout changed: the release fails, nothing is staged.
    broken = bulletin(water_unit="(000)Litres")
    site.serve(
        [msb_entry(1970, month="December", xls="https://api.ncsi.gov.om/uploads/xls/msb_dec.xlsx")],
        {"https://api.ncsi.gov.om/uploads/xls/msb_dec.xlsx": broken},
    )
    run = service.run_check(db, FEED, trigger="manual")
    assert run["status"] == "failed" and "verified layout" in run["message"]
    assert _release(db, run).import_job_id is None
    assert _published_count(db) == before
    # The listing works again: the failure count is cleared.
    site.serve([msb_entry()], {OCT: bulletin()})
    ok = service.run_check(db, FEED, trigger="schedule")
    assert ok["status"] in ("no_new_release", "unchanged")
    with db.begin():
        feed = db.scalar(select(SourceFeed).where(SourceFeed.code == FEED))
        assert feed.consecutive_failures == 0 and feed.last_success_at is not None


def test_status_schedule_and_permissions(anonymous, login, make_user, site) -> None:  # noqa: ANN001
    feeds = anonymous.get(f"{API}/source-feeds")
    assert feeds.status_code == 200
    by = {f["code"]: f for f in feeds.json()}
    assert by["ncsi-data-portal"]["access"] == "requires_access"
    assert "403" in by["ncsi-data-portal"]["notes"]["en"]
    msb = by[FEED]
    # The three moments are separate fields; a public reader sees no error text.
    assert {"last_success_at", "latest_release", "latest_observation"} <= set(msb)
    assert "last_error" not in msb
    assert anonymous.get(f"{API}/admin/source-feeds").status_code in (401, 403)

    viewer = login(make_user(Role.VIEWER))
    assert (
        viewer.patch(f"{API}/admin/source-feeds/{FEED}", json={"enabled": True}).status_code == 403
    )
    assert viewer.post(f"{API}/admin/source-feeds/{FEED}/check").status_code == 403

    admin = login(make_user(Role.ADMINISTRATOR))
    portal = admin.patch(f"{API}/admin/source-feeds/ncsi-data-portal", json={"enabled": True})
    assert portal.status_code == 422
    checked = admin.post(f"{API}/admin/source-feeds/ncsi-data-portal/check").json()
    assert checked["status"] == "not_accessible" and "403" in checked["message"]
    changed = admin.patch(
        f"{API}/admin/source-feeds/{FEED}", json={"enabled": True, "check_interval_hours": 48}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["enabled"] is True and changed.json()["check_interval_hours"] == 48
    assert (
        admin.patch(
            f"{API}/admin/source-feeds/{FEED}", json={"check_interval_hours": 1}
        ).status_code
        == 422
    )
    response = admin.get(f"{API}/admin/source-feeds/{FEED}/runs")
    assert response.status_code == 200, response.text
    runs = response.json()
    assert runs and {"status", "attempts", "trigger", "message"} <= set(runs[0])
    releases = admin.get(f"{API}/admin/source-feeds/{FEED}/releases").json()
    assert releases and releases[0]["published_at"]

    # The worker picks up a due feed (the schedule starts a minute after it is switched on).
    from app.db.session import session_factory
    from app.services.sync import service

    with session_factory()() as session:
        assert FEED not in service.due_feeds(session)
        assert FEED in service.due_feeds(session, datetime.now(UTC) + timedelta(minutes=2))
    site.serve([msb_entry()], {OCT: bulletin()})
    from app import worker

    assert worker.run_due() == 0  # not due yet
    admin.patch(f"{API}/admin/source-feeds/{FEED}", json={"enabled": False})
