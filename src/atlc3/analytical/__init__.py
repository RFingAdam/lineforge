"""Closed-form analytical transmission-line solvers.

Implements the IPC-2141A formulas (Hammerstad-Jensen, Wadell) for the seven
standard PCB geometries. These run in microseconds — about a million times
faster than the bitmap kernel — and are accurate to ±1% over the published
validity ranges.

Use :func:`solve` to dispatch any :class:`~atlc3.geometry.GeometryUnion` to
the right formula.
"""

from __future__ import annotations

from atlc3.analytical.dispatcher import solve
from atlc3.analytical.hammerstad import embedded_microstrip, microstrip
from atlc3.analytical.wadell import (
    broadside_coupled_diff_stripline,
    cpwg,
    edge_coupled_diff_microstrip,
    edge_coupled_diff_stripline,
    stripline_asymmetric,
    stripline_symmetric,
)

__all__ = [
    "broadside_coupled_diff_stripline",
    "cpwg",
    "edge_coupled_diff_microstrip",
    "edge_coupled_diff_stripline",
    "embedded_microstrip",
    "microstrip",
    "solve",
    "stripline_asymmetric",
    "stripline_symmetric",
]
