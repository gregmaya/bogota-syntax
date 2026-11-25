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
- `bogota-syntax arterials` restores removed lines that were the only link to the main network, and extends MVI dead ends onto a line within 10 m (`neatnet.extend_lines`).
- ADR-0009: dual (segment) graph, simplest-path closeness and betweenness at six distances, undirected, unweighted, islands kept.
- `bogota-syntax network`: segments from intersection to intersection with stable `segment_id`, `piece`/`in_main`, recovered source attributes; `data/processed/network.parquet`.
- ADR-0010: v1 network is MVI only. `bogota-syntax network` builds it by default (`network.mode: mvi_only`) with `boundary_dist_m` per segment; the stitched pipeline (ADR-0007, ADR-0008) is shelved, its lessons recorded in the ADR.
- `bogota-syntax network` collapses segments shorter than 0.5 m (`min_segment_m`) so cityseer's graph matches the network one-to-one.
- `bogota-syntax centrality`: pilot run of simplest-path closeness (`cc_harmonic_<d>_ang`) and betweenness (`cc_betweenness_<d>_ang`) at six distances on the dual graph, cityseer's own cleaning off; `data/processed/centrality_pilot.parquet`. Adds cityseer (AGPL-3.0, ADR-0001).
- `bogota-syntax centrality --area city`: the whole city, live inside the SDP urban perimeter; `data/processed/centrality_city.parquet` (local only, not published).
- ADR-0011: angular density, farness and Hillier integration added to harmonic closeness and betweenness; expressions in `config/analysis.yaml` (`centrality:`).
- New source `sdp_red_infraestructura_vial`: the POT arterial road polygons (SDP, CC BY 4.0).
- ADR-0012 (Proposed) and `bogota-syntax foreground`: SDP Eje Vial cleaned into a foreground network, guided by the arterial polygons; `data/processed/foreground.{parquet,gpkg}` and review layers in `data/interim/foreground/review.gpkg`. Not used by v1 centrality.
- `foreground` step 11: interchange centres relocated where `config/enlace_decisions.csv` says so (from Gregorio's QGIS labels of 2026-11-25), with a fitted rule for interchanges without a decision; those are flagged for review.
