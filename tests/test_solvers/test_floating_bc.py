"""Tests for the floating-conductor boundary condition in the Laplace solver.

Validates both modes:
  - ``floating_mode="average"``: simple within-group V averaging (default)
  - ``floating_mode="boundary_weighted"``: εr-weighted external-neighbor
    average (Phase B2, more accurate for asymmetric εr)
"""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.solvers.laplace import _equipotential_boundary_weighted, solve_sor


def _two_plate_setup(n: int = 41, *, er_top: float = 1.0, er_bot: float = 1.0):
    """41x41 grid: V=+1 at top row, V=0 at bottom row, optional εr split halfway."""
    er = np.full((n, n), er_top, dtype=float)
    er[n // 2 :, :] = er_bot
    v_mask = np.zeros((n, n), dtype=bool)
    v_value = np.zeros((n, n), dtype=float)
    v_mask[0, :] = True
    v_value[0, :] = 1.0
    v_mask[-1, :] = True
    v_value[-1, :] = 0.0
    return er, v_mask, v_value


def _floating_square(n: int, top: int, size: int = 5):
    fg = np.zeros((n, n), dtype=bool)
    fg[top : top + size, n // 2 - size // 2 : n // 2 + size // 2 + 1] = True
    return fg


class TestSymmetricFloatingSquare:
    """A floating square centered between symmetric ground/V plates → V=0.5."""

    def test_average_mode_finds_centroid_v(self) -> None:
        n = 41
        er, v_mask, v_value = _two_plate_setup(n)
        fg = _floating_square(n, top=18)
        r = solve_sor(er, v_mask, v_value, float_groups=[fg], floating_mode="average", tol=1e-9)
        v_f = float(r.v_field[fg].mean())
        assert v_f == pytest.approx(0.5, abs=1e-3)

    def test_boundary_weighted_mode_finds_centroid_v(self) -> None:
        n = 41
        er, v_mask, v_value = _two_plate_setup(n)
        fg = _floating_square(n, top=18)
        r = solve_sor(
            er,
            v_mask,
            v_value,
            float_groups=[fg],
            floating_mode="boundary_weighted",
            tol=1e-9,
        )
        v_f = float(r.v_field[fg].mean())
        assert v_f == pytest.approx(0.5, abs=1e-3)

    def test_modes_agree_on_symmetric_problem(self) -> None:
        """For symmetric geometry+εr, both modes converge to identical V."""
        n = 41
        er, v_mask, v_value = _two_plate_setup(n)
        fg = _floating_square(n, top=18)
        r_avg = solve_sor(er, v_mask, v_value, float_groups=[fg], floating_mode="average")
        r_bw = solve_sor(er, v_mask, v_value, float_groups=[fg], floating_mode="boundary_weighted")
        assert float(r_avg.v_field[fg].mean()) == pytest.approx(
            float(r_bw.v_field[fg].mean()), abs=1e-6
        )


class TestAsymmetricEr:
    """When εr is asymmetric, boundary_weighted is more accurate than average."""

    def test_boundary_weighted_closer_to_no_floating_reference(self) -> None:
        """Sanity baseline: V at the floating-square location *without* the
        floating conductor inserted is ≈ 0.21 (linear-in-εr profile).
        boundary_weighted converges close to this; average overshoots."""
        n = 41
        er, v_mask, v_value = _two_plate_setup(n, er_top=1.0, er_bot=4.0)
        fg = _floating_square(n, top=18)

        # Reference: no floating conductor at all
        r_ref = solve_sor(er, v_mask, v_value, tol=1e-9)
        v_ref = float(r_ref.v_field[fg].mean())

        r_avg = solve_sor(er, v_mask, v_value, float_groups=[fg], floating_mode="average", tol=1e-9)
        v_avg = float(r_avg.v_field[fg].mean())
        r_bw = solve_sor(
            er,
            v_mask,
            v_value,
            float_groups=[fg],
            floating_mode="boundary_weighted",
            tol=1e-9,
        )
        v_bw = float(r_bw.v_field[fg].mean())

        # boundary_weighted should be closer to the reference than average is.
        err_avg = abs(v_avg - v_ref)
        err_bw = abs(v_bw - v_ref)
        assert err_bw < err_avg, (
            f"boundary_weighted ({v_bw:.4f}) should be closer to reference "
            f"({v_ref:.4f}) than average ({v_avg:.4f}) — got errs avg={err_avg:.4f}, "
            f"bw={err_bw:.4f}"
        )


class TestNoFloatingGroupsNoOp:
    """Solver with no float_groups should match itself with empty list."""

    def test_no_floating_groups_no_change(self) -> None:
        n = 21
        er, v_mask, v_value = _two_plate_setup(n)
        r1 = solve_sor(er, v_mask, v_value, tol=1e-9)
        r2 = solve_sor(er, v_mask, v_value, float_groups=[], tol=1e-9)
        np.testing.assert_allclose(r1.v_field, r2.v_field, atol=1e-9)


class TestEmptyGroupSkipped:
    """A floating group that's all-False should be skipped, not crash."""

    def test_empty_group(self) -> None:
        n = 21
        er, v_mask, v_value = _two_plate_setup(n)
        empty = np.zeros((n, n), dtype=bool)
        # Should run without error
        r = solve_sor(er, v_mask, v_value, float_groups=[empty], tol=1e-9)
        assert r.converged


class TestEquipotentialBoundaryWeightedHelper:
    """Direct unit tests of the helper used by boundary_weighted mode."""

    def test_uniform_field_returns_centroid(self) -> None:
        """In a uniform field with α=1, the helper returns the average of
        the boundary-neighbor potentials, which equals the centroid V."""
        n = 21
        v = np.linspace(0, 1, n).reshape(-1, 1).repeat(n, axis=1)  # V varies with row
        aE = aW = aN = aS = np.ones_like(v)
        fg = np.zeros_like(v, dtype=bool)
        fg[8:13, 8:13] = True
        v_f = _equipotential_boundary_weighted(v, aE, aW, aN, aS, fg)
        # Floating square is at rows 8-12 (centroid at 10). V[10, *] = 10/20 = 0.5.
        assert v_f == pytest.approx(0.5, abs=1e-2)

    def test_off_grid_treated_as_outside(self) -> None:
        """A group that touches a grid edge sees the off-grid Dirichlet V=0
        as part of its external boundary (zero-padded for the outer BC).
        This anchors the floating conductor toward 0 even when nothing else
        in the grid is actively pulling it down."""
        n = 7
        v = np.full((n, n), 0.5)
        a = np.ones_like(v)
        fg = np.zeros_like(v, dtype=bool)
        fg[0, :] = True  # top row, against the off-grid boundary at top
        v_f = _equipotential_boundary_weighted(v, a, a, a, a, fg)
        # Top row's "outside" neighbors: row 1 (V=0.5) below, plus off-grid (V=0)
        # to the top. Result is between 0 and 0.5, biased toward the row-1 side
        # because there are more in-row external edges than off-grid edges.
        assert 0.0 <= v_f <= 0.5
