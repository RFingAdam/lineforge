"""Graded-mesh electrostatic solver with bounded memory.

The uniform-grid path in :mod:`lineforge.solvers.cgp` approximates an open
boundary by padding the usermap with *uniform* pixels out to ~16x its size.
For a realistic PCB cross-section rasterized at a few microns per pixel that
is a million-cell grid, and the charge-shift predictor that seeds the
relaxation is quadratic in the conductor surface, so a 5 um microstrip took
minutes and a 12 um one could run for over ten minutes.

This module keeps the usermap's own pixels as-is and grows the padding cells
geometrically instead (``px, px*g, px*g^2, ...``), so the far boundary sits
tens of cross-section widths away for a few dozen extra rows and columns.
The cell-centred finite-volume system it builds is assembled straight into a
sparse matrix (never a dense one) and solved with a sparse direct
factorisation, or with smoothed-aggregation AMG + CG when the system is
large. Memory is O(cells) and a hard cell budget refuses or coarsens inputs
that would not fit.

Discretisation
--------------
Unknowns live at cell centres. Between two neighbouring cells the flux
conductance is the series combination of the two half cells,

    g = l_face / (d_a / (2 eps_a) + d_b / (2 eps_b))

which is exact for a dielectric interface normal to the flux. A conductor
cell is an equipotential, so its half cell contributes no resistance and the
conductor surface lies on the cell boundary. A floating conductor is a single
shared unknown, which enforces zero net charge exactly. The outer boundary is
V = 0 on the far face of the last padding cell.

Outputs
-------
* ``C`` and ``Gp`` from the discrete field energy (the same
  ``C = eps0/V^2 * integral(eps_r |E|^2)`` convention as
  :func:`lineforge.solvers.cgp.solve_cgp`).
* The conductor surface charge per boundary face, which
  :func:`lineforge.solvers.lrs.solve_full` turns into the surface-current
  distribution of the TEM mode for the perturbational (Wheeler incremental
  inductance) conductor-loss calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from lineforge.analytical._constants import EPS0
from lineforge.geometry.usermap import Usermap, UsermapMetadata

DEFAULT_MAX_CELLS = 1_500_000
"""Default ceiling on the number of mesh cells (bitmap + padding).

At this size the sparse system, its AMG hierarchy and the field arrays stay
well under 1 GB.
"""

_DIRECT_SOLVE_LIMIT = 250_000
"""Unknown count above which the solver switches from SuperLU to AMG + CG."""


class MeshBudgetExceeded(ValueError):  # noqa: N818  public solver API name
    """The graded mesh would exceed the configured cell budget."""


@dataclass
class GradedMesh:
    """A tensor-product mesh: the usermap's pixels plus graded padding."""

    dx: np.ndarray
    """Column widths [m], shape (nx,)."""
    dy: np.ndarray
    """Row heights [m], shape (ny,)."""
    er: np.ndarray
    """Relative permittivity per cell (1.0 inside conductors), shape (ny, nx)."""
    tan_delta: np.ndarray
    """Loss tangent per cell, shape (ny, nx)."""
    cond: np.ndarray
    """Conductor label per cell: -1 dielectric, 0 ground, 1 (+1), 2 (-1), 3+ floating."""
    rho: np.ndarray
    """Resistivity [ohm m] per cell (only meaningful where ``cond >= 0``)."""
    mu_r: np.ndarray
    """Relative permeability per cell (only meaningful where ``cond >= 0``)."""
    in_bitmap: np.ndarray
    """True for cells that come from the usermap (False for padding)."""
    pixel_width_m: float
    coarsen_factor: int = 1

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.dy), len(self.dx))

    @property
    def n_cells(self) -> int:
        return len(self.dy) * len(self.dx)


@dataclass
class FaceCharges:
    """Surface charge on every conductor boundary face of one solve."""

    q: np.ndarray
    """Charge per unit length on the face [C/m] (outward flux times eps0)."""
    length: np.ndarray
    """Face length [m]."""
    label: np.ndarray
    """Conductor label of the face's conductor cell."""
    rho: np.ndarray
    """Resistivity of the face's conductor cell [ohm m]."""
    mu_r: np.ndarray
    """Relative permeability of the face's conductor cell."""


