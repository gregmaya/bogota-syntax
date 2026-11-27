"""Foreground network: SDP Eje Vial cleaned with the POT arterial polygons (ADR-0012).

Classify, then correct: dead ends are classified by the arterial polygons they sit in,
and only `critical` ones are extended or connected. Every correction is kept as its own
layer for review. All geometry EPSG:9377, lengths in metres, angles in degrees.

Steps (numbers as in ADR-0012):
0. prepare: explode, drop duplicate and zero-length lines; polygon neighbours.
1. snap_dead_ends      2. node_all            3. drop_stubs
4. classify            5. pair_dead_ends      6. extend_step (in growing steps)
7. merge_junctions     8. connect             9. node_all + consolidate
10. simplify_lines     11. relocate_centres (interchanges: decisions, else a rule)
12. apply_edits (reviewed manual edits, applied last as drawn)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import geopandas as gpd
import neatnet
import networkx as nx
import numpy as np
import pandas as pd
import shapely
import shapely.ops

from bogota_syntax.network import merge_chains

CLASSES = ("critical", "corridor_end", "no_polygon")


@dataclass(frozen=True)
class Params:
    """The `foreground:` block of config/analysis.yaml (ADR-0012)."""

    polygon_touch_m: float  # polygons this close are neighbours
    dead_end_near_m: float  # a dead end belongs to the polygons within this distance
    connected_m: float  # an end this close to another line is connected
    area_pad_m: float  # slack when checking a new piece stays inside the polygons
    direction_back_m: float  # an end's direction is taken over this length
    snap_m: float
    stub_m: float
    duplicate_m: float
    duplicate_share: float
    pair_opposed_deg: float
    extend_step_m: float
    extend_max_m: float
    extend_cone_deg: float
    merge_junctions_m: float
    connect_ahead_deg: float
    connect_alongside_m: float
    connect_alongside_share: float
    connect_outside_max_m: float
    connect_line_max_m: float
    jog_deg: float
    jog_m: float
    simplify_m: tuple[float, ...]

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> Params:
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in cfg.items() if k in names}
        kw["simplify_m"] = tuple(float(x) for x in kw["simplify_m"])
        return cls(**kw)


# ── helpers ───────────────────────────────────────────────────────────────────


def end_points(lines: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray]:
    """All line ends (2n points: starts, then ends) and the row each belongs to."""
    g = lines.geometry.values
    pts = np.concatenate([shapely.get_point(g, 0), shapely.get_point(g, -1)])
    return pts, np.concatenate([np.arange(len(g))] * 2)


def dead_end_mask(lines: gpd.GeoDataFrame, connected_m: float) -> np.ndarray:
    """(2n,) bool over end_points: True where no other line is within `connected_m`."""
    pts, owner = end_points(lines)
    pi, li = shapely.STRtree(lines.geometry.values).query(
        pts, predicate="dwithin", distance=connected_m
    )
    connected = np.zeros(len(pts), bool)
    connected[pi[li != owner[pi]]] = True
    return ~connected


def consolidate(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Split where ends land on lines, merge end-to-end chains (ADR-0009). `source`
    becomes the merged labels, so the result says what each segment contains."""
    noded = neatnet.induce_nodes(lines.reset_index(drop=True))
    merged = merge_chains(noded).drop(columns=["n_parts"]).reset_index(drop=True)
    merged["source"] = merged["sources"]
    return merged


def direction_out(line: shapely.LineString, end: int, back_m: float) -> np.ndarray:
    """Unit vector pointing out of `line` at `end` (0 start, 1 end), taken from a point
    `back_m` along the line so a tiny last vertex step doesn't decide it."""
    L = line.length
    if end == 1:
        tip = np.array(line.coords[-1])
        ref = np.array(line.interpolate(max(L - back_m, 0)).coords[0])
    else:
        tip = np.array(line.coords[0])
        ref = np.array(line.interpolate(min(back_m, L)).coords[0])
    v = tip - ref
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def junctions(lines: gpd.GeoDataFrame) -> tuple[np.ndarray, list[set[int]]]:
    """Points where >= 3 line ends meet (1 cm), and the rows touching each. Exact
    coordinates of one member end, so connectors land on the junction itself."""
    pts, owner = end_points(lines)
    key = np.round(shapely.get_coordinates(pts), 2)
    df = pd.DataFrame({"x": key[:, 0], "y": key[:, 1], "row": owner, "i": np.arange(len(pts))})
    grp = df.groupby(["x", "y"]).agg(rows=("row", list), first=("i", "first"))
    grp = grp[grp["rows"].map(len) >= 3]
    return pts[grp["first"].values], [set(r) for r in grp["rows"]]


def prepare_polygons(polys: gpd.GeoDataFrame, touch_m: float) -> gpd.GeoDataFrame:
    """Add `n_neighbours` (other polygons within `touch_m`) and `nbrs` (their row
    positions) to the arterial polygons."""
    polys = polys.reset_index(drop=True).copy()
    a, b = polys.sindex.query(polys.geometry.values, predicate="dwithin", distance=touch_m)
    keep = a != b
    polys["n_neighbours"] = np.bincount(a[keep], minlength=len(polys))
    nbrs: list[set[int]] = [set() for _ in range(len(polys))]
    for i, j in zip(a[keep], b[keep], strict=True):
        nbrs[i].add(int(j))
    polys["nbrs"] = nbrs
    return polys


