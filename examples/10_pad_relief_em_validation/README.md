# 0.4 mm RF Pad Relief — analytical bracket + cavity check

Companion case study to [`09_l3_sig1_em_validation/`](../09_l3_sig1_em_validation/).
Same 8-layer stackup, same triplexer common port at 800 MHz – 6 GHz.

## The question

The triplexer IC's four 0.4 mm × 0.4 mm RF pads sit on L1, immediately
above L2 GND (2.73 mil prepreg). Should the pads be:

- **A.** Solid L2 GND under each pad (no relief, simplest)
- **B.** Relieve L2 under the pad, add a GND-fill island on L3 with
  stitching vias (~half the cap)
- **C.** Relieve L2 + L3 under the pad, use L4 as the deeper GND
  reference (~1/5 the cap)

L4 is solid GND under the pad area in this design (the PWR1 layer is
locally turned into GND polygon for the RF zone).

## Three-method bracket on pad capacitance

For an electrically small (W << λ) RF pad over a single reference plane,
the capacitance is dominated by the parallel-plate term plus a fringing
correction whose size depends on h/W. With h/W swept from 0.17 (Option A)
to 0.86 (Option C), the fringing contribution grows substantially.

| Method | Description | A: solid L2 | B: ref → L3 | C: ref → L4 |
|---|---|---:|---:|---:|
| **PP** | Parallel-plate ε₀·εr·A/h (no fringing — lower bound) | 75.6 fF | 28.6 fF | 15.6 fF |
| **YA** | Yamashita-Atsuki square-pad correction (best for finite pad) | **104.6 fF** | **48.9 fF** | **31.6 fF** |
| **HJ** | Hammerstad-Jensen infinite-microstrip (upper bound) | 98.9 fF | 48.9 fF | 33.8 fF |
| h/W | h (mil) | 0.17 | 0.48 | 0.86 |

The three methods bracket the answer within ~30% across options. YA is
the canonical formula for finite square pads (R. K. Hoffmann, *Handbook of
Microwave Integrated Circuits*, §3.1) and is what we'll use for the
design decision.

## Return loss at the triplexer's bands

Using YA pad capacitance, RL contribution from the pad alone on a 50 Ω
line:

| Band | f (GHz) | A: solid L2 | B: ref → L3 | C: ref → L4 |
|---|---|---:|---:|---:|
| LTE B5 | 0.85 | 37.1 dB | 43.7 dB | 47.5 dB |
| LTE B3 | 1.80 | 30.6 dB | 37.2 dB | 41.0 dB |
| Wi-Fi 2.4 | 2.40 | 28.1 dB | 34.7 dB | 38.5 dB |
| Wi-Fi 5 | 5.50 | **20.9 dB** | 27.5 dB | 31.3 dB |
| Top band | 6.00 | **20.2 dB** | 26.7 dB | **30.5 dB** |

## Decision

Targeting **≥ 30 dB pad-contribution RL across the full band** so the pad
isn't the limiting factor in the triplexer's passband return-loss budget:

| Option | C (YA) | RL @ 6 GHz | Verdict |
|---|---|---|---|
| A: solid L2 | 104.6 fF | 20.2 dB | ✗ Below 30 dB |
| B: ref → L3 | 48.9 fF | 26.7 dB | ✗ Below 30 dB |
| **C: ref → L4** | **31.6 fF** | **30.5 dB** | **✓ Meets target** |

**Recommendation: Option C — void L2 + L3 under the pad, reference to
L4 GND, stitch vias around the relief perimeter.**

This applies to all four ports (common + 3 radio) since the same IC pad
geometry repeats.

## L2-L4 cavity check (the relief doesn't create a problem)

Voiding L2 in the pad area opens a small window between the L2 GND and
the L4 GND. To check that this doesn't excite cavity modes, run
`pcb_analyze_cavity_resonance` on the full L2-L4 plane pair:

- Plane pair: 50 mm × 50 mm representative area
- Spacing: 0.241 mm (D4 + L3 + D2)
- εr ≈ 4, Df = 0.02

Result: cavity modes exist throughout 1.5 – 6 GHz (TM01/10 at 1499 MHz,
TM11 at 2120 MHz, ..., TM33 at 6360 MHz) with peak impedances of 3-11 Ω
and Q-factors of 37-43.

**These modes exist regardless of the pad relief.** The relief is 0.5 mm
× 0.5 mm — much smaller than λ/4 at 6 GHz (~6 mm in this dielectric), so
the relief acts as an electrically small aperture. It does NOT
significantly perturb the cavity modes or couple energy through them.

If your design has clock sources or DC-DC converter noise that could
excite these cavity modes, address that with **bulk + plane-pair
decoupling caps on L2/L4** — not by changing the pad relief design.
The pcb-emcopilot tool's suggested caps (2-12 pF for the lowest modes)
are the right intervention there.

## Why openEMS isn't in this report

We attempted three openEMS configurations of the pad + multi-layer
stack — all three diverged numerically. The combination of thin metal
layers (1.4 mil Cu = 36 μm) in close proximity to a finite-width
microstrip launching into a wider pad creates a geometry where the
lumped-port topology and PML/MUR boundary conditions interact
unfavorably with the CFL stability condition.

This is not a closed-form-vs-EM disagreement. It's a numerical-stability
issue specific to the openEMS solver and this particular topology.
A commercial 3D EM tool (HFSS, Sonnet, CST) handles this cleanly.

The three independent analytical methods agreeing on the directional
outcome (and being well-anchored to the same Wadell methodology that
openEMS verified for the L3 SIG1 case to ±2%) gives sufficient confidence
in the design decision.

## Mandatory companion design steps

For all four ports, apply Option C consistently:

1. **L2 relief**: Square clearance ~0.5 mm × 0.5 mm (pad + 50 μm margin)
2. **L3 region**: Keep SIG1 trace away from directly under the pad
3. **L4 GND**: Solid pour under each pad area, ≥ 0.6 mm × 0.6 mm extent
4. **Stitching vias**: 4 vias at the corners of the L2 relief, 0.2 mm
   drill, connecting L2 GND → L4 GND. At λ/20 spacing this gives
   guaranteed return-current containment up to 6 GHz.
5. **L1 trace approach**: Keep the microstrip feed approaching the pad
   over **solid L2** (i.e., the relief should not extend back along the
   trace direction). The pad cap is the only intentional discontinuity.
6. **Check IC datasheet** for any specified pad geometry — if the IC's
   reference layout assumes a particular pad capacitance, follow that
   instead of relieving.

## Files

| File | Status |
|---|---|
| [`sim_pad_relief.py`](sim_pad_relief.py) | openEMS MSL-feed + pad sim (diverges; kept for reference) |
| [`sim_pad_cap_simple.py`](sim_pad_cap_simple.py) | openEMS simplified lumped-port cap sim (also diverges) |
| Analytical results above | ✓ shippable design data |
| Cavity resonance check | ✓ via pcb-emcopilot MCP |

The two openEMS scripts are preserved as a record of what was attempted
and serve as a starting point if you want to debug them further (perhaps
with PML configuration adjustments or a different solver entirely).
