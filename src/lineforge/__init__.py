"""lineforge — open-source MCP-enabled transmission line calculator.

Top-level convenience entry points for the most common workflows. Full API
is organized into submodules:

    lineforge.geometry      — Pydantic geometry models, rasterizer, Usermap
    lineforge.materials     — material database, MoreColors.txt loader, JSON packs
    lineforge.analytical    — closed-form solvers (Hammerstad-Jensen, Wadell)
    lineforge.solvers       — numerical kernels (Phase 2: C/Gp; Phase 3: L/Rs)
    lineforge.visualization — V/E/D/J/loss field rendering
    lineforge.scripting     — atlc2 .txt script-file interpreter
    lineforge.cli           — Typer CLI (entry point: ``lineforge``)
    lineforge.mcp_server    — MCP server (entry point: ``lineforge mcp-serve``)

The native Rust kernels are accessed via :mod:`lineforge._kernel`.

Quick start::

    import lineforge
    r = lineforge.microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
    print(f"Z0 = {r.z0:.2f} Ω")

    # Bitmap path:
    um = lineforge.from_bmp("usermap.bmp", pixel_width="0.1mm")
    cgp = lineforge.solve_cgp(um, frequency="1GHz")
"""

from __future__ import annotations

from typing import Any

from lineforge.analytical import solve as _analytical_solve
from lineforge.cache import cached, clear_cache
from lineforge.cache import is_disabled as cache_disabled
from lineforge.geometry import (
    CPWG,
    GEOMETRY_TYPES,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    EmbeddedMicrostrip,
    GeometryUnion,
    Microstrip,
    StriplineAsymmetric,
    StriplineSymmetric,
    from_dict,
)
from lineforge.geometry.builders import rasterize
from lineforge.geometry.usermap import Usermap
from lineforge.optimize import OptimizeResult
from lineforge.optimize import optimize_for as _optimize_for
from lineforge.results import DiffResult, SolverWarning, TLineResult
from lineforge.solvers import (
    CGPResult,
    RLGCResult,
)
from lineforge.solvers import (
    solve_cgp as _solve_cgp,
)
from lineforge.solvers import (
    solve_full as _solve_full,
)
from lineforge.solvers import (
    solve_lrs as _solve_lrs,
)
from lineforge.sweep import SweepPoint
from lineforge.sweep import sweep as _sweep
from lineforge.units import parse_frequency, parse_length
from lineforge.version import __version__


def _to_m(value: float | str) -> float:
    return parse_length(value) if isinstance(value, str) else float(value)


def microstrip(
    *,
    W: float | str,
    H: float | str,
    T: float | str,
    er: float,
    tan_delta: float = 0.0,
    rho: float = 1.7241e-8,
    frequency: float | str | None = None,
) -> TLineResult:
    """Solve a microstrip via Hammerstad-Jensen.

    Examples
    --------
    >>> r = microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
    >>> 40 < r.z0 < 70
    True
    """
    geom = Microstrip(W=_to_m(W), H=_to_m(H), T=_to_m(T), er=er, tan_delta=tan_delta, rho=rho)
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    return _analytical_solve(geom, frequency_hz=freq)


def stripline(
    *,
    W: float | str,
    T: float | str,
    B: float | str,
    er: float,
    tan_delta: float = 0.0,
    rho: float = 1.7241e-8,
    frequency: float | str | None = None,
) -> TLineResult:
    """Solve a symmetric stripline via Cohn / Wadell."""
    geom = StriplineSymmetric(
        W=_to_m(W), T=_to_m(T), B=_to_m(B), er=er, tan_delta=tan_delta, rho=rho
    )
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    return _analytical_solve(geom, frequency_hz=freq)


def cpwg(
    *,
    W: float | str,
    S: float | str,
    H: float | str,
    T: float | str,
    er: float,
    tan_delta: float = 0.0,
    rho: float = 1.7241e-8,
    frequency: float | str | None = None,
) -> TLineResult:
    """Solve a coplanar waveguide with ground plane (CPWG)."""
    geom = CPWG(W=_to_m(W), S=_to_m(S), H=_to_m(H), T=_to_m(T), er=er, tan_delta=tan_delta, rho=rho)
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    return _analytical_solve(geom, frequency_hz=freq)


