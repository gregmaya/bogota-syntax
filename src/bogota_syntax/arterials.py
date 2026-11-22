"""SDP arterial axes as the geometry of built arterials inside Bogotá (ADR-0008, Proposed).

Raw MVI lines that belong to a built arterial are replaced by its axis before neatnet
runs. All geometry is EPSG:9377, lengths in metres.
"""

from __future__ import annotations

import itertools

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
import shapely.ops
from shapely.geometry import LineString, Point

from bogota_syntax.clean import kept_fraction, label_pieces


def select_axes(
    axes: gpd.GeoDataFrame, mvi: gpd.GeoDataFrame, match_m: float, min_on_mvi: float
) -> gpd.GeoDataFrame:
    """Axes (single LineStrings) with at least `min_on_mvi` of their length within `match_m`
    of an MVI line: built arterials, chosen by geometry, not by ESTADO_VIA."""
    a = axes.explode(ignore_index=True)
    a = a[a.geom_type == "LineString"].copy()
    a["geometry"] = shapely.force_2d(a.geometry.values)
    a["on_mvi"] = kept_fraction(a, mvi, match_m, 10).values
    return a[a["on_mvi"] >= min_on_mvi].reset_index(drop=True)


def arterial_lines(
    mvi: gpd.GeoDataFrame,
    axes: gpd.GeoDataFrame,
    corridor_m: float,
    arterial_types: list[str],
    min_inside: float = 0.5,
) -> pd.Series:
    """True for MVI lines to remove: an arterial or empty type, with at least `min_inside` of their
    length inside `corridor_m` of a selected axis. Untyped lines count as arterial."""
    corridor = shapely.union_all(axes.buffer(corridor_m).values)
    inside = shapely.length(shapely.intersection(mvi.geometry.values, corridor)) / mvi.length
    typ = mvi["MVITIPO"].fillna("").str.strip()
    # Untyped lines (blank in MVI, or created by neatnet) inside the corridor are mostly
    # ramps and merged carriageways.
    is_type = typ.isin(arterial_types) | (typ == "")
    return pd.Series((inside >= min_inside) & is_type.values, index=mvi.index)


def _endpoints(geoms: np.ndarray) -> np.ndarray:
    return np.stack(
        [
            shapely.get_coordinates(shapely.get_point(geoms, 0)),
            shapely.get_coordinates(shapely.get_point(geoms, -1)),
        ],
        axis=1,
    )


def _key(xy: np.ndarray, precision_m: float = 0.01) -> tuple[int, int]:
    return tuple(np.round(xy / precision_m).astype(np.int64))


