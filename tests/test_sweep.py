"""Phase 3.7 AC: parameter sweep API."""

from __future__ import annotations

import pytest

import lineforge
from lineforge.geometry.types import Microstrip


class TestSweep:
    def test_analytical_w_sweep(self) -> None:
        geom = Microstrip(W=152e-6, H=102e-6, T=35e-6, er=4.4)
        values = [50e-6, 100e-6, 200e-6, 400e-6]
        points = lineforge.sweep(geom, "W", values, solver="analytical")
        assert len(points) == 4
        # Wider W → lower Z0
        z0s = [p.result.z0 for p in points]
        assert z0s == sorted(z0s, reverse=True)

    def test_sweep_returns_sweep_points(self) -> None:
        geom = Microstrip(W=152e-6, H=102e-6, T=35e-6, er=4.4)
        points = lineforge.sweep(geom, "er", [3.5, 4.4, 6.0], solver="analytical")
        for p in points:
            assert "er" in p.params
            assert hasattr(p.result, "z0")

    def test_unknown_solver_raises(self) -> None:
        geom = Microstrip(W=152e-6, H=102e-6, T=35e-6, er=4.4)
        with pytest.raises(ValueError):
            lineforge.sweep(geom, "W", [1e-4], solver="hadron-collider")
