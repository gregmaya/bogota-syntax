"""Piece labelling and retention checks (ADR-0007), on synthetic lines in EPSG:9377."""

import geopandas as gpd
from shapely.geometry import LineString, box

from bogota_syntax import clean

X0, Y0 = 4_880_000, 2_070_000


def _lines(coords: list[list[tuple[float, float]]]) -> gpd.GeoDataFrame:
    geoms = [LineString([(X0 + x, Y0 + y) for x, y in c]) for c in coords]
    return gpd.GeoDataFrame({"source": ["mvi"] * len(geoms)}, geometry=geoms, crs="EPSG:9377")


def test_pieces_join_on_shared_endpoints_and_are_ranked_by_length() -> None:
    g = _lines(
        [
            [(0, 0), (100, 0)],
            [(100, 0), (100, 100)],  # shares an end with the first
            [(500, 0), (520, 0)],  # isolated, short
        ]
    )
    assert clean.label_pieces(g).tolist() == [0, 0, 1]


def test_kept_fraction_tolerates_merged_carriageways() -> None:
    # Two carriageways 60 m apart, cleaned into one centreline between them.
    raw = _lines([[(0, 0), (200, 0)], [(0, 60), (200, 60)]])
    centre = _lines([[(0, 30), (200, 30)]])
    assert clean.kept_fraction(raw, centre, 50, 10).tolist() == [1.0, 1.0]
    assert clean.kept_fraction(raw, centre, 25, 10).tolist() == [0.0, 0.0]


def test_compare_pieces_flags_a_vanished_piece() -> None:
    raw = _lines([[(0, 0), (1000, 0)], [(3000, 0), (3200, 0)]])
    raw["piece"] = clean.label_pieces(raw)
    after = raw.iloc[[0]].drop(columns="piece")
    boundary = box(X0 - 10, Y0 - 10, X0 + 500, Y0 + 500)
    p = clean.compare_pieces(raw, after, boundary, 50).set_index("piece")
    assert p.loc[0, "kept_ratio"] == 1.0 and p.loc[0, "touches_boundary"]
    assert p.loc[1, "kept_ratio"] == 0.0 and not p.loc[1, "touches_boundary"]
    assert clean.failing_pieces(p, 100, 0.5).index.tolist() == [1]
    assert clean.failing_pieces(p, 300, 0.5).empty
