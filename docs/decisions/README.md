# Architecture Decision Records

One short file per decision, so readers can see *why* the project is built the way it is, not only *what* it does.

ADRs are immutable once accepted. To change a decision, write a new ADR that supersedes the old one and update the old one's status to `Superseded by ADR-XXXX`.

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-code-licence.md) | Code licence: MIT, with AGPL-3.0 dependencies noted | Accepted | 2026-11-21 |
| [0002](0002-output-data-licence.md) | Output data licence: ODbL 1.0 | Accepted | 2026-11-21 |
| [0003](0003-network-source.md) | Network source: official data inside Bogotá, OSM outside | Proposed | 2026-11-21 |
| [0004](0004-study-extent.md) | Study extent, buffer and live nodes | Proposed | 2026-11-21 |
| [0005](0005-cleaning-and-analysis.md) | Cleaning with neatnet, analysis with cityseer | Proposed | 2026-11-21 |
| [0006](0006-crs-and-formats.md) | CRS and file formats, same as bogota-pop | Accepted | 2026-11-21 |

New ADRs copy [template.md](template.md) and take the next number.
