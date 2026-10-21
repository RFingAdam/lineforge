"""N-conductor Maxwell capacitance and external inductance matrices from Laplace solves.

For signal conductor k the potential phi_k has conductor k at 1 V and every other fixed
conductor (the reference and the other signals) at 0 V; floating groups are left to settle.
The energy matrix ``W[j, k] = sum over pixels of grad(phi_j) . grad(phi_k)`` is dimensionless
in 2-D (the pixel-size factors of the gradient and of the area element cancel), so

    C = eps0 * sum_m Re(er_m) * W[m]     [F/m]   Maxwell capacitance matrix
    G = omega * eps0 * sum_m (-Im er_m) * W[m]   [S/m]
    L_ext = mu0 * eps0 * inv(C0)         [H/m]   with C0 from the vacuum solves

``W`` is partitioned by material code so the same solve can be re-evaluated at any
frequency through :meth:`MaterialRecord.er_complex`. A conductor pixel's contribution
is booked on the dielectric it faces, not on the conductor: no field energy exists
inside a perfect conductor, so a conductor material's matrix is the zero matrix.

The Laplace edge coefficient is the arithmetic mean of the two pixels. A conductor
cell that touches an insulator is painted with that insulator's er so a homogeneous
fill's discrete operator is a scalar multiple of vacuum and C = er C0 holds to
round-off. Interior conductor pixels stay at er = 1; they are Dirichlet and the
stencil does not read them. This is the permittivity the adjacent dielectric already
stated, not a default.

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

    ``W[m]`` is the (N, N) energy matrix of material code ``m`` (``-1`` is vacuum /
    unrecognized), computed from the potentials solved with the materials' permittivity
    at ``f_ref_hz``. A conductor material's matrix is the zero matrix: pixel energy on
    the metal surface is attributed to the dielectric the pixel faces. ``W0`` is the
    all-space energy matrix of the vacuum solves and ``C0 = eps0 * W0``. ``W`` is empty
    when the result came from a ``vacuum_only=True`` solve, and :func:`rlgc_matrices`
    then refuses.

    ``pixel_width_m`` is the pixel size of the grid the matrices were solved on (the
    open-boundary extension replicates pixels and does not rescale them). It is carried so
    that a consumer holding only the result can convert between pixel counts and metres,
    for instance to rebuild or perturb the geometry the matrices belong to.
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
    Unrecognized pixels stay at 1. A conductor pixel that touches an insulator is
    painted with the mean of those neighbouring insulator values so the arithmetic-mean
    edge coefficient on a PEC face equals the dielectric er. Interior conductor pixels
    stay at 1; they are Dirichlet and unused.
    """
    out = np.ones(usermap.shape, dtype=np.float64)
    insulator = np.zeros(usermap.shape, dtype=bool)
    conductor = np.zeros(usermap.shape, dtype=bool)
    for idx, mat in enumerate(usermap.materials):
        sel = usermap.codes == idx
        if mat.is_insulator:
            out[sel] = mat.er if f_ref_hz is None else mat.er_complex(f_ref_hz).real
            insulator |= sel
        elif mat.is_conductor:
            conductor |= sel
    if not conductor.any() or not insulator.any():
        return out
    acc = np.zeros_like(out)
    cnt = np.zeros(usermap.shape, dtype=np.int32)

    def _add(shifted_er: np.ndarray, shifted_ins: np.ndarray) -> None:
        nonlocal acc, cnt
        acc = acc + np.where(shifted_ins, shifted_er, 0.0)
        cnt = cnt + shifted_ins

    e_er, e_ins = np.zeros_like(out), np.zeros(usermap.shape, dtype=bool)
    e_er[:, :-1], e_ins[:, :-1] = out[:, 1:], insulator[:, 1:]
    _add(e_er, e_ins)
    w_er, w_ins = np.zeros_like(out), np.zeros(usermap.shape, dtype=bool)
    w_er[:, 1:], w_ins[:, 1:] = out[:, :-1], insulator[:, :-1]
    _add(w_er, w_ins)
    s_er, s_ins = np.zeros_like(out), np.zeros(usermap.shape, dtype=bool)
    s_er[:-1, :], s_ins[:-1, :] = out[1:, :], insulator[1:, :]
    _add(s_er, s_ins)
    n_er, n_ins = np.zeros_like(out), np.zeros(usermap.shape, dtype=bool)
    n_er[1:, :], n_ins[1:, :] = out[:-1, :], insulator[:-1, :]
    _add(n_er, n_ins)
    take = conductor & (cnt > 0)
    out = np.where(take, acc / np.maximum(cnt, 1), out)
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


def _conductor_codes(materials: list[MaterialRecord]) -> frozenset[int]:
    """Material indices whose pixels are conductors."""
    return frozenset(i for i, mat in enumerate(materials) if mat.is_conductor)


