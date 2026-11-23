"""Finish the stitched network into segments from intersection to intersection (ADR-0009).

All geometry is EPSG:9377, lengths in metres.
"""

from __future__ import annotations

import hashlib
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiLineString

from bogota_syntax.clean import label_pieces
from bogota_syntax.join import lines_only

# Source attributes kept as published (CLAUDE.md rule 6).
MVI_COLS = [
    "OBJECTID", "MVICODIGO", "MVICIV", "MVICCALZAD", "MVICCAT", "MVITCLA", "MVITIPO",
    "MVINOMBRE", "MVINALTERN", "MVINPRINCI", "MVINGENERA", "MVINANTIGU", "MVIETIQUET",
    "MVISVIA", "MVINUMC", "MVIVELREG",
]  # fmt: skip
SDP_COLS = ["NOMBRE", "TIPO_VIA", "ESTADO_VIA"]
OSM_COLS = ["osmid", "highway", "name", "oneway", "lanes", "maxspeed"]
MVI_SOURCES = {"mvi", "mvi_restored"}


def recover_attributes(
    lines: gpd.GeoDataFrame,
    raw: gpd.GeoDataFrame,
    is_target: pd.Series,
    id_col: str,
    cols: list[str],
    max_m: float,
) -> gpd.GeoDataFrame:
    """Fill `cols` on target lines that lack `id_col` (lines drawn by neatnet) from the raw
    line with the most length within `max_m` of them. Sets `attr_origin` to "recovered";
    lines with no raw line in reach keep "none"."""
    lines = lines.copy()
    need = lines.index[is_target.values & lines[id_col].isna().values]
    lines.loc[is_target.values & lines[id_col].notna().values, "attr_origin"] = "own"
    lines.loc[need, "attr_origin"] = "none"
    if not len(need):
        return lines
    zones = lines.loc[need].buffer(max_m).values
    zi, ri = shapely.STRtree(raw.geometry.values).query(zones, predicate="intersects")
    overlap = shapely.length(shapely.intersection(raw.geometry.values[ri], zones[zi]))
    best = (
        pd.DataFrame({"z": zi, "r": ri, "o": overlap})
        .sort_values("o")
        .drop_duplicates("z", keep="last")
    )
    target_idx = need[best["z"].values]
    for c in cols:
        if c in raw.columns:
            lines.loc[target_idx, c] = raw[c].values[best["r"].values]
    lines.loc[target_idx, "attr_origin"] = "recovered"
    return lines


def collapse_short(lines: gpd.GeoDataFrame, min_m: float) -> gpd.GeoDataFrame:
    """Remove lines shorter than `min_m` without disconnecting anything: the line ends that
    met its far end are moved onto its near end. Loops that short are dropped.

    cityseer drops degenerate segments (a few centimetres) when it builds its graph; doing
    it here keeps the network and cityseer's graph identical (ADR-0009)."""
    lines = lines.reset_index(drop=True).copy()
    while True:
        short = lines.index[lines.length < min_m]
        if not len(short):
            return lines.reset_index(drop=True)
        i = short[0]
        coords = np.asarray(lines.geometry[i].coords)
        a, b = coords[0], coords[-1]
        lines = lines.drop(index=i)
        if np.allclose(a, b, atol=0.01, rtol=0):
            continue
        near = lines.index[lines.intersects(shapely.Point(b).buffer(0.02))]
        for j in near:
            c = np.asarray(lines.geometry[j].coords).copy()
            if np.allclose(c[0], b, atol=0.01, rtol=0):
                c[0] = a
            if np.allclose(c[-1], b, atol=0.01, rtol=0):
                c[-1] = a
            lines.at[j, "geometry"] = shapely.LineString(c)


