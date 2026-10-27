"""Uploaded datasets through the API with a database: only accounts with dataset.analyze may
upload, a dataset is visible to its owner only, the same file is stored once, limits are
enforced, a summary keeps only checked sentences and is limited per day, and deleting a
dataset removes it. The model here is a stub (no network); nothing shows a live model call."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import get_settings
from app.domain.enums import Role

CSV = """Year,Region,Generation (GWh)
2020,Muscat,10120.5
2021,Muscat,10500
2022,Muscat,11020.25
2020,Dhofar,2100
2021,Dhofar,2200
2022,Dhofar,2350
"""


def _upload(client: Any, data: str = CSV, name: str = "generation.csv") -> Any:
    return client.post("/api/v1/datasets", files={"file": (name, data.encode(), "text/csv")})


class _Stub:
    vendor, name = "stub", "stub-model"

    def structured(
        self, system: str, prompt: str, schema: dict[str, Any], name: str
    ) -> dict[str, Any]:
        assert name == "dataset_summary" and "Arabic" in system
        return {
            "overview": "تضم البيانات 6 صفوف. سترتفع إلى 99,999 في 2030.",
            "highlights": ["مسقط: من 10,120.5 في 2020 إلى 11,020.25 في 2022."],
            "caveats": [],
        }


def test_upload_analyse_summarise_and_delete(make_user, login, anonymous, monkeypatch) -> None:  # noqa: ANN001
    from app.services.datasets import store

    owner = login(make_user(Role.ANALYST))
    created = _upload(owner)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created"] is True and body["row_count"] == 6 and body["file_type"] == "csv"
    analysis = body["analysis"]
    assert {t["group"]["value"] for t in analysis["trends"]} == {"Muscat", "Dhofar"}
    assert any(v["chart"]["type"] == "line" for v in analysis["views"])
    dataset_id = body["id"]

    again = _upload(owner, name="copy.csv")
    assert again.status_code == 200 and again.json()["id"] == dataset_id, "stored once"
    assert [d["id"] for d in owner.get("/api/v1/datasets").json()] == [dataset_id]
    rows = owner.get(f"/api/v1/datasets/{dataset_id}/rows").json()
    assert rows["columns"] == ["Year", "Region", "Generation (GWh)"]
    assert rows["rows"][0] == ["2020", "Muscat", "10120.5"] and rows["truncated"] is False

    other = login(make_user(Role.ANALYST))
    assert other.get(f"/api/v1/datasets/{dataset_id}").status_code == 404, "owner only"
    assert other.get("/api/v1/datasets").json() == []
    viewer = login(make_user(Role.VIEWER))
    assert _upload(viewer).status_code == 403
    assert anonymous.get("/api/v1/datasets").status_code == 401

    monkeypatch.setattr(store, "get_provider", lambda: _Stub())
    monkeypatch.setattr(store, "get_fallback_provider", lambda: None)
    monkeypatch.setattr(get_settings(), "dataset_summaries_per_day", 1)
    summary = owner.post(f"/api/v1/datasets/{dataset_id}/summary", json={"language": "ar"})
    assert summary.status_code == 200, summary.text
    out = summary.json()
    assert out["status"] == "ok" and out["removed"] == 1
    assert "99,999" not in out["overview"] and out["overview"] == "تضم البيانات 6 صفوف."
    assert out["highlights"] == ["مسقط: من 10,120.5 في 2020 إلى 11,020.25 في 2022."]
    stored = owner.get(f"/api/v1/datasets/{dataset_id}").json()
    assert stored["summary"]["ar"]["overview"] == out["overview"]
    limited = owner.post(f"/api/v1/datasets/{dataset_id}/summary", json={"language": "en"})
    assert limited.status_code == 429

    assert owner.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
    assert owner.get(f"/api/v1/datasets/{dataset_id}").status_code == 404


@pytest.mark.parametrize(
    ("name", "data", "status", "code"),
    [
        ("data.pdf", "x", 422, "unsupported_file_type"),
        ("data.csv", "a,b\n", 422, "no_rows"),
        ("data.json", "[1, 2]", 422, "json_not_a_table"),
    ],
)
def test_unreadable_uploads_are_refused(make_user, login, name, data, status, code) -> None:  # noqa: ANN001
    client = login(make_user(Role.DATA_MANAGER))
    response = _upload(client, data, name)
    assert response.status_code == status and response.json()["error"]["code"] == code


def test_size_and_count_limits(make_user, login, monkeypatch) -> None:  # noqa: ANN001
    client = login(make_user(Role.ANALYST))
    s = get_settings()
    monkeypatch.setattr(s, "dataset_max_bytes", 50)
    too_big = _upload(client)
    assert too_big.status_code == 413 and too_big.json()["error"]["code"] == "file_too_large"
    monkeypatch.setattr(s, "dataset_max_bytes", 5 * 1024 * 1024)
    monkeypatch.setattr(s, "dataset_max_per_user", 1)
    assert _upload(client, "a\n1\n", "one.csv").status_code == 201
    second = _upload(client, "a\n2\n", "two.csv")
    assert second.status_code == 409 and second.json()["error"]["code"] == "dataset_limit"
