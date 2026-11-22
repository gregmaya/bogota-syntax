"""Load the YAML settings in config/ and resolve project paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Internal CRS for everything (ADR-0006): MAGNA-SIRGAS Origen Nacional, metres.
CRS = "EPSG:9377"
# CRS the web services and OSM deliver in.
CRS_WGS84 = "EPSG:4326"


def project_root(start: Path | None = None) -> Path:
    """Return the nearest parent directory (inclusive) that holds pyproject.toml and config/."""
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "pyproject.toml").is_file() and (d / "config").is_dir():
            return d
    raise FileNotFoundError(f"No bogota-syntax project root found above {here}")


def _load(name: str, root: Path | None) -> dict[str, Any]:
    path = (root or project_root()) / "config" / name
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return the `sources` mapping from config/sources.yaml, keyed by source id."""
    return _load("sources.yaml", root)["sources"]


def load_analysis(root: Path | None = None) -> dict[str, Any]:
    """Return config/analysis.yaml as a dict."""
    return _load("analysis.yaml", root)


def data_dir(root: Path | None = None) -> Path:
    """Return the git-ignored data/ directory."""
    return (root or project_root()) / "data"
