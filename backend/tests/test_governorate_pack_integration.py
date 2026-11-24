"""The staged governorate evidence pack (docs/data-imports/2026-11-governorates) through the
reviewed import workflow in the throwaway test database: both files validate with no rejected
row (indicators, units, areas and periods all known, honey included after migration 0035), and
once a data manager has approved and published them:

* honey production is published for the eleven governorates in kilograms, with its source;
* artisanal fishing for Al Batinah stays one published group, never split between North and South;
* January-October 2026 stays a year to date (period_complete false), grouped regions stay groups.

The versions are superseded afterwards, so other tests see the database as before.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import API, register_test_verified_source, upload_validate_approve

pytestmark = pytest.mark.integration

STAGED = Path(__file__).resolve().parents[2] / "docs" / "data-imports" / "2026-11-governorates"


@pytest.fixture
def manager(make_user, login):  # noqa: ANN001, ANN201
    return login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )


def _compare(client, indicator: str, **params: str) -> dict:  # noqa: ANN001
    response = client.get(
        f"{API}/areas/compare",
        params={"data_mode": "verified_source", "indicator": indicator, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_staged_pack_validates_and_publishes_as_published(manager, anonymous) -> None:  # noqa: ANN001
    from sqlalchemy import text

    from app.db.session import session_factory

    versions = []
    try:
        for name in (
            "ncsi-yearbook-2026-governorates-2025.csv",
            "ncsi-msb-2026-11-ytd.csv",
            "moc-active-commercial-records-2025.csv",
        ):
            source_id = register_test_verified_source(manager)
            approved = upload_validate_approve(manager, source_id, (STAGED / name).read_bytes())
            assert approved["rejected_row_count"] == 0, f"{name}: rows rejected"
            response = manager.post(f"{API}/imports/{approved['id']}/publish")
            assert response.status_code == 200, response.text
            versions.append(approved["version"]["id"])

        honey = _compare(anonymous, "AGRI_PROD_HONEY", period_start="2025-01-01")
        published = {
            r["area"]: Decimal(str(r["value"])) for r in honey["rows"] if r["status"] == "published"
        }
        assert len(published) == 11 and published["OM-SS"] == Decimal(248547)
        assert sum(published.values()) == Decimal(934443), "the yearbook's total"
        assert honey["unit"]["code"] == "kg"
        assert all(r["source"] for r in honey["rows"] if r["status"] == "published")

        fishing = _compare(anonymous, "FISH_LANDINGS_TRADITIONAL", period_start="2025-01-01")
        by_area = {r["area"]: r for r in fishing["rows"]}
        for half in ("OM-BS", "OM-BJ"):
            assert by_area[half]["status"] != "published", f"{half}: Al Batinah is never split"
        groups = {g["area"]: Decimal(str(g["value"])) for g in fishing.get("reporting_groups", [])}
        assert groups.get("OM-GRP-BATINAH") == Decimal(84883)

        ytd = anonymous.get(
            f"{API}/observations",
            params={
                "data_mode": "verified_source",
                "area": "OM-GRP-SHARQIYAH",
                "period_kind": "year_to_date",
            },
        )
        assert ytd.status_code == 200, ytd.text
        rows = [
            o for s in ytd.json()["series"] if s["indicator"]["code"] == "ELEC_GROSS_GENERATION"
            for o in s["observations"] if o["period_start"] == "2026-01-01"
        ]  # fmt: skip
        assert [(o["period_end"], o["value"]) for o in rows] == [("2026-10-31", "7876.3")]

        # Commercial records on record at the end of 2025: the 63 wilayats, none for governorates.
        records = _compare(
            anonymous,
            "TRADE_COMMERCIAL_REGISTRATIONS_STOCK",
            level="wilayat",
            period_start="2025-01-01",
        )
        values = {
            r["area"]: int(Decimal(str(r["value"])))
            for r in records["rows"]
            if r["status"] == "published"
        }
        assert len(values) == 63 and sum(values.values()) == 446189
        by_governorate = _compare(
            anonymous, "TRADE_COMMERCIAL_REGISTRATIONS_STOCK", period_start="2025-01-01"
        )
        assert not [r for r in by_governorate.get("rows", []) if r["status"] == "published"], (
            "no governorate total is made up"
        )
    finally:
        with session_factory()() as s, s.begin():
            for version in versions:
                s.execute(
                    text(
                        "UPDATE dataset_version SET status = 'superseded', superseded_at = now() "
                        "WHERE id = :id"
                    ),
                    {"id": version},
                )