@dataclass
class GradedSolution:
    """Result of one graded-mesh Laplace solve."""

    v: np.ndarray
    capacitance_per_m: float
    conductance_per_m_over_omega: float
    """``Gp / omega``: multiply by the angular frequency to get Gp [S/m]."""
    v_drive: float
    charges: FaceCharges
    n_unknowns: int
    solver: str
    extras: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mesh construction
# ---------------------------------------------------------------------------


def _graded_steps(px: float, extent: float, growth: float, max_steps: int = 200) -> np.ndarray:
    """Cell sizes px*g, px*g^2, ... until their sum reaches ``extent``."""
    sizes: list[float] = []
    total = 0.0
    s = px
    while total < extent and len(sizes) < max_steps:
        s *= growth
        sizes.append(s)
        total += s
    return np.asarray(sizes, dtype=np.float64)


def _labels_from_usermap(usermap: Usermap) -> np.ndarray:
    """Conductor labels per pixel, consistent with the uniform-grid C/Gp solver."""
    from lineforge.solvers.cgp import _extract_masks

    plus, minus, ground, float_groups = _extract_masks(usermap)
    lab = np.full(usermap.shape, -1, dtype=np.int32)
    lab[ground] = 0
    lab[plus] = 1
    lab[minus] = 2
    for k, grp in enumerate(float_groups):
        lab[grp & (lab < 0)] = 3 + k
    return lab


