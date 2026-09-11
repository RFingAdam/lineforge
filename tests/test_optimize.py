"""Phase 4.1 AC: geometry optimizer hits Z0 targets."""

from __future__ import annotations

import pytest

import lineforge
from lineforge.units import parse_length


class TestOptimizer:
    def test_microstrip_50ohm(self) -> None:
        result = lineforge.optimize_for(
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
        result = lineforge.optimize_for(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary={"W": ("1mil", "20mil")},
            target={"z0": 50.0},
        )
        assert isinstance(result.geometry, lineforge.Microstrip)


class TestTargetZ0:
    """Ergonomic wrapper for the most common 'find W for target Z0' workflow."""

    def test_microstrip_50ohm(self) -> None:
        from lineforge.optimize import target_z0

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
        from lineforge.optimize import target_z0

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
        from lineforge.optimize import target_z0

        # Should run without explicit bounds (defaults to 0.1mil-100mil).
        result = target_z0(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary="W",
            target_ohms=50.0,
        )
        assert result.success

    def test_dict_form_vary_passes_through(self) -> None:
        """``vary`` may be a full dict (same as optimize_for)."""
        from lineforge.optimize import target_z0

        result = target_z0(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary={"W": ("1mil", "20mil")},
            target_ohms=50.0,
        )
        assert result.success

    def test_target_below_geometry_range_low_success(self) -> None:
        """Asking for an unreachable Z0 (e.g. 200 Ω on a 50Ω-class microstrip)
        should still return a result, but ``success`` may be False."""
        from lineforge.optimize import target_z0

        result = target_z0(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary="W",
            target_ohms=200.0,
            bounds=("1mil", "20mil"),
        )
        # The optimizer will find the best it can within the bounds; flag as
        # not-success because cost > 1%.
        assert not result.success


class TestTargetZ0MetricSelection:
    """``target_z0`` must drive the metric the geometry actually reports.

    Regression: it hardcoded ``target={"z0": ...}``, but a DiffResult exposes
    z_odd/z_even/z_diff/z_common and no ``z0``. Every candidate therefore
    scored the 1e6 "metric missing" penalty, the cost surface was flat, and the
    optimizer parked at an arbitrary bound reporting success=False with a null
    impedance -- instead of simply targeting z_diff.
    """

    def test_differential_defaults_to_z_diff(self) -> None:
        from lineforge.optimize import target_z0

        result = target_z0(
            template={
                "type": "edge_coupled_diff_microstrip",
                "H": "4mil",
                "T": "1.4mil",
                "S": "5mil",
                "er": 4.2,
            },
            vary="W",
            target_ohms=100.0,
            bounds=("1mil", "20mil"),
        )
        assert result.success
        assert result.metric["z_diff"] == pytest.approx(100.0, abs=1.0)
        # and it must not have parked against a bound
        assert result.geometry.W < parse_length("20mil")

    def test_single_ended_still_targets_z0(self) -> None:
        from lineforge.optimize import target_z0

        result = target_z0(
            template={
                "type": "stripline_asymmetric",
                "T": "1.4mil",
                "H1": "4mil",
                "H2": "5mil",
                "er": 4.2,
            },
            vary="W",
            target_ohms=50.0,
            bounds=("1mil", "10mil"),
        )
        assert result.success
        assert result.metric["z0"] == pytest.approx(50.0, abs=1.0)

    def test_explicit_metric_override(self) -> None:
        """A caller can target an odd-mode impedance directly."""
        from lineforge.optimize import target_z0

        result = target_z0(
            template={
                "type": "edge_coupled_diff_microstrip",
                "H": "4mil",
                "T": "1.4mil",
                "S": "5mil",
                "er": 4.2,
            },
            vary="W",
            target_ohms=50.0,
            bounds=("1mil", "20mil"),
            metric="z_odd",
        )
        assert result.success
        assert result.metric["z_odd"] == pytest.approx(50.0, abs=1.0)

    def test_wide_bounds_do_not_crash_asymmetric_stripline(self) -> None:
        """The default 100 mil upper bound sweeps the optimizer through the
        unphysical wide-strip region; it must steer back, not die."""
        from lineforge.optimize import target_z0

        result = target_z0(
            template={
                "type": "stripline_asymmetric",
                "T": "1.4mil",
                "H1": "4mil",
                "H2": "5mil",
                "er": 4.2,
            },
            vary="W",
            target_ohms=50.0,
        )
        assert result.metric["z0"] == pytest.approx(50.0, abs=1.0)
