# ADR-0012: Foreground network from SDP Eje Vial, cleaned with the POT arterial polygons; classify before correcting

- **Status:** Proposed
- **Date:** 2026-11-24
- **Related:** ADR-0008 (SDP arterial axes, shelved), ADR-0009 (segments), ADR-0010 (v1 is MVI only)

## Context

The longer-term network has two layers. The **foreground** is the arterial grid: the Secretaría Distrital de Planeación (SDP) Eje Vial axes of the Plan de Ordenamiento Territorial (POT, Decreto 555 de 2021). The **background** is every other street, from the Malla Vial Integral (MVI) of IDECA. ADR-0010 shelved the first attempt at combining them because MVI lines parallel to the arterials stayed in and each arterial was drawn twice. ADR-0010 also asked for a geometric rule for which MVI lines an arterial replaces.

The SDP also publishes the **Red de Infraestructura Vial arterial polygons** for the same POT: the full width of each arterial, cut into stretches between avenues, with the interchanges as their own polygons ("Enlace Vehicular …"). They give that geometric rule for free. A background line lying inside an arterial polygon is overrepresenting the arterial. The polygons also say, for any foreground dead end, whether the corridor carries on.

Before the polygons can select background lines, the foreground has to be a network. As published, Eje Vial is not one: ADR-0010 found 227 axis ends that meet nothing, 170 of them within 5 m of another line. Lines also cross without sharing a point, some dead-end branches double an existing line, and some lines step sideways in short zig-zags.

Prototyping the cleaning in QGIS (Quantum GIS) taught one thing above all. **A correction applied everywhere does damage where it doesn't belong:**

- extending every dead end at growing tolerances connected roads that really end;
- connecting by distance alone joined two ends that both pointed into a roundabout, and added connectors that loop back on a road;
- relocating every interchange centre broke as many junctions as it fixed.

Each worked once it was limited to the places a classification picked out.

## Decision

**Build the foreground network from SDP Eje Vial in one cleaning step. The step uses the POT arterial polygons to decide where each correction applies. Every correction runs only on what a classification selects, and is written out as its own layer for review.**

1. **Principle: classify, then correct.** Each correction states which features it may touch and why. Everything else is left as published. Each correction's output is kept for review, and the cases a rule can't settle go to a review layer rather than being forced.

2. **New source:** `sdp_red_infraestructura_vial`, the Red de Infraestructura Vial arterial polygons (SDP, POT Decreto 555 de 2021, CC BY 4.0, CKAN dataset `red-infraestructura-vial-bogota-d-c`). It arrives in `PCS_CarMAGBOG` and is reprojected to EPSG:9377 at ingest. Each polygon gets `n_neighbours`: the number of other polygons within 0.5 m.

3. **Dead-end classification.** A dead end takes the highest `n_neighbours` among the polygons within 1 m:
   - `critical` (2 or more): the corridor carries on, so the line should too;
   - `corridor_end` (0 or 1): the avenue itself stops there;
   - `no_polygon`: nothing says it should connect.

   Only `critical` dead ends are extended or connected (steps 6 and 8 below).

