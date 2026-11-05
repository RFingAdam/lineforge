"""Hammerstad-Jensen microstrip family.

Implements the closed-form impedance and effective permittivity of plain
microstrip (Hammerstad & Jensen, 1980, *with* their finite-thickness
correction), an optional conformal solder-mask coating, embedded (buried)
microstrip, and edge-coupled microstrip pairs (Kirschning & Jansen, 1984).

Losses:

* Conductor loss uses the Pucel-Masse-Hartwig (Wheeler incremental
  inductance) closed form with the skin-effect surface resistance
  ``Rs = sqrt(pi f mu0 rho)``, optionally scaled by a surface-roughness factor
  (Hammerstad, Groisse or Huray; see :mod:`lineforge.solvers.roughness`).
* Dielectric loss uses filling factors: with
  ``eps_eff = 1 + sum_i q_i (er_i - 1)``,
  ``alpha_d = (pi f / c) / sqrt(eps_eff) * sum_i q_i er_i tan_i``, which
  reduces to the textbook ``27.3 er (eps_eff - 1) tan / (sqrt(eps_eff)
  (er - 1) lambda0)`` for one dielectric and to ``sqrt(er)`` for stripline.

Validity: Hammerstad-Jensen 0.01 <= W/H <= 100 (static error < 0.2 % for the
zero-thickness formula, ~1 % with the thickness correction for T/H <= 0.5),
Kirschning-Jansen 0.1 <= W/H <= 10, 0.1 <= S/H <= 10, er <= 18 (~1 %).
The solder-mask model is fitted to graded-mesh field solves (see
``tests/test_analytical/test_closed_form_regressions.py``) and reproduces them to
~1 % in Z0 for mask thicknesses up to ~2.5 H.

References
----------
- E. Hammerstad and Ø. Jensen, *Accurate Models for Microstrip Computer-Aided
  Design*, IEEE MTT-S Int. Microwave Symp. Digest, 1980.
- M. Kirschning and R. H. Jansen, *Accurate Wide-Range Design Equations for
  the Frequency-Dependent Characteristic of Parallel Coupled Microstrip
  Lines*, IEEE Trans. MTT-32, 1984.
- R. A. Pucel, D. J. Massé and C. P. Hartwig, *Losses in Microstrip*, IEEE
  Trans. MTT-16, 1968 (and the errata); K. C. Gupta et al., *Microstrip Lines
  and Slotlines*, 2nd ed., §2.4.
"""

from __future__ import annotations

import math
import warnings

from lineforge.analytical._constants import C0, EPS0, ETA0, INCH_M, MU0
from lineforge.geometry.types import EdgeCoupledDiffMicrostrip, EmbeddedMicrostrip, Microstrip
from lineforge.materials.database import RoughnessSpec
from lineforge.results import DiffResult, SolverWarning, TLineResult

NP_TO_DB = 8.685889638


def _validity(code: str, msg: str) -> SolverWarning:
    warnings.warn(msg, stacklevel=4)
    return SolverWarning(code=code, message=msg)


def _check_microstrip_range(W_over_H: float, er: float) -> list[SolverWarning]:
    """Warn if outside Hammerstad-Jensen's published validity range."""
    out: list[SolverWarning] = []
    if W_over_H < 0.01 or W_over_H > 100.0:
        out.append(
            _validity(
                "out_of_range",
                f"W/H = {W_over_H:.3g} is outside Hammerstad-Jensen validity (0.01-100); "
                "use solve_full for a field-solved result",
            )
        )
    if er > 128.0:
        out.append(
            _validity(
                "er_out_of_range", f"er = {er:.3g} exceeds Hammerstad-Jensen validity (<=128)"
            )
        )
    return out


# ---------------------------------------------------------------------------
# Hammerstad-Jensen building blocks
# ---------------------------------------------------------------------------


def _z01(u: float) -> float:
    """Air-filled zero-thickness microstrip impedance (HJ 1980, eq. 2)."""
    f = 6.0 + (2.0 * math.pi - 6.0) * math.exp(-((30.666 / u) ** 0.7528))
    return float((ETA0 / (2.0 * math.pi)) * math.log(f / u + math.sqrt(1.0 + (2.0 / u) ** 2)))