def merge_chains(lines: gpd.GeoDataFrame, precision_m: float = 0.01) -> gpd.GeoDataFrame:
    """Merge lines through points where exactly two line ends meet, so each output line runs
    from an intersection or dead end to the next. Attributes come from the longest part;
    `sources` lists every source merged, `n_parts` how many lines."""
    g = lines.geometry.values
    n = len(g)
    ends = np.concatenate([shapely.get_point(g, 0), shapely.get_point(g, -1)])
    keys = pd.Series([tuple(k) for k in np.round(shapely.get_coordinates(ends) / precision_m)])
    owner = np.concatenate([np.arange(n), np.arange(n)])
    groups = pd.DataFrame({"key": keys, "line": owner}).groupby("key")["line"].agg(list)
    degree = groups.map(len)
    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    for members in groups:
        if len(members) == 2 and members[0] != members[1]:
            graph.add_edge(members[0], members[1])
    rows = []
    lengths = shapely.length(g)
    for comp in nx.connected_components(graph):
        idx = sorted(comp)
        main = idx[int(np.argmax(lengths[idx]))]
        row = lines.iloc[main].copy()
        if len(idx) > 1:
            merged = shapely.line_merge(MultiLineString(list(g[idx])))
            if merged.geom_type == "LineString" and merged.is_closed:
                # A ring hanging off the network must start where it attaches.
                ends_idx = np.concatenate([idx, np.array(idx) + n])
                attach = [keys[i] for i in ends_idx if degree[keys[i]] != 2]
                if attach:
                    merged = _start_ring_at(merged, np.array(attach[0]) * precision_m)
            row["geometry"] = merged
        row["sources"] = ",".join(sorted(set(lines["source"].iloc[idx].astype(str))))
        row["n_parts"] = len(idx)
        rows.append(row)
    out = gpd.GeoDataFrame(rows, geometry="geometry", crs=lines.crs).reset_index(drop=True)
    return lines_only(out)


def _start_ring_at(ring: shapely.LineString, xy: np.ndarray) -> shapely.LineString:
    """Rotate a closed LineString so it starts and ends at its vertex nearest `xy`."""
    coords = np.asarray(ring.coords)[:-1]
    k = int(np.argmin(((coords - xy) ** 2).sum(axis=1)))
    rotated = np.vstack([coords[k:], coords[:k], coords[k : k + 1]])
    return shapely.LineString(rotated)


def segment_id(geoms: np.ndarray) -> list[str]:
    """Stable id from the geometry: 12 hex characters of a SHA-1 of the normalised
    geometry rounded to the centimetre."""
    norm = shapely.normalize(shapely.set_precision(geoms, 0.01))
    return [hashlib.sha1(shapely.to_wkb(x)).hexdigest()[:12] for x in norm]


def finish(
    stitched: gpd.GeoDataFrame,
    mvi_raw: gpd.GeoDataFrame,
    osm_raw: gpd.GeoDataFrame | None,
    recover_m: float,
    boundary: shapely.Geometry,
    min_segment_m: float = 0.5,
) -> gpd.GeoDataFrame:
    """Drop duplicate lines, recover attributes, merge to intersection-to-intersection
    segments and label pieces. Returns the segment network with a fixed column order.

    Duplicates go first: removing one after merging could leave a point where only two
    lines meet, which is not an intersection."""
    lines = lines_only(stitched)
    # Same geometry to the centimetre counts as a duplicate. Where an SDP axis and an MVI
    # line coincide, the axis is kept (ADR-0008).
    priority = lines["source"].map({"sdp_eje_vial": 0}).fillna(1).values
    lines = lines.iloc[np.argsort(priority, kind="stable")]
    rounded = shapely.normalize(shapely.set_precision(lines.geometry.values, 0.01))
    dup = pd.Series(shapely.to_wkb(rounded)).duplicated()
    lines = lines[~dup.values].reset_index(drop=True).assign(attr_origin=pd.NA)
    lines = recover_attributes(
        lines, mvi_raw, lines["source"].isin(MVI_SOURCES), "OBJECTID", MVI_COLS, recover_m
    )
    if osm_raw is not None:
        lines = recover_attributes(
            lines, osm_raw, lines["source"].eq("osm"), "osmid", OSM_COLS, recover_m
        )
    lines = lines.rename(columns={"_status": "neatnet_status"})
    lines = collapse_short(lines, min_segment_m)
    seg = merge_chains(lines).reset_index(drop=True)
    seg["segment_id"] = segment_id(seg.geometry.values)
    seg["length_m"] = seg.length.round(2)
    start = shapely.get_coordinates(shapely.get_point(seg.geometry.values, 0))
    end = shapely.get_coordinates(shapely.get_point(seg.geometry.values, -1))
    seg["is_loop"] = np.all(np.abs(start - end) < 0.01, axis=1)
    seg["piece"] = label_pieces(seg)
    seg["in_main"] = seg["piece"].eq(0)
    # Distance to the Bogotá boundary: where it is below the analysis distance, routes
    # beyond the city are missing (edge effect, ADR-0010).
    seg["boundary_dist_m"] = shapely.distance(seg.geometry.values, boundary.boundary).round(1)
    head = [
        "segment_id", "length_m", "source", "sources", "n_parts", "piece", "in_main",
        "is_loop", "boundary_dist_m", "attr_origin", "neatnet_status",
    ]  # fmt: skip
    cols = head + [c for c in MVI_COLS + SDP_COLS + OSM_COLS if c in seg.columns]
    return seg[[*cols, "geometry"]]


