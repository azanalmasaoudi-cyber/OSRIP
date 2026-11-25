# ruff: noqa: E501 - request and response lines are kept whole for readability
"""The official outlook and the annual side-by-side table against the database:

* migration 0036 defines the utility's scope (10 governorates, Dhofar excluded) and measures;
* the database refuses an observed or estimated outlook item dated in or after its statement's year;
* items are staged as pending (staging twice changes nothing), only people allowed to approve
  imports see and decide them, each decision is audited, and the public sees approved items only;
* the annual table keeps net actual consumption and electricity distributed apart, marks
  provisional years and gives the server's year-on-year change;
* Al Mulhim answers about planned desalination with the items' evidence classes.

Test data: outlook items read from docs/data-imports/2026-11-electricity-water/outlook-items.json
(the real verified items, removed afterwards), and SYNTHETIC national electricity for 1990-1993,
superseded afterwards.
"""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import API, register_synthetic_source, upload_validate_approve

pytestmark = pytest.mark.integration

ITEMS = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "data-imports"
        / "2026-11-electricity-water"
        / "outlook-items.json"
    ).read_text(encoding="utf-8")
)
BATCH = f"test-outlook-{uuid.uuid4().hex[:6]}"


@pytest.fixture
def manager(make_user, login):  # noqa: ANN001, ANN201
    return login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )


@pytest.fixture
def viewer(make_user, login):  # noqa: ANN001, ANN201
    return login(make_user(Role.VIEWER))


@pytest.fixture
def cleanup(database_url: str):  # noqa: ANN201
    yield
    from sqlalchemy import text

    from app.db.session import session_factory

    with session_factory()() as s, s.begin():
        s.execute(text("DELETE FROM outlook_item WHERE batch_label LIKE 'test-outlook-%'"))


def test_the_migration_defines_the_utility_scope_and_measures(database_url: str) -> None:
    from sqlalchemy import text

    from app.db.session import session_factory

    with session_factory()() as s, s.begin():
        members = {r[0] for r in s.execute(text(
            "SELECT m.code FROM area_group_member gm JOIN area g ON g.id = gm.group_area_id JOIN area m ON m.id = gm.member_area_id WHERE g.code = 'OM-GRP-NWS'"))}  # fmt: skip
        codes = {
            r[0]
            for r in s.execute(text("SELECT code FROM indicator WHERE code LIKE 'WATER_%_UTILITY'"))
        }
    assert len(members) == 10 and "OM-ZU" not in members
    assert codes == {"WATER_SUPPLY_UTILITY", "WATER_DELIVERED_UTILITY"}