def connect_axes(axes: gpd.GeoDataFrame, removed: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Split axes at crossings where the interchange had ramps: their removed MVI lines are
    connected in one piece. Other crossings stay unsplit (a bridge to neatnet)."""
    if removed.empty:
        return axes
    # Assign each removed line to its nearest axis, then find connected groups.
    near = gpd.sjoin_nearest(removed[["geometry"]], axes[["geometry"]], how="left")
    near = near[~near.index.duplicated()]
    g = nx.Graph()
    ends = _endpoints(removed.geometry.values)
    for i, (a, b) in zip(removed.index, ends, strict=True):
        g.add_edge(("l", i), ("p", _key(a)))
        g.add_edge(("l", i), ("p", _key(b)))
    linked: set[tuple[int, int]] = set()
    for comp in nx.connected_components(g):
        idx = [n[1] for n in comp if n[0] == "l"]
        ax = sorted(set(near.loc[idx, "index_right"].dropna().astype(int)))
        linked |= {(p, q) for p in ax for q in ax if p < q}
    cuts: dict[int, list[Point]] = {}
    for p, q in linked:
        x = axes.geometry.iloc[p].intersection(axes.geometry.iloc[q])
        pts = [g for g in getattr(x, "geoms", [x]) if g.geom_type == "Point"]
        cuts.setdefault(p, []).extend(pts)
        cuts.setdefault(q, []).extend(pts)
    rows = []
    for i, row in axes.iterrows():
        geoms = [row.geometry]
        if i in cuts:
            geoms = _split_line(row.geometry, cuts[i])
        for geom in geoms:
            rows.append({**row.drop("geometry").to_dict(), "geometry": geom})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=axes.crs)


def _split_line(line: LineString, points: list[Point]) -> list[LineString]:
    """Split `line` at the projections of `points` onto it."""
    ds = sorted({line.project(p) for p in points if 0 < line.project(p) < line.length})
    if not ds:
        return [line]
    bounds = [0.0, *ds, line.length]
    return [shapely.ops.substring(line, a, b) for a, b in itertools.pairwise(bounds)]


def reconnect(
    kept: gpd.GeoDataFrame,
    removed: gpd.GeoDataFrame,
    axes: gpd.GeoDataFrame,
    corridor_m: float,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Join kept MVI lines that touched a removed line to the axes.

    A kept line that crosses an axis is split there, and the part between the crossing
    and its loose end (inside the corridor) is dropped. A kept line that ends short of
    the axis gets a straight connector to the nearest point on it, if within `corridor_m`.
    Returns (kept lines, connectors).
    """
    removed_keys = {_key(p) for p in _endpoints(removed.geometry.values).reshape(-1, 2)}
    ax_union = shapely.union_all(axes.geometry.values)
    corridor = ax_union.buffer(corridor_m)
    out_rows, connectors = [], []
    for _, row in kept.iterrows():
        line = row.geometry
        a, b = _endpoints(np.array([line]))[0]
        loose = [_key(a) in removed_keys, _key(b) in removed_keys]
        if not any(loose):
            out_rows.append(row)
            continue
        x = line.intersection(ax_union)
        pts = [g for g in getattr(x, "geoms", [x]) if g.geom_type == "Point"]
        if pts:
            parts = _split_line(line, pts)
            for k, part in enumerate(parts):
                first, last = k == 0, k == len(parts) - 1
                dangling = (first and loose[0]) or (last and loose[1])
                if dangling and part.within(corridor):
                    continue
                out_rows.append(_with_geom(row, part))
            continue
        out_rows.append(row)
        for end, is_loose in zip((a, b), loose, strict=True):
            if is_loose:
                p = Point(end)
                target = shapely.ops.nearest_points(p, ax_union)[1]
                if 0 < p.distance(target) <= corridor_m:
                    connectors.append(LineString([p, target]))
    kept_out = gpd.GeoDataFrame(out_rows, geometry="geometry", crs=kept.crs)
    conn = gpd.GeoDataFrame(geometry=connectors, crs=kept.crs)
    return kept_out, conn


def _with_geom(row: pd.Series, geom) -> pd.Series:
    row = row.copy()
    row["geometry"] = geom
    return row


def stranded_lines(
    mvi: gpd.GeoDataFrame, is_removed: pd.Series, axes: gpd.GeoDataFrame, zone_m: float
) -> pd.Series:
    """True for kept lines left stranded by the removal: ramps and loops typed as local
    streets. A piece of the kept network is stranded if it lies entirely within `zone_m` of
    a selected axis and touched a removed line, so it only reached the rest of the network
    through the arterial."""
    kept = mvi[~is_removed]
    pieces = label_pieces(kept)
    zone = shapely.union_all(axes.buffer(zone_m).values)
    removed_keys = {_key(p) for p in _endpoints(mvi[is_removed].geometry.values).reshape(-1, 2)}
    ends = _endpoints(kept.geometry.values)
    touches = pd.Series(
        [(_key(a) in removed_keys) or (_key(b) in removed_keys) for a, b in ends],
        index=kept.index,
    )
    inside = pd.Series(shapely.within(kept.geometry.values, zone), index=kept.index)
    by_piece = pd.DataFrame({"piece": pieces, "touches": touches, "inside": inside})
    agg = by_piece.groupby("piece").agg(touches=("touches", "any"), inside=("inside", "all"))
    bad = set(agg.index[agg["touches"] & agg["inside"]])
    out = pd.Series(False, index=mvi.index)
    out.loc[kept.index[pieces.isin(bad).values]] = True
    return out


def guide(
    mvi: gpd.GeoDataFrame,
    axes: gpd.GeoDataFrame,
    corridor_m: float,
    arterial_types: list[str],
    zone_m: float,
) -> dict[str, gpd.GeoDataFrame]:
    """Replace arterial MVI lines by the selected axes. Returns the layers for review and
    `edited`, the network to pass to neatnet (with a `source` column)."""
    is_art = arterial_lines(mvi, axes, corridor_m, arterial_types)
    is_art = is_art | stranded_lines(mvi, is_art, axes, zone_m)
    removed, kept = mvi[is_art], mvi[~is_art]
    axes_split = connect_axes(axes, removed)
    kept2, conn = reconnect(kept, removed, axes_split, corridor_m)
    ax = axes_split[["NOMBRE", "ESTADO_VIA", "TIPO_VIA", "geometry"]].assign(source="sdp_eje_vial")
    conn = conn.assign(source="axis_connector")
    edited = pd.concat([kept2, ax, conn], ignore_index=True)
    edited = gpd.GeoDataFrame(edited, geometry="geometry", crs=mvi.crs)
    edited = edited[~edited.geometry.is_empty & (edited.length > 0)].reset_index(drop=True)
    return {"removed": removed, "axes": ax, "connectors": conn, "edited": edited}


def dead_end_count(lines: gpd.GeoDataFrame) -> int:
    """Line ends that meet no other line end."""
    keys = [_key(p) for p in _endpoints(lines.geometry.values).reshape(-1, 2)]
    counts = pd.Series(keys).value_counts()
    return int((counts == 1).sum())


def run(root) -> dict[str, float]:
    """Swap the SDP axes into cleaned MVI over the MVI cleaning area (ADR-0008).

    Reads data/interim/clean/mvi_{raw,cleaned}.parquet and the ingested axes; writes
    data/interim/clean/mvi_arterial.parquet (the network for the join) and the review
    layers arterial_{removed,axes,connectors}.parquet. Returns a summary.
    """
    import neatnet

    from bogota_syntax.config import CRS, data_dir, load_analysis

    cfg = load_analysis(root)["arterials"]
    interim = data_dir(root) / "interim"
    clean_dir = interim / "clean"
    raw = gpd.read_parquet(clean_dir / "mvi_raw.parquet")
    cleaned = gpd.read_parquet(clean_dir / "mvi_cleaned.parquet")
    area = shapely.union_all(
        gpd.read_parquet(interim / "extent" / "mvi_clean_area.parquet").geometry.values
    )
    eje = gpd.read_parquet(interim / f"{cfg['source']}.parquet").to_crs(CRS).clip(area)
    axes = select_axes(eje, raw, cfg["axis_match_m"], cfg["min_axis_on_mvi"])
    cleaned = cleaned.explode(ignore_index=True)
    cleaned = cleaned[cleaned.geom_type == "LineString"].reset_index(drop=True)
    out = guide(cleaned, axes, cfg["corridor_m"], cfg["arterial_types"], cfg["ramp_zone_m"])
    network = neatnet.induce_nodes(out["edited"])
    network["source"] = network["source"].fillna("mvi")
    network.to_parquet(clean_dir / "mvi_arterial.parquet")
    for name in ("removed", "axes", "connectors"):
        out[name].to_parquet(clean_dir / f"arterial_{name}.parquet")
    conn = out["connectors"]
    return {
        "axes_lines": len(axes),
        "axes_km": axes.length.sum() / 1e3,
        "removed_lines": len(out["removed"]),
        "removed_km": out["removed"].length.sum() / 1e3,
        "connectors": len(conn),
        "connector_median_m": float(conn.length.median()) if len(conn) else 0.0,
        "connector_max_m": float(conn.length.max()) if len(conn) else 0.0,
        "lines_before": len(cleaned),
        "lines_after": len(network),
        "km_before": cleaned.length.sum() / 1e3,
        "km_after": network.length.sum() / 1e3,
        "dead_ends_before": dead_end_count(neatnet.induce_nodes(cleaned)),
        "dead_ends_after": dead_end_count(network),
        "pieces_before": int(label_pieces(neatnet.induce_nodes(cleaned)).nunique()),
        "pieces_after": int(label_pieces(network).nunique()),
    }
