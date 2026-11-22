"""Fetch OSM streets inside a polygon through Overpass, with osmnx."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
from shapely.geometry.base import BaseGeometry

from bogota_syntax import provenance
from bogota_syntax.config import CRS_WGS84

KEEP_COLUMNS = ["osmid", "highway", "name", "oneway", "lanes", "maxspeed", "u", "v", "key"]


def highway_filter(values: list[str]) -> str:
    """Overpass filter selecting ways whose highway tag is exactly one of `values`."""
    if not values:
        raise ValueError("highway filter needs at least one value")
    return f'["highway"~"^({"|".join(values)})$"]'


def overpass_timestamps(cache_dir: Path) -> list[str]:
    """Sorted distinct `osm3s.timestamp_osm_base` values in the osmnx cache responses.

    This is the date of the OSM data Overpass served, one per sub-query response.
    """
    stamps = set()
    for f in cache_dir.glob("*.json"):
        data = json.loads(f.read_text())
        if isinstance(data, dict) and "osm3s" in data:
            stamps.add(data["osm3s"]["timestamp_osm_base"])
    return sorted(stamps)


def fetch_streets(
    polygon_wgs84: BaseGeometry, highway: list[str], cache_dir: Path
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Fetch the latest OSM streets inside `polygon_wgs84` (EPSG:4326) from Overpass.

    Returns one row per edge in EPSG:4326, and query metadata: when the query ran, the
    Overpass endpoint, the osmnx version and the OSM data timestamp(s) Overpass reported.
    The cache is cleared first, so no earlier response is reused (ADR-0007). The graph is
    not simplified (neatnet cleans, ADR-0005) and is made undirected, so a two-way street
    is one line, not two.
    """
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True)
    started = provenance.now_utc()
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.log_console = False
    g = ox.graph_from_polygon(
        polygon_wgs84,
        custom_filter=highway_filter(highway),
        simplify=False,
        retain_all=True,
        truncate_by_edge=True,
    )
    g = ox.convert.to_undirected(g)
    edges = ox.graph_to_gdfs(g, nodes=False).reset_index()
    edges = edges[[c for c in KEEP_COLUMNS if c in edges.columns] + ["geometry"]]
    # Tags that osmnx returns as lists (several values on one way) become "a;b" strings,
    # the OSM convention, so the table can be written to GeoParquet.
    for col in edges.columns.drop("geometry"):
        if edges[col].map(lambda x: isinstance(x, list)).any():
            edges[col] = edges[col].map(
                lambda x: ";".join(map(str, x)) if isinstance(x, list) else x
            )
    stamps = overpass_timestamps(cache_dir)
    if not stamps:
        raise RuntimeError(f"no Overpass response with osm3s timestamp found in {cache_dir}")
    meta = {
        "query_started_at": started,
        "query_finished_at": provenance.now_utc(),
        "overpass_url": ox.settings.overpass_url,
        "osmnx_version": ox.__version__,
        "n_overpass_responses": len(list(cache_dir.glob("*.json"))),
        "osm_timestamp_min": stamps[0],
        "osm_timestamp_max": stamps[-1],
    }
    return gpd.GeoDataFrame(edges, geometry="geometry", crs=CRS_WGS84), meta