def _eff0(u: float, er: float) -> float:
    """Zero-thickness effective permittivity (HJ 1980, eqs. 3-5)."""
    a = (
        1.0
        + (1.0 / 49.0) * math.log((u**4 + (u / 52.0) ** 2) / (u**4 + 0.432))
        + (1.0 / 18.7) * math.log(1.0 + (u / 18.1) ** 3)
    )
    b = 0.564 * ((er - 0.9) / (er + 3.0)) ** 0.053
    return float((er + 1.0) / 2.0 + ((er - 1.0) / 2.0) * (1.0 + 10.0 / u) ** (-a * b))


def _eps_eff_thin_strip(W: float, H: float, er: float) -> float:
    """Hammerstad-Jensen effective permittivity for a zero-thickness strip."""
    return _eff0(W / H, er)


def _z0_thin_strip(W: float, H: float, eps_eff: float) -> float:
    """Hammerstad-Jensen Z0 for a zero-thickness strip."""
    return _z01(W / H) / math.sqrt(eps_eff)


def _hj_thickness(u: float, tn: float, er: float) -> tuple[float, float]:
    """HJ 1980 thickness corrections: (u1, ur) for the air and dielectric cases."""
    if tn <= 0:
        return u, u
    du1 = (tn / math.pi) * math.log(
        1.0 + 4.0 * math.e / (tn * (1.0 / math.tanh(math.sqrt(6.517 * u))) ** 2)
    )
    dur = 0.5 * (1.0 + 1.0 / math.cosh(math.sqrt(er - 1.0))) * du1
    return u + du1, u + dur


def hj_static(W: float, H: float, T: float, er: float) -> tuple[float, float]:
    """Static (Z0, eps_eff) of a microstrip of finite thickness (HJ 1980).

    ``Z0 = Z01(ur) / sqrt(eff(ur))`` and
    ``eps_eff = eff(ur) * (Z01(u1) / Z01(ur))^2``: the thickness correction
    lowers eps_eff (more of the field of a thick strip is in air), which the
    earlier single ``W -> W_eff`` substitution got backwards.
    """
    u = W / H
    u1, ur = _hj_thickness(u, T / H, er)
    eff_r = _eff0(ur, er)
    z0 = _z01(ur) / math.sqrt(eff_r)
    eps_eff = eff_r * (_z01(u1) / _z01(ur)) ** 2
    return z0, eps_eff


def _thickness_correction_w(W: float, T: float, H: float, er: float) -> float:
    """Effective width ``u_r * H`` of the HJ 1980 thickness correction."""
    return _hj_thickness(W / H, T / H, er)[1] * H


# ---------------------------------------------------------------------------
# Solder mask / coating
# ---------------------------------------------------------------------------

# Coating fill-fraction model, fitted to graded-mesh field solves (er = 4.2
# substrate, er_c = 3.5 and 4.2 coatings, W/H 0.7-3, T/H 0.13-0.5, c 5-160 um,
# S/H 0.7-3): Z0 within ~1 % of the field solve.
_MASK_A, _MASK_P, _MASK_ALPHA, _MASK_BETA = 1.5378, 0.7597, 0.3770, 0.1678
_MASK_A_ODD, _MASK_P_ODD, _MASK_K_ODD = 1.3794, 0.9099, 1.4574


def _mask_length(W: float, H: float, T: float) -> float:
    return float(W**_MASK_ALPHA * H ** (1.0 - _MASK_ALPHA) * (1.0 + _MASK_BETA * T / H))


def coating_fill(c: float, W: float, H: float, T: float, S: float | None = None) -> float:
    """Fraction ``F`` of the air-region field that a coating of thickness ``c`` captures.

    ``S`` selects the odd-mode form of a coupled pair (the gap field hugs the
    surface, so a thin coat captures more of it).
    """
    if c <= 0:
        return 0.0
    L = _mask_length(W, H, T)
    if S is None:
        return 1.0 - math.exp(-_MASK_A * (c / L) ** _MASK_P)
    L_odd = 1.0 / (1.0 / L + 1.0 / (_MASK_K_ODD * S))
    return 1.0 - math.exp(-_MASK_A_ODD * (c / L_odd) ** _MASK_P_ODD)


def _apply_coating(
    eps_eff: float, er: float, er_c: float, fill: float
) -> tuple[float, float, float]:
    """Return (eps_eff_coated, q_substrate, q_coating).

    Filling-factor model: the bare line has ``eps_eff = 1 + q (er - 1)``; the
    coating takes over a fraction ``fill`` of the remaining air share, so
    ``eps_eff_c = 1 + q (er - 1) + (1 - q) fill (er_c - 1)``.
    """
    q = (eps_eff - 1.0) / (er - 1.0) if er > 1.0 else 1.0
    q = min(max(q, 0.0), 1.0)
    qc = (1.0 - q) * fill
    return 1.0 + q * (er - 1.0) + qc * (er_c - 1.0), q, qc


