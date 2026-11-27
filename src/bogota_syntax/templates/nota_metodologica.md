# Eje Vial del POT: vacíos de geometría y cómo los corregimos

Nota metodológica · $fecha

## Qué es y qué no es

Este paquete señala los puntos donde el Eje Vial que publica la Secretaría Distrital de Planeación (SDP) no forma una red conectada, y muestra cómo los corregimos para un análisis de red. Cada problema está ubicado y asociado al `OBJECTID` de la línea publicada, para revisarlo uno por uno.

No es una versión oficial ni reemplaza al Eje Vial. Las correcciones son inferencias geométricas, no levantamientos en campo.

Revisamos las $n_eje_vial líneas del Eje Vial del Plan de Ordenamiento Territorial (POT, Decreto 555 de 2021), versión del $fecha_eje, junto con los polígonos de la Red de Infraestructura Vial Arterial, versión del $fecha_poligonos. Encontramos $n_problemas problemas. Corregimos $n_corregido y quedan $n_abierto abiertos.

$fig1

## Limitaciones

- **Puentes y deprimidos.** Aún no distinguimos un puente de un cruce a nivel. Algunos cruces sin nodo pueden estar bien en el Eje Vial.
- **Vías proyectadas.** No usamos `ESTADO_VIA`: una vía proyectada cuenta como construida, y eso puede hacer que un extremo parezca una discontinuidad.
- **Inferencia, no campo.** Las correcciones siguen reglas geométricas y los polígonos del POT. Nada se verificó en terreno.
- **Decisiones de modelado.** La capa `decisiones_modelado` y las ediciones manuales responden a nuestro análisis de red, no a errores del Eje Vial. Las incluimos para que el proceso sea transparente.
- **Límite del Distrito.** El Eje Vial termina en el límite de Bogotá. De los casos abiertos, $n_abierto_limite terminan justo ahí y probablemente no son tramos faltantes.
- **Códigos.** $n_eje_sin_codigo de las $n_eje_vial líneas publicadas no tienen `CODIGO_ID`. Esas filas se identifican solo por `OBJECTID`.

## Método

Primero clasificamos, después corregimos. Cada corrección se aplica solo donde una regla la justifica; el resto queda como fue publicado.

Los polígonos del POT deciden si un corredor continúa. Si el extremo de una línea cae en un polígono que toca al menos otros dos, el corredor sigue y la línea también debería seguir: la extendemos o la conectamos. Si no, el extremo se respeta.

Los extremos sueltos se ajustan a la línea más cercana, los cruces sin nodo se dividen y los tramos cortos o duplicados sin salida se eliminan. Los parámetros y el método completo están documentados en el repositorio bogota-syntax (ADR-0012).

## Resultados

$tabla

### Extremo suelto

$fig2

### Cruce sin nodo

$fig3

### Discontinuidad del corredor

De las $n_discontinuidad discontinuidades, $n_discontinuidad_extension se resolvieron extendiendo la línea, $n_discontinuidad_union uniendo dos extremos enfrentados, $n_discontinuidad_conector con un conector y $n_discontinuidad_reubicacion_o_edicion al simplificar un enlace o con una edición manual.

$fig4

### Tramo corto o duplicado

$fig5

### Casos abiertos: los que más conviene revisar

De los $n_abierto casos abiertos, $n_abierto_faltante parecen tramos que faltan en el Eje Vial, $n_abierto_limite terminan en el límite del Distrito y en $n_linea_aislada_abierto la línea queda aislada del resto de la red. No los completamos: no hay forma de saber el trazado sin la SDP.

$fig6

### Decisiones de modelado

Para el análisis de red llevamos $n_reubicacion enlaces viales a un solo punto de encuentro: $n_reubicacion_revision por revisión manual y $n_reubicacion_regla por una regla ajustada a esa revisión. También fusionamos $n_fusion_nodos nodos muy cercanos entre sí y redibujamos a mano $km_editados km de líneas ($n_edicion_agregada agregadas, $n_edicion_retirada retiradas). Además simplificamos el trazado (menos vértices, sin zigzags), lo que no se muestra en las capas. Nada de esto es un error del Eje Vial.

$fig7

## Cómo leer las capas

`eje_vial_revision.gpkg`, en el sistema de coordenadas del Eje Vial publicado (PCS_CarMAGBOG):

- `problemas` (puntos): `tipo`, `estado` (corregido o abierto), `correccion`, `distancia_m`, `longitud_m`, `observacion` y la línea publicada donde está (`OBJECTID`, `CODIGO_ID`, `NOMBRE`; en los cruces también `OBJECTID_2`). Los abiertos van primero.
- `correcciones` (líneas): lo que agregamos o movimos (`ajuste`, `union`, `extension`, `conector`).
- `decisiones_modelado` (puntos): `fusion_nodos` y `reubicacion_enlace`.
- `ediciones_manuales` (líneas): `agregada` o `retirada`.

## Licencia y cómo repetirlo

Licencia CC BY 4.0. Fuente: SDP, Eje Vial y Red de Infraestructura Vial Arterial del POT. Correcciones: proyecto bogota-syntax (código abierto, licencia MIT).

Cuando la SDP publique una nueva versión, el paquete se rehace con:

```bash
uv run bogota-syntax ingest sdp_eje_vial --force
uv run bogota-syntax ingest sdp_red_infraestructura_vial --force
uv run bogota-syntax foreground
uv run bogota-syntax sdp-package
```

Lo que requiere una persona: decisiones de enlaces que ya no coinciden, ediciones manuales que ya no coinciden y casos nuevos para revisar. El programa reporta los tres.
