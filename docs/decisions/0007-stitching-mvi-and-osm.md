# ADR-0007: One stitched network: MVI for Bogotá, OSM for 10 km around the urban area

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

ADR-0003 chose IDECA Malla Vial (MVI) inside Bogotá and OpenStreetMap (OSM) outside, with OSM everywhere as the fallback if the join proved too hard. After looking at both layers on the map (Gregorio, 2026-11-22), MVI is reliable inside Bogotá. So the fallback is not needed, and the remaining work is the join itself.

The first ingest fetched OSM only over the pilot's network extent (ADR-0004), so every new pilot area or the full city would need a new download and a new join.

Measured on 2026-11-22, from the first ingest and the SDP urban perimeter (`perimetro-urbano-bogota-d-c`, Decreto 555 de 2021, CC BY 4.0):

- The Bogotá boundary (IDECA *Municipio*, `MUNCODIGO = '11001'`) is 415 km long and encloses 1,633 km².
- Buffering all of Bogotá D.C. by 10 km gives 5,129 km², 3,496 km² of it outside the city, mostly around Sumapaz.
- The urban perimeter is 370 km² in 23 parts. Buffered by 10 km it covers 1,751 km²: 1,033 km² outside Bogotá and 347 km² of rural Bogotá.
- 4 of the 36 pilot polygons reach outside the urban perimeter, by 0.59 km² in total. As a result, 0.19 km² of the pilot's network extent falls outside the urban perimeter plus 10 km.
- Inside the pilot's network extent alone, 127 OSM edges cross the Bogotá boundary, mostly `residential` (70), `unclassified` (26) and `tertiary` (19). 178 MVI segments touch the boundary.
- MVI is not cut at the boundary: 45.9 km of its lines lie outside Bogotá.

## Decision

**Build one stitched network once, for the urban area plus 10 km. Each analysis clips its own network extent (ADR-0004) out of it.**

1. **Extent.** The stitch extent is the SDP urban perimeter buffered by 10 km (`stitch_margin_m: 10000` in `config/analysis.yaml`), united with the network extent of the current analysis. The union covers pilot polygons that reach past the perimeter. Code checks that the margin is at least the analysis buffer from ADR-0004. The urban perimeter becomes a new source, `sdp_perimetro_urbano`.
2. **Who owns which side.** Inside the Bogotá boundary, only MVI. Outside it, only OSM. The seam is the Bogotá boundary, not the urban perimeter: rural Bogotá inside the extent uses MVI too.
3. **Order: clean each side, then cut, then connect.**
   1. neatnet (ADR-0005) runs on MVI over the stitch extent ∩ Bogotá plus a 500 m overlap past the boundary.
   2. It runs separately on OSM over the stitch extent *outside* Bogotá plus a 500 m overlap inside it. OSM deeper inside Bogotá is not used, so it is neither downloaded nor cleaned.
   3. Each cleaned network is then cut at the Bogotá boundary.
   4. Each OSM loose end on the boundary is joined to the nearest MVI node within a snap tolerance by a straight connector, marked `source = "connector"`. Connectors are added last and never cleaned, so their lengths are exactly what the review layers show.
   5. The tolerance goes in `config/analysis.yaml` and is set after measuring the gaps between the two sides. Loose ends with no partner inside it are listed for review, not forced.
   6. Both overlap widths are one value, `clean_overlap_m: 500`, in `config/analysis.yaml`.
