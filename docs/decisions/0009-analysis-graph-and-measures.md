# ADR-0009: Segment (dual) graph, simplest-path closeness and betweenness

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

The stitched network (ADR-0007, ADR-0008) is ready for analysis, and cityseer (ADR-0005) can analyse it in two ways:

- **Primal graph:** intersections are nodes and streets are edges, so results sit on intersections.
- **Dual graph** (`cityseer.tools.graphs.nx_to_dual`): every street segment becomes a node, and each pair of segments that meet at an intersection becomes an edge. Results sit on the segments themselves. The turning angle between segments is part of the graph, which is what simplest-path (angular) analysis needs.

When this was decided, the stitched network still had 4,452 points joining exactly two lines, which are not intersections, and 402 lines that loop back to their own start (measured 2026-11-22).

## Decision

1. **Unit of analysis: the street segment from intersection to intersection, on the dual graph.** Points joining exactly two lines are merged away before analysis, so each segment runs from one intersection or dead end to the next. Segments are not decomposed into shorter pieces (no `nx_decompose`).
2. **Measures: simplest path only.** Closeness and betweenness by `centrality_simplest`, at all six distances in `config/analysis.yaml` (400, 800, 1200, 1600, 2000, 5000 m). Distance thresholds are in metres, and routes are chosen by angular cost. The exact metric columns cityseer writes are listed in the pilot run's output, not guessed here.
3. **No direction.** The graph is undirected, cityseer's default: every segment can be walked both ways. `MVISVIA` and OSM `oneway` are kept as attributes, but not used.
4. **No weighting.** Every segment counts the same (`segment_weighted=False`, no sampling). Weighting by the population model in `bogota-pop` is future work and needs its own ADR.
5. **Islands stay.** Pieces not connected to the main network are analysed like the rest, and every segment carries `piece` and `in_main` so the viewer and readers can tell them apart. Fixing them is future work.
6. **Live and dead segments** follow ADR-0004: segments in the live area are reported, and segments in the buffer are routed through only (`set_boundary`).

## Alternatives considered

- **Primal graph, with values averaged onto segments.** Rejected: values belong to intersections, and angles between segments enter only indirectly.
- **Shortest path as well as simplest.** Not in v1. It can be added later with the same graph.
- **Directed graph using `MVISVIA` and `oneway`.** Rejected for v1: the reading is a pedestrian one, and direction data exists only for MVI and partly for OSM.
- **Decomposing segments into fixed lengths (for example 50 m).** Rejected: long segments would weigh more, and results would no longer be per street segment.

## Consequences

- A finishing step (`bogota-syntax network`) produces the segment network: lines merged from intersection to intersection, a stable `segment_id`, `piece` and `in_main`, and source attributes recovered where neatnet drew new lines.
- **The network is vehicular streets only.** The OSM filter excludes footways and paths, and MVI draws carriageways, but the reading is pedestrian. Adding pedestrian paths would be a later change with its own ADR.
- Looping segments (`is_loop`) are kept and flagged. cityseer drops loops shorter than 50 m by default (`drop_self_loops_dist`). How to treat them is settled in the pilot run.
- Segment length is not used as a weight, so a 300 m block face and a 20 m link count the same as destinations.
