# bogota-syntax

Centralidad abierta y reproducible de la red vial de Bogotá D.C., publicada como teselas para el visor de Bogotá.

[English](README.md)

> En construcción (Fase 0: configuración). Ver [docs/decisions/](docs/decisions/) y el [glosario · glossary](docs/glossary.md).

## Qué hace

Este repositorio construye una red vial de Bogotá, calcula medidas de centralidad sobre ella y publica los resultados como PMTiles que el visor ([gregmaya/bogota-pop-viewer](https://github.com/gregmaya/bogota-pop-viewer)) dibuja sin código específico por capa.

El método en breve:

1. Tomar los ejes viales oficiales de Bogotá (Malla Vial de IDECA) y limpiarlos con [neatnet](https://uscuni.org/neatnet/). La v1 usa solo esta fuente, así que la red termina en el límite de la ciudad y los valores cerca de él quedan subestimados; cada segmento registra su distancia al límite (ADR-0010). La unión con OpenStreetMap (OSM) por fuera de la ciudad se construyó y se probó, y queda para una versión posterior (ADR-0007, ADR-0008).
2. Unir la red en segmentos de calle de intersección a intersección.
3. Calcular la cercanía y la intermediación por el camino más simple (angular) sobre el grafo de segmentos con [cityseer](https://cityseer.benchmarkurbanism.com/) (ADR-0009). Los resultados se reportan solo dentro del área de estudio; el área de amortiguamiento solo se usa para calcular las rutas.

Las primeras etapas cubren una selección de proyectos de renovación urbana de RENOBO en el centro de Bogotá. La ciudad completa viene después. La razón de cada decisión queda en un registro de decisión de arquitectura (ADR, por sus siglas en inglés) en [docs/decisions/](docs/decisions/).

## Fuentes de datos

| Fuente | Entidad | Uso | Licencia |
| --- | --- | --- | --- |
| [Mapa de Referencia](https://datosabiertos.bogota.gov.co/dataset/mapa-de-referencia), capa *Malla Vial* | IDECA / UAECD | Red vial actual dentro de Bogotá; límite de la ciudad | CC BY 4.0 |
| [Perímetro urbano](https://datosabiertos.bogota.gov.co/dataset/perimetro-urbano-bogota-d-c) | SDP | Área urbana, que define hasta dónde llega la red (área urbana + 10 km) | CC BY 4.0 |
| [Eje vial](https://datosabiertos.bogota.gov.co/dataset/eje-vial-bogota-d-c) | SDP | Geometría de las vías arteriales construidas dentro de Bogotá (ADR-0008, no se usa en la v1); vías proyectadas para escenarios futuros | CC BY 4.0 |
| [Red infraestructura vial](https://datosabiertos.bogota.gov.co/dataset/red-infraestructura-vial-bogota-d-c) | SDP | Corredores de reserva vial, como referencia | CC BY 4.0 |
| [Proyecto de RenoBo](https://datosabiertos.bogota.gov.co/dataset/proyecto-de-renobo) | RENOBO | Áreas de estudio del piloto | CC BY 4.0 |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | Colaboradores de OSM | Red vial por fuera de Bogotá (no se usa en la v1) | ODbL 1.0 |

El portal de datos abiertos de Bogotá funciona con [CKAN](https://docs.ckan.org/en/2.10/api/). Su API entrega la licencia, la versión y las URL de descarga de cada conjunto de datos, que la ingesta usará para registrar la procedencia:

```bash
curl "https://datosabiertos.bogota.gov.co/api/3/action/package_show?id=eje-vial-bogota-d-c"
```

## Trabajo futuro

- **Transporte público.** TransMilenio publica la programación del SITP (Sistema Integrado de Transporte Público) en formato [GTFS](https://datosabiertos.bogota.gov.co/dataset/especificacion-gtfs-general-transport-feed-specification-sitp) (General Transit Feed Specification). Con este se podría agregar el acceso a paraderos y estaciones, o una centralidad por tiempo de viaje que combine caminata y transporte público. Su licencia es CC BY-SA 4.0, que choca con la licencia ODbL de los resultados (ADR-0002). Usarlo requiere primero su propia decisión.
- **Escenarios.** Comparar la red actual con las vías proyectadas del Plan de Ordenamiento Territorial (POT, Decreto 555 de 2021), usando los ejes viales de la SDP.
- **Morfología.** Medidas de forma urbana con [momepy](https://docs.momepy.org/), como métricas de manzana, predio y edificación junto a la centralidad.

## Entorno de desarrollo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gregmaya/bogota-syntax.git
cd bogota-syntax
uv sync
uv run pre-commit install   # una vez por clon
uv run pytest
```

## Repositorios relacionados

- [gregmaya/bogota-pop](https://github.com/gregmaya/bogota-pop): estimaciones de población de Bogotá por manzana y celda H3.
- [gregmaya/bogota-pop-viewer](https://github.com/gregmaya/bogota-pop-viewer): el visor web que muestra ambos.

## Licencia y cita

Código: MIT ([LICENSE](LICENSE)). El pipeline instala cityseer, que tiene licencia AGPL-3.0 (ADR-0001). Datos publicados: ODbL 1.0 (ADR-0002), elegida porque los resultados iban a incluir datos de OSM; la v1 usa solo fuentes CC BY 4.0 (ADR-0010). Cómo citar: [CITATION.cff](CITATION.cff).
