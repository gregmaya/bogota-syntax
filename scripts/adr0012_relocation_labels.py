"""Figures behind ADR-0012 point 5: how well geometry predicts Gregorio's labels of
interchange centres, and how the fallback rule scores on them.

Usage: uv run python scripts/adr0012_relocation_labels.py <labels.gpkg>   (~40 s)

Rebuilds the foreground network without step 11, measures each "Enlace Vehicular"
polygon with the pipeline's own functions, and compares with the labels (the `enlace`
layer of the 2026-11-24 test run: `relocated`, `correct_center`).
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from bogota_syntax import foreground as fg
from bogota_syntax.config import CRS, data_dir, load_analysis

root = Path(__file__).resolve().parents[1]
cfg = load_analysis(root)["foreground"]
p, r = fg.Params.from_config(cfg), fg.RelocationParams.from_config(cfg["relocation"])
data = data_dir(root)
axes = gpd.read_parquet(data / "interim" / f"{cfg['axes_source']}.parquet").to_crs(CRS)
polys = gpd.read_parquet(data / "interim" / f"{cfg['polygons_source']}.parquet").to_crs(CRS)
net = fg.clean(axes, polys, p)["network"].reset_index(drop=True)

enlace = polys[polys["NOMBRE"].fillna("").str.contains(r.name_pattern, case=False)]
labels = gpd.read_file(sys.argv[1], layer="enlace")
assert list(labels["NOMBRE"]) == list(enlace["NOMBRE"]), "label rows out of order"

jpts, _ = fg.junctions(net)
rows = []
for poly in enlace.geometry:
    poly = max(shapely.get_parts(poly), key=lambda q: q.area)
    inside = jpts[shapely.intersects(jpts, poly)]
    row = {"junctions": len(inside), "approaches": 0}
    if len(inside):
        _, _, apps = fg.approaches(net, poly, inside, r.approach_m)
        row["approaches"] = len(apps)
        if len(apps) >= 2:
            x, rms = fg.meeting_point(apps, poly)
            move = float(np.linalg.norm(shapely.get_coordinates(inside) - x, axis=1).max())
            side = np.sqrt(poly.area)
            row |= {"move_m": move, "rms_rel": rms / side, "move_rel": move / side}
    rows.append(row)
f = pd.DataFrame(rows)
f["relocated"] = labels["relocated"].astype(bool).values
f["right"] = labels["correct_center"].values
f = f[f["right"].notna()]
print(f"labelled: {len(f)} of {len(enlace)}")

a = f[(f["junctions"] == 1) & f["relocated"]]
y = a["right"].astype(int)
rank = a["rms_rel"].rank()
n1, n0 = int((y == 1).sum()), int((y == 0).sum())
auc = 1 - (rank[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
print(f"single-junction relocations: {len(a)} ({n1} right, {n0} wrong)")
print(f"  AUC of rms_rel (lower when right): {auc:.2f}")
for t in (0.05, r.max_rms_rel):
    k = a["rms_rel"] <= t
    print(
        f"  rms_rel <= {t}: {int(k.sum())} kept, {int(y[k].sum())} right, "
        f"{int((1 - y[k]).sum())} wrong"
    )


def rule(row) -> bool:
    return fg.fallback_relocate(row.to_dict(), r) if row["approaches"] >= 2 else False


f["rule"] = f.apply(rule, axis=1)
reloc = f[f["rule"]]
right = (reloc["relocated"] & (reloc["right"] == 1)).sum()
print(
    f"fallback rule on the labelled set: relocates {len(reloc)}, of which the test run's "
    f"relocation was labelled right {int(right)}"
)
