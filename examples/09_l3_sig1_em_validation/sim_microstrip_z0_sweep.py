#!/usr/bin/env python3
"""OpenEMS microstrip Z0 extraction — proper sweep using MSLPort native Z_ref.

Sweeps trace width to validate Wadell closed-form across the design space.
For each width:
  • Compute native line Z_ref from MSLPort (V/I integration of EM TEM mode)
  • Compare to closed-form Wadell (with the same T → 0 assumption)
  • Verify Wadell matches EM to ≤ 2%

Geometry: H = 2.73 mil prepreg, εr = 3.7, T → 0 (MSLPort intrinsic).
"""
import os
import shutil
import tempfile
import numpy as np

from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0


def run_msl_z0(trace_w_um, trace_l_um=25400.0, sub_h_um=69.34, sub_er=3.7,
               f_max=8e9, f_min=0.1e9, sim_label="msl"):
    """Run an MSLPort microstrip sim and return the EM-extracted Z0 sweep."""
    unit = 1e-6

    side = max(30 * trace_w_um, 30 * sub_h_um)
    air = 15 * sub_h_um

    FDTD = openEMS(NrTS=200000, EndCriteria=1e-5)
    FDTD.SetGaussExcite((f_max + f_min) / 2, (f_max - f_min) / 2)
    FDTD.SetBoundaryCond(["PML_8", "PML_8", "MUR", "MUR", "PEC", "MUR"])

    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(unit)

    res = C0 / (f_max * np.sqrt(sub_er)) / unit / 50
    third = np.array([2 * res / 3, -res / 3]) / 4

    mesh.AddLine("x", [-trace_l_um, trace_l_um])
    mesh.SmoothMeshLines("x", res)
    mesh.AddLine("y", 0)
    mesh.AddLine("y",  trace_w_um/2 + third)
    mesh.AddLine("y", -trace_w_um/2 - third)
    mesh.SmoothMeshLines("y", res / 4)
    mesh.AddLine("y", [-side, side])
    mesh.SmoothMeshLines("y", res)
    mesh.AddLine("z", np.linspace(0, sub_h_um, 5))
    mesh.AddLine("z", sub_h_um + air)
    mesh.SmoothMeshLines("z", res)

    substrate = CSX.AddMaterial("substrate", epsilon=sub_er)
    substrate.AddBox(
        [-trace_l_um, -side, 0],
        [trace_l_um, side, sub_h_um],
    )

    pec = CSX.AddMetal("PEC")
    port1 = FDTD.AddMSLPort(
        1, pec,
        [-trace_l_um, -trace_w_um/2, sub_h_um],
        [0,            trace_w_um/2, 0],
        "x", "z",
        excite=-1,
        FeedShift=10 * res,
        MeasPlaneShift=trace_l_um / 3,
        priority=10,
    )
    port2 = FDTD.AddMSLPort(
        2, pec,
        [trace_l_um,  -trace_w_um/2, sub_h_um],
        [0,            trace_w_um/2, 0],
        "x", "z",
        MeasPlaneShift=trace_l_um / 3,
        priority=10,
    )

    sim_path = os.path.join(tempfile.gettempdir(), f"atlc3_{sim_label}_w{int(trace_w_um*10)}")
    if os.path.isdir(sim_path):
        shutil.rmtree(sim_path)
    FDTD.Run(sim_path, cleanup=True)

    freq = np.linspace(f_min, f_max, 401)
    # Don't pass ref_impedance — let MSLPort compute Z_ref natively
    port1.CalcPort(sim_path, freq)
    port2.CalcPort(sim_path, freq)

    # port1.Z_ref is now the native line Z0 from EM
    Z0_em = port1.Z_ref
    beta = port1.beta

    # Compute εr_eff from beta = ω/c · sqrt(εr_eff)
    omega = 2 * np.pi * freq
    er_eff_em = (np.real(beta) * C0 / omega) ** 2

    return {
        "freq": freq,
        "Z0_em": Z0_em,
        "beta": beta,
        "er_eff_em": er_eff_em,
        "trace_w_um": trace_w_um,
        "sub_h_um": sub_h_um,
        "sub_er": sub_er,
    }


def closed_form_z0(W_mil, T_mil, H_mil, er):
    """Closed-form Wadell microstrip via atlc3."""
    import sys
    sys.path.insert(0, os.path.expanduser("~/projects/github/atlc3/src"))
    from atlc3.analytical import microstrip
    from atlc3.geometry.types import Microstrip
    g = Microstrip(W=f"{W_mil}mil", T=f"{T_mil}mil", H=f"{H_mil}mil", er=er)
    r = microstrip(g)
    return r.z0, r.eps_eff


if __name__ == "__main__":
    # Sweep widths (in microns), T → 0 to match MSLPort
    sub_h_um = 69.34   # 2.73 mil
    sub_er = 3.7
    H_mil = sub_h_um / 25.4

    widths_um = [80.0, 100.0, 125.34, 150.0, 175.0, 200.0]   # 3.15 to 7.87 mil
    print("=" * 88)
    print("MICROSTRIP Z₀ SWEEP — openEMS MSLPort vs Wadell closed-form (T → 0)")
    print(f"  H = {sub_h_um:.2f} μm ({H_mil:.3f} mil), εr = {sub_er}")
    print("=" * 88)
    print(f"{'W (μm)':>8} {'W (mil)':>8} {'Z₀ EM':>9} {'Z₀ CF':>9} {'Δ Ω':>7} {'Δ %':>6} {'εr_eff EM':>10} {'εr_eff CF':>10}")
    print("-" * 88)

    results = []
    for w_um in widths_um:
        out = run_msl_z0(w_um, sub_h_um=sub_h_um, sub_er=sub_er, sim_label=f"sw{int(w_um)}")
        # Take mid-band Z₀ (avoid edge effects)
        idx = (out["freq"] >= 1e9) & (out["freq"] <= 6e9)
        Z0_em = np.mean(np.real(out["Z0_em"][idx]))
        er_eff_em = np.mean(out["er_eff_em"][idx])

        W_mil = w_um / 25.4
        Z0_cf, er_eff_cf = closed_form_z0(W_mil, T_mil=0.001, H_mil=H_mil, er=sub_er)

        delta = Z0_em - Z0_cf
        delta_pct = 100 * delta / Z0_cf

        print(f"{w_um:8.2f} {W_mil:8.3f} {Z0_em:8.2f}Ω {Z0_cf:8.2f}Ω {delta:+7.2f} {delta_pct:+6.2f}% {er_eff_em:10.3f} {er_eff_cf:10.3f}")
        results.append({"w_um": w_um, "Z0_em": Z0_em, "Z0_cf": Z0_cf,
                        "er_eff_em": er_eff_em, "er_eff_cf": er_eff_cf})

    print()
    print("Mid-band (1–6 GHz) average Z₀ comparison.")
    print("  → If MSLPort matches Wadell within ±2 % across widths, closed-form is validated")
    print("    for the design-space sweep used in this analysis.")
