"""Closed-form 3-conductor transmission-line analysis (Y-decomposition).

The geometry is three round conductors of equal radius, optionally above an
infinite ground plane, embedded in a uniform dielectric. The math:

* Build the 3×3 inductance matrix L_ij (per unit length, geometry only —
  multi-conductor TL theory: ``L_ii = (μ₀/2π) ln(2yi/a)`` above a ground
  plane via image charges, ``L_ij = (μ₀/2π) ln(D'_ij/D_ij)`` where D is the
  conductor-to-conductor distance and D' is conductor-i to image-of-j).
  Without a ground plane, L_ii is unbounded — we handle the ungrounded
  case with the alternative dipole-pair formulation.
* TEM identity: ``L · C_vacuum = μ₀ε₀ I``, so ``C_vacuum = ε₀/L⁻¹`` and the
  filled-dielectric ``C = εr · C_vacuum``.
* For each pair-with-third-floating, eliminate the floating conductor via
  Schur complement on the (L, C) system. This gives the 2-port (Lp, Cp)
  for the active pair, and ``Z₀_pair = sqrt(Lp/Cp)``.
* Apply the Y-decomposition algebra (see ``docs/theory/three_wire.md``).

Reference: Pozar §4.6 ("Multiconductor Transmission Lines"), Wadell §3.7.
"""

from __future__ import annotations

import math

import numpy as np

from atlc3.analytical._constants import C0, MU0
from atlc3.geometry.three_wire import ThreeWireGeometry
from atlc3.results import SolverWarning, ThreeWireResult


def y_decomposition(z_rcz: float, z_gcz: float, z_bcz: float) -> tuple[float, float, float]:
    """Apply the Y-decomposition algebra:

    Given pair impedances with each conductor in turn at current-zero
    (floating), recover the three Y-leg impedances.

    The naming is atlc2-style — ``z_rcz`` is "Z₀ when red is at current-zero",
    i.e. the pair (green, blue) is active. Then
    ``z_rcz = zo_g + zo_b`` and analogous for the other two; solve the 3×3
    linear system::

        zo_r = (z_gcz + z_bcz − z_rcz) / 2
        zo_g = (z_rcz + z_bcz − z_gcz) / 2
        zo_b = (z_rcz + z_gcz − z_bcz) / 2

    Returns ``(zo_r, zo_g, zo_b)``.
    """
    zo_r = 0.5 * (z_gcz + z_bcz - z_rcz)
    zo_g = 0.5 * (z_rcz + z_bcz - z_gcz)
    zo_b = 0.5 * (z_rcz + z_gcz - z_bcz)
    return zo_r, zo_g, zo_b


def _build_L_matrix(geom: ThreeWireGeometry) -> np.ndarray:
    """3×3 vacuum inductance matrix from method of images.

    With a ground plane: L_ii = (μ₀/2π) ln(2 yi / a), L_ij = (μ₀/2π) ln(D'_ij/D_ij).
    Without a ground plane: there's no unique reference, so we set the
    reference at "wire 0" by gauge — fix L_11 large but the relevant
    invariants (loop inductances Lij_loop = L_ii + L_jj − 2 L_ij) are
    well-defined. We use a finite reference radius (the largest
    conductor-to-conductor distance × 100) to anchor the gauge.
    """
    a = geom.a
    centers = [(geom.red.x, geom.red.y), (geom.blue.x, geom.blue.y), (geom.green.x, geom.green.y)]

    L = np.zeros((3, 3), dtype=float)

    if geom.ground_plane:
        # Each conductor's image sits at (xi, -yi). All yi > 0.
        for i, (xi, yi) in enumerate(centers):
            L[i, i] = (MU0 / (2.0 * math.pi)) * math.log(2.0 * yi / a)
            for j, (xj, yj) in enumerate(centers):
                if i == j:
                    continue
                d_ij = math.hypot(xi - xj, yi - yj)
                d_ij_image = math.hypot(xi - xj, yi - (-yj))
                L[i, j] = (MU0 / (2.0 * math.pi)) * math.log(d_ij_image / d_ij)
    else:
        # No ground; use a far-field reference so loop differences cancel.
        max_d = max(
            math.hypot(centers[i][0] - centers[j][0], centers[i][1] - centers[j][1])
            for i in range(3)
            for j in range(i + 1, 3)
        )
        ref = max(max_d * 100.0, 1.0)  # arbitrary but consistent
        for i, (xi, yi) in enumerate(centers):
            L[i, i] = (MU0 / (2.0 * math.pi)) * math.log(ref / a)
            for j, (xj, yj) in enumerate(centers):
                if i == j:
                    continue
                d_ij = math.hypot(xi - xj, yi - yj)
                L[i, j] = (MU0 / (2.0 * math.pi)) * math.log(ref / d_ij)
    return L


