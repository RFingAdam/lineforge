"""Faraday's-law solver for L and Rs of a 2D transmission line cross-section.

We solve a 2D PEEC-style impedance system. Each conductor pixel carries an
unknown current ``i_n`` (out-of-plane). For a longitudinal ``E_z`` driving
the line, Ohm's law per pixel + the loop EMF balance gives:

    V_c = (R_n + jωL_partial) · i_n
        = (ρ_n / A_pixel) · i_n + jω · (μ₀/(2π)) · Σ_k ln(d_ref / r_nk) · i_k

where:
    - ``V_c`` is the per-conductor (constant) longitudinal voltage drop.
    - ``ρ_n`` is the resistivity of pixel n (in Ω·m).
    - ``A_pixel = px²`` is the pixel area.
    - ``r_nk`` is the center-to-center distance between pixels n and k (with
      a self-pixel cap of ~0.5·px to avoid the singularity).
    - ``d_ref`` is a reference distance: choose it so the reciprocal magnitudes
      look natural (we use the simulation extent).

Constraints: one per conductor:
    For each conductor c (the +1 and the −1 conductor for a 2-wire line),
    either fix V_c (voltage drive) or fix Σ_{n∈c} i_n (current drive).

We use **current drive**: I_+1 = +1 A, I_−1 = −1 A. The unknowns are
``[i_1, …, i_N, V_+1, V_−1, V_ground?]`` and we form a square system:
    - N rows of Ohm's law
    - n_c rows of Σ i_n = ±1 (or 0 for ground)

Solve Z·x = b → extract V_+1 − V_−1 → R_per_m + jω·L_per_m = (V_+1 − V_−1)/I.

For large systems the ``L_partial`` block is dense; we keep it dense in NumPy
for now (acceptable up to ~5000 pixels). The diagonal R block is sparse, but
the dominant cost is the dense matrix-vector multiply in the Krylov solver.
For Phase 3 acceptance this is fine; the Phase 4 polish converts to a
hierarchical / FFT-based fast multipole method for massive systems.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from lineforge.analytical._constants import MU0
from lineforge.cache import cached
from lineforge.geometry.usermap import Usermap


@dataclass
class FaradayResult:
    """Output of a Faraday solve at a single frequency."""

    L_per_m: float
    R_per_m: float
    z0_complex: complex
    frequency_hz: float
    n_conductor_pixels: int
    rs_low_confidence: bool
    rs_warning: str | None


def _conductor_pixel_indices(usermap: Usermap) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Return (ys, xs, conductor_id_per_pixel) for all conductor pixels.

    ``conductor_id_per_pixel`` is an int array with:
        0 → +1 conductor
        1 → −1 conductor  (or absent if no -1 pixels)
        2 → ground (V=0) conductor
        3+ → each floating group
    """
    plus = usermap.conductor_mask("+1")
    minus = usermap.conductor_mask("-1")
    ground = usermap.conductor_mask("0")

    cid = np.full(usermap.shape, -1, dtype=np.int32)
    next_id = 0
    label_map: dict[str, int] = {}

    if plus.any():
        cid[plus] = next_id
        label_map["+1"] = next_id
        next_id += 1
    if minus.any():
        cid[minus] = next_id
        label_map["-1"] = next_id
        next_id += 1
    if ground.any():
        cid[ground] = next_id
        label_map["0"] = next_id
        next_id += 1
    # Floating: each material group is its own conductor
    for idx, mat in enumerate(usermap.materials):
        if mat.use == "float":
            sel = usermap.codes == idx
            if sel.any():
                cid[sel] = next_id
                label_map[f"float-{idx}"] = next_id
                next_id += 1

    ys, xs = np.where(cid >= 0)
    return ys, xs, label_map


def _self_inductance_per_m(px: float) -> float:
    """Approximate self-inductance per unit length of a single square pixel.

    For a square cross-section of side a, the self-partial inductance is
    L_self ≈ (μ₀/(2π)) · (ln(2/a_eff) + 0.5) where a_eff scales with the
    geometry; for a square of side a, a common approximation is
    L_self_per_m ≈ (μ₀/(2π)) · (3/2 - ln(a)).

    We use the simpler:
        L_self_per_m ≈ (μ₀/(2π)) · (ln(1/a) + 0.5)

    This produces correct DC inductance for a coax to within a few percent,
    which is acceptable for Phase 3. The off-diagonal terms dominate the
    answer for any non-trivial geometry.
    """
    return float((MU0 / (2.0 * np.pi)) * (np.log(1.0 / max(px, 1e-12)) + 0.5))


