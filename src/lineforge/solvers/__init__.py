"""Numerical solvers — bitmap Laplace (C/Gp) and Faraday (L/Rs).

- :func:`solve_cgp`        — Phase 2: C and Gp via Laplace FD.
- :func:`solve_lrs`        — Phase 3: L and Rs via Faraday PEEC.
- :func:`solve_full`       — Phase 3: full RLGC characterization at one frequency.
- :func:`solve_modes`      — Phase B3: 3-wire Y-decomposition via three Laplace
  solves with each conductor in turn floating.
"""

from __future__ import annotations

from lineforge.solvers.cgp import CGPResult, solve_cgp
from lineforge.solvers.dispatcher import solve
from lineforge.solvers.faraday import FaradayResult
from lineforge.solvers.lrs import RLGCResult, solve_full, solve_lrs
from lineforge.solvers.three_wire_cgp import solve_modes

__all__ = [
    "CGPResult",
    "FaradayResult",
    "RLGCResult",
    "solve",
    "solve_cgp",
    "solve_full",
    "solve_lrs",
    "solve_modes",
]
