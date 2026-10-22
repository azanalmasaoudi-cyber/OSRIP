# ruff: noqa: E501 - request and response lines are kept whole for readability
"""Studies as background jobs: queued and returned at once, run step by step, cached,
stopped, retried and resumed; web retrieval through a mocked Firecrawl with provenance,
duplicates and revisions; and administrators' scheduled reports, which are off by default and
never run paid services unless allowed. No request leaves the machine."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.domain.enums import Permission, Role
from tests.workflow_helpers import API

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def setup(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.db.session import session_factory
    from app.services import providers
    from app.services.fixtures import seed_booklet_fixtures
    from app.services.research import jobs

    monkeypatch.setattr(jobs, "kick", lambda: None)  # the test runs the queue itself
    monkeypatch.setattr(providers, "meter", providers.MemoryMeter())
    monkeypatch.setattr(get_settings(), "firecrawl_api_key", None)
    with session_factory()() as s:
        seed_booklet_fixtures(s)


@pytest.fixture
def user(make_user, login):  # noqa: ANN001, ANN201
    return login(make_user(Role.VIEWER))


def _create(client, refresh: bool = False, **params: Any) -> dict[str, Any]:  # noqa: ANN001
    body = {
        "sector": "electricity",
        "question": f"Electricity supply and demand {uuid.uuid4().hex[:6]}",
        "data_mode": "synthetic",
        **params,
    }
    r = client.post(f"{API}/research/jobs", json={"params": body, "refresh": refresh})
    assert r.status_code == 202, r.text
    return r.json()


def _drain() -> None:
    from app.services.research import jobs

    jobs.drain()


def test_a_study_runs_in_the_background_step_by_step(user) -> None:  # noqa: ANN001
    created = _create(user)
    assert created["state"] == "queued" and created["progress"] == 0
    assert [s["stage"] for s in created["steps"]] == [
        "discover",
        "retrieve",
        "extract",
        "validate",
        "calculate",
        "build",
        "conclude",
        "next_steps",
    ]
    _drain()
    job = user.get(f"{API}/research/jobs/{created['id']}").json()
    assert job["state"] == "succeeded" and job["progress"] == 100 and job["attempts"] == 1
    steps = {s["stage"]: s for s in job["steps"]}
    assert steps["discover"]["state"] == "done" and steps["retrieve"]["state"] == "skipped"
    assert steps["extract"]["state"] == "skipped"
    assert all(
        steps[s]["state"] == "done"
        for s in ("validate", "calculate", "build", "conclude", "next_steps")
    )
    assert all(st["detail"]["en"] and st["detail"]["ar"] for st in job["steps"])
    result = job["result"]
    assert job["analysis_id"] and result["analysis"]["id"] == job["analysis_id"]
    assert result["sources"] and result["conclusion"]["written_by"] == "rules"
    assert result["conclusion"]["main_findings"] and result["next_steps"]
    assert all(t["dataset_id"] for t in result["tables"])
    # The stored analysis is readable as usual.
    assert user.get(f"{API}/analysis/balance/{job['analysis_id']}").status_code == 200
    listed = user.get(f"{API}/research/jobs").json()
    assert created["id"] in [j["id"] for j in listed] and "result" not in listed[0]


def test_identical_studies_are_served_from_cache_unless_refreshed(user) -> None:  # noqa: ANN001
    params = {"sector": "water", "question": "Water balance cache check"}
    first = _create(user, **params)
    _drain()
    again = _create(user, **params)
    assert again["state"] == "succeeded" and again["cached"] is True
    assert (
        again["analysis_id"] == user.get(f"{API}/research/jobs/{first['id']}").json()["analysis_id"]
    )
    fresh = _create(user, refresh=True, **params)
    assert fresh["state"] == "queued" and fresh["cached"] is False


def test_stop_retry_and_ownership(user, make_user, login, anonymous) -> None:  # noqa: ANN001
    job = _create(user)
    stopped = user.post(f"{API}/research/jobs/{job['id']}/cancel").json()
    assert stopped["state"] == "cancelled" and stopped["cancel_requested"] is True
    assert all(s["state"] == "cancelled" for s in stopped["steps"])
    retried = user.post(f"{API}/research/jobs/{job['id']}/retry")
    assert retried.status_code == 202 and retried.json()["state"] == "queued"
    _drain()
    assert user.get(f"{API}/research/jobs/{job['id']}").json()["state"] == "succeeded"
    assert user.post(f"{API}/research/jobs/{job['id']}/retry").status_code == 409
    other = login(make_user(Role.VIEWER))
    assert other.get(f"{API}/research/jobs/{job['id']}").status_code == 404
    assert other.post(f"{API}/research/jobs/{job['id']}/cancel").status_code == 404
    assert anonymous.get(f"{API}/research/jobs").status_code == 401
    bad = user.post(
        f"{API}/research/jobs", json={"params": {"sector": "gold", "question": "x y z"}}
    )
    assert bad.status_code == 422
    backwards = user.post(
        f"{API}/research/jobs",
        json={
            "params": {
                "sector": "trade",
                "question": "Trade 2024",
                "period_from": "2025-01-01",
                "period_to": "2024-01-01",
            }
        },
    )
    assert backwards.status_code == 422


def test_an_interrupted_study_resumes_from_its_last_completed_step(user) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.models import ResearchJob
    from app.services.research import jobs

    job = _create(user)
    with session_factory()() as s, s.begin():
        row = s.get(ResearchJob, uuid.UUID(job["id"]))
        steps = [dict(x) for x in row.steps]
        steps[0].update(state="done", detail={"en": "kept", "ar": "محفوظ"})
        steps[1].update(state="running")
        row.steps, row.state, row.attempts = steps, "running", 1
        row.started_at = jobs.now() - timedelta(hours=1)
        row.heartbeat_at = jobs.now() - timedelta(hours=1)  # the worker stopped
    _drain()
    done = user.get(f"{API}/research/jobs/{job['id']}").json()
    assert done["state"] == "succeeded" and done["attempts"] == 2
    assert done["steps"][0]["detail"]["en"] == "kept"  # not run again
    # A study interrupted too often stops for good.
    worn = _create(user)
    with session_factory()() as s, s.begin():
        row = s.get(ResearchJob, uuid.UUID(worn["id"]))
        row.state, row.attempts = "running", row.max_attempts
        row.started_at = row.heartbeat_at = jobs.now() - timedelta(hours=1)
    _drain()
    failed = user.get(f"{API}/research/jobs/{worn['id']}").json()
    assert failed["state"] == "failed" and failed["error_code"] == "too_many_attempts"


def test_web_documents_with_provenance_duplicates_and_revisions(user, monkeypatch) -> None:  # noqa: ANN001
    from app.services.research import firecrawl, robots, safe_fetch

    s = get_settings()
    monkeypatch.setattr(s, "research_provider", "fake")
    monkeypatch.setattr(s, "firecrawl_api_key", SecretStr("fc-test-only"))
    monkeypatch.setattr(s, "crawl_host_interval_seconds", 0.0)
    monkeypatch.setattr(safe_fetch, "resolver", lambda host, port: ["93.184.216.34"])
    monkeypatch.setattr(robots.RobotsCache, "_read", lambda self, url: robots.Rules("missing"))
    content = {"text": "Electricity generated in 2023 reached 41,234 GWh (test fixture)."}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/map":
            return httpx.Response(200, json={"success": True, "links": []})
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "markdown": f"# Statistical Bulletin 2023\n{content['text']}",
                    "metadata": {
                        "title": "Statistical Bulletin 2023",
                        "url": "https://www.ncsi.gov.om/test-fixture/electricity",
                        "statusCode": 200,
                        "contentType": "text/html",
                    },
                },
            },
        )

    monkeypatch.setattr(
        firecrawl,
        "http_client_factory",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(handler)),
    )
    first = _create(user, source_scope="official", question="Electricity generation statistics")
    _drain()
    job = user.get(f"{API}/research/jobs/{first['id']}").json()
    assert job["state"] == "succeeded", job["steps"]
    docs = user.get(f"{API}/research/jobs/{first['id']}/documents").json()
    # The fake search also returned a news site: outside the official scope, never retrieved.
    assert [d["host"] for d in docs] == ["www.ncsi.gov.om"]
    [doc] = docs
    assert doc["status"] == "ok" and doc["retriever"] == "firecrawl" and doc["untrusted"] is True
    assert doc["source_class"] == "official" and doc["publisher"] and doc["title"]
    assert doc["reporting_period"] == "2023" and doc["retrieved_at"] and doc["sha256"]
    assert job["credits_used"] >= 1
    assert any("41,234 GWh" in e["text"] for e in job["result"]["excerpts"])
    assert all(e["status"] == "unreviewed" for e in job["result"]["excerpts"])
    # The same page again, unchanged: a duplicate; changed: a revision of the earlier one.
    second = _create(
        user, refresh=True, source_scope="official", question="Electricity generation statistics"
    )
    _drain()
    [dup] = user.get(f"{API}/research/jobs/{second['id']}/documents").json()
    assert dup["duplicate_of"] and dup["revision_of"] is None
    content["text"] = "Electricity generated in 2023 reached 41,240 GWh (revised test fixture)."
    third = _create(
        user, refresh=True, source_scope="official", question="Electricity generation statistics"
    )
    _drain()
    [rev] = user.get(f"{API}/research/jobs/{third['id']}/documents").json()
    assert rev["revision_of"] and rev["duplicate_of"] is None


def test_retrieval_failures_leave_the_study_partial(user, monkeypatch) -> None:  # noqa: ANN001
    from app.services.research import robots, safe_fetch

    s = get_settings()
    monkeypatch.setattr(s, "research_provider", "fake")
    monkeypatch.setattr(safe_fetch, "resolver", lambda host, port: ["10.0.0.7"])  # private
    monkeypatch.setattr(robots.RobotsCache, "_read", lambda self, url: robots.Rules("missing"))
    job = _create(user, source_scope="official", question="Electricity bulletin pages")
    _drain()
    done = user.get(f"{API}/research/jobs/{job['id']}").json()
    assert done["state"] == "partial"
    steps = {st["stage"]: st for st in done["steps"]}
    assert (
        steps["retrieve"]["state"] == "failed"
        and steps["retrieve"]["code"] == "no_document_retrieved"
    )
    assert steps["calculate"]["state"] == "done"  # the required steps still ran
    docs = user.get(f"{API}/research/jobs/{job['id']}/documents").json()
    assert docs and all(d["status"] == "blocked_private_address" for d in docs)


# ------------------------------------------------------------------ scheduled reports


@pytest.fixture
def admin(make_user, login):  # noqa: ANN001, ANN201
    return login(make_user(Role.ADMINISTRATOR, grants=(Permission.USER_MANAGE,)))


SCHEDULE = {
    "name": "Monthly water",
    "sector": "water",
    "question": "Water supply and demand",
    "data_mode": "synthetic",
    "frequency": "monthly",
}


def test_schedules_are_off_by_default_and_paid_runs_need_permission(
    admin, user, monkeypatch
) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.models import ReportSchedule
    from app.services.research import schedules

    assert user.get(f"{API}/admin/report-schedules").status_code == 403
    status = admin.get(f"{API}/admin/research/status").json()
    assert status["scheduler_enabled"] is False
    assert status["retrieval"]["firecrawl"] == "not_configured"
    assert "fc-" not in str(status)
    created = admin.post(f"{API}/admin/report-schedules", json=SCHEDULE).json()
    assert (
        created["enabled"] is False and created["next_run_at"] is None and created["paid"] is False
    )
    paid = admin.post(
        f"{API}/admin/report-schedules",
        json={**SCHEDULE, "source_scope": "official", "enabled": True},
    )
    assert paid.status_code == 422
    paid_ok = admin.post(
        f"{API}/admin/report-schedules", json={**SCHEDULE, "source_scope": "official"}
    ).json()
    assert admin.post(f"{API}/admin/report-schedules/{paid_ok['id']}/run").status_code == 409
    enabled = admin.put(
        f"{API}/admin/report-schedules/{created['id']}", json={"enabled": True}
    ).json()
    assert enabled["enabled"] is True and enabled["next_run_at"]
    # Due, but the server switch is off: nothing runs.
    with session_factory()() as s, s.begin():
        s.get(ReportSchedule, uuid.UUID(created["id"])).next_run_at = schedules.now() - timedelta(
            minutes=1
        )
    assert schedules.tick() == 0
    monkeypatch.setattr(get_settings(), "scheduled_reports_enabled", True)
    assert schedules.tick() == 1
    after = {r["id"]: r for r in admin.get(f"{API}/admin/report-schedules").json()}[created["id"]]
    assert after["last_run_at"] and after["next_run_at"] > after["last_run_at"]
    assert schedules.tick() == 0  # not due again until next month


def test_a_schedule_stops_at_its_monthly_credit_cap(admin) -> None:  # noqa: ANN001
    from app.db.session import session_factory
    from app.models import ResearchJob

    row = admin.post(
        f"{API}/admin/report-schedules",
        json={**SCHEDULE, "max_credits_per_run": 10, "max_credits_per_month": 15},
    ).json()
    job = admin.post(f"{API}/admin/report-schedules/{row['id']}/run")
    assert job.status_code == 202
    with session_factory()() as s, s.begin():
        s.get(ResearchJob, uuid.UUID(job.json()["id"])).credits_used = 10
    capped = admin.post(f"{API}/admin/report-schedules/{row['id']}/run")
    assert capped.status_code == 409 and capped.json()["error"]["code"] == "monthly_cap_reached"
    invalid = admin.post(
        f"{API}/admin/report-schedules",
        json={**SCHEDULE, "max_credits_per_run": 50, "max_credits_per_month": 10},
    )
    assert invalid.status_code == 422
    assert admin.delete(f"{API}/admin/report-schedules/{row['id']}").status_code == 204
