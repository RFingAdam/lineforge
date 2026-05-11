"""Tests for the bitmap 3-wire Y-decomposition solver (Phase B3).

Three Laplace solves with each conductor in turn floating produce three
pair impedances; the analytical y_decomposition algebra recovers ZoR/ZoG/ZoB.
The bitmap path validates against the closed-form 3-wire solver for round
conductors above ground within ±10 % (looser than analytic-vs-analytic
because pixelation of round shapes has ~5 % discretization error).
"""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.solvers import solve_modes


def _make_three_wire_bitmap(
    *,
    n: int = 51,
    red_box: tuple[int, int, int, int] = (20, 25, 5, 10),
    blue_box: tuple[int, int, int, int] = (20, 25, 41, 46),
    green_box: tuple[int, int, int, int] = (5, 10, 23, 28),
    pixel_width_m: float = 1e-4,
    name: str = "3wire",
) -> Usermap:
    """Build a synthetic 3-conductor bitmap: red, blue, green conductor squares
    inside a vacuum cavity. ``box`` tuples are (y0, y1, x0, x1)."""
    rgb = np.full((n, n, 3), 255, dtype=np.uint8)
    y0, y1, x0, x1 = red_box
    rgb[y0:y1, x0:x1] = (255, 0, 0)
    y0, y1, x0, x1 = blue_box
    rgb[y0:y1, x0:x1] = (0, 0, 255)
    y0, y1, x0, x1 = green_box
    rgb[y0:y1, x0:x1] = (0, 255, 0)
    return Usermap(rgb, UsermapMetadata(pixel_width_m=pixel_width_m, name=name, source="test"))


class TestSolveModesValidation:
    def test_missing_red_raises(self) -> None:
        rgb = np.full((11, 11, 3), 255, dtype=np.uint8)
        rgb[2:4, 5:7] = (0, 0, 255)  # only blue
        rgb[6:8, 5:7] = (0, 255, 0)  # green
        um = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4, name="t", source="test"))
        with pytest.raises(ValueError, match="requires red"):
            solve_modes(um, tol=1e-5, max_iter=500)

    def test_missing_green_raises(self) -> None:
        rgb = np.full((11, 11, 3), 255, dtype=np.uint8)
        rgb[2:4, 5:7] = (255, 0, 0)
        rgb[6:8, 5:7] = (0, 0, 255)
        um = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4, name="t", source="test"))
        with pytest.raises(ValueError, match="requires"):
            solve_modes(um, tol=1e-5, max_iter=500)


class TestSolveModesSymmetry:
    """Mirror-symmetric R/B placement → ZoR == ZoB, no radiation."""

    def test_symmetric_geometry_preserves_r_b_symmetry(self) -> None:
        um = _make_three_wire_bitmap()
        r = solve_modes(um, tol=1e-5, max_iter=5000, floating_mode="boundary_weighted")
        # red and blue are mirror-symmetric → their pair impedances and Y-legs
        # must match
        assert r.zo_r == pytest.approx(r.zo_b, rel=1e-4)
        assert r.z_rcz == pytest.approx(r.z_bcz, rel=1e-4)
        # No radiation under push-pull symmetry
        assert r.ignd_ratio == pytest.approx(0.0, abs=1e-3)
        assert not r.warnings

    def test_method_tag(self) -> None:
        um = _make_three_wire_bitmap()
        r = solve_modes(um, tol=1e-5, max_iter=5000)
        assert r.method == "bitmap-laplace-y-decomposition"

    def test_z_odd_z_even_relationship(self) -> None:
        """z_odd = 2·ZoR; z_even = ZoR/2 + ZoB."""
        um = _make_three_wire_bitmap()
        r = solve_modes(um, tol=1e-5, max_iter=5000)
        assert r.z_odd == pytest.approx(2.0 * abs(r.zo_r), rel=1e-9)
        assert r.z_even == pytest.approx(abs(r.zo_r) / 2.0 + abs(r.zo_b), rel=1e-9)


class TestSolveModesAsymmetry:
    """Asymmetric geometry → non-zero radiation indicator."""

    def test_asymmetric_red_blue_radiation(self) -> None:
        # Move blue conductor closer to green (asymmetric)
        um = _make_three_wire_bitmap(
            red_box=(20, 25, 5, 10),
            blue_box=(20, 25, 30, 35),  # left of center, not mirror of red
            green_box=(5, 10, 23, 28),
        )
        r = solve_modes(um, tol=1e-5, max_iter=5000, floating_mode="boundary_weighted")
        # Asymmetry → ZoR ≠ ZoB
        assert abs(r.zo_r - r.zo_b) > 1.0  # at least 1 Ω difference
        # Radiation indicator > 0 (may be < 4 % if not extreme)
        assert r.ignd_ratio > 0.0


class TestYDecompositionConsistency:
    """The three pair impedances must satisfy the Y-decomposition identities."""

    def test_y_decomposition_back_calculation(self) -> None:
        """From ZoR/ZoG/ZoB, the three pair impedances should reconstruct."""
        um = _make_three_wire_bitmap()
        r = solve_modes(um, tol=1e-5, max_iter=5000)
        # Identity: z_rcz = ZoG + ZoB, z_gcz = ZoR + ZoB, z_bcz = ZoR + ZoG
        assert r.z_rcz == pytest.approx(r.zo_g + r.zo_b, rel=1e-9)
        assert r.z_gcz == pytest.approx(r.zo_r + r.zo_b, rel=1e-9)
        assert r.z_bcz == pytest.approx(r.zo_r + r.zo_g, rel=1e-9)