def test_the_database_refuses_an_observed_2032(database_url: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.db.session import session_factory

    item = next(
        i for i in ITEMS if i["metric_code"] == "ELEC_PEAK_DEMAND_MIS" and i["year"] == 2032
    )
    with (
        pytest.raises(IntegrityError, match="outlook_observed_before_issue"),
        session_factory()() as s,
        s.begin(),
    ):
        s.execute(text(
            "INSERT INTO outlook_item (section, metric_code, metric_en, metric_ar, year, value, unit, scope_en, scope_ar, evidence_class, "
            "source_title, source_publisher, source_url, source_locator, retrieved_on, issue_year, batch_label) VALUES ('electricity', "
            ":code, 'x', 'x', 2032, 1, 'MW', 'x', 'x', 'observed', 't', 'p', 'https://x.invalid/', 'p', '2026-11-24', 2026, :batch)"),
            {"code": item["metric_code"], "batch": BATCH})  # fmt: skip


def test_staging_review_permissions_and_the_public_view(
    manager, viewer, anonymous, cleanup
) -> None:  # noqa: ANN001
    # Staging: pending, nothing public yet; staging again changes nothing.
    assert anonymous.post(
        f"{API}/outlook/batches", json={"batch_label": BATCH, "items": ITEMS}
    ).status_code in (401, 403)
    assert (
        viewer.post(
            f"{API}/outlook/batches", json={"batch_label": BATCH, "items": ITEMS}
        ).status_code
        == 403
    )
    staged = manager.post(f"{API}/outlook/batches", json={"batch_label": BATCH, "items": ITEMS})
    assert staged.status_code == 201, staged.text
    assert staged.json() == {"items": 19, "inserted": 19, "already_staged": 0}
    assert (
        manager.post(f"{API}/outlook/batches", json={"batch_label": BATCH, "items": ITEMS}).json()[
            "inserted"
        ]
        == 0
    )
    assert anonymous.get(f"{API}/outlook", params={"section": "water"}).json()["items"] == []
    # An invalid item is refused as a whole.
    bad = [{**ITEMS[0], "metric_code": "X_TEST", "evidence_class": "observed", "year": 2031}]
    assert (
        manager.post(
            f"{API}/outlook/batches", json={"batch_label": BATCH, "items": bad}
        ).status_code
        == 422
    )

    # Review: only people allowed to approve imports; every decision recorded; once only.
    assert viewer.get(f"{API}/outlook/review").status_code == 403
    pending = manager.get(f"{API}/outlook/review", params={"section": "water"}).json()["items"]
    water = [i for i in pending if i["batch"] == BATCH]
    assert len(water) == 9 and {i["review_status"] for i in water} == {"pending"}
    ghubrah = next(i for i in water if i["metric"]["code"] == "WATER_PLANT_GHUBRAH_III")
    sohar = next(i for i in water if i["metric"]["code"] == "WATER_PLANT_SOHAR_ADDITIONAL")
    assert (
        viewer.post(
            f"{API}/outlook/{ghubrah['id']}/review", json={"decision": "approved"}
        ).status_code
        == 403
    )
    approved = manager.post(
        f"{API}/outlook/{ghubrah['id']}/review",
        json={"decision": "approved", "note": "checked p. 4"},
    )
    assert approved.status_code == 200 and approved.json()["review_status"] == "approved"
    assert (
        manager.post(
            f"{API}/outlook/{ghubrah['id']}/review", json={"decision": "rejected"}
        ).status_code
        == 409
    )
    assert (
        manager.post(
            f"{API}/outlook/{sohar['id']}/review", json={"decision": "approved"}
        ).status_code
        == 200
    )

    # The public: approved items only, each with its class; a plan is never "achieved".
    public = anonymous.get(f"{API}/outlook", params={"section": "water"}).json()
    shown = {i["metric"]["code"]: i for i in public["items"] if i["batch"] == BATCH}
    assert set(shown) == {"WATER_PLANT_GHUBRAH_III", "WATER_PLANT_SOHAR_ADDITIONAL"}
    assert (
        shown["WATER_PLANT_GHUBRAH_III"]["evidence_class"] == "planned"
        and shown["WATER_PLANT_GHUBRAH_III"]["achieved"] is False
    )
    assert shown["WATER_PLANT_SOHAR_ADDITIONAL"]["class_label"]["en"] == "Under consideration"
    assert (
        shown["WATER_PLANT_GHUBRAH_III"]["source"]["sha256"]
        and shown["WATER_PLANT_GHUBRAH_III"]["unit"]["code"] == "m3_per_day"
    )

    from sqlalchemy import text

    from app.db.session import session_factory

    with session_factory()() as s, s.begin():
        actions = [r[0] for r in s.execute(text(
            "SELECT action FROM audit_event WHERE action LIKE 'outlook.%' AND (entity_id = :g OR entity_id = :b) ORDER BY occurred_at"),
            {"g": ghubrah["id"], "b": BATCH})]  # fmt: skip
    assert "outlook.stage" in actions and "outlook.approved" in actions


def test_al_mulhim_gives_planned_desalination_with_its_class(
    manager, app, cleanup, monkeypatch
) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    from app.core import ratelimit
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "assistant_provider", "fake")
    monkeypatch.setattr(s, "guest_asks_per_minute", 1000)
    monkeypatch.setattr(s, "guest_asks_per_client_hour", 1000)
    monkeypatch.setattr(s, "guest_sessions_per_client_hour", 1000)
    ratelimit.reset()
    assert (
        manager.post(
            f"{API}/outlook/batches", json={"batch_label": BATCH, "items": ITEMS}
        ).status_code
        == 201
    )
    for i in manager.get(f"{API}/outlook/review", params={"section": "water"}).json()["items"]:
        if i["batch"] == BATCH:
            manager.post(f"{API}/outlook/{i['id']}/review", json={"decision": "approved"})
    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    r = client.post(f"{API}/assistant/guest/messages", json={
        "content": "Which desalination projects are planned?", "language": "en", "request_id": str(uuid.uuid4()),
        "data_mode": "verified_source", "mode": "auto"})  # fmt: skip
    assert r.status_code == 201, r.text
    message = r.json()["message"]
    assert message["status"] == "answered", message["content"]
    assert message["structured"]["intent"] == "outlook"
    classes = {
        i["metric"]["code"]: i["evidence_class"] for i in message["structured"]["outlook"]["items"]
    }
    assert classes == {
        "WATER_PLANT_DHOFAR_2030": "planned",
        "WATER_PLANT_GHUBRAH_III": "planned",
        "WATER_PLANT_SOHAR_ADDITIONAL": "under_consideration",
    }
    assert "planned, not in operation" in message["content"]
    assert "under consideration" in message["content"]
    [cited] = [e for e in message["evidence"] if e["kind"] == "outlook"]
    assert cited["data_status"] == "official_outlook"