# ---------------------------------------------------------------------------
# Losses
# ---------------------------------------------------------------------------


def surface_resistance(rho: float, frequency_hz: float) -> float:
    """Skin-effect surface resistance ``sqrt(pi f mu0 rho)`` [ohm/sq]."""
    return math.sqrt(math.pi * frequency_hz * MU0 * rho)


def skin_depth(rho: float, frequency_hz: float) -> float:
    """Skin depth ``sqrt(rho / (pi f mu0))`` [m]."""
    return math.sqrt(rho / (math.pi * frequency_hz * MU0))


def _roughness(roughness: RoughnessSpec | None, delta: float) -> float:
    if roughness is None:
        return 1.0
    from lineforge.solvers.roughness import roughness_factor

    return float(roughness_factor(roughness, delta))


def pucel_r_per_m(W: float, H: float, T: float, rs: float) -> float:
    """Series resistance [ohm/m] of a microstrip (strip + ground) from Pucel.

    ``R = 2 Z0 alpha_c``; Pucel's alpha_c is proportional to 1/Z0 so the
    result depends on geometry and Rs only.
    """
    u = W / H
    t = max(T, 1e-3 * W)
    if u <= 1.0 / (2.0 * math.pi):
        we = W + (t / math.pi) * (1.0 + math.log(4.0 * math.pi * W / t))
        q = 1.0 + H / we + (H / (math.pi * we)) * (math.log(4.0 * math.pi * W / t) + t / W)
    else:
        we = W + (t / math.pi) * (1.0 + math.log(2.0 * H / t))
        q = 1.0 + H / we + (H / (math.pi * we)) * (math.log(2.0 * H / t) - t / H)
    if u <= 2.0:
        f = (1.0 / (2.0 * math.pi)) * (1.0 - (we / (4.0 * H)) ** 2) * q
    else:
        x = we / (2.0 * H) + 0.94
        num = we / H + (we / (math.pi * H)) / x
        den = (we / H + (2.0 / math.pi) * math.log(2.0 * math.pi * math.e * x)) ** 2
        f = num / den * q
    return 2.0 * rs * f / H


def _conductor_loss_db_per_in(
    z0: float,
    W: float,
    H: float,
    T: float,
    rho: float,
    frequency_hz: float,
    roughness: RoughnessSpec | None = None,
) -> float:
    """Skin-effect conductor loss [dB/in] (Pucel, with optional roughness).

    Below the frequency where the skin depth is comparable to the strip
    thickness the DC resistance of the strip dominates; the two are combined
    as ``sqrt(R_dc^2 + R_ac^2)``.
    """
    if frequency_hz <= 0:
        return 0.0
    rs = surface_resistance(rho, frequency_hz)
    rs *= _roughness(roughness, skin_depth(rho, frequency_hz))
    r_ac = pucel_r_per_m(W, H, T, rs)
    r_dc = rho / (W * T) if T > 0 else 0.0
    r = math.hypot(r_dc, r_ac)
    return r / (2.0 * z0) * NP_TO_DB * INCH_M


def _dielectric_loss_filled(
    eps_eff: float, parts: list[tuple[float, float, float]], freq_hz: float
) -> float:
    """Dielectric loss [dB/in] from filling factors ``[(q_i, er_i, tan_i), ...]``."""
    if freq_hz <= 0:
        return 0.0
    s = sum(q * er * tan for q, er, tan in parts)
    alpha = (math.pi * freq_hz / C0) * s / math.sqrt(eps_eff)
    return alpha * NP_TO_DB * INCH_M


def _dielectric_loss_db_per_in(
    eps_eff: float, er: float, tan_delta: float, freq_hz: float
) -> float:
    """Single-dielectric microstrip loss: q = (eps_eff - 1)/(er - 1)."""
    if tan_delta <= 0 or freq_hz <= 0:
        return 0.0
    q = (eps_eff - 1.0) / (er - 1.0) if er > 1.0 else 0.0
    return _dielectric_loss_filled(eps_eff, [(q, er, tan_delta)], freq_hz)


# ---------------------------------------------------------------------------
# Public solvers
# ---------------------------------------------------------------------------