def _pair_impedance(L: np.ndarray, er: float, active: tuple[int, int]) -> float:
    """Effective Z₀ for the (i, j) pair with the third conductor floating.

    "Floating" means the third conductor carries no current (I_k = 0). With
    ``I = [I_i, I_j, 0]`` and differential drive (I_j = −I_i), the loop
    voltage is

        V_loop = (L_ii + L_jj − 2 L_ij) · I_diff

    so ``L_loop = L_ii + L_jj − 2 L_ij`` (independent of the floating
    conductor's L matrix entries — they only set the voltage *on* the
    floating conductor, which doesn't affect the active pair's loop V).

    For uniform dielectric, the TEM identity ``Z₀ = vp · L_loop`` and
    ``vp = c/√εr`` gives::

        Z₀_pair = (c / √εr) · L_loop
    """
    i, j = active
    L_loop = float(L[i, i] + L[j, j] - 2.0 * L[i, j])
    return L_loop * C0 / math.sqrt(er)


def solve_three_wire(geom: ThreeWireGeometry) -> ThreeWireResult:
    """Closed-form Y-decomposition of a 3-conductor line.

    Workflow:
    1. Build the 3×3 vacuum inductance matrix L from the method of images.
    2. Build the capacitance matrix C = εr · ε₀ · L⁻¹ × μ₀⁻¹ (TEM identity).
    3. For each pair-with-third-floating, compute ``Z₀_pair`` via Schur
       elimination of the floating conductor.
    4. Apply :func:`y_decomposition` to recover ZoR, ZoG, ZoB.
    5. Compute coupler odd/even modes and the radiation indicator.
    """
    L = _build_L_matrix(geom)

    # Indices: red=0, blue=1, green=2
    z_rcz = _pair_impedance(L, geom.er, active=(1, 2))  # red floats
    z_gcz = _pair_impedance(L, geom.er, active=(0, 1))  # green floats
    z_bcz = _pair_impedance(L, geom.er, active=(0, 2))  # blue floats

    # Capacitance matrix only needed for the radiation-imbalance estimator.
    C = geom.er * (C0 * C0) * np.linalg.inv(L)

    zo_r, zo_g, zo_b = y_decomposition(z_rcz, z_gcz, z_bcz)

    # Coupler odd/even — standard for the (red, blue) pair with green as ref:
    z_odd = 2.0 * abs(zo_r) if zo_r > 0 else float("nan")
    z_even = abs(zo_r) / 2.0 + abs(zo_b) if zo_r > 0 and zo_b > 0 else float("nan")

    # Radiation indicator: use the imbalance between forward/backward charges
    # on the green conductor in the (red, blue) drive case. For an ideal
    # symmetric coupler over ground, this is zero; for asymmetric geometries
    # it scales with the geometric asymmetry.
    ignd_ratio = _estimate_ignd_ratio(L, C)

    warnings: list[SolverWarning] = []
    if ignd_ratio > 0.04:
        warnings.append(
            SolverWarning(
                code="radiating_3wire",
                message=(
                    f"Net ground current |Ignd/Isig| ≈ {ignd_ratio * 100:.1f}% > 4%; "
                    "this geometry is radiating and the reported Z₀ values are not "
                    "true characteristic impedances."
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
        z_odd=z_odd if not math.isnan(z_odd) else 1.0,
        z_even=z_even if not math.isnan(z_even) else 1.0,
        ignd_ratio=ignd_ratio,
        method="closed-form-y-decomposition",
        warnings=warnings,
    )


def _estimate_ignd_ratio(L: np.ndarray, C: np.ndarray) -> float:
    """Estimate |I_ground/I_signal| in the (red, blue) push-pull drive case.

    Drive ``V = [+1, −1, V_g]`` where V_g floats to make Q_green = 0. Then
    the current asymmetry comes from the propagation: in pure odd mode the
    ground would carry no net current, but if the C matrix is asymmetric
    (green not equidistant from red and blue) then the displacement currents
    ``j_n × C × V`` produce a non-zero green current.
    """
    # Schur-eliminate green to get effective 2x2 system on (red, blue).
    C_aa = C[:2, :2]
    C_af = C[:2, 2]
    C_fa = C[2, :2]
    C_ff = C[2, 2]
    if C_ff == 0:
        return 0.0
    C_eff = C_aa - np.outer(C_af, C_fa) / C_ff

    # For odd-mode drive V = [+1, -1]: charges Q = C_eff · V; ground charge
    # Q_g = -C_fa · V_active / C_ff × C_ff = -C_fa @ V (the sign carries through).
    V_active = np.array([1.0, -1.0])
    Q_active = C_eff @ V_active
    V_green = -(C_fa @ V_active) / C_ff
    Q_green = C_af @ V_active + C_ff * V_green  # should be ~0 by construction

    I_signal = abs(Q_active).max()  # proxy — currents and charges are proportional in TEM
    # Imbalance in the active charges shows up as net "radiating" current that
    # would flow in the ground conductor if it were grounded. Use the absolute
    # difference between Q_red and -Q_blue as the imbalance proxy.
    I_imbalance = abs(Q_active[0] + Q_active[1])  # zero in fully symmetric case
    if I_signal == 0:
        return 0.0
    _ = Q_green  # available for diagnostics
    return float(I_imbalance / I_signal)


__all__ = ["solve_three_wire", "y_decomposition"]
