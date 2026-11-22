"""Record where every download came from in config/manifest.json (committed)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from bogota_syntax.config import project_root

CKAN_API = "https://datosabiertos.bogota.gov.co/api/3/action"
USER_AGENT = "bogota-syntax (open-data research pipeline)"


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_utc() -> str:
    """Current time as an ISO 8601 UTC string, to the second."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ckan_metadata(dataset: str, session: requests.Session | None = None) -> dict[str, Any]:
    """Return licence and modification date of a CKAN dataset on datosabiertos.bogota.gov.co."""
    s = session or requests.Session()
    r = s.get(
        f"{CKAN_API}/package_show",
        params={"id": dataset},
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    r.raise_for_status()
    res = r.json()["result"]
    return {
        "ckan_dataset": dataset,
        "ckan_license_id": res.get("license_id"),
        "ckan_metadata_modified": res.get("metadata_modified"),
    }


def manifest_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "manifest.json"


def record(source_id: str, entry: dict[str, Any], root: Path | None = None) -> None:
    """Write or replace one source's entry in config/manifest.json, keeping keys sorted."""
    path = manifest_path(root)
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest[source_id] = entry
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    tmp.replace(path)