def _energy_matrices(
    phi: np.ndarray,
    codes: np.ndarray,
    conductor_codes: frozenset[int],
) -> tuple[dict[int, np.ndarray], np.ndarray]:
    """Per-material energy matrices. Conductor-pixel energy is booked on the dielectric.

    The gradient is the same central-difference stencil as ``cgp._energy_integral``.
    A conductor pixel that faces one or more dielectric pixels has its ``|grad|^2``
    split equally among those dielectric material codes. Interior conductor pixels
    keep their own code; their gradient is zero to solver tolerance.
    """
    n = phi.shape[0]
    grads = [_gradients(phi[i]) for i in range(n)]
    h, w = codes.shape
    cond = np.zeros((h, w), dtype=bool)
    if conductor_codes:
        cond_ids = np.fromiter(conductor_codes, dtype=codes.dtype)
        cond = np.isin(codes, cond_ids)
    else:
        cond_ids = np.empty(0, dtype=codes.dtype)

    missing = np.iinfo(codes.dtype).min

    def _shift(src: np.ndarray, dy: int, dx: int) -> np.ndarray:
        out = np.full_like(src, missing)
        if dy == 0 and dx == 1:
            out[:, :-1] = src[:, 1:]
        elif dy == 0 and dx == -1:
            out[:, 1:] = src[:, :-1]
        elif dy == 1 and dx == 0:
            out[:-1, :] = src[1:, :]
        else:
            out[1:, :] = src[:-1, :]
        return out

    nbrs = [_shift(codes, 0, 1), _shift(codes, 0, -1), _shift(codes, 1, 0), _shift(codes, -1, 0)]
    diel_nbr: list[np.ndarray] = []
    for nbr in nbrs:
        is_diel = (nbr != missing) & (~np.isin(nbr, cond_ids) if conductor_codes else True)
        diel_nbr.append(np.where(is_diel, nbr, missing))
    n_diel = np.zeros((h, w), dtype=np.int32)
    for d in diel_nbr:
        n_diel += d != missing

    per_material: dict[int, np.ndarray] = {int(c): np.zeros((n, n)) for c in np.unique(codes)}
    total = np.zeros((n, n))

    def _add(
        key: int, mask: np.ndarray, scale: np.ndarray, e_jk: np.ndarray, j: int, k: int
    ) -> None:
        if not mask.any():
            return
        val = float((e_jk[mask] * scale[mask]).sum())
        bucket = per_material.setdefault(key, np.zeros((n, n)))
        bucket[j, k] += val
        total[j, k] += val
        if k != j:
            bucket[k, j] += val
            total[k, j] += val

    ones = np.ones((h, w), dtype=np.float64)
    for j in range(n):
        exj, eyj = grads[j]
        for k in range(j, n):
            exk, eyk = grads[k]
            e_jk = exj * exk + eyj * eyk
            diel = ~cond
            if diel.any():
                for m in np.unique(codes[diel]):
                    _add(int(m), diel & (codes == m), ones, e_jk, j, k)
            split = cond & (n_diel > 0)
            if split.any():
                wgt = np.zeros((h, w), dtype=np.float64)
                wgt[split] = 1.0 / n_diel[split]
                for d in diel_nbr:
                    present = split & (d != missing)
                    if not present.any():
                        continue
                    for m in np.unique(d[present]):
                        _add(int(m), present & (d == m), wgt, e_jk, j, k)
            leftover = cond & (n_diel == 0)
            if leftover.any():
                for m in np.unique(codes[leftover]):
                    _add(int(m), leftover & (codes == m), ones, e_jk, j, k)
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
    vacuum_only: bool = False,
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
    vacuum_only
        Run only the vacuum solve set, halving the cost. ``C0``, ``W0`` and ``phi0`` are
        as usual; ``W`` is left empty and ``phi`` is None, so ``C`` and ``G`` cannot be
        formed and :func:`rlgc_matrices` raises ``ValueError`` on such a result. Use it
        when only the inductance side is wanted, as the Wheeler erosion solves do.
    """
    ids = sorted(int(i) for i in np.unique(usermap.conductor_ids) if i >= 1)
    if not ids:
        raise ValueError("usermap has no signal conductors (conductor_ids >= 1)")
    extended = extension.extend(usermap, target_size=target_extent) if extend_grid else usermap

    er_field = _er_field(extended, f_ref_hz)
    conductor_codes = _conductor_codes(extended.materials)

    phi: np.ndarray | None = None
    it_er: list[int] = []
    w_per_material: dict[int, np.ndarray] = {}
    if not vacuum_only:
        phi, it_er = _solve_set(extended, er_field, ids, method=method, tol=tol, max_iter=max_iter)
        w_per_material, _ = _energy_matrices(phi, extended.codes, conductor_codes)

    phi0, it_vac = _solve_set(
        extended, np.ones_like(er_field), ids, method=method, tol=tol, max_iter=max_iter
    )
    _, w0 = _energy_matrices(phi0, extended.codes, conductor_codes)
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
    if float(np.min(np.linalg.eigvalsh(c0))) <= 0.0:
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
        phi=phi if keep_fields else None,  # already None when vacuum_only
        phi0=phi0 if keep_fields else None,
        iterations=it_er + it_vac,
        warnings=warnings,
    )


def rlgc_matrices(res: MaxwellResult, freq_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(C, G, L_ext)`` in F/m, S/m and H/m at ``freq_hz``.

    Raises ``ValueError`` when ``res`` came from a ``vacuum_only=True`` solve, which leaves
    out the per-material energy matrices that C and G are built from.
    """
    if not res.W:
        raise ValueError(
            "MaxwellResult has no per-material energy matrices (W is empty), so C and G "
            "cannot be formed; re-run solve_maxwell with vacuum_only=False"
        )
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
