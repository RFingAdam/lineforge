"""Charge-shift E-prediction for the C/Gp solver.

A method-of-moments-like surface-charge update that produces a fast initial
V-field for the relaxation solver. Per atlc2 docs §"C and Gp":

    "The E field at each surface pixel is found by summing the contributions
    from the charges at all the pixels. The field component normal to the
    surface predicts a new value for the charge at that pixel. About 20
    iterations seems to work well."

This is a 2D potential-theory iteration:
    σ_i^{k+1} = σ_i^{k} + α · (E_target - E_normal_i^{k})

where E from a unit line charge at distance r in 2D is E ∝ 1/r along the
direction to the source. The total E at a surface pixel is the superposition
over all charge pixels.

For Phase 2 simplicity (and because this is just an *initial guess* for the
relaxation), we implement a vectorized but unoptimized version: O(N²) per
iteration, where N is the number of conductor surface pixels. For typical
usermaps (a few thousand surface pixels) this completes in a few seconds.

The output is a V-field that the relaxation solver picks up and refines. The
"Skip E prediction" flag (matching atlc2's checkbox) lets users bypass this
step if it's slower than just letting relaxation work directly.
"""

from __future__ import annotations

import numpy as np


def _surface_pixels(mask: np.ndarray) -> np.ndarray:
    """Return a boolean mask of *surface* pixels: conductor pixels with at least
    one non-conductor neighbor."""
    if not mask.any():
        return np.zeros_like(mask)
    nE = np.zeros_like(mask)
    nE[:, :-1] = mask[:, 1:]
    nW = np.zeros_like(mask)
    nW[:, 1:] = mask[:, :-1]
    nN = np.zeros_like(mask)
    nN[1:, :] = mask[:-1, :]
    nS = np.zeros_like(mask)
    nS[:-1, :] = mask[1:, :]
    interior_only = nE & nW & nN & nS
    surface: np.ndarray = mask & ~interior_only
    return surface


def predict_v_field(
    er: np.ndarray,
    plus_mask: np.ndarray,
    minus_mask: np.ndarray,
    ground_mask: np.ndarray,
    *,
    iterations: int = 20,
    relaxation: float = 0.5,
) -> np.ndarray:
    """Estimate the V field by surface-charge moment matching.

    Parameters
    ----------
    er
        Per-pixel relative permittivity.
    plus_mask, minus_mask, ground_mask
        Boolean masks for V=+1, V=-1, V=0 conductor pixels.
    iterations
        How many charge-update sweeps. ~20 matches atlc2.
    relaxation
        Per-iteration σ update factor in (0, 1].

    Returns
    -------
    V field, shape ``(H, W)``. Use as the ``initial`` argument to
    :func:`lineforge.solvers.laplace.solve_sor` or `solve_amg`.
    """
    h, w = er.shape
    plus_surface = _surface_pixels(plus_mask)
    minus_surface = _surface_pixels(minus_mask)
    ground_surface = _surface_pixels(ground_mask)
    surface_mask = plus_surface | minus_surface | ground_surface

    if not surface_mask.any():
        # No conductors: return zero field
        return np.zeros((h, w), dtype=np.float64)

    # Get coordinates of every surface pixel
    ys, xs = np.where(surface_mask)
    target_v = np.where(plus_surface[ys, xs], 1.0, np.where(minus_surface[ys, xs], -1.0, 0.0))

    n = len(ys)
    if n == 0:
        return np.zeros((h, w), dtype=np.float64)

    # 2D Green's function for line charge: V(r) = -(1/2π) ln(r/r0)
    # We work in pixel units; r0 is just an additive constant absorbed into
    # the linear system.
    yi = ys[:, None]
    xi = xs[:, None]
    yj = ys[None, :]
    xj = xs[None, :]
    dy = yi - yj
    dx = xi - xj
    r2 = dy * dy + dx * dx
    # Avoid log(0) on the diagonal (self-term); use the pixel-self-potential
    # approximation: ln(0.5) for a unit-square pixel.
    r2 = np.where(r2 == 0, 0.5 * 0.5, r2)
    # Influence matrix: V_i contribution from σ_j (omitted constant out front)
    G = -0.5 * np.log(r2)

    # We want G @ σ = target_v (for unit-line-charge model), but only up to
    # an additive constant per *isolated conductor*. For unshielded lines this
    # is fine; for shielded the constant is fixed by ground.
    # Use a damped iterative solve so we don't need to invert G:
    #   σ_{k+1} = σ_k + relaxation * (G^T (target_v - G σ_k)) / max(diag(G^T G))
    # but for simplicity solve the symmetric system directly:
    try:
        sigma, *_ = np.linalg.lstsq(G, target_v, rcond=None)
    except np.linalg.LinAlgError:
        # Diverged: return zeros and let relaxation do all the work
        return np.zeros((h, w), dtype=np.float64)

    # Loop-invariant scaling factor: hoisted out of the refinement loop so
    # we don't recompute (G @ G.T) on every iteration.
    refine_denom = max(1.0, float(np.diag(G @ G.T).max()))

    # Apply ``iterations`` of damped refinement (capture the docstring contract)
    for _ in range(max(0, iterations - 1)):
        residual = target_v - G @ sigma
        if np.max(np.abs(residual)) < 1e-9:
            break
        sigma = sigma + relaxation * residual / refine_denom

    # Compute V at every grid pixel from the σ distribution. The naïve form is
    # ``G_full = -0.5 * log(r2)`` with shape ``(h*w, n_surface)``, but that
    # tries to allocate ~ 8 · h · w · n_surface bytes: 256+ GiB for extended-
    # boundary grids (issue #32). Stream the same computation in pixel-chunks
    # so the working-set stays bounded regardless of grid size.
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    yy_flat = yy.ravel()
    xx_flat = xx.ravel()

    v_flat = np.zeros(h * w, dtype=np.float64)
    # Target ~64 MB temp working set per chunk.
    max_block_bytes = 64 * 1024 * 1024
    bytes_per_pixel = 8 * n
    chunk_pixels = max(1024, max_block_bytes // bytes_per_pixel)

    ys_row = ys[None, :]
    xs_row = xs[None, :]
    for start in range(0, h * w, chunk_pixels):
        end = min(start + chunk_pixels, h * w)
        dy_blk = yy_flat[start:end, None] - ys_row
        dx_blk = xx_flat[start:end, None] - xs_row
        r2_blk = dy_blk * dy_blk + dx_blk * dx_blk
        r2_blk = np.where(r2_blk == 0, 0.25, r2_blk)
        v_flat[start:end] = (-0.5 * np.log(r2_blk)) @ sigma

    v_field = v_flat.reshape(h, w)

    # Clamp to BC-respecting bounds (numerical safety)
    v_field_clamped: np.ndarray = np.clip(v_field, -1.5, 1.5)
    return v_field_clamped


__all__ = ["predict_v_field"]
