"""RF pad capacitance and relief-decision analytics.

For an electrically small (W << λ) RF pad on a PCB layer over a reference
plane, capacitance is dominated by the parallel-plate term plus a fringing
correction. Three methods supported, in order of conservatism:

- ``"pp"``  : pure parallel-plate, no fringing. Lower bound.
- ``"ya"``  : Yamashita-Atsuki square-pad correction. Best estimate for
              finite square or near-square pads. **Default.**
- ``"hj"``  : Hammerstad-Jensen wide-microstrip C-per-length times the
              pad length. Upper bound (double-counts end fringing).

The ``pad_relief_advisor`` function ranks multiple stackup options
(typically: no-relief, relieve-one-plane, relieve-two-planes) against an
RL target and returns a recommendation with full per-option data.

References
----------
- N. Yamashita and R. Atsuki, *Analysis of Microstrip-Type Transmission
  Lines with Finite Strip Thickness*, IEEE Trans. MTT, 1976.
- R. K. Hoffmann, *Handbook of Microwave Integrated Circuits*, Artech 1987,
  §3.1.
- IPC-2141A, *Design Guide for High-Speed Controlled Impedance Circuit
  Boards*, Appendix A.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from lineforge.analytical.hammerstad import microstrip
from lineforge.geometry.dielectric import DielectricLayer, series_reduce
from lineforge.geometry.types import Microstrip
from lineforge.units import parse_length

EPS0 = 8.854_187_817e-12  # F/m


Method = Literal["pp", "ya", "hj"]


@dataclass
class PadCapResult:
    """Result of a pad-capacitance calculation."""

    C_F: float
    """Capacitance in farads."""

    method: Method
    """Which method was used ('pp', 'ya', or 'hj')."""

    W_m: float
    """Pad width in metres."""

    L_m: float
    """Pad length in metres."""

    h_m: float
    """Effective dielectric height (pad to reference plane) in metres."""

    eps_eff: float
    """Effective relative permittivity used in the calculation."""

    fringing_factor: float
    """Multiplier applied above the parallel-plate value (1.0 for 'pp')."""

    @property
    def C_pF(self) -> float:
        """Capacitance in picofarads."""
        return self.C_F * 1e12

    @property
    def C_fF(self) -> float:
        """Capacitance in femtofarads."""
        return self.C_F * 1e15

    def impedance(self, frequency_hz: float) -> complex:
        """Shunt impedance Z_pad = 1/(jωC) at the given frequency."""
        if frequency_hz <= 0 or self.C_F <= 0:
            return complex(float("inf"), 0)
        omega = 2 * math.pi * frequency_hz
        return 1.0 / (1j * omega * self.C_F)

    def return_loss_dB(self, frequency_hz: float, Z0: float = 50.0) -> float:
        """Return loss in dB when this pad shunts a Z0 line.

        Uses ``|Γ| = ωCZ₀ / √(4 + (ωCZ₀)²)``, the exact shunt-cap on a
        matched-line formula.
        """
        if frequency_hz <= 0 or self.C_F <= 0:
            return float("inf")
        omega = 2 * math.pi * frequency_hz
        x = omega * self.C_F * Z0
        gamma = x / math.sqrt(4.0 + x * x)
        if gamma <= 0:
            return float("inf")
        return -20.0 * math.log10(gamma)


def _resolve_stack(
    h: object | None,
    er: float | None,
    stack: list[DielectricLayer] | None,
) -> tuple[float, float]:
    """Return (h_total_m, εr_eff) from either a single (h, er) or a stack."""
    if stack is not None:
        if h is not None or er is not None:
            raise ValueError("Provide either (h, er) OR stack, not both")
        if not stack:
            raise ValueError("stack must be a non-empty list of DielectricLayer")
        h_total, eps_eff, _tan_eq = series_reduce(stack)
        if h_total <= 0:
            raise ValueError("stack height must be positive")
        return h_total, eps_eff
    if h is None or er is None:
        raise ValueError("Provide (h, er) when stack is not given")
    h_m = parse_length(h) if isinstance(h, str) else float(h)
    if h_m <= 0:
        raise ValueError("h must be positive")
    return h_m, float(er)


def pad_capacitance(
    W: object,
    L: object | None = None,
    h: object | None = None,
    er: float | None = None,
    *,
    stack: list[DielectricLayer] | None = None,
    method: Method = "ya",
    T: object | None = None,
) -> PadCapResult:
    """Compute the capacitance of an electrically small RF pad.

    Parameters
    ----------
    W, L
        Pad width and length. Accept ``float`` (metres) or unit-suffixed
        strings (e.g. ``"0.4mm"``, ``"15mil"``). If ``L`` is omitted, the
        pad is assumed square (``L = W``).
    h, er
        Dielectric height to the reference plane and εr. Use these for a
        single-layer dielectric. Alternatively supply ``stack``.
    stack
        List of ``DielectricLayer`` for a multi-layer dielectric between
        pad and reference (e.g. when L2 is voided and reference is L3).
        Series-reduced via the parallel-plate formula.
    method
        ``"pp"`` (parallel plate, no fringing), ``"ya"`` (Yamashita-Atsuki
        square-pad with end fringing: default), or ``"hj"`` (Hammerstad-
        Jensen wide-microstrip times pad length, upper bound).
    T
        Optional trace thickness for the HJ method (ignored otherwise).

    Returns
    -------
    PadCapResult
        Capacitance + diagnostics. See :class:`PadCapResult`.
    """
    W_m = parse_length(W) if isinstance(W, str) else float(W)
    L_m = W_m if L is None else (parse_length(L) if isinstance(L, str) else float(L))
    if W_m <= 0 or L_m <= 0:
        raise ValueError("W and L must be positive")

    h_m, eps_eff = _resolve_stack(h, er, stack)

    if method not in ("pp", "ya", "hj"):
        raise ValueError(f"Unknown method {method!r}; expected 'pp', 'ya', or 'hj'")

    A = W_m * L_m
    C_pp = EPS0 * eps_eff * A / h_m

    if method == "pp":
        return PadCapResult(
            C_F=C_pp,
            method="pp",
            W_m=W_m,
            L_m=L_m,
            h_m=h_m,
            eps_eff=eps_eff,
            fringing_factor=1.0,
        )

    if method == "ya":
        # Yamashita-Atsuki: C_pad = C_pp · (1 + 0.78·√(h/W_eq) + 0.34·(h/W_eq))
        # where W_eq is the geometric-mean edge length for non-square pads.
        W_eq = math.sqrt(A)
        ratio = h_m / W_eq
        fringing = 1.0 + 0.78 * math.sqrt(ratio) + 0.34 * ratio
        return PadCapResult(
            C_F=C_pp * fringing,
            method="ya",
            W_m=W_m,
            L_m=L_m,
            h_m=h_m,
            eps_eff=eps_eff,
            fringing_factor=fringing,
        )

    # method == "hj": treat the pad as a microstrip line of length L_m, with
    # trace width = W_m. Compute C-per-length via HJ, then C_total = C/m · L.
    T_m: float
    T_m = 0.0 if T is None else parse_length(T) if isinstance(T, str) else float(T)
    # HJ requires T > 0; use a very thin value if not specified.
    if T_m <= 0:
        T_m = 1e-9
    h_unit = "m"
    g = Microstrip(
        W=f"{W_m}{h_unit}",
        T=f"{T_m}{h_unit}",
        H=f"{h_m}{h_unit}",
        er=eps_eff,
    )
    r = microstrip(g)
    # C per unit length: C/m = √εr_eff / (Z₀ · c)
    C_per_m = math.sqrt(r.eps_eff) / (r.z0 * 2.998e8)
    C_total = C_per_m * L_m
    fringing = C_total / C_pp if C_pp > 0 else 1.0
    return PadCapResult(
        C_F=C_total,
        method="hj",
        W_m=W_m,
        L_m=L_m,
        h_m=h_m,
        eps_eff=eps_eff,
        fringing_factor=fringing,
    )


@dataclass
class ReliefOption:
    """One option to consider in :func:`pad_relief_advisor`."""

    name: str
    """Human-readable label, e.g. ``"A: solid L2"``."""

    stack: list[DielectricLayer]
    """Dielectric stack from pad down to its reference plane."""


@dataclass
class ReliefAdviceRow:
    """Per-option row in the advisor's comparison table."""

    name: str
    C: PadCapResult
    Z_at_band_max: float  # |Z_pad| at band_max_ghz (ohms)
    RL_at_band_max: float  # RL in dB at band_max_ghz
    meets_target: bool
    headroom_dB: float  # RL_at_band_max - rl_target_dB