def edge_coupled_diff(
    *,
    W: float | str,
    S: float | str,
    H: float | str,
    T: float | str,
    er: float,
    on: str = "microstrip",
    tan_delta: float = 0.0,
    rho: float = 1.7241e-8,
    frequency: float | str | None = None,
) -> DiffResult:
    """Solve an edge-coupled differential pair, on microstrip or stripline."""
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    Wm, Sm, Hm, Tm = _to_m(W), _to_m(S), _to_m(H), _to_m(T)
    geom: EdgeCoupledDiffMicrostrip | EdgeCoupledDiffStripline
    if on == "microstrip":
        geom = EdgeCoupledDiffMicrostrip(
            W=Wm,
            S=Sm,
            H=Hm,
            T=Tm,
            er=er,
            tan_delta=tan_delta,
            rho=rho,
        )
    elif on == "stripline":
        geom = EdgeCoupledDiffStripline(
            W=Wm,
            S=Sm,
            B=Hm,
            T=Tm,
            er=er,
            tan_delta=tan_delta,
            rho=rho,
        )
    else:
        raise ValueError(f"`on` must be 'microstrip' or 'stripline', got {on!r}")
    result = _analytical_solve(geom, frequency_hz=freq)
    assert isinstance(result, DiffResult)
    return result


def solve(
    geometry: GeometryUnion | Usermap | dict[str, Any],
    *,
    method: str = "auto",
    frequency: float | str | None = None,
    pixel_width: float | str | None = None,
) -> TLineResult | DiffResult | CGPResult:
    """Solve any geometry or usermap, picking the right solver automatically.

    Parameters
    ----------
    geometry
        A model from :mod:`lineforge.geometry.types`, a :class:`Usermap`, or a dict
        with a ``type`` discriminator.
    method
        ``"analytical"``, ``"cgp"``, or ``"auto"``. Auto picks analytical for
        parameterized geometries, bitmap C/Gp for raw Usermaps.
    frequency
        Optional Hz or unit string.
    pixel_width
        Pixel size (m or unit string) when forcing the bitmap path.

    Examples
    --------
    >>> r = solve({"type": "microstrip", "W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4})
    >>> r.z0 > 0
    True
    """
    if isinstance(geometry, dict):
        geometry = from_dict(geometry)

    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width

    from lineforge.solvers.dispatcher import solve as _dispatch

    return _dispatch(geometry, method=method, frequency_hz=freq, pixel_width=px)  # type: ignore[arg-type]


def solve_cgp(
    geometry: GeometryUnion | Usermap | dict[str, Any],
    *,
    frequency: float | str | None = None,
    pixel_width: float | str | None = None,
    use_charge_shift: bool = True,
    laplace_method: str = "auto",
    return_fields: bool = False,
) -> CGPResult | tuple[CGPResult, Any]:
    """Solve C and Gp via the bitmap Laplace solver.

    Forces the numerical path even for parameterized geometries (rasterizes them).
    Useful for cross-checking the closed-form analytical answer or for arbitrary
    geometries that have no analytical formula.
    """
    if isinstance(geometry, dict):
        geometry = from_dict(geometry)

    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width

    usermap = geometry if isinstance(geometry, Usermap) else rasterize(geometry, pixel_width=px)

    if return_fields:
        return _solve_cgp(
            usermap,
            frequency_hz=freq,
            use_charge_shift=use_charge_shift,
            method=laplace_method,
            return_fields=True,
        )
    return _solve_cgp(
        usermap,
        frequency_hz=freq,
        use_charge_shift=use_charge_shift,
        method=laplace_method,
        return_fields=False,
    )


def from_bmp(path: str, *, pixel_width: float | str) -> Usermap:
    """Load an atlc/atlc2-format BMP usermap.

    Parameters
    ----------
    path
        Path to the BMP file.
    pixel_width
        Physical size of one pixel (e.g. ``"0.1mm"`` or ``1e-4``).
    """
    return Usermap.from_bmp(path, pixel_width=pixel_width)


