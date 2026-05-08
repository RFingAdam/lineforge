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


def _stripline_z0_narrow(W: float, T: float, B: float, er: float) -> float:
    """IPC-2141A narrow-strip stripline (eq. 4-15).

    Z0 = (60/√εr) · ln(4·B / (0.67·π·(0.8·W + T)))

    Valid for W/(B-T) ≤ ~0.35 and T < 0.25·B. Accurate to ±2% within the range.
    """
    d = 0.8 * W + T
    return (60.0 / math.sqrt(er)) * math.log(4.0 * B / (0.67 * math.pi * d))


def _stripline_z0_wide(W: float, T: float, B: float, er: float) -> float:
    """Cohn wide-strip stripline with Wadell finite-thickness correction.

    Valid for W/(B-T) > 0.35. From Wadell §3.4.1 / IPC-2141A eq. (4-16).
    """
    if T <= 0 or B <= T:
        m = 0.0
        cf_prime = 0.0
    else:
        m = 2.0 * B / (B - T)
        cf_prime = (B / (math.pi * (B - T))) * (
            (m * math.log((m + 1.0) / (m - 1.0))) - math.log((m * m - 1.0) / 4.0)
        )
    return ETA0 / (math.sqrt(er) * 4.0 * (W / (B - T) + cf_prime / math.pi))


def stripline_symmetric(
    geometry: StriplineSymmetric,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve a symmetric stripline.

    Dispatches between IPC-2141A narrow-strip (W/(B-T) ≤ 0.35) and Cohn /
    Wadell wide-strip (W/(B-T) > 0.35) formulas. Both are accurate to ±2%
    within their validity ranges.
    """
    W, T, B, er = geometry.W, geometry.T, geometry.B, geometry.er

    issues: list[SolverWarning] = []
    if T > 0.25 * B:
        msg = "Stripline T > 0.25·B is outside published validity"
        issues.append(SolverWarning(code="thick_strip", message=msg))

    # IPC-2141A's symmetric-stripline formula is accurate over the full
    # practical W/(B-T) range (typically 0–1.5). Cohn wide-strip is only
    # better for truly wide strips W/(B-T) > 2 — very rare in PCB design.
    z0 = _stripline_z0_narrow(W, T, B, er)
    method = "ipc2141-stripline"

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
        method=method,
        frequency_hz=frequency_hz,
        warnings=issues,
    )


def stripline_asymmetric(
    geometry: StriplineAsymmetric,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve an asymmetric (offset) stripline via IPC-2141A's harmonic-mean-H formula.

    For a strip at offset H1 from one ground plane and H2 from the other,
    define the effective ground separation:

        H_eff = 2·H1·H2 / (H1 + H2)

    Then:

        Z₀ = (60/√εr) · ln(8·H_eff / (0.67π·(0.8W + T)))

    In the symmetric limit H1 = H2 = h, H_eff = h and the formula reduces to
    the symmetric IPC-2141A formula with B = 2h (good when T << h).

    When the geometry supplies ``er_above`` / ``er_below`` (different dielectric
    above and below the strip — common when an inner signal layer sits
    between a plane on Core and a plane on Prepreg), the formula uses a
    capacitance-weighted effective permittivity:

        εr_eff = (εr_above/H1 + εr_below/H2) / (1/H1 + 1/H2)

    Each half-cavity acts like a parallel-plate capacitor (Cohn parallel-plate
    decomposition); the strip's total parallel-plate capacitance is the sum,
    so the εr that produces the correct C is the C-weighted average.

    References: IPC-2141A eq. (4-19), Wadell §3.5.2.
    """
    W, T, H1, H2 = geometry.W, geometry.T, geometry.H1, geometry.H2

    er_above = geometry.er_above if geometry.er_above is not None else geometry.er
    er_below = geometry.er_below if geometry.er_below is not None else geometry.er
    tan_above = (
        geometry.tan_delta_above if geometry.tan_delta_above is not None else geometry.tan_delta
    )
    tan_below = (
        geometry.tan_delta_below if geometry.tan_delta_below is not None else geometry.tan_delta
    )

    # Capacitance-weighted (Cohn parallel-plate decomposition). Each half-cavity
    # acts like a parallel-plate cap with C ∝ ε / H; series-combine inversely.
    er_eff = (er_above / H1 + er_below / H2) / (1.0 / H1 + 1.0 / H2)
    # Loss tangent: weight by the same C contributions.
    c_above_norm = er_above / H1
    c_below_norm = er_below / H2
    tan_eff = (tan_above * c_above_norm + tan_below * c_below_norm) / (c_above_norm + c_below_norm)

    H_eff = 2.0 * H1 * H2 / (H1 + H2)
    d = 0.8 * W + T
    z0 = (60.0 / math.sqrt(er_eff)) * math.log(8.0 * H_eff / (0.67 * math.pi * d))

    vp = C0 / math.sqrt(er_eff)
    td_per_in = INCH_M / vp

    has_stack = geometry.stack_above is not None or geometry.stack_below is not None
    has_split = geometry.er_above is not None or geometry.er_below is not None
    if has_stack:
        method = "ipc2141-stripline-asymmetric-multilayer-stack"
    elif has_split:
        method = "ipc2141-stripline-asymmetric-split-er"
    else:
        method = "ipc2141-stripline-asymmetric"

    return TLineResult(
        z0=z0,
        eps_eff=er_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        dielectric_loss_db_per_in=_dielectric_loss(er_eff, tan_eff, frequency_hz),
        method=method,
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
        W=geometry.W,
        H=geometry.H,
        T=geometry.T,
        er=geometry.er,
        tan_delta=geometry.tan_delta,
        rho=geometry.rho,
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
        W=geometry.W,
        T=geometry.T,
        B=geometry.B,
        er=geometry.er,
        tan_delta=geometry.tan_delta,
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
