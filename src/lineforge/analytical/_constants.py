"""Physical constants used by the analytical solvers."""

from __future__ import annotations

from typing import Final

C0: Final[float] = 299_792_458.0
"""Speed of light in vacuum [m/s]."""

ETA0: Final[float] = 376.730_313_412
"""Impedance of free space [Ω]: η₀ = μ₀·c."""

MU0: Final[float] = 1.256_637_062_12e-6
"""Vacuum permeability [H/m]."""

EPS0: Final[float] = 8.854_187_817_62e-12
"""Vacuum permittivity [F/m]."""

INCH_M: Final[float] = 0.0254
"""Inch-to-meter conversion."""
