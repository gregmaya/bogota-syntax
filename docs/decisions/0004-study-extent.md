# ADR-0004: Study extent, buffer and live nodes

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Centrality near the edge of a network is biased low, because routes that would come in from beyond the edge are missing. The usual fix is to compute on a larger network and report only inside the study area. cityseer supports this: `set_boundary(polygon)` marks nodes inside as *live* and nodes outside as *dead*. Dead nodes are still used for routing, but no results are reported for them.

The goal is all of Bogotá. The first stages focus on central areas, using the RENOBO projects selected in `data/renobo_selection.gpkg` (36 of the 76 RENOBO project polygons, EPSG:4326).

## Decision

- **Analysis distances:** 400, 800, 1200, 1600, 2000 and 5000 m, kept in `config/analysis.yaml`.
- **Pilot (v0.x), three nested areas:**
  1. **Pilot areas:** the 36 selected RENOBO polygons. These aren't a computation boundary. They're published as their own outline layer, which the viewer draws as dotted areas over the results.
  2. **Live area:** the pilot areas plus 5 km. Results are reported and drawn for every live node, so the map shows the full context around each project, not just the inside of the polygons.
  3. **Network extent:** the live area plus the buffer. Buffer nodes are dead.
- **Buffer width** = the largest analysis distance, and at least 5 km. With today's distances that is 5 km, so the network reaches about 10 km beyond the pilot areas.
- **Full city (later):** the live area becomes Bogotá D.C. (or its urban area plus expansion land, to be decided), with the same buffer rule. The buffer then reaches into neighbouring municipalities, which is why OSM is needed (ADR-0003).

## Alternatives considered

- **No buffer.** Rejected: values near the edge would be wrong.
- **Fixed 5 km buffer regardless of distance.** Rejected: any distance over 5 km would still have an edge effect.

## Consequences

- Adding a distance over 5 km widens the buffer automatically. The buffer is computed from `config/analysis.yaml`, never written by hand.
- The live polygon is saved with each run, so published values can always be traced to the area they're valid for.
- **Viewer:** a dotted outline isn't one of the style kinds in `bogota-pop` ADR-0013 (`sequential`, `categorical`, `outline`). It needs either a new kind (for example `outline_dashed`) or a dash option on `outline`, agreed with the viewer repo first. That will be raised as a cross-linked issue, not changed from this repo.
- The 5 km margin for the live area is how the instruction "work at least 5 km around those areas" (2026-11-21) was read. It's a single value in `config/analysis.yaml`.
