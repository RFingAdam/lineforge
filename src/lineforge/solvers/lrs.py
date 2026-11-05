"""High-level L/Rs and full-RLGC orchestrator.

Combines:
    - The bitmap electrostatic solve for C and Gp (and, in vacuum, the
      external inductance L = mu0 eps0 / C_vacuum).
    - A conductor-loss calculation for R.

into a single full-frequency-resolved characterization.

Default path (``field_solver="graded"``)
----------------------------------------
:mod:`lineforge.solvers.graded` solves the usermap on its own pixels plus a
geometrically graded open-boundary padding, assembled sparse and solved
directly: a 0.1 mm microstrip at 5 um pixels is ~10k cells and solves in well
under a second. R comes from the perturbational (Wheeler incremental
inductance) method: the vacuum TEM solution gives the surface charge, hence the
surface current, on every conductor face, and

    R_ac = sum_faces Rs * |J_s|^2 * l_face        (I = 1 A)

with Rs = sqrt(pi f mu rho) (times an optional roughness factor). Below the
frequency where the skin depth is small against the conductor thickness the
DC resistance takes over through ``R = sqrt(R_dc^2 + R_ac^2)``. The internal
inductance R_ac / omega (capped at its DC value) is added to L.

Legacy path (``field_solver="uniform"`` / ``lrs_method="peec"``)
-----------------------------------------------------------------
The uniform-grid C/Gp solver and the dense PEEC Faraday solver remain
available. The PEEC system is dense in the conductor pixel count, so it is
refused above ``max_peec_pixels`` rather than allowed to allocate gigabytes.
"""

from __future__ import annotations

import warnings

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from lineforge.analytical._constants import EPS0, MU0
from lineforge.cache import cached
from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import RoughnessSpec
from lineforge.results import SolverWarning
from lineforge.solvers.cgp import solve_cgp
from lineforge.solvers.faraday import FaradayResult, SolverBudgetExceeded
from lineforge.solvers.faraday import solve_lrs as _solve_lrs_inner
from lineforge.solvers.graded import DEFAULT_MAX_CELLS, build_mesh, solve_mesh
from lineforge.solvers.skin_depth import mask_skin_depth

DEFAULT_MAX_PEEC_PIXELS = 8000
"""Conductor-pixel ceiling for the dense PEEC solver (~1 GB complex matrix, ~1.5 GB peak)."""


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
    pixel_width_m: float | None = Field(
        None, description="Pixel size actually solved (after any auto-coarsening) [m].", gt=0
    )
    n_mesh_cells: int | None = Field(
        None, description="Cells in the field-solve mesh (bitmap + graded padding).", ge=0
    )
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
    max_pixels: int = DEFAULT_MAX_PEEC_PIXELS,
) -> FaradayResult:
    """Solve only L and Rs (no C/Gp). Wraps :func:`lineforge.solvers.faraday.solve_lrs`.

    Optionally applies skin-depth masking before the solve to reduce the
    equation count. Raises :class:`SolverBudgetExceeded` when the dense PEEC
    system would exceed ``max_pixels`` conductor pixels.
    """
    if restrict_to_skin_depth:
        usermap = mask_skin_depth(usermap, frequency_hz, factor=skin_factor)
    return _solve_lrs_inner(
        usermap, frequency_hz=frequency_hz, method=method, tol=tol, max_pixels=max_pixels
    )


