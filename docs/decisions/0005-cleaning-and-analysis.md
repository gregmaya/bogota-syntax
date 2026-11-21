# ADR-0005: Cleaning with neatnet, analysis with cityseer

- **Status:** Proposed
- **Date:** 2026-11-21

## Context

Raw street data has dual carriageways, tiny roundabouts and broken connections, and all of these distort centrality. neatnet (`neatnet.neatify`, docs version 0.1.6) simplifies a street network into one that keeps the street layout and its connections. cityseer (5.8.0) computes centrality, and it also cleans while it builds a network (`remove_fillers`, `remove_danglers`, `merge_parallel_dist` in `CityNetwork.from_geopandas`). momepy is kept for later morphology work.

## Decision

- **neatnet does all the cleaning.** It runs once, on the full joined network, including every POT axis whatever its `ESTADO_VIA` (ADR-0003). The network is in EPSG:9377, which is in metres as neatnet needs, and cleaning starts from neatnet's default parameters.
- **Scenarios are filters, not re-cleans.** Each scenario takes its segments from the one cleaned network by `fuente` and `ESTADO_VIA`, and is built as its own cityseer network.
- **cityseer only analyses.** The cleaned lines are loaded with `CityNetwork.from_geopandas`, with its own cleaning turned off as far as its API allows. Then `set_boundary` is applied (ADR-0004), and `centrality_shortest` / `centrality_simplest` are run.
- **Not yet:** momepy.

## Alternatives considered

- **cityseer's built-in cleaning only.** It's simpler, but neatnet is designed to merge dual carriageways and junction clutter, and MVI has a lot of both.
- **Both cleaners in sequence.** Rejected: the effects are hard to tell apart and to document.

## Consequences

- **To check in the first task:** which `from_geopandas` values actually turn cleaning off (for example `remove_fillers=False`, `remove_danglers=0`, `merge_parallel_dist=0`), and neatnet's licence and its runtime at buffered-pilot scale.
- Every neatnet run writes a before/after review layer, so the cleaning can be checked on the map.
- neatnet is tested on street lines only. OSM footway, sidewalk and service tags are filtered before cleaning, using the same filter in both scenarios.
