"""Unit handling for atlc3.

Wraps a single ``pint`` registry with the SI base units we care about (length
in meters, frequency in hertz). Provides a convenience parser for atlc2-style
suffix strings: ``"6mil"``, ``"4mm"``, ``"2.5e-4"``, ``"30AWG"``, etc.

Conventions:
    - All numerical solvers and Pydantic models work in SI base units (meters,
      seconds, hertz, henries, farads, ohms, siemens).
    - Unit parsing happens at the boundary (CLI, MCP server, JSON loader).
    - AWG is mapped to a wire diameter in meters via the standard formula:
      ``d = 0.127 mm × 92^((36 − awg)/39)``.
"""

from __future__ import annotations

from typing import Final

import pint

ureg: Final[pint.UnitRegistry] = pint.UnitRegistry()
ureg.define("mil = 0.0254 millimeter = thou")

_AWG_BASE_MM: Final[float] = 0.127
_AWG_FACTOR: Final[float] = 92.0
_AWG_REF: Final[int] = 36
_AWG_DIVISOR: Final[float] = 39.0


def awg_to_meters(awg: float) -> float:
    """Convert an AWG number to a wire diameter in meters.

    Uses the standard formula ``d = 0.127 mm × 92^((36 − awg)/39)``,
    valid for AWG 0000 (-3) through ~50.

    Parameters
    ----------
    awg
        American Wire Gauge number. Larger numbers are thinner wires.

    Returns
    -------
    float
        Diameter in meters.

    Examples
    --------
    >>> abs(awg_to_meters(30) - 2.55e-4) < 5e-6
    True
    """
    diameter_mm = _AWG_BASE_MM * (_AWG_FACTOR ** ((_AWG_REF - awg) / _AWG_DIVISOR))
    return diameter_mm * 1e-3


def parse_length(value: str | float | int) -> float:
    """Parse a length input into meters.

    Accepts:
        - bare numbers (assumed meters): ``1.5e-4``, ``0.0001``
        - pint-parseable strings: ``"6 mil"``, ``"4mm"``, ``"0.05in"``, ``"2.5e-4 m"``
        - AWG strings: ``"30AWG"``, ``"30 AWG"`` → diameter in meters
        - power-of-ten suffix strings (atlc2 style): ``"13e-3"`` (= 13e-3 m by default)

    Parameters
    ----------
    value
        Numeric or string length spec.

    Returns
    -------
    float
        Length in meters.

    Raises
    ------
    ValueError
        If the string cannot be parsed.
    """
    if isinstance(value, (int, float)):
        return float(value)

    s = value.strip()
    if not s:
        raise ValueError("empty length string")

    upper = s.upper()
    if upper.endswith("AWG"):
        try:
            number = float(upper[:-3].strip())
        except ValueError as exc:
            raise ValueError(f"could not parse AWG number from {value!r}") from exc
        return awg_to_meters(number)

    # Try pint, falling back to a bare-float interpretation if pint can't.
    try:
        quantity = ureg.parse_expression(s)
    except (pint.errors.UndefinedUnitError, pint.errors.DimensionalityError) as exc:
        raise ValueError(f"could not parse length {value!r}") from exc

    if isinstance(quantity, (int, float)):
        return float(quantity)

    try:
        return float(quantity.to("meter").magnitude)
    except pint.errors.DimensionalityError as exc:
        raise ValueError(f"{value!r} is not a length") from exc


def parse_frequency(value: str | float | int) -> float:
    """Parse a frequency input into hertz.

    Accepts:
        - bare numbers: ``1e9`` (assumed Hz)
        - pint strings: ``"1 GHz"``, ``"100 MHz"``, ``"2.4 GHz"``

    Parameters
    ----------
    value
        Numeric or string frequency spec.

    Returns
    -------
    float
        Frequency in Hz.
    """
    if isinstance(value, (int, float)):
        return float(value)

    s = value.strip()
    if not s:
        raise ValueError("empty frequency string")
    try:
        quantity = ureg.parse_expression(s)
    except pint.errors.UndefinedUnitError as exc:
        raise ValueError(f"could not parse frequency {value!r}") from exc

    if isinstance(quantity, (int, float)):
        return float(quantity)

    try:
        return float(quantity.to("hertz").magnitude)
    except pint.errors.DimensionalityError as exc:
        raise ValueError(f"{value!r} is not a frequency") from exc


__all__ = ["awg_to_meters", "parse_frequency", "parse_length", "ureg"]
