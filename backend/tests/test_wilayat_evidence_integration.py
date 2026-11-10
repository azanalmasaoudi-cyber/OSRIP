"""The staged wilayat evidence files (docs/data-imports/2026-11-wilayat) through the reviewed import
workflow in the throwaway test database: they validate without rejected rows, and once a data
manager has approved and published them the map's comparison shows

* the population of all 63 wilayats for 2025, adding up to 5,359,557, each with its source and
  revision status, under the population section (context, not an axis);
* new commercial registrations only for the wilayats the announcement names; every other
  wilayat has no value (never zero), and the stock at the end of June 2026 is a separate
  indicator from the new registrations of the same quarter;
* water at governorate level only: no wilayat has a water value.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import API, register_test_verified_source, upload_validate_approve

pytestmark = pytest.mark.integration

STAGED = Path(__file__).resolve().parents[2] / "docs" / "data-imports" / "2026-11-wilayat"


@pytest.fixture
def manager(make_user, login):  # noqa: ANN001, ANN201
    return login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )


def _publish(manager, filename: str) -> dict:  # noqa: ANN001
    source_id = register_test_verified_source(manager)
    approved = upload_validate_approve(manager, source_id, (STAGED / filename).read_bytes())
    assert approved["rejected_row_count"] == 0, f"{filename}: rows rejected"
    response = manager.post(f"{API}/imports/{approved['id']}/publish")
    assert response.status_code == 200, response.text
    return approved


def _compare(client, indicator: str, **params: str) -> dict:  # noqa: ANN001
    response = client.get(
        f"{API}/areas/compare",
        params={
            "data_mode": "verified_source",
            "indicator": indicator,
            "level": "wilayat",
            **params,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_published_wilayat_evidence_reaches_the_map_as_it_was_published(
    manager, anonymous
) -> None:  # noqa: ANN001
    for name in (
        "ncsi-yearbook-2026-wilayats.csv",
        "moc-new-crs-batinah-north-2025.csv",
        "moc-crs-wusta-2026q2.csv",
    ):
        _publish(manager, name)

    # Population: all 63 wilayats, 2025, adding up to the workbook's total, with provenance.
    population = _compare(anonymous, "POP_TOTAL", period_start="2025-01-01")
    assert population["status"] == "ok" and population["areas_without_value"] == 0
    rows = population["rows"]
    assert len(rows) == 63 and {r["status"] for r in rows} == {"published"}
    assert sum(Decimal(str(r["value"])) for r in rows) == Decimal(5359557)
    assert all(r["source"] and r["revision_status"] == "reported" for r in rows)
    assert population["unit"]["code"] == "person"

    # Registrations: the six Al Batinah North wilayats for 2025; the other 57 have no value.
    new_2025 = _compare(anonymous, "TRADE_NEW_COMMERCIAL_REGISTRATIONS", period_start="2025-01-01")
    with_value = {r["area"]: int(Decimal(str(r["value"]))) for r in new_2025["rows"]}
    assert set(with_value) == {f"OM-BS-0{i}" for i in range(1, 7)}
    assert sum(with_value.values()) == 4271
    assert new_2025["areas_without_value"] == 57, "no value, never zero"

    # The second quarter of 2026: new registrations and the stock on 30 June are kept apart.
    def quarter(indicator: str) -> dict[str, int]:
        result = _compare(anonymous, indicator, period_kind="quarterly", period_start="2026-04-01")
        return {r["area"]: int(Decimal(str(r["value"]))) for r in result["rows"]}

    assert quarter("TRADE_NEW_COMMERCIAL_REGISTRATIONS") == {
        "OM-WU-03": 87,
        "OM-WU-04": 74,
        "OM-WU-01": 24,
    }
    assert quarter("TRADE_COMMERCIAL_REGISTRATIONS_STOCK") == {
        "OM-WU-03": 2849,
        "OM-WU-04": 1971,
        "OM-WU-01": 1207,
        "OM-WU-02": 1163,
    }
    # The quarter is not a year: no annual 2026 registrations exist for Al Wusta.
    annual_2026 = _compare(
        anonymous, "TRADE_NEW_COMMERCIAL_REGISTRATIONS", period_start="2026-01-01"
    )
    assert not [r for r in annual_2026.get("rows", []) if r["area"].startswith("OM-WU")]

    # Water stays with the governorates: no wilayat has a water value, eleven governorates do.
    water = _compare(anonymous, "WATER_PRODUCTION", period_start="2025-01-01")
    assert not water.get("rows")
    by_governorate = anonymous.get(
        f"{API}/areas/compare",
        params={
            "data_mode": "verified_source",
            "indicator": "WATER_PRODUCTION",
            "period_start": "2025-01-01",
        },
    ).json()
    assert [r for r in by_governorate["rows"] if r["status"] == "published"]

    # Coverage names population as its own section (context), not an axis.
    coverage = anonymous.get(
        f"{API}/areas/coverage", params={"data_mode": "verified_source"}
    ).json()
    sohar = {i["code"]: i for i in coverage["areas"]["OM-BS-01"]["indicators"]}
    assert sohar["POP_TOTAL"]["section"] == "population"
    assert sohar["TRADE_NEW_COMMERCIAL_REGISTRATIONS"]["section"] == "trade"
