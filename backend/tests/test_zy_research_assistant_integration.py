"""Research and decision-support assistant: answer modes, backend calculations, incorrect
premises, missing data, conflicting sources, unavailable services, bilingual questions,
validated recommendation cards, saved research with briefs, the source library, governorate
comparisons, and watchlist alerts on publication.

The scripted FakeProvider and FakeSearch stand in for the model and the search service; no
request leaves the machine. Runs late (``zy``) because it publishes synthetic governorate
values that earlier modules do not expect.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def setup(monkeypatch, database_url: str):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "research_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    monkeypatch.setattr(s, "assistant_max_per_minute", 1000)
    monkeypatch.setattr(s, "assistant_max_per_hour", 1000)
    monkeypatch.setattr(s, "research_per_client_hour", 1000)
    ratelimit.reset()
    with session_factory()() as session:
        seed_booklet_fixtures(session)


@pytest.fixture(scope="module")
def manager(database_url: str):  # noqa: ANN201
    """A data manager who can approve and publish imports."""
    from fastapi.testclient import TestClient

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.principal import Principal

    email, password = f"zy-manager-{uuid.uuid4().hex[:6]}@test.invalid", "pw-zy-manager-0000"
    with session_factory()() as s, s.begin():
        user = accounts.create_user(
            s,
            Principal(None, "t"),
            email=email,
            display_name="M",
            password=password,
            roles=[Role.DATA_MANAGER],
        )
        s.flush()
        for p in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), user.id, p)
    client = TestClient(create_app())
    client.post(f"{API}/auth/login", json={"email": email, "password": password})
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    return client


def publish(manager, *lines: str, source: str | None = None) -> str:  # noqa: ANN001
    source = source or register_synthetic_source(manager)
    imp = upload_validate_approve(manager, source, csv_bytes(*lines))
    r = manager.post(f"{API}/imports/{imp['id']}/publish")
    assert r.status_code == 200, r.text
    return source


@pytest.fixture(scope="module")
def governorates(manager) -> None:  # noqa: ANN001
    """Synthetic governorate values for 2002: two published, one missing in the source."""
    publish(
        manager,
        "ELEC_GENERATION,OM-MA,2002-01-01,2002-12-31,annual,GWh,9000,,,",
        "ELEC_GENERATION,OM-ZU,2002-01-01,2002-12-31,annual,GWh,4000,,,",
        "ELEC_GENERATION,OM-BS,2002-01-01,2002-12-31,annual,GWh,,,,",
    )


@pytest.fixture(scope="module")
def sharqiyah(manager) -> None:  # noqa: ANN001
    """One synthetic series that no other test module publishes (South Sharqiyah), with the
    booklet's worked-example values, so the growth and change tools find exactly one series."""
    publish(
        manager,
        "ELEC_GENERATION,OM-SJ,2001-01-01,2001-12-31,annual,GWh,48000,,,",
        "ELEC_GENERATION,OM-SJ,2002-01-01,2002-12-31,annual,GWh,50100,,,",
    )


