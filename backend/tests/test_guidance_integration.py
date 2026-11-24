"""The guided analysis's recommendations (POST /analysis/{section}/guidance) against the database:

* given only once objectives are known (chosen, or recognised in the person's own words);
* every figure quoted is one of the selection's published values, periods or counts: nothing is
  added, rounded away or estimated;
* the action follows what the published series does (rising or falling), better-evidenced actions
  first, with prerequisites, risks and the evidence OSRIP does not publish for the area;
* public, read-only, and strict about its input.

The series are SYNTHETIC, for Ash Sharqiyah South (OM-SJ) in 1940-1943, which no other module
publishes; they are superseded when the module ends.
"""

from __future__ import annotations

import re
import uuid

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration

AREA = "OM-SJ"
RISING = [100, 110, 121, 133]  # ELEC_GENERATION, GWh, 1940-1943
FALLING = [50, 45, 40, 30]  # WATER_PRODUCTION, million_m3, 1940-1943


@pytest.fixture(scope="module")
def published(database_url: str):  # noqa: ANN201
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.principal import Principal

    username, password = f"gd{uuid.uuid4().hex[:8]}", f"pw-{uuid.uuid4().hex}"
    with session_factory()() as s, s.begin():
        u = accounts.create_user(
            s, Principal(None, "t"), username=username, display_name="guidance manager",
            password=password, roles=[Role.DATA_MANAGER],
        )  # fmt: skip
        s.flush()
        for g in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), u.id, g)
    client = TestClient(create_app())
    login = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]
    rows = [
        f"ELEC_GENERATION,{AREA},{1940 + i}-01-01,{1940 + i}-12-31,annual,GWh,{v},,,"
        for i, v in enumerate(RISING)
    ]
    rows += [
        f"WATER_PRODUCTION,{AREA},{1940 + i}-01-01,{1940 + i}-12-31,annual,million_m3,{v},,,"
        for i, v in enumerate(FALLING)
    ]
    imp = upload_validate_approve(client, register_synthetic_source(client), csv_bytes(*rows))
    assert client.post(f"{API}/imports/{imp['id']}/publish").status_code == 200
    yield
    with session_factory()() as s, s.begin():
        s.execute(
            text(
                "UPDATE dataset_version SET status = 'superseded', superseded_at = now() WHERE id = :id"
            ),
            {"id": imp["version"]["id"]},
        )


def guidance(anonymous, section: str = "electricity", **body):  # noqa: ANN001, ANN201
    payload = {
        "data_mode": "synthetic", "indicator": "ELEC_GENERATION", "area": AREA, "view": "annual",
        "period_from": "1940-01-01", "period_to": "1943-12-31", "objectives": [], "note": "",
    } | body  # fmt: skip
    return anonymous.post(f"{API}/analysis/{section}/guidance", json=payload)


def texts(doc: dict) -> list[str]:
    out = [f["text"]["en"] for f in doc["facts"]]
    for a in doc["actions"]:
        out += [a["title"]["en"], a["rationale"]["en"]]
        out += [x["en"] for key in ("prerequisites", "risks", "missing_evidence") for x in a[key]]
    return out


def test_no_recommendation_before_an_objective(anonymous, published) -> None:  # noqa: ANN001
    r = guidance(anonymous)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "needs_objectives" and r.json()["actions"] == []
    # Words that name no objective leave the objectives unknown: nothing is guessed.
    r = guidance(anonymous, note="something nice")
    assert r.json()["status"] == "needs_objectives" and r.json()["note_recognised"] is False


def test_recommendations_quote_only_the_published_figures(anonymous, published) -> None:  # noqa: ANN001
    r = guidance(anonymous, objectives=["diversify", "reduce_shortages"])
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["status"] == "ok"
    assert [o["code"] for o in doc["objectives"]] == ["reduce_shortages", "diversify"]
    facts = {f["kind"]: f["text"]["en"] for f in doc["facts"]}
    assert facts["latest"] == "Latest published value: 133 gigawatt-hour (1943)."
    assert facts["change"] == "Change from 1940 to 1943: +33.0%."
    assert facts["coverage"].endswith("4 of 4; missing (not zero): 0.")
    # Every number in the text is a published value, a year, the computed change or a count.
    allowed = {str(v) for v in RISING} | {str(y) for y in range(1940, 1944)} | {"33.0", "4", "0"}
    for sentence in texts(doc):
        for number in re.findall(r"\d+(?:\.\d+)?", sentence.replace(",", "")):
            assert number in allowed, f"{number!r} in {sentence!r}"
    # Rising: the rationale says so; each action has its parts; the evidence gap comes last.
    first, second, last = doc["actions"]
    assert first["rank"] == 1 and first["objective"]["code"] == "reduce_shortages"
    assert "is rising" in first["rationale"]["en"] and first["evidence"] == "trend"
    assert first["prerequisites"] and first["risks"] and first["facts"] == ["F1", "F2"]
    assert second["objective"]["code"] == "diversify"
    assert last["evidence"] == "gap" and last["objective"] is None
    assert any(
        "Peak demand for A'Sharqiyah South is not published" in m["en"]
        for m in doc["missing_evidence"]
    )
    assert all(set(a["title"]) == {"en", "ar"} and a["title"]["ar"] for a in doc["actions"])


def test_a_falling_series_and_an_objective_in_the_persons_words(anonymous, published) -> None:  # noqa: ANN001
    r = guidance(
        anonymous, "water", indicator="WATER_PRODUCTION", note="We want less waste and leakage"
    )
    doc = r.json()
    assert doc["status"] == "ok" and doc["note_recognised"] is True
    assert [o["code"] for o in doc["objectives"]] == ["improve_efficiency"]
    assert "is falling" in doc["actions"][0]["rationale"]["en"]
    assert "Change from 1940 to 1943: -40.0%." in [f["text"]["en"] for f in doc["facts"]]


def test_one_value_gives_no_direction(anonymous, published) -> None:  # noqa: ANN001
    doc = guidance(anonymous, objectives=["strengthen"], period_from="1943-01-01").json()
    assert doc["status"] == "ok"
    assert doc["actions"][0]["evidence"] == "single_value"
    assert "no direction can be read" in doc["actions"][0]["rationale"]["en"]


def test_no_published_data_and_bad_input(anonymous, published) -> None:  # noqa: ANN001
    assert guidance(anonymous, objectives=["diversify"], area="OM-WU").json()["status"] == "no_data"
    assert guidance(anonymous, objectives=["win"]).status_code == 422
    assert guidance(anonymous, objectives=["diversify"], note="x" * 301).status_code == 422
    assert guidance(anonymous, objectives=["diversify"], indicator="NO_SUCH").status_code == 404
