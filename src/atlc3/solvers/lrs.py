"""High-level L/Rs and full-RLGC orchestrator.

Combines:
    - Optional skin-depth restriction (Phase 3.1)
    - Faraday solve for L and R (Phase 3.2-3.5)
    - C/Gp Laplace solve (Phase 2)

into a single full-frequency-resolved characterization.
"""

from __future__ import annotations

import warnings

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from atlc3.cache import cached
from atlc3.geometry.usermap import Usermap
from atlc3.results import SolverWarning
from atlc3.solvers.cgp import solve_cgp
from atlc3.solvers.faraday import FaradayResult
from atlc3.solvers.faraday import solve_lrs as _solve_lrs_inner
from atlc3.solvers.skin_depth import mask_skin_depth


class RLGCResult(BaseModel):
    """Full per-unit-length RLGC characterization at one frequency."""

    model_config = ConfigDict(extra="forbid")

    frequency_hz: float = Field(..., gt=0)
    L_per_m: float = Field(..., gt=0)
    C_per_m: float = Field(..., gt=0)
    R_per_m: float = Field(..., ge=0)
    Gp_per_m: float = Field(..., ge=0)

    z0_real: float = Field(..., description="Re(Z0) [Ω].", gt=0)
    z0_imag: float = Field(..., description="Im(Z0) [Ω].")
    eps_eff: float = Field(..., ge=1)
    vp: float = Field(..., gt=0)

    # propagation constant γ = α + jβ
    alpha_neper_per_m: float = Field(..., ge=0)
    beta_rad_per_m: float = Field(..., gt=0)

    n_conductor_pixels: int = Field(..., ge=0)
    method: str = Field("faraday+laplace")
    warnings: list[SolverWarning] = Field(default_factory=list)


def _z0_complex(L: float, R: float, C: float, G: float, omega: float) -> complex:
    """Z0 = sqrt((R + jωL) / (G + jωC))"""
    num = R + 1j * omega * L
    den = G + 1j * omega * C
    return complex(np.sqrt(num / den))


def _gamma(L: float, R: float, C: float, G: float, omega: float) -> complex:
    """γ = sqrt((R + jωL)·(G + jωC))"""
    return complex(np.sqrt((R + 1j * omega * L) * (G + 1j * omega * C)))


def solve_lrs(
    usermap: Usermap,
    *,
    frequency_hz: float,
    method: str = "auto",
    tol: float = 1e-8,
    restrict_to_skin_depth: bool = True,
    skin_factor: float = 3.0,
) -> FaradayResult:
    """Solve only L and Rs (no C/Gp). Wraps :func:`atlc3.solvers.faraday.solve_lrs`.

    Optionally applies skin-depth masking before the solve to reduce the
    equation count.
    """
    if restrict_to_skin_depth:
        usermap = mask_skin_depth(usermap, frequency_hz, factor=skin_factor)
    return _solve_lrs_inner(usermap, frequency_hz=frequency_hz, method=method, tol=tol)


@cached("solve_full")
def solve_full(
    usermap: Usermap,
    *,
    frequency_hz: float,
    method: str = "auto",
    tol: float = 1e-8,
    restrict_to_skin_depth: bool = True,
    skin_factor: float = 3.0,
    extend_grid_for_cgp: bool = True,
) -> RLGCResult:
    """Solve both (L, Rs) and (C, Gp) at the given frequency.

    Returns a :class:`RLGCResult` with the full propagation parameters.
    """
    omega = 2.0 * np.pi * frequency_hz

    cgp_result = solve_cgp(
        usermap,
        frequency_hz=frequency_hz,
        method="auto",
        extend_grid=extend_grid_for_cgp,
    )

    lrs_input = (
        mask_skin_depth(usermap, frequency_hz, factor=skin_factor)
        if restrict_to_skin_depth
        else usermap
    )
    try:
        faraday = _solve_lrs_inner(lrs_input, frequency_hz=frequency_hz, method=method, tol=tol)
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"Faraday solve failed: {exc}; using analytical L from C_vacuum", stacklevel=2
        )
        # Fallback: use C/Gp's L_per_m (computed from C_vacuum)
        faraday = FaradayResult(
            L_per_m=cgp_result.L_per_m,
            R_per_m=0.0,
            z0_complex=complex(cgp_result.z0, 0),
            frequency_hz=frequency_hz,
            n_conductor_pixels=0,
            rs_low_confidence=True,
            rs_warning=f"Faraday solve failed; R=0 fallback ({exc})",
        )

    L = faraday.L_per_m
    R = faraday.R_per_m
    C = cgp_result.C_per_m
    G = cgp_result.Gp_per_m

    z0_c = _z0_complex(L, R, C, G, omega)
    gamma = _gamma(L, R, C, G, omega)

    warns: list[SolverWarning] = []
    if faraday.rs_low_confidence and faraday.rs_warning:
        warns.append(
            SolverWarning(
                code="rs_low_confidence",
                message=faraday.rs_warning,
                severity="warning",
            )
        )

    return RLGCResult(
        frequency_hz=frequency_hz,
        L_per_m=L,
        C_per_m=C,
        R_per_m=R,
        Gp_per_m=G,
        z0_real=float(z0_c.real),
        z0_imag=float(z0_c.imag),
        eps_eff=cgp_result.eps_eff,
        vp=cgp_result.vp,
        alpha_neper_per_m=float(gamma.real),
        beta_rad_per_m=float(abs(gamma.imag)),
        n_conductor_pixels=faraday.n_conductor_pixels,
        warnings=warns,
    )


__all__ = ["RLGCResult", "solve_full", "solve_lrs"]
