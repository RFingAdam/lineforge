"""Laplace solver — finite-difference relaxation for ∇·(εr ∇V) = 0.

The 5-point FD scheme on a uniform Cartesian grid with εr varying per cell:

    V[i,j] · (αE+αW+αN+αS) = αE·V[i,j+1] + αW·V[i,j-1]
                              + αN·V[i-1,j] + αS·V[i+1,j]

where αX = arithmetic mean of εr at the cell-edge between (i,j) and the
neighbor — accurate enough for piecewise-constant material maps and matches
atlc v1's choice.

Two solvers:
    - :func:`solve_sor` — Successive over-relaxation, default ω = 1.9. Pure
      NumPy. Best for grids ≲ 1000² in Phase 2.
    - :func:`solve_amg` — Algebraic multigrid via PyAMG. ~5–10× faster on
      grids ≳ 1000². Falls back to SOR if PyAMG isn't installed.

Boundary conditions:
    - **Dirichlet**: pixels in ``v_mask`` are clamped to ``v_value``.
    - **Floating** conductors: pixel groups passed via ``float_groups``. SOR
      enforces a common voltage by averaging within each group every iteration
      (a simplification of atlc2's eddy-current treatment; the rigorous version
      lives in the Phase 3 Faraday solver).
    - **Outer boundary**: zero-Dirichlet (V=0). Combined with
      :mod:`atlc3.solvers.extension` this approximates "ground at infinity".
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
    """``"sor"`` or ``"amg"`` — which solver produced the result."""


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

    v = (initial.copy() if initial is not None else np.zeros_like(er, dtype=np.float64))
    v[v_mask] = v_value[v_mask]
    free = ~v_mask

    h, w = er.shape
    ij = (np.arange(h)[:, None] + np.arange(w)[None, :]) % 2
    parity_masks = [(ij == 0) & free, (ij == 1) & free]

    residual = float("inf")
    last_check = v.copy()

    for it in range(1, max_iter + 1):
        for pmask in parity_masks:
            nE = np.zeros_like(v); nE[:, :-1] = v[:, 1:]
            nW = np.zeros_like(v); nW[:, 1:] = v[:, :-1]
            nN = np.zeros_like(v); nN[1:, :] = v[:-1, :]
            nS = np.zeros_like(v); nS[:-1, :] = v[1:, :]
            num = aE * nE + aW * nW + aN * nN + aS * nS
            v_pixel = num / safe_denom
            v[pmask] += omega * (v_pixel[pmask] - v[pmask])

        if float_groups:
            for group in float_groups:
                if group.any():
                    v[group] = float(v[group].mean())

        if it % check_every == 0:
            residual = float(np.max(np.abs(v - last_check)))
            if residual < tol:
                return LaplaceResult(
                    v_field=v, iterations=it, residual=residual,
                    converged=True, method="sor",
                )
            last_check = v.copy()

    return LaplaceResult(
        v_field=v, iterations=max_iter, residual=residual,
        converged=False, method="sor",
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
    rows.append(np.arange(n)); cols.append(np.arange(n)); data.append(diag)

    # East: link (i,j) with (i,j+1)
    valid = aE[:, :-1] > 0
    r = idx_grid[:, :-1][valid]
    c = idx_grid[:, 1:][valid]
    d = aE[:, :-1][valid]
    rows += [r, c]; cols += [c, r]; data += [d, d]  # symmetric

    # South: link (i,j) with (i+1,j)
    valid = aS[:-1, :] > 0
    r = idx_grid[:-1, :][valid]
    c = idx_grid[1:, :][valid]
    d = aS[:-1, :][valid]
    rows += [r, c]; cols += [c, r]; data += [d, d]

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
    """
    A = A.tolil()
    n = A.shape[0]
    masked = np.where(mask_flat)[0]

    # Move masked-column contributions to RHS for free rows
    A_csr_view = A.tocsr()
    contrib = A_csr_view[:, masked] @ val_flat[masked]
    b = b - contrib

    # Now zero masked rows + columns and set the diagonal to 1
    A_csc = A.tocsc()
    for ri in masked:
        ptr = slice(A_csc.indptr[ri], A_csc.indptr[ri + 1])
        A_csc.data[ptr] = 0.0
    A_csr = A_csc.tocsr()
    for ri in masked:
        ptr = slice(A_csr.indptr[ri], A_csr.indptr[ri + 1])
        A_csr.data[ptr] = 0.0

    # Set diagonal = 1 and RHS = val for masked rows
    A_lil = A_csr.tolil()
    for ri in masked:
        A_lil[ri, ri] = 1.0
    b[masked] = val_flat[masked]

    return A_lil.tocsr(), b


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
    converged = residual < tol * (1 + np.linalg.norm(b_red))
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
) -> LaplaceResult:
    """Top-level Laplace solve dispatcher.

    Parameters
    ----------
    method
        ``"sor"``, ``"amg"``, or ``"auto"``. Auto picks AMG for grids
        with ≥ 250_000 free pixels, SOR otherwise.
    """
    n_free = int((~v_mask).sum())
    chosen = method
    if method == "auto":
        chosen = "amg" if n_free >= 250_000 else "sor"

    if chosen == "amg":
        return solve_amg(er, v_mask, v_value, tol=tol, max_iter=max_iter or 200)
    return solve_sor(
        er, v_mask, v_value,
        initial=initial, omega=omega,
        max_iter=max_iter or 50_000, tol=tol, float_groups=float_groups,
    )


__all__ = ["LaplaceResult", "solve_amg", "solve_laplace", "solve_sor"]
