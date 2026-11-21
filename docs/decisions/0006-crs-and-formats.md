# ADR-0006: CRS and file formats, same as bogota-pop

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The sources arrive in three different coordinate reference systems (CRS): the SDP layers in the Bogotá local plane (`PCS_CarMAGBOG`), RENOBO in EPSG:4326, and OSM in EPSG:4326. neatnet and cityseer need projected metres. `bogota-pop` already settled on one internal CRS and format, and the viewer already reads its tiles.

## Decision

- **Internal CRS:** MAGNA-SIRGAS Origen Nacional, EPSG:9377 (metres). Every source is reprojected at ingest, never later.
- **Internal format:** GeoParquet.
- **Published tiles:** PMTiles in EPSG:3857, written with GDAL's PMTiles driver through pyogrio. The layer list follows `bogota-pop` ADR-0013 (an `etapas.yaml` list and an `etapas.json` that the viewer reads).

## Alternatives considered

- **UTM 18N (EPSG:32618)**, which cityseer would infer from OSM. Rejected: it isn't the national standard, and it differs from `bogota-pop`, so overlays would need another reprojection.

## Consequences

- Z values (RENOBO is 3D) are dropped at ingest.
- Reprojection from `PCS_CarMAGBOG` relies on the WKT that ships with each file. Ingest checks this by testing that a known point lands inside Bogotá in EPSG:9377.
