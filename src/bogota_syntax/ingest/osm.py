"""Fetch OSM streets inside a polygon through Overpass, with osmnx."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry.base import BaseGeometry

from bogota_syntax.config import CRS_WGS84

KEEP_COLUMNS = ["osmid", "highway", "name", "oneway", "lanes", "maxspeed", "u", "v", "key"]


def highway_filter(values: list[str]) -> str:
    """Overpass filter selecting ways whose highway tag is exactly one of `values`."""
    if not values:
        raise ValueError("highway filter needs at least one value")
    return f'["highway"~"^({"|".join(values)})$"]'


def fetch_streets(
    polygon_wgs84: BaseGeometry, highway: list[str], cache_dir: Path
) -> gpd.GeoDataFrame:
    """Return OSM street edges inside `polygon_wgs84` (EPSG:4326), one row per edge, in EPSG:4326.

    The graph is not simplified (neatnet cleans, ADR-0005) and is made undirected, so a
    two-way street is one line, not two.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
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
    return gpd.GeoDataFrame(edges, geometry="geometry", crs=CRS_WGS84)
