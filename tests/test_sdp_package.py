"""SDP package (docs/briefs/sdp-eje-vial-package-design.md) on small synthetic layouts,
EPSG:9377 metres."""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point

from bogota_syntax import sdp_package as sp

X0, Y0 = 4_880_000, 2_070_000
WKT = (Path(__file__).parent / "fixtures" / "pcs_carmagbog.wkt").read_text().strip()


def axes(*coords, ids=None) -> gpd.GeoDataFrame:
    ids = list(ids) if ids is not None else list(range(len(coords)))
    return gpd.GeoDataFrame(
        {
            "OBJECTID": ids,
            "CODIGO_ID": [f"c{i}" for i in ids],
            "NOMBRE": [f"Avenida {i}" for i in ids],
        },
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in c]) for c in coords],
        crs="EPSG:9377",
    )


def points(*xy, **cols) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(cols, geometry=[Point(X0 + x, Y0 + y) for x, y in xy], crs="EPSG:9377")


def segs(*coords, **cols) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        cols,
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in c]) for c in coords],
        crs="EPSG:9377",
    )


# ── task 1: keys and CRS ──────────────────────────────────────────────────────


def test_attach_keys_nearest_within_tolerance() -> None:
    ax = axes([(0, 0), (100, 0)], [(0, 50), (100, 50)], ids=[7, 8])
    out = sp.attach_keys(points((50, 0.3)), ax, key_m=1)
    assert out["OBJECTID"].iloc[0] == 7
    assert out["NOMBRE"].iloc[0] == "Avenida 7"


def test_attach_keys_unmatched_keeps_row_null() -> None:
    ax = axes([(0, 0), (100, 0)], ids=[7])
    out = sp.attach_keys(points((50, 5), (50, 0)), ax, key_m=1)
    assert len(out) == 2
    assert out["OBJECTID"].isna().iloc[0]
    assert out["OBJECTID"].iloc[1] == 7


def test_attach_keys_second_feature_for_crossing() -> None:
    ax = axes([(0, 0), (100, 0)], [(50, -50), (50, 50)], ids=[3, 4])
    out = sp.attach_keys(points((50, 0)), ax, key_m=1, second=True)
    assert {out["OBJECTID"].iloc[0], out["OBJECTID_2"].iloc[0]} == {3, 4}


def test_attach_keys_line_start() -> None:
    ax = axes([(0, 0), (100, 0)], [(0, 80), (100, 80)], ids=[1, 2])
    out = sp.attach_keys(segs([(100, 0), (100, 80)]), ax, key_m=1, at="start")
    assert out["OBJECTID"].iloc[0] == 1


def test_round_trip_under_1cm() -> None:
    ax = axes([(0, 0), (100, 0)], [(0, 50), (300, 900)], [(-2000, 10), (5000, 4000)])
    assert sp.round_trip_error_m(ax, WKT) < 0.01


# ── task 2: problemas and correcciones ────────────────────────────────────────

CFG = {"key_m": 1, "end_match_m": 0.01}


def empty(**cols) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(cols, geometry=[], crs="EPSG:9377")


def review_layers(**over) -> dict[str, gpd.GeoDataFrame]:
    """One case of everything. Axes: 0 runs (0,0)-(100,0); 1 runs (0,50)-(100,50);
    2 runs (50,-50)-(50,100) and crosses both."""
    L = {
        "snaps": segs([(100, 0), (102, 0)], snap_m=[2.0], to=["line"]),
        "crossings": points((50, 0)),
        "removed": segs([(0, 50), (10, 50)], [(20, 50), (60, 50)], why=["stub", "duplicate"]),
        "dead_ends_classified": points(
            (0, 0),
            (100, 50),
            (50, 100),
            (50, -50),
            (30, 50),
            status=["critical"] * 4 + ["corridor_end"],
        ),
        "dead_ends_final": points((50, -50), (30, 50), status=["critical", "corridor_end"]),
        "extensions": segs([(0, 0), (-20, 0)], ext_tol_m=[20.0], added_m=[20.0]),
        "connectors": segs([(100, 50), (130, 50)], kind=["line"], length_m=[30.0]),
    }
    L["pairs"] = empty(gap_m=[])
    L.update(over)
    return L


AX = axes([(0, 0), (100, 0)], [(0, 50), (100, 50)], [(50, -50), (50, 100)])
NET = segs([(0, 0), (100, 0)], [(500, 500), (600, 500)])


