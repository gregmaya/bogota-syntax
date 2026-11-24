# CLAUDE.md — bogota-syntax

Open, reproducible street-network centrality for Bogotá D.C., published as PMTiles for the Bogotá viewer.

Decisions live in `docs/decisions/` as ADRs. Read them before changing anything structural.

## Current status

- Phase: **0, setup** (update this line when a phase closes).
- ADRs 0001–0011 Accepted (0007 and 0008 shelved for v1 by 0010); 0012 Proposed. Not decided yet: orchestration.
- **Foreground (ADR-0012, Proposed):** `foreground` cleans SDP Eje Vial with the POT arterial polygons (`sdp_red_infraestructura_vial`): classify dead ends by polygon neighbours, then correct only `critical` ones. Not used by v1 centrality yet. Interchange centre relocation is prototyped but waits for its own classification.
- Distances: 400, 800, 1200, 1600, 2000 and 5000 m (`config/analysis.yaml`).
- Pilot: the 36 RENOBO polygons in `data/renobo_selection.gpkg` are drawn as dotted outlines. The live area is those polygons + 5 km, and the network is the live area + a 5 km dead buffer (ADR-0004).
- **v1 is MVI only (ADR-0010):** cleaned by neatnet, clipped to Bogotá, dead ends extended within 10 m, merged into intersection-to-intersection segments (`network.mode: mvi_only`). No OSM, no SDP axes. Each segment has `boundary_dist_m` because the network stops at the city limit (edge effect). The stitched pipeline (ADR-0007/0008: `arterials`, `join`, `network.mode: stitched`) is shelved, not deleted; ADR-0010 lists what it needs. Analysis is simplest-path closeness and betweenness on the dual (segment) graph, undirected and unweighted, islands kept and flagged (ADR-0009). The pilot centrality run works (`centrality`); next: publishing (PMTiles, etapas).

## Method in one paragraph

v1: official IDECA Malla Vial centrelines, inside Bogotá only (ADR-0010). neatnet does all the cleaning, and cityseer only analyses, with `set_boundary` so the buffer is dead (ADR-0004, ADR-0005). Everything internal is EPSG:9377 GeoParquet; tiles are PMTiles (ADR-0006).

## Stack

- Python, environment managed with **uv**: `pyproject.toml` + `uv.lock`, both committed. Add dependencies with `uv add`, never with plain `pip install`. Don't add a system dependency (GDAL, tippecanoe) without asking.
- Quality: ruff, pytest, pre-commit, GitHub Actions.

## Data access

Official datasets are found through the CKAN API (`https://datosabiertos.bogota.gov.co/api/3/action/package_show?id=<dataset>`), which gives licence, modification date and resource URLs. The Mapa de Referencia is also served as ArcGIS REST (`serviciosgis.catastrobogota.gov.co/.../Mapa_Referencia/MapServer`, Malla Vial = layer 13), which allows a bounding-box query instead of the 1.9 GB download.

## Commands

```bash
uv sync                       # create/refresh .venv from uv.lock
uv run pre-commit install     # once per clone
uv run bogota-syntax ingest              # all sources, in order; builds the extent once its inputs are in
uv run bogota-syntax ingest <source_id>  # one source; --force to download again
uv run bogota-syntax extent              # ADR-0004 areas + stitch extent and cleaning areas (ADR-0007)
uv run bogota-syntax clean [mvi|osm]     # neatnet per side, with piece checks (~10 min for both)
uv run bogota-syntax arterials           # shelved for v1: SDP axes replace MVI arterials (ADR-0008)
uv run bogota-syntax join                # shelved for v1: OSM + MVI at the boundary (ADR-0007)
uv run bogota-syntax network             # v1: MVI-only segments -> data/processed/network.parquet (~4 min)
uv run bogota-syntax foreground            # SDP Eje Vial cleaned with the POT arterial polygons (ADR-0012) -> data/processed/foreground.{parquet,gpkg} (~35 s)
uv run bogota-syntax centrality [--area city]  # density, farness, harmonic, Hillier, betweenness (ADR-0009/0011) -> data/processed/centrality_<area>.parquet (~4 min)
uv run pytest
uv run ruff check . && uv run ruff format .
```

Update this block when the real commands differ.

## Repository layout

- `config/sources.yaml`: every dataset with URL or service, licence and kind. A new source is added here first.
- `config/analysis.yaml`: distances, pilot selection (RENOBO by `GmlID`), margins. No magic numbers in code.
- `config/manifest.json`: written by ingest and committed. Query, date, feature count, SHA-256, CKAN modification date.
- `src/bogota_syntax/`: `ingest/` (CKAN files, ArcGIS REST, OSM via osmnx), `extent.py`, `clean.py`, `arterials.py`, `join.py`, `network.py`, `foreground.py`, `centrality.py`, `cli.py`. `scripts/`: one-off checks behind ADR figures. `sandbox/` (git-ignored): QGIS prototypes before they move into `src/`.
- `data/raw/<source>/` as received (EPSG:4326); `data/interim/<source>.parquet` in EPSG:9377; `data/interim/extent/`.

## Hard rules

1. **Never commit data.** Nothing under `data/` goes into git; pre-commit blocks files over 1 MB.
2. **No invented numbers.** Every figure in the README, docs or changelog is produced by code in the repo. If a number isn't computed yet, write a TODO, not an estimate.
3. **CI never downloads full datasets.** Tests use small fixtures in `tests/fixtures/`.
4. **Licences:** code MIT; outputs ODbL because of OSM (ADR-0002). Any new source's licence is checked against ODbL before it's used. CC BY-SA sources such as the SITP GTFS feed can't be mixed in without a new ADR.
5. **CRS:** everything internal is EPSG:9377. Reproject at ingest, never later. SDP layers arrive in `PCS_CarMAGBOG`, and RENOBO and OSM in EPSG:4326.
6. **Source field names stay as published** (`MVISVIA`, `ESTADO_VIA`), as in `bogota-pop`.

## Conventions

Follow `../bogota-pop` unless an ADR here says otherwise:

- Code, comments, commit messages and ADRs in English. Issues, PRs and release notes in English **and** Spanish, titles as `English · Español`. README bilingual (`README.md`, `README.es.md`).
- Spell out every acronym the first time it appears, using `docs/glossary.md`; never guess one.
- Type hints on public functions. Short docstrings that state inputs, outputs, CRS and units.

## How to work with me (Gregorio)

- Talk a decision through before writing code for it. Propose, then wait.
- Stop after each step for review. Small PRs, one per task.
- A new structural decision becomes a new ADR (copy `docs/decisions/template.md`, list it in `docs/decisions/README.md`).
- Prose in docs: direct, specific, varied sentence length, no filler intros or recap endings.

## Companion repos

- `gregmaya/bogota-pop-viewer` (`../bogota-pop-viewer`): the web viewer. It only reads files this repo publishes. Keep published file names and schemas stable; changing them is a breaking change with a changelog note. How layers are described to the viewer should follow `../bogota-pop/docs/decisions/0013-etapas-layer-contract.md` unless an ADR here says otherwise.
- `gregmaya/bogota-pop` (`../bogota-pop`): population model.
- **One session per repo.** A session here never edits the other repos. A need from them becomes a note to Gregorio or a cross-linked issue.
