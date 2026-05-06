"""Parameter sweeps over geometries and frequencies.

Sweeps run a list of solves and return their results in a list. Useful for
gathering Z0(f), Z0(W), L(f) curves, or generating data for plot rendering.

Phase 3 implements the sweep over a single parameter; Phase 4 polish adds
2D sweeps + caching.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from atlc3.geometry.types import GeometryUnion
from atlc3.geometry.usermap import Usermap


@dataclass
class SweepPoint:
    """One point in a sweep: input params + result."""

    params: dict[str, Any]
    result: Any


def sweep(
    geometry: GeometryUnion | Usermap,
    *,
    parameter: str,
    values: Iterable[Any],
    method: str = "auto",
    frequency_hz: float | None = None,
    solver: str = "analytical",
    progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> list[SweepPoint]:
    """Sweep a parameter and collect results.

    Parameters
    ----------
    geometry
        Base geometry. The sweep will produce variants by overriding ``parameter``.
    parameter
        The name of a field on the geometry model (e.g. ``"W"``, ``"S"``, ``"er"``)
        or the literal string ``"frequency"`` to sweep frequency instead.
    values
        Iterable of values to sweep through (in their native type — meters for
        length fields, Hz for frequency, dimensionless for εr).
    method
        Solver dispatch: ``"analytical"``, ``"cgp"``, ``"full"`` (Phase 3 RLGC),
        or ``"auto"``.
    frequency_hz
        Frequency for the solve (only used by ``"cgp"`` / ``"full"``).
    solver
        ``"analytical"`` (default), ``"cgp"`` (bitmap C/Gp), or ``"full"``
        (bitmap RLGC including Faraday).
    progress
        Optional callable ``(idx, total, params) -> None`` for progress reporting.

    Returns
    -------
    list[SweepPoint]
    """
    from atlc3.analytical import solve as analytical
    from atlc3.geometry.builders import rasterize
    from atlc3.solvers.cgp import solve_cgp
    from atlc3.solvers.lrs import solve_full as solve_full_rlgc

    values_list = list(values)
    out: list[SweepPoint] = []

    for i, v in enumerate(values_list):
        params: dict[str, Any] = {parameter: v}
        if progress is not None:
            progress(i, len(values_list), params)

        # Build mutated geometry/frequency
        freq = frequency_hz
        if parameter == "frequency":
            freq = float(v)
            geom = geometry
        else:
            if isinstance(geometry, Usermap):
                # No way to mutate a usermap parameter — caller should pre-build one per value
                raise ValueError(
                    "sweep() cannot mutate a Usermap parameter; sweep over a parameterized geometry "
                    "or sweep frequency only with a fixed Usermap"
                )
            geom = geometry.model_copy(update={parameter: v})

        # Dispatch
        result: Any
        if solver == "analytical":
            result = analytical(geom, frequency_hz=freq)  # type: ignore[arg-type]
        elif solver == "cgp":
            usermap = geom if isinstance(geom, Usermap) else rasterize(geom)
            result = solve_cgp(usermap, frequency_hz=freq)
        elif solver == "full":
            usermap = geom if isinstance(geom, Usermap) else rasterize(geom)
            if freq is None:
                raise ValueError("solver='full' requires frequency_hz")
            result = solve_full_rlgc(usermap, frequency_hz=freq)
        else:
            raise ValueError(f"unknown solver {solver!r}")

        out.append(SweepPoint(params=params, result=result))

    return out


__all__ = ["SweepPoint", "sweep"]
