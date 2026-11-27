"""Figures for the SDP package's note (docs/briefs/sdp-eje-vial-package-design.md).

Drawn from the package's own layers in EPSG:9377 metres, with no basemap. One style:
original lines grey, corrections in one strong colour, open cases in a second, POT
arterial polygons as a light fill, a scale bar on every map.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely

GREY = "#8c8c8c"
FIX = "#e66100"  # corrections
OPEN = "#5d3a9b"  # open cases
POLY = "#efe6d2"
POLY_EDGE = "#d9c9a3"
# Okabe-Ito, colour-blind safe, one per problem type in the overview
TYPE_COLOURS = {
    "extremo_suelto": "#0072b2",
    "cruce_sin_nodo": "#009e73",
    "tramo_corto": "#cc79a7",
    "tramo_duplicado": "#cc79a7",
    "discontinuidad": "#e69f00",
    "linea_aislada": OPEN,
}
TYPE_LABELS = {
    "extremo_suelto": "Extremo suelto",
    "cruce_sin_nodo": "Cruce sin nodo",
    "tramo_corto": "Tramo corto o duplicado",
    "tramo_duplicado": "Tramo corto o duplicado",
    "discontinuidad": "Discontinuidad del corredor",
    "linea_aislada": "Línea aislada",
}
VERB = {"extension": "extiende", "conector": "conecta"}
WIDTH_IN = 16 / 2.54
DPI = 200


def _num(x: float) -> str:
    return f"{x:,.1f}".replace(",", " ").replace(".", ",")


def pick_example(rows: gpd.GeoDataFrame, wanted: int | str | None, key: str) -> pd.Series | None:
    """The row whose `key` equals `wanted`; if `wanted` is None or not found (with a
    warning), the row nearest the median `distancia_m` (the first row when there is
    none, then `longitud_m`; the first row when neither). None for an empty frame."""
    if not len(rows):
        return None
    if wanted is not None:
        hit = rows[rows[key].astype(str) == str(wanted)]
        if len(hit):
            return hit.iloc[0]
        warnings.warn(f"example {key}={wanted} not found; using an automatic one", stacklevel=2)
    d = pd.Series(np.nan, index=rows.index)
    for col in ("distancia_m", "longitud_m"):
        if col in rows and pd.to_numeric(rows[col], errors="coerce").notna().any():
            d = pd.to_numeric(rows[col], errors="coerce")
            break
    if d.notna().any():
        return rows.loc[(d - d.median()).abs().idxmin()]
    return rows.iloc[0]


def _window(ax, focus: shapely.Point, w: float) -> shapely.Polygon:
    ax.set_xlim(focus.x - w, focus.x + w)
    ax.set_ylim(focus.y - w, focus.y + w)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#cccccc")
    return shapely.box(focus.x - w, focus.y - w, focus.x + w, focus.y + w)


def _scalebar(ax, w: float, at: tuple[float, float] = (0.05, 0.05)) -> None:
    length = 10 ** np.floor(np.log10(w))
    length = length * 5 if length * 5 <= w else length
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x, y = x0 + at[0] * (x1 - x0), y0 + at[1] * (y1 - y0)
    ax.plot([x, x + length], [y, y], color="black", lw=2, solid_capstyle="butt")
    label = f"{length / 1000:g} km" if length >= 1000 else f"{length:g} m"
    ax.text(x + length / 2, y + 0.02 * (y1 - y0), label, ha="center", va="bottom", fontsize=7)


def _base(ax, lines: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame, box: shapely.Polygon) -> None:
    polygons[polygons.intersects(box)].plot(ax=ax, color=POLY, edgecolor=POLY_EDGE, lw=0.5)
    near = lines[lines.intersects(box)]
    near.plot(ax=ax, color=GREY, lw=1.6)
    ends = shapely.get_coordinates(
        np.concatenate(
            [
                shapely.get_point(near.geometry.values, 0),
                shapely.get_point(near.geometry.values, -1),
            ]
        )
    )
    ax.scatter(ends[:, 0], ends[:, 1], s=9, color="white", edgecolor=GREY, lw=0.8, zorder=3)
    ax.set_xlabel("")
    ax.set_ylabel("")


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    for ax in fig.axes:  # geopandas labels the axes on every plot call
        ax.set_xlabel("")
        ax.set_ylabel("")
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def overview(package: dict[str, gpd.GeoDataFrame], axes: gpd.GeoDataFrame, path: Path) -> Path:
    """Figure 1: the whole city, Eje Vial in grey, problems by type, open cases ringed."""
    pr = package["problemas"]
    fig, ax = plt.subplots(figsize=(WIDTH_IN, WIDTH_IN * 1.1))
    axes.plot(ax=ax, color="#c8c8c8", lw=0.5)
    done = set()
    for t, colour in TYPE_COLOURS.items():
        rows = pr[(pr["tipo"] == t) & (pr["estado"] == "corregido")]
        label = TYPE_LABELS[t]
        if len(rows):
            ax.scatter(
                rows.geometry.x,
                rows.geometry.y,
                s=7,
                color=colour,
                zorder=3,
                label=None if label in done else label,
            )
            done.add(label)
    op = pr[pr["estado"] == "abierto"]
    if len(op):
        ax.scatter(
            op.geometry.x,
            op.geometry.y,
            s=90,
            facecolor="none",
            edgecolor=OPEN,
            lw=1.8,
            zorder=4,
            label="Abierto (requiere revisión de la SDP)",
        )
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 0.75), fontsize=8, frameon=False)
    _scalebar(ax, (ax.get_xlim()[1] - ax.get_xlim()[0]) / 2, at=(0.6, 0.45))
    return _save(fig, path)


def before_after(
    focus: shapely.Point,
    axes: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    highlight: gpd.GeoDataFrame | None,
    path: Path,
    window_m: float,
    highlight_before: gpd.GeoDataFrame | None = None,
) -> Path:
    """Two panels around `focus`: left the published Eje Vial, right the corrected
    network with `highlight` in the correction colour. `highlight_before` marks what
    the correction removes, on the left."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(WIDTH_IN, WIDTH_IN / 2))
    for ax, lines, title in ((a, axes, "Publicado"), (b, network, "Corregido")):
        box = _window(ax, focus, window_m)
        _base(ax, lines, polygons, box)
        ax.set_title(title, fontsize=9)
    a.scatter([focus.x], [focus.y], s=160, facecolor="none", edgecolor=FIX, lw=1.5, zorder=4)
    if highlight_before is not None and len(highlight_before):
        highlight_before.plot(ax=a, color=FIX, lw=2.4, linestyle=(0, (2, 1)), zorder=4)
    if highlight is not None and len(highlight):
        if highlight.geom_type.iloc[0] == "Point":
            highlight.plot(ax=b, color=FIX, markersize=30, zorder=4)
        else:
            highlight.plot(ax=b, color=FIX, lw=2.4, zorder=4)
    for ax in (a, b):
        _scalebar(ax, window_m)
    return _save(fig, path)


