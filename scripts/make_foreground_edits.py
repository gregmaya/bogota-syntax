"""Turn a manually edited foreground network into config/foreground_edits.geojson
(ADR-0012, step 12), so `bogota-syntax foreground` reproduces the edits.

Usage: uv run python scripts/make_foreground_edits.py <edited.gpkg> [layer]

Compares the edited network (a local copy, e.g. in data/labels/) with the pipeline's
output without edits (data/processed/foreground.parquet, from a run before any edits file
existed or with it emptied). A row whose geometry and attributes are both unchanged is
not an edit. Every other pipeline row is an `edit: remove`, every other edited row an
`edit: add` with its attributes. EPSG:9377, coordinates written exactly.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

root = Path(__file__).resolve().parents[1]
edited = gpd.read_file(sys.argv[1], layer=sys.argv[2] if len(sys.argv) > 2 else "foreground")
base = gpd.read_parquet(root / "data/processed/foreground.parquet")
cols = [c for c in base.columns if c != "geometry"]
assert set(cols) <= set(edited.columns), "edited layer lacks pipeline columns"


def keys(gdf: gpd.GeoDataFrame) -> pd.Series:
    attrs = gdf[cols].astype(object).map(lambda v: "" if pd.isna(v) else str(v))
    return gdf.geometry.normalize().to_wkb().map(bytes.hex) + "|" + attrs.agg("|".join, axis=1)


kb, ke = keys(base), keys(edited)
removed = base[~kb.isin(set(ke))].assign(edit="remove")
added = edited[~ke.isin(set(kb))][[*cols, "geometry"]].assign(edit="add")
edits = pd.concat([removed, added], ignore_index=True).pipe(gpd.GeoDataFrame, crs=base.crs)
out = root / "config" / "foreground_edits.geojson"
out.unlink(missing_ok=True)
edits.to_file(out, driver="GeoJSON", RFC7946="NO", WRITE_NAME="NO")  # 17 digits: exact
print(f"remove {len(removed)}, add {len(added)} -> {out.relative_to(root)}")
