"""Pilot areas, live area and network extent (ADR-0004). All in EPSG:9377, metres."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import geopandas as gpd
import shapely
from shapely.geometry.base import BaseGeometry

from bogota_syntax.config import CRS


def buffer_width(distances: Iterable[float], buffer_min_m: float) -> float:
    """Dead-buffer width in metres: the largest analysis distance, and at least buffer_min_m."""
    ds = list(distances)
    if not ds:
        raise ValueError("at least one analysis distance is needed")
    return float(max(max(ds), buffer_min_m))


def select_pilot_areas(projects: gpd.GeoDataFrame, gml_ids: list[str]) -> gpd.GeoDataFrame:
    """Return the RENOBO polygons whose GmlID is in `gml_ids`, 2D, in EPSG:9377.

    Raises ValueError if an id is missing or repeated.
    """
    if len(set(gml_ids)) != len(gml_ids):
        raise ValueError("gml_ids contains duplicates")
    missing = set(gml_ids) - set(projects["GmlID"])
    if missing:
        raise ValueError(f"GmlID not found in source: {sorted(missing)}")
    sel = projects[projects["GmlID"].isin(gml_ids)].copy()
    sel = sel.to_crs(CRS)
    sel["geometry"] = shapely.force_2d(sel.geometry.values)
    return sel.reset_index(drop=True)


def live_area(pilot: gpd.GeoDataFrame, margin_m: float) -> BaseGeometry:
    """Union of the pilot areas buffered by margin_m (EPSG:9377)."""
    return shapely.union_all(pilot.geometry.values).buffer(margin_m)


def network_extent(live: BaseGeometry, width_m: float) -> BaseGeometry:
    """Live area buffered by the dead-buffer width (EPSG:9377)."""
    return live.buffer(width_m)


def build(projects: gpd.GeoDataFrame, analysis: dict[str, Any]) -> dict[str, gpd.GeoDataFrame]:
    """Compute pilot areas, live area and network extent from config/analysis.yaml settings."""
    pilot_cfg = analysis["pilot"]
    pilot = select_pilot_areas(projects, pilot_cfg["gml_ids"])
    live = live_area(pilot, pilot_cfg["live_margin_m"])
    width = buffer_width(analysis["distances"], analysis["buffer_min_m"])
    net = network_extent(live, width)
    return {
        "pilot_areas": pilot,
        "live_area": gpd.GeoDataFrame(
            {"margin_m": [pilot_cfg["live_margin_m"]]}, geometry=[live], crs=CRS
        ),
        "network_extent": gpd.GeoDataFrame({"buffer_m": [width]}, geometry=[net], crs=CRS),
    }
