"""Fetch a whole layer from an ArcGIS REST MapServer, page by page."""

from __future__ import annotations

import time
from typing import Any

import geopandas as gpd
import requests

from bogota_syntax.config import CRS_WGS84
from bogota_syntax.provenance import USER_AGENT


class ArcGISError(RuntimeError):
    pass


def _get(session: requests.Session, url: str, params: dict[str, Any], retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise ArcGISError(f"{url}: {data['error']}")
            return data
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def count(service: str, layer_id: int, where: str, session: requests.Session) -> int:
    """Number of features matching `where`."""
    data = _get(
        session,
        f"{service}/{layer_id}/query",
        {"where": where, "returnCountOnly": "true", "f": "json"},
    )
    return int(data["count"])


def fetch_layer(
    service: str,
    layer_id: int,
    where: str = "1=1",
    session: requests.Session | None = None,
    page_size: int | None = None,
) -> gpd.GeoDataFrame:
    """Download every feature of a layer as a GeoDataFrame in EPSG:4326.

    Pages with resultOffset ordered by OBJECTID, and checks that the number of features
    received equals the server's count. Raises ArcGISError if it doesn't.
    """
    s = session or requests.Session()
    url = f"{service}/{layer_id}"
    if page_size is None:
        page_size = int(_get(s, url, {"f": "json"}).get("maxRecordCount", 1000))
    expected = count(service, layer_id, where, s)

    frames: list[gpd.GeoDataFrame] = []
    offset = 0
    while offset < expected:
        data = _get(
            s,
            f"{url}/query",
            {
                "where": where,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "geojson",
            },
        )
        feats = data.get("features", [])
        if not feats:
            break
        frames.append(gpd.GeoDataFrame.from_features(feats, crs=CRS_WGS84))
        offset += len(feats)

    if not frames:
        raise ArcGISError(f"{url}: no features returned for where={where!r}")
    gdf = gpd.GeoDataFrame(
        gpd.pd.concat(frames, ignore_index=True), geometry="geometry", crs=CRS_WGS84
    )
    if len(gdf) != expected:
        raise ArcGISError(f"{url}: received {len(gdf)} features, server count is {expected}")
    if "OBJECTID" in gdf and gdf["OBJECTID"].duplicated().any():
        raise ArcGISError(f"{url}: duplicated OBJECTID across pages")
    return gdf
