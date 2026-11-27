# SDP Eje Vial package: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `bogota-syntax sdp-package` command that writes a small Spanish package for the SDP: a four-layer GeoPackage in `PCS_CarMAGBOG`, seven figures, a filled methodological note and a `LEEME.txt`.

**Architecture:** A new module reads what `foreground` already wrote (`data/interim/foreground/review.gpkg`, `data/processed/foreground.parquet`) plus the original Eje Vial and the two reviewed config files. It reshapes them into the package layers, keys every row to the nearest original feature, and writes everything to `data/processed/sdp_package/`. It never writes to any pipeline output.

**Tech Stack:** Python, geopandas, shapely, pyogrio, networkx (already installed), matplotlib (made a direct dependency), typer, pytest.

**Spec:** [sdp-eje-vial-package-design.md](sdp-eje-vial-package-design.md); licence in ADR-0013 (Proposed).

## Global Constraints

- Package text, layer names and new field names in Spanish; source field names as published (`OBJECTID`, `CODIGO_ID`, `NOMBRE`; CLAUDE.md rule 6). Code, comments, docstrings and commits in English.
- No number written by hand in the note or `LEEME.txt`: every figure comes from the command (rule 2).
- Output CRS: the `PCS_CarMAGBOG` definition read from `data/raw/sdp_eje_vial/eje_vial.gpkg`. All work in between is EPSG:9377; reproject once, at write.
- No new system dependency. `uv add matplotlib` only.
- Parameters in `config/analysis.yaml` under `sdp_package:`, no magic numbers in code.
- The pipeline's outputs don't change: `foreground.py` is read from, never edited, in this plan.
- CI never needs `data/`: tests build tiny synthetic layouts in EPSG:9377, as `tests/test_foreground.py` does. The one CRS fixture is a WKT text file.
- Figures: no basemap, nothing downloaded. Original lines grey, corrections one strong colour, open cases a second, POT polygons light fill, scale bar, `NOMBRE` in the caption.

## Review Focus

1. **A row with no Eje Vial feature within `key_m`** must keep its row with null keys and be counted in the run report as unmatched, never dropped or keyed to a far feature. Test in Task 1.
2. **An example ID in config that no longer exists** (after SDP republishes) must warn and fall back to the automatic pick, not crash. Test in Task 4.
3. **A problem type with zero cases** (0 connectors, no edits file) must still write an empty layer of the right schema; its figure is skipped and the note says "sin casos". Tests in Tasks 2, 3 and 4.
4. **`review.gpkg` older than `data/interim/sdp_eje_vial.parquet`** (foreground not rerun after a new ingest) must stop the command with "run `bogota-syntax foreground` first". Test in Task 3.
5. **A critical dead end fixed by neither pair, extension nor connector** (it went with an interchange relocation or a manual edit) must come out `corregido` with `correccion = reubicacion_o_edicion`, not `abierto`. Test in Task 2.

---

## File structure

- Create `src/bogota_syntax/sdp_package.py`: layers, keys, CRS, run.
- Create `src/bogota_syntax/sdp_figures.py`: the seven figures (kept apart so the layer logic stays readable).
- Create `src/bogota_syntax/templates/nota_metodologica.md`, `src/bogota_syntax/templates/LEEME.txt`: Spanish text with `string.Template` placeholders (`$n_extremo_suelto`).
- Modify `src/bogota_syntax/cli.py`: add the `sdp-package` command after `foreground`.
- Modify `config/analysis.yaml`: add the `sdp_package:` block.
- Create `tests/test_sdp_package.py`, `tests/test_sdp_figures.py`, `tests/fixtures/pcs_carmagbog.wkt`.
- Modify `CLAUDE.md` (commands block), `pyproject.toml` / `uv.lock` (matplotlib).

---

### Task 1: Config, keys and the SDP CRS

**Files:**
- Modify: `config/analysis.yaml` (new block after `foreground:`)
- Create: `src/bogota_syntax/sdp_package.py`, `tests/test_sdp_package.py`, `tests/fixtures/pcs_carmagbog.wkt`

**Interfaces:**
- Produces:
  - `KEYS = ["OBJECTID", "CODIGO_ID", "NOMBRE"]`
  - `attach_keys(gdf: gpd.GeoDataFrame, axes: gpd.GeoDataFrame, key_m: float, at: str = "point") -> gpd.GeoDataFrame`: adds `KEYS` from the nearest feature of `axes` within `key_m` of each row's geometry (`at="point"`), or of a line's first coordinate (`at="start"`), or of its midpoint (`at="mid"`). Unmatched rows keep null keys. Adds `OBJECTID_2` when `second=True` is passed (keyword-only arg, default False): the nearest *other* feature within `key_m`.
  - `sdp_crs(root: Path) -> str`: WKT of the raw Eje Vial file's CRS via `pyogrio.read_info(...)["crs"]`.
  - `round_trip_error_m(axes_9377: gpd.GeoDataFrame, crs_wkt: str) -> float`: max coordinate shift after 9377 → `crs_wkt` → 9377.

