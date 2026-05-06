"""Numerical solvers — bitmap Laplace (C/Gp) and Faraday (L/Rs).

- :func:`solve_cgp`        — Phase 2: C and Gp via Laplace FD.
- :func:`solve_lrs`        — Phase 3: L and Rs via Faraday PEEC.
- :func:`solve_full`       — Phase 3: full RLGC characterization at one frequency.
"""

from __future__ import annotations

from atlc3.solvers.cgp import CGPResult, solve_cgp
from atlc3.solvers.dispatcher import solve
from atlc3.solvers.faraday import FaradayResult, solve_lrs as _solve_lrs_inner
from atlc3.solvers.lrs import RLGCResult, solve_full, solve_lrs

__all__ = [
    "CGPResult",
    "FaradayResult",
    "RLGCResult",
    "solve",
    "solve_cgp",
    "solve_full",
    "solve_lrs",
]
