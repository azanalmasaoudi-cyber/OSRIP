"""Import-to-API workflow against PostgreSQL (booklet 3.12; FR01, FR02, T02, T04, T05, T07, T11).

Every step goes through the HTTP API with a signed-in data manager, so these
tests exercise routing, authorization, the service layer and database rules together.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import func, select, text

from app.domain.enums import DatasetVersionStatus, Permission, Role
from app.models import DatasetVersion, ImportRow, Observation
from tests.workflow_helpers import (
    API,
    csv_bytes,
    observations,
    register_synthetic_source,
    register_test_verified_source,
    upload,
    upload_validate_approve,
    values_of,
)

pytestmark = pytest.mark.integration

MANAGER_GRANTS = (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH)


@pytest.fixture
def manager(make_user, login):  # noqa: ANN001, ANN201
    """A data manager with the explicit approve and publish grants."""
    return login(make_user(Role.DATA_MANAGER, grants=MANAGER_GRANTS))


def count_observations(db, version_id: str) -> int:  # noqa: ANN001
    return (
        db.scalar(
            select(func.count())
            .select_from(Observation)
            .where(Observation.dataset_version_id == version_id)
        )
        or 0
    )


# ------------------------------------------------------------------ the full path


def test_upload_map_validate_preview_approve_publish_and_read(manager, anonymous, db) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    data = csv_bytes(
        "ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,48000,,,",
        "ELEC_GENERATION,OM,2002-01-01,2002-12-31,annual,GWh,50100,,,",
        "ELEC_GENERATION,OM,2003-01-01,2003-12-31,annual,MW,5,,,",  # incompatible unit
        "ELEC_GENERATION,OM,31/12/2004,2004-12-31,annual,GWh,1,,,",  # ambiguous date
        "WATER_CONSUMPTION,OM,2001-01-01,2001-12-31,annual,million_m3,,,,",  # missing value
    )

    # 1. Upload: stored privately as a draft with a suggested column mapping.
    created = upload(manager, source_id, data, "v1", filename="booklet-test.csv")
    assert created.status_code == 201, created.text
    imp = created.json()
    assert imp["version"]["status"] == "draft"
    assert imp["column_mapping"]["value"] == "value"

    # 2. Column mapping is confirmed (here: unchanged).
    mapped = manager.put(
        f"{API}/imports/{imp['id']}/mapping", json={"mapping": imp["column_mapping"]}
    )
    assert mapped.status_code == 200, mapped.text

    # 3. Validation.
    validated = manager.post(f"{API}/imports/{imp['id']}/validate").json()
    assert validated["version"]["status"] == "validated"
    assert (
        validated["valid_row_count"],
        validated["warning_row_count"],
        validated["rejected_row_count"],
    ) == (2, 1, 2)

    # 4. Error preview: row number, original value and reason for each rejected row.
    preview = manager.get(f"{API}/imports/{imp['id']}/rows", params={"outcome": "rejected"}).json()
    by_row = {r["row_number"]: r for r in preview["rows"]}
    assert set(by_row) == {4, 5}
    assert by_row[4]["raw"]["unit_code"] == "MW"
    assert by_row[4]["issues"][0]["code"] == "unit_incompatible"
    assert by_row[5]["issues"][0]["code"] == "invalid_date"
    assert "YYYY-MM-DD" in by_row[5]["issues"][0]["message"]
    report = manager.get(f"{API}/imports/{imp['id']}/errors.csv")
    assert report.status_code == 200
    assert "unit_incompatible" in report.text and "31/12/2004" in report.text

    # Nothing is public before publication.
    before = observations(anonymous, data_mode="synthetic", indicator="ELEC_GENERATION")
    assert source_id not in {s["source"]["id"] for s in before["series"]}

    # 5. Approval must acknowledge the rejected rows explicitly.
    wrong = manager.post(
        f"{API}/imports/{imp['id']}/approve", json={"acknowledged_rejected_rows": 0}
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "acknowledgement_mismatch"
    approved = manager.post(
        f"{API}/imports/{imp['id']}/approve", json={"acknowledged_rejected_rows": 2}
    )
    assert approved.json()["version"]["status"] == "approved"

    # 6. Publication.
    published = manager.post(f"{API}/imports/{imp['id']}/publish").json()
    assert published["already_published"] is False
    assert published["observations_inserted"] == 3
    version_id = published["import"]["version"]["id"]

    # 7. Public read through the API, with provenance and the missing value kept as null.
    payload = observations(anonymous, data_mode="synthetic", indicator="ELEC_GENERATION")
    assert values_of(payload, "ELEC_GENERATION", source_id) == ["48000", "50100"]
    water = observations(anonymous, data_mode="synthetic", indicator="WATER_CONSUMPTION")
    assert values_of(water, "WATER_CONSUMPTION", source_id) == [None]  # T02: missing, not 0
    series = next(s for s in payload["series"] if s["source"]["id"] == source_id)
    assert series["frequency"] == "annual" and series["unit"]["code"] == "GWh"
    assert series["dataset_version"]["id"] == version_id and series["source"]["publisher"] is None
    assert series["observations"][0]["source_row"] == "booklet-test.csv#row=2"

    # FR01: rejected rows are preserved after publication, never silently deleted.
    kept = db.scalars(
        select(ImportRow.row_number).where(
            ImportRow.import_job_id == imp["id"], ImportRow.outcome == "rejected"
        )
    ).all()
    assert sorted(kept) == [4, 5]


# ------------------------------------------------------------------ idempotent publication


def test_repeated_publication_does_not_duplicate_observations(manager, db) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload_validate_approve(
        manager,
        source_id,
        csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,48000,,,"),
    )
    first = manager.post(f"{API}/imports/{imp['id']}/publish").json()
    second = manager.post(f"{API}/imports/{imp['id']}/publish").json()
    assert (first["already_published"], second["already_published"]) == (False, True)
    assert second["observations_inserted"] == 0
    assert count_observations(db, imp["version"]["id"]) == 1


def test_concurrent_publication_requests_insert_once(manager, db) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload_validate_approve(
        manager,
        source_id,
        csv_bytes(
            "ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,48000,,,",
            "ELEC_GENERATION,OM,2002-01-01,2002-12-31,annual,GWh,50100,,,",
        ),
    )
    results: list[int] = []

    def publish() -> None:
        results.append(manager.post(f"{API}/imports/{imp['id']}/publish").status_code)

    threads = [threading.Thread(target=publish) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200, 200, 200, 200]
    assert count_observations(db, imp["version"]["id"]) == 2


# ------------------------------------------------------------------ revisions and snapshots (T05)


def test_revision_supersedes_previous_snapshot_without_double_counting(manager, anonymous) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    v1 = upload_validate_approve(
        manager,
        source_id,
        csv_bytes("WATER_CONSUMPTION,OM,2001-01-01,2001-12-31,annual,million_m3,330,,,"),
        "v1",
    )
    manager.post(f"{API}/imports/{v1['id']}/publish")
    v2 = upload_validate_approve(
        manager,
        source_id,
        csv_bytes("WATER_CONSUMPTION,OM,2001-01-01,2001-12-31,annual,million_m3,331,,,"),
        "v2",
    )
    published = manager.post(f"{API}/imports/{v2['id']}/publish").json()
    assert published["superseded_version_id"] == v1["version"]["id"]

    current = observations(anonymous, data_mode="synthetic", indicator="WATER_CONSUMPTION")
    assert values_of(current, "WATER_CONSUMPTION", source_id) == ["331"]  # one snapshot, not both
    historic = observations(
        anonymous, data_mode="synthetic", dataset_version_id=v1["version"]["id"]
    )
    assert values_of(historic, "WATER_CONSUMPTION", source_id) == [
        "330"
    ]  # explicit version still readable


# ------------------------------------------------------------------ failed publication (T11)


def test_failed_publication_rolls_back_and_keeps_previous_snapshot(manager, anonymous, db) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    v1 = upload_validate_approve(
        manager,
        source_id,
        csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,48000,,,"),
        "v1",
    )
    manager.post(f"{API}/imports/{v1['id']}/publish")
    v2 = upload_validate_approve(
        manager,
        source_id,
        csv_bytes(
            "ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,48500,,,",
            "ELEC_GENERATION,OM,2002-01-01,2002-12-31,annual,GWh,50100,,,",
        ),
        "v2",
    )

    # Simulate a database failure part-way through publication: the second
    # observation insert of v2 raises, after the first one has been written.
    with db.begin():
        db.execute(
            text(f"""
            CREATE FUNCTION test_fail_publication() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.dataset_version_id = '{v2["version"]["id"]}'
                   AND right(NEW.source_row, 5) = 'row=3' THEN
                    RAISE EXCEPTION 'simulated storage failure';
                END IF;
                RETURN NEW;
            END $$""")
        )
        db.execute(
            text(
                "CREATE TRIGGER trg_test_fail BEFORE INSERT ON observation "
                "FOR EACH ROW EXECUTE FUNCTION test_fail_publication()"
            )
        )
    try:
        failed = manager.post(f"{API}/imports/{v2['id']}/publish")
    finally:
        with db.begin():
            db.execute(text("DROP TRIGGER trg_test_fail ON observation"))
            db.execute(text("DROP FUNCTION test_fail_publication()"))

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "publication_failed"
    assert "simulated" not in failed.text  # no database internals leak
    db.expire_all()
    assert db.get(DatasetVersion, v1["version"]["id"]).status is DatasetVersionStatus.PUBLISHED
    assert db.get(DatasetVersion, v2["version"]["id"]).status is DatasetVersionStatus.APPROVED
    assert count_observations(db, v2["version"]["id"]) == 0  # nothing partial is left
    assert values_of(
        observations(anonymous, data_mode="synthetic", indicator="ELEC_GENERATION"),
        "ELEC_GENERATION",
        source_id,
    ) == ["48000"]
    detail = manager.get(f"{API}/imports/{v2['id']}").json()
    assert detail["last_error_code"] == "publication_failed"

    # Once the cause is gone, the same approved import publishes normally.
    retried = manager.post(f"{API}/imports/{v2['id']}/publish").json()
    assert retried["observations_inserted"] == 2
    assert retried["superseded_version_id"] == v1["version"]["id"]


# ------------------------------------------------------------------ guards


def test_same_file_cannot_be_uploaded_twice_for_a_source(manager) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    data = csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,48000,,,")
    assert upload(manager, source_id, data).status_code == 201
    again = upload(manager, source_id, data)
    assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate_file"


def test_all_rows_rejected_cannot_be_approved(manager) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload(
        manager, source_id, csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,MW,1,,,")
    ).json()
    manager.post(f"{API}/imports/{imp['id']}/validate")
    refused = manager.post(
        f"{API}/imports/{imp['id']}/approve", json={"acknowledged_rejected_rows": 1}
    )
    assert refused.json()["error"]["code"] == "nothing_to_publish"


def test_publication_requires_prior_approval(manager) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload(
        manager, source_id, csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,1,,,")
    ).json()
    manager.post(f"{API}/imports/{imp['id']}/validate")
    refused = manager.post(f"{API}/imports/{imp['id']}/publish")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "invalid_state"


def test_remapping_invalidates_the_previous_validation(manager) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload(
        manager, source_id, csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,1,,,")
    ).json()
    manager.post(f"{API}/imports/{imp['id']}/validate")
    remapped = manager.put(
        f"{API}/imports/{imp['id']}/mapping", json={"mapping": imp["column_mapping"]}
    ).json()
    assert remapped["version"]["status"] == "draft" and remapped["row_count"] is None


def test_oversized_and_non_csv_uploads_are_refused(manager) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    big = upload(manager, source_id, b"a,b\n" + b"1,2\n" * 1_400_000)
    assert big.status_code == 413
    wrong = upload(manager, source_id, b"PK\x03\x04", filename="data.xlsx")
    assert wrong.json()["error"]["code"] == "unsupported_format"


# ------------------------------------------------------------------ provenance and modes


def test_catalogue_page_cannot_be_registered_as_a_verified_source(manager) -> None:  # noqa: ANN001
    response = manager.post(
        f"{API}/sources",
        json={
            "data_mode": "verified_source",
            "dataset_title": "Statistics catalogue",
            "publisher": "Test publisher",
            "url": "https://example.invalid/catalogue",
            "locator_kind": "catalogue_page",
            "access_date": "2026-09-25",
            "geographic_coverage": "OM",
            "reuse_conditions": "Test.",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "catalogue_page_not_verifiable"


def test_verified_source_requires_complete_provenance(manager) -> None:  # noqa: ANN001
    response = manager.post(
        f"{API}/sources",
        json={
            "data_mode": "verified_source",
            "dataset_title": "Untraceable table",
            "geographic_coverage": "OM",
        },
    )
    assert response.json()["error"]["code"] == "provenance_incomplete"
    assert set(response.json()["error"]["details"]["missing"]) == {
        "publisher",
        "url",
        "access_date",
        "locator_kind",
        "reuse_conditions",
    }


def test_synthetic_source_cannot_have_a_publisher(manager) -> None:  # noqa: ANN001
    response = manager.post(
        f"{API}/sources",
        json={
            "data_mode": "synthetic",
            "dataset_title": "Fake",
            "publisher": "Some ministry",
            "geographic_coverage": "OM",
        },
    )
    assert response.json()["error"]["code"] == "synthetic_has_no_publisher"


def test_modes_are_separate_in_queries_and_exports(manager, anonymous) -> None:  # noqa: ANN001
    synthetic_id = register_synthetic_source(manager)
    verified_id = register_test_verified_source(manager)
    for source_id, value in ((synthetic_id, "111"), (verified_id, "222")):
        imp = upload_validate_approve(
            manager,
            source_id,
            csv_bytes(f"ELEC_CONSUMPTION,OM,2023-01-01,2023-12-31,annual,GWh,{value},,,"),
        )
        manager.post(f"{API}/imports/{imp['id']}/publish")

    # Pinned to the year this test publishes, so other tests' data cannot interfere.
    year = {"indicator": "ELEC_CONSUMPTION", "period_from": "2023-01-01", "period_to": "2023-12-31"}
    synthetic = observations(anonymous, data_mode="synthetic", **year)
    verified = observations(anonymous, data_mode="verified_source", **year)
    assert {s["source"]["id"] for s in synthetic["series"]} == {synthetic_id}
    assert {s["source"]["id"] for s in verified["series"]} == {verified_id}
    assert all(s["data_mode"] == "synthetic" for s in synthetic["series"])
    assert synthetic["label"] and verified["label"] is None

    export = anonymous.get(
        f"{API}/observations/export.csv",
        params={"data_mode": "synthetic", **year},
    )
    assert "osrip-observations-synthetic.csv" in export.headers["content-disposition"]
    assert export.text.startswith("# OSRIP export - SYNTHETIC DEMONSTRATION DATA")
    assert "222" not in export.text and ",111," in export.text

    # A version of one mode cannot be read through the other mode.
    other = anonymous.get(
        f"{API}/observations",
        params={
            "data_mode": "verified_source",
            "dataset_version_id": synthetic["series"][0]["dataset_version"]["id"],
        },
    )
    assert other.json()["error"]["code"] == "data_mode_mismatch"


def test_mixed_frequencies_for_one_indicator_are_refused(manager, anonymous) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload_validate_approve(
        manager,
        source_id,
        csv_bytes(
            "ELEC_PEAK_DEMAND,OM,2011-01-01,2011-12-31,annual,MW,5000,,,",
            "ELEC_PEAK_DEMAND,OM,2011-07-01,2011-07-31,monthly,MW,4800,,,",
        ),
    )
    manager.post(f"{API}/imports/{imp['id']}/publish")
    mixed = anonymous.get(
        f"{API}/observations", params={"data_mode": "synthetic", "indicator": "ELEC_PEAK_DEMAND"}
    )
    assert mixed.status_code == 422 and mixed.json()["error"]["code"] == "incompatible_series"
    monthly = observations(
        anonymous, data_mode="synthetic", indicator="ELEC_PEAK_DEMAND", frequency="monthly"
    )
    assert values_of(monthly, "ELEC_PEAK_DEMAND", source_id) == ["4800"]


def test_drafts_are_not_public(manager, anonymous) -> None:  # noqa: ANN001
    source_id = register_synthetic_source(manager)
    imp = upload(
        manager, source_id, csv_bytes("ELEC_GENERATION,OM,2001-01-01,2001-12-31,annual,GWh,9,,,")
    ).json()
    hidden = anonymous.get(
        f"{API}/observations",
        params={"data_mode": "synthetic", "dataset_version_id": imp["version"]["id"]},
    )
    assert hidden.status_code == 404
    assert anonymous.get(f"{API}/imports/{imp['id']}").status_code == 401


# ------------------------------------------------------------------ booklet fixtures


def test_seeded_booklet_fixture_is_retrievable_through_the_api(db, anonymous) -> None:  # noqa: ANN001
    from app.services.fixtures import seed_booklet_fixtures

    first = seed_booklet_fixtures(db)
    again = seed_booklet_fixtures(db)
    assert again.created is False and again.dataset_version_id == first.dataset_version_id

    payload = observations(
        anonymous, data_mode="synthetic", dataset_version_id=first.dataset_version_id
    )
    assert values_of(payload, "ELEC_GENERATION") == ["48000", "50100"]
    assert values_of(payload, "WATER_CONSUMPTION") == ["330", "343"]
    partners = {
        s["partner"]["code"]: s["observations"][0]["value"]
        for s in payload["series"]
        if s["indicator"]["code"] == "TRADE_QUANTITY" and s["partner"]
    }
    assert partners == {"PARTNER_A": "48000", "PARTNER_B": "20000", "PARTNER_C": "12000"}
    assert all(s["partner"]["is_fictional"] for s in payload["series"] if s["partner"])
    assert all(s["source"]["publisher"] is None for s in payload["series"])
    assert all(s["data_mode"] == "synthetic" for s in payload["series"])
