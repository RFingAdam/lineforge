"""Phase 1 example — parameter sweep via the Python API.

Sweeps W from 3 mil to 25 mil for a microstrip on 4 mil FR4, prints Z0 and εeff
for each value. Phase 3 will add a first-class `atlc3.sweep()` API for the
numerical kernels.
"""

from __future__ import annotations

import atlc3


def main() -> None:
    print(f"{'W (mil)':>8}  {'Z0 (Ω)':>8}  {'εeff':>6}  {'td (ps/in)':>10}")
    for w_mil in range(3, 26, 2):
        r = atlc3.microstrip(W=f"{w_mil}mil", H="4mil", T="1.4mil", er=4.4)
        print(f"{w_mil:>8}  {r.z0:>8.2f}  {r.eps_eff:>6.3f}  {r.td_per_inch * 1e12:>10.3f}")


if __name__ == "__main__":
    main()
