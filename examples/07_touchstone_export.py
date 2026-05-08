"""Phase A2 example — frequency sweep + Touchstone (.s2p) export.

Sweep a 50Ω microstrip from 0.1–20 GHz and write the result as a 2-port
Touchstone file that can be loaded into HyperLynx, ADS, scikit-rf, or any
RF analysis tool.

Run::

    python examples/07_touchstone_export.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from atlc3.geometry.types import Microstrip
from atlc3.sweep import sweep
from atlc3.touchstone import to_touchstone


def main() -> None:
    geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4, tan_delta=0.02)

    freqs = np.linspace(1e8, 2e10, 101).tolist()  # 0.1–20 GHz, 101 points
    points = sweep(geom, parameter="frequency", values=freqs, solver="analytical")

    out_dir = Path("/tmp/atlc3_examples")
    out_dir.mkdir(exist_ok=True)
    out_path = to_touchstone(
        points,
        out_dir / "fr4_microstrip_50ohm.s2p",
        line_length="1in",
        z_ref=50.0,
    )
    print(f"Wrote {out_path}")

    # Reload via scikit-rf and report a few sanity numbers.
    import skrf

    net = skrf.Network(str(out_path))
    f_ghz = net.f / 1e9
    s21_db = 20.0 * np.log10(np.abs(net.s[:, 1, 0]))
    s11_db = 20.0 * np.log10(np.abs(net.s[:, 0, 0]) + 1e-30)

    print(f"\nNetwork: {net.nports} ports, {net.f.size} freq points, Z_ref={net.z0[0, 0]:.0f}")
    print("\nf [GHz]   |S21| [dB]   |S11| [dB]")
    print("-" * 38)
    for i in (0, 25, 50, 75, 100):
        print(f"  {f_ghz[i]:>5.2f}    {s21_db[i]:>8.3f}    {s11_db[i]:>8.3f}")


if __name__ == "__main__":
    main()