def prepare_axes(axes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Step 0. Single-part lines, without zero-length or duplicate geometry."""
    g = axes.explode(ignore_index=True)
    g = g[g.length > 0.01]
    g = g[~g.geometry.normalize().duplicated()].reset_index(drop=True)
    return g.assign(source="original")


# ── steps ─────────────────────────────────────────────────────────────────────


def snap_dead_ends(lines: gpd.GeoDataFrame, tol: float, connected_m: float):
    """Step 1. Move each dead end onto another line's end within `tol`, else onto the
    nearest point of a line within `tol`; one end at a time on the updated geometry.
    Returns (lines, snaps as old -> new LineStrings with `snap_m` and `to`)."""
    lines = lines.reset_index(drop=True).copy()
    geoms = list(lines.geometry.values)
    tree = shapely.STRtree(lines.geometry.values)  # ends move <= tol: query 2 * tol
    snaps = []
    for i in range(len(geoms)):
        for end in (0, -1):
            coords = shapely.get_coordinates(geoms[i])
            p = shapely.Point(coords[end])
            near = [j for j in tree.query(p, predicate="dwithin", distance=2 * tol) if j != i]
            if not near:
                continue
            dist = np.array([p.distance(geoms[j]) for j in near])
            if dist.min() <= connected_m or dist.min() > tol:
                continue
            ends = [
                shapely.Point(c)
                for j, d in zip(near, dist, strict=True)
                if d <= tol
                for c in shapely.get_coordinates(geoms[j])[[0, -1]]
            ]
            end_d = np.array([p.distance(e) for e in ends])
            if end_d.size and end_d.min() <= tol:
                target, kind = ends[int(end_d.argmin())], "end"
            else:
                target = shapely.ops.nearest_points(p, geoms[near[int(dist.argmin())]])[1]
                kind = "line"
            new = coords.copy()
            new[end] = shapely.get_coordinates(target)[0]
            if shapely.LineString(new).length < 0.01:
                continue
            geoms[i] = shapely.LineString(new)
            snaps.append(
                {
                    "snap_m": round(p.distance(target), 2),
                    "to": kind,
                    "geometry": shapely.LineString([p, target]),
                }
            )
    lines["geometry"] = geoms
    snaps = pd.DataFrame(snaps, columns=["snap_m", "to", "geometry"])
    return lines, gpd.GeoDataFrame(snaps, geometry="geometry", crs=lines.crs)


def node_all(lines: gpd.GeoDataFrame, connected_m: float, split_crossings: bool = True):
    """Steps 2 and 9. Split at T-junctions and at every crossing; each piece keeps its
    parent's attributes. With `split_crossings=False` (the SDP package's errors-only
    run), crossings are found but left as drawn, since some are bridges. Returns
    (pieces, crossing points)."""
    lines = neatnet.induce_nodes(lines.reset_index(drop=True)).reset_index(drop=True)
    g = lines.geometry.values
    tree = shapely.STRtree(g)
    a, b = tree.query(g, predicate="crosses")
    keep = a < b
    xs = shapely.get_parts(shapely.intersection(g[a[keep]], g[b[keep]]))
    crossings = gpd.GeoDataFrame(geometry=xs[shapely.get_type_id(xs) == 0], crs=lines.crs)
    if not split_crossings:
        return lines, crossings
    pieces = shapely.get_parts(shapely.node(shapely.union_all(g)))
    pieces = pieces[shapely.length(pieces) > 0.01]
    mid = shapely.line_interpolate_point(pieces, 0.5, normalized=True)
    pi, li = tree.query(mid, predicate="dwithin", distance=connected_m)
    d = shapely.distance(mid[pi], g[li])
    order = np.lexsort((d, pi))
    first = np.unique(pi[order], return_index=True)[1]
    parent = np.full(len(pieces), -1)
    parent[pi[order][first]] = li[order][first]
    out = lines.iloc[parent[parent >= 0]].copy()
    out["geometry"] = pieces[parent >= 0]
    return out.reset_index(drop=True), crossings


def alongside_share(lines: gpd.GeoDataFrame, rows: np.ndarray, dist_m: float) -> np.ndarray:
    """Share of each line in `rows` lying within `dist_m` of any other line."""
    g = lines.geometry.values
    out = np.zeros(len(rows))
    for k, r in enumerate(rows):
        near = [j for j in lines.sindex.query(g[r], predicate="dwithin", distance=dist_m) if j != r]
        if near:
            band = shapely.union_all(shapely.buffer(g[near], dist_m))
            out[k] = g[r].intersection(band).length / g[r].length
    return out


def drop_stubs(lines: gpd.GeoDataFrame, p: Params):
    """Step 3. Repeat {consolidate; drop dead-end segments shorter than `stub_m` (`stub`)
    or with more than `duplicate_share` of their length within `duplicate_m` of other
    lines (`duplicate`, one per pass)} until nothing is dropped. Returns (lines, removed
    with `why`)."""
    removed = []
    while True:
        lines = consolidate(lines).reset_index(drop=True)
        dead = dead_end_mask(lines, p.connected_m).reshape(2, -1).any(axis=0)
        stub = (lines.length.values < p.stub_m) & dead
        # One duplicate per pass: two dead-end lines running beside each other are each
        # the other's duplicate, and only one of them should go. The higher share goes
        # first (the shorter on a tie); the other is measured again on the next pass.
        dup = np.zeros(len(lines), bool)
        rows = np.flatnonzero(dead & ~stub)
        share = alongside_share(lines, rows, p.duplicate_m)
        cand = np.flatnonzero(share > p.duplicate_share)
        if len(cand):
            lengths = lines.length.values[rows[cand]]
            dup[rows[cand[np.lexsort((lengths, -share[cand]))[0]]]] = True
        drop = stub | dup
        if not drop.any():
            gone = (
                pd.concat(removed, ignore_index=True)
                if removed
                else pd.DataFrame({"why": pd.Series(dtype=str), "geometry": []})
            )
            return lines, gpd.GeoDataFrame(gone, geometry="geometry", crs=lines.crs)
        removed.append(
            pd.DataFrame(
                {
                    "why": np.where(stub[drop], "stub", "duplicate"),
                    "geometry": lines.geometry.values[drop],
                }
            )
        )
        lines = lines[~drop]


def classify(lines: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, p: Params) -> gpd.GeoDataFrame:
    """Step 4. Dead ends as points with `row` (line position), `end` (0 start, 1 end),
    `n_neighbours` (highest among polygons within `dead_end_near_m`), `status`
    (critical >= 2, corridor_end <= 1, no_polygon), `polys` (their polygon positions)
    and `area` (those polygons plus their neighbours, padded: the search area)."""
    pts, owner = end_points(lines)
    idx = np.flatnonzero(dead_end_mask(lines, p.connected_m))
    dead = gpd.GeoDataFrame(
        {"row": owner[idx], "end": (idx >= len(lines)).astype(int)},
        geometry=pts[idx],
        crs=lines.crs,
    )
    di, pj = polys.sindex.query(
        dead.geometry.values, predicate="dwithin", distance=p.dead_end_near_m
    )
    best = pd.Series(polys["n_neighbours"].values[pj]).groupby(di).max().reindex(range(len(dead)))
    dead["n_neighbours"] = best.values
    dead["status"] = np.select(
        [best.isna().values, best.values <= 1], ["no_polygon", "corridor_end"], "critical"
    )
    groups = pd.Series(pj).groupby(di).agg(list).reindex(range(len(dead)))
    dead["polys"] = [set(g) if isinstance(g, list) else set() for g in groups]
    nbrs = polys["nbrs"].values
    dead["area"] = [
        shapely.union_all(
            polys.geometry.values[sorted(set(g).union(*(nbrs[i] for i in g)))]
        ).buffer(p.area_pad_m)
        if isinstance(g, list)
        else None
        for g in groups
    ]
    return dead


def pair_dead_ends(lines: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, p: Params):
    """Step 5. Join two dead ends at their midpoint when each is the other's nearest dead
    end, their polygons are the same or touching, they point at least
    `pair_opposed_deg` apart, and neither points away from the other.
    Returns (lines, gap lines with `gap_m`)."""
    lines = lines.reset_index(drop=True).copy()
    dead = classify(lines, polys, p)
    dead = dead[dead["polys"].map(len) > 0].reset_index(drop=True)
    empty = gpd.GeoDataFrame(
        pd.DataFrame(columns=["gap_m", "geometry"]), geometry="geometry", crs=lines.crs
    )
    if len(dead) < 2:
        return lines, empty
    xy = shapely.get_coordinates(dead.geometry.values)
    dist = np.linalg.norm(xy[:, None] - xy[None], axis=2)
    rows = dead["row"].values
    dist[rows[:, None] == rows[None]] = np.inf  # not the other end of the same line
    nearest = dist.argmin(axis=1)
    geoms = list(lines.geometry.values)
    dirs = [
        direction_out(geoms[r], e, p.direction_back_m)
        for r, e in zip(dead["row"], dead["end"], strict=True)
    ]
    cos_opposed = np.cos(np.radians(p.pair_opposed_deg))
    nbrs = polys["nbrs"].values
    pairs = []
    for i, j in enumerate(nearest):
        if i >= j or nearest[j] != i or not np.isfinite(dist[i, j]):
            continue
        pi_, pj_ = dead.at[i, "polys"], dead.at[j, "polys"]
        touching = bool(pi_ & pj_) or any(nbrs[a] & pj_ for a in pi_)
        ab = (xy[j] - xy[i]) / dist[i, j]
        # Opposed, and each has the other ahead of it or beside it (ends that overlap
        # side by side still pair; two ends both pointing into a junction don't).
        facing = dirs[i] @ dirs[j] <= cos_opposed and dirs[i] @ ab >= 0 and dirs[j] @ -ab >= 0
        if not (touching and facing):
            continue
        mid = (xy[i] + xy[j]) / 2
        for k in (i, j):
            r, e = dead.at[k, "row"], dead.at[k, "end"]
            c = shapely.get_coordinates(geoms[r])
            c[-1 if e == 1 else 0] = mid
            geoms[r] = shapely.LineString(c)
            lines.loc[r, "source"] = "pair"
        pairs.append(
            {"gap_m": round(dist[i, j], 2), "geometry": shapely.LineString([xy[i], xy[j]])}
        )
    lines["geometry"] = geoms
    if not pairs:
        return lines, empty
    return lines, gpd.GeoDataFrame(pairs, geometry="geometry", crs=lines.crs)


def extend_step(lines: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, tol: float, p: Params):
    """Step 6, one tolerance. Extend each critical dead end onto the nearest line within
    `tol` in a cone of +-`extend_cone_deg` ahead; keep the extension only if it lies
    inside the end's search area. Returns (lines, extensions with `ext_tol_m`, `added_m`)."""
    lines = lines.reset_index(drop=True).copy()
    dead = classify(lines, polys, p)
    dead = dead[dead["status"] == "critical"]
    g = lines.geometry.values
    tree = shapely.STRtree(g)
    geoms = list(g)
    added = []
    for _, d in dead.iterrows():
        line = geoms[d["row"]]
        tip = np.array(d.geometry.coords[0])
        v = direction_out(line, d["end"], p.direction_back_m)
        angles = np.arctan2(v[1], v[0]) + np.radians(
            np.linspace(-p.extend_cone_deg, p.extend_cone_deg, 13)
        )
        cone = shapely.Polygon(
            [tip] + [tip + tol * np.array([np.cos(a), np.sin(a)]) for a in angles]
        )
        best = None
        for j in tree.query(cone, predicate="intersects"):
            if j == d["row"]:
                continue
            q = np.array(
                shapely.ops.nearest_points(d.geometry, g[j].intersection(cone))[1].coords[0]
            )
            dist = np.linalg.norm(q - tip)
            if dist > p.connected_m and (best is None or dist < best[0]):
                best = (dist, q)
        if best is None:
            continue
        piece = shapely.LineString([tip, best[1]])
        if not d["area"].covers(piece):
            continue
        c = shapely.get_coordinates(line)
        c = np.vstack([c, best[1]]) if d["end"] == 1 else np.vstack([best[1], c])
        geoms[d["row"]] = shapely.LineString(c)
        lines.loc[d["row"], "source"] = "extension"
        added.append({"ext_tol_m": float(tol), "added_m": round(best[0], 2), "geometry": piece})
    lines["geometry"] = geoms
    added = pd.DataFrame(added, columns=["ext_tol_m", "added_m", "geometry"]).astype(
        {"ext_tol_m": float, "added_m": float}
    )
    return lines, gpd.GeoDataFrame(added, geometry="geometry", crs=lines.crs)


