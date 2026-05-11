"""Frequency-dependent dielectric properties (Dk(f), Df(f) interpolation).

Modern high-speed laminate vendors publish εr (Dk) and tan_δ (Df) at multiple
frequencies — Megtron 4/6/7 datasheets give 1/2.5/5/10 GHz points; Rogers
RO4350B publishes 100 MHz, 1 GHz, 10 GHz, etc. This module interpolates
between those tabulated points so a solver run at, say, 6.5 GHz gets a
realistic Dk(f) value rather than the single nominal εr.

Interpolation is **linear in log(f)**, which is the reasonable default for
the gentle Debye-like dispersion of PCB resins over the 0.1–40 GHz range
where most signal-integrity work lives. Extrapolation past the published
range clamps to the endpoint value (no Lorentz-style modeling here — that
would need datasheet-fit parameters we don't have).
"""

from __future__ import annotations

import math
from collections.abc import Mapping


def interpolate_log_freq(
    table: Mapping[float, float],
    freq_hz: float,
) -> float:
    """Linear-in-log-f interpolation through tabulated values.

    Parameters
    ----------
    table
        Mapping ``{frequency_hz: value}``. Must have ≥ 2 entries.
    freq_hz
        Query frequency. Must be > 0.

    Returns
    -------
    Interpolated value. Outside the table's range, clamps to the nearest
    endpoint (no extrapolation).

    Examples
    --------
    >>> table = {1e9: 4.40, 10e9: 4.30}  # Dk dropping with frequency
    >>> round(interpolate_log_freq(table, 3.16e9), 4)  # mid-decade in log space
    4.35
    """
    if freq_hz <= 0:
        raise ValueError(f"freq_hz must be positive; got {freq_hz}")
    if len(table) < 2:
        raise ValueError("interpolate_log_freq requires at least 2 points")

    freqs = sorted(table.keys())
    if freq_hz <= freqs[0]:
        return table[freqs[0]]
    if freq_hz >= freqs[-1]:
        return table[freqs[-1]]

    # Bracket
    for i in range(len(freqs) - 1):
        f_lo, f_hi = freqs[i], freqs[i + 1]
        if f_lo <= freq_hz <= f_hi:
            v_lo, v_hi = table[f_lo], table[f_hi]
            log_ratio = (math.log(freq_hz) - math.log(f_lo)) / (math.log(f_hi) - math.log(f_lo))
            return v_lo + log_ratio * (v_hi - v_lo)
    # unreachable, but keep mypy happy
    return float("nan")


def material_at_frequency(
    er: float,
    tan_delta: float,
    er_freq: Mapping[float, float] | None,
    tan_freq: Mapping[float, float] | None,
    freq_hz: float | None,
) -> tuple[float, float]:
    """Resolve (εr, tan_δ) at a query frequency, falling back to constants.

    If ``er_freq`` is provided and ``freq_hz`` is given, εr is interpolated;
    otherwise the constant ``er`` is returned. Same logic for tan_δ.

    Parameters
    ----------
    er
        Constant fallback εr (used when no frequency table is given).
    tan_delta
        Constant fallback tan_δ.
    er_freq
        Optional mapping ``{Hz: εr}`` from a datasheet.
    tan_freq
        Optional mapping ``{Hz: tan_δ}`` from a datasheet.
    freq_hz
        Operating frequency. If ``None``, the constants are used.

    Returns
    -------
    ``(εr, tan_δ)`` at the requested frequency.
    """
    if freq_hz is None:
        return er, tan_delta

    er_at = interpolate_log_freq(er_freq, freq_hz) if er_freq else er
    tan_at = interpolate_log_freq(tan_freq, freq_hz) if tan_freq else tan_delta
    return er_at, tan_at


__all__ = ["interpolate_log_freq", "material_at_frequency"]
