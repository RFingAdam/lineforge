#!/usr/bin/env python3
"""Simplified pad-cap measurement via direct lumped-port drive.

No feed line — just the pad, the dielectric stack, and a lumped voltage
source connecting the pad to the deepest GND of each option. Z_in at low
frequency gives the pad capacitance directly: C ≈ 1/(jω·Z_in).

This avoids the microstrip/transmission-line dynamics that destabilized
the earlier sim and gives a clean cap measurement.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0

MIL = 25.4  # micron per mil


def run_option(option: str) -> dict:
    unit = 1e-6

    # Pad
    W_pad = 400.0
    W_pad_h = W_pad / 2

    # Stackup heights (μm)
    h_D1 = 2.73 * MIL  # L1 to L2 prepreg
    h_L2 = 1.4 * MIL  # L2 GND
    h_D4 = 3.5 * MIL  # L2 to L3 core
    h_L3 = 0.689 * MIL  # L3 trace
    h_D2 = 5.3 * MIL  # L3 to L4 prepreg

    # Z coordinates, building down from pad at z=0
    z_pad = 0
    z_L2_top = -h_D1
    z_L2_bot = z_L2_top - h_L2
    z_L3_top = z_L2_bot - h_D4
    z_L3_bot = z_L3_top - h_L3
    z_L4_top = z_L3_bot - h_D2

    # For Option A: pad over L2, all we need is L2 GND
    # For Option B: void L2 under pad, GND island on L3
    # For Option C: void L2 + L3 under pad, GND on L4

    # The "deepest reference" depends on the option
    if option == "A":
        z_ref = z_L2_top  # bottom of D1 = top of L2 GND
    elif option == "B":
        z_ref = z_L3_top  # bottom of (D1+L2-void+D4) = top of L3
    elif option == "C":
        z_ref = z_L4_top  # bottom of full stack = top of L4
    else:
        raise ValueError(option)

    h_total = abs(z_ref)  # depth from pad to its deepest reference

    f_min = 0.01e9
    f_max = 2e9  # low f — pad acts purely capacitive

    side = 4000.0

    FDTD = openEMS(NrTS=100000, EndCriteria=1e-6)
    FDTD.SetGaussExcite((f_max + f_min) / 2, (f_max - f_min) / 2)
    FDTD.SetBoundaryCond(["MUR"] * 6)

    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(unit)

    # Mesh sizing — sub-pad resolution
    res = 50  # 50 μm bulk mesh
    fine = 15  # 15 μm fine mesh near pad

    # X mesh: fine near pad edges
    mesh.AddLine(
        "x",
        [
            -side,
            -W_pad_h - fine,
            -W_pad_h,
            -W_pad_h + fine,
            0,
            W_pad_h - fine,
            W_pad_h,
            W_pad_h + fine,
            side,
        ],
    )
    mesh.SmoothMeshLines("x", res)

    # Y mesh: fine near pad edges
    mesh.AddLine("y", [-side, -W_pad_h - fine, -W_pad_h, 0, W_pad_h, W_pad_h + fine, side])
    mesh.SmoothMeshLines("y", res)

    # Z mesh: lines at every layer surface, with refinement in dielectrics
    z_lines = [z_pad, z_L2_top, z_L2_bot, z_L3_top, z_L3_bot, z_L4_top]
    mesh.AddLine("z", z_lines)
    mesh.AddLine("z", np.linspace(z_pad, z_L2_top, 4))
    mesh.AddLine("z", z_L4_top - 200)  # mesh extension below
    mesh.SmoothMeshLines("z", 20)

    # Dielectric: simplified single εr_eff for the depth between pad and ref
    if option == "A":
        # D1 prepreg εr = 3.7
        er_eff = 3.7
    elif option == "B":
        # Series: D1 prepreg + L2 fill (prepreg) + D4 core
        layers = [(h_D1, 3.7), (h_L2, 3.7), (h_D4, 4.2)]
        inv = sum(h / e for h, e in layers)
        er_eff = h_total / inv
    else:
        # Series: D1 + L2 fill + D4 + L3 fill + D2
        layers = [(h_D1, 3.7), (h_L2, 3.7), (h_D4, 4.2), (h_L3, 3.7), (h_D2, 3.7)]
        inv = sum(h / e for h, e in layers)
        er_eff = h_total / inv

    diel = CSX.AddMaterial("diel", epsilon=er_eff)
    diel.AddBox([-side, -side, z_ref], [side, side, z_pad], priority=1)

    pec = CSX.AddMetal("PEC")

    # Pad: thin square sheet at z=0
    pec.AddBox([-W_pad_h, -W_pad_h, z_pad], [W_pad_h, W_pad_h, z_pad], priority=10)

    # Reference plane: solid sheet at z=z_ref, with rectangular hole
    # only if the relief is needed at the reference level (it isn't —
    # by construction, the reference is the FIRST solid plane the pad
    # sees, with all relief above it removed)
    plane_side = side - 12 * res
    pec.AddBox([-plane_side, -plane_side, z_ref], [plane_side, plane_side, z_ref], priority=10)

    # Lumped port: drives the pad against the reference plane
    # Place the port at one corner of the pad (asymmetric drive is OK
    # since we're measuring lumped C, not transmission-line behavior)
    port = FDTD.AddLumpedPort(
        1,
        1000,  # high reference impedance to better measure high-Z cap
        [W_pad_h - res, -res, z_ref],
        [W_pad_h, res, z_pad],
        "z",
        excite=1,
        priority=5,
    )

    sim_path = os.path.join(tempfile.gettempdir(), f"atlc3_padcap_{option}")
    if os.path.isdir(sim_path):
        shutil.rmtree(sim_path)
    FDTD.Run(sim_path, cleanup=True)

    freq = np.linspace(f_min, f_max, 201)
    port.CalcPort(sim_path, freq)

    Z_in = port.uf_tot / port.if_tot
    # At low f, Z_in ≈ 1/(jωC) for pure cap, so C = -1/(2πf · Im(Z_in))
    # But there's a small inductive component too. Fit at low f.
    f_use = freq[freq < 0.5e9]
    Z_use = Z_in[freq < 0.5e9]
    omega = 2 * np.pi * f_use
    # C from Im(1/Z_in)/ω
    Y = 1 / Z_use
    C_est = np.imag(Y) / omega
    C_avg = np.mean(C_est[C_est > 0])

    return {
        "option": option,
        "h_total_mil": h_total / MIL,
        "er_eff": er_eff,
        "C_pF": C_avg * 1e12 if not np.isnan(C_avg) else None,
        "freq": freq,
        "Z_in": Z_in,
    }


def main():
    print("=" * 70)
    print("Pad-cap measurement: direct lumped-port (no transmission line)")
    print("=" * 70)
    results = []
    for opt in ["A", "B", "C"]:
        print(f"\n>>> Option {opt} ...")
        r = run_option(opt)
        results.append(r)

    print(f"\n{'Option':<6} {'h (mil)':>8} {'εr_eff':>7} {'EM C (fF)':>12} {'PP C (fF)':>12}")
    print("-" * 50)
    pp = {"A": 75.6, "B": 28.6, "C": 15.6}
    for r in results:
        c_fF = r["C_pF"] * 1000 if r["C_pF"] else None
        c_str = f"{c_fF:.1f}" if c_fF else "—"
        print(
            f"  {r['option']:<4} {r['h_total_mil']:>8.2f} {r['er_eff']:>7.2f} "
            f"{c_str:>12} {pp[r['option']]:>12.1f}"
        )


if __name__ == "__main__":
    main()
