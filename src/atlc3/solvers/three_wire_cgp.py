"""Bitmap 3-wire Y-decomposition solver.

For an arbitrary 3-conductor cross-section rasterized as a Usermap (red/+1
signal, blue/−1 signal, green/0 third conductor), this module runs three
Laplace solves — each with one of the three conductors set to *float* — to
obtain the three pair impedances ``z_rcz`` / ``z_gcz`` / ``z_bcz``, then
applies :func:`atlc3.analytical.three_wire.y_decomposition` to recover the
Y-leg impedances ZoR/ZoG/ZoB plus the coupler odd/even-mode impedances.

The radiation indicator ``ignd_ratio`` is estimated from the green-floats
run (red+blue active): under perfect push-pull symmetry the field on the
green conductor's surface integrates to zero net induced charge; otherwise
the |Q_imbalance| / |Q_signal| ratio is the radiation proxy (atlc2's
4 % red-text rule).

For the Y-decomposition algebra and the underlying physics see
``docs/theory/three_wire.md``.
"""

from __future__ import annotations

import numpy as np

from atlc3.analytical._constants import EPS0, MU0
from atlc3.analytical.three_wire import y_decomposition
from atlc3.geometry.usermap import Usermap
from atlc3.results import SolverWarning, ThreeWireResult
from atlc3.solvers import laplace
from atlc3.solvers.cgp import _energy_integral, _extract_masks


def _solve_pair_z0_and_charges(
    usermap: Usermap,
    *,
    plus_mask: np.ndarray,
    minus_mask: np.ndarray,
    floating_mask: np.ndarray,
    method: str = "sor",
    tol: float = 1e-7,
    max_iter: int | None = None,
    floating_mode: str = "boundary_weighted",
) -> tuple[float, np.ndarray]:
    """Run one Laplace solve with a custom plus/minus/floating assignment.

    Returns ``(z0, v_field)``: the pair characteristic impedance under the
    given conductor assignment, plus the converged voltage field (used by
    the caller to compute the radiation indicator).
    """
    er_field = usermap.er_field()

    v_mask = plus_mask | minus_mask
    v_value = np.zeros(usermap.shape, dtype=np.float64)
    v_value[plus_mask] = 1.0
    v_value[minus_mask] = -1.0

    res = laplace.solve_laplace(
        er_field,
        v_mask,
        v_value,
        method=method,
        tol=tol,
        max_iter=max_iter,
        float_groups=[floating_mask] if floating_mask.any() else None,
        floating_mode=floating_mode,
    )

    # Drive voltage is +1 to -1 → 2 V difference.
    v_drive = 2.0
    integral_with_er = _energy_integral(res.v_field, er_field)
    c_filled = EPS0 / (v_drive * v_drive) * integral_with_er

    # Vacuum solve for L extraction.
    er_vac = np.ones_like(er_field)
    res_vac = laplace.solve_laplace(
        er_vac,
        v_mask,
        v_value,
        method=method,
        tol=tol,
        max_iter=max_iter,
        float_groups=[floating_mask] if floating_mask.any() else None,
        floating_mode=floating_mode,
    )
    integral_vac = _energy_integral(res_vac.v_field, er_vac)
    c_vacuum = EPS0 / (v_drive * v_drive) * integral_vac

    if c_vacuum <= 0 or c_filled <= 0:
        raise RuntimeError("3-wire pair solve: non-positive capacitance — bitmap is degenerate")

    l_per_m = MU0 * EPS0 / c_vacuum
    z0 = float(np.sqrt(l_per_m / c_filled))
    return z0, res.v_field


def _conductor_charge(
    v_field: np.ndarray,
    er_field: np.ndarray,
    conductor_mask: np.ndarray,
) -> float:
    """Net induced charge on a conductor (scaled — only the ratio matters).

    Q ∝ ∮ εr E·n dA around the conductor's perimeter. We approximate this
    via the FD outward-flux through the cells immediately adjacent to the
    conductor (sum of α × (V_inside − V_outside) over its boundary edges).
    """
    # For each cell on the conductor boundary, sum α × (V_neighbor − V_self)
    # outward through the conductor's faces. We compute the divergence at
    # conductor cells: each conductor pixel contributes α × (V_neighbor −
    # V_self) for each direction where the neighbor is *not* in the
    # conductor mask.
    charge = 0.0

    for di, dj in ((0, 1), (0, -1), (-1, 0), (1, 0)):
        # Shift the conductor mask to find which conductor pixels have a
        # NON-conductor neighbor in this direction.
        nbr_in_cond = np.zeros_like(conductor_mask)
        if di == 0 and dj == 1:
            nbr_in_cond[:, :-1] = conductor_mask[:, 1:]
        elif di == 0 and dj == -1:
            nbr_in_cond[:, 1:] = conductor_mask[:, :-1]
        elif di == -1:
            nbr_in_cond[1:, :] = conductor_mask[:-1, :]
        else:
            nbr_in_cond[:-1, :] = conductor_mask[1:, :]

        face_mask = conductor_mask & ~nbr_in_cond  # boundary face in this dir

        # Neighbor V and edge α
        nv = np.zeros_like(v_field)
        if di == 0 and dj == 1:
            nv[:, :-1] = v_field[:, 1:]
            er_edge = np.zeros_like(er_field)
            er_edge[:, :-1] = 0.5 * (er_field[:, :-1] + er_field[:, 1:])
        elif di == 0 and dj == -1:
            nv[:, 1:] = v_field[:, :-1]
            er_edge = np.zeros_like(er_field)
            er_edge[:, 1:] = 0.5 * (er_field[:, :-1] + er_field[:, 1:])
        elif di == -1:
            nv[1:, :] = v_field[:-1, :]
            er_edge = np.zeros_like(er_field)
            er_edge[1:, :] = 0.5 * (er_field[:-1, :] + er_field[1:, :])
        else:
            nv[:-1, :] = v_field[1:, :]
            er_edge = np.zeros_like(er_field)
            er_edge[:-1, :] = 0.5 * (er_field[:-1, :] + er_field[1:, :])

        charge += float((er_edge * (nv - v_field) * face_mask).sum())

    return charge


