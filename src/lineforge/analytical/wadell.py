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

from lineforge.analytical._constants import C0, EPS0, ETA0, INCH_M
from lineforge.geometry.types import (
    CPWG,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    StriplineAsymmetric,
    StriplineSymmetric,
)
from lineforge.results import DiffResult, SolverWarning, TLineResult

# ---------------------------------------------------------------------------
# Stripline
# ---------------------------------------------------------------------------


def wheeler_stripline_z0(W: float, T: float, B: float, er: float) -> float:
    """Wheeler (1978) symmetric stripline impedance with finite thickness.

    ``Z0 = 30/sqrt(er) ln{1 + (4/pi) (b-t)/W' [(8/pi)(b-t)/W'
    + sqrt(((8/pi)(b-t)/W')^2 + 6.27)]}``, with the thickness-corrected width
    ``W' = W + dW``,
    ``dW/(b-t) = x/(pi (1-x)) {1 - 0.5 ln[(x/(2-x))^2
    + (0.0796 x/(W/b + 1.1 x))^m]}``, ``m = 2/(1 + (2/3) x/(1-x))``,
    ``x = t/b``. Wheeler states 0.5 % accuracy for ``W'/(b-t) < 10``; it is
    within 0.3 % of the graded-mesh field solver over the PCB range.
    """
    b, t = B, T
    if t > 0:
        x = t / b
        m = 2.0 / (1.0 + (2.0 / 3.0) * x / (1.0 - x))
        dW = (
            (x / (math.pi * (1.0 - x)))
            * (1.0 - 0.5 * math.log((x / (2.0 - x)) ** 2 + (0.0796 * x / (W / b + 1.1 * x)) ** m))
            * (b - t)
        )
    else:
        dW = 0.0
    a = (4.0 / math.pi) * (b - t) / (W + dW)
    return float(
        (30.0 / math.sqrt(er)) * math.log(1.0 + a * (2.0 * a + math.sqrt((2.0 * a) ** 2 + 6.27)))
    )


def _stripline_z0_narrow(W: float, T: float, B: float, er: float) -> float:
    """IPC-2141A narrow-strip stripline (kept for reference; not used by the solvers).

    Z0 = (60/sqrt(er)) * ln(4 B / (0.67 pi (0.8 W + T))). Only valid for
    narrow strips; it reads 16.5 ohm instead of ~20 ohm for a 0.3 mm strip in
    a 0.24 mm cavity.
    """
    d = 0.8 * W + T
    return (60.0 / math.sqrt(er)) * math.log(4.0 * B / (0.67 * math.pi * d))


def _stripline_validity(W: float, T: float, B: float) -> list[SolverWarning]:
    out: list[SolverWarning] = []
    if B <= T:
        raise ValueError(
            f"stripline: plate separation B={B:.6g} m must exceed strip thickness T={T:.6g} m"
        )
    if T / B > 0.25:
        out.append(
            SolverWarning(
                code="out_of_range",
                message=(
                    f"T/B = {T / B:.3g} > 0.25 is outside the validated range of Wheeler's "
                    "thickness correction; use solve_full"
                ),
            )
        )
    a = W / (B - T)
    if a > 10.0:
        out.append(
            SolverWarning(
                code="out_of_range",
                message=(
                    f"W/(B-T) = {a:.3g} > 10 is outside Wheeler's stated 0.5 % range; "
                    "use solve_full"
                ),
            )
        )
    return out