def _perturbational_r(
    usermap: Usermap,
    frequency_hz: float,
    roughness: RoughnessSpec | None,
    q: np.ndarray,
    length: np.ndarray,
    label: np.ndarray,
    rho: np.ndarray,
    mu_r: np.ndarray,
    bitmap_area: dict[int, tuple[float, float]],
) -> tuple[float, float, float, list[SolverWarning]]:
    """Return (R_total, R_ac, L_internal, warnings) from TEM surface charges."""
    warns: list[SolverWarning] = []
    omega = 2.0 * np.pi * frequency_hz
    q_plus = float(q[label == 1].sum())
    if q_plus <= 0:
        raise RuntimeError("perturbational R: the +1 conductor carries no charge")
    rs = np.sqrt(omega * MU0 * mu_r * rho / 2.0)
    delta_face = np.sqrt(2.0 * rho / (omega * MU0 * mu_r))
    if roughness is not None:
        from lineforge.solvers.roughness import roughness_factor

        rs = rs * np.array([roughness_factor(roughness, float(d)) for d in delta_face])
    j = q / q_plus  # face current for I = 1 A on the +1 conductor
    r_ac = float(np.sum(rs * j * j / length))

    # DC resistance: signal conductor plus its return (the -1 conductor if the
    # map has one, otherwise the ground), each with its bitmap cross-section.
    def _rdc(lbl: int) -> float:
        area, rho_k = bitmap_area.get(lbl, (0.0, 0.0))
        return rho_k / area if area > 0 else 0.0

    ret = 2 if 2 in bitmap_area else 0
    r_dc = _rdc(1) + _rdc(ret)
    r_tot = float(np.hypot(r_dc, r_ac))

    # Internal inductance of a skin-effect conductor is R_ac / omega; cap it at
    # the uniform-current (DC) value so it does not diverge as f -> 0.
    l_int = min(r_ac / omega, 2.0 * MU0 / (8.0 * np.pi))

    d_all = float(np.min(delta_face)) if delta_face.size else 0.0
    if usermap.pixel_width_m < 0.5 * d_all:
        warns.append(
            SolverWarning(
                code="rs_corner_overweight",
                message=(
                    f"pixel {usermap.pixel_width_m * 1e6:.3g} um is below half the skin depth "
                    f"({d_all * 1e6:.3g} um): the TEM corner singularity is resolved finer "
                    "than the real current spreads, so R reads high (~10-20%). A pixel of "
                    "about one skin depth matches Pucel's closed form."
                ),
                severity="info",
            )
        )

    # Confidence: the surface-impedance model needs delta << conductor thickness.
    from scipy.ndimage import distance_transform_edt

    plus = usermap.conductor_mask("+1")
    if plus.any() and (label == 1).any():
        dist = distance_transform_edt(plus)
        if isinstance(dist, tuple):
            dist = dist[0]
        thickness = 2.0 * float(np.max(dist)) * usermap.pixel_width_m
        d_min = float(np.min(delta_face[label == 1]))
        if d_min > thickness / 3.0:
            warns.append(
                SolverWarning(
                    code="rs_skin_depth_not_small",
                    message=(
                        f"skin depth {d_min * 1e6:.2f} um is not small against the "
                        f"conductor thickness ({thickness * 1e6:.1f} um); R blends DC and "
                        "surface-impedance values (sqrt(Rdc^2 + Rac^2)), accuracy ~±20%."
                    ),
                    severity="info",
                )
            )
    return r_tot, r_ac, l_int, warns


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
    field_solver: str = "graded",
    lrs_method: str = "auto",
    max_cells: int = DEFAULT_MAX_CELLS,
    max_peec_pixels: int = DEFAULT_MAX_PEEC_PIXELS,
    auto_coarsen: bool = True,
    roughness: RoughnessSpec | None = None,
) -> RLGCResult:
    """Solve both (L, Rs) and (C, Gp) at the given frequency.

    Parameters
    ----------
    usermap
        Cross-section bitmap.
    frequency_hz
        Solve frequency.
    method
        Dense/Krylov selector for the legacy PEEC solver (``lrs_method="peec"``).
    extend_grid_for_cgp
        Open boundary (graded padding / uniform extension). ``False`` treats
        the bitmap edge as a V = 0 shield.
    field_solver
        ``"graded"`` (default; sparse graded-mesh solve, bounded memory) or
        ``"uniform"`` (the legacy :func:`solve_cgp` path).
    lrs_method
        ``"auto"`` / ``"perturbation"`` (surface-impedance R from the TEM field)
        or ``"peec"`` (dense Faraday solver; refused above ``max_peec_pixels``).
        ``"auto"`` means perturbation with the graded solver and PEEC with
        the uniform one.
    max_cells
        Cell budget of the graded mesh. Larger inputs are block-coarsened
        (``auto_coarsen=True``, reported as an ``auto_coarsened`` warning) or
        refused with :class:`~lineforge.solvers.graded.MeshBudgetExceeded`.
    roughness
        Optional conductor roughness applied to the surface resistance.

    Returns a :class:`RLGCResult` with the full propagation parameters.
    """
    omega = 2.0 * np.pi * frequency_hz
    if field_solver not in {"graded", "uniform"}:
        raise ValueError(f"unknown field_solver {field_solver!r}")
    if lrs_method not in {"auto", "perturbation", "peec"}:
        raise ValueError(f"unknown lrs_method {lrs_method!r}")
    use_peec = lrs_method == "peec" or (lrs_method == "auto" and field_solver == "uniform")
    if not use_peec and field_solver != "graded":
        raise ValueError("lrs_method='perturbation' needs field_solver='graded'")

    warns: list[SolverWarning] = []
    n_cells: int | None = None
    px_used = usermap.pixel_width_m

    if field_solver == "graded":
        mesh = build_mesh(
            usermap,
            open_boundary=extend_grid_for_cgp,
            max_cells=max_cells,
            auto_coarsen=auto_coarsen,
        )
        n_cells = mesh.n_cells
        px_used = mesh.pixel_width_m
        if mesh.coarsen_factor > 1:
            warns.append(
                SolverWarning(
                    code="auto_coarsened",
                    message=(
                        f"usermap {usermap.shape} at {usermap.pixel_width_m * 1e6:.3g} um "
                        f"exceeds the {max_cells:,}-cell budget; solved at "
                        f"{px_used * 1e6:.3g} um (coarsened x{mesh.coarsen_factor})."
                    ),
                )
            )
        sol = solve_mesh(mesh)
        sol_vac = solve_mesh(mesh, vacuum=True)
        C = sol.capacitance_per_m
        C_vacuum = sol_vac.capacitance_per_m
        G = sol.conductance_per_m_over_omega * omega
        if C_vacuum <= 0 or C <= 0:
            raise RuntimeError("graded solve produced non-positive capacitance")
        L_ext = MU0 * EPS0 / C_vacuum
        eps_eff = C / C_vacuum
    else:
        cgp_result = solve_cgp(
            usermap,
            frequency_hz=frequency_hz,
            method="auto",
            extend_grid=extend_grid_for_cgp,
        )
        C = cgp_result.C_per_m
        G = cgp_result.Gp_per_m
        L_ext = cgp_result.L_per_m
        eps_eff = cgp_result.eps_eff

    n_cond_px = int(usermap.conductor_mask().sum())

    if use_peec:
        lrs_input = (
            mask_skin_depth(usermap, frequency_hz, factor=skin_factor)
            if restrict_to_skin_depth
            else usermap
        )
        try:
            faraday = _solve_lrs_inner(
                lrs_input,
                frequency_hz=frequency_hz,
                method=method,
                tol=tol,
                max_pixels=max_peec_pixels,
            )
        except SolverBudgetExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"Faraday solve failed: {exc}; using analytical L from C_vacuum", stacklevel=2
            )
            faraday = FaradayResult(
                L_per_m=L_ext,
                R_per_m=0.0,
                z0_complex=complex(np.sqrt(L_ext / C), 0),
                frequency_hz=frequency_hz,
                n_conductor_pixels=0,
                rs_low_confidence=True,
                rs_warning=f"Faraday solve failed; R=0 fallback ({exc})",
            )
        L = faraday.L_per_m
        R = faraday.R_per_m
        n_cond_px = faraday.n_conductor_pixels
        if faraday.rs_low_confidence and faraday.rs_warning:
            warns.append(SolverWarning(code="rs_low_confidence", message=faraday.rs_warning))
        method_tag = "faraday+laplace"
    else:
        ch = sol_vac.charges
        areas: dict[int, tuple[float, float]] = {}
        cell_area = mesh.dy[:, None] * mesh.dx[None, :]
        for lbl in (0, 1, 2):
            sel = (mesh.cond == lbl) & mesh.in_bitmap
            if sel.any():
                areas[lbl] = (float(cell_area[sel].sum()), float(np.mean(mesh.rho[sel])))
        R, _r_ac, l_int, r_warns = _perturbational_r(
            usermap,
            frequency_hz,
            roughness,
            ch.q,
            ch.length,
            ch.label,
            ch.rho,
            ch.mu_r,
            areas,
        )
        warns.extend(r_warns)
        L = L_ext + l_int
        method_tag = "graded-fd+perturbation"

    z0_c = _z0_complex(L, R, C, G, omega)
    gamma = _gamma(L, R, C, G, omega)

    return RLGCResult(
        frequency_hz=frequency_hz,
        L_per_m=L,
        C_per_m=C,
        R_per_m=R,
        Gp_per_m=G,
        z0_real=float(z0_c.real),
        z0_imag=float(z0_c.imag),
        eps_eff=float(eps_eff),
        vp=float(1.0 / np.sqrt(L_ext * C)),
        alpha_neper_per_m=float(gamma.real),
        beta_rad_per_m=float(abs(gamma.imag)),
        n_conductor_pixels=n_cond_px,
        method=method_tag,
        pixel_width_m=px_used,
        n_mesh_cells=n_cells,
        warnings=warns,
    )


__all__ = ["DEFAULT_MAX_PEEC_PIXELS", "RLGCResult", "solve_full", "solve_lrs"]
