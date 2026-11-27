"""Spanish package for the SDP: the foreground's problems and fixes, keyed to the
published Eje Vial features (docs/briefs/sdp-eje-vial-package-design.md, ADR-0013).

Reads what `bogota-syntax foreground` wrote and never writes to it. Everything is
EPSG:9377 metres until the GeoPackage is written in the SDP's own PCS_CarMAGBOG.
"""

from __future__ import annotations

import json
import warnings
from datetime import date
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

PROBLEM_COLS = [
    "tipo",
    "estado",
    "correccion",
    "distancia_m",
    "longitud_m",
    *KEYS,
    "OBJECTID_2",
]
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
    out = out.reindex(columns=[*cols, "geometry"])
    return gpd.GeoDataFrame(out, geometry="geometry", crs=crs)


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


def mark_limit(pr: gpd.GeoDataFrame, limit: gpd.GeoDataFrame, limit_m: float) -> gpd.GeoDataFrame:
    """Add `observacion`: rows within `limit_m` metres of the Bogotá limit (`limit`, its
    boundary as lines or the polygon) end there because the data stops at the city
    limit, not because a segment is missing."""
    edge = (
        shapely.union_all(shapely.boundary(limit.geometry.values))
        if (limit.geom_type.str.contains("Polygon").any())
        else shapely.union_all(limit.geometry.values)
    )
    at = shapely.distance(pr.geometry.values, edge) <= limit_m
    return pr.assign(observacion=np.where(at, "termina en el límite del Distrito", ""))


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


# ── decisiones_modelado and ediciones_manuales ────────────────────────────────

DECISION_COLS = ["tipo", "origen", "CODIGO_ID", "NOMBRE"]
EDIT_COLS = ["edicion", "longitud_m", *KEYS]
ORIGEN = {"relocate": "revision_manual", "relocate (rule)": "regla"}


