"""Phase 4.1 AC: geometry optimizer hits Z0 targets."""

from __future__ import annotations

import pytest

import atlc3


class TestOptimizer:
    def test_microstrip_50ohm(self) -> None:
        result = atlc3.optimize_for(
            template={
                "type": "microstrip",
                "H": "4mil",
                "T": "1.4mil",
                "er": 4.4,
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


class TestTargetZ0:
    """Ergonomic wrapper for the most common 'find W for target Z0' workflow."""

    def test_microstrip_50ohm(self) -> None:
        from atlc3.optimize import target_z0

        result = target_z0(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary="W",
            target_ohms=50.0,
            bounds=("0.5mil", "30mil"),
        )
        assert result.success
        assert result.metric["z0"] == pytest.approx(50.0, abs=0.05)

    def test_l3_sig1_void_l4_recovers_3p18mil(self) -> None:
        """The session benchmark: solve W to land Z0=48Ω on the L3 SIG1 stackup
        (Core εr=4.2 above 3.5mil, Prepreg εr=3.7 below 5.3mil, T=0.689mil).
        Expected W ≈ 3.18 mil."""
        from atlc3.optimize import target_z0

        result = target_z0(
            template={
                "type": "stripline_asymmetric",
                "T": "0.689mil",
                "H1": "3.5mil",
                "H2": "5.3mil",
                "er": 4.2,
                "er_above": 4.2,
                "er_below": 3.7,
            },
            vary="W",
            target_ohms=48.0,
            bounds=("1mil", "10mil"),
        )
        assert result.success
        # The brentq solution from the planning session was 3.182 mil; tighten
        # the optimizer must converge to within 0.005 mil.
        W_mil = result.geometry.W * 39370.0787
        assert W_mil == pytest.approx(3.182, abs=0.005)
        assert result.metric["z0"] == pytest.approx(48.0, abs=0.001)

    def test_default_bounds_when_none(self) -> None:
        from atlc3.optimize import target_z0

        # Should run without explicit bounds (defaults to 0.1mil-100mil).
        result = target_z0(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary="W",
            target_ohms=50.0,
        )
        assert result.success

    def test_dict_form_vary_passes_through(self) -> None:
        """``vary`` may be a full dict (same as optimize_for)."""
        from atlc3.optimize import target_z0

        result = target_z0(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary={"W": ("1mil", "20mil")},
            target_ohms=50.0,
        )
        assert result.success

    def test_target_below_geometry_range_low_success(self) -> None:
        """Asking for an unreachable Z0 (e.g. 200 Ω on a 50Ω-class microstrip)
        should still return a result, but ``success`` may be False."""
        from atlc3.optimize import target_z0

        result = target_z0(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary="W",
            target_ohms=200.0,
            bounds=("1mil", "20mil"),
        )
        # The optimizer will find the best it can within the bounds; flag as
        # not-success because cost > 1%.
        assert not result.success
