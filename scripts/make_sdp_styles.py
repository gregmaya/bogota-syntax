"""Write the QGIS styles of the SDP package (src/bogota_syntax/templates/styles/*.qml).

Run with QGIS's own Python, not the project's environment:

    QT_QPA_PLATFORM=offscreen /Applications/QGIS-<version>.app/Contents/MacOS/python \
        scripts/make_sdp_styles.py

`bogota-syntax sdp-package` embeds the files as each layer's default style in the
GeoPackage, so QGIS opens the layers with them. Colours match the figures
(`sdp_figures.TYPE_COLOURS`, `FIX`, `OPEN`, `GREY`); change both together.
"""

from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsLineSymbol,
    QgsMapLayer,
    QgsMarkerSymbol,
    QgsRuleBasedRenderer,
    QgsVectorLayer,
)

OUT = Path(__file__).resolve().parents[1] / "src" / "bogota_syntax" / "templates" / "styles"
GREY, FIX, OPEN = "#8c8c8c", "#e66100", "#5d3a9b"
TYPES = [  # (tipo values, label, colour), as in sdp_figures.TYPE_COLOURS / TYPE_LABELS
    (("extremo_suelto",), "Extremo suelto", "#0072b2"),
    (("cruce_sin_nodo",), "Cruce sin nodo (posible puente)", "#009e73"),
    (("tramo_corto", "tramo_duplicado"), "Tramo corto o duplicado", "#cc79a7"),
    (("discontinuidad",), "Discontinuidad del corredor", "#e69f00"),
    (("linea_aislada",), "Línea aislada", OPEN),
]


def dot(colour: str, size: float = 2.2) -> QgsMarkerSymbol:
    return QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": colour, "size": str(size), "outline_style": "no"}
    )


def ring(colour: str, size: float = 6.0) -> QgsMarkerSymbol:
    return QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "0,0,0,0",
            "outline_color": colour,
            "outline_width": "0.7",
            "size": str(size),
        }
    )


def line(colour: str, width: float, dash: bool = False) -> QgsLineSymbol:
    props = {"line_color": colour, "line_width": str(width), "capstyle": "round"}
    if dash:
        props["line_style"] = "dash"
    return QgsLineSymbol.createSimple(props)


def ruled(geom: str, rules: list[tuple[str, str, object]]) -> QgsRuleBasedRenderer:
    """Rule-based renderer from (label, filter, symbol), drawn in list order."""
    root = QgsRuleBasedRenderer.Rule(None)
    for label, expr, symbol in rules:
        root.appendChild(QgsRuleBasedRenderer.Rule(symbol, 0, 0, expr, label))
    return QgsRuleBasedRenderer(root)


def quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def save(name: str, geom: str, fields: str, renderer) -> None:
    lyr = QgsVectorLayer(f"{geom}?crs=EPSG:9377&{fields}", name, "memory")
    lyr.setRenderer(renderer)
    path = OUT / f"{name}.qml"
    msg, ok = lyr.saveNamedStyle(str(path), QgsMapLayer.StyleCategory.Symbology)
    if not ok:
        raise RuntimeError(f"{name}: {msg}")
    print(path.relative_to(OUT.parents[3]))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rules = [
        (label, f'"estado" <> \'abierto\' AND "tipo" IN ({quoted(v)})', dot(c))
        for v, label, c in TYPES
    ]
    rules.append(("Abierto (requiere revisión de la SDP)", "\"estado\" = 'abierto'", ring(OPEN)))
    save("problemas", "Point", "field=tipo:string&field=estado:string", ruled("Point", rules))

    save(
        "eje_vial_corregido",
        "LineString",
        "field=origen:string",
        ruled(
            "LineString",
            [
                ("Como se publicó", "\"origen\" = 'original'", line(GREY, 0.4)),
                (
                    "Segmento con geometría nueva (unión, extensión o conector)",
                    "\"origen\" <> 'original'",
                    line(FIX, 0.6),
                ),
            ],
        ),
    )
    save(
        "correcciones",
        "LineString",
        "field=tipo:string",
        ruled("LineString", [("Corrección", "TRUE", line(FIX, 0.8))]),
    )
    save(
        "decisiones_modelado",
        "Point",
        "field=tipo:string",
        ruled(
            "Point",
            [
                (
                    "Fusión de nodos (solo análisis de red)",
                    "\"tipo\" = 'fusion_nodos'",
                    dot("#b0b0b0", 1.6),
                ),
                (
                    "Enlace reubicado (solo análisis de red)",
                    "\"tipo\" = 'reubicacion_enlace'",
                    ring("#606060", 4.0),
                ),
            ],
        ),
    )
    save(
        "ediciones_manuales",
        "LineString",
        "field=edicion:string",
        ruled(
            "LineString",
            [("Dibujada a mano (solo análisis de red)", "TRUE", line("#404040", 0.5, dash=True))],
        ),
    )


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    try:
        main()
    finally:
        app.exitQgis()