def solve_modes(
    usermap: Usermap,
    *,
    method: str = "sor",
    tol: float = 1e-7,
    max_iter: int | None = None,
    floating_mode: str = "boundary_weighted",
) -> ThreeWireResult:
    """Bitmap Y-decomposition of a 3-conductor line.

    Three Laplace solves are performed, each with one of the three
    conductors set to float. The resulting pair impedances are combined
    via :func:`atlc3.analytical.three_wire.y_decomposition` to give
    ZoR/ZoG/ZoB and the coupler odd/even modes.

    Parameters
    ----------
    usermap
        Usermap with at least red (+1), blue (−1), and green (0) conductor
        pixels — :func:`atlc3.solvers.cgp._extract_masks` is used to find
        them. Floating conductors already in the usermap (use="float") are
        ignored — this routine treats one of (R, G, B) as floating per run.
    method
        Laplace solver (``"sor"`` / ``"amg"`` / ``"auto"``).
    floating_mode
        ``"boundary_weighted"`` (default) or ``"average"`` — see
        :mod:`atlc3.solvers.laplace`.

    Returns
    -------
    ThreeWireResult
        Pair impedances + Y-decomposition + odd/even modes + radiation
        indicator + warnings.
    """
    plus, minus, ground, _ = _extract_masks(usermap)
    if not plus.any() or not minus.any() or not ground.any():
        raise ValueError(
            "solve_modes requires red (+1), blue (−1), and green (0) conductors "
            "in the usermap; got "
            f"plus={plus.any()}, minus={minus.any()}, ground={ground.any()}"
        )

    # Run 1: green floats, red & blue active → z_gcz
    z_gcz, v_gcz = _solve_pair_z0_and_charges(
        usermap,
        plus_mask=plus,
        minus_mask=minus,
        floating_mask=ground,
        method=method,
        tol=tol,
        max_iter=max_iter,
        floating_mode=floating_mode,
    )

    # Run 2: red floats, green (now +V) & blue (-V) active → z_rcz
    z_rcz, _ = _solve_pair_z0_and_charges(
        usermap,
        plus_mask=ground,
        minus_mask=minus,
        floating_mask=plus,
        method=method,
        tol=tol,
        max_iter=max_iter,
        floating_mode=floating_mode,
    )

    # Run 3: blue floats, red (+V) & green (now -V) active → z_bcz
    z_bcz, _ = _solve_pair_z0_and_charges(
        usermap,
        plus_mask=plus,
        minus_mask=ground,
        floating_mask=minus,
        method=method,
        tol=tol,
        max_iter=max_iter,
        floating_mode=floating_mode,
    )

    zo_r, zo_g, zo_b = y_decomposition(z_rcz, z_gcz, z_bcz)

    z_odd = 2.0 * abs(zo_r) if zo_r > 0 else 1.0
    z_even = abs(zo_r) / 2.0 + abs(zo_b) if (zo_r > 0 and zo_b > 0) else 1.0

    # Radiation indicator: from the green-floats run, compute charges on
    # red and blue. Under perfect push-pull symmetry Q_red + Q_blue = 0.
    er_field = usermap.er_field()
    q_red = _conductor_charge(v_gcz, er_field, plus)
    q_blue = _conductor_charge(v_gcz, er_field, minus)
    q_signal = max(abs(q_red), abs(q_blue))
    ignd_ratio = abs(q_red + q_blue) / q_signal if q_signal > 0 else 0.0

    warnings: list[SolverWarning] = []
    if ignd_ratio > 0.04:
        warnings.append(
            SolverWarning(
                code="radiating_3wire",
                message=(
                    f"Net ground current |Ignd/Isig| ≈ {ignd_ratio * 100:.1f}% > 4%; "
                    "this geometry is radiating and reported Z₀ values are "
                    "approximate."
                ),
                severity="warning",
            )
        )

    return ThreeWireResult(
        z_rcz=z_rcz,
        z_gcz=z_gcz,
        z_bcz=z_bcz,
        zo_r=zo_r,
        zo_g=zo_g,
        zo_b=zo_b,
        z_odd=z_odd,
        z_even=z_even,
        ignd_ratio=ignd_ratio,
        method="bitmap-laplace-y-decomposition",
        warnings=warnings,
    )


__all__ = ["solve_modes"]
