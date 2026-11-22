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

    With no source, runs every source in order and builds the extent after RENOBO.
    """
    from bogota_syntax.ingest import ORDER, ingest_source

    root = project_root()
    known = load_sources(root)
    if source is not None and source not in known:
        raise typer.BadParameter(f"unknown source {source!r}; known: {', '.join(known)}")
    for sid in [source] if source else ORDER:
        typer.echo(f"ingest {sid} ...")
        entry = ingest_source(sid, root, force=force)
        typer.echo(f"  {entry['n_features']} features -> {entry['interim_file']}")
        if source is None and sid == "renobo_proyectos":
            extent()


@app.command()
def extent() -> None:
    """Build pilot areas, live area and network extent (ADR-0004) into data/interim/extent/."""
    from bogota_syntax.ingest import build_extent

    for name, path in build_extent(project_root()).items():
        typer.echo(f"  {name} -> {path.relative_to(project_root())}")
