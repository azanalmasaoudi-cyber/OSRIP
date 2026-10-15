"""Administrative registry and statistical coverage by area (booklet 3.11, 3.14).

Two different questions, kept apart:

* Registry coverage: which governorates and wilayats exist, with names, parents,
  identifiers, verification date and references. Every area is listed.
* Statistical coverage: which published observations of one data mode are
  recorded *for that exact area*. An area with none has no entry (the interface
  shows "No data"); nothing is derived from a parent or a national total.

No coordinates or boundaries are stored or returned.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.domain.enums import DataMode, DatasetVersionStatus
from app.models import (
    Area,
    AreaGroupMember,
    AreaReference,
    AreaRegistryVerification,
    DatasetVersion,
    GeoReference,
    Indicator,
    Observation,
)
from app.services.exports import mode_label


def registry(session: Session) -> dict[str, Any]:
    parent = aliased(Area)
    areas = session.execute(
        select(Area, parent.code)
        .outerjoin(parent, parent.id == Area.parent_id)
        .where(Area.level.in_(("national", "governorate", "wilayat")))
        .order_by(Area.code)
    ).all()
    refs: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for link, ref_code in session.execute(
        select(AreaReference, GeoReference.code)
        .join(GeoReference, GeoReference.id == AreaReference.geo_reference_id)
        .order_by(GeoReference.code)
    ):
        refs[link.area_id].append({"code": ref_code, "supports": list(link.supports)})

    references = [
        {
            "code": r.code,
            "publisher": r.publisher,
            "title": r.title,
            "url": r.url,
            "language": r.language,
            "published_on": r.published_on.isoformat() if r.published_on else None,
            "page_updated_on": r.page_updated_on.isoformat() if r.page_updated_on else None,
            "accessed_on": r.accessed_on.isoformat(),
            "supports": r.supports,
        }
        for r in session.scalars(select(GeoReference).order_by(GeoReference.code))
    ]

    counts = {"governorate": 0, "wilayat": 0}
    for a, _ in areas:
        if a.level in counts:
            counts[a.level] += 1
    check = session.scalar(
        select(AreaRegistryVerification).order_by(AreaRegistryVerification.id.desc()).limit(1)
    )
    verification = None
    if check is not None:
        verification = {
            "verified_on": check.verified_on.isoformat(),
            "expected_governorates": check.expected_governorates,
            "expected_wilayats": check.expected_wilayats,
            "found_governorates": counts["governorate"],
            "found_wilayats": counts["wilayat"],
            "complete": counts["governorate"] == check.expected_governorates
            and counts["wilayat"] == check.expected_wilayats,
            "basis_en": check.basis_en,
            "basis_ar": check.basis_ar,
            "reference_codes": list(check.reference_codes),
        }

    member = aliased(Area)
    group_rows = session.execute(
        select(Area, member.code)
        .outerjoin(AreaGroupMember, AreaGroupMember.group_area_id == Area.id)
        .outerjoin(member, member.id == AreaGroupMember.member_area_id)
        .where(Area.level == "reporting_group")
        .order_by(Area.code, member.code)
    ).all()
    groups: dict[str, dict[str, Any]] = {}
    for g, member_code in group_rows:
        entry = groups.setdefault(
            g.code,
            {
                "code": g.code,
                "name_en": g.name_en,
                "name_ar": g.name_ar,
                "members_stated": g.members_stated,
                "members": [],
                "note_en": g.registry_note_en,
                "note_ar": g.registry_note_ar,
            },
        )
        if member_code:
            entry["members"].append(member_code)

    return {
        "verification": verification,
        "references": references,
        # Groups used by sources to publish figures; never split among their members and
        # never counted as registry areas.
        "reporting_groups": list(groups.values()),
        "geometry": {
            "available": False,
            "en": "No boundary geometry is included: no current, suitably licensed boundary "
            "dataset matching this registry was found. Areas have no coordinates or centroids.",
            "ar": "لا تتضمن المنصة حدوداً جغرافية: لم يُعثر على مجموعة حدود حديثة ومرخصة بشكل مناسب "
            "تطابق هذا السجل. لا توجد إحداثيات أو نقاط مركزية للمناطق.",
        },
        "areas": [
            {
                "code": a.code,
                "level": a.level,
                "parent_code": parent_code,
                "name_en": a.name_en,
                "name_ar": a.name_ar,
                "iso_3166_2": a.iso_3166_2,
                "code_authority": a.code_authority,
                "verified_on": a.verified_on.isoformat() if a.verified_on else None,
                "note_en": a.registry_note_en,
                "note_ar": a.registry_note_ar,
                "references": refs.get(a.id, []),
            }
            for a, parent_code in areas
        ],
    }


def coverage(session: Session, data_mode: DataMode) -> dict[str, Any]:
    """Published observations per area and indicator, for the current snapshot only."""
    rows = session.execute(
        select(
            Area.code,
            Indicator.code,
            Indicator.name_en,
            Indicator.name_ar,
            Observation.frequency,
            func.count(),
            func.count(Observation.value),
            func.min(Observation.period_start),
            func.max(Observation.period_end),
        )
        .join(Area, Area.id == Observation.area_id)
        .join(Indicator, Indicator.id == Observation.indicator_id)
        .join(DatasetVersion, DatasetVersion.id == Observation.dataset_version_id)
        .where(
            Observation.data_mode == data_mode,
            DatasetVersion.data_mode == data_mode,
            DatasetVersion.status == DatasetVersionStatus.PUBLISHED,
        )
        .group_by(
            Area.code, Indicator.code, Indicator.name_en, Indicator.name_ar, Observation.frequency
        )
        .order_by(Area.code, Indicator.code)
    ).all()
    areas: dict[str, dict[str, Any]] = {}
    for code, ind, name_en, name_ar, freq, n, n_values, start, end in rows:
        entry = areas.setdefault(
            code, {"observations": 0, "values": 0, "missing": 0, "indicators": []}
        )
        entry["observations"] += n
        entry["values"] += n_values
        entry["missing"] += n - n_values
        entry["indicators"].append(
            {
                "code": ind,
                "name_en": name_en,
                "name_ar": name_ar,
                "frequency": freq.value,
                "observations": n,
                "values": n_values,
                "first_period": start.isoformat(),
                "last_period": end.isoformat(),
            }
        )
    return {
        "data_mode": data_mode.value,
        "label": mode_label(data_mode),
        "note_en": "Counts cover published observations recorded for each exact area. An area "
        "without an entry has no data; it is not zero, and no national or parent total is "
        "divided among areas.",
        "note_ar": "تشمل الأعداد المشاهدات المنشورة المسجلة لكل منطقة بعينها. المنطقة التي لا "
        "تظهر لها بيانات ليست صفراً، ولا يُوزَّع أي مجموع وطني أو مجموع للمحافظة على المناطق.",
        "areas": areas,
    }