def single(
    focus: shapely.Point,
    network: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    path: Path,
    window_m: float,
) -> Path:
    """One panel around `focus` on the corrected network, the open case ringed."""
    fig, ax = plt.subplots(figsize=(WIDTH_IN / 1.6, WIDTH_IN / 1.6))
    box = _window(ax, focus, window_m)
    _base(ax, network, polygons, box)
    ax.scatter([focus.x], [focus.y], s=200, facecolor="none", edgecolor=OPEN, lw=2, zorder=4)
    _scalebar(ax, window_m)
    return _save(fig, path)


def _who(row: pd.Series) -> str:
    name = row.get("NOMBRE")
    oid = row.get("OBJECTID")
    if name is None or pd.isna(name):
        return ""
    return f" ({name}, OBJECTID {oid})" if not pd.isna(oid) else f" ({name})"


def make_figures(
    package: dict[str, gpd.GeoDataFrame],
    layers: dict[str, gpd.GeoDataFrame],
    axes: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    cfg: dict[str, Any],
    out_dir: Path,
) -> dict[str, dict[str, Any] | None]:
    """Figures 1-7 as PNG in `out_dir`, without captions (the note carries them). Each
    is {"path", "caption"}, or None when the
    package has no case of that type. Examples come from `cfg["examples"]`."""
    pr, co, de = package["problemas"], package["correcciones"], package["decisiones_modelado"]
    ex = cfg.get("examples") or {}
    w = cfg["figure_window_m"]
    ws = cfg.get("figure_window_small_m", w)
    out: dict[str, dict[str, Any] | None] = {}

    p = overview(package, axes, out_dir / "figura_1_ciudad.png")
    out["fig1"] = {
        "path": p,
        "caption": "Figura 1. Problemas encontrados en el Eje Vial publicado. Los círculos "
        "morados son los casos abiertos, que necesitan revisión de la SDP.",
    }

    def near(gdf: gpd.GeoDataFrame, focus: shapely.Point, d: float) -> gpd.GeoDataFrame:
        return gdf[gdf.distance(focus) <= d]

    def case(fig: str, key: str, rows, caption, highlight=None, before=None, window=w):
        row = pick_example(rows, ex.get(key), "OBJECTID")
        if row is None:
            out[fig] = None
            return
        f = row.geometry
        hl = highlight(f) if highlight else None
        hb = before(f) if before else None
        path = out_dir / f"figura_{fig[3:]}_{key}.png"
        text = caption(row)
        before_after(f, axes, network, polygons, hl, path, window, hb)
        out[fig] = {"path": path, "caption": text}

    def fixes(tipo):
        return lambda f: near(co[co["tipo"].isin(tipo)], f, 1)

    def kept(rows, tipo):
        """Rows whose correction line is still in the final network (later steps,
        such as interchange relocation, may have redrawn it)."""
        if not len(rows):
            return rows
        keep = []
        for f in rows.geometry:
            lines = fixes(tipo)(f)
            mids = shapely.line_interpolate_point(lines.geometry.values, 0.5, normalized=True)
            keep.append(bool(len(lines)) and bool((network.distance(mids[0]) < 0.5).any()))
        return rows[keep] if any(keep) else rows

    case(
        "fig2",
        "extremo_suelto",
        kept(pr[pr["tipo"] == "extremo_suelto"], ["ajuste"]),
        lambda r: (
            f"Figura 2. Extremo suelto{_who(r)}: la línea termina a "
            f"{_num(r['distancia_m'])} m de otra sin tocarla. Se ajusta el extremo."
        ),
        highlight=fixes(["ajuste"]),
        window=ws,
    )
    case(
        "fig3",
        "cruce_sin_nodo",
        pr[pr["tipo"] == "cruce_sin_nodo"],
        lambda r: (
            f"Figura 3. Cruce sin nodo{_who(r)}: dos líneas se cruzan sin compartir un "
            "punto. Se dividen en el cruce. Ojo: puede ser un puente."
        ),
        highlight=lambda f: gpd.GeoDataFrame(geometry=[f], crs=axes.crs),
    )
    disc = pr[(pr["tipo"] == "discontinuidad") & pr["correccion"].isin(["extension", "conector"])]
    disc = kept(disc, ["extension", "conector"])
    case(
        "fig4",
        "discontinuidad",
        disc,
        lambda r: (
            f"Figura 4. Discontinuidad{_who(r)}: la línea termina, pero los polígonos "
            "del POT muestran que el corredor sigue. Se "
            f"{VERB[r['correccion']]} {_num(r['distancia_m'])} m."
        ),
        highlight=fixes(["extension", "conector"]),
    )
    removed = layers.get("removed")
    case(
        "fig5",
        "tramo_corto",
        pr[pr["tipo"].isin(["tramo_corto", "tramo_duplicado"])],
        lambda r: (
            f"Figura 5. Tramo {'corto' if r['tipo'] == 'tramo_corto' else 'duplicado'}"
            f"{_who(r)}: un tramo sin salida de {_num(r['longitud_m'])} m. Se elimina "
            "(línea punteada)."
        ),
        before=(lambda f: near(removed, f, 1)) if removed is not None else None,
        window=ws,
    )
    op = pr[(pr["tipo"] == "discontinuidad") & (pr["estado"] == "abierto")]
    if "observacion" in op:
        op = op[op["observacion"] == ""]  # at the city limit is not a missing segment
    if len(op):  # automatic pick: the case with the most POT polygon around it
        area = [polygons.intersection(f.buffer(w)).area.sum() for f in op.geometry]
        op = op.iloc[np.argsort(area)[::-1]].assign(distancia_m=np.nan, longitud_m=np.nan)
    row = pick_example(op, ex.get("abierto"), "OBJECTID")
    if row is None:
        out["fig6"] = None
    else:
        text = (
            f"Figura 6. Caso abierto{_who(row)}: el corredor sigue según los polígonos del "
            "POT, pero falta el tramo en el Eje Vial. No se inventa: lo debe revisar la SDP."
        )
        path = single(row.geometry, network, polygons, out_dir / "figura_6_abierto.png", w)
        out["fig6"] = {"path": path, "caption": text}

    rel = de[de["tipo"] == "reubicacion_enlace"]
    row = pick_example(rel, ex.get("reubicacion_enlace"), "CODIGO_ID") if len(rel) else None
    if row is None:
        out["fig7"] = None
    else:
        f = row.geometry
        moved = network[network["sources"].astype(str).str.contains("relocated")]
        text = (
            f"Figura 7. Decisión de modelado, no un error ({row['NOMBRE']}): las vías que "
            "entran al enlace se llevan a un solo punto de encuentro, para el análisis de red."
        )
        path = out_dir / "figura_7_reubicacion_enlace.png"
        before_after(f, axes, network, polygons, near(moved, f, 2.5 * w), path, 2.5 * w)
        out["fig7"] = {"path": path, "caption": text}
    return out
