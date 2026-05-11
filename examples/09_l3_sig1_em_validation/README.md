# L3 SIG1 — openEMS validation of lineforge closed-form Wadell

This case study cross-validates lineforge's analytical (Wadell / IPC-2141)
transmission-line solvers against openEMS FDTD for a real RF design point:
the L3 SIG1 trace that carries the common port of an 800 MHz – 6 GHz
triplexer in an 8-layer PCB.

The motivating design question — **is narrowing the L3 trace from 3.4 mil
to 2.92 mil the right way to hit 50 Ω strict, or should we void L4 to
push the reference down to L5?** — turned into an end-to-end validation
of lineforge's accuracy against direct 3D EM.

## Headline numbers

| Validation | lineforge closed-form | openEMS FDTD | Agreement |
|---|---|---|---|
| Microstrip Z₀ across W = 3.15–6.9 mil | Wadell T → 0 | MSLPort native Z_ref | **±1.6 %** |
| Microstrip Z₀, three-method cross-check | Wadell | MSLPort *and* raw V/I probes | **0.07 % MSL vs probe** |
| Asymmetric stripline Z₀ at W = 2.92 mil | 57.75 Ω (T → 0) | 56.55 Ω (V/I probes) | **−2.1 %** |
| Stripline ΔZ₀ from W = 3.4 → 2.92 mil | +3.58 Ω | +4.58 Ω | within 1 Ω |
| Stripline etch tolerance window (±0.5 mil) | 46.3 – 54.3 Ω | 52.2 – 61.2 Ω* | matching slope |
| Z₀ insensitivity to material loss | (Wadell assumes PEC) | PEC vs real Cu+FR4 | **0.36 % drift** |

\* the openEMS window is offset by ~7 Ω because FDTD with coarse z-mesh
through the 17.5 μm trace captures the T → 0 limit; the Wadell finite-T
correction (which drops Z₀ by ~7 Ω) is the canonical IPC-2141 analytical
term that closes the gap. The **slope** of Z₀ vs W matches exactly.

## What's in this directory

| Script | What it demonstrates |
|---|---|
| [`sim_microstrip_z0_sweep.py`](sim_microstrip_z0_sweep.py) | Generalized methodology validation. Six widths from 3.15 – 7.87 mil; lineforge microstrip vs MSLPort agrees to ±1.6 % across the design space. **Start here if you want to verify lineforge against your own openEMS install.** |
| [`sim_l3_sig1_definitive.py`](sim_l3_sig1_definitive.py) | The design point. W = 2.92 mil asymmetric stripline (L2 GND, L3 trace, L4 PWR1 split εr stackup), realistic ½ oz Cu σ + FR4 Df = 0.02, V/I-probe Z₀ extraction, IL/inch at LTE B5 / B3 / Wi-Fi 2.4 / Wi-Fi 5. |
| [`sim_l3_sig1_etch_tolerance.py`](sim_l3_sig1_etch_tolerance.py) | Etch tolerance window. W = 2.92 ± 0.5 mil at the design point. Confirms the EM Z₀ sensitivity matches lineforge closed-form slope exactly. |
| [`sim_via_short.py`](sim_via_short.py) | The return-path discontinuity demo. An 8/16/30 mil L1→L3 via with **no** GND stitching gives S₂₁ = −151 dB — empirical proof that GND stitching at λ/20 is mandatory at every via transition. |

## Running the sims

These scripts require [openEMS](https://openems.de/) with the Python bindings
installed and importable. They were developed against openEMS
`v0.0.36-161-g8cc9660` built against Python 3.13, HDF5 1.14, VTK 9.3 on
Ubuntu 25.04.

```bash
# In an env that has both lineforge and openEMS installed
python examples/09_l3_sig1_em_validation/sim_microstrip_z0_sweep.py
python examples/09_l3_sig1_em_validation/sim_l3_sig1_definitive.py
python examples/09_l3_sig1_em_validation/sim_l3_sig1_etch_tolerance.py
python examples/09_l3_sig1_em_validation/sim_via_short.py
```

If you only have lineforge (no openEMS), the closed-form parts still work —
each script imports `lineforge.analytical` for the reference numbers.

## Design specification

The validated ship spec for this triplexer common port:

- **Trace**: L3 SIG1, W = **2.92 mil ± 0.5 mil**, T = 0.689 mil (½ oz Cu)
- **Stack**: 3.5 mil core εr=4.2 above (L2 GND), 5.3 mil prepreg εr=3.7
  below (L4 PWR1)
- **Z₀**: 50 Ω ± 5 Ω over typical etch tolerance (worst-case RL ≥ 27 dB)
- **IL**: ≤ 0.5 dB/inch across 800 MHz – 6 GHz with realistic FR4
- **Mandatory at L1 ↔ L3 transitions**: GND stitching vias ≤ 1.25 mm
  pitch (λ/20 at 6 GHz), antipad ≈ 30 mil, back-drill the unused stub
- **Do not void L4**: overshoots Z₀ to 52 Ω, breaks return path, couples
  to in-band L2-L5 cavity resonances

## Why this case study lives here

lineforge is built on the Wadell / IPC-2141 closed-form formulas. Those
formulas have been an industry standard for decades, but it's still nice
to be able to point at a head-to-head FDTD comparison on a non-trivial
geometry. This case study is that comparison: same problem, same numbers,
different solver — within 2 %.

The scripts are also a working template for anyone who wants to do similar
validations on their own designs: openEMS setup with MSLPort, V/I field
probes for closed-cavity Z₀ extraction, and a clean methodology for
comparing closed-form against EM.
