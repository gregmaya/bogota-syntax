# ADR-0008: SDP arterial axes as the geometry of built arterials inside Bogotá

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

MVI draws every carriageway, ramp and loop of an interchange. neatnet (ADR-0005) merges parallel carriageways, but at interchanges the cleaned arterial still follows the loops and slip roads (Calle 72 × Avenida 68, reviewed by Gregorio, 2026-11-22). Shortest-path centrality is barely affected. Simplest-path (angular) centrality is: every bend through a loop counts as a change of direction a driver on the main road doesn't make.

The SDP `eje-vial` layer draws each arterial of the Plan de Ordenamiento Territorial (POT) as one straight axis (1,235 lines once multi-part lines are split, CC BY 4.0). ADR-0003 kept it out of v1, because its `ESTADO_VIA` codes aren't decoded and some axes are projected roads.

Measured on 2026-11-22: the share of each code's axis length that has a cleaned MVI line nearby.

| `ESTADO_VIA` | km | within 10 m | within 25 m | within 50 m |
| --- | --- | --- | --- | --- |
| 0 | 330 | 35% | 42% | 45% |
| 19 | 121 | 73% | 84% | 91% |
| 20 | 451 | 83% | 94% | 98% |
| 21 | 172 | 91% | 97% | 99% |

Where an axis runs along a built road, the two are usually within 10 m of each other. This suggests 20 and 21 are built roads and 0 is mostly projected, but it doesn't prove what the codes mean.

neatnet only adds a node where a line *ends* on another (`fix_topology`, `induce_nodes`). Two lines that cross without ending on each other stay unconnected, as a bridge would be.

## Decision

**Inside Bogotá, built arterials take their geometry from the SDP axes. The axes go in after neatnet has cleaned MVI, replacing the cleaned arterial lines, and neatnet does not run again.**

1. **Which axes.** An axis line is used if at least `min_axis_on_mvi` (0.9) of its length lies within `axis_match_m` (25 m) of raw MVI. The choice is made from the geometry, not from `ESTADO_VIA`, so projected roads stay out without decoding the codes. With these values, 1,104 of the 1,235 axis lines are used, 774 km. Each axis keeps its `ESTADO_VIA`, which is recorded but not used.
2. **What is removed from cleaned MVI.**
   1. Every line with at least half its length inside `corridor_m` (60 m) of a selected axis is removed if its `MVITIPO` is `AC` or `AK`, or if it has no type. Untyped lines are blank in MVI or new lines drawn by neatnet, and inside the corridor they are mostly ramps and merged carriageways.
   2. After that, any piece of the remaining network that lies entirely within `ramp_zone_m` (150 m) of an axis, and only touched removed lines, is removed too. These are loops and ramps typed as local streets, such as the cloverleaf at Calle 26 × Avenida 68.
3. **Reconnecting.** A remaining line that touched a removed line is joined to the axis. If it crosses the axis, it is split there, and the loose part inside the corridor is dropped. If it ends short of the axis, a straight connector (`source = "axis_connector"`) goes to the nearest point on the axis, within `corridor_m`. Lines that crossed the corridor without touching a removed line stay unconnected, so underpasses and bridges stay as they were.
4. **Axis against axis.** Two axes are joined where they cross only if their removed lines were connected to each other, which means the interchange has ramps. Otherwise they cross as a bridge.
5. **Nodes, not a second cleaning.** `neatnet.induce_nodes` then splits the axes where connectors and split lines end on them. Lines from the axes are marked `source = "sdp_eje_vial"`. The settings go in an `arterials:` block in `config/analysis.yaml`.

## Interchange test (2026-11-22)

Seven interchanges were run both ways: axes inserted into raw MVI before neatnet, and axes inserted into cleaned MVI after it. The script is `scripts/adr0008_interchanges.py`, and each window is 900 m square. "Axis kept" is the share of axis length that still has a network line within 5 m. "Dead ends" counts line ends that meet no other line, edges of the window included.

| Interchange | Axis kept, before neatnet | Axis kept, after neatnet | Dead ends: now / axes after neatnet |
| --- | --- | --- | --- |
| Calle 72 × Avenida 68 | 1.00 | 1.00 | 68 / 68 |
| Calle 26 × Avenida 68 | 0.70 | 1.00 | 43 / 39 |
| Calle 26 × NQS | 1.00 | 1.00 | 63 / 63 |
| Autopista Norte × Calle 100 | 1.00 | 1.00 | 44 / 42 |
| Calle 80 × Avenida Boyacá | 0.97 | 1.00 | 51 / 52 |
| Avenida Américas × Avenida 68 | 0.81 | 1.00 | 37 / 34 |
| NQS × Autopista Norte (added at Gregorio's request) | 0.90 | 1.00 | 54 / 49 |

The two orders differ where ramps are left next to an axis. When neatnet runs after the axes go in, it treats the small enclosed shapes between leftover ramps and the axis as clutter, and redraws the axis through them. Inserting the axes after cleaning keeps them exactly, without adding dead ends. At all seven sites, the axes are joined at their crossings, which is right because each interchange has ramps. At NQS × Autopista Norte, six avenues meet within the window and all are joined. None of the seven tests a flyover without ramps, so the bridge rule in point 4 is not yet checked against real data.

**Known effect:** along arterials with service roads (Autopista Norte, Avenida Américas), the service roads are typed `AK`/`AC` and are removed with the main carriageways. Local streets that met the service road now meet the axis through a connector of up to 60 m. Access to the arterial becomes more direct than it is on the ground. Gregorio accepted this on 2026-11-22: service roads are removed with the arterial.

## Alternatives considered

- **Tune neatnet's artifact thresholds** so it removes the loops itself. Rejected: the loops are as large as real blocks, so thresholds large enough to catch them would also merge real blocks.
- **Insert the axes into raw MVI, then run neatnet once.** This was tried first. Rejected because neatnet then bends axes near leftover ramps: Calle 26 × Avenida 68 kept only 70% of its axis length (table above).
- **Edit the cleaned network and run neatnet again.** This was Gregorio's first framing. It's unnecessary: `induce_nodes` adds the nodes the edit needs, and a second full run would bend axes for the same reason as above.
- **Use the axes only for angles in the analysis, and keep MVI geometry.** cityseer derives angles from the geometry it is given, so this would need a parallel graph. Rejected as more complex.
- **Leave interchanges as neatnet draws them.** Rejected for simplest-path measures (above), and it's the baseline the test compares against.

## Consequences

- `sdp_eje_vial` becomes a source in `config/sources.yaml` (CC BY 4.0, compatible with ODbL). ADR-0003's point 4 ("no `eje-vial` in v1") is superseded for built arterials only. Projected axes and scenarios are still out of v1.
- The pipeline order inside Bogotá becomes: neatnet on MVI (ADR-0007), then the arterial edit, then the cut and connectors at the boundary.
- Arterial geometry inside Bogotá follows the POT axis, not the built carriageway. Where the two differ, the difference is within the 10–25 m shown above.
- The axes stop at the Bogotá boundary. Outside it, OSM arterials keep their own geometry.
