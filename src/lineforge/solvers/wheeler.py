"""Conductor loss by Wheeler's incremental inductance rule on the Maxwell inductance matrix.

``R = (Rs / mu0) dL_ext/dn``, evaluated per conductor by eroding its cross-section by a
pixel and re-solving the vacuum Laplace problem (Wheeler, Proc. IRE 30, 1942; Pozar,
Microwave Engineering, section 2.7). The rule is the high-frequency asymptote: it assumes
the current rides a skin much thinner than the conductor, so that pushing the surface in by
``dn`` reproduces the field the skin effect itself produces. Roughness multiplies each
conductor's own contribution, and the internal inductance is ``L_int = R / omega``, the
other half of the same surface impedance.

The erosion is per conductor id, so every other conductor keeps its pixels; ids are
``0`` (reference), ``1..N`` (signals) and ``-2`` (floating, eroded as one set because the
label carries no group identity).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from lineforge.analytical._constants import EPS0, MU0
from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord, RoughnessSpec
from lineforge.results import SolverWarning
from lineforge.solvers.mtl import MaxwellResult, solve_maxwell
from lineforge.solvers.roughness import roughness_factor
from lineforge.solvers.skin_depth import compute_delta


@dataclass
class WheelerResult:
    """Skin-effect series impedance of an N-conductor cross-section at one frequency.

    ``R_per_m`` and ``L_int_per_m`` are (N, N) matrices over the signal conductors, in
    ohm/m and H/m. ``per_conductor[c]`` is conductor ``c``'s own contribution to ``R``
    *before* its roughness factor is applied, so that
    ``R = sum_c roughness_factors[c] * per_conductor[c]``.
    """

    R_per_m: np.ndarray
    L_int_per_m: np.ndarray
    per_conductor: dict[int, np.ndarray]
    frequency_hz: float
    roughness_factors: dict[int, float]
    warnings: list[SolverWarning] = field(default_factory=list)


def _conductor_ids(usermap: Usermap) -> list[int]:
    """Reference, signals and (as one set) the floating conductors, in a stable order."""
    present = {int(i) for i in np.unique(usermap.conductor_ids)}
    return sorted(i for i in present if i >= 0 or i == -2)


def _conductor_material(usermap: Usermap, conductor_id: int) -> MaterialRecord | None:
    """The conductor material covering most of ``conductor_id``'s pixels."""
    codes = usermap.codes[usermap.conductor_ids == conductor_id]
    codes = codes[codes >= 0]
    if codes.size == 0:
        return None
    best: MaterialRecord | None = None
    best_count = 0
    for idx in (int(c) for c in np.unique(codes)):
        mat = usermap.materials[idx]
        count = int((codes == idx).sum())
        if mat.is_conductor and count > best_count:
            best, best_count = mat, count
    return best


def _thickness_m(mask: np.ndarray, pixel_width_m: float) -> float:
    """Minimum cross-sectional dimension, from the distance transform of the pixel set.

    For a slab ``t`` pixels thick the deepest pixel sits ``(t + 1) / 2`` from the outside,
    so ``2 * d_max - 1`` recovers ``t`` exactly; for other shapes it is the inscribed
    diameter, which is the dimension the skin has to fit inside.
    """
    dist = ndimage.distance_transform_edt(mask)
    if isinstance(dist, tuple):  # pragma: no cover - only when return_indices is set
        dist = dist[0]
    return float(2.0 * dist.max() - 1.0) * pixel_width_m


def _eroded_copy(usermap: Usermap, conductor_id: int, pixels: int) -> Usermap | None:
    """``usermap`` with ``conductor_id``'s pixel set eroded by ``pixels``, or None if it vanishes."""
    mask = usermap.conductor_ids == conductor_id
    eroded = ndimage.binary_erosion(mask, iterations=pixels)
    if not eroded.any():
        return None
    codes = usermap.codes.copy()
    conductor_ids = usermap.conductor_ids.copy()
    removed = mask & ~eroded
    codes[removed] = -1  # vacuum
    conductor_ids[removed] = -1
    return Usermap.from_labels(
        codes,
        list(usermap.materials),
        pixel_width_m=usermap.pixel_width_m,
        conductor_ids=conductor_ids,
        name=f"{usermap.meta.name} (conductor {conductor_id} eroded)",
    )


