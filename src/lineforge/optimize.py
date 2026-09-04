"""Geometry optimizer: find dimensions that hit a target electrical metric.

Wraps :mod:`scipy.optimize` with the lineforge analytical and numerical solvers.
Common workflows:

    # Find the trace width for 50Ω on 4 mil FR4
    result = lineforge.optimize_for(
        template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
        vary={"W": ("0.5mil", "30mil")},
        target={"z0": 50.0},
    )
    print(result.geometry, result.metric)

    # Two-variable optimization: find (W, S) for 100Ω diff and 50Ω single-ended
    result = lineforge.optimize_for(
        template={"type": "edge_coupled_diff_microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
        vary={"W": ("2mil", "20mil"), "S": ("3mil", "30mil")},
        target={"z_diff": 100.0, "z_odd": 50.0},
    )
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from lineforge.analytical import solve as analytical_solve
from lineforge.geometry import from_dict
from lineforge.units import parse_length


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


#: Cost returned for a candidate that could not be evaluated at all -- bad
#: geometry, a solver refusal (e.g. a closed-form validity limit), or a target
#: metric this geometry does not report. Large enough to lose to any real cost.
INFEASIBLE_COST = 1e6


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
        from lineforge.geometry.builders import rasterize
        from lineforge.solvers.cgp import solve_cgp
        from lineforge.solvers.lrs import solve_full as solve_full_rlgc

    # Best *evaluable* candidate seen. Closed-form models have validity limits
    # (a strip can outgrow its cavity), so wide default bounds put a large slab
    # of the search domain at INFEASIBLE_COST. A bounded scalar search that
    # probes mostly inside that slab can return an infeasible x -- which then
    # blew up in the un-guarded final re-solve below. Remembering the best
    # feasible point makes the outcome independent of where the optimizer
    # happens to stop.
    best: dict[str, Any] = {"cost": float("inf"), "x": None}

    def objective(x: np.ndarray) -> float:
        # Build the geometry
        params = dict(template)
        for fld, val in zip(fields, x, strict=True):
            params[fld] = float(val)
        try:
            geom = from_dict(params)
        except (KeyError, ValueError):
            return INFEASIBLE_COST  # bad geometry → huge penalty

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
            return INFEASIBLE_COST

        # Cost = RMS relative deviation across targets
        sqr_sum = 0.0
        for k, v_target in target.items():
            v_actual = _extract_metric(result, k)
            if v_actual is None:
                return INFEASIBLE_COST
            sqr_sum += ((v_actual - v_target) / max(abs(v_target), 1e-12)) ** 2
        cost = float(np.sqrt(sqr_sum / len(target)))
        if cost < best["cost"]:
            best["cost"] = cost
            best["x"] = np.array(x, dtype=float, copy=True)
        return cost

    if len(fields) == 1:
        lo, hi = bounds[0]

        # Bracket the search on the feasible sub-interval before optimizing.
        # Closed-form models have validity limits, so a wide default bound such
        # as 0.1-100 mil can leave the feasible region confined to the bottom
        # fraction of the interval. Golden-section then probes only the flat
        # INFEASIBLE_COST slab, never samples a solvable geometry, and returns
        # an arbitrary endpoint. A coarse log-spaced scan costs a few dozen
        # microsecond solves and makes the outcome bound-insensitive.
        scan = np.geomspace(lo, hi, 64) if lo > 0 else np.linspace(lo, hi, 64)
        with warnings.catch_warnings():
            # The scan deliberately probes geometries outside model validity;
            # those warnings describe throwaway samples, not the returned answer.
            warnings.simplefilter("ignore")
            feasible = [float(x) for x in scan if objective(np.array([x])) < INFEASIBLE_COST]
        if feasible:
            # Widen by one scan step so the true optimum is not clipped off the
            # edge of the feasible samples.
            step = (hi / lo) ** (1.0 / 63) if lo > 0 else (hi - lo) / 63
            if lo > 0:
                lo, hi = max(lo, min(feasible) / step), min(hi, max(feasible) * step)
            else:
                lo, hi = max(lo, min(feasible) - step), min(hi, max(feasible) + step)

        # xatol scaled to the bound-range. The optimizer should converge to a
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

    # Prefer the best evaluable point over whatever the optimizer returned:
    # never worse, and it keeps an infeasible endpoint from reaching the
    # un-guarded final solve below.
    if best["x"] is not None and best["cost"] < cost:
        x_opt = best["x"]
        cost = float(best["cost"])

    if best["x"] is None:
        raise ValueError(
            "optimize_for: no evaluable geometry inside the given bounds. Every "
            f"candidate for {fields} failed to solve or did not report "
            f"{sorted(target)}. Check that the target metric exists for this "
            "geometry type (single-ended results carry 'z0', differential ones "
            "'z_diff') and that the bounds lie inside the model's validity range."
        )

    # Build the final geometry + result
    params = dict(template)
    for fld, val in zip(fields, x_opt, strict=True):
        params[fld] = float(val)
    geom = from_dict(params)

    final: Any
    if solver == "analytical":
        final = analytical_solve(geom, frequency_hz=frequency_hz)
    else:
        from lineforge.geometry.builders import rasterize as _ras
        from lineforge.solvers.cgp import solve_cgp as _cgp

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


def _default_metric_for(
    template: dict[str, Any],
    vary_dict: dict[str, tuple[float | str, float | str]],
    *,
    frequency_hz: float | None,
) -> str:
    """Pick the impedance metric this geometry actually reports.

    Single-ended geometries return a ``TLineResult`` carrying ``z0``;
    differential ones return a ``DiffResult`` carrying ``z_odd``/``z_even``/
    ``z_diff``/``z_common`` and **no** ``z0``. Targeting ``z0`` on a
    differential pair made every candidate miss, so the objective returned the
    1e6 penalty everywhere, the cost surface was perfectly flat, and the
    optimizer parked wherever the bounded search happened to land -- reporting
    ``success=False`` with a null impedance instead of the obvious "that
    metric does not exist for this geometry".

    The template normally omits the varying field, so fill each one with the
    midpoint of its bounds before probing. Any failure here is non-fatal:
    fall back to ``z0`` and let the normal machinery report the problem.
    """
    probe_params = dict(template)
    for fld, (lo, hi) in vary_dict.items():
        probe_params[fld] = 0.5 * (_coerce_bound(lo) + _coerce_bound(hi))
    try:
        probe = analytical_solve(from_dict(probe_params), frequency_hz=frequency_hz)
    except Exception:
        return "z0"
    if _extract_metric(probe, "z0") is not None:
        return "z0"
    if _extract_metric(probe, "z_diff") is not None:
        return "z_diff"
    return "z0"


def target_z0(
    template: dict[str, Any],
    *,
    vary: str | dict[str, tuple[float | str, float | str]],
    target_ohms: float,
    solver: str = "analytical",
    frequency_hz: float | None = None,
    max_iter: int = 100,
    bounds: tuple[float | str, float | str] | None = None,
    metric: str | None = None,
) -> OptimizeResult:
    """Find a single dimension that hits a target characteristic impedance.

    Ergonomic wrapper around :func:`optimize_for` for the most common workflow:
    "what trace width gives me 50 Ω on this stackup?"

    Parameters
    ----------
    template
        Geometry dict with all the fixed fields (type + everything not varying).
    vary
        Either a field name (e.g. ``"W"``): bounds default to ``("0.1mil", "100mil")``
        or are taken from the optional ``bounds`` argument, or a full ``vary``
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
    metric
        Result field to drive toward ``target_ohms``. Defaults to ``"z0"`` for
        single-ended geometries and ``"z_diff"`` for differential ones, chosen
        by probe-solving the template. Set it explicitly to target something
        else, e.g. ``"z_odd"`` on a coupled pair.

    Returns
    -------
    OptimizeResult
        ``.geometry`` is the dimensioned geometry; ``.metric[<metric>]`` is the
        achieved impedance; ``.success`` is ``True`` when within 1 % of target.

    Examples
    --------
    Single-ended: width for 50 ohm on an asymmetric inner layer::

        >>> from lineforge.optimize import target_z0
        >>> r = target_z0(
        ...     template={
        ...         "type": "stripline_asymmetric",
        ...         "T": "1.4mil",
        ...         "H1": "4mil",
        ...         "H2": "5mil",
        ...         "er": 4.2,
        ...     },
        ...     vary="W",
        ...     target_ohms=50.0,
        ...     bounds=("1mil", "10mil"),
        ... )
        >>> r.success
        True

    Differential: the metric defaults to ``z_diff``, so a 100 ohm pair is::

        >>> r = target_z0(
        ...     template={
        ...         "type": "edge_coupled_diff_microstrip",
        ...         "H": "4mil", "T": "1.4mil", "S": "5mil", "er": 4.2,
        ...     },
        ...     vary="W",
        ...     target_ohms=100.0,
        ...     bounds=("1mil", "20mil"),
        ... )
        >>> r.success
        True
    """
    if isinstance(vary, str):
        if bounds is None:
            bounds = ("0.1mil", "100mil")
        vary_dict: dict[str, tuple[float | str, float | str]] = {vary: bounds}
    else:
        vary_dict = vary

    metric_name = metric or _default_metric_for(template, vary_dict, frequency_hz=frequency_hz)

    return optimize_for(
        template=template,
        vary=vary_dict,
        target={metric_name: target_ohms},
        solver=solver,
        frequency_hz=frequency_hz,
        max_iter=max_iter,
    )


__all__ = ["OptimizeResult", "optimize_for", "target_z0"]
