# Architecture Decision Records

One short file per decision, so readers can see *why* the project is built the way it is, not only *what* it does.

ADRs are immutable once accepted. To change a decision, write a new ADR that supersedes the old one and update the old one's status to `Superseded by ADR-XXXX`.

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-code-licence.md) | Code licence: MIT, with AGPL-3.0 dependencies noted | Accepted | 2026-11-21 |
| [0002](0002-output-data-licence.md) | Output data licence: ODbL 1.0 | Accepted | 2026-11-21 |
| [0003](0003-network-source.md) | Network source: official data inside Bogotá, OSM outside, OSM-only fallback | Accepted (fallback superseded by 0007; `eje-vial` exclusion by 0008) | 2026-11-21 |
| [0004](0004-study-extent.md) | Study extent, buffer and live nodes | Accepted | 2026-11-21 |
| [0005](0005-cleaning-and-analysis.md) | Cleaning with neatnet, analysis with cityseer | Accepted | 2026-11-21 |
| [0006](0006-crs-and-formats.md) | CRS and file formats, same as bogota-pop | Accepted | 2026-11-21 |
| [0007](0007-stitching-mvi-and-osm.md) | One stitched network: MVI for Bogotá, OSM for 10 km around the urban area | Accepted; shelved for v1 by 0010 | 2026-11-22 |
| [0008](0008-arterial-axes-as-guide.md) | SDP arterial axes as the geometry of built arterials inside Bogotá | Accepted; shelved for v1 by 0010 | 2026-11-22 |
| [0009](0009-analysis-graph-and-measures.md) | Segment (dual) graph, simplest-path closeness and betweenness | Accepted | 2026-11-22 |
| [0010](0010-v1-mvi-only.md) | v1 network is MVI only; the stitched network is shelved | Accepted | 2026-11-22 |

New ADRs copy [template.md](template.md) and take the next number.