- [ ] **Step 1: Add config**

```yaml
sdp_package:
  key_m: 1              # a row takes the keys of the nearest Eje Vial feature within this distance
  end_match_m: 0.01     # a dead end and a correction line's end are the same point within this
  round_trip_max_m: 0.01
  figure_window_m: 100  # half-width of a before/after panel
  contacto: null        # name/email for LEEME.txt, filled by Gregorio before sending
  examples:             # OBJECTID (CODIGO_ID for reubicacion_enlace) per figure; null = automatic
    extremo_suelto: null
    cruce_sin_nodo: null
    discontinuidad: null
    tramo_corto: null
    abierto: null
    reubicacion_enlace: null
```

- [ ] **Step 2: Copy the CRS fixture**: `uv run python -c "import pyogrio; print(pyogrio.read_info('data/raw/sdp_eje_vial/eje_vial.gpkg')['crs'])" > tests/fixtures/pcs_carmagbog.wkt`. It is a CRS definition (< 1 KB), not data.

- [ ] **Step 3: Write failing tests**

```python
def test_attach_keys_nearest_within_tolerance(): # point 0.3 m from feature 7 -> OBJECTID 7
def test_attach_keys_unmatched_keeps_row_null(): # point 5 m away, key_m 1 -> row kept, OBJECTID is NA
def test_attach_keys_second_feature_for_crossing(): # point on features 3 and 4 -> {OBJECTID, OBJECTID_2} == {3, 4}
def test_round_trip_under_1cm():                 # fixture WKT, 3 lines -> round_trip_error_m(...) < 0.01
```

- [ ] **Step 4: Run** `uv run pytest tests/test_sdp_package.py -v`. Expected: FAIL (module missing).
- [ ] **Step 5: Implement** with `gpd.sjoin_nearest(..., max_distance=key_m)`; for `OBJECTID_2`, `STRtree.query(..., predicate="dwithin")` excluding the first match.
- [ ] **Step 6: Run** tests. Expected: 4 PASS.
- [ ] **Step 7: Commit** `git commit -m "SDP package: config, feature keys and the SDP CRS"`

### Task 2: `problemas` and `correcciones`

**Files:** Modify `src/bogota_syntax/sdp_package.py`, `tests/test_sdp_package.py`

**Interfaces:**
- Consumes: `attach_keys`, `KEYS`.
- Produces:
  - `build_correcciones(layers: dict[str, gpd.GeoDataFrame], axes, cfg: dict) -> gpd.GeoDataFrame`: lines. Columns `tipo` (`ajuste` from `snaps`, `union` from `pairs`, `extension` from `extensions`, `conector` from `connectors`), `longitud_m`, `KEYS` (at `"start"`), geometry.
  - `build_problemas(layers, axes, network: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame`: points. Columns `tipo`, `estado`, `correccion`, `distancia_m`, `longitud_m`, `KEYS`, `OBJECTID_2`, geometry. Sorted with `estado == "abierto"` first.

Mapping (from `review.gpkg` layer → rows):

| Source | `tipo` | point | `correccion` | `distancia_m` / `longitud_m` |
| --- | --- | --- | --- | --- |
| `snaps` | `extremo_suelto` | line start | `ajuste` | `snap_m` |
| `crossings` | `cruce_sin_nodo` | as is | `division` | — |
| `removed` `why=stub` / `duplicate` | `tramo_corto` / `tramo_duplicado` | line midpoint | `eliminado` | `longitud_m` = line length |
| `dead_ends_classified` `status=critical` | `discontinuidad` | as is | `union` / `extension` / `conector` when a `pairs` / `extensions` / `connectors` line end is within `end_match_m`; `abierto` (empty) when a `dead_ends_final` critical point is within `end_match_m`; else `reubicacion_o_edicion` | length of the matched line (`gap_m`, `added_m`, `length_m`) |
| `network` pieces outside the largest connected component (same node rule as `foreground.components`) | `linea_aislada` | line midpoint | empty, `abierto` | `longitud_m` |

- [ ] **Step 1: Write failing tests** on a synthetic `layers` dict:

