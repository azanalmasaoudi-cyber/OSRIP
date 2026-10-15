"""Seed the booklet's SYNTHETIC fixtures through the normal import workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import DataMode, DatasetVersionStatus, Permission, Role
from app.models import AppUser, DatasetVersion, ImportJob, Source
from app.services import accounts
from app.services.imports import workflow
from app.services.principal import Principal

FIXTURE_FILE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "booklet_synthetic_fixtures_v1.csv"
)
SERVICE_EMAIL = "fixture-loader@osrip.invalid"
SOURCE_TITLE = "OSRIP booklet worked-example fixtures (synthetic)"
SYSTEM = Principal(user_id=None, label="system:seed-synthetic")


@dataclass(frozen=True, slots=True)
class SeedResult:
    source_id: str
    dataset_version_id: str
    created: bool
    rejected_rows: int


def _service_principal(session: Session) -> Principal:
    with session.begin():
        user = session.scalar(select(AppUser).where(AppUser.email == SERVICE_EMAIL))
        if user is None:
            user = accounts.create_user(
                session,
                SYSTEM,
                email=SERVICE_EMAIL,
                display_name="Fixture loader",
                password=None,
                roles=[Role.DATA_MANAGER],
                service_account=True,
            )
            session.flush()
            for permission in (Permission.IMPORT_APPROVE, Permission.IMPORT_PUBLISH):
                accounts.grant_permission(session, SYSTEM, user.id, permission)
        session.flush()
        return accounts.load_principal(session, user)


def seed_booklet_fixtures(session: Session) -> SeedResult:
    data = FIXTURE_FILE.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    actor = _service_principal(session)

    with session.begin():
        source = session.scalar(
            select(Source).where(
                Source.data_mode == DataMode.SYNTHETIC, Source.dataset_title == SOURCE_TITLE
            )
        )
        existing = (
            None
            if source is None
            else session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.source_id == source.id,
                    DatasetVersion.checksum_sha256 == checksum,
                )
            )
        )
    if (
        source is not None
        and existing is not None
        and existing.status is DatasetVersionStatus.PUBLISHED
    ):
        return SeedResult(str(source.id), str(existing.id), False, 0)

    if source is None:
        source = workflow.register_source(
            session,
            actor,
            data_mode=DataMode.SYNTHETIC,
            dataset_title=SOURCE_TITLE,
            publisher=None,  # synthetic data never has a publisher
            url=None,
            locator_kind=None,
            access_date=None,
            publication_date=None,
            reference_period="Placeholder years 2001-2002 (not reference dates)",
            geographic_coverage="OM (national, synthetic)",
            definition_note=(
                "Booklet Table 4.1 and Sections 4.3-4.4. Declared test inputs, not statistics."
            ),
            reuse_conditions=(
                "Synthetic demonstration data for testing the interface and formulas only."
            ),
        )

    if existing is None:
        state = workflow.create_import(
            session,
            actor,
            source_id=source.id,
            version_label="fixtures-v1",
            filename=FIXTURE_FILE.name,
            data=data,
        )
        import_id = state.job.id
    else:
        with session.begin():
            import_id = session.scalar(
                select(ImportJob.id).where(ImportJob.dataset_version_id == existing.id)
            )
        assert import_id is not None

    # Resume from wherever an interrupted earlier run stopped.
    status = existing.status if existing is not None else DatasetVersionStatus.DRAFT
    rejected = 0
    if status in (DatasetVersionStatus.DRAFT, DatasetVersionStatus.VALIDATED):
        state = workflow.validate_import(session, actor, import_id)
        rejected = state.job.rejected_row_count or 0
        workflow.approve_import(
            session,
            actor,
            import_id,
            acknowledged_rejected_rows=rejected,
            note="Booklet synthetic fixtures loaded by the seed command.",
        )
    elif status is not DatasetVersionStatus.APPROVED:
        raise RuntimeError(f"The fixture version is {status.value}; it cannot be seeded again.")
    result = workflow.publish_import(session, actor, import_id)
    return SeedResult(str(source.id), str(result.state.version.id), True, rejected)