def merge_junctions(lines: gpd.GeoDataFrame, tol: float):
    """Step 7. Junctions closer than `tol` become one at their weighted centre
    (neatnet.consolidate_nodes); dead ends stay. Returns (lines, old positions moved)."""
    before, _ = junctions(lines)
    merged = neatnet.consolidate_nodes(lines, tolerance=tol, preserve_ends=True)
    merged = merged.drop(columns="_status", errors="ignore").reset_index(drop=True)
    after, _ = junctions(merged)
    still = np.zeros(len(before), bool)
    if len(after):
        still[shapely.STRtree(after).query(before, predicate="dwithin", distance=0.01)[0]] = True
    return merged, gpd.GeoDataFrame(geometry=before[~still], crs=lines.crs)


def connect(lines: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, p: Params):
    """Step 8. Connect each critical dead end still open to the nearest junction in its
    search area (not on its own segment), else to the nearest point of a line passing
    through the area (at most `connect_line_max_m`). A connector must point ahead
    (within `connect_ahead_deg`), leave the area by at most `connect_outside_max_m`, and
    not run within `connect_alongside_m` of another line for more than
    `connect_alongside_share` of its length; otherwise the end goes to review.
    Returns (lines with connectors added, connectors, review points)."""
    lines = lines.reset_index(drop=True)
    dead = classify(lines, polys, p)
    crit = dead[dead["status"] == "critical"]
    dead_rows = set(dead["row"])
    jpts, jrows = junctions(lines)
    g = lines.geometry.values
    new, review = [], []

    def fits(c: shapely.LineString, area) -> bool:
        return c.length - c.intersection(area).length <= p.connect_outside_max_m

    for _, d in crit.iterrows():
        area, pt, own = d["area"], d.geometry, d["row"]
        v = direction_out(g[own], d["end"], p.direction_back_m)

        def angle(c: shapely.LineString, v: np.ndarray = v) -> float:
            w = np.array(c.coords[-1]) - np.array(c.coords[0])
            return float(np.degrees(np.arccos(np.clip(v @ w / np.linalg.norm(w), -1, 1))))

        conn, kind = None, None
        cand = [k for k in range(len(jpts)) if own not in jrows[k] and area.covers(jpts[k])]
        for k in sorted(cand, key=lambda k: pt.distance(jpts[k])):
            c = shapely.LineString([pt, jpts[k]])
            if fits(c, area) and angle(c) <= p.connect_ahead_deg:
                conn, kind = c, "junction"
                break
        if conn is None:
            opts = []
            for j in lines.sindex.query(area, predicate="intersects"):
                if j == own or j in dead_rows:
                    continue
                q = shapely.ops.nearest_points(pt, g[j].intersection(area))[1]
                c = shapely.LineString([pt, q])
                if (
                    p.connected_m < c.length <= p.connect_line_max_m
                    and fits(c, area)
                    and angle(c) <= p.connect_ahead_deg
                ):
                    opts.append(c)
            if opts:
                conn, kind = min(opts, key=lambda c: c.length), "line"
        if conn is not None:
            near = [
                j
                for j in lines.sindex.query(
                    conn, predicate="dwithin", distance=p.connect_alongside_m
                )
                if j != own
            ]
            if near:
                band = shapely.union_all(shapely.buffer(g[near], p.connect_alongside_m))
                if conn.intersection(band).length / conn.length > p.connect_alongside_share:
                    conn = None
        if conn is None:
            review.append({"n_neighbours": d["n_neighbours"], "geometry": pt})
        else:
            new.append(
                {
                    "kind": kind,
                    "length_m": round(conn.length, 1),
                    "angle_deg": round(angle(conn)),
                    "geometry": conn,
                }
            )
    connectors = gpd.GeoDataFrame(
        pd.DataFrame(new, columns=["kind", "length_m", "angle_deg", "geometry"]),
        geometry="geometry",
        crs=lines.crs,
    )
    add = connectors[["geometry"]].assign(source="connector")
    lines = pd.concat([lines, add], ignore_index=True).pipe(gpd.GeoDataFrame, crs=lines.crs)
    review = gpd.GeoDataFrame(
        pd.DataFrame(review, columns=["n_neighbours", "geometry"]),
        geometry="geometry",
        crs=lines.crs,
    )
    return lines, connectors, review