def _partial_inductance(
    ys: np.ndarray, xs: np.ndarray, field_shape: tuple[int, ...], px: float
) -> np.ndarray:
    """Dense pairwise partial-inductance matrix ``(μ₀/2π)·ln(d_ref/r_nk)`` in H/m.

    ``d_ref`` is the simulation extent so the logs stay positive; the self term
    is capped at half a pixel and then replaced by :func:`_self_inductance_per_m`.
    """
    h, w = field_shape[0], field_shape[1]
    d_ref = float(max(h, w)) * px

    yy = ys[:, None].astype(np.float64) * px
    xx = xs[:, None].astype(np.float64) * px
    yy_t = yy.T
    xx_t = xx.T
    r2 = (yy - yy_t) ** 2 + (xx - xx_t) ** 2
    np.fill_diagonal(r2, (px * 0.5) ** 2)
    L_partial = (MU0 / (2.0 * np.pi)) * np.log(d_ref / np.sqrt(r2))
    np.fill_diagonal(L_partial, _self_inductance_per_m(px))
    return L_partial


def _assemble_impedance(
    ys: np.ndarray,
    xs: np.ndarray,
    pixel_col: np.ndarray,
    rho_field: np.ndarray,
    px: float,
    omega: float,
    n_conductors: int,
) -> np.ndarray:
    """Assemble the square PEEC matrix shared by the single- and multi-drive solvers.

    ``pixel_col[n]`` is the *column offset* of the conductor that pixel n belongs
    to, i.e. its voltage unknown lives at index ``N + pixel_col[n]``. Rows
    ``0..N-1`` are Ohm's law, rows ``N..N+n_conductors-1`` are ``Σ i_n = I_c``.
    """
    N = len(ys)
    if N == 0:
        raise ValueError("no conductor pixels in usermap")

    Z = np.zeros((N + n_conductors, N + n_conductors), dtype=np.complex128)

    # ---- R diagonal -------------------------------------------------------
    R_diag = rho_field[ys, xs] / (px * px)  # Ω/m per pixel

    # ---- Top-left block: R_diag + jω·L_partial -----------------------------
    Z[:N, :N] = 1j * omega * _partial_inductance(ys, xs, rho_field.shape, px)
    np.fill_diagonal(Z[:N, :N], np.diag(Z[:N, :N]) + R_diag)

    # Voltage columns: each pixel n in conductor c subtracts V_c from its row
    # so the equation is: Σ_k Z[n,k]·i_k − V_{c(n)} = 0
    Z[np.arange(N), N + pixel_col] = -1.0

    # Constraint rows: Σ_{n in c} i_n = I_drive[c]
    for c in range(n_conductors):
        Z[N + c, np.where(pixel_col == c)[0]] = 1.0

    return Z


