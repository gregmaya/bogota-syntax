"""Extent rules from ADR-0004, on synthetic squares in EPSG:9377."""

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from bogota_syntax import extent

# A point in central Bogotá, EPSG:9377 (Origen Nacional, metres).
X0, Y0 = 4_880_000, 2_070_000


def _projects() -> gpd.GeoDataFrame:
    geoms = [box(X0, Y0, X0 + 100, Y0 + 100), box(X0 + 1000, Y0, X0 + 1100, Y0 + 100)]
    return gpd.GeoDataFrame(
        {"GmlID": ["P.1", "P.2"], "Identificador_de_Proyecto": ["A", "A"]},
        geometry=geoms,
        crs="EPSG:9377",
    )


def test_buffer_width_is_max_distance_or_minimum() -> None:
    assert extent.buffer_width([400, 800, 5000], 5000) == 5000
    assert extent.buffer_width([400, 10_000], 5000) == 10_000
    assert extent.buffer_width([400], 5000) == 5000


def test_buffer_width_needs_distances() -> None:
    with pytest.raises(ValueError):
        extent.buffer_width([], 5000)


def test_select_by_gml_id_not_project_id() -> None:
    sel = extent.select_pilot_areas(_projects(), ["P.2"])
    assert list(sel["GmlID"]) == ["P.2"]
    assert sel.crs.to_epsg() == 9377


def test_select_rejects_missing_and_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="not found"):
        extent.select_pilot_areas(_projects(), ["P.9"])
    with pytest.raises(ValueError, match="duplicates"):
        extent.select_pilot_areas(_projects(), ["P.1", "P.1"])


def test_select_drops_z() -> None:
    p = _projects()
    p["geometry"] = gpd.GeoSeries.from_wkt(
        [f"POLYGON Z (({X0} {Y0} 5, {X0 + 10} {Y0} 5, {X0 + 10} {Y0 + 10} 5, {X0} {Y0} 5))"] * 2,
        crs="EPSG:9377",
    )
    assert not extent.select_pilot_areas(p, ["P.1"]).has_z.any()


def test_areas_are_nested() -> None:
    analysis = {
        "distances": [400, 5000],
        "buffer_min_m": 5000,
        "pilot": {"gml_ids": ["P.1", "P.2"], "live_margin_m": 5000},
    }
    out = extent.build(_projects(), analysis)
    pilot = out["pilot_areas"].union_all()
    live = out["live_area"].geometry.iloc[0]
    net = out["network_extent"].geometry.iloc[0]
    assert live.contains(pilot)
    assert net.contains(live)
    # A point 9 km from the pilot areas is in the network but not live; 11 km is outside.
    assert net.contains(Point(X0 + 1100 + 9_000, Y0)) and not live.contains(
        Point(X0 + 1100 + 9_000, Y0)
    )
    assert not net.contains(Point(X0 + 1100 + 11_000, Y0))