def summary(seg: gpd.GeoDataFrame) -> dict[str, Any]:
    """Counts for the CLI and the changelog."""
    g = seg.geometry.values
    ends = np.concatenate([shapely.get_point(g, 0), shapely.get_point(g, -1)])
    keys = pd.Series([tuple(k) for k in np.round(shapely.get_coordinates(ends), 2)])
    deg = keys.value_counts()
    by_source = seg.groupby("source").agg(
        n=("segment_id", "size"), km=("length_m", lambda s: s.sum() / 1e3)
    )
    origin = seg.groupby(["source", seg["attr_origin"].fillna("n/a")]).size()
    return {
        "segments": len(seg),
        "km": seg["length_m"].sum() / 1e3,
        "nodes": len(deg),
        "degree2_nodes": int((deg == 2).sum()),
        "loops": int(seg["is_loop"].sum()),
        "pieces": int(seg["piece"].nunique()),
        "main_km": seg.loc[seg["in_main"], "length_m"].sum() / 1e3,
        "median_m": float(seg["length_m"].median()),
        "by_source": by_source,
        "attr_origin": origin,
    }


def mvi_only(cleaned: gpd.GeoDataFrame, boundary, extend_m: float) -> gpd.GeoDataFrame:
    """v1 network (ADR-0010): cleaned MVI clipped to the Bogotá boundary, with dead ends
    extended onto a line within `extend_m` (neatnet.extend_lines)."""
    from bogota_syntax.arterials import extend_dead_ends

    lines = lines_only(cleaned.clip(boundary)).assign(source="mvi")
    lines, _ = extend_dead_ends(lines, extend_m)
    return lines_only(lines)


def run(root) -> dict[str, Any]:
    """Build data/processed/network.parquet in the mode set in config/analysis.yaml.

    `mvi_only` (v1, ADR-0010) reads data/interim/clean/mvi_cleaned.parquet; `stitched`
    (ADR-0007, ADR-0008, shelved) reads data/interim/join/network.parquet.
    """
    from bogota_syntax.config import CRS, data_dir, load_analysis

    analysis = load_analysis(root)
    cfg = analysis["network"]
    data = data_dir(root)
    interim = data / "interim"
    boundary = shapely.union_all(
        gpd.read_parquet(interim / f"{analysis['stitch']['boundary_source']}.parquet")
        .to_crs(CRS)
        .geometry.values
    )
    mvi_raw = gpd.read_parquet(interim / "clean" / "mvi_raw.parquet")
    if cfg["mode"] == "mvi_only":
        cleaned = gpd.read_parquet(interim / "clean" / "mvi_cleaned.parquet")
        lines = mvi_only(cleaned, boundary, cfg["extend_lines_m"])
        seg = finish(lines, mvi_raw, None, cfg["recover_m"], boundary, cfg["min_segment_m"])
    elif cfg["mode"] == "stitched":
        stitched = gpd.read_parquet(interim / "join" / "network.parquet")
        osm_raw = gpd.read_parquet(interim / "clean" / "osm_raw.parquet")
        seg = finish(stitched, mvi_raw, osm_raw, cfg["recover_m"], boundary, cfg["min_segment_m"])
    else:
        raise ValueError(f"network.mode must be mvi_only or stitched, not {cfg['mode']!r}")
    out = data / "processed" / "network.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    seg.to_parquet(out)
    return summary(seg) | {"path": out, "mode": cfg["mode"]}
