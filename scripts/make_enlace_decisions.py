"""Derive config/enlace_decisions.csv from Gregorio's QGIS labels (ADR-0012, step 11).

Usage: uv run python scripts/make_enlace_decisions.py <labels.gpkg>

The labels file is local (data/labels/, not committed): the `enlace` layer of the
2026-11-24 relocation run, with `relocated` (what the run did) and `correct_center`
(1 if the network at that interchange was right after the run, moved or not).

Decision per labelled polygon:
- relocate: relocated and right
- keep:     relocated and wrong, or not relocated and right
- review:   not relocated and wrong (relocation alone doesn't fix it)
Unlabelled polygons get no row; the fallback rule handles them.

Each row is keyed by CODIGO_ID plus the polygon's representative point (rounded to
1 m) and stores its area, so a polygon SDP redraws no longer matches its decision.
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[1]
labels = gpd.read_file(sys.argv[1], layer="enlace")
polys = gpd.read_parquet(root / "data/interim/sdp_red_infraestructura_vial.parquet")
enlace = polys[polys["NOMBRE"].fillna("").str.contains("enlace", case=False)]
assert list(labels["NOMBRE"]) == list(enlace["NOMBRE"]), "label rows out of order"

rel = labels["relocated"].astype(bool).values
ok = labels["correct_center"].values
decision = np.select(
    [rel & (ok == 1), (rel & (ok == 0)) | (~rel & (ok == 1)), ~rel & (ok == 0)],
    ["relocate", "keep", "review"],
    "",
)
rep = enlace.geometry.representative_point()
table = pd.DataFrame(
    {
        "codigo_id": enlace["CODIGO_ID"].values,
        "rep_x": rep.x.round(0).astype(int).values,
        "rep_y": rep.y.round(0).astype(int).values,
        "area_m2": enlace.area.round(0).astype(int).values,
        "decision": decision,
        "nombre": enlace["NOMBRE"].str.strip().values,  # informational only
    }
)
table = table[table["decision"] != ""]
out = root / "config" / "enlace_decisions.csv"
table.to_csv(out, index=False)
print(table["decision"].value_counts().to_dict(), f"-> {out.relative_to(root)}")
