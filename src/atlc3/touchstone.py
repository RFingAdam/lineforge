"""Touchstone (.s2p) export for transmission-line frequency sweeps.

A frequency sweep over a transmission-line geometry yields ``Z₀(f)``, ``γ(f)``
(propagation constant), and per-frequency loss. Modeled as a 2-port network
of length ``L``, the line has ABCD matrix:

    A = D = cosh(γL)
    B = Z₀ · sinh(γL)
    C = sinh(γL) / Z₀

This module converts that to S-parameters at a user-chosen reference impedance
(typically 50 Ω) and writes a Touchstone v1 ``.s2p`` file via ``scikit-rf``.
The resulting file plugs straight into HyperLynx, ADS, SiSoft, or any
network analyzer software for cascade analysis with measured/simulated
neighbouring components.

Example
-------
>>> from atlc3 import microstrip_geom  # doctest: +SKIP
>>> from atlc3.sweep import sweep
>>> from atlc3.touchstone import to_touchstone
>>> import numpy as np
>>> geom = microstrip_geom(W="6mil", H="4mil", T="1.4mil", er=4.4)  # doctest: +SKIP
>>> points = sweep(geom, parameter="frequency", values=np.linspace(1e8, 10e9, 51),
...                solver="analytical")  # doctest: +SKIP
>>> to_touchstone(points, "trace.s2p", line_length="1in")  # doctest: +SKIP
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from atlc3.sweep import SweepPoint
from atlc3.units import parse_length

INCH_M = 0.0254
DB_PER_NEPER = 8.685889638065035  # 20 / ln(10)


def _alpha_neper_per_m(result: Any) -> float:
    """Total propagation loss (conductor + dielectric) in nepers/m.

    ``TLineResult`` stores conductor and dielectric loss in dB/inch and may
    leave them as ``None`` for analytical frequency-independent runs.
    """
    cond_db_in = getattr(result, "conductor_loss_db_per_in", None) or 0.0
    diel_db_in = getattr(result, "dielectric_loss_db_per_in", None) or 0.0
    total_db_per_m = (cond_db_in + diel_db_in) / INCH_M
    return total_db_per_m / DB_PER_NEPER


def _abcd_to_s_2port(
    A: complex,
    B: complex,
    C: complex,
    D: complex,
    z_ref: float,
) -> tuple[complex, complex, complex, complex]:
    """Convert a 2-port ABCD matrix to S-parameters at reference Z."""
    delta = A + B / z_ref + C * z_ref + D
    s11 = (A + B / z_ref - C * z_ref - D) / delta
    s12 = 2.0 * (A * D - B * C) / delta
    s21 = 2.0 / delta
    s22 = (-A + B / z_ref - C * z_ref + D) / delta
    return s11, s12, s21, s22


def _line_section_s_params(
    z0_real: float,
    vp: float,
    alpha_np_per_m: float,
    freq_hz: float,
    length_m: float,
    z_ref: float,
) -> tuple[complex, complex, complex, complex]:
    """S-params of a length of uniform line at one frequency."""
    omega = 2.0 * math.pi * freq_hz
    beta = omega / vp
    gamma = complex(alpha_np_per_m, beta)
    gL = gamma * length_m
    # cmath cosh/sinh for complex arg
    coshg = (np.exp(gL) + np.exp(-gL)) / 2.0
    sinhg = (np.exp(gL) - np.exp(-gL)) / 2.0
    A = complex(coshg)
    D = A
    B = z0_real * complex(sinhg)
    C = complex(sinhg) / z0_real
    return _abcd_to_s_2port(A, B, C, D, z_ref)


def to_touchstone(
    sweep_results: list[SweepPoint],
    path: str | Path,
    *,
    line_length: float | str = "1in",
    z_ref: float = 50.0,
) -> Path:
    """Export a frequency sweep over a TL geometry to a Touchstone ``.s2p`` file.

    Parameters
    ----------
    sweep_results
        Output of :func:`atlc3.sweep.sweep` with ``parameter="frequency"``.
        Each point's ``result`` must expose ``z0``, ``vp``, and may optionally
        carry conductor/dielectric loss values.
    path
        Output file path. Should end in ``.s2p``; scikit-rf adds it if absent.
    line_length
        Physical length of the modeled line section. Accepts a float in meters
        or a unit string (``"1in"``, ``"50mm"``, etc.). Default 1 inch — long
        enough for the loss to register, short enough that 0–10 GHz fits in
        a few wavelengths.
    z_ref
        Reference impedance for the S-parameters. Default 50 Ω.

    Returns
    -------
    Path
        The actual path written.

    Raises
    ------
    ValueError
        If the sweep is not a frequency sweep, or no points are provided.
    """
    if not sweep_results:
        raise ValueError("to_touchstone: empty sweep_results")

    # Validate it really is a frequency sweep — peek at the first point.
    first_params = sweep_results[0].params
    if "frequency" not in first_params:
        raise ValueError(
            "to_touchstone requires a frequency sweep; got params with keys "
            f"{list(first_params.keys())!r} (use parameter='frequency' in sweep())"
        )

    length_m = parse_length(line_length) if isinstance(line_length, str) else float(line_length)
    if length_m <= 0:
        raise ValueError(f"line_length must be positive; got {length_m}")

    n = len(sweep_results)
    freqs = np.empty(n, dtype=float)
    s_matrix = np.empty((n, 2, 2), dtype=complex)

    for i, point in enumerate(sweep_results):
        f_hz = float(point.params["frequency"])
        freqs[i] = f_hz
        result = point.result
        z0_real = float(result.z0)
        vp = float(result.vp)
        alpha = _alpha_neper_per_m(result)
        s11, s12, s21, s22 = _line_section_s_params(
            z0_real=z0_real,
            vp=vp,
            alpha_np_per_m=alpha,
            freq_hz=f_hz,
            length_m=length_m,
            z_ref=z_ref,
        )
        s_matrix[i, 0, 0] = s11
        s_matrix[i, 0, 1] = s12
        s_matrix[i, 1, 0] = s21
        s_matrix[i, 1, 1] = s22

    # Build the skrf Network and write.
    import skrf

    freq = skrf.Frequency.from_f(freqs, unit="Hz")
    net = skrf.Network(
        frequency=freq, s=s_matrix, z0=z_ref, name=f"atlc3-line-{length_m * 1e3:.3f}mm"
    )

    out = Path(path)
    if out.suffix.lower() != ".s2p":
        out = out.with_suffix(".s2p")
    net.write_touchstone(str(out.with_suffix("")), form="ri")
    return out


__all__ = ["to_touchstone"]