def _l_ext(result: MaxwellResult) -> np.ndarray:
    l_ext: np.ndarray = MU0 * EPS0 * np.linalg.inv(result.C0)
    return l_ext


def solve_wheeler_resistance(
    usermap: Usermap,
    *,
    frequency_hz: float,
    base: MaxwellResult | None = None,
    method: str = "auto",
    tol: float = 1e-7,
    extend_grid: bool = True,
    roughness: dict[int, RoughnessSpec] | None = None,
    erode_pixels: int = 1,
) -> WheelerResult:
    """Skin-effect ``R`` and ``L_int`` matrices of ``usermap`` at ``frequency_hz``.

    One extra vacuum Maxwell solve per conductor is needed, so the cost is roughly
    ``(1 + n_conductors)`` times :func:`lineforge.solvers.mtl.solve_maxwell`. Pass ``base``
    to reuse an unperturbed solve across a frequency sweep: the geometry derivative
    ``dL_ext/dn`` is frequency independent, only ``Rs(f)`` and the roughness factor are not.

    Parameters
    ----------
    base
        An unperturbed :class:`~lineforge.solvers.mtl.MaxwellResult` for the same map and
        solver settings. Solved here when omitted.
    roughness
        Per conductor id roughness spec; conductors without one are treated as smooth.
    erode_pixels
        Erosion depth in pixels. The recession must stay small against the conductor
        dimensions but large against the discretisation error of a single-pixel step; 1 is
        right for maps whose conductors are several pixels thick.

    Warnings raised on the result:

    - ``conductor_too_thin_for_wheeler``: the conductor vanishes under the erosion, so no
      derivative can be taken and its loss is left out of ``R`` entirely.
    - ``skin_depth_not_small``: the skin depth exceeds a third of the conductor's smallest
      dimension, where the rule's asymptotic assumption no longer holds and ``R`` is an
      underestimate.
    """
    if base is None:
        base = solve_maxwell(usermap, method=method, tol=tol, extend_grid=extend_grid)
    n = len(base.conductor_ids)
    l_base = _l_ext(base)
    px = usermap.pixel_width_m
    step = erode_pixels * px

    specs = roughness or {}
    warnings: list[SolverWarning] = []
    per_conductor: dict[int, np.ndarray] = {}
    factors: dict[int, float] = {}
    total = np.zeros((n, n))

    for c in _conductor_ids(usermap):
        mask = usermap.conductor_ids == c
        material = _conductor_material(usermap, c)
        if material is None:
            continue
        eroded = _eroded_copy(usermap, c, erode_pixels)
        if eroded is None:
            warnings.append(
                SolverWarning(
                    code="conductor_too_thin_for_wheeler",
                    message=(
                        f"conductor {c} vanishes when eroded by {erode_pixels} px, so its "
                        "incremental inductance cannot be taken; its loss is omitted from R"
                    ),
                )
            )
            continue
        delta = compute_delta(material, frequency_hz)
        thickness = _thickness_m(mask, px)
        if delta > thickness / 3.0:
            warnings.append(
                SolverWarning(
                    code="skin_depth_not_small",
                    message=(
                        f"conductor {c}: skin depth {delta:.3g} m exceeds a third of its "
                        f"smallest dimension {thickness:.3g} m; the Wheeler rule is a "
                        "high-frequency asymptote and R is underestimated here"
                    ),
                )
            )
        res_c = solve_maxwell(eroded, method=method, tol=tol, extend_grid=extend_grid)
        # Rs = rho / delta = sqrt(pi f mu rho), taken through compute_delta so that the
        # material's mu_r enters both the skin depth and the surface resistance.
        rs = material.resistivity_ohm_cm * 1e-8 / delta
        contribution = (rs / MU0) * (_l_ext(res_c) - l_base) / step
        spec = specs.get(c)
        k = roughness_factor(spec, delta) if spec is not None else 1.0
        per_conductor[c] = contribution
        factors[c] = k
        total += k * contribution

    omega = 2.0 * np.pi * frequency_hz
    return WheelerResult(
        R_per_m=total,
        L_int_per_m=total / omega,
        per_conductor=per_conductor,
        frequency_hz=frequency_hz,
        roughness_factors=factors,
        warnings=warnings,
    )


__all__ = ["WheelerResult", "solve_wheeler_resistance"]
