"""The curated reference pack: its references, reconciliation notes and record counts (public)."""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.models import (
    DataQualityNote,
    DatasetVersion,
    Observation,
    ReferencePack,
    ReferencePackSource,
    Source,
)

router = APIRouter(tags=["reference pack"])


@router.get("/reference-pack")
def reference_pack(session: DbSession) -> dict[str, Any]:
    """The latest loaded pack with every reference (including crosschecks that supply no
    imported value), its documented conflicts and limitations, and how many of its records
    are published. ``pack`` is null when no pack has been loaded."""
    with session.begin():
        pack = session.scalar(select(ReferencePack).order_by(ReferencePack.research_cutoff.desc()))
        if pack is None:
            return {"pack": None, "sources": [], "notes": []}
        published = dict(
            session.execute(
                select(Source.source_code, func.count(Observation.id))
                .join(DatasetVersion, DatasetVersion.source_id == Source.id)
                .join(Observation, Observation.dataset_version_id == DatasetVersion.id)
                .where(
                    DatasetVersion.version_label == pack.code, DatasetVersion.status == "published"
                )
                .group_by(Source.source_code)
            ).all()
        )
        sources = [
            {
                "code": s.code,
                "publisher": s.publisher,
                "title": s.title,
                "publication": s.publication,
                "accessed_on": s.accessed_on.isoformat(),
                "role": s.role,
                "url": s.url,
                "locations": s.locations,
                "published_records": published.get(s.code, 0),
            }
            for s in session.scalars(
                select(ReferencePackSource)
                .where(ReferencePackSource.pack_id == pack.id)
                .order_by(ReferencePackSource.code)
            )
        ]
        notes = [
            {
                "code": n.code,
                "title": {"en": n.title_en, "ar": n.title_ar},
                "body": {"en": n.body_en, "ar": n.body_ar},
                "source_codes": list(n.source_codes),
                "sections": list(n.sections),
            }
            for n in session.scalars(
                select(DataQualityNote)
                .where(DataQualityNote.pack_id == pack.id)
                .order_by(DataQualityNote.code)
            )
        ]
        return {
            "pack": {
                "code": pack.code,
                "title": pack.title,
                "research_cutoff": pack.research_cutoff.isoformat(),
                "document": pack.document,
                "record_count": pack.record_count,
                "published_records": sum(published.values()),
                "loaded_at": pack.created_at.isoformat(),
                "status_note": {
                    "en": "Curated extract of official publications and statements, checked up "
                    f"to {pack.research_cutoff.isoformat()}. Not a live or official data feed.",
                    "ar": "مستخلص منسّق من منشورات وتصريحات رسمية، جرى التحقق منه حتى "
                    f"{pack.research_cutoff.isoformat()}. ليس مصدر بيانات مباشراً ولا رسمياً.",
                },
            },
            "sources": sources,
            "notes": notes,
        }
