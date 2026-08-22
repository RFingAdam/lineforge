"""Laplace solver: finite-difference relaxation for ∇·(εr ∇V) = 0.

The 5-point FD scheme on a uniform Cartesian grid with εr varying per cell:

    V[i,j] · (αE+αW+αN+αS) = αE·V[i,j+1] + αW·V[i,j-1]
                              + αN·V[i-1,j] + αS·V[i+1,j]

where αX = arithmetic mean of εr at the cell-edge between (i,j) and the
neighbor: accurate enough for piecewise-constant material maps and matches
atlc v1's choice.

Two solvers:
    - :func:`solve_sor`: Successive over-relaxation, default ω = 1.9. Pure
      NumPy. Best for grids ≲ 1000² in Phase 2.
    - :func:`solve_amg`: Algebraic multigrid via PyAMG. ~5–10× faster on
      grids ≳ 1000². Falls back to SOR if PyAMG isn't installed.

Boundary conditions:
    - **Dirichlet**: pixels in ``v_mask`` are clamped to ``v_value``.
    - **Floating** conductors: pixel groups passed via ``float_groups``. The
      group is forced to a single equipotential value at every iteration via
      the ``floating_mode`` parameter:

      * ``"average"`` (default): V_group = arithmetic mean of the group's
        post-relaxation values. Fast and correct for symmetric problems
        (where the linear-V centroid coincides with the zero-net-charge V).
        For asymmetric εr around the group it's an approximation; use the
        radiation indicator (Σ E·n on the group boundary) to flag cases
        where it matters.
      * ``"boundary_weighted"``: V_group = εr-weighted average of the
        outward-neighbor potentials. More accurate when εr is asymmetric
        around the group. Stable for the cases tested (3-wire above ground,
        coupled-stripline coupler); see ``tests/test_solvers/test_floating_bc.py``.

      A rigorous Schur-complement formulation enforcing exactly zero net
      charge on each floating group is tracked as a follow-up: for the
      3-wire Y-decomposition use case the existing modes are sufficient
      modulo the 4 % radiation indicator.
    - **Outer boundary**: zero-Dirichlet (V=0). Combined with
      :mod:`lineforge.solvers.extension` this approximates "ground at infinity".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp


@dataclass
class LaplaceResult:
    """Output of a Laplace solve."""

    v_field: np.ndarray
    """Voltage field, shape (H, W)."""

    iterations: int
    """Number of iterations performed."""

    residual: float
    """Final residual (max |ΔV| in the last iteration for SOR;
    ‖Ax − b‖ for AMG)."""

    converged: bool
    """True if residual fell below tolerance."""

    method: str
    """``"sor"`` or ``"amg"``, which solver produced the result."""


def _edge_coefficients(er: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute εr at the four cell-edges of every pixel via arithmetic mean.

    Returns (aE, aW, aN, aS) with cells beyond the grid set to zero (Dirichlet
    V=0 at the outer boundary).
    """
    h, w = er.shape
    aE = np.zeros((h, w), dtype=np.float64)
    aW = np.zeros((h, w), dtype=np.float64)
    aN = np.zeros((h, w), dtype=np.float64)
    aS = np.zeros((h, w), dtype=np.float64)
    aE[:, :-1] = 0.5 * (er[:, :-1] + er[:, 1:])
    aW[:, 1:] = aE[:, :-1]
    aN[1:, :] = 0.5 * (er[:-1, :] + er[1:, :])
    aS[:-1, :] = aN[1:, :]
    return aE, aW, aN, aS


# ---------------------------------------------------------------------------
# SOR solver
# ---------------------------------------------------------------------------


def _equipotential_boundary_weighted(
    v: np.ndarray,
    aE: np.ndarray,
    aW: np.ndarray,
    aN: np.ndarray,
    aS: np.ndarray,
    group: np.ndarray,
) -> float:
    """Compute the equipotential V_F as the εr-weighted average of the
    group's external-neighbor potentials.

    For a constant-V group F satisfying ∮(εr ∇V)·n dA = 0 on its boundary
    (zero net induced charge), the FD form gives::

        V_F = Σ_{external edges} α_edge · V_neighbor_outside  /  Σ_{external edges} α_edge

    Internal edges (between two F-cells) cancel and don't contribute. This
    is computed directly here without iterating on a current-V proxy, so it
    converges cleanly even in highly asymmetric εr geometries.
    """
    # For each direction (E, W, N, S), find F-cells whose neighbor in that
    # direction is OUTSIDE F (or off-grid).
    # Boundary masks: True for F-cells whose <dir>-neighbor is outside F.
    out_E = group.copy()
    out_E[:, :-1] = group[:, :-1] & ~group[:, 1:]  # E-neighbor outside
    # The rightmost column has no E-neighbor (off-grid is "outside"). Keep True.

    out_W = group.copy()
    out_W[:, 1:] = group[:, 1:] & ~group[:, :-1]

    out_N = group.copy()
    out_N[1:, :] = group[1:, :] & ~group[:-1, :]

    out_S = group.copy()
    out_S[:-1, :] = group[:-1, :] & ~group[1:, :]

    # Neighbor potentials (zero-padded at grid boundary, which matches the
    # outer Dirichlet V=0 BC of the solver).
    nE = np.zeros_like(v)
    nE[:, :-1] = v[:, 1:]
    nW = np.zeros_like(v)
    nW[:, 1:] = v[:, :-1]
    nN = np.zeros_like(v)
    nN[1:, :] = v[:-1, :]
    nS = np.zeros_like(v)
    nS[:-1, :] = v[1:, :]

    num = float(
        (aE * out_E * nE).sum()
        + (aW * out_W * nW).sum()
        + (aN * out_N * nN).sum()
        + (aS * out_S * nS).sum()
    )
    denom = float((aE * out_E).sum() + (aW * out_W).sum() + (aN * out_N).sum() + (aS * out_S).sum())
    if denom <= 0:
        # Group fully interior with no boundary. Keep current value.
        return float(v[group].mean())
    return num / denom


