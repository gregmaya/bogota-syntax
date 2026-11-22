"""Command line: `uv run bogota-syntax --help`."""

from __future__ import annotations

from typing import Annotated

import typer

from bogota_syntax import __version__
from bogota_syntax.config import load_sources, project_root

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    """Street-network centrality for Bogotá."""


@app.command()
def ingest(
    source: Annotated[str | None, typer.Argument(help="One source id; all if omitted.")] = None,
    force: Annotated[bool, typer.Option(help="Download again even if raw files exist.")] = False,
) -> None:
    """Download sources, record provenance in config/manifest.json, reproject to EPSG:9377.

    With no source, runs every source in order and builds the extent once its inputs
    (RENOBO, Bogotá boundary, urban perimeter) are in.
    """
    from bogota_syntax.ingest import EXTENT_INPUTS, ORDER, ingest_source

    root = project_root()
    known = load_sources(root)
    if source is not None and source not in known:
        raise typer.BadParameter(f"unknown source {source!r}; known: {', '.join(known)}")
    for sid in [source] if source else ORDER:
        typer.echo(f"ingest {sid} ...")
        entry = ingest_source(sid, root, force=force)
        typer.echo(f"  {entry['n_features']} features -> {entry['interim_file']}")
        if source is None and sid == EXTENT_INPUTS[-1]:
            extent()


@app.command()
def extent() -> None:
    """Build the ADR-0004 areas and ADR-0007 stitch areas into data/interim/extent/."""
    import geopandas as gpd

    from bogota_syntax.ingest import build_extent

    root = project_root()
    for name, path in build_extent(root).items():
        area_km2 = gpd.read_parquet(path).area.sum() / 1e6
        typer.echo(f"  {name:<16} {area_km2:>9,.1f} km²  -> {path.relative_to(root)}")


@app.command()
def clean(
    side: Annotated[str | None, typer.Argument(help="mvi or osm; both if omitted.")] = None,
) -> None:
    """Clean each side with neatnet over its cleaning area (ADR-0007) into data/interim/clean/.

    Stops with an error if a piece of the network is lost in cleaning.
    """
    from bogota_syntax.clean import SIDES, run

    if side is not None and side not in SIDES:
        raise typer.BadParameter(f"unknown side {side!r}; known: {', '.join(SIDES)}")
    for name, s in run(project_root(), [side] if side else None).items():
        typer.echo(
            f"  {name}: {s['raw_lines']:,} lines {s['raw_km']:,.0f} km -> "
            f"{s['cleaned_lines']:,} lines {s['cleaned_km']:,.0f} km; pieces "
            f"{s['pieces_before']} -> {s['pieces_after']}, vanished {s['pieces_vanished']}"
        )


@app.command()
def arterials() -> None:
    """Swap SDP arterial axes into cleaned MVI (ADR-0008) -> data/interim/clean/mvi_arterial."""
    from bogota_syntax.arterials import run

    s = run(project_root())
    typer.echo(f"  axes used: {s['axes_lines']:,} lines, {s['axes_km']:,.0f} km")
    typer.echo(f"  removed: {s['removed_lines']:,} MVI lines, {s['removed_km']:,.0f} km")
    typer.echo(
        f"  connectors: {s['connectors']:,} (median {s['connector_median_m']:.1f} m, "
        f"max {s['connector_max_m']:.1f} m); axis gaps closed: {s['axis_gaps']:,}"
    )
    typer.echo(
        f"  network: {s['lines_before']:,} -> {s['lines_after']:,} lines, "
        f"{s['km_before']:,.0f} -> {s['km_after']:,.0f} km"
    )
    typer.echo(
        f"  dead ends {s['dead_ends_before']:,} -> {s['dead_ends_after']:,}; "
        f"pieces {s['pieces_before']} -> {s['pieces_after']}"
    )


@app.command()
def join() -> None:
    """Cut both sides at the Bogotá boundary and connect them (ADR-0007) -> data/interim/join/."""
    from bogota_syntax.join import run

    s = run(project_root())
    typer.echo(f"  network: {s['lines']:,} lines, {s['km']:,.0f} km")
    typer.echo(
        f"  OSM ends on the boundary: {s['osm_boundary_ends']}; connected {s['connectors']}, "
        f"unmatched {s['unmatched_osm_ends']}; MVI ends near boundary unmatched "
        f"{s['unmatched_mvi_ends']}"
    )
    typer.echo(
        f"  pieces: {s['pieces']} (main {s['main_km']:,.0f} km, others {s['other_km']:,.1f} km)"
    )