def test_each_source_layer_maps_to_its_tipo() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    got = pr.groupby("tipo").size().to_dict()
    assert got == {
        "extremo_suelto": 1,
        "cruce_sin_nodo": 1,
        "tramo_corto": 1,
        "tramo_duplicado": 1,
        "discontinuidad": 4,
        "linea_aislada": 1,
    }
    assert set(pr.columns) >= {
        "tipo",
        "estado",
        "correccion",
        "distancia_m",
        "longitud_m",
        *sp.KEYS,
        "OBJECTID_2",
    }
    cruce = pr[pr.tipo == "cruce_sin_nodo"].iloc[0]
    assert {cruce.OBJECTID, cruce.OBJECTID_2} == {0, 2}
    assert pr.loc[pr.tipo == "extremo_suelto", "distancia_m"].iloc[0] == 2.0


def test_discontinuidad_fixed_by_extension() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    row = pr[(pr.tipo == "discontinuidad") & (pr.geometry.x == X0)].iloc[0]
    assert (row.estado, row.correccion, row.distancia_m) == ("corregido", "extension", 20.0)


def test_discontinuidad_still_open() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    row = pr[(pr.tipo == "discontinuidad") & (pr.geometry.y == Y0 - 50)].iloc[0]
    assert (row.estado, row.correccion) == ("abierto", "")


def test_discontinuidad_fixed_elsewhere() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    row = pr[(pr.tipo == "discontinuidad") & (pr.geometry.y == Y0 + 100)].iloc[0]
    assert (row.estado, row.correccion) == ("corregido", "reubicacion_o_edicion")


def test_pair_fixes_both_ends() -> None:
    L = review_layers(
        pairs=segs([(0, 0), (100, 50)], gap_m=[111.8]), extensions=empty(ext_tol_m=[], added_m=[])
    )
    pr = sp.build_problemas(L, AX, NET, CFG)
    fixed = pr[(pr.tipo == "discontinuidad") & (pr.correccion == "union")]
    assert len(fixed) == 2


def test_isolated_line_is_open() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    row = pr[pr.tipo == "linea_aislada"].iloc[0]
    assert (row.estado, row.longitud_m) == ("abierto", 100.0)


def test_empty_layers_keep_schema() -> None:
    full = sp.build_correcciones(review_layers(), AX, CFG)
    none = sp.build_correcciones(review_layers(connectors=empty(kind=[], length_m=[])), AX, CFG)
    assert list(none.columns) == list(full.columns)
    assert (none.tipo == "conector").sum() == 0
    assert full.groupby("tipo").size().to_dict() == {"ajuste": 1, "extension": 1, "conector": 1}
    assert full.loc[full.tipo == "conector", "OBJECTID"].iloc[0] == 1


def test_open_rows_first() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    assert pr.estado.iloc[0] == "abierto"
    assert (pr.estado == "abierto").sum() == 2


# ── task 3: modelling layers, GeoPackage, run ─────────────────────────────────


def test_relocated_centre_gets_interchange_keys_and_origin() -> None:
    inter = gpd.GeoDataFrame(
        {
            "CODIGO_ID": ["1084", "2000"],
            "NOMBRE": ["Enlace A", "Enlace B"],
            "action": ["relocate", "relocate (rule)"],
        },
        geometry=[
            Point(X0, Y0).buffer(50),
            Point(X0 + 500, Y0).buffer(50),
        ],
        crs="EPSG:9377",
    )
    L = {
        "junctions_merged": points((900, 900)),
        "centres": points((10, 5), (505, 0), polygon=[0, 1]),
        "interchanges": inter,
    }
    d = sp.build_decisiones(L)
    rel = d[d.tipo == "reubicacion_enlace"].set_index("CODIGO_ID")
    assert rel.loc["1084", "origen"] == "revision_manual"
    assert rel.loc["2000", "origen"] == "regla"
    assert rel.loc["1084", "NOMBRE"] == "Enlace A"
    assert (d.tipo == "fusion_nodos").sum() == 1


def test_no_edits_file_gives_empty_layer() -> None:
    e = sp.build_ediciones(None)
    assert len(e) == 0
    assert {"edicion", "longitud_m", *sp.KEYS} <= set(e.columns)


