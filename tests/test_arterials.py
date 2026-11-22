"""ADR-0008 arterial replacement, on a synthetic divided road in EPSG:9377."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from bogota_syntax import arterials

X0, Y0 = 4_880_000, 2_070_000


def _gdf(rows: list[tuple[str, list[tuple[float, float]]]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"MVITIPO": [t for t, _ in rows]},
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in c]) for _, c in rows],
        crs="EPSG:9377",
    )


def _axis() -> gpd.GeoDataFrame:
    a = _gdf([("", [(0, 0), (1000, 0)])])
    return a.assign(NOMBRE="Avenida X", ESTADO_VIA=20, TIPO_VIA="A-2")[
        ["NOMBRE", "ESTADO_VIA", "TIPO_VIA", "geometry"]
    ]


def _mvi() -> gpd.GeoDataFrame:
    # Two carriageways 20 m either side of the axis, a local street ending on the north
    # carriageway, a local street crossing nothing 200 m away, and a loop ramp near the
    # axis that only touches the carriageway.
    return _gdf(
        [
            ("AC", [(0, 20), (500, 20)]),
            ("AC", [(500, 20), (700, 20)]),  # split where the loop meets it, as MVI is
            ("AC", [(700, 20), (780, 20)]),
            ("AC", [(780, 20), (1000, 20)]),
            ("AC", [(0, -20), (1000, -20)]),
            ("CL", [(500, 20), (500, 300)]),
            ("CL", [(0, 200), (1000, 200)]),
            ("CL", [(700, 20), (720, 60), (760, 60), (780, 20)]),
        ]
    )


def test_axes_are_selected_by_distance_to_mvi() -> None:
    far = _gdf([("", [(0, 900), (1000, 900)])]).assign(NOMBRE="Projected")
    axes = gpd.GeoDataFrame(pd.concat([_axis(), far], ignore_index=True), crs="EPSG:9377")
    sel = arterials.select_axes(axes, _mvi(), 25, 0.9)
    assert sel["NOMBRE"].tolist() == ["Avenida X"]


def test_carriageways_replaced_by_axis_and_local_street_connected() -> None:
    out = arterials.guide(_mvi(), _axis(), 60, ["AC", "AK"], 150)
    assert len(out["removed"]) == 6  # five carriageway lines + the stranded loop
    conn = out["connectors"]
    assert len(conn) == 1
    assert round(conn.length.iloc[0]) == 20  # local street end -> axis
    edited = out["edited"]
    assert set(edited["source"].dropna()) >= {"sdp_eje_vial", "axis_connector"}
    # The parallel local street 200 m away is untouched.
    assert (edited.geometry.length.round() == 1000).sum() == 2  # axis + that street


def test_axis_gap_closed_within_snap_distance() -> None:
    net = _gdf(
        [
            ("", [(0, 0), (500, 0)]),
            ("", [(503, 0), (1000, 0)]),  # 3 m gap between two axis lines
            ("", [(0, 500), (400, 500)]),  # far from anything
        ]
    ).assign(source="sdp_eje_vial")
    gaps = arterials.close_axis_gaps(net, 10)
    assert len(gaps) == 1  # both facing ends give the same segment; kept once
    assert gaps.length.round().tolist() == [3]


def test_removed_sole_link_is_restored() -> None:
    # main street -- link (removed) -- side street; the side street was in the main piece.
    net = _gdf([("CL", [(0, 0), (1000, 0)]), ("CL", [(0, 200), (300, 200)])])
    removed = _gdf([("AK", [(0, 0), (0, 200)])])
    net["_cid"], removed["_cid"] = [0, 2], [1]
    out, restored = arterials.restore_links(net.assign(source="mvi"), removed, {0, 1, 2})
    assert len(restored) == 1 and restored["source"].iloc[0] == "mvi_restored"
    assert len(out) == 3


def test_dead_end_extended_only_when_it_meets_a_line() -> None:
    net = _gdf(
        [
            ("CL", [(0, 0), (1000, 0)]),
            ("KR", [(500, 8), (500, 300)]),  # stops 8 m short of the street: extended
            ("KR", [(800, 300), (800, 100)]),  # 100 m short: left as a cul-de-sac
        ]
    )
    _, extended = arterials.extend_dead_ends(net, 10)
    assert len(extended) == 1
    assert round(extended["added_m"].iloc[0]) == 8
