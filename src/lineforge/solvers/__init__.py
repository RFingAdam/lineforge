"""Numerical solvers: bitmap Laplace (C/Gp) and Faraday (L/Rs).

- :func:`solve_cgp`       : Phase 2: C and Gp via Laplace FD.
- :func:`solve_lrs`       : Phase 3: L and Rs via Faraday PEEC.
- :func:`solve_full`      : Phase 3: full RLGC characterization at one frequency.
- :func:`solve_maxwell`   : N-conductor Maxwell C and L matrices via one Laplace
  solve per signal conductor.
- :func:`solve_modes`     : Phase B3: 3-wire Y-decomposition via three Laplace
  solves with each conductor in turn floating.
- :func:`solve_impedance_matrix` : N-port PEEC R/L matrices from one LU
  factorisation reused across the drives.
- :func:`solve_wheeler_resistance` : skin-effect R and L_int by Wheeler's
  incremental-inductance rule, with per-conductor surface roughness.
"""

from __future__ import annotations

from lineforge.solvers.cgp import CGPResult, solve_cgp
from lineforge.solvers.dispatcher import solve
from lineforge.solvers.faraday import (
    FaradayResult,
    SolverBudgetExceeded,
    solve_impedance_matrix,
)
from lineforge.solvers.lrs import RLGCResult, solve_full, solve_lrs
from lineforge.solvers.mtl import MaxwellResult, rlgc_matrices, solve_maxwell
from lineforge.solvers.roughness import (
    cannonball_from_rz,
    groisse_factor,
    hammerstad_factor,
    huray_factor,
    roughness_factor,
)
from lineforge.solvers.three_wire_cgp import solve_modes
from lineforge.solvers.wheeler import WheelerResult, solve_wheeler_resistance

__all__ = [
    "CGPResult",
    "FaradayResult",
    "MaxwellResult",
    "RLGCResult",
    "SolverBudgetExceeded",
    "WheelerResult",
    "cannonball_from_rz",
    "groisse_factor",
    "hammerstad_factor",
    "huray_factor",
    "rlgc_matrices",
    "roughness_factor",
    "solve",
    "solve_cgp",
    "solve_full",
    "solve_impedance_matrix",
    "solve_lrs",
    "solve_maxwell",
    "solve_modes",
    "solve_wheeler_resistance",
]