def stripline_symmetric(
    geometry: StriplineSymmetric,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve a symmetric stripline with Wheeler's (1978) finite-thickness formula.

    Replaces the IPC-2141A narrow-strip formula, which was used for every
    width and is only valid for narrow strips: it read 16.5 ohm instead of
    ~20 ohm for W = 0.3 mm in a 0.24 mm cavity.
    """
    W, T, B, er = geometry.W, geometry.T, geometry.B, geometry.er
    issues = _stripline_validity(W, T, B)
    z0 = wheeler_stripline_z0(W, T, B, er)

    eps_eff = er  # stripline is fully embedded. No air dispersion
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
        method="wheeler-1978-stripline",
        model_accuracy="±0.5% (Wheeler 1978, W'/(B-T)<10, T/B<=0.25)",
        frequency_hz=frequency_hz,
        warnings=issues,
    )


def _offset_error_pct(ratio: float) -> float:
    """Typical overestimate of the parallel-combination model vs a field solve.

    From graded-mesh solves across W/h_near = 0.5-15 (largest at narrow W):
    <=1.5 % at h_far/h_near <= 2, ~3 % at 3, ~5 % at 5, ~9 % at 10.
    """
    if ratio <= 2.0:
        return 1.5
    return min(1.5 + 0.95 * (ratio - 2.0), 15.0)


def stripline_asymmetric(
    geometry: StriplineAsymmetric,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve an asymmetric (offset) stripline by the parallel-combination model.

    The strip at distance H1 from one plane and H2 from the other is split at
    its mid-plane into two symmetric striplines of plate spacing
    ``b_i = 2 H_i + T``, each solved with Wheeler's formula; their
    capacitances add, so ``1/Z0 = (1/Z_1 + 1/Z_2)/2`` (Cohn / Wadell 3.5.2).
    Within 1.5 % of a field solve while the larger dielectric is at most
    twice the smaller; the error grows with the offset and a
    ``validity_offset`` warning states the expected size.

    With ``er_above`` / ``er_below`` (or ``stack_above`` / ``stack_below``,
    series-reduced to those) each half keeps its own er, so
    ``eps_eff = (er_a / Z_1,air + er_b / Z_2,air) / (1/Z_1,air + 1/Z_2,air)``:
    each dielectric is weighted by its half's capacitance rather than by
    1/H alone.
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

    b1, b2 = 2.0 * H1 + T, 2.0 * H2 + T
    issues = _stripline_validity(W, T, b1)
    for w in _stripline_validity(W, T, b2):
        if all(w.message != x.message for x in issues):
            issues.append(w)
    z1 = wheeler_stripline_z0(W, T, b1, 1.0)
    z2 = wheeler_stripline_z0(W, T, b2, 1.0)
    y1, y2 = 1.0 / z1, 1.0 / z2
    z_air = 2.0 / (y1 + y2)
    q_above, q_below = y1 / (y1 + y2), y2 / (y1 + y2)
    er_eff = q_above * er_above + q_below * er_below
    z0 = z_air / math.sqrt(er_eff)

    ratio = max(H1, H2) / min(H1, H2)
    err = _offset_error_pct(ratio)
    accuracy = f"±{err:.2g}% (Wheeler 1978 halves in parallel; h_far/h_near={ratio:.2g})"
    if ratio > 2.0:
        issues.append(
            SolverWarning(
                code="validity_offset",
                message=(
                    f"strip offset h_far/h_near = {ratio:.3g} > 2: the parallel-combination "
                    f"model reads high by up to ~{err:.0f}% (most for narrow strips); "
                    "use solve_full for a field-solved value"
                ),
            )
        )

    vp = C0 / math.sqrt(er_eff)
    td_per_in = INCH_M / vp

    has_stack = geometry.stack_above is not None or geometry.stack_below is not None
    has_split = geometry.er_above is not None or geometry.er_below is not None
    if has_stack:
        method = "wheeler-parallel-stripline-asymmetric-multilayer-stack"
    elif has_split:
        method = "wheeler-parallel-stripline-asymmetric-split-er"
    else:
        method = "wheeler-parallel-stripline-asymmetric"

    diel = None
    if frequency_hz:
        alpha = (
            (math.pi * frequency_hz / C0)
            * (q_above * er_above * tan_above + q_below * er_below * tan_below)
            / math.sqrt(er_eff)
        )
        diel = alpha * 8.6858896 * INCH_M if alpha > 0 else None

    return TLineResult(
        z0=z0,
        eps_eff=er_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        dielectric_loss_db_per_in=diel,
        method=method,
        model_accuracy=accuracy,
        frequency_hz=frequency_hz,
        warnings=issues,
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


# Coplanar-increment fit (graded-mesh field solves, er 2.2 and 4.2, W 50-300 um,
# H 69-200 um, T 18-35 um, S 25-400 um): Z0 rms 0.9 %, worst 2.8 % (the worst
# cases are the Hammerstad-Jensen microstrip base itself at T/W = 0.7).
_CPWG_LOW, _CPWG_UP_B, _CPWG_UP_C = 0.99402, 1.83221, 0.52901
_CPWG_SIDE, _CPWG_SIDE_DECAY, _CPWG_UP_ER = 0.98981, 0.82377, -0.13764


def cpwg(
    geometry: CPWG,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve a grounded coplanar waveguide (CPWG / conductor-backed CPW).

    Capacitance model: the finite-thickness Hammerstad-Jensen microstrip
    (the ``S -> infinity`` limit) plus the extra capacitance the coplanar
    grounds add,

        C = C_ms + 2 eps0 [ a er dK_low + K_up(k) e^{-b (S/H)^c} (1 + g (er - 1))
                            + s (T/S) e^{-d S/H} ]

    where ``dK_low = K(k1)/K(k1') - K(k1inf)/K(k1inf')`` is the Ghione-Naldi /
    Wen conformal-mapping increment of the substrate region
    (``k1 = tanh(pi W/4H) / tanh(pi (W+2S)/4H)``), ``K_up(k) = K(k)/K(k')``
    with ``k = W/(W+2S)`` is the coplanar air term, and the last term is the
    side-wall capacitance of the strip thickness across the gaps. The vacuum
    capacitance uses the same expression with er = 1. Every increment is
    non-negative and shrinks as S grows, so Z0 rises monotonically to the
    microstrip value and never exceeds it.

    The previous pure Wen formula ignored the strip-to-ground fringing that
    a microstrip has, so it read *above* microstrip for wide gaps (61.7 ohm
    vs 52 ohm for W = 0.104 mm, S = 0.26 mm, H = 69 um).
    """
    from lineforge.analytical.hammerstad import hj_static

    W, S, H, T, er = geometry.W, geometry.S, geometry.H, geometry.T, geometry.er

    issues: list[SolverWarning] = []
    for name, val, lo, hi in (("W/H", W / H, 0.2, 5.0), ("S/H", S / H, 0.1, 8.0)):
        if not lo <= val <= hi:
            issues.append(
                SolverWarning(
                    code="out_of_range",
                    message=(
                        f"{name} = {val:.3g} is outside the fitted CPWG range ({lo}-{hi}); "
                        "use solve_full"
                    ),
                )
            )
    if er > 6.0 or T / H > 0.5:
        issues.append(
            SolverWarning(
                code="out_of_range",
                message=(
                    f"er = {er:.3g}, T/H = {T / H:.3g}: the CPWG coplanar-increment fit "
                    "covers er <= 6 and T/H <= 0.5; use solve_full"
                ),
            )
        )

    z_ms, eps_ms = hj_static(W, H, T, er)
    cv_ms = 1.0 / (C0 * z_ms * math.sqrt(eps_ms))
    c_ms = eps_ms * cv_ms

    k = W / (W + 2.0 * S)
    k1_inf = math.tanh(math.pi * W / (4.0 * H))
    k1 = k1_inf / math.tanh(math.pi * (W + 2.0 * S) / (4.0 * H))
    d_low = max(_kk(k1) - _kk(k1_inf), 0.0)
    x = S / H
    up = _kk(k) * math.exp(-_CPWG_UP_B * x**_CPWG_UP_C)
    side = _CPWG_SIDE * (T / S) * math.exp(-_CPWG_SIDE_DECAY * x) if T > 0 else 0.0
    up_er = max(1.0 + _CPWG_UP_ER * (er - 1.0), 0.0)

    cv = cv_ms + 2.0 * EPS0 * (_CPWG_LOW * d_low + up + side)
    c = c_ms + 2.0 * EPS0 * (_CPWG_LOW * er * d_low + up * up_er + side)
    z0 = 1.0 / (C0 * math.sqrt(c * cv))
    eps_eff = c / cv

    vp = C0 / math.sqrt(eps_eff)
    td_per_in = INCH_M / vp
    q = (eps_eff - 1.0) / (er - 1.0) if er > 1.0 else 0.0
    diel = None
    if frequency_hz and geometry.tan_delta:
        alpha = (math.pi * frequency_hz / C0) * q * er * geometry.tan_delta / math.sqrt(eps_eff)
        diel = alpha * 8.6858896 * INCH_M

    return TLineResult(
        z0=z0,
        eps_eff=eps_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        dielectric_loss_db_per_in=diel,
        method="hj-microstrip+coplanar-increment-cpwg",
        model_accuracy="±3% vs field solve (er<=6, 0.2<=W/H<=5, 0.1<=S/H<=8, T/H<=0.5)",
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
    """Edge-coupled microstrip pair: Kirschning-Jansen, see
    :func:`lineforge.analytical.hammerstad.edge_coupled_diff_microstrip`.

    The previous IPC-2141A exponential coupling factor scaled one single-line
    Z0 and reported the single line's eps_eff for both modes.
    """
    from lineforge.analytical.hammerstad import edge_coupled_diff_microstrip as _kj

    return _kj(geometry, frequency_hz=frequency_hz)


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