def test_the_annual_table_keeps_consumption_and_distribution_apart(manager, anonymous) -> None:  # noqa: ANN001
    from sqlalchemy import text

    from app.db.session import session_factory

    header = (
        "indicator_code,area_code,period_start,period_end,frequency,unit_code,value,revision_status"
    )
    lines = [header]
    for code, values in (
        ("ELEC_CONSUMPTION", (300.5, 320.0, 340.0, 360.0)),
        ("ELEC_DISTRIBUTION", (298.0, 320.0, 340.0, 360.0)),
    ):
        for i, v in enumerate(values):
            y = 1990 + i
            lines.append(
                f"{code},OM,{y}-01-01,{y}-12-31,annual,GWh,{v},{'provisional' if y == 1993 else 'reported'}"
            )
    imp = upload_validate_approve(
        manager, register_synthetic_source(manager), ("\n".join(lines) + "\n").encode("utf-8")
    )
    assert manager.post(f"{API}/imports/{imp['id']}/publish").status_code == 200
    try:
        r = anonymous.get(
            f"{API}/series/annual-table",
            params={
                "section": "electricity",
                "data_mode": "synthetic",
                "year_from": 1990,
                "year_to": 1993,
            },
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["years"] == ["1990", "1991", "1992", "1993"]
        totals = {row["indicator"]["code"]: row for g in doc["groups"] for row in g["rows"]}
        consumption, distribution = totals["ELEC_CONSUMPTION"], totals["ELEC_DISTRIBUTION"]
        assert [c["value"] for c in consumption["cells"]] == ["300.5", "320", "340", "360"]
        assert [c["value"] for c in distribution["cells"]] == ["298", "320", "340", "360"], (
            "two indicators, never merged"
        )
        assert [c["provisional"] for c in consumption["cells"]] == [False, False, False, True]
        assert consumption["cells"][1]["change_percent"].startswith("6.49"), (
            "the server's year-on-year change"
        )
        assert any("different published indicators" in n["en"] for n in doc["notes"])
        exported = anonymous.get(
            f"{API}/series/annual-table.csv",
            params={"section": "electricity", "data_mode": "synthetic", "year_from": 1990, "year_to": 1993},
        )  # fmt: skip
        assert exported.status_code == 200 and exported.headers["content-type"].startswith(
            "text/csv"
        )
        records = list(csv.reader(exported.text.lstrip("\ufeff").splitlines()))
        assert any(
            r[0].startswith("#") and "different published indicators" in r[0] for r in records
        ), "the notes as comment lines"
        cells = {(r[2], r[5]): r for r in records if r[:2] == ["electricity", "totals"]}
        assert cells[("ELEC_CONSUMPTION", "1990")][6] == "300.5"
        assert cells[("ELEC_DISTRIBUTION", "1990")][6] == "298", "the CSV keeps the two apart"
        assert cells[("ELEC_CONSUMPTION", "1993")][11] == "true", "provisional"
        assert cells[("ELEC_CONSUMPTION", "1991")][13].startswith("6.49")
        assert (
            anonymous.get(
                f"{API}/series/annual-table", params={"section": "trade", "data_mode": "synthetic"}
            ).status_code
            == 404
        )
    finally:
        with session_factory()() as s, s.begin():
            s.execute(
                text(
                    "UPDATE dataset_version SET status = 'superseded', superseded_at = now() WHERE id = :id"
                ),
                {"id": imp["version"]["id"]},
            )