def solve_lrs(
    geometry: GeometryUnion | Usermap | dict[str, Any],
    *,
    frequency: float | str,
    pixel_width: float | str | None = None,
    method: str = "auto",
    restrict_to_skin_depth: bool = True,
) -> Any:
    """Solve only L and Rs via the Faraday/PEEC bitmap solver (Phase 3).

    Parameters
    ----------
    geometry
        Parameterized geometry, dict, or Usermap.
    frequency
        Hz or unit string (e.g. ``"1GHz"``).
    pixel_width
        Pixel size for rasterization (geometry → bitmap).
    method
        ``"auto"`` | ``"dense"`` | ``"bicgstab"``.
    restrict_to_skin_depth
        atlc2's "Restrict to skin depth" toggle (default True at high f).
    """
    if isinstance(geometry, dict):
        geometry = from_dict(geometry)
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width

    usermap = geometry if isinstance(geometry, Usermap) else rasterize(geometry, pixel_width=px)
    return _solve_lrs(
        usermap,
        frequency_hz=float(freq),
        method=method,
        restrict_to_skin_depth=restrict_to_skin_depth,
    )


def solve_full(
    geometry: GeometryUnion | Usermap | dict[str, Any],
    *,
    frequency: float | str,
    pixel_width: float | str | None = None,
    restrict_to_skin_depth: bool = True,
) -> RLGCResult:
    """Solve the full RLGC characterization at one frequency (Phase 3).

    Combines the Phase 2 C/Gp Laplace solve with the Phase 3 Faraday L/Rs
    solve. Returns :class:`RLGCResult` with L, C, R, G, Z0, εeff, vp, α, β.
    """
    if isinstance(geometry, dict):
        geometry = from_dict(geometry)
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width

    usermap = geometry if isinstance(geometry, Usermap) else rasterize(geometry, pixel_width=px)
    return _solve_full(
        usermap,
        frequency_hz=float(freq),
        restrict_to_skin_depth=restrict_to_skin_depth,
    )


def sweep(
    geometry: GeometryUnion | Usermap | dict[str, Any],
    parameter: str,
    values: Any,
    *,
    solver: str = "analytical",
    frequency: float | str | None = None,
) -> list[SweepPoint]:
    """Sweep a single parameter over a list of values."""
    if isinstance(geometry, dict):
        geometry = from_dict(geometry)
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    return _sweep(
        geometry,
        parameter=parameter,
        values=values,
        solver=solver,
        frequency_hz=freq,
    )


def optimize_for(
    *,
    template: dict[str, Any],
    vary: dict[str, tuple[float | str, float | str]],
    target: dict[str, float],
    solver: str = "analytical",
    frequency: float | str | None = None,
    max_iter: int = 100,
) -> OptimizeResult:
    """Find geometry parameters that hit electrical targets.

    Examples
    --------
    Find the trace width for 50Ω on 4 mil FR4::

        result = lineforge.optimize_for(
            template={"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
            vary={"W": ("0.5mil", "30mil")},
            target={"z0": 50.0},
        )
        print(result.geometry.W)  # → ~6 mil
    """
    freq = parse_frequency(frequency) if isinstance(frequency, str) else frequency
    return _optimize_for(
        template=template,
        vary=vary,
        target=target,
        solver=solver,
        frequency_hz=freq,
        max_iter=max_iter,
    )


__all__ = [
    "CPWG",
    "GEOMETRY_TYPES",
    "BroadsideCoupledDiffStripline",
    "CGPResult",
    "DiffResult",
    "EdgeCoupledDiffMicrostrip",
    "EdgeCoupledDiffStripline",
    "EmbeddedMicrostrip",
    "GeometryUnion",
    "Microstrip",
    "OptimizeResult",
    "RLGCResult",
    "SolverWarning",
    "StriplineAsymmetric",
    "StriplineSymmetric",
    "SweepPoint",
    "TLineResult",
    "Usermap",
    "__version__",
    "cache_disabled",
    "cached",
    "clear_cache",
    "cpwg",
    "edge_coupled_diff",
    "from_bmp",
    "from_dict",
    "microstrip",
    "optimize_for",
    "parse_frequency",
    "parse_length",
    "rasterize",
    "solve",
    "solve_cgp",
    "solve_full",
    "solve_lrs",
    "stripline",
    "sweep",
]
