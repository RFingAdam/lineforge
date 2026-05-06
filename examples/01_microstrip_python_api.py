"""Phase 1 example — Python API.

Solve a 50Ω microstrip on 4 mil FR4 and a 100Ω diff pair on the same stackup.

Run::

    python examples/01_microstrip_python_api.py
"""

from __future__ import annotations

import atlc3


def main() -> None:
    # Single-ended microstrip: ~50Ω on 4 mil FR4.
    se = atlc3.microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4, tan_delta=0.02, frequency="1GHz")
    print("Single-ended microstrip:")
    print(f"  Z0       = {se.z0:.2f} Ω")
    print(f"  εeff     = {se.eps_eff:.3f}")
    print(f"  vp       = {se.vp:.3e} m/s ({se.vp / 299_792_458:.3f} c)")
    print(f"  td/inch  = {se.td_per_inch * 1e12:.2f} ps/in")
    if se.dielectric_loss_db_per_in is not None:
        print(f"  αd      = {se.dielectric_loss_db_per_in:.4f} dB/in")
    print()

    # Differential pair: target 100Ω diff
    dp = atlc3.edge_coupled_diff(W="4mil", S="6mil", H="4mil", T="1.4mil", er=4.4, on="microstrip")
    print("Edge-coupled differential pair:")
    print(f"  Z_diff   = {dp.z_diff:.2f} Ω")
    print(f"  Z_odd    = {dp.z_odd:.2f} Ω")
    print(f"  Z_even   = {dp.z_even:.2f} Ω")
    print(f"  Z_common = {dp.z_common:.2f} Ω")


if __name__ == "__main__":
    main()
