"""Build the governorate and wilayat boundary files from OpenStreetMap (ODbL).

    python scripts/build_boundaries.py fetch  OUT.json   # one Overpass request, saved as is
    python scripts/build_boundaries.py build  OUT.json   # GeoJSON + report into frontend/public/geo

``build`` needs the database (``OSRIP_DATABASE_URL``) for the area registry: every OSM
boundary is matched to a registry code, governorates by their ISO 3166-2 tag and wilayats by
name within their governorate (the parent comes from the OSM ``ref`` prefix). Nothing is
matched silently: the report lists every match with its name similarity, and anything left
unmatched on either side. Geometry is simplified (Douglas-Peucker) and rounded for the web;
it is for orientation and choropleths, not for legal or survey use.

It also writes:

* ``oman-national.geojson``: the national outline, dissolved from the 11 governorates. In OSM
  an internal border is one way shared by two governorates; the national edge (land borders,
  coast and the maritime limit) is made of ways used once. Joining those gives the mainland,
  Musandam and Madha, with the Nahwa enclave (part of the UAE) as a hole.
* ``oman-mask.geojson``: everything outside that outline, to dim neighbouring countries.
* ``oman-labels.geojson``: one label point inside each governorate and wilayat (a point far
  from the edges of its largest part), with the registry's English and Arabic names.

Rings are oriented as RFC 7946 asks (outer counter-clockwise, holes clockwise), so renderers
draw holes as holes.

OpenStreetMap data is (c) OpenStreetMap contributors, available under the Open Database
Licence 1.0. The files written here are a derived database under the same licence.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = (
    '[out:json][timeout:180];area["ISO3166-1"="OM"][admin_level=2]->.om;'
    '(relation(area.om)["boundary"="administrative"]["admin_level"~"^(4|6)$"];);out geom;'
)
OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "geo"
TOLERANCE = {"4": 0.002, "6": 0.001}  # degrees (about 200 m and 100 m)
DIGITS = 4  # about 11 m
# OSM tagging errors found while matching: corrected on evidence, and listed in the report.
CORRECTIONS = {
    19558488: (
        "OM-SJ-01",
        "Named 'Jalaan Bani Bu ALi' in OSM (ref 0801), but the polygon contains the town of Sur "
        "(22.567 N, 59.529 E); the Jaalan Bani Bu Ali boundary is relation 19558567 (ref 0804).",
    ),
}

Point = tuple[float, float]


def fetch(path: Path) -> None:
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    request = urllib.request.Request(
        OVERPASS, data=body, headers={"User-Agent": "OSRIP boundary build (academic prototype)"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - fixed https URL
        path.write_bytes(response.read())


def _rings(ways: list[list[Point]]) -> tuple[list[list[Point]], int]:
    """Join way segments into closed rings by their shared end points."""
    pending = [w for w in ways if len(w) >= 2]
    rings, broken = [], 0
    while pending:
        ring = list(pending.pop(0))
        while ring[0] != ring[-1]:
            for i, way in enumerate(pending):
                if way[0] == ring[-1]:
                    ring.extend(way[1:])
                elif way[-1] == ring[-1]:
                    ring.extend(reversed(way[:-1]))
                elif way[-1] == ring[0]:
                    ring[:0] = way[:-1]
                elif way[0] == ring[0]:
                    ring[:0] = list(reversed(way[1:]))
                else:
                    continue
                pending.pop(i)
                break
            else:
                broken += 1
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings, broken


def _simplify(points: list[Point], tolerance: float) -> list[Point]:
    """Douglas-Peucker on an open polyline (iterative)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (ax, ay), (bx, by) = points[first], points[last]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5
        best, index = 0.0, -1
        for i in range(first + 1, last):
            px, py = points[i]
            d = (
                abs(dy * px - dx * py + bx * ay - by * ax) / norm
                if norm
                else ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            )
            if d > best:
                best, index = d, i
        if best > tolerance and index > 0:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [p for p, k in zip(points, keep, strict=True) if k]


def _ring(ring: list[Point], tolerance: float) -> list[list[float]] | None:
    # Split at the far point so both halves are open lines, then simplify each.
    far = max(
        range(len(ring)),
        key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2,
    )
    line = _simplify(ring[: far + 1], tolerance)[:-1] + _simplify(ring[far:], tolerance)
    out: list[list[float]] = []
    for x, y in line:
        p = [round(x, DIGITS), round(y, DIGITS)]
        if not out or out[-1] != p:
            out.append(p)
    return out if len(out) >= 4 else None


