"""Clean each side of the network with neatnet, and check that no piece is lost (ADR-0007).

All geometry is EPSG:9377, lengths in metres.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from bogota_syntax.config import CRS


def prepare(streets: gpd.GeoDataFrame, area: BaseGeometry, source: str) -> gpd.GeoDataFrame:
    """Clip `streets` to `area` and return single 2D LineStrings with a `source` column."""
    out = streets.to_crs(CRS).clip(area).explode(ignore_index=True)
    out = out[(out.geom_type == "LineString") & ~out.geometry.is_empty & (out.length > 0)]
    out = out.copy()
    out["geometry"] = shapely.force_2d(out.geometry.values)
    out.insert(0, "source", source)
    return out.reset_index(drop=True)


def label_pieces(lines: gpd.GeoDataFrame, precision_m: float = 0.01) -> pd.Series:
    """Connected piece id for each line, joining lines that share an endpoint.

    Endpoints are compared after rounding to `precision_m`. Pieces are numbered by length,
    0 being the longest.
    """
    coords = shapely.get_coordinates(
        np.concatenate(
            [
                shapely.get_point(lines.geometry.values, 0),
                shapely.get_point(lines.geometry.values, -1),
            ]
        )
    )
    keys = [tuple(k) for k in np.round(coords / precision_m).astype(np.int64)]
    n = len(lines)
    g = nx.Graph()
    g.add_nodes_from(range(n))
    node_of: dict[tuple, int] = {}
    for i, k in enumerate(keys):
        g.add_edge(i % n, node_of.setdefault(k, i % n))
    comp = np.empty(n, dtype=np.int64)
    for c, members in enumerate(nx.connected_components(g)):
        comp[list(members)] = c
    lengths = pd.Series(lines.length.values).groupby(comp).sum()
    rank = {c: r for r, c in enumerate(lengths.sort_values(ascending=False).index)}
    return pd.Series([rank[c] for c in comp], index=lines.index, name="piece")


def kept_fraction(
    before: gpd.GeoDataFrame, after: gpd.GeoDataFrame, match_m: float, step_m: float
) -> pd.Series:
    """Share of each raw line's length that still has a cleaned line within `match_m`.

    Points are sampled every `step_m` along each raw line (at least its midpoint).
    """
    geoms = before.geometry.values
    n_pts = np.maximum(1, np.ceil(shapely.length(geoms) / step_m).astype(int))
    owner = np.repeat(np.arange(len(geoms)), n_pts)
    frac = np.concatenate([(np.arange(k) + 0.5) / k for k in n_pts])
    pts = shapely.line_interpolate_point(geoms[owner], frac, normalized=True)
    tree = shapely.STRtree(after.geometry.values)
    hit_pts, _ = tree.query_nearest(pts, max_distance=match_m, return_distance=False)
    hit = np.zeros(len(pts), dtype=bool)
    hit[hit_pts] = True
    return pd.Series(
        pd.Series(hit).groupby(owner).mean().reindex(range(len(geoms))).values,
        index=before.index,
        name="kept_fraction",
    )


def compare_pieces(
    before: gpd.GeoDataFrame,
    after: gpd.GeoDataFrame,
    boundary: BaseGeometry,
    match_m: float,
    step_m: float = 10.0,
) -> gpd.GeoDataFrame:
    """One row per piece of `before` (needs a `piece` column, see label_pieces).

    `kept_ratio` is the share of the piece's raw length that still has a cleaned line
    within `match_m`; 0 means the piece is gone. Cleaning merges the two lines of a divided
    road into one between them, so `match_m` must be at least half their separation.
    `touches_boundary` says whether the piece crosses the Bogotá boundary line, so it will
    be joined through the connectors.
    """
    kept = kept_fraction(before, after, match_m, step_m) * before.length
    pieces = before[["piece", "source", "geometry"]].dissolve("piece", aggfunc="first")
    pieces["n_lines"] = before.groupby("piece").size()
    pieces["before_m"] = before.length.groupby(before["piece"]).sum()
    pieces["kept_m"] = kept.groupby(before["piece"]).sum()
    pieces["kept_ratio"] = pieces["kept_m"] / pieces["before_m"]
    pieces["touches_boundary"] = pieces.intersects(boundary.boundary)
    return pieces.reset_index()


def clean_side(
    streets: gpd.GeoDataFrame,
    area: BaseGeometry,
    source: str,
    boundary: BaseGeometry,
    neatify_kwargs: dict[str, Any],
    match_m: float,
    step_m: float = 10.0,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Prepare, label pieces, run neatnet and compare. Returns (raw, cleaned, pieces)."""
    import neatnet

    raw = prepare(streets, area, source)
    raw["piece"] = label_pieces(raw)
    cleaned = neatnet.neatify(raw.drop(columns="piece"), **neatify_kwargs)
    cleaned["source"] = source
    cleaned["piece_after"] = label_pieces(cleaned)
    pieces = compare_pieces(raw, cleaned, boundary, match_m, step_m)
    return raw, cleaned, pieces


