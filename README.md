# bogota-syntax

Open, reproducible street-network centrality for Bogotá D.C., published as map tiles for the Bogotá viewer.

[Español](README.es.md)

> Work in progress (Phase 0: setup). See [docs/decisions/](docs/decisions/) and the [glossary · glosario](docs/glossary.md).

## What it does

This repo builds a street network for Bogotá, computes centrality measures on it, and publishes the results as PMTiles that the companion viewer ([gregmaya/bogota-pop-viewer](https://github.com/gregmaya/bogota-pop-viewer)) draws without any per-layer code.

The method in short:

1. Take the official street centrelines of Bogotá (IDECA Malla Vial) and clean them with [neatnet](https://uscuni.org/neatnet/). v1 uses this one source only, so the network stops at the city limit and values near it are biased low; each segment records its distance to the boundary (ADR-0010). Joining OpenStreetMap (OSM) outside the city was built and tested, and is kept for a later version (ADR-0007, ADR-0008).
2. Merge the network into street segments from intersection to intersection.
3. Compute simplest-path closeness and betweenness on the segment graph with [cityseer](https://cityseer.benchmarkurbanism.com/) (ADR-0009). Results are reported only inside the study area; the buffer is used for routing only.

The first stages cover a selection of RENOBO urban renewal projects in central Bogotá. The whole city comes later. Why each choice was made is recorded as an Architecture Decision Record (ADR) in [docs/decisions/](docs/decisions/).

## Data sources

| Source | Publisher | Used for | Licence |
| --- | --- | --- | --- |
| [Mapa de Referencia](https://datosabiertos.bogota.gov.co/dataset/mapa-de-referencia), layer *Malla Vial* | IDECA / UAECD | Current street network inside Bogotá; city boundary | CC BY 4.0 |
| [Perímetro urbano](https://datosabiertos.bogota.gov.co/dataset/perimetro-urbano-bogota-d-c) | SDP | Urban area, which sets how far the network reaches (urban area + 10 km) | CC BY 4.0 |
| [Eje vial](https://datosabiertos.bogota.gov.co/dataset/eje-vial-bogota-d-c) | SDP | Geometry of built arterials inside Bogotá (ADR-0008, not used in v1); projected roads for later scenarios | CC BY 4.0 |
| [Red infraestructura vial](https://datosabiertos.bogota.gov.co/dataset/red-infraestructura-vial-bogota-d-c) | SDP | Road reserve corridors, for reference | CC BY 4.0 |
| [Proyecto de RenoBo](https://datosabiertos.bogota.gov.co/dataset/proyecto-de-renobo) | RENOBO | Pilot study areas | CC BY 4.0 |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | OSM contributors | Street network outside Bogotá (not used in v1) | ODbL 1.0 |

Bogotá's open-data portal runs on [CKAN](https://docs.ckan.org/en/2.10/api/). Its API gives the licence, version and download URLs of each dataset, which ingest will use to record provenance:

```bash
curl "https://datosabiertos.bogota.gov.co/api/3/action/package_show?id=eje-vial-bogota-d-c"
```

## Future work

- **Public transport.** TransMilenio publishes the SITP (Sistema Integrado de Transporte Público) timetable as [GTFS](https://datosabiertos.bogota.gov.co/dataset/especificacion-gtfs-general-transport-feed-specification-sitp) (General Transit Feed Specification). With it, the analysis could add access to stops and stations, or travel-time centrality across walking and transit. The feed is licensed CC BY-SA 4.0, which conflicts with the ODbL outputs (ADR-0002). Using it needs its own decision first.
- **Scenarios.** Compare the current network with the projected roads of the Plan de Ordenamiento Territorial (POT, Decreto 555 de 2021), using the SDP road axes.
- **Morphology.** Measures of urban form from [momepy](https://docs.momepy.org/), such as block, plot and building metrics alongside centrality.

## Development setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gregmaya/bogota-syntax.git
cd bogota-syntax
uv sync
uv run pre-commit install   # once per clone
uv run pytest
```

## Related repositories

- [gregmaya/bogota-pop](https://github.com/gregmaya/bogota-pop): population estimates for Bogotá, by block and H3 cell.
- [gregmaya/bogota-pop-viewer](https://github.com/gregmaya/bogota-pop-viewer): the web viewer that shows both.

## Licence and citation

Code: MIT ([LICENSE](LICENSE)). Running the pipeline installs cityseer, which is AGPL-3.0 (ADR-0001). Data outputs: ODbL 1.0 (ADR-0002), chosen because outputs were to include OSM data; v1 uses CC BY 4.0 sources only (ADR-0010). How to cite: [CITATION.cff](CITATION.cff).
