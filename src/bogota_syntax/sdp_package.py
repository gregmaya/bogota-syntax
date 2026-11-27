"""Spanish package for the SDP: the foreground's problems and fixes, keyed to the
published Eje Vial features (docs/briefs/sdp-eje-vial-package-design.md, ADR-0013).

Reads what `bogota-syntax foreground` wrote and never writes to it. Everything is
EPSG:9377 metres until the GeoPackage is written in the SDP's own PCS_CarMAGBOG.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import pyogrio
import shapely

KEYS = ["OBJECTID", "CODIGO_ID", "NOMBRE"]
LAYERS = ["problemas", "correcciones", "decisiones_modelado", "ediciones_manuales"]
TIPOS = [
    "extremo_suelto",
    "cruce_sin_nodo",
    "tramo_corto",
    "tramo_duplicado",
    "discontinuidad",
    "linea_aislada",
]
LICENCE = (
    "CC BY 4.0. Fuente: Secretaría Distrital de Planeación (SDP), Eje Vial y Red de "
    "Infraestructura Vial Arterial del POT (Decreto 555 de 2021). Correcciones: bogota-syntax."
)


# ── keys and CRS ──────────────────────────────────────────────────────────────


def _anchor(geoms: gpd.GeoSeries, at: str) -> np.ndarray:
    g = geoms.values
    if at == "point":
        return g
    if at == "start":
        return shapely.get_point(g, 0)
    if at == "mid":
        return shapely.line_interpolate_point(g, 0.5, normalized=True)
    raise ValueError(f"at must be point, start or mid, not {at!r}")


def attach_keys(
    gdf: gpd.GeoDataFrame,
    axes: gpd.GeoDataFrame,
    key_m: float,
    at: str = "point",
    *,
    second: bool = False,
) -> gpd.GeoDataFrame:
    """Add `OBJECTID`, `CODIGO_ID`, `NOMBRE` of the nearest `axes` feature within `key_m`
    metres of each row's anchor (the geometry, a line's first point, or its midpoint).
    Rows with nothing in range keep null keys. With `second`, also `OBJECTID_2`: the
    nearest other feature in range (for crossings). Both inputs EPSG:9377."""
    out = gdf.drop(columns=[*KEYS, "OBJECTID_2"], errors="ignore").reset_index(drop=True)
    pts = _anchor(out.geometry, at)
    ag = axes.geometry.values
    tree = shapely.STRtree(ag)
    first = np.full(len(out), -1)
    other = np.full(len(out), -1)
    for i, p in enumerate(pts):
        cand = tree.query(p, predicate="dwithin", distance=key_m)
        if len(cand) == 0:
            continue
        cand = cand[np.argsort(shapely.distance(ag[cand], p), kind="stable")]
        first[i] = cand[0]
        if second and len(cand) > 1:
            other[i] = cand[1]
    ok = first >= 0
    for k in KEYS:
        col = axes[k].reset_index(drop=True)
        vals = pd.Series(pd.NA, index=out.index, dtype="object")
        vals[ok] = col.iloc[first[ok]].to_numpy()
        out[k] = vals.astype("Int64") if k == "OBJECTID" else vals.astype("string")
    if second:
        vals = pd.Series(pd.NA, index=out.index, dtype="Int64")
        has = other >= 0
        vals[has] = axes["OBJECTID"].reset_index(drop=True).iloc[other[has]].to_numpy()
        out["OBJECTID_2"] = vals
    return out


def sdp_crs(root: Path) -> str:
    """WKT of the CRS the raw SDP Eje Vial file arrives in (PCS_CarMAGBOG)."""
    from bogota_syntax.config import data_dir

    raw = sorted((data_dir(root) / "raw" / "sdp_eje_vial").glob("*.gpkg"))
    if not raw:
        raise FileNotFoundError("No raw Eje Vial file: run `bogota-syntax ingest sdp_eje_vial`")
    return pyogrio.read_info(raw[0])["crs"]


def round_trip_error_m(axes_9377: gpd.GeoDataFrame, crs_wkt: str) -> float:
    """Largest coordinate shift, in metres, after EPSG:9377 -> `crs_wkt` -> EPSG:9377."""
    back = axes_9377.to_crs(crs_wkt).to_crs(axes_9377.crs)
    a = shapely.get_coordinates(axes_9377.geometry.values)
    b = shapely.get_coordinates(back.geometry.values)
    return float(np.max(np.hypot(*(a - b).T))) if len(a) else 0.0


# ── problemas and correcciones ────────────────────────────────────────────────

PROBLEM_COLS = ["tipo", "estado", "correccion", "distancia_m", "longitud_m", *KEYS, "OBJECTID_2"]
FIX_COLS = ["tipo", "longitud_m", *KEYS]
# review.gpkg layer -> correccion label, for the lines that fix a problem
FIX_LAYERS = {
    "snaps": "ajuste",
    "pairs": "union",
    "extensions": "extension",
    "connectors": "conector",
}


def _frame(rows: list[gpd.GeoDataFrame], cols: list[str], crs) -> gpd.GeoDataFrame:
    rows = [r for r in rows if len(r)]
    if not rows:
        return gpd.GeoDataFrame({c: [] for c in cols}, geometry=[], crs=crs)
    out = pd.concat(rows, ignore_index=True)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=crs)[[*cols, "geometry"]]


def _near(pts: np.ndarray, lines: gpd.GeoDataFrame, tol: float) -> np.ndarray:
    """Index into `lines` of a line with an end within `tol` of each point, else -1."""
    hit = np.full(len(pts), -1)
    if not len(lines) or not len(pts):
        return hit
    ends = np.concatenate(
        [shapely.get_point(lines.geometry.values, 0), shapely.get_point(lines.geometry.values, -1)]
    )
    owner = np.tile(np.arange(len(lines)), 2)
    pi, ei = shapely.STRtree(ends).query(pts, predicate="dwithin", distance=tol)
    hit[pi[::-1]] = owner[ei[::-1]]  # the first match wins
    return hit


def isolated_lines(network: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Lines outside the largest connected piece (nodes at 0.01 m, as
    `foreground.components`)."""
    G = nx.Graph()
    for i, ln in enumerate(network.geometry.values):
        a, b = (tuple(np.round(ln.coords[k], 2)) for k in (0, -1))
        G.add_edge(a, b, row=i)
    if G.number_of_nodes() == 0:
        return network.iloc[:0]
    main = max(nx.connected_components(G), key=len)
    rows = sorted(d["row"] for u, v, d in G.edges(data=True) if u not in main)
    return network.iloc[rows]