SIDES = {"mvi": "ideca_malla_vial", "osm": "osm_vias"}


def failing_pieces(pieces: gpd.GeoDataFrame, min_piece_m: float, min_kept_ratio: float):
    """Pieces at least `min_piece_m` long that kept less than `min_kept_ratio` of their length."""
    return pieces[(pieces["before_m"] >= min_piece_m) & (pieces["kept_ratio"] < min_kept_ratio)]


def run(root, sides: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Clean each side over its cleaning area and write data/interim/clean/<side>_*.parquet.

    Writes the raw input (with `piece`), the cleaned network (with `piece_after`) and the
    piece table. Returns a summary per side. Raises RuntimeError if a piece fails the
    retention rule in config/analysis.yaml (`clean:` block).
    """
    from bogota_syntax.config import data_dir, load_analysis

    analysis = load_analysis(root)
    cfg = analysis["clean"]
    interim = data_dir(root) / "interim"
    boundary = shapely.union_all(
        gpd.read_parquet(interim / f"{analysis['stitch']['boundary_source']}.parquet")
        .to_crs(CRS)
        .geometry.values
    )
    out_dir = interim / "clean"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, Any]] = {}
    failures = []
    for side in sides or list(SIDES):
        area_path = interim / "extent" / f"{side}_clean_area.parquet"
        area = shapely.union_all(gpd.read_parquet(area_path).geometry.values)
        streets = gpd.read_parquet(interim / f"{SIDES[side]}.parquet")
        raw, cleaned, pieces = clean_side(
            streets, area, side, boundary, cfg["neatify"], cfg["match_m"], cfg["sample_step_m"]
        )
        raw.to_parquet(out_dir / f"{side}_raw.parquet")
        cleaned.to_parquet(out_dir / f"{side}_cleaned.parquet")
        pieces.to_parquet(out_dir / f"{side}_pieces.parquet")
        bad = failing_pieces(pieces, cfg["min_piece_m"], cfg["min_kept_ratio"])
        if len(bad):
            failures.append(f"{side}: pieces {bad['piece'].tolist()}")
        summary[side] = {
            "raw_lines": len(raw),
            "raw_km": raw.length.sum() / 1e3,
            "cleaned_lines": len(cleaned),
            "cleaned_km": cleaned.length.sum() / 1e3,
            "pieces_before": len(pieces),
            "pieces_after": int(cleaned["piece_after"].nunique()),
            "pieces_vanished": int((pieces["kept_ratio"] == 0).sum()),
            "pieces_failing": len(bad),
        }
    if failures:
        raise RuntimeError(
            "pieces lost in cleaning (see data/interim/clean/*_pieces.parquet): "
            + "; ".join(failures)
        )
    return summary
