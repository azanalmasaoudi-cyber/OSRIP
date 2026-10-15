"""Regression tests for defects found by the release audit's performance workload.

1. A long series produced one change calculation per consecutive pair (a 29 MB
   response for 63 monthly series); changes now cover the latest pair inside the
   selected years, with a note, and the period filters select an earlier pair.
2. A section holding monthly and annual values of one indicator made report
   creation fail without explanation in the interface; the API refuses the mix
   with an explained 422 and accepts the report once a frequency is chosen.
All data are SYNTHETIC and exist only in the throwaway test database.
"""

from __future__ import annotations

import pytest

from app.domain.enums import Permission, Role
from tests.workflow_helpers import (
    API,
    csv_bytes,
    register_synthetic_source,
    upload_validate_approve,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def manager(make_user, login):  # noqa: ANN001, ANN201
    return login(
        make_user(Role.DATA_MANAGER, grants=(Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH))
    )


def publish(manager, *lines: str) -> str:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload_validate_approve(manager, source_id, csv_bytes(*lines))
    assert manager.post(f"{API}/imports/{imp['id']}/publish").status_code == 200
    return imp["version"]["id"]


def changes(client, version: str, **params: str) -> list[dict]:  # noqa: ANN001
    response = client.get(
        f"{API}/analysis/water",
        params={"data_mode": "synthetic", "dataset_version_id": version, **params},
    )
    assert response.status_code == 200, response.text
    return [
        c
        for c in response.json()["calculations"]
        if c["kind"] in ("absolute_change", "percentage_change")
    ]


def test_changes_cover_the_latest_pair_and_an_earlier_one_by_filter(manager, anonymous) -> None:  # noqa: ANN001
    version = publish(
        manager,
        "WATER_PRODUCTION,OM-BU-01,2019-01-01,2019-12-31,annual,million_m3,100,,,",
        "WATER_PRODUCTION,OM-BU-01,2020-01-01,2020-12-31,annual,million_m3,110,,,",
        "WATER_PRODUCTION,OM-BU-01,2021-01-01,2021-12-31,annual,million_m3,121,,,",
    )
    latest = changes(anonymous, version)
    assert len(latest) == 2  # one absolute, one percentage: 2020 -> 2021 only
    absolute = next(c for c in latest if c["kind"] == "absolute_change")
    assert absolute["result"]["value"] == "11"
    assert [i["value"] for i in absolute["inputs"]] == ["110", "121"]
    assert all("latest_pair_only" in {n.get("code") for n in c["notes"]} for c in latest)

    earlier = changes(anonymous, version, period_to="2020-12-31")
    absolute = next(c for c in earlier if c["kind"] == "absolute_change")
    assert absolute["result"]["value"] == "10"
    assert all(c["notes"] == [] for c in earlier)  # only two periods: no note needed


def test_mixed_frequencies_are_refused_with_a_reason_until_one_is_chosen(
    manager, make_user, login
) -> None:  # noqa: ANN001
    publish(
        manager,
        "WATER_PRODUCTION,OM-MU-01,2020-01-01,2020-12-31,annual,million_m3,12,,,",
        "WATER_PRODUCTION,OM-MU-01,2021-01-01,2021-01-31,monthly,million_m3,1.1,,,",
        "WATER_PRODUCTION,OM-MU-01,2021-02-01,2021-02-28,monthly,million_m3,1.2,,,",
    )
    analyst = login(make_user(Role.ANALYST))
    body = {"title": "Musandam water", "data_mode": "synthetic", "section": "water"}

    refused = analyst.post(f"{API}/reports", json={**body, "filters": {"area": "OM-MU-01"}})
    assert refused.status_code == 422
    error = refused.json()["error"]
    assert error["code"] == "incompatible_series"
    assert {c["frequency"] for c in error["details"]["WATER_PRODUCTION"]} == {"annual", "monthly"}

    observations = analyst.get(
        f"{API}/observations", params={"data_mode": "synthetic", "area": "OM-MU-01"}
    )
    assert observations.status_code == 422

    accepted = analyst.post(
        f"{API}/reports", json={**body, "filters": {"area": "OM-MU-01", "frequency": "monthly"}}
    )
    assert accepted.status_code == 201, accepted.text
    report = analyst.get(f"{API}/reports/{accepted.json()['id']}").json()
    assert report["filters"]["frequency"] == "monthly"
    assert {s["frequency"] for s in report["content"]["series"]} == {"monthly"}