def solve_sor(
    er: np.ndarray,
    v_mask: np.ndarray,
    v_value: np.ndarray,
    *,
    initial: np.ndarray | None = None,
    omega: float = 1.9,
    max_iter: int = 50_000,
    tol: float = 1e-7,
    check_every: int = 50,
    float_groups: list[np.ndarray] | None = None,
    floating_mode: str = "average",
) -> LaplaceResult:
    """Successive over-relaxation Laplace solve.

    See module docstring for the discretization and BC handling.
    """
    if er.shape != v_mask.shape or er.shape != v_value.shape:
        raise ValueError(
            f"shape mismatch: er={er.shape}, v_mask={v_mask.shape}, v_value={v_value.shape}"
        )

    aE, aW, aN, aS = _edge_coefficients(er)
    denom = aE + aW + aN + aS
    safe_denom = np.where(denom > 0, denom, 1.0)

    v = initial.copy() if initial is not None else np.zeros_like(er, dtype=np.float64)
    v[v_mask] = v_value[v_mask]
    free = ~v_mask

    h, w = er.shape
    ij = (np.arange(h)[:, None] + np.arange(w)[None, :]) % 2
    parity_masks = [(ij == 0) & free, (ij == 1) & free]

    residual = float("inf")
    last_check = v.copy()

    for it in range(1, max_iter + 1):
        for pmask in parity_masks:
            nE = np.zeros_like(v)
            nE[:, :-1] = v[:, 1:]
            nW = np.zeros_like(v)
            nW[:, 1:] = v[:, :-1]
            nN = np.zeros_like(v)
            nN[1:, :] = v[:-1, :]
            nS = np.zeros_like(v)
            nS[:-1, :] = v[1:, :]
            num = aE * nE + aW * nW + aN * nN + aS * nS
            v_pixel = num / safe_denom
            v[pmask] += omega * (v_pixel[pmask] - v[pmask])

        if float_groups:
            for group in float_groups:
                if not group.any():
                    continue
                if floating_mode == "boundary_weighted":
                    v_f = _equipotential_boundary_weighted(v, aE, aW, aN, aS, group)
                else:
                    v_f = float(v[group].mean())
                v[group] = v_f

        if it % check_every == 0:
            residual = float(np.max(np.abs(v - last_check)))
            if residual < tol:
                return LaplaceResult(
                    v_field=v,
                    iterations=it,
                    residual=residual,
                    converged=True,
                    method="sor",
                )
            last_check = v.copy()

    return LaplaceResult(
        v_field=v,
        iterations=max_iter,
        residual=residual,
        converged=False,
        method="sor",
    )


# ---------------------------------------------------------------------------
# Algebraic multigrid (PyAMG) solver
# ---------------------------------------------------------------------------


def _build_laplace_csr(er: np.ndarray) -> sp.csr_matrix:
    """Assemble the discrete εr-weighted 5-point Laplacian as a CSR sparse matrix.

    For unmasked rows we use the standard FD pattern. The diagonal is
    ``-(αE+αW+αN+αS)`` so that ``A·v = 0`` is the discrete Laplace equation.
    """
    aE, aW, aN, aS = _edge_coefficients(er)
    h, w = er.shape
    n = h * w
    diag = -(aE + aW + aN + aS).ravel()

    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    data: list[np.ndarray] = []

    idx_grid = np.arange(n).reshape(h, w)

    # Main diagonal
    rows.append(np.arange(n))
    cols.append(np.arange(n))
    data.append(diag)

    # East: link (i,j) with (i,j+1)
    valid = aE[:, :-1] > 0
    r = idx_grid[:, :-1][valid]
    c = idx_grid[:, 1:][valid]
    d = aE[:, :-1][valid]
    rows += [r, c]
    cols += [c, r]
    data += [d, d]  # symmetric

    # South: link (i,j) with (i+1,j)
    valid = aS[:-1, :] > 0
    r = idx_grid[:-1, :][valid]
    c = idx_grid[1:, :][valid]
    d = aS[:-1, :][valid]
    rows += [r, c]
    cols += [c, r]
    data += [d, d]

    A = sp.coo_matrix(
        (np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n),
    ).tocsr()
    return A


