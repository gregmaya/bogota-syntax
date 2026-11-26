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
    measures: dict[str, dict[str, str]] | None = None,
) -> gpd.GeoDataFrame:
    """Closeness and betweenness by simplest (angular) path at `distances`.

    `segments` is the finished network (one row per intersection-to-intersection segment,
    with `segment_id`). Segments whose midpoint lies in `live` are reported; the rest are
    routed through only (ADR-0004). cityseer's own cleaning is switched off, so its graph
    has exactly these segments. `measures` holds cityseer's `closeness`, `betweenness` and
    `postprocess` expression dicts (config/analysis.yaml `centrality:`); None keeps
    cityseer's CityNetwork defaults (harmonic and betweenness only). Returns one row per
    segment with `live` and the `cc_<name>_<d>_ang` columns joined to `segments`.
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
    cn.centrality_simplest(distances=distances, **(measures or {}))
    res = cn.to_geopandas().drop(columns="geometry")
    if len(res) != len(segments) or not res["segment_id"].is_unique:
        raise RuntimeError(
            f"cityseer returned {len(res)} rows for {len(segments)} segments; "
            "its graph no longer matches the network"
        )
    keep = ["segment_id", "live"] + [c for c in res.columns if c.startswith("cc_")]
    return segments.merge(res[keep], on="segment_id", how="left", validate="1:1")


def run(root, area: str = "pilot", network: str = "v1") -> dict[str, Any]:
    """Run centrality on a finished network version.

    - `network`: `v1` reads data/processed/network.parquet and writes
      centrality_<area>.parquet (as before); any other version `vN` (or `vN.M` after manual
      edits) reads network_vN.parquet and writes centrality_<area>_vN.parquet.

    - `pilot`: segments within the pilot network extent, live in the pilot live area
      (ADR-0004).
    - `city`: every segment, live inside the SDP urban perimeter; the rest of the network
      (inside Bogotá, up to the stitch margin beyond the perimeter) is the dead buffer.
    """
    from bogota_syntax.config import data_dir, load_analysis

    analysis = load_analysis(root)
    data = data_dir(root)
    suffix = "" if network == "v1" else f"_{network}"
    segments = gpd.read_parquet(data / "processed" / f"network{suffix}.parquet")
    if area == "pilot":
        ext = data / "interim" / "extent"
        network_extent = shapely.union_all(
            gpd.read_parquet(ext / "network_extent.parquet").geometry.values
        )
        live = shapely.union_all(gpd.read_parquet(ext / "live_area.parquet").geometry.values)
        segments = segments[segments.intersects(network_extent)].reset_index(drop=True)
    elif area == "city":
        urban = data / "interim" / f"{analysis['stitch']['urban_source']}.parquet"
        live = shapely.union_all(gpd.read_parquet(urban).to_crs(CRS).geometry.values)
    else:
        raise ValueError(f"area must be pilot or city, not {area!r}")
    t0 = time.time()
    out = run_centrality(segments, live, analysis["distances"], analysis["centrality"])
    seconds = time.time() - t0
    path = data / "processed" / f"centrality_{area}{suffix}.parquet"
    out.to_parquet(path)
    return {
        "segments": len(out),
        "live": int(out["live"].sum()),
        "km": out.length.sum() / 1e3,
        "seconds": seconds,
        "columns": [c for c in out.columns if c.startswith("cc_")],
        "path": path,
    }
