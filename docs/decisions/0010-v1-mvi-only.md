# ADR-0010: v1 network is MVI only; the stitched network is shelved

- **Status:** Accepted
- **Date:** 2026-11-22
- **Supersedes for v1:** ADR-0003 (sources), ADR-0007 (stitching MVI and OSM), ADR-0008 (SDP arterial axes)

## Context

ADR-0007 and ADR-0008 were implemented city-wide on 2026-11-22: neatnet on each side, the SDP axes swapped in for MVI arterials, OSM joined at the Bogotá boundary, and the result finished into intersection-to-intersection segments (ADR-0009). Reviewing the result in QGIS, Gregorio found SDP axes and MVI streets overlapping along the main arterials. Measured on the finished network:

- 157 km of MVI (2,713 segments) lies with at least 80% of its length within 20 m of an SDP axis; 117 km within 10 m, 193 km within 30 m.
- Almost all of it is typed as local streets (`KR` 1,269, `CL` 1,008, `TV` 225, `DG` 184 segments), not `AC`/`AK`. The removal rule of ADR-0008 only removes `AC`/`AK` and untyped lines, so these parallel lines stayed, and the axis was laid on top of them. Each such arterial is drawn twice, which would split its flows and distort simplest-path centrality.

Fixing this needs a better rule for which MVI lines an axis replaces, and the stitched pipeline has several other parts that still need work (listed below). v1 needs a centrality output first.

## Decision

**v1 uses one source: IDECA Malla Vial (MVI), cleaned by neatnet, inside Bogotá only. No OSM, no SDP axes, no other data.**

1. **Network.** MVI as cleaned by `bogota-syntax clean mvi` (ADR-0005), clipped to the Bogotá boundary. Dead ends are then extended onto a line within 10 m (`neatnet.extend_lines`, `extend_lines_m`), which only uses MVI itself. The result is finished into intersection-to-intersection segments as in ADR-0009. The mode is set in `config/analysis.yaml` (`network.mode: mvi_only`).
2. **Analysis** is as in ADR-0009: dual graph, simplest-path closeness and betweenness at six distances, undirected, unweighted, islands kept and flagged.
3. **Edge effect at the city limit.** Without OSM, there are no streets outside Bogotá. For the pilot, 20% of the live area (75.5 of 370.1 km²) lies outside Bogotá, and 185.5 of the 294.6 km² inside it is within 5 km of the boundary, where larger-distance values are biased low. Every segment carries `boundary_dist_m`, its distance to the Bogotá boundary. Outputs and the viewer state the bias rather than hide it.
4. **The stitched pipeline stays in the repository**, unused in v1: `arterials.py`, `join.py`, the `arterials` and `join` commands, the `osm_vias` and `sdp_eje_vial` sources, and `scripts/adr0008_interchanges.py`. `network.mode: stitched` rebuilds it. ADR-0007 and ADR-0008 remain the record of how it works.

## What the stitched pipeline taught us (for automating it later)

Measured 2026-11-22, city-wide, unless stated:

- **Boundary join (ADR-0007) worked.** OSM crosses the boundary 159 times inside the stitch extent. At a 25 m snap, 131 were joined, 121 of them to the same street cut on the MVI side. Going to 50 m or 100 m added under 15 joins and no connectivity.
- **neatnet keeps attributes**, adds `_status`, and draws new lines without any. Recovering attributes from the raw line with most overlap within 15 m filled 2,383 of about 2,830 MVI lines and 622 of 647 OSM lines.
- **Merged carriageways keep one side's attributes,** so `MVISVIA` and `MVINUMC` describe one carriageway only.
- **SDP axes are not topologically closed.** 227 axis ends meet nothing; 170 of them are within 5 m of another line. Closing gaps within 10 m fixed 191.
- **Axes must go in after neatnet** (ADR-0008 test), or neatnet bends them near leftover ramps.
- **Removing arterial lines by type is not enough.** It missed 157 km of local-typed parallel lines (above). Removing service roads also cut off local streets; restoring removed lines that were the only link fixed 21 of them.
- **Islands are mostly in MVI itself.** Raw MVI, with T-junctions joined, has 180 islands (219 km). Our steps created 12 small ones (2.5 km). `extend_lines` at 10 m took the MVI side from 140 pieces to 94.
- **Duplicates arise** when connectors and axes coincide with existing lines: 747 exact and 51 within 1 cm. Merging lines into segments must come after removing them.

**To make the stitched network work:**
- Match MVI lines to the axis they duplicate by geometry (parallel, within a distance, along most of their length), whatever their type.
- Check the bridge rule on a real flyover without ramps.
- Test the removal and swap on the whole of one arterial, not only at interchanges.

## Alternatives considered

- **Fix the overlap now and keep the stitched network for v1.** Rejected: it delays the first centrality output, and the fix needs its own testing.
- **OSM only.** Rejected: MVI is more reliable inside Bogotá (ADR-0007), and OSM-only has the same arterial complexity.
- **MVI without neatnet.** Rejected: dual carriageways would double every arterial, the same problem in another form.

## Consequences

- v1 results are for streets inside Bogotá only, with a known edge effect near the boundary, flagged per segment.
- The OSM and SDP downloads stay in `config/sources.yaml` and the manifest, but v1 outputs don't depend on them. Outputs remain ODbL (ADR-0002) until a release made only from CC BY sources is reconsidered in its own ADR.
- ADR-0007 and ADR-0008 are marked superseded for v1, not deleted.
