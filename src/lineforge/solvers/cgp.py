"""C and Gp orchestrator — capacitance and dielectric conductance from the bitmap.

After the Laplace solve produces V(x,y), we extract:

**Capacitance per unit length**:
    C = (ε₀ / V²) · ∫ εr · |E|² dA   [F/m]

where V is the applied voltage difference (2.0 for ±1 conductors). Integrated
over the simulation area in pixel units; multiplied by ``pixel_width²`` to
convert to physical area.

**Shunt conductance per unit length** (dielectric loss):
    Gp(ω) = ω · ε₀ / V² · ∫ εr · tanδ · |E|² dA   [S/m]

Frequency-dependent.

**Z₀, vp, εeff (D.C. surface)**:
    First solve once with the actual εr field → C.
    Solve again with εr = 1 everywhere → C_vacuum.
    Then:
        L = μ₀ · ε₀ / C_vacuum     (since v_p,vacuum = c → L · C_vacuum = 1/c²)
        εeff = C / C_vacuum
        vp = c / sqrt(εeff)
        Z₀ = 1 / (vp · C) = sqrt(L / C)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, overload

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from lineforge.analytical._constants import C0, EPS0, MU0
from lineforge.cache import cached
from lineforge.geometry.usermap import Usermap
from lineforge.solvers import charge_shift, extension, laplace


class CGPResult(BaseModel):
    """C and Gp solve result."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    z0: float = Field(..., description="Characteristic impedance Z0 [Ω].", gt=0)
    eps_eff: float = Field(..., description="Effective relative permittivity εeff.", ge=1)
    vp: float = Field(..., description="Phase velocity [m/s].", gt=0)
    L_per_m: float = Field(..., description="Series inductance per meter [H/m].", gt=0)
    C_per_m: float = Field(..., description="Shunt capacitance per meter [F/m].", gt=0)
    Gp_per_m: float = Field(..., description="Shunt conductance per meter [S/m].", ge=0)
    frequency_hz: float | None = Field(None, gt=0)

    iterations: int = Field(..., description="Iterations used by the Laplace solver.")
    method: str = Field("laplace-fd", description="Solver method.")


@dataclass
class _LaplaceWorkspace:
    """Intermediate fields kept around for visualization or further analysis."""

    v_field: np.ndarray
    er_field: np.ndarray
    pixel_width_m: float
    iterations: int
    converged: bool
    extended_shape: tuple[int, int] = field(default=(0, 0))


def _extract_masks(usermap: Usermap) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[np.ndarray]]:
    """Return (plus_mask, minus_mask, ground_mask, [float_groups])."""
    plus = usermap.conductor_mask("+1")
    minus = usermap.conductor_mask("-1")
    ground = usermap.conductor_mask("0")

    # Floating conductors: group by RGB
    float_mask = usermap.conductor_mask("float")
    float_groups: list[np.ndarray] = []
    if float_mask.any():
        # Build groups by exact material code (so different float colors stay separate)
        for idx, mat in enumerate(usermap.materials):
            if mat.use == "float":
                grp = usermap.codes == idx
                if grp.any():
                    float_groups.append(grp)

    return plus, minus, ground, float_groups


def _energy_integral(
    v_field: np.ndarray,
    er_field: np.ndarray,
    weight_field: np.ndarray | None = None,
) -> float:
    """Compute ∫ εr · weight · |E|² dA in pixel units.

    The result has units of (pixel side)². Caller multiplies by ``pixel_width²``
    to get physical units.

    Uses central differences for ∂V/∂x and ∂V/∂y; cell-centered εr.
    """
    Ex = np.zeros_like(v_field)
    Ex[:, 1:-1] = -(v_field[:, 2:] - v_field[:, :-2]) / 2.0
    Ey = np.zeros_like(v_field)
    Ey[1:-1, :] = -(v_field[2:, :] - v_field[:-2, :]) / 2.0
    e_sq = Ex * Ex + Ey * Ey
    integrand = er_field * e_sq
    if weight_field is not None:
        integrand = integrand * weight_field
    return float(integrand.sum())


def _solve_one(
    usermap: Usermap,
    er_field: np.ndarray,
    *,
    use_charge_shift: bool,
    method: str,
    tol: float,
    max_iter: int | None,
) -> _LaplaceWorkspace:
    plus, minus, ground, float_groups = _extract_masks(usermap)

    v_mask = plus | minus | ground
    v_value = np.zeros(usermap.shape, dtype=np.float64)
    v_value[plus] = 1.0
    v_value[minus] = -1.0
    v_value[ground] = 0.0

    initial = None
    if use_charge_shift:
        initial = charge_shift.predict_v_field(er_field, plus, minus, ground)

    res = laplace.solve_laplace(
        er_field,
        v_mask,
        v_value,
        method=method,
        initial=initial,
        tol=tol,
        max_iter=max_iter,
        float_groups=float_groups,
    )
    return _LaplaceWorkspace(
        v_field=res.v_field,
        er_field=er_field,
        pixel_width_m=usermap.pixel_width_m,
        iterations=res.iterations,
        converged=res.converged,
        extended_shape=usermap.shape,
    )