def _dejog(line: shapely.LineString, ok, jog_deg: float, jog_m: float):
    """Remove both vertices of each pair of turns sharper than `jog_deg` within `jog_m`,
    while `ok(candidate)` holds. Returns (line, jogs removed)."""
    k = 0
    while True:
        c = shapely.get_coordinates(line)
        seg = np.diff(c, axis=0)
        n = np.linalg.norm(seg, axis=1)
        if len(c) < 4 or (n == 0).any():
            return line, k
        u = seg / n[:, None]
        turn = np.degrees(np.arccos(np.clip((u[:-1] * u[1:]).sum(axis=1), -1, 1)))
        changed = False
        for a, b in itertools.pairwise(np.flatnonzero(turn > jog_deg)):
            if b == a + 1 and np.linalg.norm(c[b + 1] - c[a + 1]) <= jog_m:
                cand = shapely.LineString(np.delete(c, [a + 1, b + 1], axis=0))
                if ok(cand):
                    line, k, changed = cand, k + 1, True
                    break
        if not changed:
            return line, k


def simplify_lines(lines: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, p: Params):
    """Step 10. Straighten jogs, Douglas-Peucker with the largest of `simplify_m` that
    works, jogs again. A change is kept only if no more of the line lies outside the
    polygons than before, and undone if it makes two lines cross. Line ends never move.
    Returns (lines, jogs straightened)."""
    area = shapely.union_all(polys.geometry.values).buffer(p.area_pad_m)
    shapely.prepare(area)
    g = lines.geometry.values
    out0 = shapely.length(shapely.difference(g, area))

    def ok_for(i: int):
        return lambda line: shapely.length(shapely.difference(line, area)) <= out0[i] + 0.01

    new, n_jogs = list(g), 0
    for i in range(len(new)):
        new[i], k = _dejog(new[i], ok_for(i), p.jog_deg, p.jog_m)
        n_jogs += k
    done = np.zeros(len(new), bool)
    for tol in sorted(p.simplify_m, reverse=True):
        for i in np.flatnonzero(~done):
            s = shapely.simplify(new[i], tol, preserve_topology=True)
            if shapely.get_num_coordinates(s) < shapely.get_num_coordinates(new[i]) and ok_for(i)(
                s
            ):
                new[i], done[i] = s, True
    for i in range(len(new)):
        new[i], k = _dejog(new[i], ok_for(i), p.jog_deg, p.jog_m)
        n_jogs += k
    arr = np.array(new, dtype=object)
    while True:
        a, b = shapely.STRtree(arr).query(arr, predicate="crosses")
        bad = np.unique(np.concatenate([a[a < b], b[a < b]]))
        bad = bad[arr[bad] != g[bad]]
        if not len(bad):
            break
        arr[bad] = g[bad]
    return lines.assign(geometry=arr), n_jogs


