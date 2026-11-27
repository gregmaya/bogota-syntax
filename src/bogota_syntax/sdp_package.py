"""Spanish package for the SDP: the foreground's problems and fixes, keyed to the
published Eje Vial features (docs/briefs/sdp-eje-vial-package-design.md, ADR-0013).

Reads what `bogota-syntax foreground` wrote and never writes to it. Everything is
EPSG:9377 metres until the GeoPackage is written in the SDP's own PCS_CarMAGBOG.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
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
