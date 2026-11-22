"""Pilot areas, live area and network extent (ADR-0004), and the stitch areas (ADR-0007).

All in EPSG:9377, metres.
"""

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


def stitch_areas(
    boundary: BaseGeometry,
    urban: BaseGeometry,
    net_extent: BaseGeometry,
    stitch_margin_m: float,
    clean_overlap_m: float,
    buffer_m: float,
) -> dict[str, BaseGeometry]:
    """Areas for the stitched network (ADR-0007), all EPSG:9377.

    Inputs are the Bogotá boundary, the urban perimeter and the analysis network extent.
    Returns:
    - stitch_extent: urban perimeter + stitch_margin_m, united with the network extent;
    - mvi_clean_area: stitch extent inside the boundary grown by clean_overlap_m;
    - osm_clean_area: stitch extent outside the boundary shrunk by clean_overlap_m.

    Raises ValueError if stitch_margin_m is below the dead-buffer width buffer_m, or if
    clean_overlap_m is not positive.
    """
    if stitch_margin_m < buffer_m:
        raise ValueError(
            f"stitch_margin_m ({stitch_margin_m}) is below the dead buffer ({buffer_m}); "
            "the full city would lose part of its buffer"
        )
    if clean_overlap_m <= 0:
        raise ValueError("clean_overlap_m must be positive")
    stitch = shapely.union(urban.buffer(stitch_margin_m), net_extent)
    return {
        "stitch_extent": stitch,
        "mvi_clean_area": stitch.intersection(boundary.buffer(clean_overlap_m)),
        "osm_clean_area": stitch.difference(boundary.buffer(-clean_overlap_m)),
    }


def build_stitch(
    boundary: gpd.GeoDataFrame,
    urban: gpd.GeoDataFrame,
    net_extent: gpd.GeoDataFrame,
    analysis: dict[str, Any],
) -> dict[str, gpd.GeoDataFrame]:
    """One-row GeoDataFrames for the stitch areas, from config/analysis.yaml settings."""
    cfg = analysis["stitch"]
    width = buffer_width(analysis["distances"], analysis["buffer_min_m"])
    areas = stitch_areas(
        shapely.union_all(boundary.to_crs(CRS).geometry.values),
        shapely.union_all(urban.to_crs(CRS).geometry.values),
        shapely.union_all(net_extent.to_crs(CRS).geometry.values),
        cfg["stitch_margin_m"],
        cfg["clean_overlap_m"],
        width,
    )
    attrs = {"stitch_margin_m": cfg["stitch_margin_m"], "clean_overlap_m": cfg["clean_overlap_m"]}
    return {
        name: gpd.GeoDataFrame({k: [v] for k, v in attrs.items()}, geometry=[g], crs=CRS)
        for name, g in areas.items()
    }
