"""Publish layers for bogota-atlas: one PMTiles per layer plus etapas.json.

The layer list and its text live in config/etapas.yaml; colour breaks, bounds and field types
are computed here from the data. The contract is bogota-pop ADR-0013 (schema in
bogota-atlas/schema/etapas.schema.json).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

KEEP = ["segment_id", "boundary_dist_m"]  # kept in every layer
MEASURE_METHOD = {
    "harmonic": {
        "es": "Ruta más simple (costo angular) en el grafo dual, sin dirección ni pesos.",
        "en": "Simplest route (angular cost) on the dual graph, undirected and unweighted.",
    },
    "betweenness": {
        "es": "Rutas más simples (costo angular) en el grafo dual, sin dirección ni pesos.",
        "en": "Simplest routes (angular cost) on the dual graph, undirected and unweighted.",
    },
}
EDGE = {
    "es": "La red se corta en el límite de Bogotá; boundary_dist_m da la distancia al borde (m).",
    "en": "The network stops at the Bogotá limit; boundary_dist_m gives the distance to it (m).",
}


def load_etapas(root: Path) -> dict[str, Any]:
    """Read config/etapas.yaml."""
    with (root / "config" / "etapas.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def quantile_breaks(values: pd.Series, classes: int) -> list[float]:
    """Ascending, distinct class starts at quantiles 0, 1/classes, ... (rounded to 3 dp)."""
    q = np.quantile(values.dropna().to_numpy(float), np.arange(classes) / classes)
    return sorted({round(float(v), 3) for v in q})


def _field_type(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_numeric_dtype(s):
        return "number"
    return "string"


def _commit(root: Path) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"], cwd=root, capture_output=True, text=True
    )
    return out.stdout.strip()


def _method(layer: dict, net: dict) -> dict[str, str]:
    field = layer["style_field"]
    kind = next((k for k in MEASURE_METHOD if k in field), None)
    parts = [MEASURE_METHOD[kind]] if kind else []
    parts += [net["network_method"], EDGE]
    return {lang: " ".join(p[lang].strip() for p in parts) for lang in ("es", "en")}


def write_pmtiles(
    gdf: gpd.GeoDataFrame, path: Path, layer: str, minzoom: int, maxzoom: int, max_bytes: int
):
    """Write `gdf` (any CRS) as a PMTiles vector file with one layer named `layer`.

    `max_bytes` is GDAL's MAX_SIZE: a tile over it is rewritten on a coarser grid.
    """
    import pyogrio

    path.unlink(missing_ok=True)
    pyogrio.write_dataframe(
        gdf.to_crs(3857),
        path,
        driver="PMTiles",
        layer=layer,
        dataset_options={"MINZOOM": minzoom, "MAXZOOM": maxzoom, "MAX_SIZE": max_bytes},
    )


def run(root: Path) -> dict[str, Any]:
    """Build every layer in config/etapas.yaml.

    Input: the centrality parquet of each network (EPSG:9377). Output: <out_dir>/<id>.pmtiles
    (EPSG:3857) and <out_dir>/etapas.json (bounds in EPSG:4326 degrees).
    """
    cfg = load_etapas(root)
    out = root / cfg["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.pmtiles"):  # layers dropped from the config must not linger
        old.unlink()
    cache: dict[str, gpd.GeoDataFrame] = {}
    layers = []
    for layer in cfg["layers"]:
        net = cfg["networks"][layer["network"]]
        if layer["network"] not in cache:
            gdf = gpd.read_parquet(root / net["input"])
            if net.get("live_only"):
                gdf = gdf[gdf["live"]]
            cache[layer["network"]] = gdf.reset_index(drop=True)
        gdf = cache[layer["network"]]
        field = layer["style_field"]
        fields = [KEEP[0], field, *KEEP[1:]]
        sub = gdf[[*fields, "geometry"]]
        write_pmtiles(
            sub,
            out / f"{layer['id']}.pmtiles",
            layer["id"],
            net["minzoom"],
            net["maxzoom"],
            net["max_tile_bytes"],
        )
        style: dict[str, Any] = {"field": field, "kind": layer["kind"]}
        if layer["kind"] == "sequential":
            style["breaks"] = quantile_breaks(sub[field], cfg["quantile_classes"])
        w, s, e, n = sub.to_crs(4326).total_bounds
        layers.append(
            {
                "id": layer["id"],
                "title": layer["title"],
                "description": layer["description"],
                "method": _method(layer, net),
                "review": layer["review"],
                "group": "red_vial",
                "stage": "centrality",
                "sources": net["sources"],
                "input": net["input"],
                "level": "segmento",
                "public": True,
                "fields": fields,
                "style": style,
                "unit": layer["unit"],
                "minzoom": net["minzoom"],
                "maxzoom": net["maxzoom"],
                "file": f"{layer['id']}.pmtiles",
                "geometry": "line",
                "field_types": {f: _field_type(sub[f]) for f in fields},
                "bounds": [round(float(v), 5) for v in (w, s, e, n)],
                "vigencia": {sid: None for sid in net["sources"]},
                "attribution": " ".join(net["attribution"].split()),
            }
        )
        if "series" in layer:
            p = cfg["series_parameter"]
            layers[-1]["series"] = layer["series"]
            layers[-1]["parameter"] = {**p, "value": layer["radius_m"]}
        if "subtitle" in net:
            layers[-1]["subtitle"] = net["subtitle"]
    doc = {
        "schema_version": cfg["schema_version"],
        "producer": cfg["producer"],
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": _commit(root),
        "layers": layers,
    }
    (out / "etapas.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    sizes = {p.name: p.stat().st_size for p in sorted(out.glob("*.pmtiles"))}
    return {"out_dir": str(out), "layers": len(layers), "bytes": sizes}
