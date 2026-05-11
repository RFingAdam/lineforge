"""Phase A1 example — multi-layer dielectric stack.

Real PCB stackups often have a stratified dielectric on one side of a stripline:
think of an inner-layer trace (L3) where the next plane down has been voided
in the trace region, pushing the lower reference all the way down to L5. The
dielectric below the strip is then ``Prepreg + voided-plane + Core``, three
layers in series.

This example mirrors the L3 SIG1 trace from the planning session of
2026-05-06 (3.4 mil wide, 0.689 mil thick ½-oz Cu, 8-layer board).

Run::

    python examples/06_dielectric_stack.py
"""

from __future__ import annotations

from lineforge.analytical.wadell import stripline_asymmetric
from lineforge.geometry.dielectric import DielectricLayer, series_reduce
from lineforge.geometry.types import StriplineAsymmetric


def main() -> None:
    # --- Stand-alone series_reduce on the void-L4 stack -------------------
    below_stack = [
        DielectricLayer(h="5.3mil", er=3.7, tan_delta=0.020, name="Prepreg"),
        DielectricLayer(h="1.4mil", er=3.7, tan_delta=0.020, name="L4 voided (filled)"),
        DielectricLayer(h="3.5mil", er=4.2, tan_delta=0.020, name="Core"),
    ]
    h_total, er_eq, tan_eq = series_reduce(below_stack)
    print("Series reduction of below-strip stack (Prepreg + voided + Core):")
    print(f"  h_total = {h_total * 39.37e3:.3f} mil")
    print(f"  εr_eq   = {er_eq:.4f}")
    print(f"  tan_eq  = {tan_eq:.5f}")
    print()

    # --- L3 SIG1 with L4 voided as a single StriplineAsymmetric -----------
    geom = StriplineAsymmetric(
        W="3.4mil",
        T="0.689mil",
        H1="3.5mil",
        er=4.2,
        er_above=4.2,
        tan_delta_above=0.020,
        stack_below=below_stack,
    )
    result = stripline_asymmetric(geom, frequency_hz=1e9)
    print("L3 SIG1 inner-layer trace (Core above, Prepreg+voided+Core below):")
    print(f"  Z0      = {result.z0:.3f} Ω")
    print(f"  εr_eff  = {result.eps_eff:.4f}")
    print(f"  vp      = {result.vp:.3e} m/s ({result.vp / 299_792_458:.3f} c)")
    print(f"  td/inch = {result.td_per_inch * 1e12:.2f} ps/in")
    if result.dielectric_loss_db_per_in is not None:
        print(f"  α_diel  = {result.dielectric_loss_db_per_in:.4f} dB/in @ 1 GHz")
    print(f"  method  = {result.method}")


if __name__ == "__main__":
    main()
