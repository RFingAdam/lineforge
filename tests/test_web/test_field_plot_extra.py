"""Extra tests for `web/api_field_plot.py`.

The synchronous `/api/solve/field_plot` is covered by tests/test_web/test_field_plot.py.
This file adds:

  - Synchronous error paths (invalid geometry, unknown usermap URI, both
    geometry+uri given, neither given).
  - The async variant `/api/solve/field_plot/async` happy path plus error
    branches (it returns a task_id immediately, then the background worker
    pushes progress / result / error events over `/ws/progress/{task_id}`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lineforge.web.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_MICROSTRIP = {
    "type": "microstrip",
    "W": "6mil",
    "H": "4mil",
    "T": "1.4mil",
    "er": 4.4,
}


class TestSyncFieldPlotErrors:
    def test_unknown_usermap_uri_404(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/field_plot",
            json={"usermap_uri": "atlc://geometries/no-such-id", "field_kind": "V"},
        )
        assert r.status_code == 404

    def test_invalid_geometry_400(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/field_plot",
            json={"geometry": {"type": "purple-twirl"}, "field_kind": "V"},
        )
        assert r.status_code == 400

    def test_both_geometry_and_uri_400(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/field_plot",
            json={
                "geometry": _MICROSTRIP,
                "usermap_uri": "atlc://geometries/foo",
                "field_kind": "V",
            },
        )
        assert r.status_code == 400

    def test_neither_geometry_nor_uri_400(self, client: TestClient) -> None:
        r = client.post("/api/solve/field_plot", json={"field_kind": "V"})
        assert r.status_code == 400

    def test_sync_field_plot_E(self, client: TestClient) -> None:
        """Hit the rasterize → solve_cgp path for an E plot."""
        r = client.post("/api/solve/field_plot", json={"geometry": _MICROSTRIP, "field_kind": "E"})
        assert r.status_code == 200
        body = r.json()
        assert body["png_data_uri"].startswith("data:image/png;base64,")

    def test_sync_field_plot_T(self, client: TestClient) -> None:
        """T (tan_delta) plot exercises the `usermap.tan_delta_field()` branch."""
        r = client.post("/api/solve/field_plot", json={"geometry": _MICROSTRIP, "field_kind": "T"})
        assert r.status_code == 200

    def test_sync_field_plot_D(self, client: TestClient) -> None:
        r = client.post("/api/solve/field_plot", json={"geometry": _MICROSTRIP, "field_kind": "D"})
        assert r.status_code == 200


class TestAsyncFieldPlot:
    """The /async endpoint immediately returns a task_id; the background
    worker runs the same code path as the sync endpoint but pushes events
    over the progress WebSocket. We test that the endpoint accepts requests
    and returns a task_id — the full WS streaming is exercised in
    test_main.py::TestProgressWebSocket."""

    def test_async_returns_task_id(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/field_plot/async",
            json={"geometry": _MICROSTRIP, "field_kind": "V"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "task_id" in body
        assert len(body["task_id"]) > 0

    def test_async_with_usermap_uri(self, client: TestClient) -> None:
        """Upload a usermap, then drive the async endpoint via usermap_uri."""
        import base64
        import io

        import numpy as np
        from PIL import Image

        n = 21
        rgb = np.full((n, n, 3), 255, dtype=np.uint8)
        rgb[0, :] = (0, 255, 0)
        rgb[-1, :] = (0, 255, 0)
        rgb[n // 2, n // 2] = (255, 0, 0)
        img = Image.fromarray(rgb, mode="RGB")
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        bmp_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        upload = client.post(
            "/api/usermap/upload",
            json={"bmp_base64": bmp_b64, "pixel_width": "0.1mm"},
        ).json()
        r = client.post(
            "/api/solve/field_plot/async",
            json={"usermap_uri": upload["uri"], "field_kind": "V"},
        )
        assert r.status_code == 200
        assert "task_id" in r.json()

    def test_async_accepts_bad_inputs(self, client: TestClient) -> None:
        """The endpoint always accepts the request (returns task_id); the
        background worker reports any error over the progress WS rather
        than via HTTP."""
        r = client.post(
            "/api/solve/field_plot/async",
            json={"geometry": {"type": "purple-twirl"}, "field_kind": "V"},
        )
        assert r.status_code == 200
        assert "task_id" in r.json()


# NOTE: end-to-end exercise of the async worker's progress + result events
# is covered by tests/test_web/test_main.py::TestProgressWebSocket — repeat-
# ing it here would race the background task. The async-endpoint smoke tests
# above guarantee the request handler doesn't crash and returns a task_id.
