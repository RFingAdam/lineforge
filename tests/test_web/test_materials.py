"""Tests for /api/materials endpoints (D-F3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestLaminates:
    def test_laminates_returns_known_vendors(self, client: TestClient) -> None:
        r = client.get("/api/materials/laminates")
        assert r.status_code == 200
        body = r.json()
        names = [m["name"] for m in body["laminates"]]
        assert any("RO4350B" in n for n in names)
        assert any("Megtron" in n for n in names)
        assert any("Isola" in n for n in names)

    def test_laminate_shape(self, client: TestClient) -> None:
        r = client.get("/api/materials/laminates")
        body = r.json()
        first = body["laminates"][0]
        assert "name" in first
        assert "er" in first
        assert "tan_delta" in first
        assert isinstance(first["er"], (int, float))
        assert first["er"] > 1.0


class TestSeriesReduce:
    def test_three_layer_l3_sig1(self, client: TestClient) -> None:
        """L3 SIG1 void-L4: Prepreg 5.3 + voided 1.4 + Core 3.5 ≈ 10.2 mil eq;
        εr_eq ≈ 3.858."""
        r = client.post(
            "/api/materials/series_reduce",
            json={
                "layers": [
                    {"h": "5.3mil", "er": 3.7, "tan_delta": 0.020, "name": "Prepreg"},
                    {"h": "1.4mil", "er": 3.7, "tan_delta": 0.020, "name": "voided L4"},
                    {"h": "3.5mil", "er": 4.2, "tan_delta": 0.020, "name": "Core"},
                ],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["h_total_m"] == pytest.approx(10.2 * 25.4e-6, rel=1e-9)
        assert body["er_eq"] == pytest.approx(3.858, abs=1e-3)
        # Uniform tan_δ → unchanged after reduction
        assert body["tan_eq"] == pytest.approx(0.020, abs=1e-6)

    def test_empty_layers_rejected(self, client: TestClient) -> None:
        r = client.post("/api/materials/series_reduce", json={"layers": []})
        assert r.status_code == 400