@overload
def solve_cgp(
    usermap: Usermap,
    *,
    frequency_hz: float | None = ...,
    use_charge_shift: bool = ...,
    method: str = ...,
    tol: float = ...,
    max_iter: int | None = ...,
    extend_grid: bool = ...,
    target_extent: int = ...,
    return_fields: Literal[False] = False,
) -> CGPResult: ...
@overload
def solve_cgp(
    usermap: Usermap,
    *,
    frequency_hz: float | None = ...,
    use_charge_shift: bool = ...,
    method: str = ...,
    tol: float = ...,
    max_iter: int | None = ...,
    extend_grid: bool = ...,
    target_extent: int = ...,
    return_fields: Literal[True],
) -> tuple[CGPResult, _LaplaceWorkspace]: ...


@cached(
    "solve_cgp",
    # Skip cache when return_fields=True: the _LaplaceWorkspace contains big
    # numpy arrays that aren't worth disk-caching and aren't always picklable.
    skip_when=lambda *args, **kwargs: bool(kwargs.get("return_fields", False)),
)
def solve_cgp(
    usermap: Usermap,
    *,
    frequency_hz: float | None = None,
    use_charge_shift: bool = True,
    method: str = "auto",
    tol: float = 1e-7,
    max_iter: int | None = None,
    extend_grid: bool = True,
    target_extent: int = 3200,
    return_fields: bool = False,
) -> CGPResult | tuple[CGPResult, _LaplaceWorkspace]:
    """Solve for C, Gp, and the derived TL parameters of a Usermap.

    Strategy:
        1. Optionally extend the usermap (open-boundary, atlc2 §"For unshielded
           lines, the Usermap is extended outward...").
        2. Build the εr field and Dirichlet BC masks.
        3. Optionally seed with charge-shift E-prediction.
        4. Solve ∇·(εr ∇V) = 0 via SOR or AMG.
        5. Compute C from ∫½εr|E|² and Gp from ∫½ωεr·tanδ·|E|².
        6. Solve again with εr = 1 everywhere → C_vacuum → L, εeff, vp.

    Parameters
    ----------
    usermap
        Cross-section bitmap with material assignments.
    frequency_hz
        Frequency for Gp computation. Without it, Gp = 0.
    use_charge_shift
        atlc2's "Skip E prediction" checkbox = pass ``False`` here.
    method
        Laplace solver: ``"sor"``, ``"amg"``, or ``"auto"``.
    tol
        Convergence tolerance.
    max_iter
        Override default iteration cap.
    extend_grid
        Pad the usermap for open-boundary simulation.
    target_extent
        Target effective grid size (atlc2 uses 3200).
    return_fields
        If True, also return the V/εr workspace for visualization.

    Returns
    -------
    CGPResult or (CGPResult, _LaplaceWorkspace)
    """
    # Optionally extend
    extended = extension.extend(usermap, target_size=target_extent) if extend_grid else usermap
    er_field = extended.er_field()
    tan_delta_field = extended.tan_delta_field()

    # Solve with actual εr
    ws = _solve_one(
        extended,
        er_field,
        use_charge_shift=use_charge_shift,
        method=method,
        tol=tol,
        max_iter=max_iter,
    )

    V_drive = 2.0  # +1V to -1V
    has_minus = extended.conductor_mask("-1").any()
    if not has_minus:
        # No -1 conductor → drive voltage is 1.0 (V=+1 against V=0 ground)
        V_drive = 1.0

    # Capacitance: C = ε₀/V² · ∫ εr |E|² dA
    #
    # The pixel-unit gradients (V_diff between adjacent pixels) and pixel-unit
    # areas (1 per pixel) cancel out the dx factors automatically — verify
    # with a parallel-plate problem: discrete sum εr·(V/h_px)²·W_px·h_px
    # = εr·V²·W_px/h_px = εr·V²·W_phys/h_phys = ∫ εr|E_phys|² dA.
    integral_with_er = _energy_integral(ws.v_field, er_field)
    C_per_m = EPS0 / (V_drive * V_drive) * integral_with_er

    # Gp = ω · ε₀/V² · ∫ εr · tanδ · |E|² dA
    if frequency_hz and tan_delta_field.any():
        omega = 2 * np.pi * frequency_hz
        integral_loss = _energy_integral(ws.v_field, er_field, tan_delta_field)
        Gp_per_m = omega * EPS0 / (V_drive * V_drive) * integral_loss
    else:
        Gp_per_m = 0.0

    # Solve again with εr = 1 everywhere → C_vacuum → L, εeff, vp
    er_vac = np.ones_like(er_field)
    ws_vac = _solve_one(
        extended,
        er_vac,
        use_charge_shift=use_charge_shift,
        method=method,
        tol=tol,
        max_iter=max_iter,
    )
    integral_vac = _energy_integral(ws_vac.v_field, er_vac)
    C_vacuum = EPS0 / (V_drive * V_drive) * integral_vac

    if C_vacuum <= 0:
        raise RuntimeError("vacuum C solve produced non-positive capacitance")

    L_per_m = MU0 * EPS0 / C_vacuum
    eps_eff = C_per_m / C_vacuum
    vp = C0 / np.sqrt(eps_eff)
    z0 = float(np.sqrt(L_per_m / C_per_m))

    result = CGPResult(
        z0=z0,
        eps_eff=float(eps_eff),
        vp=float(vp),
        L_per_m=float(L_per_m),
        C_per_m=float(C_per_m),
        Gp_per_m=float(Gp_per_m),
        frequency_hz=frequency_hz,
        iterations=ws.iterations,
        method="laplace-fd-sor" if method != "amg" else "laplace-fd-amg",
    )
    if return_fields:
        return result, ws
    return result


__all__ = ["CGPResult", "solve_cgp"]
