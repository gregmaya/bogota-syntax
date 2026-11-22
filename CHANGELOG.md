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
