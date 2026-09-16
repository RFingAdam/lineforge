"""Conductor loss by Wheeler's incremental inductance rule on the Maxwell inductance matrix.

``R = (Rs / mu0) dL_ext/dn``, evaluated per conductor by eroding its cross-section by a
pixel and re-solving the vacuum Laplace problem (Wheeler, Proc. IRE 30, 1942; Pozar,
Microwave Engineering, section 2.7). The rule is the high-frequency asymptote: it assumes
the current rides a skin much thinner than the conductor, so that pushing the surface in by
``dn`` reproduces the field the skin effect itself produces. Roughness multiplies each
conductor's own contribution.

The erosion is per conductor id, so every other conductor keeps its pixels; ids are
``0`` (reference), ``1..N`` (signals) and ``-2`` (floating, eroded as one set because the
label carries no group identity). Erosion uses ``border_value=1``: a conductor that runs off
the edge of the map, such as a full-width ground plane, continues outside it once
:func:`lineforge.solvers.extension.extend` replicates the border, so its cut edge is not a
surface and must not recede. :func:`_thickness_m` follows the same convention.

Two caveats on the outputs:

- ``L_int = R / omega`` is the reactive half of the same surface impedance, so as written it
  inherits the roughness factor of ``R``. That is an approximation: roughness raises the loss
  more than it raises the stored magnetic energy, so ``L_int`` is overstated for a rough
  conductor. It is exact for the smooth case.
- The wide parallel-plate closed form ``R = 2 Rs / W`` is approached from below as the plates
  widen. Fringing at the plate edges enlarges ``C0`` beyond the parallel-plate value, which
  dilutes ``dL_ext/dn``; the error therefore scales with gap over width, not with the number
  of current-carrying surfaces.
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
    ``R = sum_c roughness_factors[c] * per_conductor[c]``. ``dL_dn[c]`` is the underlying
    frequency-independent geometry derivative in H/m per metre of recession, which can be
    handed back to :func:`solve_wheeler_resistance` to sweep frequency without re-solving.
    """

    R_per_m: np.ndarray
    L_int_per_m: np.ndarray
    per_conductor: dict[int, np.ndarray]
    dL_dn: dict[int, np.ndarray]
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

    ``distance_transform_edt`` measures the distance to the nearest *background pixel of the
    array*, so the edge of the map is never a background and a conductor running off it is
    measured as continuing outside. That is the same convention as the ``border_value=1``
    erosion, and it is what we want: an edge-touching plane is semi-infinite after the
    open-boundary extension replicates the border, so the skin always fits inside it and no
    ``skin_depth_not_small`` warning is due. (Padding the mask with a border of conductor is
    a no-op here for exactly this reason: it adds no background pixel, so no distance
    changes.)
    """
    dist = ndimage.distance_transform_edt(mask)
    if isinstance(dist, tuple):  # pragma: no cover - only when return_indices is set
        dist = dist[0]
    return float(2.0 * dist[mask].max() - 1.0) * pixel_width_m


def _eroded_copy(usermap: Usermap, conductor_id: int, pixels: int) -> Usermap | None:
    """``usermap`` with ``conductor_id``'s pixel set eroded by ``pixels``, or None if it vanishes.

    ``border_value=1`` keeps a conductor that touches the edge of the map intact there: that
    edge is replicated outward by the solver's open-boundary extension, so it is an interior
    cut and not a surface that can recede.
    """
    mask = usermap.conductor_ids == conductor_id
    eroded = ndimage.binary_erosion(mask, iterations=pixels, border_value=1)
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


def _without_ids(usermap: Usermap, conductor_ids: list[int]) -> Usermap:
    """``usermap`` with those conductor labels erased (their pixels keep their material)."""
    labels = usermap.conductor_ids.copy()
    for c in conductor_ids:
        labels[labels == c] = -1
    return Usermap.from_labels(
        usermap.codes.copy(),
        list(usermap.materials),
        pixel_width_m=usermap.pixel_width_m,
        conductor_ids=labels,
        name=f"{usermap.meta.name} (unusable conductor labels dropped)",
    )


def _no_material_warning(conductor_id: int) -> SolverWarning:
    return SolverWarning(
        code="conductor_without_material",
        message=(
            f"conductor {conductor_id} covers no conductor-material pixel, so it has no "
            "resistivity and no skin depth; its loss is omitted from R"
        ),
        severity="error",
    )


def _geometry_derivatives(
    usermap: Usermap,
    base: MaxwellResult,
    *,
    method: str,
    tol: float,
    extend_grid: bool,
    erode_pixels: int,
    warnings: list[SolverWarning],
) -> dict[int, np.ndarray]:
    """``dL_ext/dn`` per conductor id, one eroded vacuum solve each.

    Appends the base solve's warnings and any new warning code raised by an eroded solve to
    ``warnings``, so an ignored floating group or an unlabelled conductor pixel stays visible
    on the Wheeler result instead of being discarded with the intermediate solves.
    """
    warnings.extend(base.warnings)
    seen = {w.code for w in base.warnings}
    l_base = _l_ext(base)
    step = erode_pixels * usermap.pixel_width_m
    derivatives: dict[int, np.ndarray] = {}
    for c in _conductor_ids(usermap):
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
        res_c = solve_maxwell(eroded, method=method, tol=tol, extend_grid=extend_grid)
        for w in res_c.warnings:
            if w.code not in seen:
                seen.add(w.code)
                warnings.append(w)
        derivatives[c] = (_l_ext(res_c) - l_base) / step
    return derivatives


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
    dl_dn: dict[int, np.ndarray] | None = None,
) -> WheelerResult:
    """Skin-effect ``R`` and ``L_int`` matrices of ``usermap`` at ``frequency_hz``.

    One extra vacuum Maxwell solve per conductor is needed, so the cost is roughly
    ``(1 + n_conductors)`` times :func:`lineforge.solvers.mtl.solve_maxwell`. The geometry
    derivative ``dL_ext/dn`` is frequency independent: only ``Rs(f)`` and the roughness factor
    are not. Pass ``dl_dn=<earlier result>.dL_dn`` to sweep frequency with no solve at all, or
    ``base`` to at least reuse the unperturbed solve.

    Parameters
    ----------
    base
        An unperturbed :class:`~lineforge.solvers.mtl.MaxwellResult` for the same map and
        solver settings. Solved here when omitted and ``dl_dn`` is not given.
    roughness
        Per conductor id roughness spec; conductors without one are treated as smooth.
    erode_pixels
        Erosion depth in pixels. The recession must stay small against the conductor
        dimensions but large against the discretisation error of a single-pixel step; 1 is
        right for maps whose conductors are several pixels thick.
    dl_dn
        Geometry derivatives from an earlier call on the same geometry. When given, no Laplace
        solve is run and ``base``, ``method``, ``tol``, ``extend_grid`` and ``erode_pixels``
        are unused.

    Raises
    ------
    ValueError
        When no conductor contributes, that is, every one of them vanished under the erosion
        or had no conductor material. ``R`` is undefined rather than zero in that case.

    Warnings raised on the result:

    - every warning of the base Maxwell solve, plus any code first raised by one of the eroded
      solves;
    - ``conductor_too_thin_for_wheeler``: the conductor vanishes under the erosion, so no
      derivative can be taken and its loss is left out of ``R`` entirely;
    - ``conductor_without_material``: a conductor id covers no conductor-material pixel, so it
      has no loss to compute and its label is dropped for the solves;
    - ``skin_depth_not_small``: the skin depth exceeds a third of the conductor's smallest
      dimension, where the rule's asymptotic assumption no longer holds and ``R`` is an
      underestimate;
    - ``roughness_id_not_in_map``: a ``roughness`` entry names a conductor id the map has no
      pixel of, so that spec had no effect.
    """
    warnings: list[SolverWarning] = []
    specs = roughness or {}
    present = set(_conductor_ids(usermap))
    for c in sorted(specs):
        if c not in present:
            warnings.append(
                SolverWarning(
                    code="roughness_id_not_in_map",
                    message=(
                        f"roughness was given for conductor {c}, which the map has no pixel "
                        "of; that spec had no effect"
                    ),
                )
            )

    # A label on a pixel of no conductor material has no resistivity and no skin depth. Say so
    # and drop the label: leaving it in place would only make the eroded copies unbuildable.
    unusable = [c for c in sorted(present) if _conductor_material(usermap, c) is None]
    if unusable:
        warnings.extend(_no_material_warning(c) for c in unusable)
        usermap = _without_ids(usermap, unusable)

    if dl_dn is not None:
        derivatives = {int(c): np.asarray(d) for c, d in dl_dn.items()}
        if not derivatives:
            raise ValueError("no conductor could be eroded; R is undefined")
        n = int(next(iter(derivatives.values())).shape[0])
    else:
        if base is None:
            base = solve_maxwell(usermap, method=method, tol=tol, extend_grid=extend_grid)
        n = len(base.conductor_ids)
        derivatives = _geometry_derivatives(
            usermap,
            base,
            method=method,
            tol=tol,
            extend_grid=extend_grid,
            erode_pixels=erode_pixels,
            warnings=warnings,
        )

    per_conductor: dict[int, np.ndarray] = {}
    factors: dict[int, float] = {}
    total = np.zeros((n, n))
    for c in sorted(derivatives):
        material = _conductor_material(usermap, c)
        if material is None:
            warnings.append(_no_material_warning(c))
            continue
        delta = compute_delta(material, frequency_hz)
        thickness = _thickness_m(usermap.conductor_ids == c, usermap.pixel_width_m)
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
        # Rs = rho / delta = sqrt(pi f mu rho), taken through compute_delta so that the
        # material's mu_r enters both the skin depth and the surface resistance.
        rs = material.resistivity_ohm_cm * 1e-8 / delta
        contribution = (rs / MU0) * derivatives[c]
        spec = specs.get(c)
        k = roughness_factor(spec, delta) if spec is not None else 1.0
        per_conductor[c] = contribution
        factors[c] = k
        total += k * contribution

    if not per_conductor:
        raise ValueError("no conductor could be eroded; R is undefined")

    omega = 2.0 * np.pi * frequency_hz
    return WheelerResult(
        R_per_m=total,
        L_int_per_m=total / omega,
        per_conductor=per_conductor,
        dL_dn=derivatives,
        frequency_hz=frequency_hz,
        roughness_factors=factors,
        warnings=warnings,
    )


__all__ = ["WheelerResult", "solve_wheeler_resistance"]
