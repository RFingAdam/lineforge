"""Direct odd / even / diff mode solve for differential pairs.

Phase 1's analytical formulas use the IPC-2141A coupling correction:

    Z_odd  = Z0 · (1 − coupling)
    Z_even = Z0 · (1 + coupling)

This is empirical and loses accuracy for tightly coupled pairs (S/H < 0.5).
For the bitmap path, lineforge can drive the C/Gp Laplace solver with explicit
odd/even-mode BCs:

    Odd  mode: V(strip 1) = +1, V(strip 2) = −1   → Z_odd direct
    Even mode: V(strip 1) = +1, V(strip 2) = +1   → Z_even direct

Both modes share the ground BC. Run two separate Laplace solves; extract the
*per-line* mode capacitance (see :func:`_solve_with_strip_voltages`) and
$Z_\text{odd/even} = \\sqrt{L_\\text{vac}/C_\\text{odd/even}}$. These are the
per-line mode impedances of Paul, MTL 2nd ed. §5, that is
$C_\\text{odd} = C_{11} - C_{12}$ and $C_\\text{even} = C_{11} + C_{12}$ of the
Maxwell capacitance matrix; :mod:`lineforge.solvers.mtl` reproduces them from an
N-conductor solve.

The differential and common-mode impedances then follow exactly (not by the
IPC-2141A approximation): $Z_\\text{diff} = 2 Z_\\text{odd}$ and
$Z_\\text{common} = Z_\\text{even} / 2$; typically within 1% of measured for
tight pairs.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from lineforge.analytical._constants import EPS0, MU0
from lineforge.geometry.usermap import Usermap
from lineforge.solvers import extension, laplace

Mode = Literal["odd", "even", "diff", "common"]


class DiffModeResult(BaseModel):
    """Result of a direct odd/even-mode bitmap solve."""

    model_config = ConfigDict(extra="forbid")

    z_odd: float = Field(..., gt=0)
    z_even: float = Field(..., gt=0)
    z_diff: float = Field(..., gt=0)
    z_common: float = Field(..., gt=0)
    eps_eff_odd: float = Field(..., ge=1)
    eps_eff_even: float = Field(..., ge=1)
    method: str = Field("bitmap-direct-mode")


def _solve_with_strip_voltages(
    usermap: Usermap, v_strip_1: float, v_strip_2: float
) -> tuple[float, float]:
    """Run two Laplace solves (with εr and with vacuum) and return (C_per_m, vp).

    Strip 1 gets ``v_strip_1``, strip 2 gets ``v_strip_2``. Atlc3 identifies
    "strip 1" as the V=+1 conductor and "strip 2" as the V=-1 conductor in
    the *original* usermap. The function temporarily reassigns voltage masks.
    """
    extended = extension.extend(usermap)
    er = extended.er_field()
    plus = extended.conductor_mask("+1")
    minus = extended.conductor_mask("-1")
    ground = extended.conductor_mask("0")

    v_mask = plus | minus | ground
    v_value = np.zeros(extended.shape, dtype=np.float64)
    v_value[plus] = v_strip_1
    v_value[minus] = v_strip_2
    v_value[ground] = 0.0

    res = laplace.solve_laplace(er, v_mask, v_value, method="auto", tol=1e-7)
    res_vac = laplace.solve_laplace(np.ones_like(er), v_mask, v_value, method="auto", tol=1e-7)

    # ∫ εr |E|² dA
    def integrate(v_field: np.ndarray, er_field: np.ndarray) -> float:
        Ex = np.zeros_like(v_field)
        Ex[:, 1:-1] = -(v_field[:, 2:] - v_field[:, :-2]) / 2.0
        Ey = np.zeros_like(v_field)
        Ey[1:-1, :] = -(v_field[2:, :] - v_field[:-2, :]) / 2.0
        return float(np.sum(er_field * (Ex * Ex + Ey * Ey)))

    integ = integrate(res.v_field, er)
    integ_vac = integrate(res_vac.v_field, np.ones_like(er))

    # Per-line mode capacitance. The stored energy of the two driven strips is
    # Σ_lines C_mode · V_line², so C_mode = ε₀ ∫ εr|E|² dA / (n_lines · V_line²).
    # This is the quantity that pairs with the per-line mode inductance in
    # Z_odd/even = √(L_mode/C_mode) (Paul, MTL 2nd ed. §5; C_odd = C11 − C12,
    # C_even = C11 + C12 of the Maxwell matrix), so the odd drive (±1 V) is
    # normalized by 2, not by the 2 V differential drive squared.
    #
    # This normalization is only valid for the two symmetric drives this module
    # applies (±1 and +1/+1) on a symmetric pair, where both lines carry the
    # same |V| and the same mode capacitance. It is not a general N-conductor
    # formula: use solvers.mtl.solve_maxwell for arbitrary drives.
    #
    # The pixel-unit gradients and pixel-unit areas already cancel the dx
    # factors (see cgp._energy_integral): no pixel_width² scaling belongs here.
    n_lines = 2.0
    v_line_sq = 0.5 * (v_strip_1 * v_strip_1 + v_strip_2 * v_strip_2)
    if v_line_sq <= 0.0:
        raise ValueError("mode solve needs a non-zero drive on at least one strip")
    C_per_m = EPS0 * integ / (n_lines * v_line_sq)
    C_vac_per_m = EPS0 * integ_vac / (n_lines * v_line_sq)
    if C_vac_per_m <= 0:
        return 0.0, 0.0
    eps_eff = C_per_m / C_vac_per_m
    return C_per_m, eps_eff


def solve_modes(usermap: Usermap) -> DiffModeResult:
    """Direct odd/even mode solve.

    Requires the usermap to have V=+1 (red) and V=-1 (blue) conductors as the
    differential pair. A V=0 (green) ground is optional.
    """
    if not (usermap.conductor_mask("+1").any() and usermap.conductor_mask("-1").any()):
        raise ValueError("solve_modes requires both +1 and -1 conductor pixels in the usermap")

    # Odd mode: V = +1, -1
    C_odd, eps_eff_odd = _solve_with_strip_voltages(usermap, +1.0, -1.0)
    # Even mode: V = +1, +1
    C_even, eps_eff_even = _solve_with_strip_voltages(usermap, +1.0, +1.0)

    if C_odd <= 0 or C_even <= 0:
        raise RuntimeError(
            "mode solve produced non-positive capacitance; "
            "check geometry and increase pixel resolution"
        )

    L_odd = MU0 * EPS0 * eps_eff_odd / C_odd  # L stays the same for both modes (vacuum-derived)
    L_even = MU0 * EPS0 * eps_eff_even / C_even
    Z_odd = float(np.sqrt(L_odd / C_odd))
    Z_even = float(np.sqrt(L_even / C_even))

    return DiffModeResult(
        z_odd=Z_odd,
        z_even=Z_even,
        z_diff=2.0 * Z_odd,
        z_common=Z_even / 2.0,
        eps_eff_odd=eps_eff_odd,
        eps_eff_even=eps_eff_even,
    )


__all__ = ["DiffModeResult", "solve_modes"]
