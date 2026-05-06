# 3-wire transmission line analysis

When a transmission line has three conductors (e.g. a directional coupler, a
microstrip with both signal traces and a ground bridge), there is no single
$Z_0$ — instead there are three pair-wise impedances.

## Y-decomposition

Following atlc2 (and standard microwave-engineering practice), model the
3-conductor line as three impedances in a "Y" configuration:

```
        ZoR
   +1 ───────●
              \
               ●─── center
              /
   −1 ───────●
        ZoB
   ───── ZoG ────── ground
```

A single atlc2/atlc3 run with **only two of the three conductors active** at
a time (the third floating) gives one of the three pair-wise impedances:

| Run | Active conductors | Result |
|-----|-------------------|--------|
| 1 | red (+1), blue (−1) only; green floats | $Z_{0,\text{GCZ}}$ ("green current zero") |
| 2 | red, green; blue floats | $Z_{0,\text{BCZ}}$ |
| 3 | green, blue; red floats | $Z_{0,\text{RCZ}}$ |

These satisfy:

$$
\begin{aligned}
Z_{0,\text{RCZ}} &= Z_{0,B} + Z_{0,G} \\
Z_{0,\text{GCZ}} &= Z_{0,R} + Z_{0,B} \\
Z_{0,\text{BCZ}} &= Z_{0,R} + Z_{0,G}
\end{aligned}
$$

Solve for the Y-impedances:

$$
Z_{0,R} = \tfrac{1}{2}(Z_{0,\text{GCZ}} + Z_{0,\text{BCZ}} - Z_{0,\text{RCZ}})
$$

(and analogous for $Z_{0,G}$, $Z_{0,B}$).

## Coupler odd/even modes

For a quarter-wave directional coupler (a common 3-wire geometry — two
parallel signal traces over a ground plane), it's standard to characterize
the **odd mode** (push-pull drive, $V_R = -V_B$) and **even mode** (in-phase
drive, $V_R = V_B$). atlc2 provides a shortcut: a single run with the green
ground floating, where the floating voltage equals the center voltage $V_C$:

$$
\begin{aligned}
Z_{0,B} &= Z_{0,\text{GCZ}} \cdot (V_\text{float} + 1) / 2 \\
Z_{0,R} &= Z_{0,\text{GCZ}} - Z_{0,B} \\
Z_{0,G} &= Z_{0,R} \\
Z_\text{ODD} &= 2 \cdot Z_{0,R} \\
Z_\text{EVEN} &= Z_{0,R}/2 + Z_{0,B}
\end{aligned}
$$

**Caveat from atlc2 docs:** this single-run approach is convenient but often
> 5% off due to the asymmetric charge distribution producing radiation that
the single-mode solver doesn't capture correctly. For accurate coupler
characterization, run two solves directly with the right boundary
conditions for each mode (Phase 4's `solve_differential` API).

## Net current and ZoG warning

If the grounded conductor carries a non-zero net current $I_\text{gnd}$
(reported as `Ignd` in atlc2 / `result.ignd_pct` in atlc3), the line is
radiating and the reported $Z_0$ is not a true characteristic impedance.

**Rule of thumb:** if $|I_\text{gnd}/I_R| > 4\%$, reconsider the geometry —
something is wrong with the assumed boundary conditions, or the line is
unsuitable as a transmission line as defined.

## References

- atlc2 docs §"A discussion of 3-wire transmission lines":
  <http://www.hdtvprimer.com/kq6qv/atlc2.html>.
- E. M. T. Jones et al., *Microwave Filters, Impedance-Matching Networks, and
  Coupling Structures*, Artech 1980, Chapter 5 (directional couplers).
- D. Pozar, *Microwave Engineering*, 4th ed., §7.6 (coupled-line couplers).
