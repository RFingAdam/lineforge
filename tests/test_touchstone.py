"""Tests for Touchstone (.s2p) export from frequency sweeps."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from atlc3.geometry.types import Microstrip
from atlc3.sweep import sweep
from atlc3.touchstone import to_touchstone


@pytest.fixture
def fr4_microstrip_sweep() -> list:
    """50Ω-ish FR4 microstrip swept 0.1–10 GHz."""
    geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4, tan_delta=0.02)
    freqs = np.linspace(1e8, 1e10, 21).tolist()
    return sweep(geom, parameter="frequency", values=freqs, solver="analytical")


class TestTouchstoneRoundTrip:
    def test_writes_loadable_s2p(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        out = to_touchstone(
            fr4_microstrip_sweep,
            tmp_path / "trace.s2p",
            line_length="1in",
            z_ref=50.0,
        )
        assert out.exists()
        assert out.suffix == ".s2p"

        import skrf

        net = skrf.Network(str(out))
        assert net.nports == 2
        assert net.f.size == 21
        assert net.z0[0, 0].real == pytest.approx(50.0)
        # First freq should match input
        assert net.f[0] == pytest.approx(1e8, rel=1e-9)
        assert net.f[-1] == pytest.approx(1e10, rel=1e-9)

    def test_energy_balance_matches_alpha(self, tmp_path: Path) -> None:
        """Verify |S11|² + |S21|² + dissipated = 1, where dissipated is computed
        from the α the solver reported. This is the physically rigorous test —
        we don't assume the analytical solver is exactly lossless (it reports
        a Phase-1 conductor-loss estimate even at tan_δ=0), but we assert the
        network's energy budget matches the α it claims.
        """
        from atlc3.touchstone import DB_PER_NEPER, INCH_M

        geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4, tan_delta=0.02)
        points = sweep(geom, parameter="frequency", values=[1e8, 1e9, 5e9], solver="analytical")
        out = to_touchstone(points, tmp_path / "balance.s2p", line_length="1in", z_ref=50.0)
        import skrf

        net = skrf.Network(str(out))
        for i, p in enumerate(points):
            cond_db_in = p.result.conductor_loss_db_per_in or 0.0
            diel_db_in = p.result.dielectric_loss_db_per_in or 0.0
            alpha_np_per_m = (cond_db_in + diel_db_in) / INCH_M / DB_PER_NEPER
            expected_dissipated = 1.0 - np.exp(-2.0 * alpha_np_per_m * INCH_M)
            measured_dissipated = 1.0 - abs(net.s[i, 0, 0]) ** 2 - abs(net.s[i, 1, 0]) ** 2
            assert measured_dissipated == pytest.approx(expected_dissipated, abs=1e-4), (
                f"At f={net.f[i]:.2e}: expected dissipation {expected_dissipated:.6f}, "
                f"got {measured_dissipated:.6f}"
            )

    def test_loss_grows_with_frequency(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        """Insertion loss must increase with frequency (positive tan_δ)."""
        out = to_touchstone(fr4_microstrip_sweep, tmp_path / "loss.s2p", line_length="1in")
        import skrf

        net = skrf.Network(str(out))
        il_low = -20.0 * np.log10(abs(net.s[0, 1, 0]))
        il_high = -20.0 * np.log10(abs(net.s[-1, 1, 0]))
        assert il_high > il_low
        # Sanity: 1 inch FR4 at 10 GHz should be ~0.5–1.5 dB IL
        assert 0.3 < il_high < 2.0

    def test_z_ref_passes_through(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        """Non-50Ω reference impedance should be preserved in the file."""
        out = to_touchstone(
            fr4_microstrip_sweep, tmp_path / "z75.s2p", line_length="1in", z_ref=75.0
        )
        import skrf

        net = skrf.Network(str(out))
        assert net.z0[0, 0].real == pytest.approx(75.0, abs=1e-9)

    def test_path_gets_s2p_suffix(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        """Missing .s2p suffix gets added."""
        out = to_touchstone(fr4_microstrip_sweep, tmp_path / "no_suffix")
        assert out.suffix == ".s2p"

    def test_reciprocity(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        """A uniform line is reciprocal: S12 = S21."""
        out = to_touchstone(fr4_microstrip_sweep, tmp_path / "reciprocal.s2p")
        import skrf

        net = skrf.Network(str(out))
        np.testing.assert_allclose(net.s[:, 0, 1], net.s[:, 1, 0], atol=1e-9)

    def test_symmetry(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        """A uniform line is symmetric: S11 = S22."""
        out = to_touchstone(fr4_microstrip_sweep, tmp_path / "symmetric.s2p")
        import skrf

        net = skrf.Network(str(out))
        np.testing.assert_allclose(net.s[:, 0, 0], net.s[:, 1, 1], atol=1e-9)


class TestTouchstoneInputValidation:
    def test_empty_sweep_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty sweep_results"):
            to_touchstone([], tmp_path / "empty.s2p")

    def test_non_frequency_sweep_raises(self, tmp_path: Path) -> None:
        """A geometry sweep (e.g. over W) is not exportable as Touchstone."""
        geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
        points = sweep(
            geom,
            parameter="W",
            values=[5e-5, 1e-4, 2e-4],
            solver="analytical",
            frequency_hz=1e9,
        )
        with pytest.raises(ValueError, match="requires a frequency sweep"):
            to_touchstone(points, tmp_path / "no.s2p")

    def test_zero_length_raises(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="line_length must be positive"):
            to_touchstone(fr4_microstrip_sweep, tmp_path / "zero.s2p", line_length=0.0)

    def test_negative_length_raises(self, fr4_microstrip_sweep: list, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="line_length must be positive"):
            to_touchstone(fr4_microstrip_sweep, tmp_path / "neg.s2p", line_length=-1e-3)


class TestTouchstoneZ0Recovery:
    """Sanity: when Z0 of the line matches z_ref, S11 should be near zero."""

    def test_matched_line_low_reflection(self, tmp_path: Path) -> None:
        """A line with Z0 ≈ z_ref produces |S11| ≪ 1 across the band."""
        geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4, tan_delta=0.0)
        z0_solve = float(
            sweep(geom, parameter="frequency", values=[1e9], solver="analytical")[0].result.z0
        )
        # Set z_ref = the line's actual Z0 at 1 GHz; then |S11| ≈ 0 there.
        points = sweep(geom, parameter="frequency", values=[1e9], solver="analytical")
        out = to_touchstone(points, tmp_path / "matched.s2p", line_length="1in", z_ref=z0_solve)
        import skrf

        net = skrf.Network(str(out))
        # |S11| should be tiny — this is the matching test.
        assert abs(net.s[0, 0, 0]) < 1e-6