```python
def test_each_source_layer_maps_to_its_tipo():        # one row per source -> tipos as in the table
def test_discontinuidad_fixed_by_extension():         # dead end + extension starting there -> correccion "extension", estado "corregido"
def test_discontinuidad_still_open():                 # dead end also in dead_ends_final critical -> estado "abierto", correccion ""
def test_discontinuidad_fixed_elsewhere():            # no correction, not final -> "reubicacion_o_edicion"  (Review Focus 5)
def test_isolated_line_is_open():                     # network of 2 components -> 1 linea_aislada, abierto
def test_empty_layers_keep_schema():                  # connectors empty -> build_correcciones has same columns, 0 conector rows  (Review Focus 3)
def test_open_rows_first():                           # problemas.estado.iloc[0] == "abierto"
```

- [ ] **Step 2: Run**, expect FAIL. **Step 3: Implement.** **Step 4: Run**, expect 7 PASS.
- [ ] **Step 5: Commit** `git commit -m "SDP package: problems and corrections layers"`

### Task 3: Modelling layers, GeoPackage and the command

**Files:** Modify `src/bogota_syntax/sdp_package.py`, `src/bogota_syntax/cli.py`, `tests/test_sdp_package.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `build_decisiones(layers) -> gpd.GeoDataFrame`: points. `fusion_nodos` from `junctions_merged` (keys null); `reubicacion_enlace` from `centres`, each joined by containment to its `interchanges` polygon for `CODIGO_ID`, `NOMBRE`, and `origen` = `revision_manual` (`action == "relocate"`) or `regla` (`"relocate (rule)"`).
  - `build_ediciones(edits: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame`: lines, `edicion` = `agregada` / `retirada` from `edit`, `KEYS` as in the edits file, `longitud_m`. `None` → empty layer, same columns.
  - `counts(package: dict[str, gpd.GeoDataFrame]) -> dict[str, int]`: flat counts the note and the CLI use, keys `n_<tipo>`, `n_<tipo>_abierto`, `n_fusion_nodos`, `n_reubicacion_revision`, `n_reubicacion_regla`, `n_edicion_agregada`, `n_edicion_retirada`, `km_editados`, `n_sin_clave`.
  - `run(root: Path) -> dict[str, Any]`: checks inputs are fresh, builds the four layers, checks the round trip against `round_trip_max_m`, writes `data/processed/sdp_package/entrega_sdp_eje_vial_<YYYY-MM-DD>/eje_vial_revision.gpkg` in `sdp_crs(root)` with layer order `problemas`, `correcciones`, `decisiones_modelado`, `ediciones_manuales`; returns `counts | {"path": ...}`. The run date and the source dates come from `config/manifest.json` (`retrieved_at`, `ckan_metadata_modified` for `sdp_eje_vial` and `sdp_red_infraestructura_vial`).
- CLI `sdp-package`: prints one line per layer with its count, the unmatched count, the round-trip error, and the path.

- [ ] **Step 1: Write failing tests**

```python
def test_relocated_centre_gets_interchange_keys_and_origin(): # centre inside polygon CODIGO_ID "1084", action relocate -> origen "revision_manual"
def test_no_edits_file_gives_empty_layer():                   # build_ediciones(None) -> 0 rows, columns present  (Review Focus 3)
def test_stale_review_stops_run(tmp_path):                    # review.gpkg mtime < interim parquet mtime -> raises, message names "bogota-syntax foreground"  (Review Focus 4)
def test_gpkg_written_in_sdp_crs(tmp_path):                   # write tiny package -> pyogrio.read_info crs name contains "CarMAGBOG"; 4 layers in order
```

- [ ] **Step 2: Run**, expect FAIL. **Step 3: Implement**; put the file writing in `write_gpkg(package, path, crs_wkt)` so the last test needn't call `run`; each layer gets `layer_metadata={"DESCRIPTION": ...}` with the CC BY 4.0 notice and SDP attribution. **Step 4: Run**, expect PASS.
- [ ] **Step 5: Real run** `uv run bogota-syntax sdp-package`. Expected: `problemas` counts by `tipo` agree with ADR-0012's results (112 snaps, 45 crossings, 18 + 1 removed, 79 critical, 4 open dead ends + 1 isolated line), 0 unmatched or each one listed, round trip < 0.01 m. Any disagreement is a bug to fix, not a number to explain away.
- [ ] **Step 6: Commit** `git commit -m "SDP package: modelling layers, GeoPackage in PCS_CarMAGBOG, sdp-package command"`
- [ ] **Step 7: Stop for review.** Gregorio opens the GeoPackage in QGIS and picks the figure examples into `config/analysis.yaml`.

### Task 4: Figures

**Files:** Create `src/bogota_syntax/sdp_figures.py`, `tests/test_sdp_figures.py`; modify `pyproject.toml`, `uv.lock` (`uv add matplotlib`), `sdp_package.run`.

**Interfaces:**
- Consumes: the four layers, `axes` (original Eje Vial), `network` (foreground output), `polygons` (POT, EPSG:9377), `cfg["examples"]`, `cfg["figure_window_m"]`.
- Produces:
  - `pick_example(rows: gpd.GeoDataFrame, wanted: int | str | None, key: str) -> pd.Series | None`: the row whose `key` equals `wanted`; if `wanted` is None or not found (warn), the row nearest the median `distancia_m` (first row when it has none); `None` for an empty frame.
  - `overview(package, axes, path: Path) -> Path` (figure 1).
  - `before_after(focus: shapely.Point, axes, network, polygons, highlight: gpd.GeoDataFrame, caption: str, path: Path, window_m: float) -> Path`: two panels, left original axes, right network, `highlight` drawn on the right in the correction colour.
  - `single(focus, network, polygons, highlight, caption, path, window_m) -> Path` (figure 6).
  - `make_figures(package, axes, network, polygons, cfg, out_dir: Path) -> dict[str, Path | None]`: keys `fig1`…`fig7`; `None` for a type with no cases. Figures in EPSG:9377 (plot only; the GPKG CRS rule is about data). PNG, 200 dpi, width 16 cm.

- [ ] **Step 1: Write failing tests**

```python
def test_pick_example_by_id():                 # wanted 7 present -> row 7
def test_pick_example_missing_id_falls_back(): # wanted 999 absent -> warns, returns median row  (Review Focus 2)
def test_pick_example_empty_is_none():         # empty frame -> None
def test_make_figures_writes_pngs(tmp_path):   # synthetic package -> fig1..fig7 exist where cases exist; empty type -> None  (Review Focus 3)
```

- [ ] **Step 2: Run**, expect FAIL. **Step 3: `uv add matplotlib`, implement** (backend `Agg`). **Step 4: Run**, expect PASS.
- [ ] **Step 5: Real run**, then open the seven PNGs in `figuras/`. Each focus feature is centred and readable at print size.
- [ ] **Step 6: Commit** `git commit -m "SDP package: example figures"`

### Task 5: Note, LEEME and docs

**Files:** Create `src/bogota_syntax/templates/nota_metodologica.md`, `src/bogota_syntax/templates/LEEME.txt`; modify `sdp_package.run`, `CLAUDE.md`, `tests/test_sdp_package.py`.

**Interfaces:**
- Consumes: `counts(...)`, `make_figures(...)` paths, manifest dates.
- Produces: `render(template: Path, values: dict[str, Any]) -> str` using `string.Template.substitute` (a missing value raises, so no placeholder ships unfilled). `LEEME.txt` takes `$contacto` from config; while it is null the line reads "Contacto: (por completar)" and the CLI warns.

Note sections, in this order, with the design's content: 1 Qué es y qué no es + figura 1; 2 Limitaciones; 3 Método; 4 Resultados (table of `tipo` × total × corregidos × abiertos built from `counts`, then figures 2–7, each with a one-line caption, "sin casos" where a figure is `None`); 5 Cómo leer las capas, licencia (CC BY 4.0, attribution to the SDP), cómo repetirlo (the four commands from the design). At most four pages printed. Plain Spanish: direct, short sentences, no filler. Every acronym spelled out the first time (SDP, POT, CRS), as in `docs/glossary.md`.

- [ ] **Step 1: Write failing tests**

```python
def test_render_fills_every_placeholder():     # template "$a y $b", {"a":1,"b":2} -> "1 y 2"
def test_render_missing_value_raises():        # {"a":1} -> KeyError
def test_note_has_no_bare_digits_outside_placeholders(): # the template's prose, minus placeholders, section numbers, dates in commands and CRS names, has no digits
```

- [ ] **Step 2: Run**, expect FAIL. **Step 3: Write the templates and `render`; `run` writes `nota_metodologica.md`, `figuras/`, `LEEME.txt` next to the GPKG.** **Step 4: Run tests**, expect PASS.
- [ ] **Step 5: Real run** and read the note in the VS Code Markdown preview; export to PDF (print from the preview) as `nota_metodologica.pdf`. Check: four pages or fewer, every figure shows, the table matches the CLI counts.
- [ ] **Step 6: Docs**: add `uv run bogota-syntax sdp-package  # Spanish package for the SDP (ADR-0013) -> data/processed/sdp_package/` to the CLAUDE.md commands block.
- [ ] **Step 7: Lint and full suite**: `uv run ruff check . && uv run ruff format . && uv run pytest`. Expected: all pass.
- [ ] **Step 8: Commit** `git commit -m "SDP package: methodological note and LEEME in Spanish"`
- [ ] **Step 9: Stop for review.** Gregorio reads the PDF and checks the package in QGIS; he accepts ADR-0013 and decides whether and when to send.

## Not in this plan

The `sources` label bug in `foreground.apply_edits` (manual lines don't get `manual`): a separate small PR, because fixing it changes a pipeline output.