def _apply_dirichlet(
    A: sp.csr_matrix, b: np.ndarray, mask_flat: np.ndarray, val_flat: np.ndarray
) -> tuple[sp.csr_matrix, np.ndarray]:
    """Reduce a sparse system to a square Laplace system with Dirichlet BCs imposed.

    Strategy: keep all rows/cols, but zero rows of ``A`` that are masked,
    set their diagonal to 1, and put ``v_value`` in ``b``. Move ``A[free, masked]
    @ val_flat[masked]`` to the RHS for free rows so the solve doesn't have to
    iterate against fixed values.

    The earlier implementation slammed into a scipy quirk: ``A[:, masked]`` for
    a CSR matrix builds a dense ``(n, len(masked))`` int64 indexing
    intermediate, which OOMs on extended-boundary grids (issue #32). We now
    project via a sparse boundary vector instead: O(nnz(A)) regardless of
    mask size.
    """
    n = A.shape[0]
    masked = np.where(mask_flat)[0]

    # Move masked-column contributions to RHS via a one-shot sparse mat-vec.
    boundary = np.zeros(n, dtype=np.float64)
    boundary[masked] = val_flat[masked]
    contrib = A @ boundary
    b = b - contrib

    # Zero masked rows + masked columns of A.
    A_csc = A.tocsc()
    for ri in masked:
        ptr = slice(A_csc.indptr[ri], A_csc.indptr[ri + 1])
        A_csc.data[ptr] = 0.0
    A_csr = A_csc.tocsr()
    for ri in masked:
        ptr = slice(A_csr.indptr[ri], A_csr.indptr[ri + 1])
        A_csr.data[ptr] = 0.0

    # Set diagonal = 1 for masked rows and RHS = val. Build a tiny diagonal
    # patch matrix instead of round-tripping through LIL so we never allocate
    # a (n,)-sized object array for large grids.
    diag_patch = sp.coo_matrix(
        (np.ones(len(masked), dtype=np.float64), (masked, masked)),
        shape=(n, n),
    ).tocsr()
    A_csr = A_csr + diag_patch
    b[masked] = val_flat[masked]

    return A_csr, b


def solve_amg(
    er: np.ndarray,
    v_mask: np.ndarray,
    v_value: np.ndarray,
    *,
    tol: float = 1e-9,
    max_iter: int = 200,
) -> LaplaceResult:
    """Solve via PyAMG smoothed-aggregation multigrid. Falls back to SOR if PyAMG missing."""
    try:
        import pyamg
    except ImportError:
        import warnings

        warnings.warn(
            "PyAMG not installed; falling back to SOR. `pip install pyamg` for a speedup.",
            stacklevel=2,
        )
        return solve_sor(er, v_mask, v_value)

    h, w = er.shape
    n = h * w
    A = _build_laplace_csr(er)
    b = np.zeros(n, dtype=np.float64)
    A_red, b_red = _apply_dirichlet(A, b, v_mask.ravel(), v_value.ravel())
    A_red.eliminate_zeros()

    ml = pyamg.smoothed_aggregation_solver(A_red.astype(np.float64))
    x = ml.solve(b_red, tol=tol, maxiter=max_iter)

    residual = float(np.linalg.norm(A_red @ x - b_red))
    converged = bool(residual < tol * (1 + np.linalg.norm(b_red)))
    return LaplaceResult(
        v_field=x.reshape(h, w),
        iterations=max_iter,
        residual=residual,
        converged=converged,
        method="amg",
    )


def solve_laplace(
    er: np.ndarray,
    v_mask: np.ndarray,
    v_value: np.ndarray,
    *,
    method: str = "auto",
    initial: np.ndarray | None = None,
    omega: float = 1.9,
    max_iter: int | None = None,
    tol: float = 1e-7,
    float_groups: list[np.ndarray] | None = None,
    floating_mode: str = "average",
) -> LaplaceResult:
    """Top-level Laplace solve dispatcher.

    Parameters
    ----------
    method
        ``"sor"``, ``"amg"``, or ``"auto"``. Auto picks AMG for grids
        with ≥ 250_000 free pixels, SOR otherwise.
    floating_mode
        ``"average"`` or ``"charge_balanced"``. See module docstring.
    """
    n_free = int((~v_mask).sum())
    chosen = method
    if method == "auto":
        chosen = "amg" if n_free >= 250_000 else "sor"

    if chosen == "amg":
        return solve_amg(er, v_mask, v_value, tol=tol, max_iter=max_iter or 200)
    return solve_sor(
        er,
        v_mask,
        v_value,
        initial=initial,
        omega=omega,
        max_iter=max_iter or 50_000,
        tol=tol,
        float_groups=float_groups,
        floating_mode=floating_mode,
    )


__all__ = ["LaplaceResult", "solve_amg", "solve_laplace", "solve_sor"]
