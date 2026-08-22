"""End-to-end RF path return-loss budget.

Combines three reflection sources on a typical RF path:

1. **Source pad**: shunt capacitance to its reference plane (e.g. an
   IC pin pad or RF connector launch pad)
2. **Trace**: characteristic-impedance mismatch vs the port reference
   (e.g. a 56 Ω microstrip seen by a 50 Ω port)
3. **End pad**: shunt capacitance at the far end (e.g. U.FL connector,
   second IC pin)

For each operating frequency, returns the per-element |S11| contributions
and a worst-case combined RL (in-phase sum). This gives a first-order
budget that helps decide which element dominates and which to optimize.

For deeper analysis (frequency-dependent dispersion, transmission-line
phase rotation, S-parameter cascading), use a full S-parameter
simulator. This module is for budgeting, not detailed verification.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from lineforge.analytical.pads import PadCapResult


@dataclass
class TraceSpec:
    """Characteristic impedance + length of a transmission-line segment."""

    Z0: float
    """Trace characteristic impedance in ohms (e.g. 56.0)."""

    length_inch: float = 0.0
    """Trace length in inches. Not used for RL (steady-state), but kept
    for future IL-budget integration."""

    name: str = "trace"


@dataclass
class PathBudgetRow:
    """Per-frequency row of the path budget."""

    frequency_ghz: float
    s11_source_dB: float
    s11_trace_dB: float
    s11_end_dB: float
    s11_combined_dB: float  # worst-case sum of |Γ|s, converted to dB

    @property
    def combined_rl_dB(self) -> float:
        """Worst-case combined return loss (= -S11_combined)."""
        return -self.s11_combined_dB

    @property
    def dominant(self) -> str:
        """Name of the contributor with the largest |S11| at this frequency."""
        contributors = [
            ("source_pad", self.s11_source_dB),
            ("trace", self.s11_trace_dB),
            ("end_pad", self.s11_end_dB),
        ]
        # Largest |S11| = least negative dB
        return max(contributors, key=lambda x: x[1])[0]


@dataclass
class PathBudget:
    """Full path-budget result across the frequency sweep."""

    rows: list[PathBudgetRow]
    Z0_port: float
    source_pad: PadCapResult | None
    trace: TraceSpec | None
    end_pad: PadCapResult | None

    @property
    def worst_rl_dB(self) -> float:
        """Worst combined RL across all frequencies."""
        if not self.rows:
            return float("inf")
        return min(row.combined_rl_dB for row in self.rows)


def _shunt_cap_gamma(C_F: float, freq_hz: float, Z0: float) -> float:
    """|Γ| from a shunt capacitor on a Z0 line.

    |Γ| = ωCZ₀ / √(4 + (ωCZ₀)²)  (exact, no small-signal approximation).
    Returns 0 when C ≤ 0 or freq ≤ 0.
    """
    if C_F <= 0 or freq_hz <= 0 or Z0 <= 0:
        return 0.0
    omega = 2 * math.pi * freq_hz
    x = omega * C_F * Z0
    return x / math.sqrt(4.0 + x * x)


def _trace_gamma(Z_trace: float, Z0: float) -> float:
    """|Γ| from a transmission line of impedance Z_trace looking into Z0.

    Frequency-independent at steady-state (ignoring line-length resonance
    effects, which require full S-parameter cascading).
    """
    if Z_trace <= 0 or Z0 <= 0:
        return 0.0
    return abs(Z_trace - Z0) / (Z_trace + Z0)


def _gamma_to_dB(gamma: float) -> float:
    if gamma <= 0:
        return float("-inf")
    if gamma >= 1:
        return 0.0
    return 20.0 * math.log10(gamma)


def rf_path_budget(
    *,
    freq_ghz: Iterable[float],
    source_pad: PadCapResult | None = None,
    trace: TraceSpec | None = None,
    end_pad: PadCapResult | None = None,
    Z0_port: float = 50.0,
) -> PathBudget:
    """Compute a worst-case end-to-end return-loss budget.

    Parameters
    ----------
    freq_ghz
        Iterable of operating frequencies in GHz at which to evaluate.
    source_pad
        Source-side pad (e.g. IC output pin pad). Pass None if absent.
        Build via :func:`lineforge.analytical.pads.pad_capacitance`.
    trace
        Transmission line between the two pads. Pass None if just two
        pads with no significant line between them.
    end_pad
        End-side pad (e.g. U.FL connector pad, antenna pad).
    Z0_port
        Reference impedance for the |Γ| calculations (default 50 Ω).

    Returns
    -------
    PathBudget
        Per-frequency rows + worst-case summary. The combined RL is a
        first-order worst-case (in-phase sum of |Γ|s), conservative
        compared to actual S-parameter cascading.
    """
    rows: list[PathBudgetRow] = []

    for f_ghz in freq_ghz:
        f_hz = f_ghz * 1e9
        g_src = _shunt_cap_gamma(source_pad.C_F, f_hz, Z0_port) if source_pad else 0.0
        g_trc = _trace_gamma(trace.Z0, Z0_port) if trace else 0.0
        g_end = _shunt_cap_gamma(end_pad.C_F, f_hz, Z0_port) if end_pad else 0.0

        # Worst-case combined: in-phase sum, clipped to 1.0
        g_sum = min(g_src + g_trc + g_end, 0.999_999)

        rows.append(
            PathBudgetRow(
                frequency_ghz=f_ghz,
                s11_source_dB=_gamma_to_dB(g_src),
                s11_trace_dB=_gamma_to_dB(g_trc),
                s11_end_dB=_gamma_to_dB(g_end),
                s11_combined_dB=_gamma_to_dB(g_sum),
            )
        )

    return PathBudget(
        rows=rows,
        Z0_port=Z0_port,
        source_pad=source_pad,
        trace=trace,
        end_pad=end_pad,
    )


__all__ = ["PathBudget", "PathBudgetRow", "TraceSpec", "rf_path_budget"]
