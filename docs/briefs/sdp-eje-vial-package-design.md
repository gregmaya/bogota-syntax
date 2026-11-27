# Design: the Eje Vial package for the SDP

- **Status:** approved by Gregorio 2026-11-26; plan in [sdp-eje-vial-package-plan.md](sdp-eje-vial-package-plan.md)
- **Date:** 2026-11-26
- **Builds on:** [the brief](sdp-eje-vial-package.md), ADR-0012, ADR-0013 (licence, Proposed)

## Intent

Give the Secretaría Distrital de Planeación (SDP) a small package, in Spanish, that shows where the published Eje Vial is not a connected network, how each gap was fixed, and what the fixes can't be trusted for. It should be simple to open in QGIS or ArcGIS, accurate down to each feature, and useful enough that they can fix their own layer from it.

**Goals:** every problem located and keyed to their `OBJECTID`; their own errors kept apart from our modelling choices; caveats stated before results; every number produced by code.

**Non-goals:** a full corrected network for them to adopt (option c, not chosen); changes to the pipeline's outputs; an English version.

**Anti-goals:** a package that reads as "your data is wrong" for things that are really our analysis choices; a number in the note that the command didn't compute; a large or many-file delivery.

## Approaches considered

- **(a) Errors only.** Cleanest message, but hides the interchange and manual work they may ask about.
- **(b) Errors plus a separate, clearly labelled layer of modelling decisions.** Chosen by Gregorio: complete, and the labelling keeps the two apart.
- **(c) Also the full corrected network.** Most to explain; not needed for them to fix their layer.

## What the package contains

`entrega_sdp_eje_vial_<fecha>/`, three files:

1. **`eje_vial_revision.gpkg`**, in the SDP's own CRS, `PCS_CarMAGBOG`, taken from the raw Eje Vial file's definition. Four layers:

   | Layer | Geometry | One row per | From `review.gpkg` / config |
   | --- | --- | --- | --- |
   | `problemas` | point | problem found in the published data | `snaps`, `crossings`, `removed`, `dead_ends_classified` (critical), `dead_ends_final` (critical) |
   | `correcciones` | line | line added or moved to fix a problem | `snaps`, `pairs`, `extensions`, `connectors` |
   | `decisiones_modelado` | point | place changed for network analysis, not because the data is wrong | `junctions_merged`, `centres` + `interchanges` (relocated only) |
   | `ediciones_manuales` | line | line removed or drawn by hand | `config/foreground_edits.geojson` |

   `problemas` fields: `tipo` (`extremo_suelto`, `cruce_sin_nodo`, `tramo_corto`, `tramo_duplicado`, `discontinuidad`, `linea_aislada`), `estado` (`corregido` / `abierto`), `correccion` (how it was fixed: `ajuste`, `division`, `eliminado`, `union`, `extension`, `conector`, or empty when open), `distancia_m` where it applies, and `OBJECTID`, `CODIGO_ID`, `NOMBRE` of the Eje Vial feature it sits on (a crossing gets `OBJECTID_2` for the second line). The open cases (4 dead ends where a segment is missing from the source, and the isolated line) are `estado = abierto` and listed first in the note.

   `correcciones` and `ediciones_manuales` carry the same keys and `longitud_m`. `decisiones_modelado` carries `tipo` (`fusion_nodos`, `reubicacion_enlace`), the interchange's `CODIGO_ID` / `NOMBRE`, and `origen` (`revision_manual` for a decision from `config/enlace_decisions.csv`, `regla` for the fallback rule).

   Source field names stay as published (rule 6); new fields are in Spanish.

2. **`nota_metodologica.md`** with its figures in `figuras/`, exported to **`nota_metodologica.pdf`** at send time. At most four pages, most of it pictures:
   1. Qué es y qué no es (one paragraph) and **figure 1**.
   2. Limitaciones, first: bridges and overpasses not told apart, so some `cruce_sin_nodo` are not errors; `ESTADO_VIA` ignored, so a planned road can make a dead end look like a discontinuity; fixes are geometric inferences, not field survey; the modelling layer is our choice, not an error.
   3. Método: classify, then correct; the POT arterial polygons tell whether a corridor carries on.
   4. Resultados: one table, problem type × count × fixed / open, then one example per type (figures 2–5), the open cases (figure 6) and the modelling decisions (figure 7).
   5. Cómo leer las capas, licencia y atribución, cómo repetirlo.

   **Figures**, made by the command with matplotlib from the package's own layers (no basemap, so nothing is downloaded and no third-party map data gets in):

   | # | Shows | Form |
   | --- | --- | --- |
   | 1 | The whole city: Eje Vial in grey, problems as points by type, open cases marked | one map |
   | 2 | `extremo_suelto`: an end stopping short of a line, then snapped | before / after, zoomed to ~100 m |
   | 3 | `cruce_sin_nodo`: two lines crossing with no shared point, then split | before / after |
   | 4 | `discontinuidad`: a dead end inside a POT polygon that carries on, then extended or connected; the polygons drawn | before / after |
   | 5 | `tramo_corto` / `tramo_duplicado`: the stub or duplicate removed | before / after |
   | 6 | `abierto`: a missing segment, with the polygon that shows the corridor continues | one panel |
   | 7 | `reubicacion_enlace`: an interchange before and after relocation, labelled as a modelling decision | before / after |

   One drawing style throughout: original lines grey, corrections in one strong colour, open cases in a second, POT polygons as a light fill; a scale bar and the feature's `NOMBRE` in each caption. **Examples are chosen in `config/analysis.yaml`** (`sdp_package.examples`, by `OBJECTID` or `CODIGO_ID` per figure), so Gregorio can pick clear ones in QGIS. Without a choice, the command takes the case nearest the median distance for that type, so it always runs.

