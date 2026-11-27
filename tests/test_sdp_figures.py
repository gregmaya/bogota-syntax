"""Figures for the SDP package, on the synthetic layout of test_sdp_package."""

import warnings

import geopandas as gpd

from bogota_syntax import sdp_figures as sf
from bogota_syntax import sdp_package as sp
from test_sdp_package import AX, CFG, NET, X0, Y0, empty, points, review_layers, segs


def test_pick_example_by_id() -> None:
    rows = points((0, 0), (1, 1), (2, 2), OBJECTID=[5, 7, 9], distancia_m=[1.0, 2.0, 3.0])
    assert sf.pick_example(rows, 7, "OBJECTID")["OBJECTID"] == 7


def test_pick_example_missing_id_falls_back() -> None:
    rows = points((0, 0), (1, 1), (2, 2), OBJECTID=[5, 7, 9], distancia_m=[1.0, 2.0, 30.0])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        got = sf.pick_example(rows, 999, "OBJECTID")
    assert got["OBJECTID"] == 7  # nearest the median distance
    assert any("999" in str(x.message) for x in w)


def test_pick_example_empty_is_none() -> None:
    assert sf.pick_example(empty(OBJECTID=[], distancia_m=[]), None, "OBJECTID") is None


def test_make_figures_writes_pngs(tmp_path) -> None:
    L = review_layers()
    pkg = {
        "problemas": sp.build_problemas(L, AX, NET, CFG),
        "correcciones": sp.build_correcciones(L, AX, CFG),
        "decisiones_modelado": empty(tipo=[], origen=[], CODIGO_ID=[], NOMBRE=[]),
        "ediciones_manuales": sp.build_ediciones(None),
    }
    polys = gpd.GeoDataFrame(
        geometry=[segs([(-20, 0), (120, 0)]).geometry.iloc[0].buffer(10)], crs="EPSG:9377"
    )
    net = NET.assign(sources="original")
    figs = sf.make_figures(
        pkg, L, AX, net, polys, CFG | {"figure_window_m": 100, "examples": {}}, tmp_path
    )
    assert set(figs) == {f"fig{i}" for i in range(1, 8)}
    for k in ("fig1", "fig2", "fig3", "fig4", "fig5", "fig6"):
        assert figs[k]["path"].exists() and figs[k]["path"].stat().st_size > 1000
        assert figs[k]["caption"]
    assert figs["fig7"] is None  # no relocated interchange in the fixture
    assert X0 and Y0


def test_loose_end_caption_is_neutral(tmp_path) -> None:
    L = review_layers()
    pkg = {
        "problemas": sp.build_problemas(L, AX, NET, CFG),
        "correcciones": sp.build_correcciones(L, AX, CFG),
        "decisiones_modelado": empty(tipo=[], origen=[], CODIGO_ID=[], NOMBRE=[]),
        "ediciones_manuales": sp.build_ediciones(None),
    }
    figs = sf.make_figures(
        pkg,
        L,
        AX,
        NET.assign(sources="original"),
        empty(),
        CFG | {"figure_window_m": 100, "examples": {}},
        tmp_path,
    )
    cap = figs["fig2"]["caption"]
    assert "sin tocarla" not in cap  # the end may overshoot the other line
    assert "queda a 2,0 m" in cap