# ── step 11: interchange centres ──────────────────────────────────────────────


@dataclass(frozen=True)
class RelocationParams:
    """The `foreground.relocation:` block of config/analysis.yaml (ADR-0012, step 11)."""

    decisions: str  # CSV of per-interchange decisions, relative to the project root
    name_pattern: str  # polygons whose NOMBRE contains this (case-insensitive)
    approach_m: float  # an approach's direction is taken over this length
    min_move_m: float  # fallback, one junction: move at least this far ...
    max_rms_rel: float  # ... and the approaches meet within this x sqrt(area)
    max_move_rel: float  # fallback, 2+ junctions: collapse if the farthest is this close
    match_point_m: float  # a decision matches a polygon whose point is this close ...
    match_area_share: float  # ... and whose area differs by at most this share

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> RelocationParams:
        return cls(**{f.name: cfg[f.name] for f in fields(cls)})


def approaches(lines: gpd.GeoDataFrame, poly, jpts: np.ndarray, approach_m: float):
    """For an interchange polygon and the junctions inside it: the lines with an end at
    one of them (row positions), their parts outside the polygon with which ends lie on
    the edge, and each approach as (entry point, unit direction into the polygon) taken
    over the last `approach_m` before the edge. Lines merely crossing a corner of the
    polygon are not included."""
    edge = poly.boundary
    jset = {tuple(np.round(xy, 2)) for xy in shapely.get_coordinates(jpts)}
    g = lines.geometry.values
    hit = [
        i
        for i in lines.sindex.query(poly, predicate="intersects")
        if {tuple(np.round(g[i].coords[k], 2)) for k in (0, -1)} & jset
    ]
    parts, apps = [], []
    for i in hit:
        for part in shapely.get_parts(shapely.difference(g[i], poly)):
            if part.length < 0.05:
                continue
            ends = []
            for end in (0, 1):
                tip = np.array(part.coords[-1 if end else 0])
                if edge.distance(shapely.Point(tip)) > 0.05:
                    continue
                L = part.length
                ref = part.interpolate(max(L - approach_m, 0) if end else min(approach_m, L))
                v = tip - np.array(ref.coords[0])
                if np.linalg.norm(v) > 0:
                    ends.append(end)
                    apps.append((tip, v / np.linalg.norm(v)))
            parts.append((i, part, ends))
    return hit, parts, apps