def test_edits_labelled_in_spanish() -> None:
    e = segs(
        [(0, 0), (10, 0)],
        [(0, 5), (30, 5)],
        edit=["add", "remove"],
        OBJECTID=[1.0, 2.0],
        CODIGO_ID=["a", "b"],
        NOMBRE=["x", "y"],
    )
    out = sp.build_ediciones(e)
    assert out.edicion.tolist() == ["agregada"]  # removed lines are not in the layer
    assert out.longitud_m.tolist() == [10.0]
    assert out.OBJECTID.tolist() == [1]
    assert sp.removed_edits(e) == 1


def test_stale_review_stops_run(tmp_path) -> None:
    import os

    interim = tmp_path / "data" / "interim"
    (interim / "foreground").mkdir(parents=True)
    review = interim / "foreground" / "review.gpkg"
    review.write_text("x")
    parquet = interim / "sdp_eje_vial.parquet"
    parquet.write_text("x")
    os.utime(review, (1_000, 1_000))
    import pytest

    with pytest.raises(RuntimeError, match="bogota-syntax foreground"):
        sp.check_fresh(review, [parquet])


def test_gpkg_written_in_sdp_crs(tmp_path) -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    co = sp.build_correcciones(review_layers(), AX, CFG)
    pkg = {
        "eje_vial_corregido": sp.build_corregida(NET.assign(sources="original", OBJECTID=[1, 2])),
        "problemas": pr,
        "correcciones": co,
        "decisiones_modelado": sp.build_decisiones(
            {
                "junctions_merged": points((1, 1)),
                "centres": empty(polygon=[]),
                "interchanges": empty(CODIGO_ID=[], NOMBRE=[], action=[]),
            }
        ),
        "ediciones_manuales": sp.build_ediciones(None),
    }
    path = tmp_path / "eje_vial_revision.gpkg"
    sp.write_gpkg(pkg, path, WKT)
    import pyogrio

    assert [n for n, _ in pyogrio.list_layers(path)] == [*sp.LAYERS, "layer_styles"]
    assert "CarMAGBOG" in pyogrio.read_info(path, layer="problemas")["crs"]
    back = gpd.read_file(path, layer="problemas")
    assert len(back) == len(pr)


def test_counts_names() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    n = sp.counts(
        {
            "problemas": pr,
            "correcciones": empty(tipo=[]),
            "decisiones_modelado": empty(tipo=[], origen=[]),
            "ediciones_manuales": sp.build_ediciones(None),
        }
    )
    assert n["n_discontinuidad"] == 4
    assert n["n_discontinuidad_abierto"] == 1
    assert n["n_abierto"] == 2
    assert n["n_sin_clave"] == int(pr.OBJECTID.isna().sum())
    assert n["n_edicion_agregada"] == 0


def test_rows_at_city_limit_are_marked() -> None:
    pr = points((0, 0), (0, 50), estado=["abierto", "abierto"], tipo=["discontinuidad"] * 2)
    limit = segs([(-100, 1), (100, 1)])
    out = sp.mark_limit(pr, limit, limit_m=5)
    assert out.observacion.tolist() == [sp.LIMIT, ""]
    assert out.estado.tolist() == ["sin_cambio", "abierto"]  # at the limit = assumed correct
    assert "se asume correcto" in sp.LIMIT


# ── task 5: note and LEEME ────────────────────────────────────────────────────

TEMPLATES = Path(sp.__file__).parent / "templates"


def test_render_fills_every_placeholder(tmp_path) -> None:
    t = tmp_path / "t.md"
    t.write_text("$a y $b", encoding="utf-8")
    assert sp.render(t, {"a": 1, "b": 2}) == "1 y 2"


def test_render_missing_value_raises(tmp_path) -> None:
    import pytest

    t = tmp_path / "t.md"
    t.write_text("$a y $b", encoding="utf-8")
    with pytest.raises(KeyError):
        sp.render(t, {"a": 1})


def test_note_has_no_bare_digits_outside_placeholders() -> None:
    import re

    allowed = ["Decreto 555 de 2021", "CC BY 4.0", "ADR-0012", "OBJECTID_2"]
    for name in ("nota_metodologica.md", "LEEME.txt"):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        for a in allowed:
            text = text.replace(a, "")
        text = re.sub(r"\$\{?\w+\}?", "", text)
        assert not re.search(r"\d", text), f"{name}: {re.findall(r'.{20}\d.{20}', text)}"


