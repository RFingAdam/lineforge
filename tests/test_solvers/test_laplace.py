"""Phase 2.6/2.7 AC: Laplace SOR + AMG solvers reproduce analytical solutions."""

from __future__ import annotations

import numpy as np
import pytest

from atlc3.solvers.laplace import solve_laplace, solve_sor


def _parallel_plate_setup(n: int = 32) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Two horizontal plate conductors at top (V=+1) and bottom (V=-1)."""
    er = np.ones((n, n), dtype=np.float64)
    v_mask = np.zeros_like(er, dtype=bool)
    v_value = np.zeros_like(er)
    # Top plate
    v_mask[1, :] = True
    v_value[1, :] = 1.0
    # Bottom plate
    v_mask[-2, :] = True
    v_value[-2, :] = -1.0
    return er, v_mask, v_value


class TestSOR:
    def test_parallel_plates_linear_v(self) -> None:
        n = 32
        er, mask, val = _parallel_plate_setup(n)
        result = solve_sor(er, mask, val, tol=1e-8, max_iter=10_000)
        assert result.iterations < 10_000

        # In the middle column, V should fall linearly from +1 at top plate to -1 at bottom
        col = result.v_field[:, n // 2]
        # The interior between rows 1 and n-2:
        for i in range(2, n - 2):
            expected = 1.0 - 2.0 * (i - 1) / (n - 3)
            assert col[i] == pytest.approx(expected, abs=0.05)

    def test_constant_field_with_dielectric(self) -> None:
        """If εr is uniform, the solve should be insensitive to its value."""
        n = 16
        er_unit, mask, val = _parallel_plate_setup(n)
        er_high = er_unit * 4.4
        r1 = solve_sor(er_unit, mask, val, tol=1e-8)
        r2 = solve_sor(er_high, mask, val, tol=1e-8)
        np.testing.assert_allclose(r1.v_field, r2.v_field, atol=1e-3)

    def test_dirichlet_pixels_unchanged(self) -> None:
        n = 16
        er, mask, val = _parallel_plate_setup(n)
        result = solve_sor(er, mask, val, tol=1e-8)
        assert (result.v_field[mask] == val[mask]).all()


class TestDispatcher:
    def test_auto_picks_sor_for_small(self) -> None:
        n = 16
        er, mask, val = _parallel_plate_setup(n)
        result = solve_laplace(er, mask, val, method="auto", tol=1e-7)
        assert result.method == "sor"

    def test_force_amg(self) -> None:
        n = 16
        er, mask, val = _parallel_plate_setup(n)
        try:
            import pyamg  # noqa: F401
        except ImportError:
            pytest.skip("pyamg not installed")
        result = solve_laplace(er, mask, val, method="amg")
        # AMG should converge to ~the same answer
        result_sor = solve_laplace(er, mask, val, method="sor", tol=1e-9)
        # Check on free pixels
        free = ~mask
        np.testing.assert_allclose(
            result.v_field[free], result_sor.v_field[free], atol=0.05
        )
