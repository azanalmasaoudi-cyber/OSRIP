"""The decision brief for an axis: performance, strengths and weaknesses, regional shares,
data gaps and recommendations, all from published values (synthetic test rows here) by the
stated rules. A partner's slice never stands in for the national total; findings carry
reference ids while source names stay in the provenance list."""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def published(database_url: str) -> Iterator[dict[str, Any]]:
    from fastapi.testclient import TestClient

    from app.db.session import session_factory
    from app.main import create_app
    from app.services import accounts
    from app.services.principal import Principal

    email, password = "brief-manager@test.invalid", "pw-brief-manager-000000"
    with session_factory()() as s, s.begin():
        u = accounts.create_user(
            s,
            Principal(None, "t"),
            email=email,
            display_name="brief manager",
            password=password,
            roles=[Role.DATA_MANAGER],
        )
        s.flush()
        for g in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
            accounts.grant_permission(s, Principal(None, "t"), u.id, g)
    client = TestClient(create_app())
    assert (
        client.post(f"{API}/auth/login", json={"email": email, "password": password}).status_code
        == 200
    )
    client.headers["X-CSRF-Token"] = client.cookies["osrip_csrf"]

    def publish(*rows: str) -> str:
        imp = upload_validate_approve(client, register_synthetic_source(client), csv_bytes(*rows))
        assert client.post(f"{API}/imports/{imp['id']}/publish").status_code == 200
        return imp["version"]["id"]

    water = publish(
        "WATER_PRODUCTION,OM,2023-01-01,2023-12-31,annual,million_m3,100,,,",
        "WATER_PRODUCTION,OM,2024-01-01,2024-12-31,annual,million_m3,90,,,",
        "WATER_CONSUMPTION,OM,2023-01-01,2023-12-31,annual,million_m3,80,,,",
        "WATER_CONSUMPTION,OM,2024-01-01,2024-12-31,annual,million_m3,88,,,",
        "WATER_PRODUCTION,OM-MA,2024-01-01,2024-12-31,annual,million_m3,60,,,",
        "WATER_PRODUCTION,OM-ZU,2024-01-01,2024-12-31,annual,million_m3,30,,,",
    )
    trade = publish(
        "TRADE_MERCH_IMPORTS,OM,2023-01-01,2023-12-31,annual,million_OMR,1000,,,import",
        "TRADE_MERCH_IMPORTS,OM,2024-01-01,2024-12-31,annual,million_OMR,1100,,,import",
        "TRADE_MERCH_IMPORTS,OM,2023-01-01,2023-12-31,annual,million_OMR,100,,TUR,import",
        "TRADE_MERCH_IMPORTS,OM,2024-01-01,2024-12-31,annual,million_OMR,500,,TUR,import",
    )
    yield {"client": client, "water": water, "trade": trade}
    # Leave nothing published behind: other modules count synthetic coverage by area.
    from sqlalchemy import text

    with session_factory()() as s, s.begin():
        s.execute(
            text(
                "UPDATE dataset_version SET status = 'superseded', superseded_at = now() "
                "WHERE id IN (:water, :trade)"
            ),
            {"water": water, "trade": trade},
        )


def brief(client, section: str, version: str) -> dict[str, Any]:  # noqa: ANN001
    r = client.get(
        f"{API}/analysis/{section}/brief",
        params={"data_mode": "synthetic", "dataset_version_id": version},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_water_brief_from_published_values(published) -> None:  # noqa: ANN001
    b = brief(published["client"], "water", published["water"])
    perf = {p["indicator"]["code"]: p for p in b["performance"]}
    assert Decimal(perf["WATER_PRODUCTION"]["change_pct"]) == Decimal(-10)
    assert Decimal(perf["WATER_CONSUMPTION"]["change_pct"]) == Decimal(10)
    assert perf["WATER_PRODUCTION"]["current"]["period"] == {"en": "2024", "ar": "2024"}

    kinds = {w["kind"] for w in b["weaknesses"]}
    assert {"supply_down", "demand_outpaces_supply"} <= kinds and b["strengths"] == []
    pace = next(w for w in b["weaknesses"] if w["kind"] == "demand_outpaces_supply")
    assert "10%" in pace["text"]["en"] and "-10%" in pace["text"]["en"] and pace["rule"]["ar"]
    assert any(
        r["kind"] == "demand_pressure" and pace["id"] in r["based_on"] for r in b["recommendations"]
    )

    # Shares of the national total of the same period, unit and version.
    region = next(r for r in b["regional"] if r["indicator"]["code"] == "WATER_PRODUCTION")
    shares = {a["area"]["code"]: Decimal(a["share_pct"]) for a in region["areas"]}
    assert shares["OM-MA"].quantize(Decimal("0.1")) == Decimal("66.7")
    assert shares["OM-ZU"].quantize(Decimal("0.1")) == Decimal("33.3")
    assert region["national"] == "90"

    # Unpublished registry series and missing governorates are listed as gaps, not guessed.
    gaps = {(g["kind"], (g.get("indicator") or {}).get("code")) for g in b["gaps"]}
    assert ("not_published", "WATER_SUBSCRIBERS") in gaps
    assert ("regional", None) in gaps and b["coverage"]["governorates"] == ["OM-MA", "OM-ZU"]
    assert b["balance"]["assessable"] is False, "no published balance for water"

    # Every figure traces to a provenance entry; source names stay out of the findings.
    refs = {e["ref"] for e in b["provenance"]}
    used = [r for f in b["weaknesses"] for r in f["refs"]] + [
        p for x in b["performance"] for p in x["refs"]
    ]
    assert used and set(used) <= refs
    assert all(e["published_at"] and e["dataset_version"] for e in b["provenance"])
    title = b["provenance"][0]["source_title"]
    assert title.startswith("Integration-test synthetic source")
    assert title not in json.dumps([b["weaknesses"], b["strengths"], b["recommendations"]])


def test_brief_without_data_says_so(published) -> None:  # noqa: ANN001
    b = brief(published["client"], "electricity", published["water"])
    assert b["performance"] == [] and b["strengths"] == [] and b["weaknesses"] == []
    assert any(g["kind"] == "not_published" for g in b["gaps"])
    assert b["provenance"] == []


def test_a_partner_slice_never_replaces_the_national_total(published) -> None:  # noqa: ANN001
    b = brief(published["client"], "trade", published["trade"])
    imports = [p for p in b["performance"] if p["indicator"]["code"] == "TRADE_MERCH_IMPORTS"]
    assert [Decimal(p["change_pct"]) for p in imports] == [Decimal(10)], (
        "1000 to 1100, not 100 to 500"
    )
    assert not any(g["kind"] == "regional" for g in b["gaps"]), "trade figures are national"
