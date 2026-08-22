#!/usr/bin/env python3
"""OpenEMS short L1↔L3 via: actual via geometry from L3 SIG1 transition.

The user's L3 SIG1 trace transitions from top (L1) down to L3 via short
through-vias, NOT all the way to L8. Modeling the actual length:
  L1 top to L3 = 1.4 + 2.73 + 1.4 + 3.5 + 0.345 ≈ 9.4 mil = 239 μm

Drive structure: short 50 Ω microstrip feed on L1 (over L2 GND), via barrel
through L2 antipad, lands on L3 trace inside the L2-L4 cavity. L4 PWR1 is
the lower reference for the L3 trace.

This is much shorter than a through-via (37 mil), so via parasitics should
be smaller and the simulation should be more stable.
"""

import os
import shutil
import tempfile

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0

unit = 1e-6

# Stack-up positions (μm), z=0 at L1 top
L1_top = 0.0
L2_top = -(1.4 + 2.73) * 25.4  # = -105 μm
L3_top = L2_top - (1.4 + 3.5) * 25.4  # = -230 μm
L4_top = L3_top - (0.689 + 5.3) * 25.4  # = -382 μm

# Via geometry
drill_d = 203.2  # 8 mil
pad_d = 406.4  # 16 mil
antipad_d = 762.0  # 30 mil

# Feed traces: L1 microstrip on top, L3 stripline below
L1_trace_w = 175.0  # ~6.9 mil for ~50 Ω over L2 GND with H = 2.73 mil
L3_trace_w = 74.2  # 2.92 mil. The recommended narrowed width

feed_l = 3000.0  # 3 mm feed line
side = 5000.0

# Trace and plane thicknesses (model planes as finite for antipad cuts)
plane_t = 35.6  # 1.4 mil
trace_t = 17.5  # 0.689 mil for L3, use same for simplicity

f_max = 8e9
f_min = 0.1e9

FDTD = openEMS(NrTS=200000, EndCriteria=1e-5)
FDTD.SetGaussExcite((f_max + f_min) / 2, (f_max - f_min) / 2)
FDTD.SetBoundaryCond(["MUR"] * 6)

CSX = ContinuousStructure()
FDTD.SetCSX(CSX)
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(unit)

res = C0 / (f_max * np.sqrt(4.0)) / unit / 30
res_via = drill_d / 4  # ~50 μm in via region
third = np.array([2 * res / 3, -res / 3]) / 4

# X: fine near via, microstrip feed extends -x from via
mesh.AddLine("x", np.linspace(-antipad_d, antipad_d, 30))
mesh.AddLine("x", [-feed_l - antipad_d / 2, -antipad_d / 2, antipad_d / 2, feed_l + antipad_d / 2])
mesh.AddLine("x", [-side, side])
mesh.SmoothMeshLines("x", res)

# Y: fine across feed traces and via region
mesh.AddLine("y", np.linspace(-antipad_d, antipad_d, 20))
mesh.AddLine("y", [-side, -L1_trace_w / 2, 0, L1_trace_w / 2, side])
mesh.AddLine("y", [-L3_trace_w / 2 - third[0], L3_trace_w / 2 + third[0]])
mesh.SmoothMeshLines("y", res)

# Z: through stack: L1 to L4 with antipad cuts
mesh.AddLine("z", [L4_top, L3_top, L2_top, L1_top])
mesh.AddLine("z", np.linspace(L4_top, L1_top, 20))
mesh.SmoothMeshLines("z", res / 2)

# Substrate: εr=4 throughout (mid-FR4 average)
substrate = CSX.AddMaterial("FR4", epsilon=4.0)
substrate.AddBox(
    [-side - 1000, -side - 1000, L4_top - 200],
    [side + 1000, side + 1000, L1_top + 200],
)

pec = CSX.AddMetal("PEC")

# L2 GND plane (full extent, with antipad punch later)
pec.AddBox(
    [-side, -side, L2_top - plane_t / 2],
    [side, side, L2_top + plane_t / 2],
    priority=10,
)
# L4 PWR1 plane (treat as GND)
pec.AddBox(
    [-side, -side, L4_top - plane_t / 2],
    [side, side, L4_top + plane_t / 2],
    priority=10,
)
# Antipad cutouts in L2 (signal via passes through it)
air = CSX.AddMaterial("air", epsilon=1.0)
air.AddCylinder(
    [0, 0, L2_top - plane_t],
    [0, 0, L2_top + plane_t],
    antipad_d / 2,
    priority=20,
)

