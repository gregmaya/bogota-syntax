"""Centrality on a synthetic grid (ADR-0009): one row per segment, live by midpoint."""

import geopandas as gpd
from shapely.geometry import LineString, box

from bogota_syntax.centrality import run_centrality
from bogota_syntax.config import load_analysis
from bogota_syntax.network import segment_id

X0, Y0 = 4_880_000, 2_070_000


def _grid(n: int = 6, step: float = 100) -> gpd.GeoDataFrame:
    lines = []
    for i in range(n + 1):
        for j in range(n):
            lines.append(
                LineString([(X0 + j * step, Y0 + i * step), (X0 + (j + 1) * step, Y0 + i * step)])
            )
            lines.append(
                LineString([(X0 + i * step, Y0 + j * step), (X0 + i * step, Y0 + (j + 1) * step)])
            )
    g = gpd.GeoDataFrame(geometry=lines, crs="EPSG:9377")
    g["segment_id"] = segment_id(g.geometry.values)
    return g


def test_one_row_per_segment_and_live_by_midpoint() -> None:
    g = _grid()
    live = box(X0 + 150, Y0 + 150, X0 + 450, Y0 + 450)
    measures = load_analysis()["centrality"]
    out = run_centrality(g, live, [400], measures)
    assert len(out) == len(g) and out["segment_id"].is_unique
    names = ["density", "farness", "harmonic", "hillier", "betweenness"]
    assert {f"cc_{n}_400_ang" for n in names} <= set(out.columns)
    lv = out[out["live"]]
    hil = lv["cc_density_400_ang"] ** 2 / lv["cc_farness_400_ang"]
    assert (abs(hil - lv["cc_hillier_400_ang"]) < 1e-6 * hil).all()
    mid = out.geometry.interpolate(0.5, normalized=True)
    assert (out["live"] == mid.within(live)).all()
    # Live segments in the middle of a grid reach others; dead ones get no closeness.
    assert (out.loc[out["live"], "cc_harmonic_400_ang"] > 0).all()
    assert (out.loc[~out["live"], "cc_harmonic_400_ang"] == 0).all()
