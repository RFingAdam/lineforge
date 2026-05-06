"""Hammerstad-Jensen microstrip family.

Implements the closed-form impedance and effective permittivity formulas for
plain microstrip (Hammerstad & Jensen, 1980) and embedded (coated) microstrip
(Wheeler / IPC-2141A). Validity range: ``0.05 ≤ W/H ≤ 20``, ``εr ≤ 128``.

References
----------
- E. Hammerstad and Ø. Jensen, *Accurate Models for Microstrip Computer-Aided
  Design*, IEEE MTT-S Int. Microwave Symp. Digest, 1980.
- IPC-2141A, *Design Guide for High-Speed Controlled Impedance Circuit Boards*,
  Appendix A.
- B. Wadell, *Transmission Line Design Handbook*, Artech House 1991, §3.3.
"""

from __future__ import annotations

import math
import warnings

from atlc3.analytical._constants import C0, ETA0, INCH_M
from atlc3.geometry.types import EmbeddedMicrostrip, Microstrip
from atlc3.results import SolverWarning, TLineResult


def _check_microstrip_range(W_over_H: float, er: float) -> list[SolverWarning]:
    """Warn if outside Hammerstad-Jensen's published validity range."""
    out: list[SolverWarning] = []
    if W_over_H < 0.05 or W_over_H > 20.0:
        msg = (
            f"W/H = {W_over_H:.3g} is outside Hammerstad-Jensen validity (0.05–20); "
            "consider the bitmap kernel for higher accuracy"
        )
        warnings.warn(msg, stacklevel=3)
        out.append(SolverWarning(code="out_of_range", message=msg))
    if er > 128.0:
        msg = f"εr = {er:.3g} exceeds Hammerstad-Jensen validity (≤128)"
        warnings.warn(msg, stacklevel=3)
        out.append(SolverWarning(code="er_out_of_range", message=msg))
    return out


def _eps_eff_thin_strip(W: float, H: float, er: float) -> float:
    """Hammerstad-Jensen effective permittivity for a zero-thickness strip.

    From IPC-2141A eq. (4-10) / Wadell §3.3.1.
    """
    u = W / H
    a = (
        1.0
        + (1.0 / 49.0) * math.log((u**4 + (u / 52.0) ** 2) / (u**4 + 0.432))
        + (1.0 / 18.7) * math.log(1.0 + (u / 18.1) ** 3)
    )
    b = 0.564 * ((er - 0.9) / (er + 3.0)) ** 0.053
    return (er + 1.0) / 2.0 + ((er - 1.0) / 2.0) * (1.0 + 10.0 / u) ** (-a * b)


def _z0_thin_strip(W: float, H: float, eps_eff: float) -> float:
    """Hammerstad-Jensen Z0 for a zero-thickness strip.

    IPC-2141A eq. (4-11).
    """
    u = W / H
    f = 6.0 + (2.0 * math.pi - 6.0) * math.exp(-((30.666 / u) ** 0.7528))
    z0_air = (ETA0 / (2.0 * math.pi)) * math.log(f / u + math.sqrt(1.0 + (2.0 / u) ** 2))
    return z0_air / math.sqrt(eps_eff)


def _thickness_correction_w(W: float, T: float, H: float, er: float) -> float:
    """Wheeler's thickness correction: returns effective W to use in thin-strip formulas.

    From IPC-2141A §4.2.1.
    """
    if T <= 0:
        return W
    t_h = T / H
    if W / H <= 1.0 / (2.0 * math.pi):
        delta = (T / math.pi) * (1.0 + math.log(4.0 * math.pi * W / T))
    else:
        delta = (T / math.pi) * (1.0 + math.log(2.0 * H / T))
    # Reduce slightly to account for finite εr (Wadell §3.3.4)
    correction_factor = 1.0 - 0.5 * (t_h / (er + 1))
    return W + delta * correction_factor


def _conductor_loss_db_per_in(z0: float, W_eff: float, T: float, rho: float) -> float:
    """Approximate conductor loss using surface-resistance Wheeler model.

    Phase 1 estimate only — Phase 3 will replace with the full Faraday-based Rs.
    """
    if T <= 0 or W_eff <= 0:
        return 0.0
    # crude DC approximation; Phase 3 supersedes
    rs = rho / T  # Ω per square (DC)
    alpha_neper_per_m = rs / (2.0 * z0 * W_eff)
    return alpha_neper_per_m * 8.6858896 * INCH_M


