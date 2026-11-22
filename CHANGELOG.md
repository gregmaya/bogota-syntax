# Changelog

All notable changes to this project are recorded here. Each release covers data, method and results.

## [Unreleased]

### Added

- Repository scaffold: README (EN/ES), MIT licence, citation file, pre-commit, CI, ADR template, glossary.
- ADRs 0001–0006: code and data licences, network source, study extent, cleaning and analysis tools, CRS and formats.
- README: data sources, CKAN API access, future work (SITP GTFS, momepy).
- `bogota-syntax ingest` and `extent`: sources in `config/sources.yaml`, provenance in `config/manifest.json`, pilot areas, live area and network extent (ADR-0004).
- ADR-0007: one stitched network, MVI inside Bogotá and OSM outside, over the urban area plus 10 km.
- Source `sdp_perimetro_urbano` and the stitch areas: `stitch_extent`, `mvi_clean_area`, `osm_clean_area` (ADR-0007).
- OSM is fetched over `osm_clean_area` only, always the latest data; the manifest records the query time, Overpass endpoint, osmnx version and the OSM data timestamp (ADR-0007).
- `bogota-syntax clean`: neatnet cleans MVI and OSM over their cleaning areas; every connected piece is labelled before and after, and the step stops if a piece is lost (ADR-0007).
- ADR-0008: SDP arterial axes replace cleaned MVI arterials inside Bogotá; `scripts/adr0008_interchanges.py` tests it on seven interchanges.
- Source `sdp_eje_vial` and `bogota-syntax arterials`: the axes swap runs city-wide and writes `mvi_arterial` plus review layers (ADR-0008).
- `bogota-syntax arterials` closes gaps where SDP axes stop short of each other (`axis_snap_m`).
- `bogota-syntax join`: MVI inside and OSM outside Bogotá, cut at the boundary and joined by connectors; review layers in `data/interim/join/` (ADR-0007).