def _build_system(
    ys: np.ndarray,
    xs: np.ndarray,
    cid: np.ndarray,
    rho_field: np.ndarray,
    px: float,
    omega: float,
    n_conductors: int,
    drive_currents: dict[int, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Assemble the dense complex impedance system.

    Returns (Z, b) such that solving Z·x = b yields::
        x = [i_1, …, i_N, V_c0, V_c1, …]
    where each V_ck is the longitudinal voltage drop on conductor k.

    The system size is (N + n_conductors) × (N + n_conductors).

    For `drive_currents`, pass a dict ``{conductor_id: I_total}``. For 2-wire,
    pass ``{0: +1.0, 1: -1.0}``. Ground (V=0) gets fixed at V=0 and contributes
    no row equation; instead we add a row "V_ground = 0" via a row eliminating
    its column.
    """
    N = len(ys)
    pixel_cid = cid[ys, xs]  # int per pixel
    Z = _assemble_impedance(ys, xs, pixel_cid, rho_field, px, omega, n_conductors)

    b = np.zeros(N + n_conductors, dtype=np.complex128)
    for c in range(n_conductors):
        b[N + c] = drive_currents.get(c, 0.0)

    return Z, b


def _solve_dense(Z: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Direct dense complex solve via numpy."""
    return np.linalg.solve(Z, b)


def _solve_bicgstab_with_ilu(Z: np.ndarray, b: np.ndarray, tol: float = 1e-8) -> np.ndarray:
    """BiCGSTAB with ILU(0) preconditioner via SciPy. Falls back to dense if Z is small."""
    n = Z.shape[0]
    if n < 500:
        return _solve_dense(Z, b)
    Z_sp = sp.csr_matrix(Z)
    try:
        ilu = spla.spilu(Z_sp, fill_factor=10, drop_tol=1e-4)
        M = spla.LinearOperator((n, n), matvec=ilu.solve)
    except Exception:
        M = None
    x, info = spla.bicgstab(Z_sp, b, M=M, rtol=tol, atol=tol, maxiter=500)
    if info != 0:
        # Fall back to dense
        return _solve_dense(Z, b)
    x_arr: np.ndarray = np.asarray(x)
    return x_arr


def _check_rs_geometry(
    usermap: Usermap,
    ys: np.ndarray,
    xs: np.ndarray,
    frequency_hz: float = 0.0,
) -> tuple[bool, str | None]:
    """Detect Rs-accuracy hazards.

    Two independent triggers, either of which sets ``rs_low_confidence``:

    1. **Conductor separation**: per atlc2 §"Getting an accurate Rs": a corner
       pixel must be ≥ 16 pixels from another corner pixel of different voltage,
       or ≥ 8 pixels from a flat or curved surface of different voltage. If
       violated, Rs is flagged (atlc2 prints in red).
    2. **Skin-depth resolution**: for the AC skin-effect formula
       ``R_s = 1/(σ·δ·P)`` to be reproduced to ±1%, the grid must resolve δ
       with at least ~30 pixels. When the smallest conductor material has
       ``δ / pixel_width < 30`` the bitmap solver under-resolves the surface
       current density and Rs accuracy degrades (≥10% error). Skipped at DC
       (``frequency_hz <= 0``) where the formula isn't applicable.
    """
    plus = usermap.conductor_mask("+1")
    minus = usermap.conductor_mask("-1")

    messages: list[str] = []

    # ----- Conductor separation check -----
    if plus.any() and minus.any():
        from scipy.ndimage import distance_transform_edt

        dist_to_minus = distance_transform_edt(~minus)
        if isinstance(dist_to_minus, tuple):
            dist_to_minus = dist_to_minus[0]
        min_separation = float(np.min(dist_to_minus[plus]))
        if min_separation < 8.0:
            messages.append(
                f"+1 and -1 conductors are only {min_separation:.1f} pixels apart; "
                "Rs accuracy may be > 5% (atlc2 §'Getting an accurate Rs'). "
                "Consider a finer grid (smaller pixel_width)."
            )

    # ----- Skin-depth resolution check -----
    if frequency_hz > 0:
        from lineforge.solvers.skin_depth import compute_delta

        px = usermap.pixel_width_m
        # Find the smallest δ across all conductor materials present in the map.
        min_delta_px: float | None = None
        for idx, mat in enumerate(usermap.materials):
            if not mat.is_conductor:
                continue
            if not (usermap.codes == idx).any():
                continue
            d = compute_delta(mat, frequency_hz)
            d_px = d / px
            if min_delta_px is None or d_px < min_delta_px:
                min_delta_px = d_px
        if min_delta_px is not None and min_delta_px < 30.0:
            messages.append(
                f"skin depth δ resolved by only {min_delta_px:.1f} pixels (< 30); "
                f"AC Rs accuracy may exceed ±10% (target ±1% requires δ ≥ 30·px). "
                "Reduce pixel_width or lower the frequency."
            )

    if messages:
        return True, " | ".join(messages)
    return False, None


@cached("solve_lrs_faraday")
def solve_lrs(
    usermap: Usermap,
    *,
    frequency_hz: float,
    method: str = "auto",
    tol: float = 1e-8,
) -> FaradayResult:
    """Solve for L and Rs at a given frequency via the 2D Faraday/PEEC system.

    Parameters
    ----------
    usermap
        Cross-section bitmap with material assignments.
    frequency_hz
        Frequency for the solve (sets ω, skin-depth-relevant for high f).
    method
        ``"auto"``, ``"dense"``, or ``"bicgstab"``. Auto picks bicgstab for
        N ≥ 500 conductor pixels, dense otherwise.
    tol
        Krylov convergence tolerance.

    Returns
    -------
    FaradayResult
        Frequency-resolved L_per_m and R_per_m. The complex line impedance
        ``z0_complex = √((R + jωL) / (G + jωC))`` is left for the higher-level
        :class:`lineforge.results.RLGCResult` to combine with the C/Gp solve.
    """
    ys_initial, _xs_initial, _label_map = _conductor_pixel_indices(usermap)
    if len(ys_initial) == 0:
        raise ValueError("no conductor pixels in usermap")

    plus = usermap.conductor_mask("+1")
    minus = usermap.conductor_mask("-1")
    if not (plus.any() and minus.any()) and not (plus.any() and usermap.conductor_mask("0").any()):
        raise ValueError("need both +1 and (-1 or 0) conductor pixels for L/Rs solve")

    cid = np.full(usermap.shape, -1, dtype=np.int32)
    next_id = 0
    drive: dict[int, float] = {}
    if plus.any():
        cid[plus] = 0
        drive[0] = +1.0
        next_id = 1
    if minus.any():
        cid[minus] = next_id
        drive[next_id] = -1.0
        next_id += 1
    elif usermap.conductor_mask("0").any():
        cid[usermap.conductor_mask("0")] = next_id
        drive[next_id] = -1.0  # ground carries the return current
        next_id += 1
    if usermap.conductor_mask("0").any() and minus.any():
        cid[usermap.conductor_mask("0")] = next_id
        drive[next_id] = 0.0
        next_id += 1
    n_cond = next_id

    rho_field = usermap.resistivity_field_ohm_m()
    omega = 2.0 * np.pi * frequency_hz
    px = usermap.pixel_width_m

    # Re-extract pixel indices using the (possibly remapped) cid array
    ys, xs = np.where(cid >= 0)
    N = len(ys)

    Z, b = _build_system(ys, xs, cid, rho_field, px, omega, n_cond, drive)

    chosen = method
    if method == "auto":
        chosen = "bicgstab" if Z.shape[0] >= 500 else "dense"

    x = _solve_bicgstab_with_ilu(Z, b, tol=tol) if chosen == "bicgstab" else _solve_dense(Z, b)

    # Extract V values for each conductor
    V_per_conductor = x[N:]
    V_plus = V_per_conductor[0]  # +1 conductor (always cid 0 if plus.any())
    V_minus = V_per_conductor[1]  # -1 (or returning ground)
    delta_V = V_plus - V_minus

    # Z_per_m = (V_+ - V_-) / I_+ ; we drove with +1 A so this is just delta_V
    R_per_m = float(np.real(delta_V))
    L_per_m = float(np.imag(delta_V) / omega)

    rs_warn, rs_msg = _check_rs_geometry(usermap, ys, xs, frequency_hz=frequency_hz)

    return FaradayResult(
        L_per_m=L_per_m,
        R_per_m=R_per_m,
        z0_complex=delta_V,  # only true if you also know G+jωC
        frequency_hz=frequency_hz,
        n_conductor_pixels=N,
        rs_low_confidence=rs_warn,
        rs_warning=rs_msg,
    )


class SolverBudgetExceeded(ValueError):  # noqa: N818  name is part of the public solver API
    """The dense PEEC system would exceed the configured pixel budget."""


def solve_impedance_matrix(
    usermap: Usermap,
    *,
    frequency_hz: float,
    restrict_to_skin_depth: bool = True,
    skin_factor: float = 3.0,
    max_pixels: int = 6000,
    tol: float = 1e-8,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-unit-length R and L matrices for an N-conductor cross-section.

    The usermap must carry ``conductor_ids``: ``0`` for the reference conductor
    and ``1..N`` for the signal conductors (see
    :meth:`lineforge.geometry.usermap.Usermap.from_labels`).

    Drive *j* puts ``+1 A`` on signal conductor *j*, ``-1 A`` on the reference,
    and ``0 A`` on every other signal conductor. Column *j* of the impedance
    matrix is then ``Z[k, j] = V_k − V_ref`` for each signal conductor *k*.
    Because every drive shares one matrix, the dense system is assembled once
    and factored once; the N drives are N right-hand sides of that one LU.

    Parameters
    ----------
    usermap
        Cross-section with ``conductor_ids`` assigned.
    frequency_hz
        Frequency for the solve (sets ω and the skin depth).
    restrict_to_skin_depth
        Blacken conductor interiors deeper than ``skin_factor·δ`` before
        solving (see :func:`lineforge.solvers.skin_depth.mask_skin_depth`).
    skin_factor
        Multiplier on δ for that masking.
    max_pixels
        Refusal threshold on the conductor pixel count *after* masking. The
        dense system is ``(N + n_c)²`` complex entries, so this is the knob
        that keeps a careless call from allocating tens of gigabytes.
    tol
        Accepted for signature compatibility with :func:`solve_lrs`; the
        direct LU path is exact and does not iterate.

    Returns
    -------
    tuple of ndarray
        ``(R, L)``, each ``(N, N)``, in Ω/m and H/m, indexed by signal
        conductor in ascending ``conductor_ids`` order.

    Raises
    ------
    SolverBudgetExceeded
        If the conductor pixel count after masking exceeds ``max_pixels``.
    ValueError
        If there are no conductor pixels, or no reference conductor (id 0).

    Notes
    -----
    Floating conductors (``conductor_ids == -2``) are **excluded**: they are
    dropped from the pixel selection, carry no induced current in the solve,
    and do not appear as a row or column of the returned matrices. This differs
    from :func:`solve_lrs`, which gives every floating material group its own
    conductor and constraint row. For a cross-section with floating metal the
    two routines will therefore not agree.
    """
    del tol  # the LU path is direct; kept for call-site symmetry with solve_lrs

    from scipy.linalg import lu_factor, lu_solve

    from lineforge.solvers.skin_depth import mask_skin_depth

    working = (
        mask_skin_depth(usermap, frequency_hz, factor=skin_factor)
        if restrict_to_skin_depth
        else usermap
    )

    cid_field = working.conductor_ids
    # Only the reference (0) and the signals (1..N). Floating conductors are
    # tagged -2 and are deliberately left out of the system; see Notes above.
    ys, xs = np.where(cid_field >= 0)
    n_pixels = len(ys)
    if n_pixels > max_pixels:
        raise SolverBudgetExceeded(
            f"{n_pixels} conductor pixels exceed the budget of {max_pixels}; "
            "coarsen the grid, enable restrict_to_skin_depth, or raise max_pixels"
        )

    pixel_cid = cid_field[ys, xs]
    ids = [int(c) for c in np.unique(pixel_cid)]  # np.unique already returns them sorted
    signals = [c for c in ids if c >= 1]
    if n_pixels:  # an empty map is _assemble_impedance's error to report
        if 0 not in ids:
            raise ValueError("solve_impedance_matrix needs a reference conductor with id 0")
        if not signals:
            raise ValueError("solve_impedance_matrix needs at least one signal conductor (id >= 1)")

    # Column offset of each conductor's voltage unknown, in ascending id order.
    conductor_index = {c: i for i, c in enumerate(ids)}
    pixel_col = np.array([conductor_index[int(c)] for c in pixel_cid], dtype=np.intp)

    omega = 2.0 * np.pi * frequency_hz
    Z = _assemble_impedance(
        ys,
        xs,
        pixel_col,
        working.resistivity_field_ohm_m(),
        working.pixel_width_m,
        omega,
        len(ids),
    )

    lu_piv = lu_factor(Z)
    ref_col = conductor_index[0]
    n_sig = len(signals)
    rhs = np.zeros((Z.shape[0], n_sig), dtype=np.complex128)
    for j, drive in enumerate(signals):
        rhs[n_pixels + conductor_index[drive], j] = 1.0
        rhs[n_pixels + ref_col, j] = -1.0
    sol = lu_solve(lu_piv, rhs)

    voltages = sol[n_pixels:, :]  # (n_c, n_sig)
    rows = np.array([conductor_index[c] for c in signals], dtype=np.intp)
    zmat = voltages[rows, :] - voltages[ref_col, :][None, :]

    return np.real(zmat), np.imag(zmat) / omega


__all__ = ["FaradayResult", "SolverBudgetExceeded", "solve_impedance_matrix", "solve_lrs"]