def meeting_point(apps, poly) -> tuple[np.ndarray, float]:
    """The point closest (least squares) to all approach lines extended straight, and
    rms: the root mean square of their perpendicular distances to it (small = the
    approaches really meet there). point_on_surface if the point falls outside."""
    E = np.array([e for e, _ in apps])
    D = np.array([d for _, d in apps])
    P = np.eye(2)[None] - D[:, :, None] * D[:, None, :]
    x = np.linalg.lstsq(P.sum(axis=0), (P @ E[:, :, None]).sum(axis=0)[:, 0], rcond=None)[0]
    if not poly.buffer(1).covers(shapely.Point(x)):
        x = np.array(poly.point_on_surface().coords[0])
    v = x - E
    perp = v - (v * D).sum(axis=1)[:, None] * D
    return x, float(np.sqrt((perp**2).sum(axis=1).mean()))


def rebuild(lines: gpd.GeoDataFrame, hit, parts, x: np.ndarray) -> gpd.GeoDataFrame:
    """Drop the inside parts of the `hit` lines and run each approach straight from the
    polygon edge to `x`."""
    rows = []
    for i, part, ends in parts:
        c = shapely.get_coordinates(part)
        for end in ends:
            c = np.vstack([c, x]) if end == 1 else np.vstack([x, c])
        r = lines.iloc[i].copy()
        r["geometry"] = shapely.LineString(c)
        r["source"] = "relocated"
        rows.append(r)
    keep = lines.drop(index=lines.index[hit])
    new = gpd.GeoDataFrame(rows, geometry="geometry", crs=lines.crs)
    return pd.concat([keep, new], ignore_index=True).pipe(gpd.GeoDataFrame, crs=lines.crs)


def match_decisions(enlace: gpd.GeoDataFrame, decisions: pd.DataFrame, r: RelocationParams):
    """Match decisions to interchange polygons by CODIGO_ID, representative point and
    area. Returns (decision per polygon, empty where none matches; the decision rows
    that match no polygon: stale, e.g. a polygon SDP has redrawn)."""
    rep = enlace.geometry.representative_point()
    by_id = {k: g for k, g in decisions.groupby(decisions["codigo_id"].astype(str))}
    out, used = [], set()
    for cid, x, y, area in zip(
        enlace["CODIGO_ID"].astype(str), rep.x, rep.y, enlace.area, strict=True
    ):
        g = by_id.get(cid)
        if g is None:
            out.append("")
            continue
        near = np.hypot(g["rep_x"] - x, g["rep_y"] - y) <= r.match_point_m
        same = (g["area_m2"] - area).abs() <= r.match_area_share * area
        hit = g[near & same]
        out.append(hit["decision"].iloc[0] if len(hit) else "")
        used.update(hit.index)
    return out, decisions.drop(index=list(used))


def fallback_relocate(row: dict, r: RelocationParams) -> bool:
    """Rule for interchanges without a decision, fitted to the 2026-11-25 labels."""
    if row["approaches"] < 2:
        return False
    if row["junctions"] == 1:
        return row["move_m"] >= r.min_move_m and row["rms_rel"] <= r.max_rms_rel
    return row["junctions"] >= 2 and row["move_rel"] <= r.max_move_rel