def microstrip(
    geometry: Microstrip,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve a microstrip via Hammerstad-Jensen (1980), optionally solder-mask coated.

    Parameters
    ----------
    geometry
        :class:`~lineforge.geometry.types.Microstrip` instance (all dims in meters).
    frequency_hz
        Optional frequency for loss estimates. If ``None``, dielectric and
        conductor loss fields are left ``None``.
    """
    W, H, T, er = geometry.W, geometry.H, geometry.T, geometry.er

    issues = _check_microstrip_range(W / H, er)
    if T / H > 0.5:
        issues.append(
            _validity(
                "out_of_range",
                f"T/H = {T / H:.3g} > 0.5: the Hammerstad-Jensen thickness correction "
                "is not validated this thick; use solve_full",
            )
        )

    z0_bare, eps_bare = hj_static(W, H, T, er)
    z_air = z0_bare * math.sqrt(eps_bare)
    parts = [((eps_bare - 1.0) / (er - 1.0) if er > 1.0 else 0.0, er, geometry.tan_delta)]
    eps_eff = eps_bare
    method = "hammerstad-jensen-1980-microstrip"
    accuracy = "±1% (HJ 1980 with thickness correction, 0.01<=W/H<=100, T/H<=0.5)"
    c = geometry.mask_thickness
    if c:
        fill = coating_fill(c, W, H, T)
        eps_eff, q, qc = _apply_coating(eps_bare, er, geometry.mask_er, fill)
        parts = [(q, er, geometry.tan_delta), (qc, geometry.mask_er, geometry.mask_tan_delta)]
        method += "+solder-mask"
        accuracy = "±1.5% (HJ 1980 + field-fitted solder-mask fill model)"
        if c > 2.5 * H:
            issues.append(
                _validity(
                    "out_of_range",
                    f"mask_thickness = {c * 1e6:.3g} um > 2.5 H is outside the "
                    "fitted solder-mask range",
                )
            )
    z0 = z_air / math.sqrt(eps_eff)

    vp = C0 / math.sqrt(eps_eff)
    td_per_in = INCH_M / vp

    cond_loss = (
        _conductor_loss_db_per_in(z0, W, H, T, geometry.rho, frequency_hz, geometry.roughness)
        if frequency_hz
        else None
    )
    diel_loss = _dielectric_loss_filled(eps_eff, parts, frequency_hz) if frequency_hz else None

    return TLineResult(
        z0=z0,
        eps_eff=eps_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        conductor_loss_db_per_in=cond_loss,
        dielectric_loss_db_per_in=diel_loss,
        method=method,
        model_accuracy=accuracy,
        frequency_hz=frequency_hz,
        warnings=issues,
    )


def embedded_microstrip(
    geometry: EmbeddedMicrostrip,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve an embedded (buried) microstrip.

    The strip sits on the substrate (``H``, ``er``) and is buried in a cover
    dielectric (``er2``) that fills the strip's own layer and extends ``H2``
    above its top face. The cover is treated with the same filling-factor
    model as a solder mask, with a coating thickness of ``T + H2`` over the
    substrate surface. In the thick-cover, ``er2 == er`` limit eps_eff -> er.

    The previous IPC-2141A blend averaged ``er``/``er2`` and the two loss
    tangents arithmetically and could exceed er (eps_eff 4.76 for er = 4.2);
    its dielectric loss came out *below* bare microstrip's at the same Df.
    """
    W, H, H2, T, er, er2 = (
        geometry.W,
        geometry.H,
        geometry.H2,
        geometry.T,
        geometry.er,
        geometry.er2,
    )

    tan2 = geometry.tan_delta if geometry.tan_delta_2 is None else geometry.tan_delta_2
    issues = _check_microstrip_range(W / H, er)

    z0_bare, eps_bare = hj_static(W, H, T, er)
    z_air = z0_bare * math.sqrt(eps_bare)
    fill = coating_fill(T + H2, W, H, T)
    eps_eff, q, qc = _apply_coating(eps_bare, er, er2, fill)
    z0 = z_air / math.sqrt(eps_eff)

    vp = C0 / math.sqrt(eps_eff)
    td_per_in = INCH_M / vp

    cond_loss = (
        _conductor_loss_db_per_in(z0, W, H, T, geometry.rho, frequency_hz, geometry.roughness)
        if frequency_hz
        else None
    )
    diel_loss = (
        _dielectric_loss_filled(
            eps_eff,
            [(q, er, geometry.tan_delta), (qc, er2, tan2)],
            frequency_hz,
        )
        if frequency_hz
        else None
    )

    return TLineResult(
        z0=z0,
        eps_eff=eps_eff,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        conductor_loss_db_per_in=cond_loss,
        dielectric_loss_db_per_in=diel_loss,
        method="hammerstad-jensen-1980+cover-fill-embedded-microstrip",
        model_accuracy="±2% (HJ 1980 + field-fitted cover fill model)",
        frequency_hz=frequency_hz,
        warnings=issues,
    )


# ---------------------------------------------------------------------------
# Coupled microstrip (Kirschning-Jansen)
# ---------------------------------------------------------------------------


def _kj_even_eff(u: float, g: float, er: float) -> float:
    v = u * (20.0 + g * g) / (10.0 + g * g) + g * math.exp(-g)
    a_e = (
        1.0
        + math.log((v**4 + (v / 52.0) ** 2) / (v**4 + 0.432)) / 49.0
        + math.log(1.0 + (v / 18.1) ** 3) / 18.7
    )
    b_e = 0.564 * ((er - 0.9) / (er + 3.0)) ** 0.053
    return float((er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (1.0 + 10.0 / v) ** (-a_e * b_e))


def _kj_odd_eff(u: float, g: float, er: float, eff_single: float) -> float:
    a_o = 0.7287 * (eff_single - (er + 1.0) / 2.0) * (1.0 - math.exp(-0.179 * u))
    b_o = 0.747 * er / (0.15 + er)
    c_o = b_o - (b_o - 0.207) * math.exp(-0.414 * u)
    d_o = 0.593 + 0.694 * math.exp(-0.562 * u)
    return float(((er + 1.0) / 2.0 + a_o - eff_single) * math.exp(-c_o * g**d_o) + eff_single)


def _kj_q(u: float, g: float) -> tuple[float, float]:
    """Kirschning-Jansen Q4 (even) and Q10 (odd) impedance coefficients."""
    q1 = 0.8695 * u**0.194
    q2 = 1.0 + 0.7519 * g + 0.189 * g**2.31
    q3 = (
        0.1975
        + (16.6 + (8.4 / g) ** 6) ** (-0.387)
        + math.log(g**10 / (1.0 + (g / 3.4) ** 10)) / 241.0
    )
    q4 = (2.0 * q1 / q2) / (math.exp(-g) * u**q3 + (2.0 - math.exp(-g)) * u ** (-q3))
    q5 = 1.794 + 1.14 * math.log(1.0 + 0.638 / (g + 0.517 * g**2.43))
    q6 = (
        0.2305
        + math.log(g**10 / (1.0 + (g / 5.8) ** 10)) / 281.3
        + math.log(1.0 + 0.598 * g**1.154) / 5.1
    )
    q7 = (10.0 + 190.0 * g * g) / (1.0 + 82.3 * g**3)
    q8 = math.exp(-6.5 - 0.95 * math.log(g) - (g / 0.15) ** 5)
    q9 = math.log(q7) * (q8 + 1.0 / 16.5)
    q10 = q4 - (q5 / q2) * math.exp(q6 * math.log(u) / u**q9)
    return q4, q10


def _kj_zero_thickness(u: float, g: float, er: float) -> tuple[float, float, float, float]:
    """Zero-thickness KJ static (Z_even, Z_odd, eps_even, eps_odd), lengths normalised to H."""
    eff1 = _eff0(u, er)
    z1 = _z01(u) / math.sqrt(eff1)
    eps_e = _kj_even_eff(u, g, er)
    eps_o = _kj_odd_eff(u, g, er, eff1)
    q4, q10 = _kj_q(u, g)
    z_e = z1 * math.sqrt(eff1 / eps_e) / (1.0 - z1 / ETA0 * math.sqrt(eff1) * q4)
    z_o = z1 * math.sqrt(eff1 / eps_o) / (1.0 - z1 / ETA0 * math.sqrt(eff1) * q10)
    return z_e, z_o, eps_e, eps_o


# Coupled-line thickness corrections, fitted to graded-mesh field solves of
# T/H = 0.25-0.5 pairs (odd and even Z within ~1.5 %):
_KJ_EVEN_DW_SCALE = 0.6  # even mode: the inner edges' fringing is suppressed
_KJ_ODD_SIDEWALL = 0.5  # odd mode: facing side walls add k * 2 eps0 T / S per line


def kirschning_jansen(
    W: float, S: float, H: float, T: float, er: float
) -> tuple[float, float, float, float]:
    """Static (Z_even, Z_odd, eps_even, eps_odd) of an edge-coupled microstrip pair.

    Zero-thickness Kirschning-Jansen, with finite thickness applied per mode
    the way Hammerstad-Jensen 1980 applies it to a single line: the air and
    dielectric widths ``u1``/``ur`` give ``Z = Z_air(ur)/sqrt(eps(ur))`` and
    ``eps = eps(ur) (Z_air(u1)/Z_air(ur))^2``. The even mode uses a reduced
    width increment; the odd mode adds the air capacitance between the
    facing side walls.
    """
    u, g = W / H, S / H
    u1, ur = _hj_thickness(u, T / H, er)
    out: list[tuple[float, float]] = []
    for mode in (0, 1):  # even, odd
        scale = _KJ_EVEN_DW_SCALE if mode == 0 else 1.0
        m1 = u + (u1 - u) * scale
        mr = u + (ur - u) * scale
        za1 = _kj_zero_thickness(m1, g, 1.0)[mode]
        zar = _kj_zero_thickness(mr, g, 1.0)[mode]
        rr = _kj_zero_thickness(mr, g, er)
        eps = rr[2 + mode] * (za1 / zar) ** 2
        cv = 1.0 / (C0 * za1)
        c = eps * cv
        if mode == 1 and T > 0:
            dc = _KJ_ODD_SIDEWALL * 2.0 * EPS0 * T / S
            cv += dc
            c += dc
        out.append((1.0 / (C0 * math.sqrt(c * cv)), c / cv))
    (z_e, eps_e), (z_o, eps_o) = out
    return z_e, z_o, eps_e, eps_o


def edge_coupled_diff_microstrip(
    geometry: EdgeCoupledDiffMicrostrip,
    *,
    frequency_hz: float | None = None,
) -> DiffResult:
    """Edge-coupled microstrip pair via Kirschning-Jansen (static), optional solder mask.

    Even and odd modes get separate effective permittivities: the odd mode
    keeps more of its field in the air above the gap, so ``eps_eff_odd <
    eps_eff_even``. A solder mask raises both, the odd mode more.
    """
    W, S, H, T, er = geometry.W, geometry.S, geometry.H, geometry.T, geometry.er
    issues: list[SolverWarning] = []
    u, g = W / H, S / H
    if not (0.1 <= u <= 10.0):
        issues.append(
            _validity(
                "out_of_range",
                f"W/H = {u:.3g} is outside Kirschning-Jansen validity (0.1-10); use solve_full",
            )
        )
    if not (0.1 <= g <= 10.0):
        issues.append(
            _validity(
                "out_of_range",
                f"S/H = {g:.3g} is outside Kirschning-Jansen validity (0.1-10); use solve_full",
            )
        )
    if er > 18.0:
        issues.append(
            _validity("er_out_of_range", f"er = {er:.3g} exceeds Kirschning-Jansen validity (<=18)")
        )

    z_e, z_o, eps_e, eps_o = kirschning_jansen(W, S, H, T, er)
    method = "kirschning-jansen-coupled-microstrip"
    accuracy = "±2% (Kirschning-Jansen static, 0.1<=W/H,S/H<=10)"
    c = geometry.mask_thickness
    if c:
        ze_air = z_e * math.sqrt(eps_e)
        zo_air = z_o * math.sqrt(eps_o)
        eps_e, _, _ = _apply_coating(eps_e, er, geometry.mask_er, coating_fill(c, W, H, T))
        eps_o, _, _ = _apply_coating(eps_o, er, geometry.mask_er, coating_fill(c, W, H, T, S=S))
        z_e = ze_air / math.sqrt(eps_e)
        z_o = zo_air / math.sqrt(eps_o)
        method += "+solder-mask"
        accuracy = "±2.5% (Kirschning-Jansen + field-fitted solder-mask fill model)"

    return DiffResult(
        z_odd=z_o,
        z_even=z_e,
        z_diff=2.0 * z_o,
        z_common=z_e / 2.0,
        eps_eff_odd=eps_o,
        eps_eff_even=eps_e,
        vp_odd=C0 / math.sqrt(eps_o),
        vp_even=C0 / math.sqrt(eps_e),
        method=method,
        model_accuracy=accuracy,
        frequency_hz=frequency_hz,
        warnings=issues,
    )


__all__ = [
    "edge_coupled_diff_microstrip",
    "embedded_microstrip",
    "hj_static",
    "kirschning_jansen",
    "microstrip",
    "pucel_r_per_m",
]
