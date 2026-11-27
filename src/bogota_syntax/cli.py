"""Command line: `uv run bogota-syntax --help`."""

from __future__ import annotations

import re
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
    """Shelved, not used in v1 (ADR-0010). Swap SDP axes into cleaned MVI (ADR-0008)."""
    from bogota_syntax.arterials import run

    s = run(project_root())
    typer.echo(f"  axes used: {s['axes_lines']:,} lines, {s['axes_km']:,.0f} km")
    typer.echo(
        f"  removed: {s['removed_lines']:,} MVI lines, {s['removed_km']:,.0f} km; restored as "
        f"the only link to the main network: {s['restored_lines']:,} ({s['restored_km']:.1f} km)"
    )
    typer.echo(
        f"  connectors: {s['connectors']:,} (median {s['connector_median_m']:.1f} m, "
        f"max {s['connector_max_m']:.1f} m); axis gaps closed: {s['axis_gaps']:,}"
    )
    typer.echo(
        f"  dead ends extended onto a nearby line: {s['extended_lines']:,} "
        f"(+{s['extended_km'] * 1e3:,.0f} m in total)"
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
    """Shelved, not used in v1 (ADR-0010). Join OSM and MVI at the boundary (ADR-0007)."""
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


@app.command()
def network() -> None:
    """Merge into intersection-to-intersection segments (ADR-0009) -> data/processed/network."""
    from bogota_syntax.network import run

    s = run(project_root())
    typer.echo(f"  mode: {s['mode']}")
    typer.echo(
        f"  {s['segments']:,} segments, {s['km']:,.0f} km, median {s['median_m']:.0f} m; "
        f"nodes {s['nodes']:,} (degree 2: {s['degree2_nodes']}); loops {s['loops']}"
    )
    typer.echo(f"  pieces {s['pieces']}, main network {s['main_km']:,.0f} km")
    for src, r in s["by_source"].iterrows():
        typer.echo(f"    {src:<16} {int(r['n']):>7,} segments {r['km']:>8,.1f} km")
    typer.echo("  attributes by source and origin:")
    for (src, origin), n in s["attr_origin"].items():
        typer.echo(f"    {src:<16} {origin:<10} {n:>7,}")
    typer.echo(f"  -> {s['path'].relative_to(project_root())}")


@app.command()
def foreground() -> None:
    """Clean SDP Eje Vial into the foreground network (ADR-0012) -> data/processed/foreground."""
    from bogota_syntax.foreground import run

    root = project_root()
    s = run(root)

    def cls(d: dict) -> str:
        return ", ".join(f"{k} {v}" for k, v in d.items())

    typer.echo(f"  0 input: {s['input_lines']:,} lines; dead ends {cls(s['input'])}")
    typer.echo(f"  1 snapped: {s['snapped']} ends")
    typer.echo(f"  2 crossings split: {s['crossings_split']}")
    typer.echo(f"  3 removed: {s['stubs']} stubs, {s['duplicates']} duplicates")
    typer.echo(f"  4 dead ends: {cls(s['classified'])}")
    typer.echo(f"  5 pairs joined: {s['pairs']}")
    steps = ", ".join(
        f"{t['tol_m']:g} m +{t['extended']}" for t in s["extension_steps"] if t["extended"]
    )
    typer.echo(f"  6 extensions: {s['extensions']} ({steps})")
    typer.echo(f"  7 junctions merged: {s['junctions_moved']} moved")
    typer.echo(f"  8 connectors: {cls(s['connectors'])}; to review: {s['review']}")
    typer.echo(
        f"  10 jogs straightened: {s['jogs']}; "
        f"vertices {s['vertices'][0]:,} -> {s['vertices'][1]:,}"
    )
    if "relocation" in s:
        typer.echo(
            f"  11 interchange centres relocated: {s['relocated']}; to review: "
            f"{s['needs_review']}; stale decisions (no matching polygon): {s['stale_decisions']}"
        )
        for (dec, act), n in sorted(s["relocation"].items()):
            typer.echo(f"     decision {dec or '(none)':<9} -> {act:<15} {n:>4}")
    if "edits" in s:
        e = s["edits"]
        typer.echo(
            f"  12 manual edits: {e['removed']} lines removed, {e['added']} added; "
            f"stale removals (no matching line): {e['stale']}"
        )
    typer.echo(
        f"  final: {s['segments']:,} segments, {s['km']:,.1f} km, {s['components']} components, "
        f"{s['unsplit_crossings']} unsplit crossings; dead ends {cls(s['final'])}"
    )
    for k in ("path", "gpkg", "review_path"):
        typer.echo(f"  -> {s[k].relative_to(root)}")


@app.command("sdp-package")
def sdp_package() -> None:
    """Spanish package for the SDP (ADR-0013) -> data/processed/sdp_package/."""
    from bogota_syntax.sdp_package import TIPOS, run

    root = project_root()
    s = run(root)
    typer.echo(f"  problemas: {s['n_problemas']} ({s['n_abierto']} abiertos)")
    for t in TIPOS:
        typer.echo(f"     {t:<16} {s[f'n_{t}']:>4}  abiertos {s[f'n_{t}_abierto']}")
    typer.echo(f"  correcciones: {s['n_correcciones']}")
    typer.echo(
        f"  decisiones_modelado: {s['n_fusion_nodos']} fusiones de nodos, {s['n_reubicacion']} "
        f"enlaces reubicados ({s['n_reubicacion_revision']} por revisión, "
        f"{s['n_reubicacion_regla']} por regla)"
    )
    typer.echo(
        f"  ediciones_manuales: {s['n_edicion_agregada']} agregadas, "
        f"{s['n_edicion_retirada']} retiradas"
    )
    typer.echo(f"  rows without an Eje Vial feature in range: {s['n_sin_clave']}")
    for _, r in s["unmatched"].iterrows():
        typer.echo(f"     {r['tipo']} ({r['estado']}) at {r.geometry.x:.1f}, {r.geometry.y:.1f}")
    typer.echo(f"  PCS_CarMAGBOG round trip: {s['round_trip_m'] * 1000:.2f} mm")
    for w in s.get("warnings", []):
        typer.echo(f"  warning: {w}")
    typer.echo(f"  -> {s['dir'].relative_to(root)}")


@app.command()
def centrality(
    area: Annotated[
        str, typer.Option(help="pilot (ADR-0004) or city (urban perimeter).")
    ] = "pilot",
    network: Annotated[
        str,
        typer.Option(help="Network version: v1 (network.parquet) or vN (network_vN.parquet)."),
    ] = "v1",
) -> None:
    """Simplest-path closeness and betweenness (ADR-0009) -> centrality_<area>[_vN].parquet."""
    from bogota_syntax.centrality import run

    if area not in ("pilot", "city"):
        raise typer.BadParameter("area must be pilot or city")
    if not re.fullmatch(r"v\d+(\.\d+)?", network):
        raise typer.BadParameter("network must look like v1, v2 or v2.1")
    s = run(project_root(), area, network)
    typer.echo(
        f"  {s['segments']:,} segments ({s['live']:,} live), {s['km']:,.0f} km, "
        f"{s['seconds']:.0f} s"
    )
    typer.echo(f"  columns: {', '.join(s['columns'])}")
    typer.echo(f"  -> {s['path'].relative_to(project_root())}")
