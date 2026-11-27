"""SDP package (docs/briefs/sdp-eje-vial-package-design.md) on small synthetic layouts,
EPSG:9377 metres."""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point

from bogota_syntax import sdp_package as sp

X0, Y0 = 4_880_000, 2_070_000
WKT = (Path(__file__).parent / "fixtures" / "pcs_carmagbog.wkt").read_text().strip()


def axes(*coords, ids=None) -> gpd.GeoDataFrame:
    ids = list(ids) if ids is not None else list(range(len(coords)))
    return gpd.GeoDataFrame(
        {
            "OBJECTID": ids,
            "CODIGO_ID": [f"c{i}" for i in ids],
            "NOMBRE": [f"Avenida {i}" for i in ids],
        },
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in c]) for c in coords],
        crs="EPSG:9377",
    )


def points(*xy, **cols) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(cols, geometry=[Point(X0 + x, Y0 + y) for x, y in xy], crs="EPSG:9377")


def segs(*coords, **cols) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        cols,
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in c]) for c in coords],
        crs="EPSG:9377",
    )


# ── task 1: keys and CRS ──────────────────────────────────────────────────────


def test_attach_keys_nearest_within_tolerance() -> None:
    ax = axes([(0, 0), (100, 0)], [(0, 50), (100, 50)], ids=[7, 8])
    out = sp.attach_keys(points((50, 0.3)), ax, key_m=1)
    assert out["OBJECTID"].iloc[0] == 7
    assert out["NOMBRE"].iloc[0] == "Avenida 7"


def test_attach_keys_unmatched_keeps_row_null() -> None:
    ax = axes([(0, 0), (100, 0)], ids=[7])
    out = sp.attach_keys(points((50, 5), (50, 0)), ax, key_m=1)
    assert len(out) == 2
    assert out["OBJECTID"].isna().iloc[0]
    assert out["OBJECTID"].iloc[1] == 7


def test_attach_keys_second_feature_for_crossing() -> None:
    ax = axes([(0, 0), (100, 0)], [(50, -50), (50, 50)], ids=[3, 4])
    out = sp.attach_keys(points((50, 0)), ax, key_m=1, second=True)
    assert {out["OBJECTID"].iloc[0], out["OBJECTID_2"].iloc[0]} == {3, 4}


def test_attach_keys_line_start() -> None:
    ax = axes([(0, 0), (100, 0)], [(0, 80), (100, 80)], ids=[1, 2])
    out = sp.attach_keys(segs([(100, 0), (100, 80)]), ax, key_m=1, at="start")
    assert out["OBJECTID"].iloc[0] == 1


def test_round_trip_under_1cm() -> None:
    ax = axes([(0, 0), (100, 0)], [(0, 50), (300, 900)], [(-2000, 10), (5000, 4000)])
    assert sp.round_trip_error_m(ax, WKT) < 0.01
