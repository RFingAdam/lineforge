"""Wadell formulas: stripline, CPWG, edge-coupled and broadside-coupled differential pairs.

References
----------
- B. Wadell, *Transmission Line Design Handbook*, Artech House 1991, Chapters 3 & 4.
- IPC-2141A, *Design Guide for High-Speed Controlled Impedance Circuit Boards*.
- S. B. Cohn, *Characteristic Impedance of the Shielded-Strip Transmission Line*,
  IRE Trans. MTT, July 1954 (stripline).
- C. P. Wen, *Coplanar Waveguide: A Surface Strip Transmission Line Suitable for
  Nonreciprocal Gyromagnetic Device Applications*, IEEE MTT-S 1969 (CPWG).

All formulas are closed-form approximations valid over published ranges. For
out-of-range geometries, fall back to the bitmap kernel (Phase 2/3).
"""

from __future__ import annotations

import math

from scipy.special import ellipk

from atlc3.analytical._constants import C0, ETA0, INCH_M
from atlc3.geometry.types import (
    CPWG,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    StriplineAsymmetric,
    StriplineSymmetric,
)
from atlc3.results import DiffResult, SolverWarning, TLineResult


# ---------------------------------------------------------------------------
# Stripline
# ---------------------------------------------------------------------------


def _stripline_thickness_correction_cf(W: float, B: float, T: float) -> float:
    """Wadell §3.4.2: fringing-capacitance correction Cf' for finite-thickness strip.

    Returns the effective normalized capacitance ratio used in the Cohn formula.
    """
    if T <= 0:
        return 0.0
    m = 2.0 * B / (B - T) if B > T else 1.0
    cf_prime = (
        (B / (math.pi * (B - T)))
        * ((m * math.log((m + 1.0) / (m - 1.0))) - math.log((m * m - 1.0) / 4.0))
    )
    return cf_prime