4. **The cleaning protocol**, in order. Every parameter goes in `config/analysis.yaml`:

   | Step | What it does | Applies to | Parameters |
   | --- | --- | --- | --- |
   | 0 | Explode, drop duplicate and zero-length lines | all | |
   | 1 | Snap each dead end onto another line's end, else onto the nearest point of a line | dead ends with a gap below the limit, any class | 5 m |
   | 2 | Split at T-junctions and at every crossing | all (bridges are not told apart yet) | |
   | 3 | Remove dead-end segments that are short, or that run alongside other lines (duplicates, one per pass, so two lines beside each other don't both go); repeat with the merge until stable | dead-end segments | stub < 20 m; duplicate: > 50% of length within 5 m of other lines |
   | 4 | Classify dead ends (point 3) | dead ends | 1 m, 0.5 m |
   | 5 | Join two dead ends at their midpoint | mutual-nearest dead ends in the same or touching polygons, pointing opposite ways (≥ 135° apart) and not away from each other | 135° |
   | 6 | Extend onto the nearest line within a ±30° cone ahead, in growing steps; split and merge after every step | `critical` ends; the extension must stay inside the end's polygons plus their neighbours | 5 to 50 m in 5 m steps, ±30° |
   | 7 | Merge junctions closer than the limit into one at their weighted centre (`neatnet.consolidate_nodes`, dead ends kept) | junctions | 10 m |
   | 8 | Connect to the nearest junction in the search area, else to the nearest point of a line passing through it | `critical` ends still open; the connector must point ahead, run alongside no line for over 25% of its length, and stay inside the area (≤ 10 m outside for corner cuts) | ahead ≤ 90°, 2 m / 25% alongside, ≤ 10 m outside; connectors to a line ≤ 100 m, to a junction unlimited |
   | 9 | Split and merge into intersection-to-intersection segments (ADR-0009) | all | |
   | 10 | Straighten zig-zags, then Douglas-Peucker; a change is kept only if the line stays inside the polygons and crosses no other line; line ends never move | all | zig-zag: two turns > 60° within 30 m; Douglas-Peucker ≤ 2 m |
   | 11 | Relocate the interchange centre: drop the line parts inside the polygon and run each approach straight from the edge to the least-squares meeting point of the approach directions | "Enlace Vehicular" polygons whose decision in `config/enlace_decisions.csv` is `relocate`; without a decision, the rule in point 5 | approach direction over 30 m |
   | 12 | Apply reviewed manual edits: remove the lines listed, add the lines drawn; nothing is merged afterwards | `config/foreground_edits.geojson` (from `scripts/make_foreground_edits.py`); a removal that matches no line is reported stale | match within 0.01 m |

   "Split and merge" (steps 6, 7 and 9) means: split lines where an end lands on another line, then merge lines that meet end to end with nothing else there.

5. **Interchange centres (step 11): decisions first, a rule as fallback.** Applied to every "Enlace Vehicular" polygon, relocation did more harm than good. Gregorio then labelled 409 of the 456 interchanges in QGIS, judging whether the network at each one was right after a test run (moved or not). No geometric rule reproduced those judgements cleanly. Of the 79 single-junction relocations in the test run, 45 were right and 34 wrong. The best feature, how well the approach lines meet at one point relative to the interchange's size, separated them with an AUC of 0.77; at the threshold chosen below it keeps 44 of them, 33 right and 11 wrong (`scripts/adr0012_relocation_labels.py`). So:
   - **The labels are the decisions**, kept in `config/enlace_decisions.csv` (made by `scripts/make_enlace_decisions.py`): `relocate` (relocated and right), `keep` (not relocated and right, or relocated and wrong), `review` (not relocated and wrong: relocation alone doesn't fix it). Each row is keyed by `CODIGO_ID`, the polygon's representative point and its area, because `CODIGO_ID` is not unique and SDP may redraw polygons. A decision that no longer matches a polygon is reported as stale and not applied.
   - **Interchanges without a decision** use a rule fitted to the labels, and are flagged for review: one junction, relocate if the centre moves at least 10 m (a smaller move isn't worth losing the original geometry) and the approaches meet within 0.07 × √area (RMS distance of the approach lines to the new centre); two or more junctions, collapse into one if the farthest is within 0.20 × √area of the new centre. Three or more junctions are otherwise left alone.

6. **Manual edits (step 12).** After reviewing the flagged interchanges, Gregorio redrew a few places in QGIS. Those edits are kept as a reviewed patch, `config/foreground_edits.geojson`: the lines to remove and the lines to add, with exact coordinates, made by `scripts/make_foreground_edits.py` from the edited file and the pipeline's output without edits. The step applies them last and merges nothing afterwards, so the output is the edited network itself. A removal that no longer matches a line (for example after an upstream change) is reported, not forced. A rerun therefore reproduces the edited network instead of overwriting it.

7. **Not in this step, on purpose:**
   - **Roundabout simplification,** until the background is added.
   - **`neatnet.neatify` on the foreground.** It finds no artefact threshold on an arterial-only network. Set by hand, it removes whole blocks before it fixes much.
   - **`ESTADO` / `ESTADO_VIA`** (built vs planned). Ignored for now, to be added: a planned road can make a built dead end look critical.

8. **Output.** `data/processed/foreground.parquet` (and the same as `foreground.gpkg` for QGIS), one row per segment, the Eje Vial fields kept as published (CLAUDE.md rule 6), plus `sources`, which lists what touched each segment (`original`, `pair`, `extension`, `connector`, `relocated`, `manual`), and `length_m`. `data/interim/foreground/review.gpkg` holds one layer per correction (snaps, crossings split, stubs and duplicates removed, dead ends classified, pairs, extensions, merged junctions, connectors, review), the remaining dead ends with their class, and the interchanges with their measures, decision, action and `needs_review`, plus the new centres.

9. **Implementation.** `src/bogota_syntax/foreground.py` and the command `bogota-syntax foreground`, parameters under `foreground:` in `config/analysis.yaml`, and a test on a small synthetic layout for each rule (`tests/test_foreground.py`). The ported step reproduces the prototype's network exactly. **v1 is unchanged:** ADR-0010 still governs the network that centrality runs on, until a later ADR joins foreground and background.

## Results

From `bogota-syntax foreground` on 2026-11-25, Eje Vial as ingested on 2026-11-22 and the polygons on 2026-11-24 (1,414 polygons):

| Step | Result | Dead ends (critical / corridor_end / no_polygon) |
| --- | --- | --- |
| 0. Input | 1,235 lines | 238 / 15 / 19 |
| 1. Snap | 112 ends moved | |
| 2. Split | 45 crossings split | |
| 3. Remove | 18 stubs, 1 duplicate | |
| 4. Classify | | 79 / 13 / 15 |
| 5. Pairs | 7 joined | |
| 6. Extend | 55 extensions; 17 of them at the 10 m step | |
| 7. Merge junctions | 32 junctions moved | |
| 8. Connect | 4 to a junction, 1 to a line; 5 to review | |
| 10. Simplify | 16 jogs straightened; vertices 33,925 → 11,565 | |
| 11. Interchange centres | 59 relocated: 54 by decision, 5 by the rule; 340 kept and 15 left for review by decision; 42 kept by the rule; 0 stale decisions | |
| 12. Manual edits | 46 lines removed, 36 added (4.4 km redrawn); 0 stale | |
| Final | 1,016 segments, 1,074.3 km, 2 connected pieces, 0 crossings without a shared point | 4 / 13 / 15 |

The 4 `critical` dead ends left are review cases. Gregorio checked them in QGIS and accepted them as open: missing road segments in the source data, and corridors whose polygons carry on past where Eje Vial stops. A fifth, inside the Congreso Eucarístico / Ciudad Montes / Constitución interchange, goes when that interchange is relocated (a decision Gregorio labelled right). The second connected piece is a single isolated line, left for the background network to reach.

36 interchanges were flagged for review: 14 labelled `review` that hold a junction, and 22 without a decision. Gregorio reviewed them on 2026-11-25 and fixed by hand the ones that needed it (step 12); the output reproduces his edited network exactly, geometry for geometry.

## Alternatives considered

- **Clean the foreground with `neatnet.neatify` alone,** as for MVI (ADR-0005). Rejected: see point 5.
- **One global rule per correction** (extend every dead end up to a tolerance; connect every dead end to the nearest line). Rejected: these were the corrections that did damage in the prototype; classification is what made them safe.
- **Fix the foreground by hand.** Rejected as the main method: not reproducible, and the review layers already narrow manual work to a short list.
- **Use MVI's own arterials as the foreground.** Rejected: MVI draws most arterials as two carriageways, which is the duplication ADR-0010 is trying to remove.

## Consequences

- The foreground becomes a reproducible input for the next steps: using the polygons to remove the background lines that overrepresent arterials, then joining foreground and background (each its own ADR).
- "Classify, then correct" becomes the default for later cleaning steps. Where geometry alone can't classify well enough (interchange centres), a reviewed decision table, versioned in `config/`, is the classification.
- By-product: a corrected Eje Vial that could be shared with the SDP, with each correction a traceable edit keyed by the original `OBJECTID` and `CODIGO_ID`. Not part of this ADR.
- Licences: both sources are CC BY 4.0, compatible with the project's ODbL outputs (ADR-0002); attribution to SDP goes in the README and the outputs' metadata.
- Follow-up work:
  - add `ESTADO`;
  - fold the reviewed interchanges into `config/enlace_decisions.csv`, so later SDP updates keep their decisions;
  - handle bridges in step 2;
