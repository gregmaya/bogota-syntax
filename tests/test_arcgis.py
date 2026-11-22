"""ArcGIS REST paging, with a fake session (no network)."""

import pytest

from bogota_syntax.ingest import arcgis

SERVICE = "https://example.test/MapServer"


def _feature(i: int) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[-74.07, 4.6], [-74.06, 4.61]]},
        "properties": {"OBJECTID": i, "MVITIPO": "CL"},
    }


class FakeResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class FakeSession:
    """Serves `n` features, `page` at a time; can lie about the count."""

    def __init__(self, n: int, page: int, reported_count: int | None = None) -> None:
        self.n, self.page = n, page
        self.reported = n if reported_count is None else reported_count
        self.calls: list[dict] = []

    def get(self, url, params=None, **_):
        self.calls.append(params)
        if url.endswith("/query") and params.get("returnCountOnly") == "true":
            return FakeResponse({"count": self.reported})
        if url.endswith("/query"):
            off, rc = params["resultOffset"], params["resultRecordCount"]
            ids = range(off, min(off + min(rc, self.page), self.n))
            return FakeResponse(
                {"type": "FeatureCollection", "features": [_feature(i) for i in ids]}
            )
        return FakeResponse({"maxRecordCount": self.page})


def test_pages_until_count_reached() -> None:
    s = FakeSession(n=2500, page=1000)
    gdf = arcgis.fetch_layer(SERVICE, 13, session=s)
    assert len(gdf) == 2500
    assert gdf.crs.to_epsg() == 4326
    offsets = [c["resultOffset"] for c in s.calls if c and "resultOffset" in c]
    assert offsets == [0, 1000, 2000]


def test_count_mismatch_raises() -> None:
    s = FakeSession(n=1500, page=1000, reported_count=1600)
    with pytest.raises(arcgis.ArcGISError, match="received 1500"):
        arcgis.fetch_layer(SERVICE, 13, session=s)


def test_server_error_payload_raises() -> None:
    class ErrSession(FakeSession):
        def get(self, url, params=None, **_):
            return FakeResponse({"error": {"code": 400, "message": "bad where"}})

    with pytest.raises(arcgis.ArcGISError, match="bad where"):
        arcgis.fetch_layer(SERVICE, 13, session=ErrSession(1, 1), page_size=1)