def relocate_centres(
    lines: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    decisions: pd.DataFrame,
    r: RelocationParams,
):
    """Step 11. For each interchange polygon, in order: measure it, then relocate its
    centre if its decision says `relocate`, or, without a decision, if the fallback rule
    says so. Returns (lines, interchanges with their measures, `decision`, `action` and
    `needs_review`, new centre points, stale decision rows)."""
    enlace = polygons[polygons["NOMBRE"].fillna("").str.contains(r.name_pattern, case=False)].copy()
    enlace["decision"], stale = match_decisions(enlace, decisions, r)
    rows, centres = [], []
    for pid, poly, dec in zip(enlace.index, enlace.geometry, enlace["decision"], strict=True):
        poly = max(shapely.get_parts(poly), key=lambda q: q.area)
        lines = lines.reset_index(drop=True)
        jpts, _ = junctions(lines)
        inside = jpts[shapely.intersects(jpts, poly)] if len(jpts) else jpts
        hit, parts, apps = (
            approaches(lines, poly, inside, r.approach_m) if len(inside) else ([], [], [])
        )
        row = {"polygon": pid, "junctions": len(inside), "approaches": len(apps)}
        x = None
        if len(apps) >= 2:
            x, rms = meeting_point(apps, poly)
            move = float(np.linalg.norm(shapely.get_coordinates(inside) - x, axis=1).max())
            side = np.sqrt(poly.area)
            row |= {"move_m": move, "rms_new": rms, "rms_rel": rms / side, "move_rel": move / side}
        if dec in ("relocate", "keep", "review"):
            act = dec == "relocate" and x is not None
            row["action"] = "relocate" if act else "keep"
        else:
            act = x is not None and fallback_relocate(row, r)
            row["action"] = ("relocate" if act else "keep") + " (rule)"
        row["needs_review"] = dec in ("review", "") and len(inside) > 0
        if act:
            lines = rebuild(lines, hit, parts, x)
            centres.append({"polygon": pid, "geometry": shapely.Point(x)})
        rows.append(row)
    stats = pd.DataFrame(rows).set_index("polygon")
    enlace = enlace[["CODIGO_ID", "NOMBRE", "decision", "geometry"]].join(stats)
    for c in ("move_m", "rms_new", "rms_rel", "move_rel"):
        enlace[c] = enlace[c].round(3)
    centres = gpd.GeoDataFrame(
        pd.DataFrame(centres, columns=["polygon", "geometry"]), geometry="geometry", crs=lines.crs
    )
    return lines, enlace, centres, stale


# ── step 12: manual edits ─────────────────────────────────────────────────────


def apply_edits(lines: gpd.GeoDataFrame, edits: gpd.GeoDataFrame, match_m: float):
    """Step 12. Apply reviewed manual edits (config/foreground_edits.geojson, made by
    scripts/make_foreground_edits.py): drop each line matching an `edit: remove` geometry
    (within `match_m`, Hausdorff), then add every `edit: add` row. Nothing is merged
    afterwards, so the result is the edited network itself. Returns (lines, stale
    removals that matched no line)."""
    lines = lines.reset_index(drop=True)
    g = lines.geometry.values
    tree = shapely.STRtree(g)
    drop, stale = set(), []
    for k, geom in zip(edits.index, edits.geometry, strict=True):
        if edits.at[k, "edit"] != "remove":
            continue
        cand = [
            i
            for i in tree.query(geom, predicate="dwithin", distance=match_m)
            if shapely.hausdorff_distance(g[i], geom) <= match_m
        ]
        (drop.update(cand) if cand else stale.append(k))
    add = edits[edits["edit"] == "add"].drop(columns="edit").assign(source="manual")
    out = pd.concat([lines.drop(index=sorted(drop)), add], ignore_index=True)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=lines.crs), edits.loc[stale]


# ── run ───────────────────────────────────────────────────────────────────────


def status_counts(dead: gpd.GeoDataFrame) -> dict[str, int]:
    c = dead["status"].value_counts()
    return {k: int(c.get(k, 0)) for k in CLASSES}


def components(lines: gpd.GeoDataFrame) -> int:
    G = nx.Graph()
    for ln in lines.geometry.values:
        G.add_edge(tuple(np.round(ln.coords[0], 2)), tuple(np.round(ln.coords[-1], 2)))
    return nx.number_connected_components(G)


