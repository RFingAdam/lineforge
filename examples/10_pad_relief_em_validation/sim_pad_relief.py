#!/usr/bin/env python3
"""OpenEMS validation of the 0.4 mm RF pad relief options on the
triplexer port pads (same stackup as the L3 SIG1 case study).

Options simulated (all share the same L1 microstrip feed + 0.4 mm pad):

  A. Solid L2 GND under the pad           — baseline (no relief)
  B. Void L2 + GND island on L3           — relieve to L3
  C. Void L2 + L3 area, L4 GND continues  — relieve to L4

Extracts S₁₁ vs frequency at a 50 Ω port at the far end of the feed
line. The pad terminates open (no component model). The pad cap then
shows up directly as the shunt-cap perturbation on the line.

Run:
    python sim_pad_relief.py            # runs all three, writes results
    python sim_pad_relief.py --option A # runs just A
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0

MIL = 25.4  # micron per mil — we work in μm with unit=1e-6


@dataclass
class StackZ:
    """Z coordinates (μm) of each layer surface, bottom-up."""
    L4_bot: float = 0
    L4_top: float = 0
    D2_top: float = 0       # bottom of L3 trace
    L3_top: float = 0
    D4_top: float = 0       # bottom of L2 GND
    L2_top: float = 0
    D1_top: float = 0       # bottom of L1 trace
    L1_top: float = 0


def make_stack() -> StackZ:
    """Build z coordinates of the 8-layer stackup, L4 GND at z=0."""
    s = StackZ()
    L_cu = 1.4 * MIL
    Lsig_cu = 0.689 * MIL
    s.L4_top = s.L4_bot + L_cu
    s.D2_top = s.L4_top + 5.30 * MIL   # 5.3 mil prepreg
    s.L3_top = s.D2_top + Lsig_cu
    s.D4_top = s.L3_top + 3.50 * MIL   # 3.5 mil core
    s.L2_top = s.D4_top + L_cu
    s.D1_top = s.L2_top + 2.73 * MIL   # 2.73 mil prepreg
    s.L1_top = s.D1_top + L_cu
    return s


def add_circle_via(csx_metal, x, y, z_bot, z_top, drill_um, n_segments=12):
    """Add a cylindrical via approximated as a polygon prism."""
    pts = []
    r = drill_um / 2
    for k in range(n_segments):
        th = 2 * np.pi * k / n_segments
        pts.append([x + r * np.cos(th), y + r * np.sin(th)])
    poly = csx_metal.AddLinPoly(
        points=np.array(pts).T,
        norm_dir=2,
        elevation=z_bot,
        length=z_top - z_bot,
        priority=20,
    )
    return poly


def run_option(option: str, run_dir: str | None = None) -> dict:
    """Run one sim and return the S-parameter result."""
    unit = 1e-6
    s = make_stack()

    # Pad and feed geometry (μm)
    W_pad = 400.0      # 0.4 mm
    W_relief = 500.0   # pad + 0.1 mm margin
    W_feed = 125.34    # 50 Ω microstrip over 2.73 mil prepreg, εr=3.7
    L_feed = 3000.0    # 3 mm feed line
    L_feed + W_pad / 2     # trace runs from port to pad far edge
    side = 4000.0      # lateral margin

    f_min = 0.1e9
    f_max = 8e9

    FDTD = openEMS(NrTS=300000, EndCriteria=1e-5)
    FDTD.SetGaussExcite((f_max + f_min) / 2, (f_max - f_min) / 2)
    # MUR all around (same as the working L3 SIG1 sim). The bottom of the
    # sim domain has L4 GND drawn as an explicit metal box so MUR there
    # is fine — it's effectively shorted by the GND plane.
    FDTD.SetBoundaryCond(["MUR"] * 6)

    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(unit)

    # Wavelength-based mesh sizing
    er_max = 4.2
    res_bulk = C0 / (f_max * np.sqrt(er_max)) / unit / 30
    third = np.array([2 * res_bulk / 3, -res_bulk / 3]) / 4

    # X mesh: feed + pad region. Extend simulation box past trace ends so
    # PML has room (8-cell padding minimum).
    x_port = -L_feed - W_pad / 2
    x_min = x_port - 8 * res_bulk      # PML padding on -x
    x_max = side                        # +x already padded
    mesh.AddLine("x", [x_min, x_port, -W_pad / 2, 0, W_pad / 2, x_max])
    mesh.AddLine("x", np.linspace(-W_relief / 2, W_relief / 2, 10))
    mesh.SmoothMeshLines("x", res_bulk)

    # Y mesh: across feed (trace centered at y=0), pad extends ±W_pad/2
    mesh.AddLine("y", [0])
    mesh.AddLine("y", W_feed / 2 + third)
    mesh.AddLine("y", -W_feed / 2 - third)
    mesh.AddLine("y", np.linspace(-W_relief / 2, W_relief / 2, 8))
    mesh.AddLine("y", [-side, -W_pad / 2, W_pad / 2, side])
    mesh.SmoothMeshLines("y", res_bulk)

    # Z mesh: explicit lines at every layer surface, with extra resolution
    # in the metal+nearby-dielectric regions
    z_lines = [s.L4_bot, s.L4_top, s.D2_top, s.L3_top, s.D4_top, s.L2_top, s.D1_top, s.L1_top]
    mesh.AddLine("z", z_lines)
    # Resolve each thin metal layer with at least 2 cells
    for z_bot, z_top in [(s.L4_bot, s.L4_top), (s.L2_top, s.D1_top),
                         (s.D1_top, s.L1_top), (s.D4_top, s.L2_top)]:
        mesh.AddLine("z", np.linspace(z_bot, z_top, 3))
    # Thinner D4 + D2 dielectrics
    mesh.AddLine("z", np.linspace(s.D2_top, s.L3_top, 3))
    mesh.AddLine("z", np.linspace(s.L4_top, s.D2_top, 5))
    # Cap z grid above L1 (air-ish boundary toward MUR)
    z_top_pad = s.L1_top + 400  # 400 μm above L1 (~6 cells of fine spacing)
    mesh.AddLine("z", z_top_pad)
    mesh.SmoothMeshLines("z", res_bulk)

    # Materials
    prepreg = CSX.AddMaterial("prepreg", epsilon=3.7)
    core    = CSX.AddMaterial("core",    epsilon=4.2)
    # D1 (between L1 and L2)
    prepreg.AddBox(
        [-side - 1000, -side - 1000, s.L2_top],
        [side + 1000, side + 1000, s.D1_top],
    )
    # D4 (between L2 and L3)
    core.AddBox(
        [-side - 1000, -side - 1000, s.D4_top],
        [side + 1000, side + 1000, s.L2_top],
    )
    # D2 (between L3 and L4) — exists for options B and C; harmless for A
    prepreg.AddBox(
        [-side - 1000, -side - 1000, s.L4_top],
        [side + 1000, side + 1000, s.D2_top],
    )

    pec = CSX.AddMetal("PEC")

    # ─── L1: feed trace + pad (zero-thickness sheets) ────────────────────
    # Use thin sheets at z = D1_top (bottom face of L1 metal); matches MSLPort
    # convention and avoids CFL pressure from thin Cu layers.
    L1_z = s.D1_top
    # Trace from port to pad-left-edge
    pec.AddBox(
        [x_port, -W_feed / 2, L1_z],
        [-W_pad / 2, W_feed / 2, L1_z],
        priority=10,
    )
    # Pad
    pec.AddBox(
        [-W_pad / 2, -W_pad / 2, L1_z],
        [W_pad / 2,  W_pad / 2,  L1_z],
        priority=10,
    )

    # Shrink GND-plane lateral extent so they don't reach the MUR boundary
    # (MUR misbehaves at metal surfaces). Leave 8+ cells of dielectric between
    # plane edge and sim boundary.
    plane_side = side - 12 * res_bulk

    # ─── L2 GND plane (thin sheet at z = L2_top, with optional hole) ─────
    L2_z = s.L2_top
    if option == "A":
        pec.AddBox([-plane_side, -plane_side, L2_z],
                   [plane_side,   plane_side,  L2_z], priority=10)
    else:
        # L2 sheet with rectangular hole under the pad. Build as 4 rectangles.
        rb = W_relief / 2
        pec.AddBox([-plane_side, -plane_side, L2_z], [-rb,         plane_side,  L2_z], priority=10)
        pec.AddBox([ rb,         -plane_side, L2_z], [plane_side,  plane_side,  L2_z], priority=10)
        pec.AddBox([-rb,          rb,         L2_z], [ rb,         plane_side,  L2_z], priority=10)
        pec.AddBox([-rb,         -plane_side, L2_z], [ rb,        -rb,          L2_z], priority=10)

    # ─── L3 plane (option B adds local GND island) ───────────────────────
    L3_z = s.L3_top
    if option == "B":
        pec.AddBox(
            [-W_relief / 2, -W_relief / 2, L3_z],
            [W_relief / 2,   W_relief / 2,  L3_z],
            priority=10,
        )

    # ─── L4 GND plane (thin sheet at z = L4_top, always solid) ───────────
    L4_z = s.L4_top
    pec.AddBox([-plane_side, -plane_side, L4_z],
               [plane_side,   plane_side,  L4_z], priority=10)

    # ─── Stitching vias around the relief (B and C only) ─────────────────
    # Approximated as thin rectangular posts (z-extent = L2_top to L3 or L4)
    # so they tie L2 GND to L3 island or L4 GND.
    if option in ("B", "C"):
        stitch_z_top = s.L2_top
        stitch_z_bot = s.L3_top if option == "B" else s.L4_top
        stitch_d = 200.0   # 0.2 mm via barrel diameter, approx as square post
        # 4 corners just outside the relief boundary
        for sx, sy in [
            ( W_relief / 2 + 250,  W_relief / 2 + 250),
            (-W_relief / 2 - 250,  W_relief / 2 + 250),
            ( W_relief / 2 + 250, -W_relief / 2 - 250),
            (-W_relief / 2 - 250, -W_relief / 2 - 250),
        ]:
            pec.AddBox(
                [sx - stitch_d/2, sy - stitch_d/2, stitch_z_bot],
                [sx + stitch_d/2, sy + stitch_d/2, stitch_z_top],
                priority=20,
            )

    # ─── Lumped port at far end of feed (between L1 trace and L2 GND) ────
    # With thin sheets: L1 is at z=D1_top, L2 GND is at z=L2_top.
    # Port spans the D1 prepreg gap from L2_top up to L1 (D1_top).
    port = FDTD.AddLumpedPort(
        1, 50,
        [x_port,                  -W_feed / 2, L2_z],
        [x_port + res_bulk / 2,    W_feed / 2, L1_z],
        "z", excite=1, priority=5,
    )

    # ─── Run ─────────────────────────────────────────────────────────────
    if run_dir is None:
        run_dir = os.path.join(tempfile.gettempdir(), f"atlc3_pad_{option}")
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir)
    FDTD.Run(run_dir, cleanup=True)

    # ─── Post-process ────────────────────────────────────────────────────
    freq = np.linspace(f_min, f_max, 401)
    port.CalcPort(run_dir, freq, ref_impedance=50)
    s11 = port.uf_ref / port.uf_inc

    return {
        "option": option,
        "freq": freq,
        "s11": s11,
        "run_dir": run_dir,
    }


def analyse(result: dict) -> dict:
    """Compute pad capacitance and RL at key frequencies."""
    freq = result["freq"]
    s11 = result["s11"]
    # Magnitude of S11 in dB
    s11_db = 20 * np.log10(np.maximum(np.abs(s11), 1e-9))

    # Approximate pad capacitance from S11 at low frequency (where the
    # cap dominates over the line transformation).
    # For a shunt cap on a Z0 line: Γ = -jωCZ₀/(2 + jωCZ₀)
    # At low f, |Γ| ≈ ωCZ₀/2  →  C ≈ 2|Γ|/(ωZ₀)
    # Use 2 GHz as the extraction point (well above DC noise, below pad/line resonance)
    f_extract = 2e9
    idx = int(np.argmin(np.abs(freq - f_extract)))
    g_at = abs(s11[idx])
    C_extracted = 2 * g_at / (2 * np.pi * f_extract * 50)

    return {
        "option": result["option"],
        "C_extracted_pF": C_extracted * 1e12,
        "s11_db": s11_db,
        "freq_ghz": freq / 1e9,
    }


def summary_print(results: list[dict]) -> None:
    """Print the comparison summary."""
    import math
    bands = [
        ("LTE B5",    0.85),
        ("LTE B3",    1.80),
        ("Wi-Fi 2.4", 2.40),
        ("Wi-Fi 5",   5.50),
        ("Top",       6.00),
    ]
    # Closed-form pad caps (from analytical calculation)
    cf = {
        "A": 75.6,
        "B": 28.6,
        "C": 15.6,
    }

    print()
    print("=" * 78)
    print("PAD RELIEF EM VALIDATION — 0.4 mm RF pad, 50 Ω feed, all four ports")
    print("=" * 78)
    print()
    print(f"{'Option':<10} {'C_em (fF)':>10} {'C_cf (fF)':>10} {'Δ%':>7}")
    print("-" * 45)
    for r in results:
        C_em = r["C_extracted_pF"] * 1000  # to fF
        C_cf = cf[r["option"]]
        dpct = 100 * (C_em - C_cf) / C_cf
        print(f"  {r['option']:<8} {C_em:>10.1f} {C_cf:>10.1f} {dpct:>+6.1f}%")

    print()
    print(f"{'Band':<14} {'f (GHz)':>7} ", end="")
    for r in results:
        print(f"{'opt ' + r['option']:>11}", end="")
    print()
    print("-" * (22 + 11 * len(results)))
    for name, f_ghz in bands:
        print(f"{name:<14} {f_ghz:>7.2f} ", end="")
        for r in results:
            i = int(np.argmin(np.abs(r["freq_ghz"] - f_ghz)))
            rl = -r["s11_db"][i]
            print(f"{rl:>9.1f}dB", end="")
        print()

    print()
    print("Analytical predictions (lower C = better RL at high f):")
    print("  A (solid L2):   75.6 fF →  23.0 dB RL @ 6 GHz")
    print("  B (ref → L3):   28.6 fF →  31.4 dB RL @ 6 GHz")
    print("  C (ref → L4):   15.6 fF →  36.6 dB RL @ 6 GHz")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option", type=str, choices=["A", "B", "C", "all"],
                        default="all", help="Which option to run")
    args = parser.parse_args()

    options = ["A", "B", "C"] if args.option == "all" else [args.option]
    results = []
    for opt in options:
        print(f"\n>>> Running Option {opt} ...")
        result = run_option(opt)
        analysis = analyse(result)
        results.append(analysis)

    if len(results) > 1:
        summary_print(results)


if __name__ == "__main__":
    main()