def _inside(point: Point, ring: list[Point]) -> bool:
    x, y, inside = point[0], point[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _area(ring: list[list[float]] | list[Point]) -> float:
    """Signed area (shoelace): positive for counter-clockwise rings in longitude/latitude."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False)) / 2


def _orient(ring: list[list[float]], ccw: bool) -> list[list[float]]:
    return ring if (_area(ring) > 0) == ccw else list(reversed(ring))


def _label_point(polygons: list[list[list[list[float]]]]) -> list[float]:
    """A point inside the largest part, far from its edges (a coarse-to-fine grid search for
    the pole of inaccessibility; good enough to place a name)."""
    poly = max(polygons, key=lambda p: abs(_area(p[0])))
    outer, holes = poly[0], poly[1:]
    edges = [(a, b) for ring in poly for a, b in zip(ring, ring[1:], strict=False)]
    kx = max(0.2, abs(math.cos(math.radians(outer[0][1]))))

    def inside(x: float, y: float) -> bool:
        return _inside((x, y), outer) and not any(_inside((x, y), h) for h in holes)

    def clearance(x: float, y: float) -> float:
        best = float("inf")
        for (x1, y1), (x2, y2) in edges:
            dx, dy = (x2 - x1) * kx, y2 - y1
            px, py = (x - x1) * kx, y - y1
            t = max(0.0, min(1.0, (px * dx + py * dy) / (dx * dx + dy * dy or 1)))
            best = min(best, ((px - t * dx) ** 2 + (py - t * dy) ** 2) ** 0.5)
        return best

    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    best, best_d = None, -1.0
    for _ in range(3):  # each pass searches a finer grid around the best point so far
        for i in range(1, 16):
            for j in range(1, 16):
                x, y = x0 + (x1 - x0) * i / 16, y0 + (y1 - y0) * j / 16
                if inside(x, y):
                    d = clearance(x, y)
                    if d > best_d:
                        best, best_d = (x, y), d
        if best is None:
            break
        w, h = (x1 - x0) / 8, (y1 - y0) / 8
        x0, x1, y0, y1 = best[0] - w, best[0] + w, best[1] - h, best[1] + h
    point = best or (outer[0][0], outer[0][1])
    return [round(point[0], DIGITS), round(point[1], DIGITS)]


def national(level4: list[dict[str, Any]], tolerance: float) -> tuple[dict[str, Any], int]:
    """The national outline from the governorates: ways used by exactly one governorate."""
    uses: dict[int, int] = {}
    geometry_of: dict[int, list[Point]] = {}
    for relation in level4:
        for m in relation.get("members", []):
            if m.get("type") == "way" and m.get("geometry"):
                uses[m["ref"]] = uses.get(m["ref"], 0) + 1
                geometry_of[m["ref"]] = [(g["lon"], g["lat"]) for g in m["geometry"]]
    edge = [geometry_of[ref] for ref, n in uses.items() if n == 1]
    rings, broken = _rings(edge)
    simplified = [r for r in (_ring(ring, tolerance) for ring in rings) if r]
    # Rings inside another ring are holes (the Nahwa enclave inside Madha).
    outers = [
        r for r in simplified if not any(o is not r and _inside(tuple(r[0]), o) for o in simplified)
    ]
    polygons = []
    for outer in outers:
        holes = [
            r
            for r in simplified
            if r is not outer and r not in outers and _inside(tuple(r[0]), outer)
        ]
        polygons.append([_orient(outer, ccw=True), *(_orient(h, ccw=False) for h in holes)])
    return {"type": "MultiPolygon", "coordinates": polygons}, broken


def mask(outline: dict[str, Any]) -> dict[str, Any]:
    """Everything outside the outline: the world with Oman cut out, plus any enclave inside."""
    world = [[-180.0, -85.0], [180.0, -85.0], [180.0, 85.0], [-180.0, 85.0], [-180.0, -85.0]]
    holes = [_orient(poly[0], ccw=False) for poly in outline["coordinates"]]
    enclaves = [[_orient(h, ccw=True)] for poly in outline["coordinates"] for h in poly[1:]]
    return {"type": "MultiPolygon", "coordinates": [[world, *holes], *enclaves]}


def geometry(relation: dict[str, Any], tolerance: float) -> tuple[dict[str, Any] | None, int]:
    roles: dict[str, list[list[Point]]] = {"outer": [], "inner": []}
    for m in relation.get("members", []):
        if m.get("type") == "way" and m.get("geometry"):
            role = "inner" if m.get("role") == "inner" else "outer"
            roles[role].append([(g["lon"], g["lat"]) for g in m["geometry"]])
    outers, broken_outer = _rings(roles["outer"])
    inners, broken_inner = _rings(roles["inner"])
    polygons: list[list[list[list[float]]]] = []
    holes: dict[int, list[list[list[float]]]] = {}
    for hole in inners:
        owner = next((i for i, o in enumerate(outers) if _inside(hole[0], o)), None)
        simplified = _ring(hole, tolerance)
        if owner is not None and simplified:
            holes.setdefault(owner, []).append(simplified)
    for i, outer in enumerate(outers):
        simplified = _ring(outer, tolerance)
        if simplified:
            polygons.append(
                [_orient(simplified, ccw=True), *(_orient(h, ccw=False) for h in holes.get(i, []))]
            )
    if not polygons:
        return None, broken_outer + broken_inner
    return {"type": "MultiPolygon", "coordinates": polygons}, broken_outer + broken_inner


def _norm(name: str) -> str:
    s = name.lower()
    s = re.sub(r"\b(province|wilayat|governorate)\b", " ", s)
    s = re.sub(r"\b(al|as|ad|ar|ash|az|adh|an|at)[\s-]+", "", s)
    s = re.sub(r"[^a-z]", "", s)
    return re.sub(r"(.)\1+", r"\1", s)


def build(path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy import select
    from sqlalchemy.orm import aliased

    from app.db.session import session_factory
    from app.models import Area

    parent = aliased(Area)
    with session_factory()() as session:
        rows = session.execute(
            select(Area.code, Area.level, Area.name_en, Area.name_ar, parent.code).outerjoin(
                parent, parent.id == Area.parent_id
            )
        ).all()
    governorates = {r[0]: r for r in rows if r[1] == "governorate"}
    wilayats = [r for r in rows if r[1] == "wilayat"]

    elements = json.loads(path.read_text(encoding="utf-8"))["elements"]
    level4 = [e for e in elements if e["tags"].get("admin_level") == "4"]
    level6 = [e for e in elements if e["tags"].get("admin_level") == "6"]
    by_ref = {e["tags"].get("ref"): e["tags"].get("ISO3166-2") for e in level4}

    report: dict[str, Any] = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "OpenStreetMap via the Overpass API",
        "licence": "Open Database Licence 1.0 (ODbL); (c) OpenStreetMap contributors",
        "query": QUERY,
        "governorates": [],
        "wilayats": [],
        "unmatched_osm": [],
        "unmatched_registry": [],
        "geometry_problems": [],
        "corrections": [
            {"osm_relation": rid, "code": code, "reason": why}
            for rid, (code, why) in CORRECTIONS.items()
        ],
    }

    def feature(e: dict[str, Any], code: str, level: str) -> dict[str, Any] | None:
        geom, broken = geometry(e, TOLERANCE[e["tags"]["admin_level"]])
        if broken or geom is None:
            report["geometry_problems"].append(
                {"osm_relation": e["id"], "code": code, "unjoined_segments": broken}
            )
        if geom is None:
            return None
        return {
            "type": "Feature",
            "id": code,
            "properties": {"code": code, "level": level, "osm_relation": e["id"]},
            "geometry": geom,
        }

    gov_features = []
    for e in sorted(level4, key=lambda x: x["tags"].get("ISO3166-2", "")):
        iso = e["tags"].get("ISO3166-2")
        if iso not in governorates:
            report["unmatched_osm"].append(
                {"osm_relation": e["id"], "name": e["tags"].get("name:en"), "level": "4"}
            )
            continue
        f = feature(e, iso, "governorate")
        if f:
            gov_features.append(f)
        report["governorates"].append(
            {
                "code": iso,
                "registry": governorates[iso][2],
                "osm": e["tags"].get("name:en"),
                "osm_relation": e["id"],
            }
        )
    missing_gov = sorted(set(governorates) - {g["code"] for g in report["governorates"]})
    report["unmatched_registry"] += [{"code": c, "name": governorates[c][2]} for c in missing_gov]

    # Wilayats: best name match within the governorate given by the OSM ref prefix.
    taken: set[str] = set()
    candidates = []
    for e in level6:
        if e["id"] in CORRECTIONS:
            code = CORRECTIONS[e["id"]][0]
            reg = next(w for w in wilayats if w[0] == code)
            candidates.append((2.0, e["id"], code, e["tags"].get("name:en", ""), reg[2], reg[4]))
            continue
        name = e["tags"].get("name:en") or e["tags"].get("name", "")
        ref = e["tags"].get("ref") or ""
        gov = by_ref.get(ref[:2]) if len(ref) == 4 else None
        pool = [w for w in wilayats if gov is None or w[4] == gov]
        for w in pool:
            ratio = difflib.SequenceMatcher(None, _norm(name), _norm(w[2])).ratio()
            candidates.append((ratio, e["id"], w[0], name, w[2], gov))
    matched_osm: set[int] = set()
    wil_features = []
    for ratio, osm_id, code, osm_name, reg_name, gov in sorted(candidates, reverse=True):
        if osm_id in matched_osm or code in taken or ratio < 0.6:
            continue
        matched_osm.add(osm_id)
        taken.add(code)
        e = next(x for x in level6 if x["id"] == osm_id)
        f = feature(e, code, "wilayat")
        if f:
            wil_features.append(f)
        report["wilayats"].append(
            {
                "code": code,
                "registry": reg_name,
                "osm": osm_name,
                "osm_relation": osm_id,
                "similarity": None if ratio > 1 else round(ratio, 2),
                "parent_from": "correction" if ratio > 1 else "ref" if gov else "name",
            }
        )
    for e in level6:
        if e["id"] not in matched_osm:
            report["unmatched_osm"].append(
                {
                    "osm_relation": e["id"],
                    "name": e["tags"].get("name:en") or e["tags"].get("name"),
                    "level": "6",
                }
            )
    report["unmatched_registry"] += [
        {"code": w[0], "name": w[2]} for w in wilayats if w[0] not in taken
    ]
    report["wilayats"].sort(key=lambda x: x["code"])

    OUT.mkdir(parents=True, exist_ok=True)
    for name, features in (("oman-governorates", gov_features), ("oman-wilayats", wil_features)):
        collection = {
            "type": "FeatureCollection",
            "features": sorted(features, key=lambda f: f["id"]),
        }
        (OUT / f"{name}.geojson").write_text(
            json.dumps(collection, separators=(",", ":")), encoding="utf-8", newline="\n"
        )
    # The national outline and mask, from the governorates' own OSM ways.
    outline, broken = national(level4, TOLERANCE["4"])
    report["national"] = {
        "method": "ways used by exactly one governorate, joined into rings",
        "parts": len(outline["coordinates"]),
        "holes": sum(len(p) - 1 for p in outline["coordinates"]),
        "unjoined_segments": broken,
    }
    names = {r[0]: (r[2], r[3]) for r in rows}
    labels = [
        {
            "type": "Feature",
            "properties": {
                "code": f["id"],
                "level": f["properties"]["level"],
                "name_en": names[f["id"]][0],
                "name_ar": names[f["id"]][1],
            },
            "geometry": {
                "type": "Point",
                "coordinates": _label_point(f["geometry"]["coordinates"]),
            },
        }
        for f in sorted(gov_features + wil_features, key=lambda f: f["id"])
    ]
    for name, data in (
        (
            "oman-national",
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "OM",
                        "properties": {"code": "OM"},
                        "geometry": outline,
                    }
                ],
            },
        ),
        (
            "oman-mask",
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": mask(outline)}],
            },
        ),
        ("oman-labels", {"type": "FeatureCollection", "features": labels}),
    ):
        (OUT / f"{name}.geojson").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
            newline="\n",
        )
    (OUT / "boundaries-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    low = [w for w in report["wilayats"] if w["similarity"] is not None and w["similarity"] < 0.85]
    print(
        f"governorates {len(gov_features)}/{len(governorates)}, "
        f"wilayats {len(wil_features)}/{len(wilayats)}, "
        f"unmatched osm {len(report['unmatched_osm'])}, "
        f"unmatched registry {len(report['unmatched_registry'])}, "
        f"geometry problems {len(report['geometry_problems'])}, matches below 0.85: {len(low)}; "
        f"national parts {report['national']['parts']}, holes {report['national']['holes']}, "
        f"unjoined {broken}, labels {len(labels)}"
    )


if __name__ == "__main__":
    action, target = sys.argv[1], Path(sys.argv[2])
    fetch(target) if action == "fetch" else build(target)
