"""Analytical solver dispatcher.

:func:`solve` accepts any :class:`~atlc3.geometry.GeometryUnion` and routes it
to the right closed-form solver based on the model's discriminator. Returns
:class:`~atlc3.results.TLineResult` for single-line geometries and
:class:`~atlc3.results.DiffResult` for differential pairs.

The dispatcher is the unified entry point used by the CLI, Python API, and
MCP server.
"""

from __future__ import annotations

from typing import overload

from atlc3.analytical import hammerstad, wadell
from atlc3.geometry.types import (
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
from atlc3.results import DiffResult, TLineResult


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


def solve(
    geometry: GeometryUnion, *, frequency_hz: float | None = None
) -> TLineResult | DiffResult:
    """Dispatch a geometry to its closed-form solver.

    Parameters
    ----------
    geometry
        Any of the geometry models in :mod:`atlc3.geometry.types`.
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
        case _:
            raise TypeError(
                f"unrecognized geometry type {type(geometry).__name__}; "
                "use one of the geometries from atlc3.geometry.types"
            )


__all__ = ["solve"]
