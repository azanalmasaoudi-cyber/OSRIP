"""Al Mulhim's versioned identity: content of version 1, strict validation, immutable
storage, a single active version, a read-only route and persistence across restarts."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.assistant import profile

AR_INTRO = (
    "أنا المُلْهِم، مساعد OSRIP لتحليل موارد عُمان. أساعدك على فهم البيانات ومقارنة الخيارات "
    "واستكشاف السيناريوهات، مع توضيح المصادر وحدود النتائج."
)
EN_INTRO = (
    "I am Al Mulhim, the OSRIP resource analysis assistant. I help you understand data, compare "
    "options and explore scenarios, with sources and clear limitations."
)


def v1() -> profile.AssistantProfile:
    return profile.load_file(profile.profile_file(1))


def raw_v1() -> dict:
    return json.loads(profile.profile_file(1).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ content (no database)


def test_identity_names_meaning_and_introductions_are_exact() -> None:
    p = v1()
    assert p.version == 1
    assert (p.name.ar, p.name.en) == ("المُلْهِم", "Al Mulhim")
    assert p.meaning.en == "one who inspires"
    assert p.distinguished_from.ar == "المُلْهَم" and "inspired person" in p.distinguished_from.en
    assert (p.introduction.ar, p.introduction.en) == (AR_INTRO, EN_INTRO)
    assert p.greeting_reply["ar"].reply == "وعليكم السلام ورحمة الله وبركاته"
    assert "software, not a person" in p.self_description.en


def test_linguistic_reading_is_marked_as_interpretation_with_the_booklet_reference() -> None:
    p = v1()
    assert p.linguistic_note.status == "interpretation"
    assert "interpretation" in p.linguistic_note.en and "تفسير" in p.linguistic_note.ar
    assert p.reference.url.startswith("https://www.arabicacademy.gov.eg/")
    assert p.reference.citation.startswith("Academy of the Arabic Language in Cairo.")
    assert p.reference.url in p.reference.citation, "the URL is kept exactly as cited"
    assert "not re-checked" in p.reference.verification


def test_project_knowledge_matches_the_booklet_scope() -> None:
    p = v1()
    domains = {d.code: d for d in p.domains}
    assert list(domains) == ["energy_essential_services", "food_security", "trade"]
    assert [s.code for s in domains["energy_essential_services"].sections] == [
        "electricity",
        "water",
    ]
    assert p.statistics_from == date(2022, 1, 1)
    assert {m.code for m in p.data_modes} == {"verified_source", "candidate", "synthetic"}
    assert {u.code for u in p.users} >= {"public_viewer", "registered_member", "administrator"}
    assert {c.code for c in p.capabilities} >= {"ask", "analyze", "research", "compare", "scenario"}
    never = " ".join(p.memory_policy.never_retained).lower()
    assert "passwords" in never and "api keys" in never and "raw audio" in never


def test_checksum_ignores_formatting_but_not_content(tmp_path: Path) -> None:
    data = raw_v1()
    reordered = tmp_path / "reordered.json"
    reordered.write_text(
        json.dumps(dict(reversed(list(data.items()))), indent=1, ensure_ascii=False), "utf-8"
    )
    assert profile.checksum(profile.load_file(reordered)) == profile.checksum(v1())
    data["introduction"]["en"] = data["introduction"]["en"] + " Extra."
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    assert profile.checksum(profile.load_file(changed)) != profile.checksum(v1())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(unexpected="field"),
        lambda d: d["linguistic_note"].update(status="fact"),
        lambda d: d["introduction"].pop("ar"),
        lambda d: d["reference"].update(url="http://insecure.example/x"),
        lambda d: d["greeting_reply"].pop("en"),
        lambda d: d["capabilities"].append(dict(d["capabilities"][0])),
        lambda d: d.update(schema="something/2"),
    ],
)
def test_invalid_profile_files_are_rejected(tmp_path: Path, mutate) -> None:  # noqa: ANN001
    data = raw_v1()
    mutate(data)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    with pytest.raises(ValueError):
        profile.load_file(bad)


# ------------------------------------------------------------------ storage and API


@pytest.mark.integration
def test_migration_stores_version_1_as_the_only_active_version(db) -> None:  # noqa: ANN001
    from sqlalchemy import text

    with db.begin():
        current = profile.active(db)
        actives = db.execute(
            text("SELECT count(*) FROM assistant_profile WHERE status = 'active'")
        ).scalar()
    assert current is not None and current.profile.name.en == "Al Mulhim"
    assert current.sha256 == profile.checksum(v1()) or current.version > 1
    assert actives == 1


@pytest.mark.integration
def test_stored_content_cannot_be_changed_or_deleted(db) -> None:  # noqa: ANN001
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError, IntegrityError

    for sql in (
        "UPDATE assistant_profile SET profile = "
        "jsonb_set(profile, '{name,en}', '\"Someone else\"') WHERE version = 1",
        "UPDATE assistant_profile SET content_sha256 = repeat('0', 64) WHERE version = 1",
        "DELETE FROM assistant_profile WHERE version = 1",
    ):
        with pytest.raises(DBAPIError, match="assistant_profile"), db.begin():
            db.execute(text(sql))
    # A second active version is refused by the database.
    with pytest.raises(IntegrityError), db.begin():
        db.execute(
            text(
                "INSERT INTO assistant_profile "
                "(version, status, profile, content_sha256, activated_at) "
                "SELECT 99, 'active', jsonb_set(profile, '{version}', '99'), content_sha256, now() "
                "FROM assistant_profile WHERE version = 1"
            )
        )


@pytest.mark.integration
def test_public_read_only_route_and_persistence_across_restart(app, anonymous) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient

    from app.main import create_app

    first = anonymous.get("/api/v1/assistant/profile")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["name"] == {"ar": "المُلْهِم", "en": "Al Mulhim"}
    assert body["introduction"]["ar"] == AR_INTRO and body["introduction"]["en"] == EN_INTRO
    assert body["linguistic_note"]["status"] == "interpretation"
    for method in ("post", "put", "patch", "delete"):
        assert getattr(anonymous, method)("/api/v1/assistant/profile").status_code == 405
    # A new application instance (a backend restart) reads the same stored version.
    restarted = TestClient(create_app()).get("/api/v1/assistant/profile").json()
    assert (restarted["version"], restarted["sha256"]) == (body["version"], body["sha256"])


@pytest.mark.integration
def test_new_versions_are_published_and_earlier_ones_can_be_reactivated(db, tmp_path: Path) -> None:  # noqa: ANN001
    from sqlalchemy import select

    from app.models import AssistantProfileVersion

    with db.begin():
        latest = db.scalar(
            select(AssistantProfileVersion.version).order_by(AssistantProfileVersion.version.desc())
        )
        before = profile.active(db).version
    data = raw_v1()
    data["version"] = latest + 1
    data["introduction"]["en"] = EN_INTRO  # unchanged wording; only the version differs
    path = tmp_path / f"assistant_profile_v{latest + 1}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    try:
        with db.begin():
            assert profile.publish(db, path) == latest + 1
        with db.begin():
            assert profile.active(db).version == latest + 1
            rows = {r.version: r.status for r in db.scalars(select(AssistantProfileVersion))}
        assert rows[before] == "retired" and rows[latest + 1] == "active"
        # Publishing the same version twice, or skipping a version, is refused.
        with pytest.raises(ValueError, match="next version"), db.begin():
            profile.publish(db, path)
    finally:
        # The earlier version is re-activated (versions are never deleted).
        with db.begin():
            profile.activate(db, before)
    with db.begin():
        assert profile.active(db).version == before