4. **Columns.** The stitched network keeps a `source` column (`mvi`, `osm`, `connector`) and each source's own ID (`OBJECTID` for MVI, `osmid` for OSM). Other field names stay as published (CLAUDE.md rule 6).
5. **No piece is lost in cleaning.** Outside Bogotá, OSM is a ring with the city as its hole. Some of its parts may connect to each other only through Bogotá, so on its own the OSM side can be several pieces, not one network. How many there are is measured on the first run, not assumed here. Before cleaning, every connected piece of each side is labelled, with its length and whether it touches the boundary. After cleaning, the same pieces are measured again. Any piece that disappears, or loses length beyond a tolerance set after the first run, is written to a review layer and stops the join. It is never dropped silently. The 500 m overlap means the cut happens after cleaning, so the loose ends at the boundary are not short dangles at the time neatnet runs and can't be removed by `min_dangle_length` (20 m by default in neatnet 0.1.6).
6. **Review layers.** The join writes these to `data/interim/join/`:
   - the boundary and the cut points;
   - the connectors, with their length;
   - unmatched OSM ends, and unmatched MVI ends near the boundary;
   - the pieces of each side before and after cleaning;
   - every piece of the stitched network that isn't connected to the main network.

   Centrality runs only after these have been checked. The stitched network is expected to be a single connected network, and any exception is listed.
7. **OSM is always the latest.** OSM is fetched from the live Overpass API, never with a date filter. Each download records in `config/manifest.json` when the query ran and the `timestamp_osm_base` that Overpass reports, which is the date of the OSM data actually served. `ingest osm_vias --force` clears the osmnx cache, so a forced run fetches current data instead of reusing an old response.

## Why clean before connecting

- **neatnet sees each side whole near the seam.** If the networks were cut and connected first, neatnet would meet two drawings of the same road along the seam, and how it treats that hasn't been tested. The 500 m overlaps keep each side's boundary streets away from the edge of the area neatnet cleans.
- **Simpler matching.** MVI draws one line per carriageway, and neatnet merges them. Cleaned first, a dual carriageway such as Autopista Sur meets OSM as one centreline, not as two lines that both claim the same OSM end.
- **Traceable seam.** Connectors are added after cleaning, so nothing moves them.
- **Cost.** neatnet runs twice, once per source, on areas that overlap by 500 m on each side of the boundary. This is still "neatnet runs once" in the sense of ADR-0005: each line that ends up in the network is cleaned once.
- **Risk.** Nothing cleans the seam itself, so small artefacts can stay there, such as a short triangle where two connectors meet. If the review layers show this, a neatnet pass on a narrow band around the boundary is the first fix to try. Connecting first and then cleaning everything is the second.

## Alternatives considered

- **Buffer all of Bogotá D.C. by 10 km.** Rejected by Gregorio: the extent would be about three times larger, mostly rural roads around Sumapaz that no urban analysis reaches.
- **Clean OSM over the whole stitch extent, Bogotá included.** Rejected by Gregorio: a large download and cleaning run for lines that are thrown away.
- **Connect first, then clean the stitched network once.** This would need only one neatnet run, and neatnet would tidy the seam. It's not the first choice because neatnet would move or merge the connectors, so the review layers would no longer show the real gaps. It's kept as the second fix if the seam review fails.
- **Snap by moving endpoints instead of adding connectors.** Rejected: it changes source geometry and hides the distance between the two sides.
- **SDP `clasificacion-del-suelo` for the urban area.** Rejected: its licence is CC BY-NC 4.0, which is not compatible with ODbL outputs (ADR-0002).
- **A dated OSM snapshot (Geofabrik extract or Overpass `[date:…]`).** Rejected by Gregorio: v1 uses current OSM and records the time of the query.

## Consequences

- New source `sdp_perimetro_urbano` in `config/sources.yaml`. It arrives in `PCS_CarMAGBOG` and is reprojected at ingest.
- `osm_vias` changes its extent from `network_extent` to the stitch extent outside Bogotá plus the 500 m overlap, and the extent step writes that polygon.
- Comparing MVI with OSM inside Bogotá now needs its own OSM query. It's not part of v1.
- A new step, `bogota-syntax join`, runs neatnet per source, checks the pieces, cuts, connects and writes the review layers.
- The OSM download will be larger than the pilot's. Its size is recorded in the manifest after the first run.
- Results can't be traced to an exact OSM edit. The manifest's `timestamp_osm_base` says which state of OSM was used.
- **Supersedes in part:** the OSM-only fallback in ADR-0003, whose choice of sources stays as it is. ADR-0003's status line notes the replaced clause.
