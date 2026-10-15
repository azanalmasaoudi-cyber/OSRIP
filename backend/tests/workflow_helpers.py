"""Drive the import workflow through the HTTP API, as the interface does."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

API = "/api/v1"
HEADER = (
    "indicator_code,area_code,period_start,period_end,frequency,unit_code,value,"
    "commodity_code,partner_code,flow"
)


def csv_bytes(*lines: str) -> bytes:
    return ("\n".join([HEADER, *lines]) + "\n").encode("utf-8")


def register_synthetic_source(client: TestClient) -> str:
    response = client.post(
        f"{API}/sources",
        json={
            "data_mode": "synthetic",
            "dataset_title": f"Integration-test synthetic source {uuid.uuid4().hex[:6]}",
            "geographic_coverage": "OM (national, synthetic)",
            "reuse_conditions": "Test data only.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def register_test_verified_source(client: TestClient) -> str:
    """A verified-source record that exists only in the throwaway test database.

    Its publisher and URL are explicit test placeholders (.invalid); no real
    statistic is claimed and the database is dropped after the run.
    """
    response = client.post(
        f"{API}/sources",
        json={
            "data_mode": "verified_source",
            "dataset_title": f"Integration-test verified source {uuid.uuid4().hex[:6]}",
            "publisher": "Test publisher (integration test only)",
            "url": "https://example.invalid/test-table.csv",
            "locator_kind": "direct_file",
            "access_date": "2026-09-25",
            "geographic_coverage": "OM (national)",
            "reuse_conditions": "Test placeholder.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(
    client: TestClient,
    source_id: str,
    data: bytes,
    label: str | None = None,
    filename: str = "upload.csv",
) -> Any:
    return client.post(
        f"{API}/imports",
        data={"source_id": source_id, "version_label": label or f"v-{uuid.uuid4().hex[:6]}"},
        files={"file": (filename, data, "text/csv")},
    )


def upload_validate_approve(
    client: TestClient, source_id: str, data: bytes, label: str | None = None
) -> dict:
    created = upload(client, source_id, data, label)
    assert created.status_code == 201, created.text
    import_id = created.json()["id"]
    validated = client.post(f"{API}/imports/{import_id}/validate")
    assert validated.status_code == 200, validated.text
    approved = client.post(
        f"{API}/imports/{import_id}/approve",
        json={
            "acknowledged_rejected_rows": validated.json()["rejected_row_count"],
            "note": "reviewed in test",
        },
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def observations(client: TestClient, **params: str) -> dict:
    response = client.get(f"{API}/observations", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def values_of(payload: dict, indicator: str, source_id: str | None = None) -> list[str | None]:
    return [
        o["value"]
        for s in payload["series"]
        if s["indicator"]["code"] == indicator
        and (source_id is None or s["source"]["id"] == source_id)
        for o in s["observations"]
    ]
