"""Analytical solver dispatcher.

:func:`solve` accepts any :class:`~lineforge.geometry.GeometryUnion` and routes it
to the right closed-form solver based on the model's discriminator. Returns
:class:`~lineforge.results.TLineResult` for single-line geometries and
:class:`~lineforge.results.DiffResult` for differential pairs.

The dispatcher is the unified entry point used by the CLI, Python API, and
MCP server.
"""

from __future__ import annotations

from typing import Union, overload

from lineforge.analytical import hammerstad, wadell
from lineforge.analytical.three_wire import solve_three_wire as _solve_three_wire
from lineforge.geometry.three_wire import ThreeWireGeometry
from lineforge.geometry.types import (
    CPWG,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    EmbeddedMicrostrip,
    GeometryUnion,
    Microstrip,
    StriplineAsymmetric,
    StriplineSymmetric,
)
from lineforge.results import DiffResult, ThreeWireResult, TLineResult

ExtendedGeometryUnion = Union[GeometryUnion, ThreeWireGeometry]  # noqa: UP007
"""GeometryUnion plus the ThreeWireGeometry side-class.

Kept distinct from ``GeometryUnion`` because :class:`ThreeWireGeometry`
returns :class:`ThreeWireResult`, not the TLineResult/DiffResult union.
"""


@overload
def solve(geometry: Microstrip, *, frequency_hz: float | None = ...) -> TLineResult: ...
@overload
def solve(geometry: EmbeddedMicrostrip, *, frequency_hz: float | None = ...) -> TLineResult: ...
@overload
def solve(geometry: StriplineSymmetric, *, frequency_hz: float | None = ...) -> TLineResult: ...
@overload
def solve(geometry: StriplineAsymmetric, *, frequency_hz: float | None = ...) -> TLineResult: ...
@overload
def solve(geometry: CPWG, *, frequency_hz: float | None = ...) -> TLineResult: ...
@overload
def solve(
    geometry: EdgeCoupledDiffMicrostrip, *, frequency_hz: float | None = ...
) -> DiffResult: ...
@overload
def solve(
    geometry: EdgeCoupledDiffStripline, *, frequency_hz: float | None = ...
) -> DiffResult: ...
@overload
def solve(
    geometry: BroadsideCoupledDiffStripline, *, frequency_hz: float | None = ...
) -> DiffResult: ...
@overload
def solve(geometry: ThreeWireGeometry, *, frequency_hz: float | None = ...) -> ThreeWireResult: ...


def solve(
    geometry: ExtendedGeometryUnion, *, frequency_hz: float | None = None
) -> TLineResult | DiffResult | ThreeWireResult:
    """Dispatch a geometry to its closed-form solver.

    Parameters
    ----------
    geometry
        Any of the geometry models in :mod:`lineforge.geometry.types`.
    frequency_hz
        Optional frequency for loss estimates.

    Returns
    -------
    TLineResult or DiffResult
        :class:`TLineResult` for single-line geometries; :class:`DiffResult`
        for differential pairs.

    Raises
    ------
    NotImplementedError
        If a known geometry has no closed-form formula in this phase.
    TypeError
        If the input is not a recognized geometry model.
    """
    match geometry:
        case Microstrip():
            return hammerstad.microstrip(geometry, frequency_hz=frequency_hz)
        case EmbeddedMicrostrip():
            return hammerstad.embedded_microstrip(geometry, frequency_hz=frequency_hz)
        case StriplineSymmetric():
            return wadell.stripline_symmetric(geometry, frequency_hz=frequency_hz)
        case StriplineAsymmetric():
            return wadell.stripline_asymmetric(geometry, frequency_hz=frequency_hz)
        case CPWG():
            return wadell.cpwg(geometry, frequency_hz=frequency_hz)
        case EdgeCoupledDiffMicrostrip():
            return wadell.edge_coupled_diff_microstrip(geometry, frequency_hz=frequency_hz)
        case EdgeCoupledDiffStripline():
            return wadell.edge_coupled_diff_stripline(geometry, frequency_hz=frequency_hz)
        case BroadsideCoupledDiffStripline():
            return wadell.broadside_coupled_diff_stripline(geometry, frequency_hz=frequency_hz)
        case ThreeWireGeometry():
            return _solve_three_wire(geometry)
        case _:
            raise TypeError(
                f"unrecognized geometry type {type(geometry).__name__}; "
                "use one of the geometries from lineforge.geometry.types"
            )


__all__ = ["solve"]