def test_note_values_cover_both_templates() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG).assign(observacion="")
    pkg = {
        "problemas": pr,
        "correcciones": empty(tipo=[]),
        "decisiones_modelado": empty(tipo=[], origen=[]),
        "ediciones_manuales": sp.build_ediciones(None),
    }
    n = sp.counts(pkg) | {
        "n_eje_vial": 3,
        "n_eje_sin_codigo": 0,
        "n_segmentos": 2,
        "km_red": "0,2",
        "n_piezas": 2,
        "n_piezas_analisis": 2,
        "n_edicion_retirada": 0,
    }
    figs = {f"fig{i}": None for i in range(1, 8)}
    manifest = {"sdp_eje_vial": {}, "sdp_red_infraestructura_vial": {}}
    v = sp.note_values(n, figs, manifest, {"contacto": None})
    for name in ("nota_metodologica.md", "LEEME.txt"):
        out = sp.render(TEMPLATES / name, v)
        assert "$" not in out
    assert "Sin casos" in v["fig7"]
    assert "(por completar)" in v["contacto"]


def test_open_cases_split_without_double_counting() -> None:
    pr = points(
        (0, 0),
        (0, 1),
        (0, 2),
        (0, 3),
        tipo=["discontinuidad", "discontinuidad", "discontinuidad", "linea_aislada"],
        estado=["sin_cambio", "abierto", "abierto", "abierto"],
        observacion=[sp.LIMIT, "", "", ""],
        correccion="",
        OBJECTID=[1, 2, 3, 4],
    )
    n = sp.counts(
        {
            "problemas": pr,
            "correcciones": empty(tipo=[]),
            "decisiones_modelado": empty(tipo=[], origen=[]),
            "ediciones_manuales": sp.build_ediciones(None),
        }
    )
    assert (n["n_abierto_faltante"], n["n_limite"], n["n_linea_aislada_abierto"]) == (
        2,
        1,
        1,
    )


def test_thousands_with_a_dot() -> None:
    assert sp.miles(1149) == "1.149"
    assert sp.miles(256) == "256"


# ── final review fixes ────────────────────────────────────────────────────────


def test_empty_layers_written_with_their_schema(tmp_path) -> None:
    import pyogrio

    pkg = {
        "eje_vial_corregido": sp.build_corregida(
            NET.assign(sources="original", OBJECTID=[1, 2]).iloc[:0]
        ),
        "problemas": sp.build_problemas(review_layers(), AX, NET, CFG).iloc[:0],
        "correcciones": sp.build_correcciones({k: empty() for k in sp.FIX_LAYERS}, AX, CFG),
        "decisiones_modelado": sp.build_decisiones(
            {
                "junctions_merged": empty(),
                "centres": empty(polygon=[]),
                "interchanges": empty(CODIGO_ID=[], NOMBRE=[], action=[]),
            }
        ),
        "ediciones_manuales": sp.build_ediciones(None),
    }
    path = tmp_path / "x.gpkg"
    sp.write_gpkg(pkg, path, WKT)
    corr = pyogrio.read_info(path, layer="eje_vial_corregido")
    assert corr["geometry_type"] == "LineString"
    assert dict(zip(corr["fields"], corr["dtypes"], strict=True))["origen"] == "object"
    for name, geom in [
        ("problemas", "Point"),
        ("correcciones", "LineString"),
        ("decisiones_modelado", "Point"),
        ("ediciones_manuales", "LineString"),
    ]:
        info = pyogrio.read_info(path, layer=name)
        assert info["geometry_type"] == geom, name
        types = dict(zip(info["fields"], info["dtypes"], strict=True))
        assert types[next(k for k in ("tipo", "edicion") if k in types)] == "object", name
        if "NOMBRE" in types:
            assert types["NOMBRE"] == "object", name


# ── errors-only network for the SDP ───────────────────────────────────────────


def test_crossings_are_kept_as_possible_bridges() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    c = pr[pr.tipo == "cruce_sin_nodo"].iloc[0]
    assert (c.estado, c.correccion) == ("sin_cambio", "")
    assert "posible puente" in c.observacion


