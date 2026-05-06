"""Phase 4.1 AC: geometry optimizer hits Z0 targets."""

from __future__ import annotations

import pytest

import atlc3


class TestOptimizer:
    def test_microstrip_50ohm(self) -> None:
        result = atlc3.optimize_for(
            template={
                "type": "microstrip",
                "H": "4mil", "T": "1.4mil", "er": 4.4,
            },
            vary={"W": ("0.5mil", "30mil")},
            target={"z0": 50.0},
            solver="analytical",
        )
        assert result.success
        # Z0 should be very close to 50
        assert result.metric["z0"] == pytest.approx(50.0, abs=1.0)
        # The optimal W for 50Ω 4-mil-FR4 is around 6 mil
        assert 4e-6 * 25.4 < result.geometry.W < 12e-6 * 25.4  # 4-12 mil

    def test_returns_geometry_with_correct_type(self) -> None:
        result = atlc3.optimize_for(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary={"W": ("1mil", "20mil")},
            target={"z0": 50.0},
        )
        assert isinstance(result.geometry, atlc3.Microstrip)
