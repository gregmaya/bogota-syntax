# ADR-0003: Network source: official data inside Bogotá, OSM outside

- **Status:** Proposed
- **Date:** 2026-11-21

## Context

Centrality needs a street network that is complete inside the study area and continues well beyond it (ADR-0004). We also want to compare the city as it is with the city in the Plan de Ordenamiento Territorial (POT, Decreto 555 de 2021).

What the Bogotá open-data portal offers (checked 2026-11-21 through its CKAN API and the IDECA REST service):

| Dataset | Publisher | Geometry | Content | Licence |
| --- | --- | --- | --- | --- |
| Mapa de Referencia, layer *Malla Vial* (Malla Vial Integral, MVI) | IDECA / UAECD | Lines | Every street centreline, one line per carriageway; 139,106 segments. Has direction (`MVISVIA`), lanes per carriageway (`MVINUMC`) and street type | CC BY 4.0 |
| `eje-vial-bogota-d-c` | SDP | Lines | Arterial and rural road axes of the POT only (profiles A-0 to A-3, RP, RS, RT); 1,149 lines, about 1,075 km; `ESTADO_VIA` separates existing from projected | CC BY 4.0 |
| `red-infraestructura-vial-bogota-d-c` | SDP | Polygons | Road reserve corridors of the POT arterial network; 1,414 features | CC BY 4.0 |
| OpenStreetMap | OSM contributors | Lines | Streets inside and outside Bogotá | ODbL |

The official layers stop at the city limit. SDP layers use the local plane `PCS_CarMAGBOG`, and RENOBO uses EPSG:4326.

## Decision

**One cleaned geometry, several scenarios.**

1. **Sources:**
   - **Inside Bogotá:** IDECA Malla Vial (MVI), the current street network.
   - **Outside Bogotá:** OSM streets, filtered by tag.
   - **POT axes:** every SDP `eje-vial` axis, whatever its `ESTADO_VIA` code.
2. **Joining:** the sources are joined at the Bogotá boundary (layer *Municipio*, Mapa de Referencia). Segments are snapped across a small tolerance there, and the join is checked on a map before any centrality is run.
3. **Cleaning:** the full joined network is cleaned once (ADR-0005). Every cleaned segment keeps a `fuente` attribute (`mvi`, `osm` or `eje_vial`) and, for POT axes, the source `ESTADO_VIA`.
4. **Scenarios** are subsets of that one cleaned geometry. They are never cleaned again, so the same street is the same segment in every scenario and results can be compared directly.
   - **`base`** = segments from `mvi` and `osm`.
   - **`estado_<code>`**, one per `ESTADO_VIA` code found in the data (today 0, 19, 20 and 21) = `base` + the POT axes with that code.

Until SDP confirms what each code means, scenarios are named and reported by the raw code. When the meaning is known, the codes get Spanish labels in `config/`; the geometry and the analysis don't change.

## Alternatives considered

- **OSM everywhere, official data only for comparison.** It's simpler and has no seam, but it can't show the POT's proposed roads. It stays as a validation run: MVI against OSM inside Bogotá.
- **SDP `eje-vial` as the network inside Bogotá.** Rejected: it has arterials only, and centrality without local streets means something else.
- **Turning the SDP road reserve polygons into centrelines.** Not needed, because `eje-vial` already has the lines.

## Consequences

- Each source gets an entry in `config/sources.yaml`, with URL, version (MVI uses releases like `V06.26`), licence and checksum.
- **Still open:** what the `ESTADO_VIA` codes (0, 19, 20, 21) mean. The dictionary names the code list (`cdom_fase`) but doesn't print its values. This doesn't block the analysis, which runs per raw code; it only blocks labelling.
- **To check in the first task:**
  - whether `neatnet.neatify` keeps or drops segment attributes when it merges segments. If it drops them, `fuente` and `ESTADO_VIA` are put back by spatial matching against the inputs.
  - how a segment is labelled where an axis that already exists (probably one code) overlaps an MVI street, so cleaning merges the two.
- **Risk:** the seam at the boundary can create false dead ends or duplicate roads. The review layers for the join (ADR-0013 in `bogota-pop`) are part of the first task.
- MVI draws one line per carriageway. neatnet is built to merge these (ADR-0005).
