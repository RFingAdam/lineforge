"""Tests for the field-plot endpoint + custom usermap upload (DB3)."""

from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lineforge.web.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _tiny_bmp_b64() -> str:
    """Make a 21×21 BMP with a single red pixel (signal) and green border (ground)."""
    n = 21
    rgb = np.full((n, n, 3), 255, dtype=np.uint8)  # vacuum
    rgb[0, :] = (0, 255, 0)  # top ground
    rgb[-1, :] = (0, 255, 0)  # bottom ground
    rgb[:, 0] = (0, 255, 0)  # left ground
    rgb[:, -1] = (0, 255, 0)  # right ground
    rgb[n // 2, n // 2] = (255, 0, 0)  # signal
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class TestUsermapUpload:
    def test_upload_returns_uri_and_preview(self, client: TestClient) -> None:
        r = client.post(
            "/api/usermap/upload",
            json={
                "bmp_base64": _tiny_bmp_b64(),
                "pixel_width": "0.1mm",
                "name": "test_geometry",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["uri"].startswith("atlc://geometries/")
        assert body["shape"] == [21, 21]
        assert body["pixel_width_m"] == pytest.approx(1e-4)
        assert body["preview_png_base64"].startswith("data:image/png;base64,")

    def test_get_round_trips(self, client: TestClient) -> None:
        upload = client.post(
            "/api/usermap/upload",
            json={"bmp_base64": _tiny_bmp_b64(), "pixel_width": "0.1mm"},
        ).json()
        uid = upload["uid"]
        r = client.get(f"/api/usermap/{uid}")
        assert r.status_code == 200
        body = r.json()
        assert body["uri"] == upload["uri"]
        assert body["shape"] == upload["shape"]

    def test_get_unknown_uid_404(self, client: TestClient) -> None:
        r = client.get("/api/usermap/nonexistent")
        assert r.status_code == 404

    def test_upload_bad_base64_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/usermap/upload",
            json={"bmp_base64": "!!!not-base64!!!", "pixel_width": "0.1mm"},
        )
        assert r.status_code == 400

    def test_upload_zero_pixel_width_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/usermap/upload",
            json={"bmp_base64": _tiny_bmp_b64(), "pixel_width": "0mm"},
        )
        assert r.status_code == 400


class TestFieldPlot:
    def test_field_plot_microstrip_e(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/field_plot",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "field_kind": "E",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["field_kind"] == "E"
        assert body["png_data_uri"].startswith("data:image/png;base64,")
        assert body["shape"][0] > 0 and body["shape"][1] > 0

    def test_field_plot_v(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/field_plot",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "field_kind": "V",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["field_kind"] == "V"
        # V field should span +1 to roughly 0 (signal to ground)
        assert body["v_min"] <= 0.1
        assert body["v_max"] >= 0.9

    def test_field_plot_requires_one_of_geometry_or_usermap(self, client: TestClient) -> None:
        r = client.post("/api/solve/field_plot", json={"field_kind": "E"})
        assert r.status_code == 400

    def test_field_plot_via_uploaded_usermap(self, client: TestClient) -> None:
        upload = client.post(
            "/api/usermap/upload",
            json={"bmp_base64": _tiny_bmp_b64(), "pixel_width": "0.1mm"},
        ).json()
        r = client.post(
            "/api/solve/field_plot",
            json={"usermap_uri": upload["uri"], "field_kind": "V"},
        )
        assert r.status_code == 200
        assert r.json()["png_data_uri"].startswith("data:image/png;base64,")


class TestCalculateBitmapPath:
    def test_calculate_via_usermap_uri(self, client: TestClient) -> None:
        upload = client.post(
            "/api/usermap/upload",
            json={"bmp_base64": _tiny_bmp_b64(), "pixel_width": "0.1mm"},
        ).json()
        r = client.post("/api/solve/calculate", json={"usermap_uri": upload["uri"]})
        assert r.status_code == 200
        body = r.json()
        assert body["_kind"] == "CGPResult"
        assert body["usermap_uri"] == upload["uri"]
        assert body["z0"] > 0

    def test_calculate_rejects_both_or_neither_input(self, client: TestClient) -> None:
        r = client.post("/api/solve/calculate", json={})
        assert r.status_code == 400
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "usermap_uri": "atlc://geometries/x",
            },
        )
        assert r.status_code == 400