def test_mark_limit_keeps_existing_notes() -> None:
    pr = points((0, 0), (0, 50), observacion=["posible puente", ""])
    out = sp.mark_limit(pr, segs([(-100, 1), (100, 1)]), limit_m=5)
    assert out.observacion.tolist() == [f"posible puente; {sp.LIMIT}", ""]


def test_counts_sin_cambio() -> None:
    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    n = sp.counts(
        {
            "problemas": pr,
            "correcciones": empty(tipo=[]),
            "decisiones_modelado": empty(tipo=[], origen=[]),
            "ediciones_manuales": sp.build_ediciones(None),
        }
    )
    assert (n["n_cruce_sin_nodo_corregido"], n["n_cruce_sin_nodo_sin_cambio"]) == (0, 1)
    assert n["n_sin_cambio"] == 1
    assert n["n_corregido"] == n["n_problemas"] - n["n_abierto"] - n["n_sin_cambio"]


def test_build_corregida_keeps_source_fields_and_says_origin_in_spanish() -> None:
    net = AX.assign(sources=["original", "extension,original", "connector"])
    out = sp.build_corregida(net)
    assert out.origen.tolist() == ["original", "extension, original", "conector"]
    assert {"OBJECTID", "CODIGO_ID", "NOMBRE", "longitud_m"} <= set(out.columns)
    assert "sources" not in out.columns
    assert out.longitud_m.tolist() == [100.0, 100.0, 150.0]


def test_links_point_to_a_fixed_commit() -> None:
    url = sp.link("https://github.com/x/y", "abc123", "src/a.py")
    assert url == "https://github.com/x/y/blob/abc123/src/a.py"


def test_open_ends_inside_an_interchange_are_marked() -> None:
    pr = points(
        (0, 0),
        (500, 0),
        estado=["abierto", "abierto"],
        tipo=["discontinuidad"] * 2,
        observacion=["", ""],
        OBJECTID=[1, 2],
        correccion="",
    )
    inter = gpd.GeoDataFrame(geometry=[Point(X0, Y0).buffer(30)], crs="EPSG:9377")
    out = sp.mark_enlace(pr, inter)
    assert out.observacion.iloc[0].startswith("dentro de un enlace vial")
    assert out.observacion.iloc[1] == ""
    n = sp.counts(
        {
            "problemas": out,
            "correcciones": empty(tipo=[]),
            "decisiones_modelado": empty(tipo=[], origen=[]),
            "ediciones_manuales": sp.build_ediciones(None),
        }
    )
    assert (n["n_abierto_enlace"], n["n_abierto_faltante"]) == (1, 1)


def test_gpkg_carries_a_default_qgis_style_per_layer(tmp_path) -> None:
    import sqlite3

    pr = sp.build_problemas(review_layers(), AX, NET, CFG)
    pkg = {
        "eje_vial_corregido": sp.build_corregida(NET.assign(sources="original", OBJECTID=[1, 2])),
        "problemas": pr,
        "correcciones": sp.build_correcciones(review_layers(), AX, CFG),
        "decisiones_modelado": sp.build_decisiones(
            {
                "junctions_merged": points((1, 1)),
                "centres": empty(polygon=[]),
                "interchanges": empty(CODIGO_ID=[], NOMBRE=[], action=[]),
            }
        ),
        "ediciones_manuales": sp.build_ediciones(None),
    }
    path = sp.write_gpkg(pkg, tmp_path / "x.gpkg", WKT)
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT f_table_name, f_geometry_column, useAsDefault, styleQML FROM layer_styles"
        ).fetchall()
        registered = db.execute(
            "SELECT data_type FROM gpkg_contents WHERE table_name = 'layer_styles'"
        ).fetchone()
    assert sorted(r[0] for r in rows) == sorted(sp.LAYERS)
    assert all(r[1] and r[2] == 1 and r[3].startswith("<!DOCTYPE qgis") for r in rows)
    assert registered == ("attributes",)


def test_contact_comes_from_an_ignored_local_file(tmp_path) -> None:
    (tmp_path / "config").mkdir()
    assert sp.contacto(tmp_path, {"contacto": None}) is None
    (tmp_path / "config" / "contacto.local.txt").write_text("Ana, ana@x.org\n", encoding="utf-8")
    assert sp.contacto(tmp_path, {"contacto": None}) == "Ana, ana@x.org"
    assert sp.contacto(tmp_path, {"contacto": "B"}) == "B"  # config wins when set
