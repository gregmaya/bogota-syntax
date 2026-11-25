"""Foreground cleaning rules (ADR-0012) on small synthetic layouts, EPSG:9377 metres."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
from shapely.geometry import LineString, box

from bogota_syntax import foreground as fg
from bogota_syntax.config import load_analysis

X0, Y0 = 4_880_000, 2_070_000


@pytest.fixture(scope="module")
def p() -> fg.Params:
    return fg.Params.from_config(load_analysis()["foreground"])


def lines(*coords, **attrs) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame(
        {"source": "original", "OBJECTID": range(len(coords))},
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in c]) for c in coords],
        crs="EPSG:9377",
    )
    for k, v in attrs.items():
        gdf[k] = v
    return gdf


def polygons(*boxes, touch_m: float = 0.5) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame(
        {"NOMBRE": [f"p{i}" for i in range(len(boxes))]},
        geometry=[box(X0 + a, Y0 + b, X0 + c, Y0 + d) for a, b, c, d in boxes],
        crs="EPSG:9377",
    )
    return fg.prepare_polygons(gdf, touch_m)


# A corridor cut into three stretches: the middle one touches two others (critical),
# the outer ones one each (corridor end).
CORRIDOR = [(-100, -10, 0, 10), (0, -10, 120, 10), (120, -10, 220, 10)]


def xy(geom, i):
    c = geom.coords[i]
    return round(c[0] - X0, 2), round(c[1] - Y0, 2)


def test_snap_moves_a_dead_end_onto_a_nearby_end_only_within_tolerance(p) -> None:
    gdf = lines(
        [(0, 0), (100, 0)], [(103, 0), (200, 0)], [(0, 50), (100, 50)], [(108, 50), (200, 50)]
    )
    out, snaps = fg.snap_dead_ends(gdf, p.snap_m, p.connected_m)
    assert len(snaps) == 1 and snaps["to"].iloc[0] == "end"
    assert xy(out.geometry[0], -1) == (103, 0)  # 3 m gap closed
    assert xy(out.geometry[2], -1) == (100, 50)  # 8 m gap left alone


def test_node_all_splits_crossings_and_keeps_attributes(p) -> None:
    gdf = lines([(0, 0), (100, 0)], [(50, -50), (50, 50)])
    out, crossings = fg.node_all(gdf, p.connected_m)
    assert len(out) == 4 and len(crossings) == 1
    assert sorted(out["OBJECTID"]) == [0, 0, 1, 1]


def test_drop_stubs_removes_overshoots_and_duplicate_branches(p) -> None:
    gdf = lines(
        [(0, 0), (300, 0)],
        [(100, -100), (100, 10)],  # crosses and overshoots by 10 m
        [(200, 0), (202, 3), (290, 3)],  # dead-end branch running 3 m beside the road
    )
    noded, _ = fg.node_all(gdf, p.connected_m)
    out, removed = fg.drop_stubs(noded, p)
    assert sorted(removed["why"]) == ["duplicate", "stub"]
    dead = fg.dead_end_mask(out, p.connected_m).reshape(2, -1).any(axis=0)
    assert not ((out.length.values < p.stub_m) & dead).any()


def test_classify_uses_polygon_neighbours(p) -> None:
    polys = polygons(*CORRIDOR)
    assert list(polys["n_neighbours"]) == [1, 2, 1]
    gdf = lines([(-50, 0), (60, 0)], [(0, 500), (50, 500)])
    dead = fg.classify(gdf, polys, p)
    status = {xy(g, 0): s for g, s in zip(dead.geometry, dead["status"], strict=True)}
    assert status[(-50, 0)] == "corridor_end"
    assert status[(60, 0)] == "critical"
    assert status[(0, 500)] == "no_polygon"


def test_pairs_join_opposed_ends_but_not_ends_pointing_the_same_way(p) -> None:
    polys = polygons(*CORRIDOR)
    facing = lines([(-50, 0), (40, 0)], [(70, 0), (180, 0)])
    out, pairs = fg.pair_dead_ends(facing, polys, p)
    assert len(pairs) == 1 and pairs["gap_m"].iloc[0] == 30
    assert xy(out.geometry[0], -1) == xy(out.geometry[1], 0) == (55, 0)

    parallel = lines([(-50, -5), (40, -5)], [(-50, 5), (40, 5)])
    _, pairs = fg.pair_dead_ends(parallel, polys, p)
    assert len(pairs) == 0


def test_extension_reaches_a_line_in_the_cone_only_within_the_step(p) -> None:
    polys = polygons(*CORRIDOR)
    gdf = lines([(-50, 0), (100, 0)], [(112, -60), (112, 60)])
    _, ext = fg.extend_step(gdf, polys, 10, p)
    assert len(ext) == 0  # 12 m away
    out, ext = fg.extend_step(gdf, polys, 15, p)
    assert len(ext) == 1 and ext["added_m"].iloc[0] == 12
    assert xy(out.geometry[0], -1) == (112, 0)


def test_connectors_point_ahead_and_never_back(p) -> None:
    polys = polygons(*CORRIDOR)
    spokes = [[(140, -8), (140, -60)], [(140, -8), (100, -60)], [(140, -8), (180, -60)]]
    ahead = lines([(-50, 0), (100, 0)], *spokes)
    _, conn, review = fg.connect(ahead, polys, p)
    assert (conn["kind"] == "junction").sum() == 1
    assert xy(conn.geometry[conn["kind"] == "junction"].iloc[0], -1) == (140, -8)

    behind = [[(x - 100, y) for x, y in s] for s in spokes]  # junction at (40, -8)
    back = lines([(-50, 0), (100, 0)], *behind)
    _, conn, review = fg.connect(back, polys, p)
    reviewed = {xy(g, 0) for g in review.geometry}
    assert (100, 0) in reviewed
    assert not any(xy(g, 0) == (100, 0) for g in conn.geometry)


def test_simplify_straightens_jogs_inside_the_polygons_and_keeps_ends(p) -> None:
    polys = polygons((-10, -10, 160, 15))
    gdf = lines([(0, 0), (50, 0), (50, 5), (100, 5), (150, 5)])
    out, n_jogs = fg.simplify_lines(gdf, polys, p)
    g0, g1 = gdf.geometry[0], out.geometry[0]
    assert n_jogs >= 1
    assert len(g1.coords) < len(g0.coords)
    assert (xy(g1, 0), xy(g1, -1)) == (xy(g0, 0), xy(g0, -1))
    assert polys.geometry[0].covers(g1)


def test_simplify_leaves_a_jog_that_would_leave_the_polygons(p) -> None:
    # Two stretches offset by 20 m: straightening the step would cut across open ground.
    polys = polygons((-10, -5, 55, 5), (45, 15, 160, 25))
    gdf = lines([(0, 0), (50, 0), (50, 20), (150, 20)])
    out, n_jogs = fg.simplify_lines(gdf, polys, p)
    assert n_jogs == 0
    assert np.allclose(out.geometry[0].coords, gdf.geometry[0].coords)


# ── step 11: interchange centres ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def r() -> fg.RelocationParams:
    return fg.RelocationParams.from_config(load_analysis()["foreground"]["relocation"])


def interchange(code: str = "900") -> gpd.GeoDataFrame:
    g = gpd.GeoDataFrame(
        {"NOMBRE": ["Enlace Vehicular prueba"], "CODIGO_ID": [code]},
        geometry=[box(X0 - 50, Y0 - 50, X0 + 50, Y0 + 50)],
        crs="EPSG:9377",
    )
    return g


# Four straight approaches aimed at (0, 0), drawn meeting 20 m off it, at (20, 0).
BENT = [
    [(-200, 0), (-50, 0), (20, 0)],
    [(20, 0), (50, 0), (200, 0)],
    [(0, -200), (0, -50), (20, 0)],
    [(20, 0), (0, 50), (0, 200)],
]


def decision(code: str, poly: gpd.GeoDataFrame, value: str):
    rp = poly.geometry.representative_point().iloc[0]
    return pd.DataFrame(
        {
            "codigo_id": [code],
            "rep_x": [round(rp.x)],
            "rep_y": [round(rp.y)],
            "area_m2": [round(poly.area.iloc[0])],
            "decision": [value],
        }
    )


def centre_xy(lines: gpd.GeoDataFrame):
    j, _ = fg.junctions(lines)
    return [xy(shapely.Point(c), 0) for c in shapely.get_coordinates(j)]


def test_relocation_moves_the_junction_to_where_the_approaches_meet(p, r) -> None:
    poly = interchange()
    out, enlace, _, stale = fg.relocate_centres(
        lines(*BENT), poly, decision("900", poly, "relocate"), r
    )
    out, _ = fg.node_all(out, p.connected_m)
    assert centre_xy(fg.consolidate(out)) == [(0, 0)]
    assert enlace["rms_new"].iloc[0] < 0.01 and len(stale) == 0


def test_keep_decision_leaves_the_interchange_as_drawn(r) -> None:
    poly = interchange()
    out, enlace, centres, _ = fg.relocate_centres(
        lines(*BENT), poly, decision("900", poly, "keep"), r
    )
    assert len(centres) == 0 and enlace["action"].iloc[0] == "keep"
    assert centre_xy(out) == [(20, 0)]


def test_without_a_matching_decision_the_rule_applies_and_is_flagged(r) -> None:
    poly = interchange()
    moved = decision("900", poly, "keep").assign(rep_x=lambda d: d["rep_x"] + 50)
    _, enlace, _, stale = fg.relocate_centres(lines(*BENT), poly, moved, r)
    assert len(stale) == 1  # the decision no longer matches the polygon's shape
    assert enlace["action"].iloc[0] == "relocate (rule)" and bool(enlace["needs_review"].iloc[0])


# ── step 12: manual edits ─────────────────────────────────────────────────────


def test_manual_edits_remove_matching_lines_add_new_ones_and_report_stale() -> None:
    net = lines([(0, 0), (100, 0)], [(100, 0), (100, 100)], [(100, 0), (200, 0)])
    edits = lines(
        [(100, 100), (100, 0)],  # same line as row 1, drawn the other way
        [(100, 0), (150, 80)],  # the replacement
        [(0, 500), (50, 500)],  # matches nothing: stale
    ).assign(edit=["remove", "add", "remove"])
    out, stale = fg.apply_edits(net, edits.drop(columns="source"), 0.01)
    assert len(out) == 3 and len(stale) == 1
    assert sorted(xy(g, -1) for g in out.geometry) == [(100, 0), (150, 80), (200, 0)]
    assert (out["source"] == "manual").sum() == 1
