# ADR-0013: The Eje Vial package for the SDP is licensed CC BY 4.0

- **Status:** Accepted
- **Date:** 2026-11-26
- **Related:** ADR-0002 (output data licence), ADR-0012 (foreground network)

## Context

ADR-0002 licenses the project's data outputs under ODbL 1.0, because they contain OpenStreetMap (OSM) data and ODbL requires derived databases to stay ODbL. The package for the Secretaría Distrital de Planeación (SDP) ([design](../briefs/sdp-eje-vial-package-design.md)) is made only from two SDP layers, Eje Vial and Red de Infraestructura Vial arterial, both CC BY 4.0, plus our own reviewed decisions and edits. It contains no OSM data, so ADR-0002's reason does not apply to it.

## Decision

The SDP package is licensed under CC BY 4.0, with attribution to the SDP as the source of both layers and to this project for the corrections. ADR-0002 still governs every other output.

## Alternatives considered

- **ODbL, like the other outputs.** Rejected: there is no OSM in it, and share-alike would make it harder for the SDP to fold the corrections back into their own CC BY layer.
- **No licence, sent informally.** Rejected: the package may be passed on, and attribution should travel with it.

## Consequences

- The package's `LEEME.txt` and the GeoPackage metadata carry the CC BY 4.0 notice and attribution.
- Adding any OSM or other ODbL data to the package would void this decision and needs a new ADR.
