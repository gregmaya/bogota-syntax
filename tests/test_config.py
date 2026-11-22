"""Checks on config/*.yaml: every source is complete and the pilot selection is well formed."""

import re

from typer.testing import CliRunner

from bogota_syntax.cli import app
from bogota_syntax.config import load_analysis, load_sources
from bogota_syntax.ingest import HANDLERS, ORDER
from bogota_syntax.ingest.osm import highway_filter

ALLOWED_LICENCES = {"CC-BY-4.0", "ODbL-1.0"}  # ADR-0002: anything else needs an ADR


def test_every_source_has_kind_and_licence() -> None:
    for sid, src in load_sources().items():
        assert src["kind"] in HANDLERS, sid
        assert src["licence"] in ALLOWED_LICENCES, sid
        assert src.get("title") and src.get("publisher"), sid


def test_ingest_order_covers_all_sources() -> None:
    assert sorted(ORDER) == sorted(load_sources())


def test_pilot_selection_is_unique_gml_ids() -> None:
    a = load_analysis()
    ids = a["pilot"]["gml_ids"]
    assert len(ids) == len(set(ids)) == 36
    assert all(re.fullmatch(r"Proyecto_de_RenoBo\.\d+", i) for i in ids)
    assert a["pilot"]["source"] in load_sources()


def test_osm_filter_is_anchored() -> None:
    f = highway_filter(["primary", "residential"])
    assert f == '["highway"~"^(primary|residential)$"]'


def test_cli_help() -> None:
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "ingest" in r.output and "extent" in r.output