def _dielectric_loss_db_per_in(
    eps_eff: float, er: float, tan_delta: float, freq_hz: float
) -> float:
    """Wheeler's dielectric loss formula (filled εr factor).

    Returns 0 if ``tan_delta == 0`` or ``freq_hz`` not given.
    """
    if tan_delta <= 0 or freq_hz <= 0:
        return 0.0
    # α_d = (π·f / c) · (εr·(εeff - 1)) / (sqrt(εeff)·(εr - 1)) · tanδ   [Np/m]
    alpha_neper_per_m = (
        (math.pi * freq_hz / C0)
        * (er * (eps_eff - 1.0))
        / (math.sqrt(eps_eff) * (er - 1.0))
        * tan_delta
    )
    return alpha_neper_per_m * 8.6858896 * INCH_M


def microstrip(
    geometry: Microstrip,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve a microstrip via Hammerstad-Jensen.

    Parameters
    ----------
    geometry
        :class:`~atlc3.geometry.types.Microstrip` instance (all dims in meters).
    frequency_hz
        Optional frequency for loss estimates. If ``None``, dielectric and
        conductor loss fields are left ``None``.

    Returns
    -------
    TLineResult
        Z0, εeff, vp, td/in, loss estimates.

    Notes
    -----
    Uses the thin-strip Hammerstad-Jensen formulas with Wheeler's thickness
    correction (W → W_eff). Conductor loss is a Phase 1 DC approximation; Phase 3
    supersedes with the full Faraday solver.
    """
    W, H, T, er = geometry.W, geometry.H, geometry.T, geometry.er

    issues = _check_microstrip_range(W / H, er)

    W_eff = _thickness_correction_w(W, T, H, er)
    eps_eff = _eps_eff_thin_strip(W_eff, H, er)
    z0 = _z0_thin_strip(W_eff, H, eps_eff)

    vp = C0 / math.sqrt(eps_eff)
    td_per_in = INCH_M / vp

    cond_loss = _conductor_loss_db_per_in(z0, W_eff, T, geometry.rho) if frequency_hz else None
    diel_loss = (
        _dielectric_loss_db_per_in(eps_eff, er, geometry.tan_delta, frequency_hz)
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
        method="hammerstad-jensen-microstrip",
        frequency_hz=frequency_hz,
        warnings=issues,
    )


def embedded_microstrip(
    geometry: EmbeddedMicrostrip,
    *,
    frequency_hz: float | None = None,
) -> TLineResult:
    """Solve an embedded (coated) microstrip via the IPC-2141A coated-microstrip model.

    Approach: compute εeff for the bare microstrip, compute εeff for the same strip
    with an infinite top dielectric (er2), then blend by the coating-thickness factor
    ``η`` per IPC-2141A §4.2.2. Effective εr drives the Z0 calculation through the
    same Hammerstad-Jensen formula with ``er → er_eff_blend``.
    """
    W, H, H2, T, er, er2 = (
        geometry.W,
        geometry.H,
        geometry.H2,
        geometry.T,
        geometry.er,
        geometry.er2,
    )

    issues = _check_microstrip_range(W / H, er)

    W_eff = _thickness_correction_w(W, T, H, er)

    # εeff for "bare" microstrip (er over an air half-space):
    eps_eff_bare = _eps_eff_thin_strip(W_eff, H, er)

    # εeff for "fully covered" microstrip (er and er2 stacked, infinite er2 above):
    # IPC-2141A approximation: blend toward (er + er2) / 2 using a coating-thickness
    # factor η = 1 − exp(−1.55·H2/H). When H2 → 0, η → 0 (bare). When H2 → ∞, η → 1.
    eta = 1.0 - math.exp(-1.55 * H2 / H)
    eps_eff_covered = eps_eff_bare + eta * (((er + er2) / 2.0) - (er + 1.0) / 2.0)

    # Z0 uses the blended εeff with the same thin-strip formula:
    z0 = _z0_thin_strip(W_eff, H, eps_eff_covered)

    vp = C0 / math.sqrt(eps_eff_covered)
    td_per_in = INCH_M / vp

    cond_loss = _conductor_loss_db_per_in(z0, W_eff, T, geometry.rho) if frequency_hz else None
    diel_loss = (
        _dielectric_loss_db_per_in(
            eps_eff_covered,
            (er + er2) / 2.0,
            (geometry.tan_delta + geometry.tan_delta_2) / 2.0,
            frequency_hz,
        )
        if frequency_hz
        else None
    )

    return TLineResult(
        z0=z0,
        eps_eff=eps_eff_covered,
        vp=vp,
        td_per_inch=td_per_in,
        L_per_m=z0 / vp,
        C_per_m=1.0 / (z0 * vp),
        conductor_loss_db_per_in=cond_loss,
        dielectric_loss_db_per_in=diel_loss,
        method="ipc2141-embedded-microstrip",
        frequency_hz=frequency_hz,
        warnings=issues,
    )


__all__ = ["embedded_microstrip", "microstrip"]