def build_problemas(
    layers: dict[str, gpd.GeoDataFrame],
    axes: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> gpd.GeoDataFrame:
    """One point per problem found in the published Eje Vial, open ones first.
    `layers` are the review.gpkg layers, `axes` the original Eje Vial, `network` the
    foreground output; all EPSG:9377, distances and lengths in metres."""
    crs, key_m, tol = axes.crs, cfg["key_m"], cfg["end_match_m"]

    def rows(gdf, tipo, at="point", *, second=False, **cols):
        if not len(gdf):
            return gdf.iloc[:0]
        cols = {k: (v.to_numpy() if isinstance(v, pd.Series) else v) for k, v in cols.items()}
        base = gpd.GeoDataFrame(
            {"tipo": tipo, "estado": "corregido", **cols},
            index=pd.RangeIndex(len(gdf)),
            geometry=_anchor(gdf.geometry, at),
            crs=crs,
        )
        return attach_keys(base, axes, key_m, second=second)

    s, c, r = layers["snaps"], layers["crossings"], layers["removed"]
    out = [
        rows(s, "extremo_suelto", "start", correccion="ajuste", distancia_m=s.get("snap_m")),
        rows(c, "cruce_sin_nodo", second=True, correccion="division"),
    ]
    for why, tipo in (("stub", "tramo_corto"), ("duplicate", "tramo_duplicado")):
        rr = r[r["why"] == why]
        out.append(rows(rr, tipo, "mid", correccion="eliminado", longitud_m=rr.length.round(1)))

    dead = layers["dead_ends_classified"]
    dead = dead[dead["status"] == "critical"]
    final = layers["dead_ends_final"]
    final = final[final["status"] == "critical"]
    pts = dead.geometry.values
    corr = np.full(len(dead), "reubicacion_o_edicion", dtype=object)
    dist = np.full(len(dead), np.nan)
    for name in ("connectors", "extensions", "pairs"):  # last assigned wins: pairs first
        fix = layers[name]
        hit = _near(pts, fix, tol)
        corr[hit >= 0] = FIX_LAYERS[name]
        dist[hit >= 0] = fix.length.to_numpy()[hit[hit >= 0]].round(1)
    open_ = np.zeros(len(dead), bool)
    if len(final) and len(dead):
        open_[shapely.STRtree(final.geometry.values).query(pts, "dwithin", tol)[0]] = True
    corr[open_], dist[open_] = "", np.nan
    estado = np.where(open_, "abierto", "corregido")
    out.append(rows(dead, "discontinuidad", correccion=corr, distancia_m=dist, estado=estado))

    iso = isolated_lines(network)
    out.append(
        rows(
            iso,
            "linea_aislada",
            "mid",
            correccion="",
            estado="abierto",
            longitud_m=iso.length.round(1),
        )
    )
    pr = _frame(out, PROBLEM_COLS, crs)
    pr["correccion"] = pr["correccion"].fillna("")
    pr = pr.assign(_o=(pr["estado"] != "abierto").astype(int)).sort_values("_o", kind="stable")
    return pr.drop(columns="_o").reset_index(drop=True)


def build_correcciones(
    layers: dict[str, gpd.GeoDataFrame], axes: gpd.GeoDataFrame, cfg: dict[str, Any]
) -> gpd.GeoDataFrame:
    """One line per line added or moved to fix a problem (snaps, pairs, extensions,
    connectors), keyed by the feature at its first point. EPSG:9377, metres."""
    out = []
    for name, tipo in FIX_LAYERS.items():
        g = layers[name]
        if not len(g):
            continue
        base = gpd.GeoDataFrame(
            {"tipo": tipo, "longitud_m": g.length.round(1).to_numpy()},
            geometry=g.geometry.values,
            crs=axes.crs,
        )
        out.append(attach_keys(base, axes, cfg["key_m"], at="start"))
    return _frame(out, FIX_COLS, axes.crs)
