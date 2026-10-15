"""Live study events (migration 0019): the stream the workspace follows while the assistant
researches. Units first (findings, narration, dataset validation, ordering), then through the
API with the scripted provider: replay and server-sent events, tables and narration from the
same values, cancellation, partial failures, ownership, narration speech and deletion."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.domain.enums import DataMode
from app.services.assistant import study_events as se

# ------------------------------------------------------------------ units


def test_findings_split_at_sentences_never_inside_numbers() -> None:
    found = se.split_findings(
        "Generation was 41234.5 GWh in 2023 [E2]. It rose by 3.2 percent [E3][E2]. سؤال؟ وأخيراً."
    )
    assert [f["text"] for f in found][:2] == [
        "Generation was 41234.5 GWh in 2023 [E2].",
        "It rose by 3.2 percent [E3][E2].",
    ]
    assert found[1]["evidence_ids"] == ["E3", "E2"] and found[0]["finding_id"] == "F1"
    assert se.speakable(found[0]["text"]) == "Generation was 41234.5 GWh in 2023."
    # A citation covers its paragraph: an uncited sentence takes the next cited one's evidence.
    para = se.split_findings(
        "Output rose from 100 to 110. That is 10 percent [E4].\nNo forecast is made."
    )
    assert [f["evidence_ids"] for f in para] == [["E4"], ["E4"], []]


def _stream() -> se.StudyStream:
    return se.StudyStream(None, str(uuid.uuid4()), language="en", data_mode=DataMode.SYNTHETIC)


def _obs(eid: str, start: str, value: str | None, unit: str = "GWH") -> dict[str, Any]:
    return {
        "id": eid, "kind": "observation", "indicator": "ELEC_GENERATION", "area": "OM",
        "period_kind": "annual", "period_start": start, "period_end": start[:4] + "-12-31",
        "value": value, "unit": unit, "flow": None, "commodity": None, "partner": None,
        "indicator_name": {"en": "Electricity generated", "ar": "الكهرباء المولدة"},
        "area_name": {"en": "Oman", "ar": "عُمان"},
        "unit_label": {"en": "gigawatt hours", "ar": "جيجاواط ساعة"},
    }  # fmt: skip


class _Tracker:
    def __init__(self) -> None:
        self.stages: list[str] = []

    def stage(self, name: str) -> None:
        self.stages.append(name)


def test_observation_tables_are_validated_one_unit_per_table_with_rows_tied_to_evidence() -> None:
    stream = _stream()
    items = [_obs("E1", "2001-01-01", "100.5"), _obs("E2", "2002-01-01", None),
             _obs("E3", "2003-01-01", "110"), _obs("E4", "2003-01-01", "5", unit="MW")]  # fmt: skip
    by_id = {i["id"]: i for i in items}
    tracker = _Tracker()
    stream.on_tool("get_observations", {"status": "ok", "observations": items}, by_id, tracker)
    assert tracker.stages == ["validating_data"]
    gwh, mw = stream.datasets["D1"], stream.datasets["D2"]
    # Missing stays missing (never zero), the values are the evidence's own strings.
    assert [r["value"] for r in gwh["table"]["rows"]] == ["100.5", None, "110"]
    assert [r["status"] for r in gwh["table"]["rows"]][1] == "missing_in_source"
    assert [m["evidence_id"] for m in gwh["rows_meta"]] == ["E1", "E2", "E3"]
    assert gwh["charts"][0]["series"][0]["column"] == "value" and gwh["provisional"] is True
    assert mw["charts"] == []  # one value: a table, no chart
    assert [e["result_version"] for e in stream.events if e["type"] == "dataset"] == [1, 2]


def test_a_table_that_fails_validation_is_never_sent() -> None:
    stream = _stream()
    bad = {
        "origin": "get_observations", "data_status": "synthetic_demonstration",
        "title": {"en": "x", "ar": "x"},
        "table": {"columns": [{"key": "value", "label": {"en": "v", "ar": "v"}, "kind": "number"}],
                  "rows": [{"value": "12"}]},  # a numeric column without its unit
        "charts": [], "row_evidence": ["E1"],
    }  # fmt: skip
    assert stream.dataset(bad) is None
    not_decimal = {**bad, "table": {"columns": [{"key": "value", "label": {"en": "v", "ar": "v"},
                   "kind": "number", "unit": {"code": "u", "label_en": "u", "label_ar": "u"}}],
                   "rows": [{"value": "twelve"}]}, "row_evidence": ["E1"]}  # fmt: skip
    assert stream.dataset(not_decimal) is None
    unknown_column = {**not_decimal, "table": {**not_decimal["table"], "rows": [{"value": "1"}]},
                      "charts": [{"type": "line", "title": {"en": "c", "ar": "c"}, "x": "period",
                                  "series": [{"column": "value", "label": {"en": "v", "ar": "v"},
                                              "nature": "observed"}]}], "row_evidence": ["E1"]}  # fmt: skip
    assert stream.dataset(unknown_column) is None
    assert [e["type"] for e in stream.events] == ["warning", "warning", "warning"]
    assert {e["payload"]["code"] for e in stream.events} == {"dataset_rejected"}
    assert stream.datasets == {}


class _Reply:
    def __init__(
        self, status: str, content: str, citations: list[str], structured: dict | None = None
    ):
        self.status, self.content, self.citations = status, content, citations
        self.structured = structured or {}


def test_narration_comes_from_the_findings_and_points_at_the_rows_they_cite() -> None:
    stream = _stream()
    items = [_obs("E1", "2001-01-01", "100.5"), _obs("E2", "2002-01-01", "104")]
    stream.on_tool(
        "get_observations", {"observations": items}, {i["id"]: i for i in items}, _Tracker()
    )
    stream.finish(
        _Reply("answered", "Generation was 104 GWh in 2002 [E2].\nNo forecast is made.", ["E2"]), 7
    )
    done = stream.events[-1]
    assert done["type"] == "study.completed" and done["result_version"] == 2
    p = done["payload"]
    assert p["final_datasets"] == ["D1"] and p["provisional_datasets"] == []
    first = p["narration"][0]
    assert first["text"] == "Generation was 104 GWh in 2002."
    assert first["targets"] == [{"dataset_id": "D1", "row_ids": ["r2"]}]
    assert p["narration"][1]["targets"] == []  # nothing cited in its paragraph: section level only
    # Every number spoken is a value of the row it points at.
    row = next(r for r, m in zip(stream.datasets["D1"]["table"]["rows"],
                                 stream.datasets["D1"]["rows_meta"], strict=True) if m["row_id"] == "r2")  # fmt: skip
    assert Decimal(row["value"]) == Decimal("104")
    # Nothing follows the end of a study.
    assert stream.emit("stage", {"stage": "checking", "label": {"en": "x", "ar": "x"}}) is None


def test_a_withheld_or_cancelled_study_confirms_no_dataset() -> None:
    stream = _stream()
    items = [_obs("E1", "2001-01-01", "100.5"), _obs("E2", "2002-01-01", "104")]
    stream.on_tool(
        "get_observations", {"observations": items}, {i["id"]: i for i in items}, _Tracker()
    )
    stream.finish(_Reply("unverified", "This answer was withheld.", []), 3)
    types = [e["type"] for e in stream.events]
    assert types[-2:] == ["warning", "study.completed"]
    assert stream.events[-1]["payload"]["final_datasets"] == []
    assert stream.events[-1]["payload"]["provisional_datasets"] == ["D1"]
    cancelled = _stream()
    cancelled.finish(_Reply("cancelled", "Stopped.", []), None)
    assert [e["type"] for e in cancelled.events] == ["study.cancelled"]


def _study_doc() -> dict[str, Any]:
    from app.domain import study as schema

    unit = {"code": "GWH", "label_en": "gigawatt hours", "label_ar": "جيجاواط ساعة"}
    return schema.validate({
        "kind": "trend", "status": "ok", "title": {"en": "Trend", "ar": "اتجاه"},
        "question": {"en": "How has it changed?", "ar": "كيف تغيّر؟"},
        "params": {"indicator": "ELEC_GENERATION"}, "data_mode": "synthetic",
        "dataset_versions": ["v1"], "periods": {"from": "2001", "to": "2002"},
        "findings": [{"text": {"en": "It rose.", "ar": "ارتفع."}, "evidence": ["S1"]}],
        "table": {"columns": [{"key": "period", "label": {"en": "Year", "ar": "السنة"}, "kind": "period"},
                              {"key": "value", "label": {"en": "Value", "ar": "القيمة"}, "kind": "number", "unit": unit}],
                  "rows": [{"period": "2001", "value": "100"}, {"period": "2002", "value": "110"}]},
        "charts": [{"type": "line", "title": {"en": "Trend", "ar": "اتجاه"}, "x": "period",
                    "series": [{"column": "value", "label": {"en": "Value", "ar": "القيمة"}, "nature": "observed"}]}],
        "evidence": [{"id": "S1", "indicator": "ELEC_GENERATION", "area": "OM", "period_start": "2001-01-01",
                      "period_end": "2002-12-31", "value": "110", "unit": "GWH", "source_title": "Fixture",
                      "dataset_version": "v1"}],
        "method": {"en": "Values as published.", "ar": "القيم كما نُشرت."},
    })  # fmt: skip


def test_a_study_table_is_sent_unchanged_and_a_citation_of_the_study_targets_all_of_it() -> None:
    stream = _stream()
    item = {"id": "E5", "kind": "study", "study_id": str(uuid.uuid4()), "study_kind": "trend",
            "title": {"en": "Trend", "ar": "اتجاه"}, "status": "ok", "study": _study_doc()}  # fmt: skip
    stream.on_tool("run_study", {"status": "ok", "evidence_id": "E5"}, {"E5": item}, _Tracker())
    ds = stream.datasets["D1"]
    assert ds["table"] == item["study"]["table"] and ds["charts"] == item["study"]["charts"]
    assert (
        ds["source_evidence_id"] == "E5" and ds["study"]["method"]["en"] == "Values as published."
    )
    stream.finish(_Reply("answered", "It rose from 100 to 110 GWh [E5].", ["E5"]), 1)
    p = stream.events[-1]["payload"]
    assert p["final_datasets"] == ["D1"]
    assert p["narration"][0]["targets"] == [{"dataset_id": "D1", "row_ids": []}]


def test_completion_rejects_narration_that_points_at_an_unknown_dataset() -> None:
    with pytest.raises(ValueError):
        se.Completed.model_validate({
            "status": "answered", "language": "en",
            "findings": [{"finding_id": "F1", "text": "x", "evidence_ids": []}],
            "narration": [{"narration_segment_id": "N1", "finding_id": "F1", "text": "x",
                           "targets": [{"dataset_id": "D9", "row_ids": []}], "section": "findings"}],
            "final_datasets": [], "provisional_datasets": [],
        })  # fmt: skip


# ------------------------------------------------------------------ through the API

API = "/api/v1"


@pytest.fixture
def app_db(request, monkeypatch):  # noqa: ANN001, ANN201
    from app.core import ratelimit
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    request.getfixturevalue("database_url")
    with session_factory()() as session:
        seed_booklet_fixtures(session)
    s = get_settings()
    for name, value in (("assistant_provider", "fake"), ("assistant_fallback_provider", ""),
                        ("research_provider", "fake"), ("research_fallback_provider", ""),
                        ("guest_asks_per_minute", 1000), ("assistant_max_per_minute", 1000),
                        ("speech_provider", "fake")):  # fmt: skip
        monkeypatch.setattr(s, name, value)
    ratelimit.reset()
    return request.getfixturevalue("app")


def _guest(app):  # noqa: ANN001, ANN202
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get(f"{API}/assistant/guest")
    client.headers["X-Guest-CSRF"] = client.cookies["osrip_guest_csrf"]
    return client


def _ask(client, content: str, rid: uuid.UUID, **extra: Any) -> dict[str, Any]:  # noqa: ANN001
    r = client.post(f"{API}/assistant/guest/messages", json={
        "content": content, "language": "en", "request_id": str(rid), "data_mode": "synthetic", **extra,
    })  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()


def _study(client, rid: uuid.UUID) -> list[dict[str, Any]]:  # noqa: ANN001
    r = client.get(f"{API}/assistant/guest/requests/{rid}/study")
    assert r.status_code == 200, r.text
    return r.json()["events"]


def _sse(
    client, url: str, headers: dict[str, str] | None = None
) -> list[tuple[str, dict[str, Any]]]:  # noqa: ANN001
    out: list[tuple[str, dict[str, Any]]] = []
    with client.stream("GET", url, headers=headers or {}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        kind = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: ") and kind:
                out.append((kind, json.loads(line[6:])))
                if kind == "end":
                    break
    return out


@pytest.mark.integration
def test_a_study_streams_its_steps_sources_table_and_narration_in_order(app_db) -> None:  # noqa: ANN001
    client = _guest(app_db)
    rid = uuid.uuid4()
    body = _ask(client, "What is the latest electricity generation?", rid)
    message = body["message"]
    assert message["structured"]["study_id"] == str(rid)
    events = _study(client, rid)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "study.started" and events[-1]["type"] == "study.completed"
    assert all(e["study_id"] == str(rid) for e in events)
    versions = [e["result_version"] for e in events]
    assert versions == sorted(versions)
    stages = [e["payload"]["stage"] for e in events if e["type"] == "stage"]
    assert stages[0] == "received" and "published_data" in stages and "validating_data" in stages
    evidence = {
        e["payload"]["evidence_id"]: e["payload"] for e in events if e["type"] == "evidence"
    }
    [dataset] = [e["payload"] for e in events if e["type"] == "dataset"]
    # The source arrived before the table built from it.
    assert min(e["seq"] for e in events if e["type"] == "evidence") < next(
        e["seq"] for e in events if e["type"] == "dataset"
    )
    # Every row is the value of the source it names.
    for r, m in zip(dataset["table"]["rows"], dataset["rows_meta"], strict=True):
        assert r["value"] == evidence[m["evidence_id"]]["value"]
        assert evidence[m["evidence_id"]]["data_status"] == "synthetic_demonstration"
    done = events[-1]["payload"]
    assert done["message_id"] == message["id"] and done["final_datasets"] == [dataset["dataset_id"]]
    spoken = done["narration"][0]
    [cited] = spoken["evidence_ids"]
    meta = next(m for m in dataset["rows_meta"] if m["evidence_id"] == cited)
    row = dataset["table"]["rows"][dataset["rows_meta"].index(meta)]
    assert spoken["targets"] == [{"dataset_id": dataset["dataset_id"], "row_ids": [meta["row_id"]]}]
    # The table, the reply and the narration state the same number.
    assert Decimal(row["value"]) == Decimal(spoken["text"].split("value is ")[1].split(" ")[0])
    assert row["value"] in message["content"]


@pytest.mark.integration
def test_each_sentence_of_a_series_answer_points_at_its_own_row(app_db) -> None:  # noqa: ANN001
    client = _guest(app_db)
    rid = uuid.uuid4()
    message = _ask(client, "Show the history of electricity generation", rid)["message"]
    assert message["status"] == "answered", message["content"]
    events = _study(client, rid)
    [ds] = [e["payload"] for e in events if e["type"] == "dataset"]
    assert ds["origin"] == "get_observations" and ds["charts"][0]["type"] == "line"
    rows = {m["row_id"]: r for m, r in zip(ds["rows_meta"], ds["table"]["rows"], strict=True)}
    narration = events[-1]["payload"]["narration"]
    # The scripted answer reads the latest (up to four) published years, one sentence each.
    assert len(narration) == min(4, sum(1 for r in rows.values() if r["value"] is not None)) >= 2
    seen = []
    for seg in narration:
        [target] = seg["targets"]
        [row_id] = target["row_ids"]  # exactly one row (and chart point) per sentence
        seen.append(row_id)
        assert Decimal(rows[row_id]["value"]) == Decimal(seg["text"].split("was ")[1].split(" ")[0])
        assert rows[row_id]["period"] in seg["text"]
    assert len(set(seen)) == len(seen)


@pytest.mark.integration
def test_server_sent_events_replay_resume_and_end(app_db) -> None:  # noqa: ANN001
    client = _guest(app_db)
    rid = uuid.uuid4()
    _ask(client, "What is the latest electricity generation?", rid)
    stored = _study(client, rid)
    streamed = _sse(client, f"{API}/assistant/guest/requests/{rid}/events")
    assert [k for k, _ in streamed][-1] == "end"
    assert [d for k, d in streamed if k != "end"] == stored
    resumed = _sse(client, f"{API}/assistant/guest/requests/{rid}/events", {"Last-Event-ID": "3"})
    assert [d["seq"] for k, d in resumed if k != "end"] == [e["seq"] for e in stored[3:]]


@pytest.mark.integration
def test_study_and_comparison_tables_feed_the_charts_and_narration(app_db) -> None:  # noqa: ANN001
    client = _guest(app_db)
    rid = uuid.uuid4()
    reply = _ask(client, "Run a study of electricity generation", rid, mode="analyze")
    events = _study(client, rid)
    found = [e["payload"] for e in events if e["type"] == "dataset"]
    [study] = [
        e["payload"] for e in events if e["type"] == "evidence" and e["payload"]["kind"] == "study"
    ]
    if study["status"] != "ok":
        # The published data do not support the study here (other tests add series): no
        # table is sent, nothing is confirmed, and the reply says so.
        assert found == [] and events[-1]["payload"]["final_datasets"] == []
        assert reply["message"]["status"] == "no_evidence"
        return
    [ds] = found
    assert ds["origin"] == "run_study" and ds["study"]["method"]["en"]
    assert {s["column"] for c in ds["charts"] for s in c["series"]} <= {
        c["key"] for c in ds["table"]["columns"]
    }
    done = events[-1]["payload"]
    assert done["final_datasets"] == [ds["dataset_id"]]
    # The study is cited as a whole: every segment of its paragraph points at the whole table.
    assert all(
        s["targets"] == [{"dataset_id": ds["dataset_id"], "row_ids": []}] for s in done["narration"]
    )

    rid2 = uuid.uuid4()
    _ask(client, "Compare governorates for electricity generation", rid2)
    events = _study(client, rid2)
    areas = [
        e["payload"]
        for e in events
        if e["type"] == "dataset" and e["payload"]["origin"] == "compare_areas"
    ]
    if areas:  # the fixtures carry governorate values for this indicator
        table = areas[0]
        # A bar chart only when at least two governorates have their own value.
        values = [r["value"] for r in table["table"]["rows"] if r["value"] is not None]
        assert [c["type"] for c in table["charts"]] == (["bar"] if len(values) >= 2 else [])
        by_row = {
            m["row_id"]: r for m, r in zip(table["rows_meta"], table["table"]["rows"], strict=True)
        }
        for seg in events[-1]["payload"]["narration"]:
            for t in seg["targets"]:
                for rid_ in t["row_ids"]:
                    assert by_row[rid_]["value"] is None or by_row[rid_]["value"] in seg[
                        "text"
                    ].replace(",", "")


@pytest.fixture
def stop_after_first_tool(monkeypatch):  # noqa: ANN001, ANN201
    from sqlalchemy import text

    from app.db.session import session_factory
    from app.services.assistant import provider

    original = provider.FakeProvider.complete
    pending: dict[str, Any] = {}

    def patched(self, system, messages, tools):  # noqa: ANN001, ANN202
        out = original(self, system, messages, tools)
        rid = pending.pop("rid", None)
        if rid is not None:  # stop while the first tool's results are being prepared
            with session_factory()() as s, s.begin():
                s.execute(text("UPDATE assistant_request SET cancel_requested_at = now() "
                               "WHERE idempotency_key = :rid AND state = 'reserved'"), {"rid": rid})  # fmt: skip
        return out

    monkeypatch.setattr(provider.FakeProvider, "complete", patched)
    return pending


@pytest.mark.integration
def test_a_cancelled_study_ends_with_cancellation_and_nothing_after(
    app_db, stop_after_first_tool
) -> None:  # noqa: ANN001
    client = _guest(app_db)
    rid = uuid.uuid4()
    stop_after_first_tool["rid"] = rid
    assert (
        _ask(client, "What is the latest electricity generation?", rid)["message"]["status"]
        == "cancelled"
    )
    events = _study(client, rid)
    assert events[-1]["type"] == "study.cancelled"
    assert not [e for e in events if e["type"] == "study.completed"]
    # Results reached before the stop stay provisional: no completion ever confirmed them.
    assert all(e["payload"]["provisional"] for e in events if e["type"] == "dataset")


@pytest.mark.integration
def test_a_failed_search_is_reported_as_a_partial_failure(app_db) -> None:  # noqa: ANN001
    client = _guest(app_db)
    rid = uuid.uuid4()
    _ask(client, "web search that will fail", rid, mode="research")
    events = _study(client, rid)
    searches = [e["payload"] for e in events if e["type"] == "search"]
    assert searches and searches[0]["status"] == "failed"
    warnings = [e["payload"]["code"] for e in events if e["type"] == "warning"]
    assert "search_failed" in warnings
    assert events[-1]["type"] == "study.completed" and events[-1]["payload"]["final_datasets"] == []


@pytest.mark.integration
def test_another_visitor_never_sees_a_study(app_db, monkeypatch) -> None:  # noqa: ANN001
    from app.api.routes import assistant as routes

    monkeypatch.setattr(routes, "STREAM_WAIT_SECONDS", 0.5)
    owner, other = _guest(app_db), _guest(app_db)
    rid = uuid.uuid4()
    _ask(owner, "What is the latest electricity generation?", rid)
    assert other.get(f"{API}/assistant/guest/requests/{rid}/study").status_code == 404
    streamed = _sse(other, f"{API}/assistant/guest/requests/{rid}/events")
    assert streamed == [("end", {"reason": "unknown"})]


@pytest.mark.integration
def test_narration_segments_are_spoken_one_at_a_time(app_db) -> None:  # noqa: ANN001
    client = _guest(app_db)
    rid = uuid.uuid4()
    message = _ask(client, "What is the latest electricity generation?", rid)["message"]
    ok = client.post(f"{API}/assistant/voice/speak",
                     json={"message_id": message["id"], "language": "en", "segment_id": "N1"})  # fmt: skip
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("audio/")
    missing = client.post(f"{API}/assistant/voice/speak",
                          json={"message_id": message["id"], "language": "en", "segment_id": "N9"})  # fmt: skip
    assert missing.status_code == 404


@pytest.mark.integration
def test_deleting_the_conversation_deletes_its_study_events(app_db, db) -> None:  # noqa: ANN001
    from sqlalchemy import text

    client = _guest(app_db)
    rid = uuid.uuid4()
    body = _ask(client, "What is the latest electricity generation?", rid)
    count = "SELECT count(*) FROM study_event WHERE study_id = :s"
    with db.begin():
        assert db.execute(text(count), {"s": rid}).scalar() > 0
    assert (
        client.delete(f"{API}/assistant/guest/conversations/{body['conversation_id']}").status_code
        == 204
    )
    with db.begin():
        assert db.execute(text(count), {"s": rid}).scalar() == 0


@pytest.mark.integration
def test_a_study_preview_is_computed_but_not_stored(app_db, db) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    client = TestClient(app_db)
    with db.begin():
        before = db.execute(text("SELECT count(*) FROM study_run")).scalar()
    r = client.post(f"{API}/studies/preview", json={
        "kind": "trend", "data_mode": "synthetic", "params": {"indicator": "ELEC_GENERATION", "area": "OM"}})  # fmt: skip
    assert r.status_code == 200 and r.json()["study"]["schema"] == "osrip.study/1"
    with db.begin():
        assert db.execute(text("SELECT count(*) FROM study_run")).scalar() == before