3. **`LEEME.txt`**: contents, CRS, licence (CC BY 4.0, ADR-0013), attribution to the SDP, source dates from `config/manifest.json`, contact.

## How it's built

- New module `src/bogota_syntax/sdp_package.py` and command `bogota-syntax sdp-package`. It reads `data/interim/sdp_eje_vial.parquet`, `data/interim/foreground/review.gpkg` and the two config files; it writes to `data/processed/sdp_package/`. It never writes to the foreground outputs, so the pipeline is unchanged.
- **Keys by nearest feature, no lineage in the pipeline.** Each problem point or correction line is joined to the nearest original Eje Vial feature within a tolerance in `config/analysis.yaml` (`sdp_package.match_m`). A row with no feature in range is reported, not guessed.
- **The note is a template.** `nota_metodologica.md` is filled from the command's counts, so the numbers in it are produced by code (rule 2). The prose is written once, by hand, in Spanish.
- **CRS.** Reprojection to `PCS_CarMAGBOG` happens once, at write. A test checks that original features round-trip to their raw geometry within 1 cm.
- **Figures** in the same module, one function per figure. matplotlib is already installed through other dependencies; it becomes a direct one with `uv add matplotlib`.
- **Tests** on a small synthetic layout in `tests/`: each `tipo` maps right; keys are found; the CRS round-trips; each figure renders from the fixture.

## Rerun path (for the note)

```bash
uv run bogota-syntax ingest sdp_eje_vial --force
uv run bogota-syntax ingest sdp_red_infraestructura_vial --force
uv run bogota-syntax foreground
uv run bogota-syntax sdp-package
```

The things that need a person: stale interchange decisions, stale manual edits, new review points. The command reports all three.

## Calls made in this design (check these)

1. One CRS only, `PCS_CarMAGBOG`, not both as the brief suggested: it is what they publish.
2. Open cases go inside `problemas` with `estado = abierto`, not in a layer of their own: fewer layers.
3. Douglas-Peucker simplification and zig-zag straightening are mentioned in the note but not mapped: they touch most lines and fix nothing in their data.
4. The `ediciones_manuales` layer is read straight from `config/foreground_edits.geojson`, because the output's `sources` column doesn't mark manual lines (they keep the label of the line they came from). That is a small pipeline bug, kept apart from this work.
5. The PDF is exported by hand at send time (open the Markdown in VS Code or a browser, print to PDF), not by the command: pandoc isn't installed and adding it is a system dependency. If a rerun should also rebuild the PDF, the pure-Python `fpdf2` could do it, at the cost of laying the note out in code.
6. Seven figures, before / after for each problem type, examples picked in config with an automatic fallback.

## Left to the builder

The exact `match_m`; the order and styling of the layers (a QGIS `.qml` per layer is welcome if small); how the reported unmatched rows are shown.

## Before anything is sent

Gregorio reviews the package in QGIS and reads the note. Sending it is his call.

## Revision, 2026-11-27 (Gregorio's review of the first PDF)

- **The corrected network is delivered**, as layer `eje_vial_corregido`, first in the GeoPackage. It comes from an errors-only run of the foreground cleaning (`foreground.clean(..., errors_only=True)`), made by the package command itself: snaps, stub and duplicate removal, pairs, extensions and connectors only. No junction merging, no simplification, no interchange relocation, no manual edits.
- **Crossings are not split** in that network, since some are bridges. They stay in `problemas` as `estado = sin_cambio` with an `observacion`; the analysis network still splits them.
- **Modelling decisions stay in the package for transparency**, stated as not suggested for the Eje Vial: the analysis aims at a routable spatial (not road) continuity.
- Open dead ends inside an interchange polygon are noted as such: the analysis fixes them with a modelling decision, the corrected network leaves them open.
- Step 3 (stubs) now runs again after step 8 (ADR-0012): an extension on Avenida Usminia had left a 12.4 m stub.
- The note: first person singular (Gregorio to the SDP); figure 1 framed on the urban area; the method's principle in bold; a "Preguntas para la SDP" section; a "Código utilizado" section listing each file with a link to the repository at the commit that ran (`sdp_package.repo_url`). The command warns when the linked files differ from that commit.
