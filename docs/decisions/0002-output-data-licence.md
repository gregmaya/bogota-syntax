# ADR-0002: Output data licence: ODbL 1.0

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The network outside Bogotá comes from OpenStreetMap (ADR-0003), which is licensed under the Open Database License (ODbL) 1.0. A database derived from OSM and made public must be shared under ODbL. The official Bogotá layers we use are all CC BY 4.0 (checked through the CKAN API of datosabiertos.bogota.gov.co, 2026-11-21), and CC BY 4.0 only asks for attribution.

## Decision

Published data outputs (GeoParquet, PMTiles, summary files) are licensed under ODbL 1.0. Attribution covers OSM contributors and each official source (IDECA, SDP, RENOBO).

## Alternatives considered

- **CC BY 4.0, like `bogota-pop`.** Not possible while the outputs contain OSM-derived data.
- **Official data only, so CC BY 4.0 applies.** Rejected: there is no official network outside Bogotá, and the buffer needs one (ADR-0004).

## Consequences

- A `DATA_LICENSE` file with the ODbL text and the attribution block is added before the first data release.
- The viewer must show OSM attribution on these layers.
- A source under CC BY-SA 4.0 (for example the SITP GTFS feed) is also share-alike, and BY-SA and ODbL can't both be satisfied in one output. Adding such a source needs a new ADR.
