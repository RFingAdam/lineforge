"""Geometry optimizer — find dimensions that hit a target electrical metric.

Wraps :mod:`scipy.optimize` with the atlc3 analytical and numerical solvers.
Common workflows:

    # Find the trace width for 50Ω on 4 mil FR4
    result = atlc3.optimize_for(
        template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
        vary={"W": ("0.5mil", "30mil")},
        target={"z0": 50.0},
    )
    print(result.geometry, result.metric)

    # Two-variable optimization: find (W, S) for 100Ω diff and 50Ω single-ended
    result = atlc3.optimize_for(
        template={"type": "edge_coupled_diff_microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
        vary={"W": ("2mil", "20mil"), "S": ("3mil", "30mil")},
        target={"z_diff": 100.0, "z_odd": 50.0},
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from atlc3.analytical import solve as analytical_solve
from atlc3.geometry import from_dict
from atlc3.units import parse_length


@dataclass
class OptimizeResult:
    """Result of an optimization run."""

    geometry: Any
    metric: dict[str, float]
    iterations: int
    success: bool
    cost: float
    """Final RMS deviation from target."""


def _extract_metric(result: Any, name: str) -> float | None:
    """Get a numeric attribute from a TLineResult / DiffResult / RLGCResult."""
    if hasattr(result, name):
        v = getattr(result, name)
        return float(v) if isinstance(v, (int, float)) else None
    # Tolerate dict-like
    if isinstance(result, dict):
        v = result.get(name)
        return float(v) if isinstance(v, (int, float)) else None
    return None


def _coerce_bound(b: float | str) -> float:
    return parse_length(b) if isinstance(b, str) else float(b)


def optimize_for(
    *,
    template: dict[str, Any],
    vary: dict[str, tuple[float | str, float | str]],
    target: dict[str, float],
    solver: str = "analytical",
    frequency_hz: float | None = None,
    max_iter: int = 100,
) -> OptimizeResult:
    """Find geometry params that hit electrical targets.

    Parameters
    ----------
    template
        Geometry dict with the fixed fields. Must include ``type`` and any
        non-varying dimensions.
    vary
        Mapping ``{field_name: (low, high)}`` of fields to optimize. Bounds
        accept floats (meters) or unit strings.
    target
        Mapping ``{metric_name: target_value}``. The cost function is the
        RMS relative deviation across all targets.
    solver
        ``"analytical"`` (Phase 1, microseconds) or ``"cgp"`` / ``"full"``
        (numerical, slower; use for non-standard geometries).
    frequency_hz
        Frequency for numerical solvers.
    max_iter
        Maximum optimizer iterations.
    """
    fields = list(vary.keys())
    bounds = [(_coerce_bound(lo), _coerce_bound(hi)) for lo, hi in vary.values()]

    if solver != "analytical":
        # Lazy import to avoid circulars and skip-when-unused
        from atlc3.geometry.builders import rasterize
        from atlc3.solvers.cgp import solve_cgp
        from atlc3.solvers.lrs import solve_full as solve_full_rlgc

    def objective(x: np.ndarray) -> float:
        # Build the geometry
        params = dict(template)
        for fld, val in zip(fields, x, strict=True):
            params[fld] = float(val)
        try:
            geom = from_dict(params)
        except (KeyError, ValueError):
            return 1e6  # bad geometry → huge penalty

        try:
            result: Any
            if solver == "analytical":
                result = analytical_solve(geom, frequency_hz=frequency_hz)
            elif solver == "cgp":
                usermap = rasterize(geom)
                result = solve_cgp(usermap, frequency_hz=frequency_hz)
            elif solver == "full":
                if frequency_hz is None:
                    raise ValueError("solver='full' requires frequency_hz")
                usermap = rasterize(geom)
                result = solve_full_rlgc(usermap, frequency_hz=frequency_hz)
            else:
                raise ValueError(f"unknown solver {solver!r}")
        except Exception:
            return 1e6

        # Cost = RMS relative deviation across targets
        sqr_sum = 0.0
        for k, v_target in target.items():
            v_actual = _extract_metric(result, k)
            if v_actual is None:
                return 1e6
            sqr_sum += ((v_actual - v_target) / max(abs(v_target), 1e-12)) ** 2
        return float(np.sqrt(sqr_sum / len(target)))

    if len(fields) == 1:
        lo, hi = bounds[0]
        # xatol scaled to the bound-range — the optimizer should converge to a
        # tiny fraction of the search interval, not the default 1e-5 in absolute
        # SI units which is huge when bounds are in meters (0.1 mil = 2.5 µm).
        xatol = max((hi - lo) * 1e-9, 1e-15)
        scalar_res = minimize_scalar(
            lambda x: objective(np.array([x])),
            bounds=(lo, hi),
            method="bounded",
            options={"maxiter": max_iter, "xatol": xatol},
        )
        x_opt = np.array([scalar_res.x])
        cost = float(scalar_res.fun)
        n_iter = scalar_res.nfev
    else:
        x0 = np.array([(lo + hi) / 2 for lo, hi in bounds])
        res = minimize(
            objective,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": max_iter},
        )
        x_opt = res.x
        cost = float(res.fun)
        n_iter = res.nit

    # Build the final geometry + result
    params = dict(template)
    for fld, val in zip(fields, x_opt, strict=True):
        params[fld] = float(val)
    geom = from_dict(params)

    final: Any
    if solver == "analytical":
        final = analytical_solve(geom, frequency_hz=frequency_hz)
    else:
        from atlc3.geometry.builders import rasterize as _ras
        from atlc3.solvers.cgp import solve_cgp as _cgp

        usermap = _ras(geom)
        final = _cgp(usermap, frequency_hz=frequency_hz)

    metrics: dict[str, float] = {}
    for k in target:
        v = _extract_metric(final, k)
        if v is not None:
            metrics[k] = v

    return OptimizeResult(
        geometry=geom,
        metric=metrics,
        iterations=int(n_iter),
        success=cost < 1e-2,
        cost=cost,
    )


def target_z0(
    template: dict[str, Any],
    *,
    vary: str | dict[str, tuple[float | str, float | str]],
    target_ohms: float,
    solver: str = "analytical",
    frequency_hz: float | None = None,
    max_iter: int = 100,
    bounds: tuple[float | str, float | str] | None = None,
) -> OptimizeResult:
    """Find a single dimension that hits a target characteristic impedance.

    Ergonomic wrapper around :func:`optimize_for` for the most common workflow:
    "what trace width gives me 50 Ω on this stackup?"

    Parameters
    ----------
    template
        Geometry dict with all the fixed fields (type + everything not varying).
    vary
        Either a field name (e.g. ``"W"``) — bounds default to ``("0.1mil", "100mil")``
        or are taken from the optional ``bounds`` argument — or a full ``vary``
        dict like :func:`optimize_for` accepts.
    target_ohms
        Target Z₀ in ohms (e.g. ``50.0``, ``48.0``, ``100.0``).
    solver
        ``"analytical"`` (default), ``"cgp"``, or ``"full"``.
    frequency_hz
        Required for ``solver="full"``; optional otherwise.
    max_iter
        Maximum optimizer iterations.
    bounds
        ``(low, high)`` for the varied field. Only consulted when ``vary`` is a
        bare string. Accepts unit strings.

    Returns
    -------
    OptimizeResult
        ``.geometry`` is the dimensioned geometry; ``.metric["z0"]`` is the
        achieved Z₀; ``.success`` is ``True`` when within 1 % of target.

    Examples
    --------
    Recover the L3 SIG1 W=3.18 mil result from the planning session::

        >>> from atlc3.optimize import target_z0
        >>> r = target_z0(
        ...     template={
        ...         "type": "stripline_asymmetric",
        ...         "T": "0.689mil",
        ...         "H1": "3.5mil",
        ...         "H2": "5.3mil",
        ...         "er": 4.2,
        ...         "er_above": 4.2,
        ...         "er_below": 3.7,
        ...     },
        ...     vary="W",
        ...     target_ohms=48.0,
        ...     bounds=("1mil", "10mil"),
        ... )
        >>> round(r.geometry.W * 39370.1, 2)  # convert m → mil
        3.18
    """
    if isinstance(vary, str):
        if bounds is None:
            bounds = ("0.1mil", "100mil")
        vary_dict: dict[str, tuple[float | str, float | str]] = {vary: bounds}
    else:
        vary_dict = vary

    return optimize_for(
        template=template,
        vary=vary_dict,
        target={"z0": target_ohms},
        solver=solver,
        frequency_hz=frequency_hz,
        max_iter=max_iter,
    )


__all__ = ["OptimizeResult", "optimize_for", "target_z0"]
