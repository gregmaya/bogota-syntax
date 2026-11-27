# Eje Vial del POT: vacíos de geometría y una red corregida

Nota metodológica · $fecha

## Qué es y qué no es

Este paquete señala los puntos donde el Eje Vial que publica la Secretaría Distrital de Planeación (SDP) no forma una red conectada, muestra cómo los corregí y entrega la red corregida, para que la SDP decida qué incorporar y qué no. Cada problema está ubicado y asociado al `OBJECTID` de la línea publicada más cercana; los que no tienen ninguna línea a menos de $key_m m quedan sin `OBJECTID` ($n_sin_clave en total).

No es una versión oficial ni reemplaza al Eje Vial. Las correcciones son inferencias geométricas, no levantamientos en campo.

Revisé las $n_eje_vial líneas del Eje Vial del Plan de Ordenamiento Territorial (POT, Decreto 555 de 2021), versión del $fecha_eje, junto con los polígonos de la Red de Infraestructura Vial Arterial, versión del $fecha_poligonos. Encontré $n_problemas problemas: corregí $n_corregido, $n_abierto quedan abiertos y $n_sin_cambio son cruces que dejé como están porque pueden ser puentes.

$fig1

## Qué contiene

`eje_vial_revision.gpkg`, en el sistema de coordenadas del Eje Vial publicado (PCS_CarMAGBOG):

- **`eje_vial_corregido` (líneas): la red corregida, el punto de partida que sugiero.** Son $n_segmentos segmentos y $km_red km, con todos los campos del Eje Vial tal como se publican, más `origen` (qué produjo cada geometría: `original`, `union`, `extension` o `conector`) y `longitud_m`. Solo incluye correcciones de errores: no divide los cruces sin nodo y no incluye mis decisiones de modelado.
- `problemas` (puntos): cada problema con `tipo`, `estado` (`corregido`, `abierto` o `sin_cambio`), `correccion`, `distancia_m`, `longitud_m`, `observacion` y la línea publicada donde está (`OBJECTID`, `CODIGO_ID`, `NOMBRE`; en los cruces también `OBJECTID_2`). Los abiertos van primero.
- `correcciones` (líneas): lo que agregué o moví (`ajuste`, `union`, `extension`, `conector`).
- `decisiones_modelado` (puntos) y `ediciones_manuales` (líneas): lo que hice solo para mi análisis de red. Los incluyo por transparencia; no sugiero añadirlos al Eje Vial.

## Limitaciones

- **Puentes y deprimidos.** No distingo un puente de un cruce a nivel. Por eso en la red corregida no divido ninguno de los $n_cruce_sin_nodo cruces sin nodo: los marco para que la SDP confirme cuáles son cruces a nivel. En mi análisis de red sí los divido.
- **Continuidad.** Aunque no divido los cruces, la red corregida queda en $n_piezas piezas conectadas entre sí; mi red de análisis, con los cruces divididos, queda en $n_piezas_analisis.
- **Vías proyectadas.** No uso `ESTADO_VIA`: una vía proyectada cuenta como construida, y eso puede hacer que un extremo parezca una discontinuidad.
- **Inferencia, no campo.** Las correcciones siguen reglas geométricas y los polígonos del POT. Nada se verificó en terreno.
- **Límite del Distrito.** El Eje Vial termina en el límite de Bogotá. De los casos abiertos, $n_abierto_limite terminan justo ahí y probablemente no son tramos faltantes.
- **Códigos.** $n_eje_sin_codigo de las $n_eje_vial líneas publicadas no tienen `CODIGO_ID`. Esas filas se identifican solo por `OBJECTID`.

## Método

**Primero clasifico, después corrijo. Cada corrección se aplica solo donde una regla la justifica; el resto queda como fue publicado.**

Los polígonos del POT deciden si un corredor continúa. Si el extremo de una línea cae en un polígono que toca al menos otros dos, el corredor sigue y la línea también debería seguir: la extiendo o la conecto. Si no, respeto el extremo.

Los extremos sueltos los ajusto a la línea más cercana y los tramos cortos o duplicados sin salida los elimino. Los parámetros y el método completo están en el repositorio [bogota-syntax]($repo) ([ADR-0012]($adr)).

## Resultados

$tabla

### Extremo suelto

$fig2

### Cruce sin nodo

$fig3

### Discontinuidad del corredor

De las $n_discontinuidad discontinuidades, resolví $n_discontinuidad_extension extendiendo la línea, $n_discontinuidad_union uniendo dos extremos enfrentados y $n_discontinuidad_conector con un conector.

$fig4

### Tramo corto o duplicado

$fig5

### Casos abiertos: los que más conviene revisar

De los $n_abierto casos abiertos, $n_abierto_faltante parecen tramos que faltan en el Eje Vial, $n_abierto_limite terminan en el límite del Distrito, $n_abierto_enlace quedan dentro de un enlace vial y en $n_linea_aislada_abierto la línea queda aislada del resto de la red. No los completé: no hay forma de saber el trazado sin la SDP. Los que quedan dentro de un enlace sí los resolví en mi análisis de red, con una decisión de modelado (ver abajo).

$fig6

### Decisiones de modelado (solo para mi análisis de red)

Por transparencia incluyo también lo que hice para mi propio análisis. Mi objetivo es una continuidad espacial (no vial) que se pueda rutear. Para eso llevé $n_reubicacion enlaces viales a un solo punto de encuentro ($n_reubicacion_revision por revisión manual y $n_reubicacion_regla por una regla ajustada a esa revisión), fusioné $n_fusion_nodos nodos muy cercanos entre sí, dividí los cruces sin nodo, simplifiqué el trazado (menos vértices, sin zigzags) y edité a mano algunos lugares: retiré $n_edicion_retirada líneas y dibujé $n_edicion_agregada. Nada de esto está en la red corregida, y no sugiero añadirlo al Eje Vial: son decisiones para mi propósito, no errores de los datos.

$fig7

## Preguntas para la SDP

- ¿Para qué se usa el Eje Vial? Si no está pensado como una red conectada y ruteable, varios de estos problemas no lo son para su propósito.
- ¿Hay un registro de puentes y deprimidos? Permitiría saber cuáles cruces sin nodo están bien.
- ¿Qué significan los valores de `ESTADO_VIA`? Permitiría separar las vías construidas de las proyectadas.
- ¿Les sirve la red corregida como punto de partida, o prefieren solo la lista de problemas?

## Código utilizado

Todo el código es abierto (licencia MIT) y está en [bogota-syntax]($repo). Los enlaces apuntan a la versión exacta que produjo este paquete (commit `$commit`):

$codigo

## Licencia y cómo repetirlo

Licencia CC BY 4.0. Fuente: SDP, Eje Vial y Red de Infraestructura Vial Arterial del POT. Correcciones: proyecto bogota-syntax.

Cuando la SDP publique una nueva versión, el paquete se rehace con:

```bash
uv run bogota-syntax ingest sdp_eje_vial --force
uv run bogota-syntax ingest sdp_red_infraestructura_vial --force
uv run bogota-syntax foreground
uv run bogota-syntax sdp-package
```

Lo que requiere una persona: decisiones de enlaces que ya no coinciden, ediciones manuales que ya no coinciden y casos nuevos para revisar. El programa reporta los tres.
