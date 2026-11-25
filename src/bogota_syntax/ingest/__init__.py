"""Ingest: download each source in config/sources.yaml, record provenance, reproject to EPSG:9377.

Layout under data/ (git-ignored):
- raw/<source_id>/       as received (EPSG:4326 for web services and OSM)
- interim/<source_id>.parquet   reprojected to EPSG:9377, 2D
- interim/extent/        pilot areas, live area, network extent (ADR-0004) and the
                         stitch extent and cleaning areas (ADR-0007)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
import shapely

from bogota_syntax import extent as extent_mod
from bogota_syntax import provenance
from bogota_syntax.config import CRS, CRS_WGS84, data_dir, load_analysis, load_sources
from bogota_syntax.ingest import arcgis, osm

# Sources that the extent depends on come first; the extent is built after the last one.
ORDER = [
    "renobo_proyectos",
    "ideca_limite_bogota",
    "sdp_perimetro_urbano",
    "ideca_malla_vial",
    "sdp_eje_vial",
    "sdp_red_infraestructura_vial",
    "osm_vias",
]
EXTENT_INPUTS = ["renobo_proyectos", "ideca_limite_bogota", "sdp_perimetro_urbano"]


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _to_interim(gdf: gpd.GeoDataFrame, source_id: str, data: Path) -> Path:
    out = data / "interim" / f"{source_id}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf = gdf.to_crs(CRS)
    gdf["geometry"] = shapely.force_2d(gdf.geometry.values)
    gdf.to_parquet(out)
    return out


def _download(url: str, dest: Path, session: requests.Session) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with session.get(
        url, headers={"User-Agent": provenance.USER_AGENT}, stream=True, timeout=300
    ) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(dest)


def _ingest_file(sid: str, src: dict, data: Path, force: bool, s: requests.Session):
    raw = data / "raw" / sid / Path(src["url"]).name
    if force or not raw.exists():
        _download(src["url"], raw, s)
    gdf = gpd.read_file(raw, layer=src.get("layer"))
    return raw, gdf, {"url": src["url"], "layer": src.get("layer")}


def _ingest_arcgis(sid: str, src: dict, data: Path, force: bool, s: requests.Session):
    raw = data / "raw" / sid / f"{sid}.parquet"
    if force or not raw.exists():
        gdf = arcgis.fetch_layer(src["service"], src["layer_id"], src["where"], session=s)
        raw.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_parquet(raw)
    gdf = gpd.read_parquet(raw)
    if "expected_count" in src and len(gdf) != src["expected_count"]:
        raise ValueError(f"{sid}: expected {src['expected_count']} features, got {len(gdf)}")
    query = {"service": src["service"], "layer_id": src["layer_id"], "where": src["where"]}
    return raw, gdf, query


def _ingest_osm(sid: str, src: dict, data: Path, force: bool, s: requests.Session):
    ext_path = data / "interim" / "extent" / f"{src['extent']}.parquet"
    if not ext_path.exists():
        raise FileNotFoundError(f"{sid} needs {ext_path}; run `bogota-syntax extent` first")
    polygon = gpd.read_parquet(ext_path).to_crs(CRS_WGS84).geometry.iloc[0]
    raw = data / "raw" / sid / f"{sid}.parquet"
    meta_path = raw.with_name("overpass.json")
    if force or not raw.exists() or not meta_path.exists():
        gdf, meta = osm.fetch_streets(polygon, src["highway"], data / "raw" / sid / "cache")
        raw.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_parquet(raw)
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    gdf = gpd.read_parquet(raw)
    query = {
        "overpass": "osmnx.graph_from_polygon",
        "filter": osm.highway_filter(src["highway"]),
        "extent": src["extent"],
        "extent_area_km2": round(gpd.read_parquet(ext_path).area.sum() / 1e6, 1),
        "extent_bounds_wgs84": [round(v, 6) for v in polygon.bounds],
    } | json.loads(meta_path.read_text())
    return raw, gdf, query


HANDLERS = {"file": _ingest_file, "arcgis_layer": _ingest_arcgis, "osm_overpass": _ingest_osm}


def ingest_source(sid: str, root: Path, force: bool = False) -> dict[str, Any]:
    """Ingest one source; write raw and interim files and its manifest entry. Returns the entry."""
    src = load_sources(root)[sid]
    data = data_dir(root)
    s = requests.Session()
    raw, gdf, query = HANDLERS[src["kind"]](sid, src, data, force, s)
    interim = _to_interim(gdf, sid, data)
    entry: dict[str, Any] = {
        "kind": src["kind"],
        "licence": src["licence"],
        "query": query,
        "retrieved_at": provenance.now_utc(),
        "n_features": len(gdf),
        "raw_file": _rel(raw, root),
        "raw_sha256": provenance.sha256_file(raw),
        "interim_file": _rel(interim, root),
    }
    if "ckan_dataset" in src:
        entry |= provenance.ckan_metadata(src["ckan_dataset"], s)
    provenance.record(sid, entry, root)
    return entry


def build_extent(root: Path) -> dict[str, Path]:
    """Write the ADR-0004 areas and the ADR-0007 stitch areas to data/interim/extent/.

    Reads the ingested RENOBO layer, Bogotá boundary and urban perimeter (EPSG:9377).
    """
    data = data_dir(root)
    analysis = load_analysis(root)

    def interim(sid: str) -> gpd.GeoDataFrame:
        path = data / "interim" / f"{sid}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"extent needs {path}; run `bogota-syntax ingest {sid}`")
        return gpd.read_parquet(path)

    layers = extent_mod.build(interim(analysis["pilot"]["source"]), analysis)
    layers |= extent_mod.build_stitch(
        interim(analysis["stitch"]["boundary_source"]),
        interim(analysis["stitch"]["urban_source"]),
        layers["network_extent"],
        analysis,
    )
    out_dir = data / "interim" / "extent"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, gdf in layers.items():
        paths[name] = out_dir / f"{name}.parquet"
        gdf.to_parquet(paths[name])
    return paths