@pytest.fixture
def own_series(monkeypatch, sharqiyah):  # noqa: ANN001, ANN201
    """Point the scripted model's growth and change calls at the South Sharqiyah series."""
    from app.services.assistant import provider

    original = provider.FakeProvider.complete

    def patched(self, system, messages, tools):  # noqa: ANN001, ANN202
        reply = original(self, system, messages, tools)
        for block in reply["content"]:
            if block.get("name") in ("growth_rate", "compare_periods"):
                block["input"]["area"] = "OM-SJ"
        return reply

    monkeypatch.setattr(provider.FakeProvider, "complete", patched)


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def guest_ask(
    app, content: str, mode: str = "ask", language: str = "en", **extra: Any
) -> dict[str, Any]:  # noqa: ANN001
    r = _guest(app).post(
        f"{API}/assistant/guest/messages",
        json={
            "content": content,
            "language": language,
            "request_id": str(uuid.uuid4()),
            "data_mode": extra.pop("data_mode", "synthetic"),
            "mode": mode,
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["message"]


def calc(message: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in message["calculations"] if c["calculation"] == name)


# ------------------------------------------------------------------ calculations


def test_growth_rate_is_calculated_by_the_backend_in_english_and_arabic(app, own_series) -> None:  # noqa: ANN001
    en = guest_ask(app, "What was the growth of electricity generation?", mode="analyze")
    assert en["status"] == "answered" and en["mode"] == "analyze", en["content"]
    growth = calc(en, "compound_annual_growth")
    assert growth["value"].startswith("4.375") and growth["unit"] == "percent"
    assert "4.38" in en["content"] and f"[{growth['id']}]" in en["content"]
    assert growth["id"] in en["citations"]
    ar = guest_ask(app, "ما نمو توليد الكهرباء؟", mode="analyze", language="ar")
    assert ar["status"] == "answered" and "نما" in ar["content"]
    assert calc(ar, "compound_annual_growth")["value"].startswith("4.375")


def test_incorrect_premise_is_corrected_first(app, own_series) -> None:  # noqa: ANN001
    msg = guest_ask(app, "Why did electricity generation double between 2001 and 2002?")
    assert msg["status"] == "answered"
    assert msg["content"].startswith("The premise is not supported")
    assert calc(msg, "percentage_change")["value"].startswith("4.375")
    ar = guest_ask(app, "لماذا تضاعف توليد الكهرباء بين 2001 و2002؟", language="ar")
    assert ar["content"].startswith("المقدمة غير صحيحة")


def test_missing_data_is_said_not_invented(app, own_series) -> None:  # noqa: ANN001
    # Verified-source data start in 2022, so 2001-2002 growth has no published inputs.
    msg = guest_ask(
        app, "What was the growth of electricity generation?", data_mode="verified_source"
    )
    assert msg["status"] == "no_evidence"
    assert "not enough published data" in msg["content"]
    assert not any(c.get("value") for c in msg["calculations"])


# ------------------------------------------------------------------ comparisons


def test_governorate_comparison_keeps_missing_apart_from_zero(
    app, anonymous, governorates, sharqiyah
) -> None:  # noqa: ANN001
    r = anonymous.get(
        f"{API}/areas/compare", params={"indicator": "ELEC_GENERATION", "data_mode": "synthetic"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["period_start"] == "2002-01-01"
    rows = {row["area"]: row for row in body["rows"]}
    assert rows["OM-MA"]["status"] == "published" and rows["OM-MA"]["value"] == "9000"
    assert rows["OM-BS"]["status"] == "missing_in_source" and rows["OM-BS"]["value"] is None
    assert rows["OM-MU"]["status"] == "no_published_value" and rows["OM-MU"]["value"] is None
    assert rows["OM-SJ"]["value"] == "50100"
    assert body["areas_without_value"] == len(rows) - 4
    # The national total is shown on its own line and never divided among governorates.
    assert body["national"]["area"] == "OM" and body["national"]["status"] == "published"
    assert "entries" not in body
    bad = anonymous.get(
        f"{API}/areas/compare", params={"indicator": "NOPE", "data_mode": "synthetic"}
    )
    assert bad.status_code == 422
    # Wilayat level: no wilayat has its own value, and none is inferred from governorates.
    w = anonymous.get(
        f"{API}/areas/compare",
        params={"indicator": "ELEC_GENERATION", "data_mode": "synthetic", "level": "wilayat"},
    ).json()
    assert w["status"] == "no_data" or w["rows"] == []


def test_assistant_compare_mode_lists_only_published_governorates(
    app, governorates, sharqiyah
) -> None:  # noqa: ANN001
    msg = guest_ask(app, "Compare electricity generation across governorates", mode="compare")
    assert msg["status"] == "answered", msg["content"]
    assert "9000" in msg["content"] and "4000" in msg["content"]
    assert "missing in the source" in msg["content"]
    assert "no published value" in msg["content"]
    cited = {e["area"] for e in msg["evidence"] if e["kind"] == "observation"}
    assert cited == {"OM-MA", "OM-ZU", "OM-BS", "OM-SJ"}


# ------------------------------------------------------------------ recommendation cards


def test_recommendation_cards_drop_invented_benefits(app) -> None:  # noqa: ANN001
    msg = guest_ask(app, "What do you recommend for electricity generation?", mode="analyze")
    assert msg["status"] == "answered", msg["content"]
    s = msg["structured"]
    [card] = s["recommendations"]
    assert set(card) == {
        "finding",
        "evidence",
        "action",
        "expected_benefit",
        "prerequisites",
        "uncertainty",
        "citations",
    }
    assert "25%" not in str(s), "an invented saving is never shown"
    assert s["withheld"]["recommendations"] == 1
    # The hypothesis driver is kept and labelled; an 'evidence' driver without citations is not.
    assert [(d["driver"], d["basis"]) for d in s["drivers"]] == [("population", "hypothesis")]
    assert s["withheld"]["drivers"] == 1
    assert s["evidence_points"][0]["citations"] and s["hypotheses"] and s["assumptions"]
    # The same question in Ask mode gets no cards.
    ask = guest_ask(app, "What do you recommend for electricity generation?", mode="ask")
    assert "recommendations" not in ask["structured"]


# ------------------------------------------------------------------ research


def test_conflicting_sources_are_both_reported_with_bilingual_search(app) -> None:  # noqa: ANN001
    msg = guest_ask(app, "Is there a conflict in electricity generation figures?", mode="research")
    assert msg["status"] == "answered", msg["content"]
    [conflict] = msg["structured"]["conflicts"]
    assert [v["value_text"] for v in conflict["values"]] == ["41,234", "40,000"]
    [search] = [e for e in msg["evidence"] if e["kind"] == "search"]
    assert search["status"] == "ok"
    assert search["queries"] == [
        {"query": "electricity generated 2023 Oman", "language": "en"},
        {"query": "الكهرباء المولدة 2023 عمان", "language": "ar"},
    ]
    assert search["languages"] == ["ar", "en"]
    classes = {e["source_class"] for e in msg["evidence"] if e["kind"] == "web"}
    assert classes == {"official", "secondary"}


def test_unavailable_services_are_reported_honestly(app, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    s = get_settings()
    # Research mode without a search provider: the reply records that no search was made.
    monkeypatch.setattr(s, "research_provider", "none")
    msg = guest_ask(app, "Research electricity generation in Oman", mode="research")
    searches = [e for e in msg["evidence"] if e["kind"] == "search"]
    assert [e["status"] for e in searches] == ["not_configured"]
    assert not [e for e in msg["evidence"] if e["kind"] == "web"]
    # A failing search (the provider is configured but the call fails).
    monkeypatch.setattr(s, "research_provider", "fake")
    failed = guest_ask(app, "web search please fail", mode="research")
    assert failed["status"] == "no_evidence" and "failed" in failed["content"]
    # No model service: a labelled record lookup, never an AI answer.
    monkeypatch.setattr(s, "assistant_provider", "none")
    lookup = guest_ask(app, "What is the latest electricity generation?", mode="analyze")
    assert lookup["ai_generated"] is False and lookup["status"] in ("lookup", "unavailable")


# ------------------------------------------------------------------ saved research and briefs


def test_saved_research_brief_and_ownership(app, make_user, login) -> None:  # noqa: ANN001
    owner = login(make_user(Role.VIEWER))
    conv = owner.post(
        f"{API}/assistant/conversations", json={"language": "en", "data_mode": "synthetic"}
    ).json()["id"]
    r = owner.post(
        f"{API}/assistant/conversations/{conv}/messages",
        json={
            "content": "What do you recommend for electricity generation?",
            "language": "en",
            "mode": "analyze",
        },
    )
    assert r.status_code == 201, r.text
    message = r.json()
    assert message["structured"]["recommendations"]
    # Mode and validated parts are stored with the message.
    stored = owner.get(f"{API}/assistant/conversations/{conv}").json()["messages"][-1]
    assert stored["mode"] == "analyze" and stored["structured"] == message["structured"]

    saved = owner.post(
        f"{API}/library/saved",
        json={"message_id": message["id"], "title": "Capacity <check>", "note": "for the team"},
    )
    assert saved.status_code == 201, saved.text
    sid = saved.json()["id"]
    again = owner.post(f"{API}/library/saved", json={"message_id": message["id"]})
    assert again.json()["id"] == sid, "saving twice keeps one item"
    listed = owner.get(f"{API}/library/saved").json()
    assert [i["id"] for i in listed] == [sid] and listed[0]["recommendation_count"] == 1
    assert listed[0]["question"] == "What do you recommend for electricity generation?"
    full = owner.get(f"{API}/library/saved/{sid}").json()
    assert full["snapshot"]["content"] == message["content"]

    md = owner.get(f"{API}/library/saved/{sid}/brief", params={"format": "md"})
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "attachment" in md.headers["content-disposition"]
    body = md.text
    for heading in ("## Answer", "## Recommendations", "## Sources and evidence", "## Limitations"):
        assert heading in body
    assert "25%" not in body and "Period covered" in body and "Published" in body
    html = owner.get(f"{API}/library/saved/{sid}/brief").text
    assert "<script" not in html and "Capacity &lt;check&gt;" in html
    assert (
        "default-src 'none'"
        in owner.get(f"{API}/library/saved/{sid}/brief").headers["content-security-policy"]
    )

    renamed = owner.patch(f"{API}/library/saved/{sid}", json={"title": "  Capacity   review "})
    assert renamed.json()["title"] == "Capacity review"
    # Someone else cannot see, download, change or delete it, nor save the owner's reply.
    other = login(make_user(Role.VIEWER))
    assert other.get(f"{API}/library/saved/{sid}").status_code == 404
    assert other.get(f"{API}/library/saved/{sid}/brief").status_code == 404
    assert other.delete(f"{API}/library/saved/{sid}").status_code == 404
    assert other.post(f"{API}/library/saved", json={"message_id": message["id"]}).status_code == 404
    assert _guest(app).get(f"{API}/library/saved").status_code == 401
    assert owner.delete(f"{API}/library/saved/{sid}").status_code == 204
    assert owner.get(f"{API}/library/saved").json() == []


# ------------------------------------------------------------------ source library


def _candidate(db, url: str, source_class: str, status: str) -> None:  # noqa: ANN001
    with db.begin():
        db.execute(
            text(
                "INSERT INTO research_candidate (status, domain, indicator, value, value_text, unit,"
                " geography, period_label, publisher, source_title, source_url, source_class,"
                " excerpt, retrieved_at, search_provider, language, reviewed_at, review_note)"
                " VALUES (:status, 'water', 'Water produced', 123, '123', 'million m3', 'Oman',"
                " '2023', 'Test publisher', 'Test page', :url, :cls,"
                " 'Water produced: 123 million m3.', now(), 'test', 'en',"
                " CASE WHEN :status = 'pending' THEN NULL ELSE now() END,"
                " CASE WHEN :status = 'pending' THEN NULL ELSE 'checked in test' END)"
            ),
            {"status": status, "url": url, "cls": source_class},
        )


def test_source_library_hides_unreviewed_web_sources(app, db, anonymous, make_user, login) -> None:  # noqa: ANN001
    accepted = f"https://www.ncsi.gov.om/zy-{uuid.uuid4().hex[:6]}"
    pending = f"https://www.mdpi.com/zy-{uuid.uuid4().hex[:6]}"
    _candidate(db, accepted, "official", "accepted")
    _candidate(db, pending, "research", "pending")
    public = anonymous.get(f"{API}/library/sources").json()
    assert public["note"]["en"] and public["note"]["ar"]
    web = {s["url"]: s for s in public["sources"] if s["kind"] == "web_found"}
    assert accepted in web and pending not in web, "unreviewed sources are not public"
    assert web[accepted]["figures_accepted"] == 1 and web[accepted]["figures_pending"] is None
    reviewer = login(make_user(Role.DATA_MANAGER, grants=(Permission.RESEARCH_REVIEW,)))
    seen = reviewer.get(f"{API}/library/sources", params={"source_class": "research"}).json()
    found = {s["url"]: s for s in seen["sources"] if s["kind"] == "web_found"}
    assert pending in found and found[pending]["figures_pending"] == 1
    assert all(s["source_class"] == "research" for s in found.values())
    assert not [s for s in seen["sources"] if s["kind"] != "web_found"]
    datasets = [
        s
        for s in anonymous.get(f"{API}/library/sources").json()["sources"]
        if s["kind"] == "dataset"
    ]
    assert all(s["published_records"] > 0 for s in datasets)


# ------------------------------------------------------------------ watchlist and alerts


def test_watchlist_alerts_on_publication(app, db, manager, make_user, login, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import get_settings

    person = make_user(Role.VIEWER)
    viewer = login(person)
    item = viewer.post(
        f"{API}/watchlist",
        json={"indicator": "ELEC_GENERATION", "area": "OM-MU", "data_mode": "synthetic"},
    )
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]
    assert item.json()["latest"] is None, "no value yet: nothing is shown as zero"
    rules = {
        kind: viewer.post(
            f"{API}/watchlist/{item_id}/rules", json={"kind": kind, "threshold": threshold}
        ).json()
        for kind, threshold in (("new_data", None), ("above", "100"), ("below", "50"))
    }
    assert (
        viewer.post(f"{API}/watchlist/{item_id}/rules", json={"kind": "above"}).status_code == 422
    )
    off = viewer.patch(f"{API}/alerts/rules/{rules['below']['id']}", json={"enabled": False})
    assert off.json()["enabled"] is False
    # E-mail needs configured delivery and a confirmed address.
    monkeypatch.setattr(get_settings(), "email_backend", "disabled")
    no_mail = viewer.post(
        f"{API}/watchlist/{item_id}/rules", json={"kind": "new_data", "channel": "email"}
    )
    assert no_mail.status_code == 503 and no_mail.json()["error"]["code"] == "email_not_configured"
    monkeypatch.setattr(get_settings(), "email_backend", "outbox")
    with db.begin():
        db.execute(
            text("UPDATE app_user SET email_verified_at = NULL WHERE id = :u"), {"u": person.id}
        )
    unverified = viewer.post(
        f"{API}/watchlist/{item_id}/rules", json={"kind": "new_data", "channel": "email"}
    )
    assert unverified.status_code == 422
    with db.begin():
        db.execute(
            text("UPDATE app_user SET email_verified_at = now() WHERE id = :u"),
            {"u": person.id},
        )
    email_rule = viewer.post(
        f"{API}/watchlist/{item_id}/rules", json={"kind": "new_data", "channel": "email"}
    )
    assert email_rule.status_code == 201, email_rule.text

    source = publish(manager, "ELEC_GENERATION,OM-MU,2003-01-01,2003-12-31,annual,GWh,150,,,")
    events = viewer.get(f"{API}/alerts").json()
    kinds = sorted(e["kind"] for e in events["events"])
    assert kinds == ["above", "new_data", "new_data"], "the disabled 'below' rule stays silent"
    assert events["unread"] == 3
    above = next(e for e in events["events"] if e["kind"] == "above")
    assert above["value"] == "150" and above["unit"] == "GWh" and above["threshold"] == "100"
    assert "above your threshold" in above["message"]["en"] and above["message"]["ar"]
    deliveries = sorted(e["delivery"] for e in events["events"])
    assert deliveries == ["email_sent", "in_app", "in_app"]
    with db.begin():
        sent = db.execute(
            text("SELECT count(*) FROM email_outbox WHERE purpose = 'alert' AND to_address = :e"),
            {"e": person.email},
        ).scalar()
    assert sent == 1

    # Republishing the same value is not new; a revised value is reported as revised.
    publish(
        manager,
        "ELEC_GENERATION,OM-MU,2003-01-01,2003-12-31,annual,GWh,150,,,",
        "ELEC_GENERATION,OM-DA,2003-01-01,2003-12-31,annual,GWh,10,,,",  # not watched
        source=source,
    )
    assert viewer.get(f"{API}/alerts").json()["unread"] == 3
    publish(manager, "ELEC_GENERATION,OM-MU,2003-01-01,2003-12-31,annual,GWh,40,,,", source=source)
    latest = viewer.get(f"{API}/alerts").json()["events"]
    assert any("Revised published value" in e["message"]["en"] for e in latest)
    assert not any(e["kind"] == "above" and e["value"] == "40" for e in latest)

    watched = viewer.get(f"{API}/watchlist").json()
    assert watched[0]["latest"]["value"] == "40"
    marked = viewer.post(f"{API}/alerts/read", json={})
    assert marked.json()["marked"] >= 3 and viewer.get(f"{API}/alerts").json()["unread"] == 0
    # Another user cannot change these rules.
    other = login(make_user(Role.VIEWER))
    assert (
        other.patch(
            f"{API}/alerts/rules/{rules['above']['id']}", json={"enabled": False}
        ).status_code
        == 404
    )
    assert viewer.delete(f"{API}/watchlist/{item_id}").status_code == 204
    assert viewer.get(f"{API}/watchlist").json() == []