# Signal via barrel from L1 to L3 (short via)
pec.AddCylinder(
    [0, 0, L3_top - trace_t / 2],
    [0, 0, L1_top + plane_t],
    drill_d / 2,
    priority=30,
)

# L1 microstrip feed (extends in -x from via pad)
pec.AddBox(
    [-feed_l - pad_d / 2, -L1_trace_w / 2, L1_top - plane_t / 2],
    [-pad_d / 2, L1_trace_w / 2, L1_top + plane_t / 2],
    priority=10,
)
# L1 via pad (annular ring around via at L1)
pec.AddCylinder(
    [0, 0, L1_top - plane_t / 2],
    [0, 0, L1_top + plane_t / 2],
    pad_d / 2,
    priority=30,
)

# L3 stripline trace (extends in +x from via pad)
pec.AddBox(
    [pad_d / 2, -L3_trace_w / 2, L3_top - trace_t / 2],
    [feed_l + pad_d / 2, L3_trace_w / 2, L3_top + trace_t / 2],
    priority=10,
)
# L3 via pad
pec.AddCylinder(
    [0, 0, L3_top - trace_t / 2],
    [0, 0, L3_top + trace_t / 2],
    pad_d / 2,
    priority=30,
)

# Lumped ports
# Port 1: L1 microstrip end: between L1 trace top and L2 GND
port1 = FDTD.AddLumpedPort(
    1,
    50,
    [-feed_l - pad_d / 2, -L1_trace_w / 2, L2_top + plane_t / 2],
    [-feed_l - pad_d / 2 + res, L1_trace_w / 2, L1_top - plane_t / 2],
    "z",
    excite=1,
    priority=5,
)
# Port 2: L3 stripline end: between L3 trace and L4 PWR1
port2 = FDTD.AddLumpedPort(
    2,
    50,
    [feed_l + pad_d / 2 - res, -L3_trace_w / 2, L4_top + plane_t / 2],
    [feed_l + pad_d / 2, L3_trace_w / 2, L3_top - trace_t / 2],
    "z",
    priority=5,
)

sim_path = os.path.join(tempfile.gettempdir(), "lineforge_via_short_sim")
if os.path.isdir(sim_path):
    shutil.rmtree(sim_path)
FDTD.Run(sim_path, cleanup=True)

freq = np.linspace(f_min, f_max, 401)
port1.CalcPort(sim_path, freq, ref_impedance=50)
port2.CalcPort(sim_path, freq, ref_impedance=50)

s11 = port1.uf_ref / port1.uf_inc
s21 = port2.uf_ref / port1.uf_inc

print()
print("=== L1→L3 short via (~9.4 mil), 8/16/30 mil drill/pad/antipad ===")
print(f"{'f (GHz)':>7} {'|S11| dB':>9} {'|S21| dB':>9} {'VSWR':>6}")
print("-" * 36)
for f, s11i, s21i in zip(freq[::40], s11[::40], s21[::40], strict=False):
    g = abs(s11i)
    vswr = (1 + g) / (1 - g) if g < 0.99 else 999.0
    s21_db = 20 * np.log10(np.abs(s21i)) if abs(s21i) > 0 else -300
    print(f"{f/1e9:7.2f} {20*np.log10(g):9.1f} {s21_db:9.2f} {vswr:6.2f}")

band = (freq >= 0.8e9) & (freq <= 6e9)
worst_s11 = np.max(np.abs(s11[band]))
print()
print(
    f"  Worst |S11| in 0.8–6 GHz: {20*np.log10(worst_s11):.1f} dB at {freq[band][np.argmax(np.abs(s11[band]))]/1e9:.2f} GHz"
)
print(
    "  Closed-form analyze_via (this short via, L=3.6 nH C=3.0 pF): self-res 1.54 GHz, IL ≈ -7 dB at 6 GHz"
)
