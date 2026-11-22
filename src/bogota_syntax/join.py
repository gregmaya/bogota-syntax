"""Cut both cleaned sides at the Bogotá boundary and join them with connectors (ADR-0007).

All geometry is EPSG:9377, lengths in metres.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import shapely.ops
from shapely.geometry import LineString

from bogota_syntax.clean import label_pieces


def lines_only(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Single LineStrings, non-empty."""
    gdf = gdf.explode(ignore_index=True)
    return gdf[(gdf.geom_type == "LineString") & (gdf.length > 0)].reset_index(drop=True)


def loose_ends(lines: gpd.GeoDataFrame, precision_m: float = 0.01) -> gpd.GeoDataFrame:
    """Line ends shared with no other line end: one point per dead end, with `line` index."""
    g = lines.geometry.values
    pts = np.concatenate([shapely.get_point(g, 0), shapely.get_point(g, -1)])
    owner = np.concatenate([np.arange(len(g)), np.arange(len(g))])
    keys = pd.Series([tuple(k) for k in np.round(shapely.get_coordinates(pts) / precision_m)])
    single = keys.map(keys.value_counts()).values == 1
    return gpd.GeoDataFrame(
        {"line": lines.index.values[owner[single]]}, geometry=pts[single], crs=lines.crs
    )


def candidates(
    osm_ends: gpd.GeoDataFrame,
    mvi: gpd.GeoDataFrame,
    mvi_boundary_ends: gpd.GeoDataFrame,
    max_m: float,
) -> gpd.GeoDataFrame:
    """One candidate connector per OSM loose end on the boundary.

    The target is the nearest MVI loose end on the boundary (the same street cut on the
    other side) if one lies within `max_m`; otherwise the nearest point on any MVI line
    within `max_m`. Ends with no MVI within `max_m` get no row. Columns: `osm_end`,
    `target` ("mvi_boundary_end" or "mvi_line"), `length_m`.
    """
    rows = []
    tree_end = shapely.STRtree(mvi_boundary_ends.geometry.values)
    tree_line = shapely.STRtree(mvi.geometry.values)
    for i, p in zip(osm_ends.index, osm_ends.geometry.values, strict=True):
        j, d = tree_end.query_nearest(p, max_distance=max_m, return_distance=True)
        if len(j):
            q = mvi_boundary_ends.geometry.values[j[0]]
            rows.append((i, "mvi_boundary_end", float(d[0]), LineString([p, q])))
            continue
        j, d = tree_line.query_nearest(p, max_distance=max_m, return_distance=True)
        if len(j):
            q = shapely.ops.nearest_points(p, mvi.geometry.values[j[0]])[1]
            rows.append((i, "mvi_line", float(d[0]), LineString([p, q])))
    return gpd.GeoDataFrame(
        rows, columns=["osm_end", "target", "length_m", "geometry"], crs=osm_ends.crs
    )


def stitch(
    mvi: gpd.GeoDataFrame,
    osm: gpd.GeoDataFrame,
    boundary: shapely.Geometry,
    extent: shapely.Geometry,
    snap_m: float,
    candidate_max_m: float,
) -> dict[str, gpd.GeoDataFrame]:
    """Cut MVI to inside the boundary and OSM to outside it (within `extent`), join OSM
    loose ends on the boundary to MVI with connectors up to `snap_m`, and return the
    network and review layers. Candidates up to `candidate_max_m` are kept for review.
    """
    import neatnet

    line = boundary.boundary
    mvi_in = lines_only(mvi.clip(boundary.intersection(extent))).assign(
        source=lambda d: d["source"].fillna("mvi")
    )
    osm_out = lines_only(osm.clip(extent.difference(boundary))).assign(source="osm")
    on_line = 0.01
    osm_ends = loose_ends(osm_out)
    osm_ends = osm_ends[osm_ends.distance(line) < on_line]
    mvi_ends = loose_ends(mvi_in)
    mvi_bnd = mvi_ends[mvi_ends.distance(line) < on_line]
    cand = candidates(osm_ends, mvi_in, mvi_bnd, candidate_max_m)
    cand["accepted"] = cand["length_m"] <= snap_m
    conn = cand[cand["accepted"] & (cand["length_m"] > 0)][["geometry"]].assign(source="connector")
    network = pd.concat([mvi_in, osm_out, conn], ignore_index=True)
    network = gpd.GeoDataFrame(network, geometry="geometry", crs=mvi.crs)
    network = lines_only(neatnet.induce_nodes(network))
    network["piece"] = label_pieces(network)
    matched = set(cand.loc[cand["accepted"], "osm_end"])
    unmatched_osm = osm_ends[~osm_ends.index.isin(matched)]
    # MVI dead ends near the boundary that no accepted connector reaches.
    near = mvi_ends[mvi_ends.distance(line) <= candidate_max_m]
    reached = shapely.union_all(conn.geometry.values).buffer(on_line) if len(conn) else None
    unmatched_mvi = near if reached is None else near[~near.intersects(reached)]
    pieces = network.dissolve("piece", aggfunc={"source": lambda s: ",".join(sorted(set(s)))})
    pieces["length_m"] = network.length.groupby(network["piece"]).sum()
    return {
        "network": network,
        "osm_ends": osm_ends,
        "candidates": cand,
        "unmatched_osm_ends": unmatched_osm,
        "unmatched_mvi_ends": unmatched_mvi,
        "pieces": pieces.reset_index(),
    }


def run(root) -> dict[str, Any]:
    """Build the stitched network and the review layers in data/interim/join/."""
    from bogota_syntax.config import CRS, data_dir, load_analysis

    analysis = load_analysis(root)
    cfg = analysis["join"]
    interim = data_dir(root) / "interim"
    boundary = shapely.union_all(
        gpd.read_parquet(interim / f"{analysis['stitch']['boundary_source']}.parquet")
        .to_crs(CRS)
        .geometry.values
    )
    extent = shapely.union_all(
        gpd.read_parquet(interim / "extent" / "stitch_extent.parquet").geometry.values
    )
    mvi = gpd.read_parquet(interim / "clean" / "mvi_arterial.parquet")
    osm = gpd.read_parquet(interim / "clean" / "osm_cleaned.parquet")
    layers = stitch(mvi, osm, boundary, extent, cfg["snap_m"], cfg["candidate_max_m"])
    out = interim / "join"
    out.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(geometry=[boundary.boundary], crs=CRS).to_parquet(out / "boundary.parquet")
    for name, gdf in layers.items():
        gdf.to_parquet(out / f"{name}.parquet")
    net, cand, pieces = layers["network"], layers["candidates"], layers["pieces"]
    main = pieces["length_m"].max()
    return {
        "lines": len(net),
        "km": net.length.sum() / 1e3,
        "osm_boundary_ends": len(layers["osm_ends"]),
        "connectors": int(cand["accepted"].sum()),
        "unmatched_osm_ends": len(layers["unmatched_osm_ends"]),
        "unmatched_mvi_ends": len(layers["unmatched_mvi_ends"]),
        "pieces": len(pieces),
        "main_km": main / 1e3,
        "other_km": (pieces["length_m"].sum() - main) / 1e3,
    }
