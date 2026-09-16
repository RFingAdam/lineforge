"""N-conductor Maxwell capacitance and external inductance matrices from Laplace solves.

For signal conductor k the potential phi_k has conductor k at 1 V and every other fixed
conductor (the reference and the other signals) at 0 V; floating groups are left to settle.
The energy matrix ``W[j, k] = sum over pixels of grad(phi_j) . grad(phi_k)`` is dimensionless
in 2-D (the pixel-size factors of the gradient and of the area element cancel), so

    C = eps0 * sum_m Re(er_m) * W[m]     [F/m]   Maxwell capacitance matrix
    G = omega * eps0 * sum_m (-Im er_m) * W[m]   [S/m]
    L_ext = mu0 * eps0 * inv(C0)         [H/m]   with C0 from the vacuum solves

``W`` is partitioned by material code so the same solve can be re-evaluated at any
frequency through :meth:`MaterialRecord.er_complex`. Conductor and unknown pixels carry
er = 1, matching :func:`lineforge.solvers.cgp.solve_cgp`.

Re-evaluating ``C(f)`` from potentials that were solved once at ``f_ref_hz`` is a
stationary estimate: the capacitance functional is second order in the error of the
potential, so a first-order change of the permittivity field away from ``f_ref_hz``
leaves a second-order error in ``C``. It is not exact. For a wide sweep over a strongly
dispersive stack, re-solve at a reference frequency near the band of interest.

Paul, Analysis of Multiconductor Transmission Lines, 2nd ed., ch. 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from lineforge.analytical._constants import EPS0, MU0
from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord
from lineforge.results import SolverWarning
from lineforge.solvers import extension, laplace


@dataclass
class MaxwellResult:
    """Energy matrices of an N-conductor cross-section.

    ``W[m]`` is the (N, N) energy matrix restricted to the pixels of material code ``m``
    (``-1`` is vacuum / unrecognized), computed from the potentials solved with the
    materials' permittivity at ``f_ref_hz``. ``W0`` is the all-space energy matrix of the
    vacuum solves and ``C0 = eps0 * W0``.
    """

    conductor_ids: list[int]
    C0: np.ndarray
    W: dict[int, np.ndarray]
    W0: np.ndarray
    materials: list[MaterialRecord]
    pixel_width_m: float
    phi: np.ndarray | None = None
    phi0: np.ndarray | None = None
    iterations: list[int] = field(default_factory=list)
    warnings: list[SolverWarning] = field(default_factory=list)


def _gradients(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference E = -grad(V) in pixel units (same stencil as ``cgp._energy_integral``)."""
    ex = np.zeros_like(v)
    ex[:, 1:-1] = -(v[:, 2:] - v[:, :-2]) / 2.0
    ey = np.zeros_like(v)
    ey[1:-1, :] = -(v[2:, :] - v[:-2, :]) / 2.0
    return ex, ey


def _float_groups(usermap: Usermap) -> list[np.ndarray]:
    """Floating conductor groups, one per material code (so distinct floats stay separate)."""
    groups: list[np.ndarray] = []
    floats = usermap.conductor_ids == -2
    if not floats.any():
        return groups
    for idx in range(len(usermap.materials)):
        grp = floats & (usermap.codes == idx)
        if grp.any():
            groups.append(grp)
    leftover = floats & (usermap.codes < 0)
    if leftover.any():
        groups.append(leftover)
    return groups


def _er_field(usermap: Usermap, f_ref_hz: float | None) -> np.ndarray:
    """Per-pixel permittivity for the solve.

    Insulators use their nominal ``er`` (``f_ref_hz is None``) or ``Re er(f_ref_hz)``.
    Conductors and unrecognized pixels carry er = 1 in both branches, as in
    :func:`lineforge.solvers.cgp.solve_cgp`.
    """
    out = np.ones(usermap.shape, dtype=np.float64)
    for idx, mat in enumerate(usermap.materials):
        if not mat.is_insulator:
            continue
        out[usermap.codes == idx] = mat.er if f_ref_hz is None else mat.er_complex(f_ref_hz).real
    return out