def coarsen_usermap(usermap: Usermap, factor: int) -> Usermap:
    """Block-downsample a usermap by an integer ``factor``.

    Each ``factor x factor`` block takes the colour of its first conductor
    pixel if it holds any (signal conductors before ground before floating),
    otherwise its centre pixel. Thin conductors therefore survive coarsening
    instead of disappearing between samples.
    """
    if factor <= 1:
        return usermap
    h, w = usermap.shape
    nh, nw = -(-h // factor), -(-w // factor)
    pad_h, pad_w = nh * factor - h, nw * factor - w
    lab = _labels_from_usermap(usermap)
    rgb = np.pad(usermap.rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
    lab = np.pad(lab, ((0, pad_h), (0, pad_w)), mode="edge")
    # Priority: +1 / -1 first, then ground, then floating, then dielectric.
    prio = np.where(lab == 1, 4, np.where(lab == 2, 4, np.where(lab == 0, 3, 0)))
    prio = np.where(lab >= 3, 2, prio)
    blocks_p = prio.reshape(nh, factor, nw, factor).transpose(0, 2, 1, 3).reshape(nh, nw, -1)
    blocks_rgb = rgb.reshape(nh, factor, nw, factor, 3).transpose(0, 2, 1, 3, 4)
    blocks_rgb = blocks_rgb.reshape(nh, nw, -1, 3)
    centre = (factor // 2) * factor + factor // 2
    best = np.argmax(blocks_p, axis=2)
    has_cond = np.take_along_axis(blocks_p, best[..., None], axis=2)[..., 0] > 0
    pick = np.where(has_cond, best, centre)
    new_rgb = np.take_along_axis(blocks_rgb, pick[..., None, None], axis=2)[:, :, 0, :]
    return Usermap(
        np.ascontiguousarray(new_rgb),
        UsermapMetadata(
            pixel_width_m=usermap.pixel_width_m * factor,
            name=f"{usermap.meta.name} (coarsened x{factor})",
            source=usermap.meta.source,
            notes=usermap.meta.notes,
        ),
        material_lookup=usermap.material_lookup,
        unknown_warning=False,
    )


def build_mesh(
    usermap: Usermap,
    *,
    open_boundary: bool = True,
    pad_factor: float = 25.0,
    growth: float = 1.3,
    max_cells: int = DEFAULT_MAX_CELLS,
    auto_coarsen: bool = True,
) -> GradedMesh:
    """Wrap a usermap in geometrically graded open-boundary padding.

    Parameters
    ----------
    usermap
        Cross-section bitmap.
    open_boundary
        Add graded padding (edge-replicated materials) out to ``pad_factor``
        times the bitmap's larger side on every edge. With ``False`` the
        bitmap's own edge is the V = 0 boundary (shielded geometries).
    pad_factor
        Padding extent per side, in units of the bitmap's larger side.
    growth
        Geometric growth ratio of successive padding cells.
    max_cells
        Cell budget for the whole mesh.
    auto_coarsen
        When the bitmap alone would break the budget, block-downsample it by
        the smallest integer factor that fits instead of raising.

    Raises
    ------
    MeshBudgetExceeded
        If the mesh does not fit in ``max_cells`` and ``auto_coarsen`` is off.
    """
    factor = 1
    work = usermap
    while True:
        h, w = work.shape
        px = work.pixel_width_m
        steps = (
            _graded_steps(px, pad_factor * max(h, w) * px, growth) if open_boundary else np.zeros(0)
        )
        n = len(steps)
        n_cells = (h + 2 * n) * (w + 2 * n)
        if n_cells <= max_cells:
            break
        if not auto_coarsen:
            raise MeshBudgetExceeded(
                f"graded mesh would need {n_cells:,} cells ({h}x{w} bitmap + padding) "
                f"but the budget is {max_cells:,}. Use a coarser pixel_width, crop the "
                "usermap, or pass auto_coarsen=True."
            )
        factor += 1
        work = coarsen_usermap(usermap, factor)
        if min(work.shape) < 4:
            raise MeshBudgetExceeded(
                f"usermap {usermap.shape} cannot be coarsened to fit {max_cells:,} cells"
            )

    lab = _labels_from_usermap(work)
    er = work.er_field()
    tan = work.tan_delta_field()
    rho = work.resistivity_field_ohm_m()
    mu = np.ones(work.shape, dtype=np.float64)
    for idx, mat in enumerate(work.materials):
        mu[work.codes == idx] = mat.mu_r
    er = np.where(lab >= 0, 1.0, er)
    tan = np.where(lab >= 0, 0.0, tan)
    inside = np.ones(work.shape, dtype=bool)

    if n:
        pads = ((n, n), (n, n))
        er = np.pad(er, pads, mode="edge")
        tan = np.pad(tan, pads, mode="edge")
        lab = np.pad(lab, pads, mode="edge")
        rho = np.pad(rho, pads, mode="edge")
        mu = np.pad(mu, pads, mode="edge")
        inside = np.pad(inside, pads, mode="constant", constant_values=False)
        dx = np.concatenate([steps[::-1], np.full(w, px), steps])
        dy = np.concatenate([steps[::-1], np.full(h, px), steps])
    else:
        dx = np.full(w, px)
        dy = np.full(h, px)

    return GradedMesh(
        dx=dx,
        dy=dy,
        er=er,
        tan_delta=tan,
        cond=lab,
        rho=rho,
        mu_r=mu,
        in_bitmap=inside,
        pixel_width_m=px,
        coarsen_factor=factor,
    )


# ---------------------------------------------------------------------------
# Solve
# ---------------------------------------------------------------------------


def _faces(mesh: GradedMesh, er: np.ndarray) -> list[tuple[np.ndarray, ...]]:
    """Interior faces as (flat_a, flat_b, g, ra, rb, length) per direction.

    ``ra``/``rb`` are the half-cell resistances per unit face length times the
    face length, i.e. ``g = 1 / (ra + rb)``.
    """
    ny, nx = mesh.shape
    idx = np.arange(ny * nx).reshape(ny, nx)
    cond = mesh.cond >= 0
    out: list[tuple[np.ndarray, ...]] = []
    # Horizontal neighbours (face normal along x, face length dy).
    hx = np.where(cond, 0.0, mesh.dx[None, :] / (2.0 * er)) / mesh.dy[:, None]
    ra, rb = hx[:, :-1], hx[:, 1:]
    a, b = idx[:, :-1], idx[:, 1:]
    length = np.broadcast_to(mesh.dy[:, None], ra.shape)
    out.append((a, b, ra, rb, length))
    # Vertical neighbours (face normal along y, face length dx).
    hy = np.where(cond, 0.0, mesh.dy[:, None] / (2.0 * er)) / mesh.dx[None, :]
    ra, rb = hy[:-1, :], hy[1:, :]
    a, b = idx[:-1, :], idx[1:, :]
    length = np.broadcast_to(mesh.dx[None, :], ra.shape)
    out.append((a, b, ra, rb, length))
    return out


def solve_mesh(
    mesh: GradedMesh,
    *,
    vacuum: bool = False,
    tol: float = 1e-10,
) -> GradedSolution:
    """Solve div(eps grad V) = 0 on the graded mesh with the usermap's drive.

    Ground (label 0) is held at 0 V, the +1 conductor at +1 V and the -1
    conductor at -1 V; floating conductors are free equipotentials.
    """
    ny, nx = mesh.shape
    n = ny * nx
    er = np.ones_like(mesh.er) if vacuum else mesh.er
    lab = mesh.cond.ravel()
    fixed = (lab >= 0) & (lab <= 2)
    vfix = np.where(lab == 1, 1.0, np.where(lab == 2, -1.0, 0.0))
    if not (lab == 1).any():
        raise ValueError("graded solve needs a +1 conductor")
    v_drive = 2.0 if (lab == 2).any() else 1.0

    # Unknown numbering: one per free dielectric cell, one per floating group.
    node = np.full(n, -1, dtype=np.int64)
    free = lab < 0
    n_free = int(free.sum())
    node[free] = np.arange(n_free)
    float_labels = np.unique(lab[lab >= 3])
    for k, fl in enumerate(float_labels):
        node[lab == fl] = n_free + k
    n_unk = n_free + len(float_labels)

    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    rhs = np.zeros(n_unk, dtype=np.float64)
    diag = np.zeros(n_unk, dtype=np.float64)
    face_data = []

    for a2, b2, ra2, rb2, len2 in _faces(mesh, er):
        a = a2.ravel()
        b = b2.ravel()
        ra = ra2.ravel()
        rb = rb2.ravel()
        rsum = ra + rb
        ok = rsum > 0  # both-conductor faces carry no field energy
        a, b, ra, rb, rsum = a[ok], b[ok], ra[ok], rb[ok], rsum[ok]
        length = np.ascontiguousarray(len2).ravel()[ok]
        g = 1.0 / rsum
        na, nb = node[a], node[b]
        # Faces inside one floating group are internal.
        same = (na >= 0) & (na == nb)
        keep = ~same
        a, b, ra, rb, g, na, nb, length = (
            a[keep],
            b[keep],
            ra[keep],
            rb[keep],
            g[keep],
            na[keep],
            nb[keep],
            length[keep],
        )
        face_data.append((a, b, ra, rb, g, length))
        ua, ub = na >= 0, nb >= 0
        np.add.at(diag, na[ua], g[ua])
        np.add.at(diag, nb[ub], g[ub])
        both = ua & ub
        rows += [na[both], nb[both]]
        cols += [nb[both], na[both]]
        vals += [-g[both], -g[both]]
        # Unknown next to a fixed conductor: move the known potential to the RHS.
        af = ua & ~ub & fixed[b]
        np.add.at(rhs, na[af], g[af] * vfix[b[af]])
        bf = ub & ~ua & fixed[a]
        np.add.at(rhs, nb[bf], g[bf] * vfix[a[bf]])

    # Outer boundary faces to V = 0 (the far side of the last cell).
    cond2 = mesh.cond >= 0
    idx = np.arange(n).reshape(ny, nx)
    bnd: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    for sl, half, length in (
        ((slice(None), 0), mesh.dx[0] / 2.0, mesh.dy),
        ((slice(None), -1), mesh.dx[-1] / 2.0, mesh.dy),
        ((0, slice(None)), mesh.dy[0] / 2.0, mesh.dx),
        ((-1, slice(None)), mesh.dy[-1] / 2.0, mesh.dx),
    ):
        cells = idx[sl]
        diel = ~cond2[sl]
        r = np.where(diel, half / er[sl], 0.0) / length
        gb = np.where(r > 0, 1.0 / np.where(r > 0, r, 1.0), 0.0)
        sel = (gb > 0) & (node[cells] >= 0)
        np.add.at(diag, node[cells[sel]], gb[sel])
        bnd.append((cells[sel], r[sel], gb[sel]))

    rows.append(np.arange(n_unk))
    cols.append(np.arange(n_unk))
    vals.append(diag)
    A = sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n_unk, n_unk),
    )

    if n_unk <= _DIRECT_SOLVE_LIMIT:
        x = spla.splu(A.tocsc(), permc_spec="MMD_AT_PLUS_A").solve(rhs)
        solver = "superlu"
    else:
        import pyamg

        ml = pyamg.smoothed_aggregation_solver(A, symmetry="symmetric")
        x = ml.solve(rhs, tol=tol, accel="cg", maxiter=500)
        solver = "amg-cg"
    if not np.all(np.isfinite(x)):
        raise RuntimeError("graded Laplace solve returned non-finite potentials")

    v = np.where(node >= 0, x[np.maximum(node, 0)], vfix)

    energy = 0.0
    loss = 0.0
    tan = mesh.tan_delta.ravel()
    q_list, len_list, lab_list, rho_list, mu_list = [], [], [], [], []
    rho = mesh.rho.ravel()
    mu = mesh.mu_r.ravel()
    for a, b, ra, rb, g, length in face_data:
        dv = v[a] - v[b]
        flux = g * dv  # eps_r-weighted flux per unit length, a -> b
        energy += float(np.sum(flux * dv))
        if not vacuum:
            loss += float(np.sum(flux * flux * (ra * tan[a] + rb * tan[b])))
        # Conductor boundary faces: exactly one side is a conductor.
        ca = lab[a] >= 0
        cb = lab[b] >= 0
        for side_cond, cell, sign in ((ca & ~cb, a, 1.0), (cb & ~ca, b, -1.0)):
            if not side_cond.any():
                continue
            q_list.append(EPS0 * sign * flux[side_cond])
            len_list.append(length[side_cond])
            lab_list.append(lab[cell[side_cond]])
            rho_list.append(rho[cell[side_cond]])
            mu_list.append(mu[cell[side_cond]])
    for cells, r, gb in bnd:
        vb = v[cells]
        energy += float(np.sum(gb * vb * vb))
        if not vacuum:
            loss += float(np.sum((gb * vb) ** 2 * r * tan[cells]))

    C = EPS0 * energy / (v_drive * v_drive)
    g_over_omega = EPS0 * loss / (v_drive * v_drive)

    def _cat(parts: list[np.ndarray], dtype: type) -> np.ndarray:
        return np.concatenate(parts).astype(dtype) if parts else np.zeros(0, dtype=dtype)

    charges = FaceCharges(
        q=_cat(q_list, np.float64),
        length=_cat(len_list, np.float64),
        label=_cat(lab_list, np.int32),
        rho=_cat(rho_list, np.float64),
        mu_r=_cat(mu_list, np.float64),
    )
    return GradedSolution(
        v=v.reshape(ny, nx),
        capacitance_per_m=C,
        conductance_per_m_over_omega=g_over_omega,
        v_drive=v_drive,
        charges=charges,
        n_unknowns=n_unk,
        solver=solver,
    )


__all__ = [
    "DEFAULT_MAX_CELLS",
    "FaceCharges",
    "GradedMesh",
    "GradedSolution",
    "MeshBudgetExceeded",
    "build_mesh",
    "coarsen_usermap",
    "solve_mesh",
]