@dataclass
class ReliefAdvice:
    """Result of :func:`pad_relief_advisor`."""

    recommendation: str | None
    """The recommended option name (first that meets the target), or
    ``None`` if no option meets it."""

    rows: list[ReliefAdviceRow]
    """Per-option rows, in the order they were supplied."""

    band_max_ghz: float
    rl_target_dB: float
    Z0_line: float

    def best(self) -> ReliefAdviceRow | None:
        """Return the row with the highest RL_at_band_max."""
        if not self.rows:
            return None
        return max(self.rows, key=lambda r: r.RL_at_band_max)


def pad_relief_advisor(
    W: object,
    L: object | None = None,
    *,
    options: list[ReliefOption],
    band_max_ghz: float,
    rl_target_dB: float = 30.0,
    Z0_line: float = 50.0,
    method: Method = "ya",
) -> ReliefAdvice:
    """Rank pad-relief options against an RL target at the band edge.

    Parameters
    ----------
    W, L
        Pad dimensions (same as :func:`pad_capacitance`).
    options
        List of :class:`ReliefOption`. Typically three options:
        no-relief (single dielectric layer), relieve-one-plane (three
        layers in series), relieve-two-planes (five layers in series).
    band_max_ghz
        Highest operating frequency where the RL check is made. The
        pad cap matters most at the top of the band.
    rl_target_dB
        Minimum acceptable RL contribution from the pad alone. Default
        30 dB (10× line impedance rule of thumb).
    Z0_line
        Line characteristic impedance for the shunt-cap RL calculation
        (default 50 Ω).
    method
        Pad-cap method, default ``"ya"``.

    Returns
    -------
    ReliefAdvice
        Comparison table + the recommendation (first option that meets
        the target, in the order given). Order options from least to most
        invasive so the recommendation favours the minimal change.
    """
    f_top = band_max_ghz * 1e9
    rows: list[ReliefAdviceRow] = []
    recommendation: str | None = None

    for opt in options:
        C = pad_capacitance(W, L, stack=opt.stack, method=method)
        Z_top = abs(C.impedance(f_top))
        RL_top = C.return_loss_dB(f_top, Z0=Z0_line)
        meets = RL_top >= rl_target_dB
        headroom = RL_top - rl_target_dB
        rows.append(
            ReliefAdviceRow(
                name=opt.name,
                C=C,
                Z_at_band_max=Z_top,
                RL_at_band_max=RL_top,
                meets_target=meets,
                headroom_dB=headroom,
            )
        )
        if recommendation is None and meets:
            recommendation = opt.name

    return ReliefAdvice(
        recommendation=recommendation,
        rows=rows,
        band_max_ghz=band_max_ghz,
        rl_target_dB=rl_target_dB,
        Z0_line=Z0_line,
    )


__all__ = [
    "Method",
    "PadCapResult",
    "ReliefAdvice",
    "ReliefAdviceRow",
    "ReliefOption",
    "pad_capacitance",
    "pad_relief_advisor",
]