def clean(
    axes: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    p: Params,
    r: RelocationParams | None = None,
    decisions: pd.DataFrame | None = None,
    edits: gpd.GeoDataFrame | None = None,
    edits_match_m: float = 0.01,
    errors_only: bool = False,
) -> dict[str, Any]:
    """Run steps 0-12 on Eje Vial `axes` with the arterial `polygons` (both EPSG:9377).
    Step 11 runs only when `r` and `decisions` are given, step 12 only with `edits`.
    `errors_only` (the SDP package) keeps only the fixes to data errors: crossings are
    not split (steps 2 and 9), and junctions are not merged (7) nor lines simplified (10).
    Returns the final network under "network", one layer per correction, and counts."""
    polys = prepare_polygons(polygons, p.polygon_touch_m)
    net = prepare_axes(axes)
    s: dict[str, Any] = {"input_lines": len(net), "input": status_counts(classify(net, polys, p))}

    net, snaps = snap_dead_ends(net, p.snap_m, p.connected_m)
    s["snapped"] = len(snaps)
    net, crossings = node_all(net, p.connected_m, split_crossings=not errors_only)
    s["crossings_split"] = 0 if errors_only else len(crossings)
    net, removed = drop_stubs(net, p)
    s["stubs"] = int((removed["why"] == "stub").sum())
    s["duplicates"] = int((removed["why"] == "duplicate").sum())
    classified = classify(net, polys, p)
    s["classified"] = status_counts(classified)

    net, pairs = pair_dead_ends(net, polys, p)
    net = consolidate(net)
    s["pairs"] = len(pairs)

    ext_layers, steps = [], []
    for tol in np.arange(p.extend_step_m, p.extend_max_m + p.extend_step_m / 2, p.extend_step_m):
        net, ext = extend_step(net, polys, float(tol), p)
        net = consolidate(net)
        ext_layers.append(ext)
        left = status_counts(classify(net, polys, p))["critical"]
        steps.append({"tol_m": float(tol), "extended": len(ext), "critical_left": left})
    extensions = pd.concat(ext_layers, ignore_index=True).pipe(gpd.GeoDataFrame, crs=net.crs)
    s["extensions"] = len(extensions)
    s["extension_steps"] = steps

    if errors_only:
        moved = gpd.GeoDataFrame(geometry=[], crs=net.crs)
    else:
        net, moved = merge_junctions(net, p.merge_junctions_m)
        net = consolidate(net)
    s["junctions_moved"] = len(moved)

    net, connectors, review = connect(net, polys, p)
    s["connectors"] = connectors["kind"].value_counts().to_dict()
    s["review"] = len(review)

    # Step 3 again: an extension or connector that lands just short of a line's own
    # dead end leaves that end as a stub.
    net, removed_after = drop_stubs(net, p)
    s["stubs_after"] = len(removed_after)
    removed = pd.concat([removed, removed_after], ignore_index=True).pipe(
        gpd.GeoDataFrame, geometry="geometry", crs=net.crs
    )

    net, _ = node_all(net, p.connected_m, split_crossings=not errors_only)
    net = consolidate(net)
    v0 = int(shapely.get_num_coordinates(net.geometry.values).sum())
    if errors_only:
        s["jogs"] = 0
    else:
        net, s["jogs"] = simplify_lines(net, polys, p)
    s["vertices"] = (v0, int(shapely.get_num_coordinates(net.geometry.values).sum()))

    relocation = {}
    if r is not None and decisions is not None:
        net, enlace, centres, stale = relocate_centres(net, polygons, decisions, r)
        net, _ = node_all(net, p.connected_m)
        net = consolidate(net)
        relocation = {"interchanges": enlace, "centres": centres}
        s["relocation"] = enlace.groupby(["decision", "action"]).size().to_dict()
        s["relocated"] = len(centres)
        s["needs_review"] = int(enlace["needs_review"].sum())
        s["stale_decisions"] = len(stale)

    edit_layers = {}
    if edits is not None and len(edits):
        n0 = len(net)
        net, stale_edits = apply_edits(net, edits.to_crs(net.crs), edits_match_m)
        s["edits"] = {
            "removed": n0 - (len(net) - int((edits["edit"] == "add").sum())),
            "added": int((edits["edit"] == "add").sum()),
            "stale": len(stale_edits),
        }
        edit_layers = {"stale_edits": stale_edits}

    final_dead = classify(net, polys, p)
    g = net.geometry.values
    a, b = shapely.STRtree(g).query(g, predicate="crosses")
    net = net.drop(columns=["source", "_status"], errors="ignore")
    net["length_m"] = net.length.round(1)
    s |= {
        "segments": len(net),
        "km": float(net.length.sum() / 1000),
        "components": components(net),
        "unsplit_crossings": int((a < b).sum()),
        "final": status_counts(final_dead),
    }
    drop = ["area", "polys"]
    layers = (
        {
            "snaps": snaps,
            "crossings": crossings,
            "removed": removed,
            "dead_ends_classified": classified.drop(columns=drop),
            "pairs": pairs,
            "extensions": extensions,
            "junctions_merged": moved,
            "connectors": connectors,
            "review": review,
            "dead_ends_final": final_dead.drop(columns=drop),
        }
        | relocation
        | edit_layers
    )
    return {"network": net, "layers": layers, "summary": s}


def run(root: Path) -> dict[str, Any]:
    """Build the foreground network from data/interim (ADR-0012).

    Writes data/processed/foreground.parquet (GeoParquet), data/processed/foreground.gpkg
    (the same, one layer, for QGIS) and data/interim/foreground/review.gpkg (one layer
    per correction). Returns the counts.
    """
    from bogota_syntax.config import CRS, data_dir, load_analysis

    cfg = load_analysis(root)["foreground"]
    data = data_dir(root)
    axes = gpd.read_parquet(data / "interim" / f"{cfg['axes_source']}.parquet").to_crs(CRS)
    polygons = gpd.read_parquet(data / "interim" / f"{cfg['polygons_source']}.parquet").to_crs(CRS)
    rcfg = cfg.get("relocation")
    r = RelocationParams.from_config(rcfg) if rcfg else None
    decisions = pd.read_csv(root / r.decisions, dtype={"codigo_id": str}) if r else None
    edits_path = cfg.get("edits")
    edits = (
        gpd.read_file(root / edits_path) if edits_path and (root / edits_path).exists() else None
    )
    res = clean(
        axes, polygons, Params.from_config(cfg), r, decisions, edits, cfg.get("edits_match_m", 0.01)
    )

    processed = data / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    out = processed / "foreground.parquet"
    res["network"].to_parquet(out)
    gpkg = processed / "foreground.gpkg"
    gpkg.unlink(missing_ok=True)
    res["network"].to_file(gpkg, layer="foreground")
    review = data / "interim" / "foreground" / "review.gpkg"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.unlink(missing_ok=True)
    for name, layer in res["layers"].items():
        layer.to_file(review, layer=name)
    return res["summary"] | {"path": out, "gpkg": gpkg, "review_path": review}
