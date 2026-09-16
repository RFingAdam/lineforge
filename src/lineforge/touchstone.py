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
>>> from lineforge import microstrip_geom  # doctest: +SKIP
>>> from lineforge.sweep import sweep
>>> from lineforge.touchstone import to_touchstone
>>> import numpy as np
>>> geom = microstrip_geom(W="6mil", H="4mil", T="1.4mil", er=4.4)  # doctest: +SKIP
>>> points = sweep(geom, parameter="frequency", values=np.linspace(1e8, 10e9, 51),
...                solver="analytical")  # doctest: +SKIP
>>> to_touchstone(points, "trace.s2p", line_length="1in")  # doctest: +SKIP
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np

from lineforge.sweep import SweepPoint
from lineforge.units import parse_length

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
        Output of :func:`lineforge.sweep.sweep` with ``parameter="frequency"``.
        Each point's ``result`` must expose ``z0``, ``vp``, and may optionally
        carry conductor/dielectric loss values.
    path
        Output file path. Should end in ``.s2p``; scikit-rf adds it if absent.
    line_length
        Physical length of the modeled line section. Accepts a float in meters
        or a unit string (``"1in"``, ``"50mm"``, etc.). Default 1 inch: long
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

    # Validate it really is a frequency sweep: peek at the first point.
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
        frequency=freq, s=s_matrix, z0=z_ref, name=f"lineforge-line-{length_m * 1e3:.3f}mm"
    )

    out = Path(path)
    if out.suffix.lower() != ".s2p":
        out = out.with_suffix(".s2p")
    net.write_touchstone(str(out.with_suffix("")), form="ri")
    return out


def to_touchstone_nport(
    freqs_hz: np.ndarray,
    s: np.ndarray,
    path: str | Path,
    *,
    z_ref: float | Sequence[float] = 50.0,
    port_names: Sequence[str] | None = None,
    mixed_mode_order: Sequence[str] | None = None,
    version: Literal[1, 2] = 1,
    comment: str = "",
) -> Path:
    """Write an N-port S-parameter set as Touchstone 1.x (via scikit-rf) or 2.0 (native writer).

    Port ``i`` of the file (1-based in the file, ``s[:, i, j]`` here) is the ``i``-th
    conductor in ascending ``conductor_ids`` order, that is
    ``MaxwellResult.conductor_ids[i]``. This is the same ordering the rows and columns of
    :func:`lineforge.solvers.faraday.solve_impedance_matrix` carry, so an S-matrix built
    from those matrices needs no permutation here.

    Parameters
    ----------
    freqs_hz
        Frequency points in Hz, shape ``(F,)``.
    s
        S-parameters, shape ``(F, P, P)``.
    path
        Output file path. The suffix is forced to ``.s{P}p`` for the given
        port count ``P``, for both versions.
    z_ref
        Reference impedance: a scalar applied to every port, or one value
        per port. Touchstone 1.x has a single ``R`` on its option line and no
        way to record per-port references, so differing values are refused
        there; pass ``version=2`` for those.
    port_names
        Optional per-port names. Written into the scikit-rf network (v1) or
        as comment lines (v2).
    mixed_mode_order
        Optional mixed-mode port order labels (e.g. ``"D1,2"``, ``"C1,2"``),
        written to the ``[Mixed-Mode Order]`` header (version 2 only).
    version
        ``1`` writes Touchstone 1.x via scikit-rf; ``2`` writes Touchstone
        2.0 natively.
    comment
        Optional comment line written into the version 2 header.

    Returns
    -------
    Path
        The actual path written.

    Raises
    ------
    ValueError
        If ``s`` is not shaped ``(F, P, P)`` matching ``freqs_hz``, or
        ``z_ref`` does not provide exactly one value per port, or
        ``version == 1`` was asked for with per-port references that differ.
    """
    freqs = np.asarray(freqs_hz, dtype=np.float64)
    s = np.asarray(s, dtype=np.complex128)
    if s.ndim != 3 or s.shape[1] != s.shape[2] or s.shape[0] != len(freqs):
        raise ValueError(
            f"s must have shape (F, P, P) matching {len(freqs)} frequencies, got {s.shape}"
        )
    ports = s.shape[1]
    zs = [float(z_ref)] * ports if isinstance(z_ref, (int, float)) else [float(z) for z in z_ref]
    if len(zs) != ports:
        raise ValueError("z_ref must be a scalar or one value per port")
    out = Path(path)
    if out.suffix.lower() != f".s{ports}p":
        out = out.with_suffix(f".s{ports}p")
    if version == 1:
        if len(set(zs)) > 1:
            raise ValueError(
                "Touchstone 1.x carries one reference impedance on its option line, so the "
                "per-port values would be silently reduced to the first one; pass "
                "version=2 to keep per-port references"
            )
        import skrf

        net = skrf.Network(
            frequency=skrf.Frequency.from_f(freqs, unit="Hz"), s=s, z0=np.array(zs), name=out.stem
        )
        if port_names:
            net.port_names = list(port_names)
        # The full path, not out.with_suffix(""): scikit-rf keeps a filename that already
        # carries an extension and appends one otherwise, while with_suffix("") would eat a
        # dotted stem as well, turning "chan_v1.2.s4p" into "chan_v1.s4p".
        net.write_touchstone(str(out), form="ri", write_z0=False)
        return out
    # Keyword order below is the one the 2.0 spec fixes: [Version], the option line, then
    # [Number of Ports], [Two-Port Data Order] (two-ports only), [Number of Frequencies],
    # [Reference], [Mixed-Mode Order], [Network Data], [End].
    #
    # zs[0] on the option line is only the nominal reference for legacy readers that pre-date
    # per-port references; the actual per-port values are the ones in the [Reference] line.
    lines = ["[Version] 2.0", f"# Hz S RI R {zs[0]:g}", f"[Number of Ports] {ports}"]
    if ports == 2:
        lines.append("[Two-Port Data Order] 12_21")
    lines.append(f"[Number of Frequencies] {len(freqs)}")
    lines.append("[Reference] " + " ".join(f"{z:g}" for z in zs))
    if mixed_mode_order:
        lines.append("[Mixed-Mode Order] " + " ".join(mixed_mode_order))
    if comment:
        lines.append(f"! {comment}")
    if port_names:
        lines.extend(f"! port {i + 1}: {name}" for i, name in enumerate(port_names))
    lines.append("[Network Data]")
    for fi, f in enumerate(freqs):
        # One matrix row per line, the frequency leading the first of them.
        for i in range(ports):
            row = [f"{f:.9e}"] if i == 0 else []
            for j in range(ports):
                row.append(f"{s[fi, i, j].real:.9e} {s[fi, i, j].imag:.9e}")
            lines.append(" ".join(row))
    lines.append("[End]")
    out.write_text("\n".join(lines) + "\n")
    return out


__all__ = ["to_touchstone", "to_touchstone_nport"]