def stripline_symmetric(
    geometry: StriplineSymmetric,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve a symmetric stripline via Cohn / Wadell.

    Uses the wide-strip (W/(B−T) > 0.35) Cohn formula with Wadell's
    finite-thickness correction. Validity: ``W/(B-T) > 0.35``, ``T < 0.25·B``.
    """
    W, T, B, er = geometry.W, geometry.T, geometry.B, geometry.er

    issues: list[SolverWarning] = []
    if W / (B - T) < 0.35:
        msg = "Stripline narrow-strip regime (W/(B−T) < 0.35) is approximated; ±2% accuracy"
        issues.append(SolverWarning(code="narrow_strip", message=msg, severity="info"))
    if T > 0.25 * B:
        msg = "Stripline T > 0.25·B is outside Cohn formula validity"
        issues.append(SolverWarning(code="thick_strip", message=msg))

    cf_prime = _stripline_thickness_correction_cf(W, B, T)

    # Cohn wide-strip formula: Z0 = η0 / (sqrt(εr) · 4 · ((W/(B−T)) + Cf'/π))
    z0 = ETA0 / (math.sqrt(er) * 4.0 * (W / (B - T) + cf_prime / math.pi))

    eps_eff = er  # stripline is fully embedded — no air dispersion
    vp = C0 / math.sqrt(eps_eff)
    td_per_in = INCH_M / vp

    return TLineResult(
        z0=z0,
        eps_eff=eps_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        conductor_loss_db_per_in=None,
        dielectric_loss_db_per_in=_dielectric_loss(er, geometry.tan_delta, frequency_hz),
        method="cohn-stripline-symmetric",
        frequency_hz=frequency_hz,
        warnings=issues,
    )


def stripline_asymmetric(
    geometry: StriplineAsymmetric,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve an asymmetric (offset) stripline via the parallel-plate model (Wadell §3.5).

    Models the asymmetric stripline as two symmetric striplines in parallel:
    one with cavity 2·H1 (above), the other with 2·H2 (below). Each is solved
    via :func:`stripline_symmetric`; their characteristic admittances are summed.
    """
    W, T, H1, H2, er = (
        geometry.W,
        geometry.T,
        geometry.H1,
        geometry.H2,
        geometry.er,
    )

    upper = StriplineSymmetric(W=W, T=T, B=2 * H1 + T, er=er, tan_delta=geometry.tan_delta)
    lower = StriplineSymmetric(W=W, T=T, B=2 * H2 + T, er=er, tan_delta=geometry.tan_delta)
    z_upper = stripline_symmetric(upper, frequency_hz=frequency_hz).z0
    z_lower = stripline_symmetric(lower, frequency_hz=frequency_hz).z0

    # Two transmission lines in parallel: Y_total = Y_upper + Y_lower
    z0 = 1.0 / (1.0 / z_upper + 1.0 / z_lower)
    eps_eff = er
    vp = C0 / math.sqrt(eps_eff)
    td_per_in = INCH_M / vp

    return TLineResult(
        z0=z0,
        eps_eff=eps_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        dielectric_loss_db_per_in=_dielectric_loss(er, geometry.tan_delta, frequency_hz),
        method="wadell-stripline-asymmetric",
        frequency_hz=frequency_hz,
    )


# ---------------------------------------------------------------------------
# CPWG (Coplanar Waveguide with Ground)
# ---------------------------------------------------------------------------


def _kp(k: float) -> float:
    """Complementary modulus k' = sqrt(1 − k²)."""
    return math.sqrt(1.0 - k * k)


def _kk(k: float) -> float:
    """Ratio K(k) / K(k') of complete elliptic integrals (numerically robust)."""
    if k <= 0:
        return 0.0
    if k >= 1:
        return float("inf")
    # ellipk in scipy takes m = k²
    return float(ellipk(k * k) / ellipk(_kp(k) ** 2))


def cpwg(
    geometry: CPWG,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve a coplanar waveguide with ground plane (CPWG).

    Uses Wen's elliptic-integral formula (Wadell §3.6.4 / IPC-2141A):

        εeff = (1 + εr · K(k')/K(k) · K(k1)/K(k1')) / (1 + K(k')/K(k) · K(k1)/K(k1'))
        Z0   = (60π / sqrt(εeff)) / (K(k)/K(k') + K(k1)/K(k1'))

    where:
        k  = W / (W + 2S)
        k1 = tanh(πW / 4H) / tanh(π(W + 2S) / 4H)

    Validity: W/H ≥ 0.05, conductor thickness T ignored (good if T ≪ W,S).
    """
    W, S, H, er = geometry.W, geometry.S, geometry.H, geometry.er

    issues: list[SolverWarning] = []
    if geometry.T > 0.1 * min(W, S):
        issues.append(
            SolverWarning(
                code="thick_conductor",
                message=(
                    "T > 0.1·min(W,S): closed-form CPWG ignores T; "
                    "consider the bitmap kernel for accuracy"
                ),
                severity="info",
            )
        )

    k = W / (W + 2.0 * S)
    a = math.tanh(math.pi * W / (4.0 * H))
    b = math.tanh(math.pi * (W + 2.0 * S) / (4.0 * H))
    k1 = a / b

    kk_ratio = _kk(k)
    kk1_ratio = _kk(k1)

    eps_eff = (1.0 + er * (1.0 / kk_ratio) * kk1_ratio) / (1.0 + (1.0 / kk_ratio) * kk1_ratio)
    z0 = (60.0 * math.pi / math.sqrt(eps_eff)) / (kk_ratio + kk1_ratio)

    vp = C0 / math.sqrt(eps_eff)
    td_per_in = INCH_M / vp

    return TLineResult(
        z0=z0,
        eps_eff=eps_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        dielectric_loss_db_per_in=_dielectric_loss(eps_eff, geometry.tan_delta, frequency_hz),
        method="wen-cpwg",
        frequency_hz=frequency_hz,
        warnings=issues,
    )


# ---------------------------------------------------------------------------
# Differential pairs
# ---------------------------------------------------------------------------


def edge_coupled_diff_microstrip(
    geometry: EdgeCoupledDiffMicrostrip,
    *,
    frequency_hz: float | None = None,
) -> DiffResult:
    """Edge-coupled differential pair (microstrip), Wadell §6.3 / IPC-2141A.

    Approach: compute Z0 of each individual trace via Hammerstad-Jensen, then
    apply the IPC-2141A coupling correction:
        Zodd  = Z0 · (1 − 0.48·exp(−0.96·S/H))
        Zeven = Z0 · (1 + 0.48·exp(−0.96·S/H))
    """
    from atlc3.analytical.hammerstad import microstrip
    from atlc3.geometry.types import Microstrip

    single = Microstrip(
        W=geometry.W, H=geometry.H, T=geometry.T, er=geometry.er,
        tan_delta=geometry.tan_delta, rho=geometry.rho,
    )
    base = microstrip(single, frequency_hz=frequency_hz)
    sH = geometry.S / geometry.H
    coupling = 0.48 * math.exp(-0.96 * sH)

    z_odd = base.z0 * (1.0 - coupling)
    z_even = base.z0 * (1.0 + coupling)

    return DiffResult(
        z_odd=z_odd,
        z_even=z_even,
        z_diff=2.0 * z_odd,
        z_common=z_even / 2.0,
        eps_eff_odd=base.eps_eff,
        eps_eff_even=base.eps_eff,
        vp_odd=base.vp,
        vp_even=base.vp,
        method="ipc2141-edge-coupled-diff-microstrip",
        frequency_hz=frequency_hz,
    )


def edge_coupled_diff_stripline(
    geometry: EdgeCoupledDiffStripline,
    *,
    frequency_hz: float | None = None,
) -> DiffResult:
    """Edge-coupled differential pair (stripline), Wadell §6.4 / IPC-2141A.

    Same coupling correction as edge-coupled microstrip, applied to the stripline
    single-trace Z0:
        Zodd  = Z0 · (1 − 0.347·exp(−2.9·S/B))
        Zeven = Z0 · (1 + 0.347·exp(−2.9·S/B))
    """
    base_geom = StriplineSymmetric(
        W=geometry.W, T=geometry.T, B=geometry.B, er=geometry.er, tan_delta=geometry.tan_delta,
    )
    base = stripline_symmetric(base_geom, frequency_hz=frequency_hz)
    sB = geometry.S / geometry.B
    coupling = 0.347 * math.exp(-2.9 * sB)

    z_odd = base.z0 * (1.0 - coupling)
    z_even = base.z0 * (1.0 + coupling)

    return DiffResult(
        z_odd=z_odd,
        z_even=z_even,
        z_diff=2.0 * z_odd,
        z_common=z_even / 2.0,
        eps_eff_odd=base.eps_eff,
        eps_eff_even=base.eps_eff,
        vp_odd=base.vp,
        vp_even=base.vp,
        method="ipc2141-edge-coupled-diff-stripline",
        frequency_hz=frequency_hz,
    )


def broadside_coupled_diff_stripline(
    geometry: BroadsideCoupledDiffStripline,
    *,
    frequency_hz: float | None = None,
) -> DiffResult:
    """Broadside-coupled differential pair (stripline), Wadell §6.5.

    Models two strips stacked vertically inside a stripline cavity. Closed-form
    for the wide-strip regime: each trace acts like a stripline whose effective
    cavity is the half-distance to the corresponding ground plane. Mode
    impedances follow Wadell:
        Zodd  = (η0 / sqrt(εr)) · (Hb / (W + dW))
        Zeven = (η0 / sqrt(εr)) · ((H1 + Hb/2) / (W + dW))
    where Hb = H_between, dW is the Wadell finite-thickness correction.
    """
    W, T, H1, Hb, er = (
        geometry.W,
        geometry.T,
        geometry.H1,
        geometry.H_between,
        geometry.er,
    )

    # Wadell finite-thickness correction (same form as edge-coupled stripline)
    dW = (T / math.pi) * (1.0 + math.log((4.0 * (H1 + Hb)) / T)) if T > 0 else 0.0
    W_eff = W + dW

    z_odd = (ETA0 / math.sqrt(er)) * (Hb / W_eff)
    z_even = (ETA0 / math.sqrt(er)) * ((H1 + Hb / 2.0) / W_eff)

    eps_eff = er
    vp = C0 / math.sqrt(eps_eff)

    return DiffResult(
        z_odd=z_odd,
        z_even=z_even,
        z_diff=2.0 * z_odd,
        z_common=z_even / 2.0,
        eps_eff_odd=eps_eff,
        eps_eff_even=eps_eff,
        vp_odd=vp,
        vp_even=vp,
        method="wadell-broadside-coupled-diff-stripline",
        frequency_hz=frequency_hz,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dielectric_loss(eps_eff: float, tan_delta: float, freq_hz: float | None) -> float | None:
    """Generic dielectric loss in dB/inch, returns None when not enough info."""
    if not tan_delta or not freq_hz:
        return None
    alpha_neper_per_m = (math.pi * freq_hz / C0) * math.sqrt(eps_eff) * tan_delta
    return alpha_neper_per_m * 8.6858896 * INCH_M


__all__ = [
    "broadside_coupled_diff_stripline",
    "cpwg",
    "edge_coupled_diff_microstrip",
    "edge_coupled_diff_stripline",
    "stripline_asymmetric",
    "stripline_symmetric",
]