def _unlabelled_conductor_count(usermap: Usermap) -> int:
    """Conductor-material pixels that no ``conductor_ids`` entry claims."""
    material_conductor = np.zeros(usermap.shape, dtype=bool)
    for idx, mat in enumerate(usermap.materials):
        if mat.is_conductor:
            material_conductor |= usermap.codes == idx
    return int((material_conductor & (usermap.conductor_ids == -1)).sum())


def _fixed_mask(usermap: Usermap) -> np.ndarray:
    """Dirichlet pixels: every conductor except the floating ones."""
    fixed: np.ndarray = usermap.conductor_mask(None) & ~(usermap.conductor_ids == -2)
    return fixed


def _amg_selected(method: str, fixed: np.ndarray) -> bool:
    """Replicate ``laplace.solve_laplace``'s dispatch: does this solve go to AMG?"""
    if method == "amg":
        return True
    if method == "auto":
        return int((~fixed).sum()) >= 250_000
    return False


def _solve_set(
    usermap: Usermap,
    er_field: np.ndarray,
    ids: list[int],
    *,
    method: str,
    tol: float,
    max_iter: int | None,
) -> tuple[np.ndarray, list[int]]:
    """Solve one Laplace problem per signal conductor, that conductor at 1 V."""
    fixed = _fixed_mask(usermap)
    float_groups = _float_groups(usermap)
    phi = np.zeros((len(ids), *usermap.shape), dtype=np.float64)
    iters: list[int] = []
    for n, k in enumerate(ids):
        v_value = np.zeros(usermap.shape, dtype=np.float64)
        v_value[usermap.conductor_ids == k] = 1.0
        res = laplace.solve_laplace(
            er_field,
            fixed,
            v_value,
            method=method,
            tol=tol,
            max_iter=max_iter,
            float_groups=float_groups,
        )
        phi[n] = res.v_field
        iters.append(res.iterations)
    return phi, iters


def _energy_matrices(
    phi: np.ndarray, codes: np.ndarray
) -> tuple[dict[int, np.ndarray], np.ndarray]:
    """Per-material and total energy matrices ``W[j, k] = sum grad(phi_j) . grad(phi_k)``."""
    n = phi.shape[0]
    grads = [_gradients(phi[i]) for i in range(n)]
    total = np.zeros((n, n))
    per_material: dict[int, np.ndarray] = {}
    for m in (int(c) for c in np.unique(codes)):
        sel = codes == m
        w = np.zeros((n, n))
        for j in range(n):
            exj, eyj = grads[j]
            for k in range(j, n):
                exk, eyk = grads[k]
                val = float(((exj * exk + eyj * eyk)[sel]).sum())
                w[j, k] = val
                w[k, j] = val
        per_material[m] = w
        total += w
    return per_material, total


