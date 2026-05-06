"""Bitmap-vs-analytical solver dispatcher.

Routes a geometry through:
    - the closed-form analytical solver if applicable, OR
    - rasterization → Laplace bitmap solve via :func:`atlc3.solvers.solve_cgp`.

Phase 3 extends this to include the Faraday L/Rs solver.
"""

from __future__ import annotations

from typing import Literal

from atlc3.analytical import solve as analytical_solve
from atlc3.geometry.builders import rasterize
from atlc3.geometry.types import GeometryUnion
from atlc3.geometry.usermap import Usermap
from atlc3.results import DiffResult, TLineResult
from atlc3.solvers.cgp import CGPResult, solve_cgp

SolverChoice = Literal["analytical", "cgp", "auto"]


def solve(
    geometry: GeometryUnion | Usermap,
    *,
    method: SolverChoice = "auto",
    frequency_hz: float | None = None,
    pixel_width: float | None = None,
) -> TLineResult | DiffResult | CGPResult:
    """Solve the given geometry, picking the right solver.

    Parameters
    ----------
    geometry
        A model from :mod:`atlc3.geometry.types` or a :class:`Usermap`.
    method
        ``"analytical"`` forces the closed-form path (works only for the 8
        standard PCB geometries). ``"cgp"`` forces the bitmap C/Gp solver.
        ``"auto"`` (default) picks analytical for standard parameterized
        geometries and bitmap for raw Usermaps.
    frequency_hz
        Frequency for loss / Gp. Optional.
    pixel_width
        Pixel size for rasterization (only used when method=='cgp' and the
        input is a parameterized geometry).
    """
    if isinstance(geometry, Usermap):
        return solve_cgp(geometry, frequency_hz=frequency_hz)

    chosen: SolverChoice = method if method != "auto" else "analytical"

    if chosen == "analytical":
        return analytical_solve(geometry, frequency_hz=frequency_hz)

    usermap = rasterize(geometry, pixel_width=pixel_width)
    return solve_cgp(usermap, frequency_hz=frequency_hz)


__all__ = ["solve"]
