# Brief: a corrected Eje Vial package for the SDP

- **Status:** brief for a future session, not started
- **Date:** 2026-11-25
- **Related:** ADR-0012 (foreground network), ADR-0002 (output licence)

## Why

Our contact at the Secretaría Distrital de Planeación (SDP) has shown interest in the corrected Eje Vial and in how it was made. The SDP publishes the Eje Vial axes of the Plan de Ordenamiento Territorial (POT) on Datos Abiertos Bogotá. As published they are not a connected network. `bogota-syntax foreground` fixes that for our analysis (ADR-0012): it starts from 1,235 lines with 238 dead ends that should connect to the network, and ends with 4, which are road segments missing from the source data.

A package could give the SDP a corrected layer they can check edit by edit, and a method they can rerun when they update the layer. For this project it's a by-product, not a goal: it should cost little and must not change the pipeline's outputs.

## What we already have

- **The cleaned network**: `data/processed/foreground.{parquet,gpkg}`, 1,016 segments, 1,074.3 km, no crossings without a shared point. Segments run from intersection to intersection, with the Eje Vial attributes of their longest part, plus `sources` (what touched each one: `original`, `pair`, `extension`, `connector`, `relocated`, `manual`).
- **One layer per correction**: `data/interim/foreground/review.gpkg` (snaps, crossings split, stubs and duplicates removed, dead ends with their class, pairs, extensions, merged junctions, connectors, review points, interchanges with their decision).
- **The method and its parameters**: ADR-0012, `config/analysis.yaml` (`foreground:`), and the reviewed inputs `config/enlace_decisions.csv` and `config/foreground_edits.geojson`.
- **The code**: `src/bogota_syntax/foreground.py`, MIT licence, with a test for each rule.

## What the SDP would probably want, and the gaps

1. **Their own lines, corrected, not our segments.** Our network merges and splits lines, so one segment no longer maps to one Eje Vial feature. The SDP will want each original feature, keyed by `OBJECTID` / `CODIGO_ID`, with its geometry corrected, plus a list of the new lines (connectors, extensions) that have no original feature. *Gap: this edit-level view doesn't exist yet. The pipeline would need to keep each line's lineage, or the corrections layers would need to be mapped back to the original features.*
2. **A corrections layer they can review**: one feature per edit, with its type (snap, pair, extension, connector, removed stub or duplicate, relocated interchange, manual edit), its length and the original feature it touches. Most of this is in `review.gpkg`, but not keyed to `OBJECTID`.
3. **Their coordinate reference system (CRS) and format.** SDP layers arrive in `PCS_CarMAGBOG`; ours are EPSG:9377. The package should probably come in both, as a GeoPackage.
4. **A short method note in Spanish**: classify first, then correct; the role of the POT polygons; the parameters in plain terms; what was done by hand; the limits (below).
5. **A way to rerun it** when they republish Eje Vial or the polygons: one command, plus a list of what needs a person (stale decisions, stale edits, new review points).

## Limits to state openly

- Crossings are split everywhere: bridges and overpasses are not yet told apart, so some crossings become junctions that don't exist on the ground.
- `ESTADO` / `ESTADO_VIA` (built vs planned) are ignored, so planned roads are treated like built ones.
- Interchange centres were moved where Gregorio's review said so (`config/enlace_decisions.csv`), and a few places were redrawn by hand (`config/foreground_edits.geojson`). Those are judgements, not rules.
- 4 dead ends remain, all missing segments in the source. One isolated line is left unconnected.

## Licence

The corrected Eje Vial would be made only from SDP layers (Eje Vial and Red de Infraestructura Vial, both CC BY 4.0), with no OpenStreetMap data. ADR-0002 puts the project's outputs under ODbL because of OSM, but that reason doesn't apply to this product. Sharing it as CC BY 4.0 with attribution to the SDP seems right. *To decide in a short ADR before anything is sent.*

## Questions for the SDP (through Gregorio's contact)

- Do they want the edit-level layer (their features corrected), the connected network, or both?
- Which CRS and format? Do they need their schema preserved exactly?
- Is it for internal checking only, or could corrections flow back into the published Eje Vial?
- Would they share the meaning of the `ESTADO` codes and any record of bridges and overpasses? Both would improve the cleaning.
- Who would rerun it, and how often do they republish these layers?

## Suggested plan for the session

1. Settle the licence in a short ADR (CC BY 4.0 for this product).
2. Decide the scope with Gregorio from the questions above; start with the edit-level layer and the corrections layer.
3. Add lineage to the foreground step, or a mapping back to `OBJECTID`, with tests. The pipeline's own outputs must not change.
4. Write a `bogota-syntax sdp-package` command that writes the GeoPackage (both CRSs), the method note in Spanish, and a README with attribution and the rerun steps.
5. Gregorio reviews the package in QGIS before anything is sent. Sending it is his call.
