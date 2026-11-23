"""Simplest-path centrality on the segment (dual) graph with cityseer (ADR-0009).

All geometry is EPSG:9377; distances in metres.
"""

from __future__ import annotations

import time
from typing import Any

import geopandas as gpd
import shapely

from bogota_syntax.config import CRS


def run_centrality(
    segments: gpd.GeoDataFrame,
    live: shapely.Geometry,
    distances: list[int],
) -> gpd.GeoDataFrame:
    """Closeness and betweenness by simplest (angular) path at `distances`.

    `segments` is the finished network (one row per intersection-to-intersection segment,
    with `segment_id`). Segments whose midpoint lies in `live` are reported; the rest are
    routed through only (ADR-0004). cityseer's own cleaning is switched off, so its graph
    has exactly these segments. Returns one row per segment with cityseer's columns
    (`live`, `cc_harmonic_<d>_ang`, `cc_betweenness_<d>_ang`) joined to `segments`.
    """
    from cityseer.network import CityNetwork

    cn = CityNetwork.from_geopandas(
        segments[["segment_id", "geometry"]],
        crs=CRS,
        boundary=live,
        directed=False,
        remove_fillers=False,
        remove_danglers=0,
        merge_parallel_dist=0,
        segment_weighted=False,
    )
    cn.centrality_simplest(distances=distances)
    res = cn.to_geopandas().drop(columns="geometry")
    if len(res) != len(segments) or not res["segment_id"].is_unique:
        raise RuntimeError(
            f"cityseer returned {len(res)} rows for {len(segments)} segments; "
            "its graph no longer matches the network"
        )
    keep = ["segment_id", "live"] + [c for c in res.columns if c.startswith("cc_")]
    return segments.merge(res[keep], on="segment_id", how="left", validate="1:1")


def run(root) -> dict[str, Any]:
    """Pilot run: the network within the pilot network extent, live in the live area.

    Reads data/processed/network.parquet and data/interim/extent/; writes
    data/processed/centrality_pilot.parquet.
    """
    from bogota_syntax.config import data_dir, load_analysis

    analysis = load_analysis(root)
    data = data_dir(root)
    ext = data / "interim" / "extent"
    network_extent = shapely.union_all(
        gpd.read_parquet(ext / "network_extent.parquet").geometry.values
    )
    live = shapely.union_all(gpd.read_parquet(ext / "live_area.parquet").geometry.values)
    segments = gpd.read_parquet(data / "processed" / "network.parquet")
    segments = segments[segments.intersects(network_extent)].reset_index(drop=True)
    t0 = time.time()
    out = run_centrality(segments, live, analysis["distances"])
    seconds = time.time() - t0
    path = data / "processed" / "centrality_pilot.parquet"
    out.to_parquet(path)
    return {
        "segments": len(out),
        "live": int(out["live"].sum()),
        "km": out.length.sum() / 1e3,
        "seconds": seconds,
        "columns": [c for c in out.columns if c.startswith("cc_")],
        "path": path,
    }
