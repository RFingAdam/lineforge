"""Phase 3.2-3.6 AC: Faraday solver, L/Rs extraction, RLGC pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from atlc3.geometry.usermap import Usermap, UsermapMetadata
from atlc3.solvers.faraday import solve_lrs


def _two_strip_usermap(separation_px: int = 8) -> Usermap:
    """A simple two-strip cross-section: red (+1) and blue (-1) copper bars."""
    h, w = 12, 4 + 4 + separation_px + 4 + 4
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)
    # +1 strip
    rgb[5:7, 4:8] = (255, 0, 0)
    # -1 strip
    rgb[5:7, 4 + 4 + separation_px : 4 + 4 + separation_px + 4] = (0, 0, 255)
    return Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))


class TestFaradaySmoke:
    def test_two_strip_returns_positive_l(self) -> None:
        usermap = _two_strip_usermap()
        result = solve_lrs(usermap, frequency_hz=1e6, method="dense")
        assert result.L_per_m > 0
        assert result.R_per_m >= 0
        assert result.n_conductor_pixels > 0

    def test_dc_inductance_grows_with_separation(self) -> None:
        """Wider separation between conductors → more flux linkage → higher L."""
        l_close = solve_lrs(
            _two_strip_usermap(separation_px=4),
            frequency_hz=1e6, method="dense",
        ).L_per_m
        l_far = solve_lrs(
            _two_strip_usermap(separation_px=20),
            frequency_hz=1e6, method="dense",
        ).L_per_m
        assert l_far > l_close

    def test_no_conductors_raises(self) -> None:
        rgb = np.full((10, 10, 3), 255, dtype=np.uint8)  # all vacuum
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
        with pytest.raises(ValueError):
            solve_lrs(u, frequency_hz=1e6, method="dense")


class TestRLGCFull:
    def test_rlgc_pipeline_produces_positive_quantities(self) -> None:
        from atlc3.solvers.lrs import solve_full

        # Use a small but proper microstrip cross-section
        from atlc3.geometry.builders import rasterize_microstrip
        from atlc3.geometry.types import Microstrip

        geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
        usermap = rasterize_microstrip(geom)

        result = solve_full(
            usermap, frequency_hz=1e8,
            restrict_to_skin_depth=False,  # keep equation count low for speed
            extend_grid_for_cgp=False,
        )
        assert result.z0_real > 0
        assert result.eps_eff >= 1
        assert result.L_per_m > 0
        assert result.C_per_m > 0
        assert result.alpha_neper_per_m >= 0
        assert result.beta_rad_per_m > 0