def build_decisiones(layers: dict[str, gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    """One point per place changed for network analysis, not because the data is wrong:
    merged junctions (`fusion_nodos`) and relocated interchange centres
    (`reubicacion_enlace`, keyed to the interchange polygon holding the centre)."""
    j, c, inter = layers["junctions_merged"], layers["centres"], layers["interchanges"]
    crs = inter.crs or j.crs
    out = []
    if len(j):
        out.append(
            gpd.GeoDataFrame(
                {"tipo": "fusion_nodos", "origen": "regla"},
                index=pd.RangeIndex(len(j)),
                geometry=j.geometry.values,
                crs=crs,
            )
        )
    if len(c):
        poly = inter[inter["action"].isin(list(ORIGEN))][
            ["CODIGO_ID", "NOMBRE", "action", "geometry"]
        ]
        hit = gpd.sjoin(
            gpd.GeoDataFrame(geometry=c.geometry.values, crs=crs),
            poly,
            predicate="within",
            how="left",
        )
        hit = hit[~hit.index.duplicated()]
        out.append(
            gpd.GeoDataFrame(
                {
                    "tipo": "reubicacion_enlace",
                    "origen": hit["action"].map(ORIGEN).to_numpy(),
                    "CODIGO_ID": hit["CODIGO_ID"].to_numpy(),
                    "NOMBRE": hit["NOMBRE"].to_numpy(),
                },
                geometry=hit.geometry.values,
                crs=crs,
            )
        )
    return _frame(out, DECISION_COLS, crs)


def build_ediciones(edits: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    """The reviewed manual edits (config/foreground_edits.geojson) as lines: `edicion`
    `agregada` (drawn) or `retirada` (removed), with the keys the edits file carries."""
    if edits is None or not len(edits):
        return _frame([], EDIT_COLS, edits.crs if edits is not None else "EPSG:9377")
    e = edits.reset_index(drop=True)
    out = gpd.GeoDataFrame(
        {
            "edicion": e["edit"].map({"add": "agregada", "remove": "retirada"}).to_numpy(),
            "longitud_m": e.length.round(1).to_numpy(),
            "OBJECTID": pd.array(e["OBJECTID"].round(), dtype="Int64"),
            "CODIGO_ID": e["CODIGO_ID"].astype("string").to_numpy(),
            "NOMBRE": e["NOMBRE"].astype("string").to_numpy(),
        },
        geometry=e.geometry.values,
        crs=e.crs,
    )
    return out[[*EDIT_COLS, "geometry"]]


# ── counts, writing, run ──────────────────────────────────────────────────────


def counts(package: dict[str, gpd.GeoDataFrame]) -> dict[str, Any]:
    """Flat counts for the note and the command line."""
    pr, d, e = package["problemas"], package["decisiones_modelado"], package["ediciones_manuales"]
    n: dict[str, Any] = {}
    for t in TIPOS:
        rows = pr[pr["tipo"] == t]
        n[f"n_{t}"] = len(rows)
        n[f"n_{t}_abierto"] = int((rows["estado"] == "abierto").sum())
        n[f"n_{t}_corregido"] = n[f"n_{t}"] - n[f"n_{t}_abierto"]
    n["n_problemas"] = len(pr)
    n["n_abierto"] = int((pr["estado"] == "abierto").sum())
    n["n_sin_clave"] = int(pr["OBJECTID"].isna().sum())
    lim = pr.get("observacion", pd.Series("", index=pr.index)).fillna("") != ""
    open_gap = (pr["estado"] == "abierto") & (pr["tipo"] == "discontinuidad")
    n["n_abierto_limite"] = int((open_gap & lim).sum())
    n["n_abierto_faltante"] = int((open_gap & ~lim).sum())
    for c in ("union", "extension", "conector", "reubicacion_o_edicion"):
        n[f"n_discontinuidad_{c}"] = int(
            ((pr["tipo"] == "discontinuidad") & (pr["correccion"] == c)).sum()
        )
    for t, k in (("correcciones", "n_correcciones"),):
        n[k] = len(package[t])
    n["n_fusion_nodos"] = int((d["tipo"] == "fusion_nodos").sum())
    rel = d[d["tipo"] == "reubicacion_enlace"]
    n["n_reubicacion"] = len(rel)
    n["n_reubicacion_revision"] = int((rel["origen"] == "revision_manual").sum())
    n["n_reubicacion_regla"] = int((rel["origen"] == "regla").sum())
    n["n_edicion_agregada"] = int((e["edicion"] == "agregada").sum())
    n["n_edicion_retirada"] = int((e["edicion"] == "retirada").sum())
    km = e.loc[e["edicion"] == "agregada", "longitud_m"].sum() / 1000
    n["km_editados"] = f"{km:.1f}".replace(".", ",")
    return n


# Field types and geometry per layer, so an empty layer keeps its schema.
_TEXT, _NUM, _INT = "string", "Float64", "Int64"
SCHEMAS: dict[str, tuple[str, dict[str, str]]] = {
    "problemas": (
        "Point",
        {
            "tipo": _TEXT,
            "estado": _TEXT,
            "correccion": _TEXT,
            "distancia_m": _NUM,
            "longitud_m": _NUM,
            "OBJECTID": _INT,
            "CODIGO_ID": _TEXT,
            "NOMBRE": _TEXT,
            "OBJECTID_2": _INT,
            "observacion": _TEXT,
        },
    ),
    "correcciones": (
        "LineString",
        {"tipo": _TEXT, "longitud_m": _NUM, "OBJECTID": _INT, "CODIGO_ID": _TEXT, "NOMBRE": _TEXT},
    ),
    "decisiones_modelado": (
        "Point",
        {"tipo": _TEXT, "origen": _TEXT, "CODIGO_ID": _TEXT, "NOMBRE": _TEXT},
    ),
    "ediciones_manuales": (
        "LineString",
        {
            "edicion": _TEXT,
            "longitud_m": _NUM,
            "OBJECTID": _INT,
            "CODIGO_ID": _TEXT,
            "NOMBRE": _TEXT,
        },
    ),
}


def write_gpkg(package: dict[str, gpd.GeoDataFrame], path: Path, crs_wkt: str) -> Path:
    """Write the four layers, in order, in `crs_wkt` (PCS_CarMAGBOG), with the field
    types and geometry of `SCHEMAS` (also when a layer is empty) and the licence notice
    as each layer's description."""
    path.unlink(missing_ok=True)
    for name in LAYERS:
        geom, types = SCHEMAS[name]
        gdf = package[name]
        cols = [c for c in types if c in gdf.columns]
        out = gdf[[*cols, "geometry"]].astype({c: types[c] for c in cols})
        out.to_crs(crs_wkt).to_file(
            path,
            layer=name,
            driver="GPKG",
            geometry_type=geom,
            layer_metadata={"DESCRIPTION": LICENCE},
        )
    return path


def check_fresh(review: Path, inputs: list[Path]) -> None:
    """Stop if the foreground review layers are older than any input they come from."""
    if not review.exists():
        raise RuntimeError(f"{review} is missing: run `bogota-syntax foreground` first")
    stale = [p for p in inputs if p.exists() and p.stat().st_mtime > review.stat().st_mtime]
    if stale:
        names = ", ".join(p.name for p in stale)
        raise RuntimeError(
            f"{names} is newer than {review.name}: run `bogota-syntax foreground` first"
        )


def run(root: Path) -> dict[str, Any]:
    """Build the SDP package from the foreground outputs (ADR-0012) into
    data/processed/sdp_package/entrega_sdp_eje_vial_<date>/. Returns the counts, the
    unmatched rows, the round-trip error and the paths."""
    from bogota_syntax.config import CRS, data_dir, load_analysis

    analysis = load_analysis(root)
    cfg, fg = analysis["sdp_package"], analysis["foreground"]
    data = data_dir(root)
    review = data / "interim" / "foreground" / "review.gpkg"
    axes_path = data / "interim" / f"{fg['axes_source']}.parquet"
    polys_path = data / "interim" / f"{fg['polygons_source']}.parquet"
    edits_path = root / fg["edits"] if fg.get("edits") else None
    # Data inputs only: git resets config files' dates on checkout, and stale decisions
    # or edits are already reported by `foreground` itself.
    check_fresh(review, [axes_path, polys_path])

    layers = {n: gpd.read_file(review, layer=n) for n, _ in pyogrio.list_layers(review)}
    axes = gpd.read_parquet(axes_path).to_crs(CRS)
    network = gpd.read_parquet(data / "processed" / "foreground.parquet").to_crs(CRS)
    edits = gpd.read_file(edits_path).to_crs(CRS) if edits_path and edits_path.exists() else None

    package = {
        "problemas": build_problemas(layers, axes, network, cfg),
        "correcciones": build_correcciones(layers, axes, cfg),
        "decisiones_modelado": build_decisiones(layers),
        "ediciones_manuales": build_ediciones(edits),
    }
    limit = gpd.read_parquet(data / "interim" / f"{cfg['limit_source']}.parquet").to_crs(CRS)
    package["problemas"] = mark_limit(package["problemas"], limit, cfg["limit_m"])
    crs_wkt = sdp_crs(root)
    err = round_trip_error_m(axes, crs_wkt)
    if err > cfg["round_trip_max_m"]:
        raise RuntimeError(f"PCS_CarMAGBOG round trip moves points {err:.3f} m")

    manifest = json.loads((root / "config" / "manifest.json").read_text(encoding="utf-8"))
    out = data / "processed" / "sdp_package" / f"entrega_sdp_eje_vial_{date.today().isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    gpkg = write_gpkg(package, out / "eje_vial_revision.gpkg", crs_wkt)
    n = counts(package) | {
        "n_eje_vial": len(axes),
        "n_eje_sin_codigo": int(axes["CODIGO_ID"].isna().sum()),
    }
    from bogota_syntax.sdp_figures import make_figures

    polygons = gpd.read_parquet(polys_path).to_crs(CRS)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        figures = make_figures(package, layers, axes, network, polygons, cfg, out / "figuras")
    sources = {k: manifest.get(k, {}) for k in ("sdp_eje_vial", "sdp_red_infraestructura_vial")}
    values = note_values(n, figures, sources, cfg)
    (out / "nota_metodologica.md").write_text(
        render(TEMPLATES / "nota_metodologica.md", values), encoding="utf-8"
    )
    (out / "LEEME.txt").write_text(render(TEMPLATES / "LEEME.txt", values), encoding="utf-8")
    pr = package["problemas"]
    caught_msgs = [str(w.message) for w in caught]
    if not cfg.get("contacto"):
        caught_msgs.append("sdp_package.contacto is empty: LEEME.txt says '(por completar)'")
    return n | {
        "figures": figures,
        "warnings": caught_msgs,
        "package": package,
        "layers": layers,
        "axes": axes,
        "network": network,
        "polygons": polygons,
        "cfg": cfg,
        "manifest": {k: manifest.get(k, {}) for k in (fg["axes_source"], fg["polygons_source"])},
        "unmatched": pr[pr["OBJECTID"].isna()][["tipo", "estado", "geometry"]],
        "round_trip_m": err,
        "dir": out,
        "gpkg": gpkg,
    }


# ── note and LEEME ────────────────────────────────────────────────────────────

TEMPLATES = Path(__file__).parent / "templates"
TABLE_ROWS = [
    ("extremo_suelto", "Extremo suelto", "ajuste del extremo"),
    ("cruce_sin_nodo", "Cruce sin nodo", "división en el cruce"),
    ("tramo_corto", "Tramo corto", "eliminado"),
    ("tramo_duplicado", "Tramo duplicado", "eliminado"),
    ("discontinuidad", "Discontinuidad del corredor", "extensión, unión o conector"),
    ("linea_aislada", "Línea aislada", "—"),
]


def miles(v: int) -> str:
    """An integer with a dot between thousands, as written in Spanish (1.149)."""
    return f"{v:,}".replace(",", ".")


def render(template: Path, values: dict[str, Any]) -> str:
    """Fill `$name` placeholders; a missing value raises KeyError."""
    from string import Template

    return Template(template.read_text(encoding="utf-8")).substitute(values)


def _figure(fig: dict[str, Any] | None) -> str:
    if fig is None:
        return "_Sin casos._"
    return f"![]({Path('figuras') / Path(fig['path']).name})\n\n_{fig['caption']}_"


def note_values(
    n: dict[str, Any],
    figures: dict[str, dict[str, Any] | None],
    manifest: dict[str, dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Everything the note and LEEME templates need: counts, the results table, one
    Markdown block per figure, source dates and the contact."""

    def day(source: str, field: str) -> str:
        v = manifest.get(source, {}).get(field)
        return str(v)[:10] if v else "(sin dato)"

    n = {k: miles(v) if isinstance(v, int) else v for k, v in n.items()}
    rows = [
        "| Problema | Encontrados | Corregidos | Abiertos | Cómo se corrigió |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for t, label, how in TABLE_ROWS:
        rows.append(
            f"| {label} | {n[f'n_{t}']} | {n[f'n_{t}_corregido']} | {n[f'n_{t}_abierto']} | {how} |"
        )
    corregido = miles(int(n["n_problemas"].replace(".", "")) - int(n["n_abierto"].replace(".", "")))
    rows.append(
        f"| **Total** | **{n['n_problemas']}** | **{corregido}** | **{n['n_abierto']}** | |"
    )
    contacto = cfg.get("contacto") or "(por completar)"
    return (
        n
        | {f"fig{i}": _figure(figures.get(f"fig{i}")) for i in range(1, 8)}
        | {
            "tabla": "\n".join(rows),
            "n_corregido": corregido,
            "fecha": date.today().isoformat(),
            "fecha_eje": day("sdp_eje_vial", "ckan_metadata_modified"),
            "fecha_poligonos": day("sdp_red_infraestructura_vial", "ckan_metadata_modified"),
            "fecha_descarga_eje": day("sdp_eje_vial", "retrieved_at"),
            "fecha_descarga_poligonos": day("sdp_red_infraestructura_vial", "retrieved_at"),
            "contacto": contacto,
            "key_m": f"{cfg.get('key_m', '')}".replace(".", ","),
        }
    )
