"""Import workflow (booklet 3.12): upload -> map columns -> validate -> review errors
-> explicit approval -> transactional publication.

The dataset version's status is the lifecycle:

    draft --map/validate--> validated --approve--> approved --publish--> published
      \\__________________________ reject __________________/          (previous
                                                                         published
                                                                         version ->
                                                                         superseded)

Callers pass a Session with no open transaction; each operation owns one.
Authorization by permission happens in the API layer; ownership rules that need
the import's data are checked here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, conflict, not_found, unprocessable
from app.domain.enums import (
    DataMode,
    DatasetVersionStatus,
    Frequency,
    Permission,
    QualityStatus,
    TradeFlow,
)
from app.models import (
    Area,
    Commodity,
    DatasetVersion,
    ImportJob,
    ImportRow,
    Indicator,
    Observation,
    Partner,
    Source,
    Unit,
)
from app.services import alerts, audit
from app.services.imports.csv_file import parse_csv
from app.services.imports.validation import (
    AreaRef,
    CommodityRef,
    IndicatorRef,
    PartnerRef,
    Reference,
    UnitRef,
    check_mapping,
    suggest_mapping,
    validate_rows,
)
from app.services.principal import Principal

S = DatasetVersionStatus


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ImportState:
    job: ImportJob
    version: DatasetVersion
    source: Source


# ------------------------------------------------------------------ loading


def load_reference(session: Session) -> Reference:
    units = {u.code: u for u in session.scalars(select(Unit))}
    unit_by_id = {u.id: u for u in units.values()}
    return Reference(
        indicators={
            i.code: IndicatorRef(
                str(i.id), i.dimension.value, i.measure, i.requires_commodity, i.requires_flow
            )
            for i in session.scalars(select(Indicator))
        },
        units={u.code: UnitRef(str(u.id), u.dimension.value) for u in units.values()},
        areas={
            a.code: AreaRef(str(a.id), a.valid_from, a.valid_to)
            for a in session.scalars(select(Area))
        },
        commodities={
            c.code: CommodityRef(
                str(c.id), c.mapping_status, c.synthetic_only, unit_by_id[c.quantity_unit_id].code
            )
            for c in session.scalars(select(Commodity))
        },
        partners={
            p.code: PartnerRef(str(p.id), p.is_fictional) for p in session.scalars(select(Partner))
        },
    )


def get_state(session: Session, import_id: uuid.UUID, *, lock: bool = False) -> ImportState:
    stmt = (
        select(ImportJob, DatasetVersion, Source)
        .join(DatasetVersion, DatasetVersion.id == ImportJob.dataset_version_id)
        .join(Source, Source.id == DatasetVersion.source_id)
        .where(ImportJob.id == import_id)
    )
    if lock:
        # Serialises concurrent transitions of the same import (e.g. a repeated publish).
        stmt = stmt.with_for_update(of=[ImportJob, DatasetVersion])
    row = session.execute(stmt).first()
    if row is None:
        raise not_found("import")
    return ImportState(*row)


def _require_status(state: ImportState, allowed: set[DatasetVersionStatus], action: str) -> None:
    if state.version.status not in allowed:
        raise conflict(
            "invalid_state",
            f"This import is {state.version.status.value}; it cannot be {action} now.",
            {"status": state.version.status.value, "allowed": sorted(s.value for s in allowed)},
        )


def _require_owner_or_manager(actor: Principal, state: ImportState) -> None:
    if state.job.created_by != actor.user_id and not actor.has(Permission.IMPORT_MANAGE_ANY):
        raise ApiError(
            403,
            "permission_denied",
            "Only the person who uploaded this file, or a permitted manager, can change it.",
        )


# ------------------------------------------------------------------ upload


def create_import(
    session: Session,
    actor: Principal,
    *,
    source_id: uuid.UUID,
    version_label: str,
    filename: str,
    data: bytes,
) -> ImportState:
    parsed = parse_csv(
        data, filename
    )  # rejects unsafe or malformed files before anything is stored
    version_label = version_label.strip()
    if not version_label:
        raise unprocessable(
            "version_label_required", "Give this dataset version a label, e.g. 2026-09 or v2."
        )

    with session.begin():
        source = session.get(Source, source_id)
        if source is None:
            raise not_found("source")
        clash = session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.source_id == source.id,
                DatasetVersion.checksum_sha256 == parsed.checksum_sha256,
                DatasetVersion.status != S.REJECTED,
            )
        )
        if clash is not None:
            raise conflict(
                "duplicate_file",
                "This exact file was already uploaded for this source.",
                {
                    "dataset_version_id": str(clash.id),
                    "version_label": clash.version_label,
                    "status": clash.status.value,
                },
            )
        if session.scalar(
            select(DatasetVersion.id).where(
                DatasetVersion.source_id == source.id, DatasetVersion.version_label == version_label
            )
        ):
            raise conflict(
                "version_label_taken", "This source already has a version with that label."
            )

        version = DatasetVersion(
            source_id=source.id,
            data_mode=source.data_mode,
            version_label=version_label,
            checksum_sha256=parsed.checksum_sha256,
            status=S.DRAFT,
        )
        session.add(version)
        session.flush()
        job = ImportJob(
            dataset_version_id=version.id,
            data_mode=source.data_mode,
            original_filename=filename,
            file_bytes=data,
            file_size=len(data),
            header=parsed.header,
            column_mapping=suggest_mapping(parsed.header),
            created_by=actor.user_id,
        )
        session.add(job)
        session.flush()
        audit.record(
            session,
            actor,
            "import.create",
            entity_type="import",
            entity_id=job.id,
            metadata={
                "source_id": str(source.id),
                "version_label": version_label,
                "rows": len(parsed.rows),
                "checksum": parsed.checksum_sha256,
            },
        )
        return ImportState(job, version, source)


# ------------------------------------------------------------------ mapping and validation


def set_mapping(
    session: Session, actor: Principal, import_id: uuid.UUID, mapping: dict[str, str]
) -> ImportState:
    mapping = {k: v for k, v in mapping.items() if v}
    with session.begin():
        state = get_state(session, import_id, lock=True)
        _require_owner_or_manager(actor, state)
        _require_status(state, {S.DRAFT, S.VALIDATED}, "remapped")
        problems = check_mapping(mapping, state.job.header)
        if problems:
            raise unprocessable("invalid_mapping", " ".join(problems), {"problems": problems})
        state.job.column_mapping = mapping
        if state.version.status is S.VALIDATED:
            # A new mapping invalidates the previous validation report.
            session.execute(delete(ImportRow).where(ImportRow.import_job_id == state.job.id))
            state.version.status = S.DRAFT
            state.job.row_count = state.job.valid_row_count = None
            state.job.warning_row_count = state.job.rejected_row_count = None
            state.job.validated_at = state.job.validated_by = None
        audit.record(
            session,
            actor,
            "import.map",
            entity_type="import",
            entity_id=import_id,
            metadata={"mapping": mapping},
        )
        return state


def validate_import(session: Session, actor: Principal, import_id: uuid.UUID) -> ImportState:
    with session.begin():
        state = get_state(session, import_id, lock=True)
        _require_owner_or_manager(actor, state)
        _require_status(state, {S.DRAFT, S.VALIDATED}, "validated")
        mapping = state.job.column_mapping or {}
        problems = check_mapping(mapping, state.job.header)
        if problems:
            raise unprocessable("invalid_mapping", " ".join(problems), {"problems": problems})

        parsed = parse_csv(state.job.file_bytes, state.job.original_filename)
        results = validate_rows(
            parsed.rows, mapping, load_reference(session), state.version.data_mode
        )

        session.execute(delete(ImportRow).where(ImportRow.import_job_id == state.job.id))
        session.add_all(
            ImportRow(
                import_job_id=state.job.id,
                row_number=r.row_number,
                raw=r.raw,
                outcome=r.outcome.value,
                issues=[i.as_dict() for i in r.issues],
                normalized=r.normalized,
            )
            for r in results
        )
        counts = {
            o: sum(1 for r in results if r.outcome.value == o)
            for o in ("valid", "warning", "rejected")
        }
        job = state.job
        job.row_count = len(results)
        job.valid_row_count, job.warning_row_count, job.rejected_row_count = (
            counts["valid"],
            counts["warning"],
            counts["rejected"],
        )
        job.validated_at, job.validated_by = _now(), actor.user_id
        state.version.status = S.VALIDATED
        audit.record(
            session,
            actor,
            "import.validate",
            entity_type="import",
            entity_id=import_id,
            metadata=counts,
        )
        return state


# ------------------------------------------------------------------ approval


def approve_import(
    session: Session,
    actor: Principal,
    import_id: uuid.UUID,
    *,
    acknowledged_rejected_rows: int,
    note: str | None,
) -> ImportState:
    """Explicit approval after the error preview has been reviewed."""
    with session.begin():
        state = get_state(session, import_id, lock=True)
        _require_status(state, {S.VALIDATED}, "approved")
        job = state.job
        if (job.valid_row_count or 0) + (job.warning_row_count or 0) == 0:
            raise unprocessable(
                "nothing_to_publish", "Every row was rejected; there is nothing to approve."
            )
        if acknowledged_rejected_rows != job.rejected_row_count:
            raise unprocessable(
                "acknowledgement_mismatch",
                "Review the error preview first: this import has "
                f"{job.rejected_row_count} rejected rows, "
                f"and the approval acknowledged {acknowledged_rejected_rows}.",
                {"rejected_row_count": job.rejected_row_count},
            )
        job.approved_by, job.approval_note = actor.user_id, (note or "").strip() or None
        job.acknowledged_rejected_rows = acknowledged_rejected_rows
        state.version.status, state.version.approved_at = S.APPROVED, _now()
        audit.record(
            session,
            actor,
            "import.approve",
            entity_type="import",
            entity_id=import_id,
            metadata={"rejected_rows_acknowledged": acknowledged_rejected_rows},
        )
        return state


def reject_import(
    session: Session, actor: Principal, import_id: uuid.UUID, reason: str
) -> ImportState:
    if not reason.strip():
        raise unprocessable("reason_required", "Give a reason for rejecting this import.")
    with session.begin():
        state = get_state(session, import_id, lock=True)
        _require_status(state, {S.DRAFT, S.VALIDATED, S.APPROVED}, "rejected")
        state.version.status = S.REJECTED
        state.job.rejected_by, state.job.rejection_reason = actor.user_id, reason.strip()
        audit.record(session, actor, "import.reject", entity_type="import", entity_id=import_id)
        return state


# ------------------------------------------------------------------ publication


@dataclass(frozen=True, slots=True)
class PublishResult:
    state: ImportState
    already_published: bool
    observations_inserted: int
    superseded_version_id: uuid.UUID | None


def _observation(job: ImportJob, version: DatasetVersion, row: ImportRow) -> Observation:
    n: dict[str, Any] = row.normalized or {}
    source_row = f"{job.original_filename}#row={row.row_number}"
    if n.get("source_reference"):
        source_row += f" ({n['source_reference']})"
    return Observation(
        dataset_version_id=version.id,
        data_mode=version.data_mode,
        indicator_id=uuid.UUID(n["indicator_id"]),
        area_id=uuid.UUID(n["area_id"]),
        period_start=datetime.fromisoformat(n["period_start"]).date(),
        period_end=datetime.fromisoformat(n["period_end"]).date(),
        period_complete=n["period_complete"],
        frequency=Frequency(n["frequency"]),
        value=None if n["value"] is None else Decimal(n["value"]),
        unit_id=uuid.UUID(n["unit_id"]),
        commodity_id=uuid.UUID(n["commodity_id"]) if n["commodity_id"] else None,
        partner_id=uuid.UUID(n["partner_id"]) if n["partner_id"] else None,
        flow=TradeFlow(n["flow"]) if n["flow"] else None,
        valuation_basis=n.get("valuation_basis"),
        quality_status=QualityStatus(n["quality_status"]),
        source_row=source_row,
        record_ref=n.get("record_ref"),
        source_locator=n.get("source_locator"),
        revision_status=n.get("revision_status"),
        value_operator=n.get("value_operator"),
        statement_date=date.fromisoformat(n["statement_date"]) if n.get("statement_date") else None,
        note=n.get("note"),
    )


def publish_import(session: Session, actor: Principal, import_id: uuid.UUID) -> PublishResult:
    """All-or-nothing publication (booklet 3.12, FR02, T05, T11).

    Runs in one transaction holding a row lock on the import. If anything fails,
    the transaction rolls back: no observation of the new version becomes visible
    and the previously published version stays published. A repeated request for
    an already published import returns the existing result without inserting
    anything.
    """
    try:
        with session.begin():
            state = get_state(session, import_id, lock=True)
            if state.version.status is S.PUBLISHED:
                return PublishResult(state, True, 0, None)
            _require_status(state, {S.APPROVED}, "published")

            previous = session.scalar(
                select(DatasetVersion)
                .where(
                    DatasetVersion.source_id == state.version.source_id,
                    DatasetVersion.status == S.PUBLISHED,
                )
                .with_for_update()
            )
            now = _now()
            if previous is not None:
                previous.status, previous.superseded_at = S.SUPERSEDED, now
                session.flush()  # release the one-published-per-source slot inside this transaction

            rows = session.scalars(
                select(ImportRow)
                .where(ImportRow.import_job_id == state.job.id, ImportRow.outcome != "rejected")
                .order_by(ImportRow.row_number)
            ).all()
            session.add_all(_observation(state.job, state.version, r) for r in rows)
            state.version.status, state.version.published_at = S.PUBLISHED, now
            state.job.published_by, state.job.last_error_code, state.job.last_error_at = (
                actor.user_id,
                None,
                None,
            )
            session.flush()
            # Watchlist alerts for new or revised values: created in this transaction, so
            # they exist only if the publication commits.
            alerts_created = alerts.evaluate_version(session, state.version)
            audit.record(
                session,
                actor,
                "import.publish",
                entity_type="import",
                entity_id=import_id,
                metadata={
                    "observations": len(rows),
                    "superseded_version_id": str(previous.id) if previous else None,
                    "alerts": alerts_created,
                },
            )
            result = PublishResult(state, False, len(rows), previous.id if previous else None)
        if alerts_created:
            # E-mail after the commit; a delivery failure is recorded and never undoes it.
            alerts.deliver_pending(session)
        return result
    except (IntegrityError, DBAPIError) as exc:
        # The transaction is rolled back. Record the failure separately so the data
        # manager can see it; the earlier published snapshot is untouched (T11).
        session.rollback()
        with session.begin():
            session.execute(
                update(ImportJob)
                .where(ImportJob.id == import_id)
                .values(last_error_code="publication_failed", last_error_at=_now())
            )
            audit.record(
                session,
                actor,
                "import.publish",
                "failed",
                entity_type="import",
                entity_id=import_id,
                metadata={
                    "error_type": type(exc.orig).__name__ if exc.orig else type(exc).__name__
                },
            )
        raise ApiError(
            500,
            "publication_failed",
            "Publication failed and was rolled back. "
            "No part of this version was published, and the "
            "previously published version is still the one shown. Nothing needs to be undone; the "
            "failure has been recorded for the data manager.",
        ) from exc


# ------------------------------------------------------------------ sources


def register_source(session: Session, actor: Principal, **fields: Any) -> Source:
    """Register provenance before any import (booklet 3.2)."""
    data_mode = fields["data_mode"]
    if data_mode is DataMode.SYNTHETIC and fields.get("publisher"):
        raise unprocessable(
            "synthetic_has_no_publisher",
            "Synthetic demonstration data never has a publisher (booklet 3.4).",
        )
    if data_mode is DataMode.VERIFIED_SOURCE:
        missing = [
            f
            for f in ("publisher", "url", "access_date", "locator_kind", "reuse_conditions")
            if not fields.get(f)
        ]
        if missing:
            raise unprocessable(
                "provenance_incomplete",
                f"A verified source needs: {', '.join(missing)}.",
                {"missing": missing},
            )
        if fields["locator_kind"] == "catalogue_page":
            raise unprocessable(
                "catalogue_page_not_verifiable",
                "A dataset catalogue page does not verify a particular numerical observation. "
                "Register the "
                "direct file or the statistical table that contains the values.",
            )
    with session.begin():
        source = Source(created_by=actor.user_id, **fields)
        session.add(source)
        try:
            session.flush()
        except IntegrityError as exc:
            raise unprocessable(
                "invalid_source", "The source record breaks a provenance rule."
            ) from exc
        audit.record(
            session,
            actor,
            "source.register",
            entity_type="source",
            entity_id=source.id,
            metadata={"data_mode": data_mode.value, "dataset_title": source.dataset_title},
        )
        return source
