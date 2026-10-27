"""Research and dataset reports through the API with a database: created only from the
person's own dataset or verified answer, frozen, private, exported as PDF, Excel and CSV,
and deletable; platform reports export as PDF and Excel too. No model is called here."""

from __future__ import annotations

import io
import uuid
import zipfile
from typing import Any

import pytest

from app.domain.enums import DataMode, Role

CSV = """Year,Region,Generation (GWh)
2020,Muscat,10120.5
2021,Muscat,10500
2022,Muscat,11020.25
2020,Dhofar,2100
2021,Dhofar,2200
2022,Dhofar,=2350
"""


def _pdf_ok(response: Any) -> None:
    """A PDF, or (on a machine without a suitable font) the documented 503."""
    if response.status_code == 503:
        assert response.json()["error"]["code"] == "pdf_font_missing"
        return
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-") and b"%%EOF" in response.content[-32:]


def _answer(user_id: uuid.UUID, status: str = "answered") -> int:
    from app.db.session import session_factory
    from app.models import AssistantConversation, AssistantMessage

    with session_factory()() as s, s.begin():
        conversation = AssistantConversation(user_id=user_id, title="t", language="en",
                                             data_mode=DataMode.VERIFIED_SOURCE)  # fmt: skip
        s.add(conversation)
        s.flush()
        s.add(AssistantMessage(conversation_id=conversation.id, role="user",
                               content="What was gross generation in January to July 2026?"))  # fmt: skip
        answer = AssistantMessage(
            conversation_id=conversation.id, role="assistant", status=status,
            content="Gross generation was 31,732.5 GWh [E1].", citations=["E1"],
            evidence=[{"id": "E1", "kind": "web", "title": "NCSI release", "url": "https://www.ncsi.gov.om/news/366",
                       "publisher": {"en": "NCSI", "ar": "المركز"}, "published": "2026-09-01",
                       "retrieved_at": "2026-10-25T10:00:00+00:00", "content_kind": "page_excerpt"}],
            structured={}, model="deepseek-flash",
        )  # fmt: skip
        s.add(answer)
        s.flush()
        return answer.id


def test_dataset_report_is_frozen_private_and_exported(make_user, login) -> None:  # noqa: ANN001
    person = make_user(Role.ANALYST)
    client = login(person)
    dataset = client.post(
        "/api/v1/datasets", files={"file": ("gen.csv", CSV.encode(), "text/csv")}
    ).json()
    created = client.post(
        f"/api/v1/datasets/{dataset['id']}/report",
        json={"language": "ar", "title": "توليد الكهرباء", "questions": ["كيف تغير التوليد؟"]},
    )
    assert created.status_code == 201, created.text
    report = created.json()
    assert (report["kind"], report["language"], report["dataset_id"]) == (
        "dataset",
        "ar",
        dataset["id"],
    )
    full = client.get(f"/api/v1/analysis-reports/{report['id']}").json()
    content = full["content"]
    assert content["schema"] == "osrip.report/1" and content["sections"][0]["blocks"][0][
        "items"
    ] == ["كيف تغير التوليد؟"]
    assert [r["id"] for r in client.get("/api/v1/analysis-reports").json()] == [report["id"]]

    _pdf_ok(client.get(f"/api/v1/analysis-reports/{report['id']}/export.pdf"))
    xlsx = client.get(f"/api/v1/analysis-reports/{report['id']}/export.xlsx")
    assert xlsx.status_code == 200 and zipfile.is_zipfile(io.BytesIO(xlsx.content))
    report_csv = client.get(f"/api/v1/analysis-reports/{report['id']}/export.csv")
    assert report_csv.status_code == 200 and report_csv.text.startswith("﻿")

    rows_csv = client.get(f"/api/v1/datasets/{dataset['id']}/export.csv")
    assert rows_csv.status_code == 200
    lines = rows_csv.text.lstrip("﻿").splitlines()
    assert lines[0] == "Year,Region,Generation (GWh)" and lines[-1] == "2022,Dhofar,'=2350", (
        "formula text neutralised"
    )
    book = client.get(f"/api/v1/datasets/{dataset['id']}/export.xlsx?language=en")
    assert book.status_code == 200
    with zipfile.ZipFile(io.BytesIO(book.content)) as z:
        assert "<f>" not in z.read("xl/worksheets/sheet1.xml").decode()

    other = login(make_user(Role.ANALYST))
    assert other.get(f"/api/v1/analysis-reports/{report['id']}").status_code == 404
    assert other.get(f"/api/v1/analysis-reports/{report['id']}/export.pdf").status_code == 404
    assert other.post(f"/api/v1/datasets/{dataset['id']}/report", json={}).status_code == 404

    from app.db.session import session_factory
    from app.models import AnalysisReport

    with pytest.raises(Exception, match="frozen"), session_factory()() as s, s.begin():
        row = s.get(AnalysisReport, uuid.UUID(report["id"]))
        row.title = "changed"
    assert client.delete(f"/api/v1/analysis-reports/{report['id']}").status_code == 204
    assert client.get(f"/api/v1/analysis-reports/{report['id']}").status_code == 404


def test_research_report_only_from_ones_own_verified_answer(make_user, login, anonymous) -> None:  # noqa: ANN001
    person = make_user(Role.VIEWER)
    client = login(person)
    message_id = _answer(person.id)
    created = client.post(
        f"/api/v1/assistant/messages/{message_id}/report", json={"language": "en"}
    )
    assert created.status_code == 201, created.text
    report = client.get(f"/api/v1/analysis-reports/{created.json()['id']}").json()
    content = report["content"]
    assert report["title"] == "What was gross generation in January to July 2026?"
    assert content["sections"][1]["blocks"][0]["text"] == "Gross generation was 31,732.5 GWh [1]."
    assert content["references"][0]["url"] == "https://www.ncsi.gov.om/news/366"
    _pdf_ok(client.get(f"/api/v1/analysis-reports/{report['id']}/export.pdf"))

    withheld = _answer(person.id, status="unverified")
    refused = client.post(f"/api/v1/assistant/messages/{withheld}/report", json={})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "answer_not_verified"
    stranger = login(make_user(Role.ANALYST))
    assert (
        stranger.post(f"/api/v1/assistant/messages/{message_id}/report", json={}).status_code == 404
    )
    assert (
        anonymous.post(f"/api/v1/assistant/messages/{message_id}/report", json={}).status_code
        == 401
    )


def test_platform_reports_export_as_pdf_and_excel(make_user, login) -> None:  # noqa: ANN001
    client = login(make_user(Role.ANALYST))
    created = client.post(
        "/api/v1/reports",
        json={
            "title": "Electricity report",
            "data_mode": "synthetic",
            "section": "electricity",
            "filters": {"frequency": "annual"},
        },
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]
    _pdf_ok(client.get(f"/api/v1/reports/{report_id}/export.pdf?language=ar"))
    book = client.get(f"/api/v1/reports/{report_id}/export.xlsx")
    assert book.status_code == 200 and zipfile.is_zipfile(io.BytesIO(book.content))
    assert client.get(f"/api/v1/reports/{report_id}/export.csv").status_code == 200, (
        "the CSV route is unchanged"
    )
