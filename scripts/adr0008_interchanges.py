"""ADR-0008 interchange test: SDP arterial axes inserted before vs after neatnet.

Run after `bogota-syntax clean mvi` (needs data/interim/clean/mvi_*.parquet) and with the
SDP eje-vial download in data/raw/sdp_eje_vial/eje_vial.gpkg:

    uv run --with matplotlib python scripts/adr0008_interchanges.py OUT_DIR

Writes, per interchange and order, review layers to OUT_DIR/interchanges_<order>.gpkg
and a PNG, and prints the table in ADR-0008. EPSG:9377, metres.
"""

from __future__ import annotations

import collections
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib
import neatnet
import shapely

from bogota_syntax import arterials
from bogota_syntax.clean import kept_fraction
from bogota_syntax.config import project_root

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

AXIS_MATCH_M, MIN_AXIS_ON_MVI = 25, 0.9
CORRIDOR_M, RAMP_ZONE_M = 60, 150
TYPES = ["AC", "AK"]
VIEW_M, MARGIN_M = 450, 700  # half-width of the reviewed window; extra area processed

# Interchanges as pairs of axis names in eje-vial; the site is their crossing.
SITES = {
    "1_cl72_av68": ("Avenida Chile", "Avenida del Congreso Eucaristico"),
    "2_cl26_av68": (
        "Avenida El Dorado - Jorge Eliecer Gaitan",
        "Avenida del Congreso Eucaristico",
    ),
    "3_cl26_nqs": ("Avenida El Dorado - Jorge Eliecer Gaitan", "Avenida Ciudad de Quito"),
    "4_autonorte_cl100": (
        "Avenida Paseo de los Libertadores ( Autopista Norte)",
        "Avenida Carlos Lleras Restrepo",
    ),
    "5_cl80_boyaca": ("Avenida Medellin", "Avenida Boyaca"),
    "6_americas_av68": ("Avenida de las Americas", "Avenida del Congreso Eucaristico"),
    "7_nqs_autonorte": (
        "Avenida Ciudad de Quito",
        "Avenida Paseo de los Libertadores ( Autopista Norte)",
    ),
}


def dead_ends(lines: gpd.GeoDataFrame) -> int:
    """Line ends that meet no other line end (window edges included)."""
    g = lines.geometry.values
    pts = [
        *shapely.get_coordinates(shapely.get_point(g, 0)).round(2).tolist(),
        *shapely.get_coordinates(shapely.get_point(g, -1)).round(2).tolist(),
    ]
    return sum(1 for v in collections.Counter(map(tuple, pts)).values() if v == 1)


def lines_only(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.explode(ignore_index=True)
    return gdf[gdf.geom_type == "LineString"].reset_index(drop=True)


def main(out: Path) -> None:
    root = project_root()
    out.mkdir(parents=True, exist_ok=True)
    raw = gpd.read_parquet(root / "data/interim/clean/mvi_raw.parquet")
    cleaned = gpd.read_parquet(root / "data/interim/clean/mvi_cleaned.parquet")
    eje = gpd.read_file(root / "data/raw/sdp_eje_vial/eje_vial.gpkg").to_crs(9377)
    axes_all = arterials.select_axes(eje, raw, AXIS_MATCH_M, MIN_AXIS_ON_MVI)
    print(
        f"axes selected: {len(axes_all)} of {len(lines_only(eje))} lines, "
        f"{axes_all.length.sum() / 1e3:.0f} km"
    )
    print("| site | axis kept before | axis kept after | dead ends now / after |")
    for name, (name_a, name_b) in SITES.items():
        line_a = eje.loc[eje["NOMBRE"].eq(name_a)].union_all()
        x = line_a.intersection(eje.loc[eje["NOMBRE"].eq(name_b)].union_all())
        c = x.centroid
        view = shapely.box(c.x - VIEW_M, c.y - VIEW_M, c.x + VIEW_M, c.y + VIEW_M)
        work = view.buffer(MARGIN_M, join_style="mitre")
        m = lines_only(raw.clip(work))
        now = lines_only(cleaned.clip(work))
        ax = lines_only(axes_all.clip(work))
        before = arterials.guide(m, ax, CORRIDOR_M, TYPES, RAMP_ZONE_M)
        before["result"] = lines_only(neatnet.neatify(before["edited"]))
        after = arterials.guide(now, ax, CORRIDOR_M, TYPES, RAMP_ZONE_M)
        after["result"] = lines_only(neatnet.induce_nodes(after["edited"]))
        row = [name]
        for order, g in (("before", before), ("after", after)):
            axv = lines_only(g["axes"].clip(view))
            k = kept_fraction(axv, lines_only(g["result"].clip(view)), 5, 5)
            row.append(f"{(k * axv.length).sum() / axv.length.sum():.2f}")
            gpkg = out / f"interchanges_{order}.gpkg"
            for layer in ("removed", "axes", "connectors", "result"):
                v = g[layer].clip(view)
                if len(v):
                    v.to_file(gpkg, layer=f"{name}__{layer}", driver="GPKG")
            _plot(out / f"{name}_{order}.png", name, order, view, m, now, g)
        now_v, after_v = lines_only(now.clip(view)), lines_only(after["result"].clip(view))
        row.append(f"{dead_ends(now_v)} / {dead_ends(after_v)}")
        print("| " + " | ".join(row) + " |")


def _plot(path, name, order, view, raw, now, g) -> None:
    x0, y0, x1, y1 = view.bounds
    fig, axs = plt.subplots(1, 3, figsize=(18, 6.4))
    panels = [
        ("MVI raw (grey), SDP axes (black)", [(raw, "#999", 0.8), (g["axes"], "k", 2.2)]),
        ("Cleaned now (red)", [(now, "#d62728", 1.2), (g["axes"], "k", 0.6)]),
        (
            f"Axes {order} neatnet (blue), connectors (orange)",
            [(g["result"], "#1f77b4", 1.2), (g["connectors"], "orange", 2.5)],
        ),
    ]
    for a, (title, layers) in zip(axs, panels, strict=True):
        for gdf, colour, lw in layers:
            v = gdf.clip(view)
            if len(v):
                v.plot(ax=a, color=colour, linewidth=lw)
        a.set_xlim(x0, x1)
        a.set_ylim(y0, y1)
        a.set_aspect("equal")
        a.set_axis_off()
        a.set_title(title, fontsize=10)
    fig.suptitle(f"{name}: corridor {CORRIDOR_M} m, ramp zone {RAMP_ZONE_M} m")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