def solve_maxwell(
    usermap: Usermap,
    *,
    f_ref_hz: float | None = None,
    method: str = "auto",
    tol: float = 1e-7,
    max_iter: int | None = None,
    extend_grid: bool = True,
    target_extent: int = 3200,
    keep_fields: bool = False,
) -> MaxwellResult:
    """Solve the N-conductor Maxwell energy matrices of ``usermap``.

    One Laplace solve per signal conductor (``conductor_ids >= 1``) with that conductor at
    1 V and every other fixed conductor at 0 V, plus the same set again with er = 1
    everywhere for the external inductance. The outer grid boundary is 0 V, as in
    :func:`lineforge.solvers.cgp.solve_cgp`.

    Conventions and limitations, both reported through :attr:`MaxwellResult.warnings`:

    - A conductor-material pixel that carries no ``conductor_ids`` entry (``-1``) is
      pinned to 0 V, that is, treated as part of the reference. Such pixels raise the
      ``unlabelled_conductor_pixels`` warning with their count.
    - :func:`lineforge.solvers.laplace.solve_amg` has no floating-conductor support and
      silently ignores ``float_groups``. When this solve dispatches to AMG (explicitly,
      or through ``method="auto"`` on a grid with at least 250k free pixels) and the map
      has floating conductors, the ``float_groups_ignored_by_amg`` warning is raised and
      the floating conductors are solved as ordinary dielectric. Pass ``method="sor"``
      for a map with floating conductors.

    Parameters
    ----------
    f_ref_hz
        Frequency at which the materials' permittivity is evaluated for the solve. Without
        it the nominal ``er`` of each material is used.
    keep_fields
        Keep the (N, H, W) potential stacks on the result (for field plots or the
        roughness/erosion re-solves).
    """
    ids = sorted(int(i) for i in np.unique(usermap.conductor_ids) if i >= 1)
    if not ids:
        raise ValueError("usermap has no signal conductors (conductor_ids >= 1)")
    extended = extension.extend(usermap, target_size=target_extent) if extend_grid else usermap

    er_field = _er_field(extended, f_ref_hz)

    phi, it_er = _solve_set(extended, er_field, ids, method=method, tol=tol, max_iter=max_iter)
    w_per_material, _ = _energy_matrices(phi, extended.codes)

    phi0, it_vac = _solve_set(
        extended, np.ones_like(er_field), ids, method=method, tol=tol, max_iter=max_iter
    )
    _, w0 = _energy_matrices(phi0, extended.codes)
    c0 = EPS0 * w0

    warnings: list[SolverWarning] = []
    n_unlabelled = _unlabelled_conductor_count(extended)
    if n_unlabelled:
        warnings.append(
            SolverWarning(
                code="unlabelled_conductor_pixels",
                message=(
                    f"{n_unlabelled} conductor pixel(s) carry no conductor_ids entry and are "
                    "driven at 0 V (treated as reference); label them 1..N to drive them"
                ),
            )
        )
    if _float_groups(extended) and _amg_selected(method, _fixed_mask(extended)):
        warnings.append(
            SolverWarning(
                code="float_groups_ignored_by_amg",
                message=(
                    "the AMG Laplace solver ignores floating conductors; they were solved as "
                    "dielectric. Pass method='sor' to enforce the floating equipotential"
                ),
            )
        )
    if float(np.linalg.eigvalsh(c0).min()) <= 0.0:
        warnings.append(
            SolverWarning(
                code="c0_not_positive_definite",
                message=(
                    "vacuum capacitance matrix is not positive definite; check conductor labels"
                ),
                severity="error",
            )
        )
    return MaxwellResult(
        conductor_ids=ids,
        C0=c0,
        W=w_per_material,
        W0=w0,
        materials=list(extended.materials),
        pixel_width_m=extended.pixel_width_m,
        phi=phi if keep_fields else None,
        phi0=phi0 if keep_fields else None,
        iterations=it_er + it_vac,
        warnings=warnings,
    )


def rlgc_matrices(res: MaxwellResult, freq_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(C, G, L_ext)`` in F/m, S/m and H/m at ``freq_hz``."""
    n = len(res.conductor_ids)
    c = np.zeros((n, n))
    g = np.zeros((n, n))
    omega = 2.0 * np.pi * freq_hz
    for m, w in res.W.items():
        if m < 0:
            er = complex(1.0, 0.0)
        else:
            mat = res.materials[m]
            er = mat.er_complex(freq_hz) if mat.is_insulator else complex(1.0, 0.0)
        c += er.real * w
        g += (-er.imag) * w
    c *= EPS0
    g *= omega * EPS0
    l_ext: np.ndarray = MU0 * EPS0 * np.linalg.inv(res.C0)
    return c, g, l_ext


__all__ = ["MaxwellResult", "rlgc_matrices", "solve_maxwell"]
