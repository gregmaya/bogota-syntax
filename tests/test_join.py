"""Boundary join (ADR-0007) on a synthetic seam in EPSG:9377."""

import geopandas as gpd
from shapely.geometry import LineString, box

from bogota_syntax import join

X0, Y0 = 4_880_000, 2_070_000
BOGOTA = box(X0, Y0, X0 + 1000, Y0 + 1000)  # the seam is the line x = X0
EXTENT = box(X0 - 1000, Y0 - 500, X0 + 1500, Y0 + 1500)


def _g(rows, source):
    return gpd.GeoDataFrame(
        {"source": [source] * len(rows)},
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in r]) for r in rows],
        crs="EPSG:9377",
    )


def test_osm_cut_at_boundary_is_joined_to_mvi() -> None:
    mvi = _g([[(5, 300), (500, 300)], [(0, 700), (500, 700)]], "mvi")
    osm = _g(
        [
            [(-500, 300), (300, 300)],  # crosses into Bogotá; cut leaves an end 5 m from MVI
            [(-500, 700), (100, 700)],  # meets the MVI street cut at the boundary
            [(-500, 900), (50, 900)],  # no MVI within reach: stays unmatched
        ],
        "osm",
    )
    out = join.stitch(mvi, osm, BOGOTA, EXTENT, snap_m=25, candidate_max_m=100)
    cand = out["candidates"].sort_values("length_m")
    assert cand["accepted"].tolist() == [True, True]
    assert cand["length_m"].round().tolist() == [0, 5]
    assert len(out["unmatched_osm_ends"]) == 1
    net = out["network"]
    # OSM never inside Bogotá, MVI never outside.
    assert not net[net.source == "osm"].geometry.within(BOGOTA.buffer(-0.01)).any()
    assert net[net.source == "mvi"].geometry.within(BOGOTA.buffer(0.01)).all()
    # Each joined OSM street forms one piece with its MVI street; the third is alone.
    assert net["piece"].nunique() == 3
