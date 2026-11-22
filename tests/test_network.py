"""Finishing into intersection-to-intersection segments (ADR-0009), EPSG:9377."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from bogota_syntax import network
from bogota_syntax.clean import label_pieces

X0, Y0 = 4_880_000, 2_070_000


def _g(rows):
    return gpd.GeoDataFrame(
        {
            "source": [s for s, _, _ in rows],
            "OBJECTID": [o for _, o, _ in rows],
        },
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in c]) for _, _, c in rows],
        crs="EPSG:9377",
    )


def test_chain_through_degree_two_points_becomes_one_segment() -> None:
    lines = _g(
        [
            ("mvi", 1, [(0, 0), (100, 0)]),
            ("mvi", 2, [(100, 0), (300, 0)]),  # longer part: its attributes win
            ("connector", None, [(300, 0), (310, 0)]),
            ("mvi", 3, [(310, 0), (310, 100)]),
            ("mvi", 4, [(310, 0), (400, 0)]),  # (310, 0) is an intersection
        ]
    )
    seg = network.merge_chains(lines)
    assert len(seg) == 3
    long = seg.loc[seg.length.idxmax()]
    assert round(long.geometry.length) == 310
    assert long["OBJECTID"] == 2 and long["sources"] == "connector,mvi" and long["n_parts"] == 3


def test_ring_hanging_off_the_network_stays_attached() -> None:
    lines = _g(
        [
            ("mvi", 1, [(0, 0), (100, 0)]),
            ("mvi", 2, [(100, 0), (150, 50)]),
            ("mvi", 3, [(150, 50), (100, 100)]),
            ("mvi", 4, [(100, 100), (100, 0)]),  # loop 2-3-4 attached at (100, 0)
        ]
    )
    seg = network.merge_chains(lines)
    assert len(seg) == 2
    assert label_pieces(seg).nunique() == 1


def test_attributes_recovered_from_overlapping_raw_line() -> None:
    lines = _g([("mvi", None, [(0, 5), (200, 5)]), ("osm", None, [(0, 900), (10, 900)])])
    lines["MVITIPO"] = pd.NA
    raw = _g([("mvi", 77, [(0, 0), (200, 0)]), ("mvi", 78, [(0, 300), (200, 300)])])
    raw["MVITIPO"] = ["CL", "KR"]
    out = network.recover_attributes(
        lines.assign(attr_origin=pd.NA),
        raw,
        lines["source"].eq("mvi"),
        "OBJECTID",
        ["OBJECTID", "MVITIPO"],
        15,
    )
    assert out.loc[0, "OBJECTID"] == 77 and out.loc[0, "MVITIPO"] == "CL"
    assert out.loc[0, "attr_origin"] == "recovered"
