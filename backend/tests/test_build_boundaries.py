"""The boundary build's geometry steps on small hand-made shapes: ways joined into rings, ring
orientation (RFC 7946), the national outline dissolved from the ways that only one governorate
uses, the mask with an enclave, and label points inside their areas."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "build_boundaries", Path(__file__).resolve().parents[1] / "scripts" / "build_boundaries.py"
)
assert _spec and _spec.loader
bb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bb)


def way(ref: int, *points: tuple[float, float], role: str = "outer") -> dict:
    return {
        "type": "way",
        "ref": ref,
        "role": role,
        "geometry": [{"lon": x, "lat": y} for x, y in points],
    }


def test_ways_are_joined_into_closed_rings_in_any_direction() -> None:
    a = [(0.0, 0.0), (1.0, 0.0)]
    b = [(1.0, 1.0), (1.0, 0.0)]  # reversed relative to a
    c = [(1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    rings, broken = bb._rings([a, b, c])
    assert broken == 0 and len(rings) == 1
    assert rings[0][0] == rings[0][-1] and len(rings[0]) == 5


def test_rings_are_oriented_outer_counter_clockwise_and_holes_clockwise() -> None:
    clockwise = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
    assert bb._area(clockwise) < 0
    assert bb._area(bb._orient(clockwise, ccw=True)) > 0
    assert bb._area(bb._orient(clockwise, ccw=False)) < 0


def test_the_national_outline_keeps_only_ways_used_by_one_governorate() -> None:
    # Two governorates side by side share the way x = 1; an enclave sits inside the east one.
    west = {
        "members": [way(1, (0, 0), (1, 0)), way(2, (1, 0), (1, 1)), way(3, (1, 1), (0, 1), (0, 0))]
    }
    east = {"members": [
        way(4, (1, 0), (2, 0), (2, 1), (1, 1)), way(2, (1, 0), (1, 1)),
        way(5, (1.4, 0.4), (1.6, 0.4), (1.6, 0.6), (1.4, 0.6), (1.4, 0.4), role="inner"),
    ]}  # fmt: skip
    outline, broken = bb.national([west, east], tolerance=0.0)
    assert broken == 0
    assert len(outline["coordinates"]) == 1, "the shared border is gone: one part"
    outer, *holes = outline["coordinates"][0]
    xs = sorted({p[0] for p in outer})
    assert xs == [0, 1, 2] or (min(xs), max(xs)) == (0, 2)
    assert len(holes) == 1 and bb._area(holes[0]) < 0 < bb._area(outer)

    shape = bb.mask(outline)["coordinates"]
    world, *cut = shape[0]
    assert len(cut) == 1 and bb._area(cut[0]) < 0, "the country is a hole in the world"
    assert len(shape) == 2 and bb._area(shape[1][0]) > 0, "the enclave is masked again"


def test_label_points_fall_inside_even_for_a_c_shaped_area() -> None:
    # A "C": its centroid lies in the gap, outside the shape.
    c_shape = [[[0, 0], [3, 0], [3, 1], [1, 1], [1, 2], [3, 2], [3, 3], [0, 3], [0, 0]]]
    x, y = bb._label_point([c_shape])
    assert bb._inside((x, y), [tuple(p) for p in c_shape[0]])
    # The largest part wins when an area has islands.
    island = [[[10, 10], [10.1, 10], [10.1, 10.1], [10, 10.1], [10, 10]]]
    assert bb._label_point([island, c_shape])[0] < 5
