# ADR-0003: Network source: official data inside Bogotá, OSM outside, OSM-only fallback

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Centrality needs a street network that is complete inside the study area and continues well beyond it (ADR-0004). Later on, we also want to compare the city as it is with the city in the Plan de Ordenamiento Territorial (POT, Decreto 555 de 2021).

What the Bogotá open-data portal offers (checked 2026-11-21 through its CKAN API and the IDECA REST service):

| Dataset | Publisher | Geometry | Content | Licence |
| --- | --- | --- | --- | --- |
| Mapa de Referencia, layer *Malla Vial* (Malla Vial Integral, MVI) | IDECA / UAECD | Lines | Every street centreline, one line per carriageway; 139,106 segments. Has direction (`MVISVIA`), lanes per carriageway (`MVINUMC`) and street type | CC BY 4.0 |
| `eje-vial-bogota-d-c` | SDP | Lines | Arterial and rural road axes of the POT only (profiles A-0 to A-3, RP, RS, RT); 1,149 lines, about 1,075 km; `ESTADO_VIA` separates existing from projected | CC BY 4.0 |
| `red-infraestructura-vial-bogota-d-c` | SDP | Polygons | Road reserve corridors of the POT arterial network; 1,414 features | CC BY 4.0 |
| OpenStreetMap | OSM contributors | Lines | Streets inside and outside Bogotá | ODbL |

The official layers stop at the city limit. SDP layers use the local plane `PCS_CarMAGBOG`, and RENOBO uses EPSG:4326.

## Decision

**v1 is one network, with official data tried first and OSM only as the fallback.**

1. **Try first:** IDECA Malla Vial (MVI) inside Bogotá, and OSM streets (filtered by tag) outside it. The two are clipped at the Bogotá boundary (layer *Municipio*, Mapa de Referencia) and snapped together there.
2. **Look before running:** the join is drawn as review layers (boundary, raw join, join after neatnet) and checked on the map before any centrality is run.
3. **Fallback:** if the join turns out too hard to make clean (false dead ends, duplicated or missing roads along the boundary that neatnet doesn't fix), v1 switches to OSM inside and outside. That switch is recorded in a new ADR that supersedes this one, with the review layers that justified it.
4. **No scenarios in v1.** The SDP `eje-vial` axes are not added. They are mostly the same arterials MVI already draws, and adding them would put a second overlap on top of the boundary seam. Scenarios, including the projected POT roads by `ESTADO_VIA` code, come back in a later ADR once v1 works.

## Alternatives considered

- **OSM everywhere from the start.** Simplest, with no seam. It is kept as the fallback, and later as a comparison: MVI against OSM inside Bogotá.
- **MVI + OSM + every `eje-vial` axis, one scenario per `ESTADO_VIA` code.** Written in an earlier draft of this ADR. Deferred: two sources of overlap at once make the first network hard to debug, and the codes aren't decoded yet.
- **SDP `eje-vial` as the network inside Bogotá.** Rejected: it has arterials only, and centrality without local streets means something else.

## Consequences

- Each source gets an entry in `config/sources.yaml`, with URL, version (MVI uses releases like `V06.26`), licence and checksum. OSM is ingested in both paths, because it's needed outside Bogotá anyway.
- The first task is the join and its review layers, not centrality. The criteria for "too hard" are written down in that task's issue once we've seen the data, not guessed here.
- MVI draws one line per carriageway. neatnet is built to merge these (ADR-0005).
- **Kept for later:** the `ESTADO_VIA` codes (0, 19, 20, 21) and what they mean. The dictionary names the code list (`cdom_fase`) but doesn't print its values.
