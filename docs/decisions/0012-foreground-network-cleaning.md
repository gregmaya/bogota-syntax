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
   | 3 | Remove dead-end segments that are short, or that run alongside other lines (duplicates); repeat with step 7's merge until stable | dead-end segments | stub < 20 m; duplicate: > 50% of length within 5 m of other lines |
   | 4 | Classify dead ends (point 3) | dead ends | 1 m, 0.5 m |
   | 5 | Join two dead ends at their midpoint | mutual-nearest dead ends in the same or touching polygons, pointing opposite ways (≥ 135° apart) and not away from each other | 135° |
   | 6 | Extend onto the nearest line within a ±30° cone ahead, in growing steps; split and merge after every step | `critical` ends; the extension must stay inside the end's polygons plus their neighbours | 5 to 50 m in 5 m steps, ±30° |
   | 7 | Merge junctions closer than the limit into one at their weighted centre (`neatnet.consolidate_nodes`, dead ends kept) | junctions | 10 m |
   | 8 | Connect to the nearest junction in the search area, else to the nearest point of a line passing through it | `critical` ends still open; the connector must point ahead, run alongside no line for over 25% of its length, and stay inside the area (≤ 10 m outside for corner cuts) | ahead ≤ 90°, 2 m / 25% alongside, ≤ 10 m outside; connectors to a line ≤ 100 m, to a junction unlimited |
   | 9 | Split and merge into intersection-to-intersection segments (ADR-0009) | all | |
   | 10 | Straighten zig-zags, then Douglas-Peucker; a change is kept only if the line stays inside the polygons and crosses no other line; line ends never move | all | zig-zag: two turns > 60° within 30 m; Douglas-Peucker ≤ 2 m |

   "Split and merge" (steps 6, 7 and 9) means: split lines where an end lands on another line, then merge lines that meet end to end with nothing else there.

5. **Not in this step, on purpose:**
   - **Relocating interchange centres.** The method works where it fits: each approach line runs straight from the polygon edge to the least-squares meeting point of the approach directions. Applied to every "Enlace Vehicular" polygon, it did more harm than good. It waits for its own classification of which interchanges to rebuild.
   - **Roundabout simplification,** until the background is added.
   - **`neatnet.neatify` on the foreground.** It finds no artefact threshold on an arterial-only network. Set by hand, it removes whole blocks before it fixes much.
   - **`ESTADO` / `ESTADO_VIA`** (built vs planned). Ignored for now, to be added: a planned road can make a built dead end look critical.

6. **Output.** One file, one row per segment, the Eje Vial fields kept as published (CLAUDE.md rule 6), plus `sources`, which lists what touched each segment (`original`, `pair`, `extension`, `connector`), and `length_m`. A diagnostic file holds one layer per correction (snaps, crossings split, stubs and duplicates removed, dead ends classified, pairs, extensions, merged junctions, connectors, review) and the remaining dead ends with their class. File names are settled in the implementation PR.

7. **Implementation.** A new module and command, `bogota-syntax foreground`, ported from the prototype, with a test on a small fixture for each rule in point 4. **v1 is unchanged:** ADR-0010 still governs the network that centrality runs on, until a later ADR joins foreground and background.

## Results

TODO: step-by-step counts, produced by `bogota-syntax foreground` once ported. The prototype's figures are not reproducible from the repository, so they are not quoted here (CLAUDE.md rule 2).

## Alternatives considered

- **Clean the foreground with `neatnet.neatify` alone,** as for MVI (ADR-0005). Rejected: see point 5.
- **One global rule per correction** (extend every dead end up to a tolerance; connect every dead end to the nearest line). Rejected: these were the corrections that did damage in the prototype; classification is what made them safe.
- **Fix the foreground by hand.** Rejected as the main method: not reproducible, and the review layers already narrow manual work to a short list.
- **Use MVI's own arterials as the foreground.** Rejected: MVI draws most arterials as two carriageways, which is the duplication ADR-0010 is trying to remove.

## Consequences

- The foreground becomes a reproducible input for the next steps: using the polygons to remove the background lines that overrepresent arterials, then joining foreground and background (each its own ADR).
- "Classify, then correct" becomes the default for later cleaning steps, with interchange relocation as the first one waiting for its classification.
- By-product: a corrected Eje Vial that could be shared with the SDP, with each correction a traceable edit keyed by the original `OBJECTID` and `CODIGO_ID`. Not part of this ADR.
- Licences: both sources are CC BY 4.0, compatible with the project's ODbL outputs (ADR-0002); attribution to SDP goes in the README and the outputs' metadata.
- Follow-up work:
  - add `ESTADO`;
  - classify interchanges for centre relocation;
  - handle bridges in step 2;
  - add "foreground", "background" and the dead-end classes to `docs/glossary.md`.
