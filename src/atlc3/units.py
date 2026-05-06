"""Unit handling for atlc3.

A small hand-rolled parser for atlc2-style length and frequency suffix strings:
``"6mil"``, ``"4mm"``, ``"2.5e-4"``, ``"30AWG"``, ``"1GHz"``, etc.

Conventions:
    - All numerical solvers and Pydantic models work in SI base units (meters,
      seconds, hertz, henries, farads, ohms, siemens).
    - Unit parsing happens at the boundary (CLI, MCP server, JSON loader).
    - AWG is mapped to a wire diameter in meters via the standard formula:
      ``d = 0.127 mm × 92^((36 − awg)/39)``.

We deliberately *don't* use :mod:`pint` for parsing: pint 0.25's default
``mil`` is the angular unit (dimensionless), which conflicts with the
PCB-designer convention that ``"mil"`` always means a length. A small
suffix table keeps the semantics unambiguous.
"""

from __future__ import annotations

import re
from typing import Final

# Length suffixes → multiplier to meters
_LENGTH_SUFFIXES: Final[dict[str, float]] = {
    "": 1.0,  # bare numbers default to meters
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "um": 1e-6,
    "µm": 1e-6,
    "micron": 1e-6,
    "microns": 1e-6,
    "nm": 1e-9,
    "in": 2.54e-2,
    "inch": 2.54e-2,
    "inches": 2.54e-2,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
    "mil": 25.4e-6,
    "thou": 25.4e-6,
    "mils": 25.4e-6,
}

# Frequency suffixes → multiplier to hertz (case-insensitive after normalization)
_FREQ_SUFFIXES: Final[dict[str, float]] = {
    "": 1.0,
    "hz": 1.0,
    "khz": 1e3,
    "mhz": 1e6,
    "ghz": 1e9,
    "thz": 1e12,
}

_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^\s*
    ([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)   # group 1: number
    \s*
    ([A-Za-zµ]*)                                  # group 2: suffix (alpha or µ)
    \s*$
    """,
    re.VERBOSE,
)

_AWG_BASE_MM: Final[float] = 0.127
_AWG_FACTOR: Final[float] = 92.0
_AWG_REF: Final[int] = 36
_AWG_DIVISOR: Final[float] = 39.0


def awg_to_meters(awg: float) -> float:
    """Convert an AWG number to a wire diameter in meters.

    Uses the standard formula ``d = 0.127 mm × 92^((36 − awg)/39)``,
    valid for AWG 0000 (-3) through ~50.

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
        - bare numeric strings: ``"1.5e-4"``, ``"0.0001"``
        - suffix strings: ``"6mil"``, ``"6 mil"``, ``"4mm"``, ``"0.05in"``,
          ``"2.5e-4 m"``, ``"100µm"``
        - AWG strings: ``"30AWG"``, ``"30 AWG"`` → wire diameter in meters

    Examples
    --------
    >>> parse_length(1.5e-4)
    0.00015
    >>> parse_length("6mil")
    0.0001524
    >>> parse_length("4 mm")
    0.004
    >>> abs(parse_length("30AWG") - 2.55e-4) < 5e-6
    True
    """
    if isinstance(value, (int, float)):
        return float(value)

    if not value or not value.strip():
        raise ValueError("empty length string")

    s = value.strip()

    # AWG special case
    upper = s.upper()
    if upper.endswith("AWG"):
        try:
            number = float(upper[:-3].strip())
        except ValueError as exc:
            raise ValueError(f"could not parse AWG number from {value!r}") from exc
        return awg_to_meters(number)

    match = _NUMBER_RE.match(s)
    if match is None:
        raise ValueError(f"could not parse length {value!r}")
    number_str, suffix = match.groups()
    suffix_lower = suffix.lower()

    if suffix_lower not in _LENGTH_SUFFIXES:
        raise ValueError(
            f"unknown length suffix {suffix!r} in {value!r}; "
            f"valid suffixes: {sorted(set(_LENGTH_SUFFIXES) - {''})}"
        )
    return float(number_str) * _LENGTH_SUFFIXES[suffix_lower]


def parse_frequency(value: str | float | int) -> float:
    """Parse a frequency input into hertz.

    Accepts:
        - bare numbers: ``1e9`` (assumed Hz)
        - suffix strings: ``"1 GHz"``, ``"100MHz"``, ``"2.4 GHz"``, ``"50kHz"``

    Examples
    --------
    >>> parse_frequency(1e9)
    1000000000.0
    >>> parse_frequency("1GHz")
    1000000000.0
    >>> parse_frequency("100 MHz")
    100000000.0
    """
    if isinstance(value, (int, float)):
        return float(value)

    if not value or not value.strip():
        raise ValueError("empty frequency string")

    s = value.strip()
    match = _NUMBER_RE.match(s)
    if match is None:
        raise ValueError(f"could not parse frequency {value!r}")
    number_str, suffix = match.groups()
    suffix_lower = suffix.lower()

    if suffix_lower not in _FREQ_SUFFIXES:
        raise ValueError(
            f"unknown frequency suffix {suffix!r} in {value!r}; "
            f"valid: {sorted(set(_FREQ_SUFFIXES) - {''})}"
        )
    return float(number_str) * _FREQ_SUFFIXES[suffix_lower]


__all__ = ["awg_to_meters", "parse_frequency", "parse_length"]
