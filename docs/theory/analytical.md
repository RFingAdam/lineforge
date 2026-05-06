# Analytical formulas (theory)

atlc3.0's Phase 1 solvers are closed-form approximations valid over published
geometric ranges. They run in microseconds and serve two roles:

1. **Fast path for the 7 standard PCB geometries** — most users never need the
   bitmap kernel.
2. **Cross-validation reference** for the Phase 2/3 numerical kernels — every
   bitmap-rasterized standard geometry must agree with the closed-form answer
   to within 1%.

## Microstrip — Hammerstad-Jensen (1980)

Effective permittivity:

$$
\varepsilon_{\text{eff}} = \frac{\varepsilon_r + 1}{2}
+ \frac{\varepsilon_r - 1}{2}\left(1 + \frac{10}{u}\right)^{-ab}
$$

where $u = W/H$ and:

$$
a = 1 + \frac{1}{49}\ln\!\frac{u^4 + (u/52)^2}{u^4 + 0.432}
+ \frac{1}{18.7}\ln\!\left(1 + (u/18.1)^3\right)
$$

$$
b = 0.564 \left(\frac{\varepsilon_r - 0.9}{\varepsilon_r + 3}\right)^{0.053}
$$

Characteristic impedance (zero-thickness strip):

$$
Z_{0,\text{air}} = \frac{\eta_0}{2\pi}
\ln\!\left(\frac{f}{u} + \sqrt{1 + \frac{4}{u^2}}\right),
\qquad
f = 6 + (2\pi - 6)\,e^{-(30.666/u)^{0.7528}}
$$

$$
Z_0 = \frac{Z_{0,\text{air}}}{\sqrt{\varepsilon_{\text{eff}}}}
$$

Finite-thickness Wheeler correction replaces $W$ with $W_{\text{eff}} =
W + \Delta W$ before substitution.

**Validity:** $0.05 \le W/H \le 20$, $\varepsilon_r \le 128$. Outside this
range, atlc3 emits an `out_of_range` warning and the user should fall back to
the bitmap kernel (Phase 2).

**Reference:** E. Hammerstad and Ø. Jensen, *Accurate Models for Microstrip
Computer-Aided Design*, IEEE MTT-S 1980; IPC-2141A Appendix A.

## Symmetric stripline — Cohn (1954) / Wadell

Wide-strip closed form:

$$
Z_0 = \frac{\eta_0}{\sqrt{\varepsilon_r}}
\cdot \frac{1}{4}\,\frac{1}{\dfrac{W}{B - T} + \dfrac{C_f'}{\pi}}
$$

where the fringing capacitance term:

$$
C_f' = \frac{B}{\pi(B - T)}
\left[
m\,\ln\!\frac{m+1}{m-1} - \ln\!\frac{m^2 - 1}{4}
\right],\quad m = \frac{2B}{B - T}
$$

**Validity:** $W/(B-T) > 0.35$, $T < 0.25\,B$.

**Reference:** S. B. Cohn, *Characteristic Impedance of the Shielded-Strip
Transmission Line*, IRE Trans. MTT, July 1954; Wadell §3.4.

## CPWG — Wen (1969) / Wadell

Elliptic-integral formula:

$$
\varepsilon_{\text{eff}} =
\frac{1 + \varepsilon_r\,(K(k')/K(k))(K(k_1)/K(k_1'))}
     {1 +  (K(k')/K(k))(K(k_1)/K(k_1'))}
$$

$$
Z_0 = \frac{60\pi}{\sqrt{\varepsilon_{\text{eff}}}}
\cdot \frac{1}{K(k)/K(k') + K(k_1)/K(k_1')}
$$

where:

$$
k = \frac{W}{W + 2S}, \qquad
k_1 = \frac{\tanh(\pi W/4H)}{\tanh(\pi(W + 2S)/4H)}
$$

and $K(\cdot)$ is the complete elliptic integral of the first kind, evaluated
in atlc3 via `scipy.special.ellipk`.

**Validity:** $W/H \ge 0.05$. Conductor thickness ignored when $T \ll W,S$.

**Reference:** C. P. Wen, IEEE MTT-S 1969; Wadell §3.6.4; IPC-2141A.

## Differential pairs — IPC-2141A coupling correction

For edge-coupled microstrip and stripline differential pairs, atlc3 uses the
empirical IPC-2141A coupling correction on the single-trace Z₀:

**Microstrip:** $Z_{\text{odd/even}} = Z_0\,(1 \mp 0.48\,e^{-0.96\,S/H})$

**Stripline:**  $Z_{\text{odd/even}} = Z_0\,(1 \mp 0.347\,e^{-2.9\,S/B})$

Differential and common-mode impedances follow from:

$$
Z_{\text{diff}} = 2\,Z_{\text{odd}}, \qquad
Z_{\text{common}} = Z_{\text{even}}/2
$$

For broadside-coupled stripline, atlc3 uses the parallel-plate Wadell §6.5
formula with finite-thickness correction.

**Caveat:** The IPC-2141A coupling exponential is empirical and loses accuracy
for tightly coupled pairs ($S/H < 0.5$). For exact differential analysis with
arbitrary geometries, use the Phase 4 direct odd/even-mode bitmap solver.

**References:** Wadell §6; IPC-2141A.

## Bibliography

- B. Wadell, *Transmission Line Design Handbook*, Artech House 1991.
- IPC-2141A, *Design Guide for High-Speed Controlled Impedance Circuit Boards.*
- E. Hammerstad and Ø. Jensen, IEEE MTT-S 1980.
- S. B. Cohn, IRE Trans. MTT, July 1954.
- C. P. Wen, IEEE MTT-S 1969.
