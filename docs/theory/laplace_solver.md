# C and Gp — the Laplace solver

lineforge's bitmap C/Gp pipeline solves the 2D electrostatic Laplace equation
on a Cartesian pixel grid:

$$
\nabla \cdot (\varepsilon_r \nabla V) = 0
$$

with **Dirichlet boundary conditions** at conductor pixels (V = +1, −1, or 0)
and **homogeneous Dirichlet at the outer boundary** (V = 0 at infinity,
approximated via the open-boundary grid extension).

## 5-point FD stencil with εr coupling

For a uniform Cartesian grid of pixel side $h$, the standard 5-point FD scheme
with εr varying per cell is:

$$
V_{i,j}\,(\alpha_E + \alpha_W + \alpha_N + \alpha_S)
= \alpha_E V_{i,j+1} + \alpha_W V_{i,j-1} + \alpha_N V_{i-1,j} + \alpha_S V_{i+1,j}
$$

where each $\alpha_X$ is the εr at the cell-edge between (i,j) and the named
neighbor — lineforge uses the **arithmetic mean** of the two adjacent pixels
(matching atlc v1):

$$
\alpha_E = \tfrac{1}{2}(\varepsilon_{r,(i,j)} + \varepsilon_{r,(i,j+1)})
$$

(and similarly for W, N, S).

For piecewise-constant material maps, the arithmetic-mean stencil produces a
solution accurate to second-order in $h$ inside each material region, and
first-order at material interfaces.

## Successive over-relaxation (SOR)

The iterative scheme:

$$
V_{i,j}^{(k+1)} = V_{i,j}^{(k)} + \omega \left(
  \frac{\alpha_E V_{i,j+1}^{(k)} + \alpha_W V_{i,j-1}^{(k)}
        + \alpha_N V_{i-1,j}^{(k)} + \alpha_S V_{i+1,j}^{(k)}}
       {\alpha_E + \alpha_W + \alpha_N + \alpha_S}
  - V_{i,j}^{(k)}
\right)
$$

Optimal ω for an $N \times N$ Dirichlet problem is

$$
\omega_{\text{opt}} = \frac{2}{1 + \sin(\pi/N)} \approx 2 - \frac{2\pi}{N}
$$

For typical PCB usermaps ($N \sim 100$–$1000$), lineforge's default
$\omega = 1.9$ is close to optimal.

## Algebraic multigrid

For grids ≳ $1000 \times 1000$, SOR's iteration count grows as $\mathcal{O}(N^2)$,
which becomes prohibitive. lineforge falls back to PyAMG's smoothed-aggregation
multigrid, which converges in $\mathcal{O}(N)$ work — typically a 5–10× speedup
on big grids.

## Capacitance from the field

After convergence, the per-unit-length capacitance is extracted via the
energy integral:

$$
C = \frac{\varepsilon_0}{V^2} \iint \varepsilon_r |\mathbf{E}|^2 \, dA
\quad [\mathrm{F/m}]
$$

where $V$ is the applied voltage difference (2.0 for a ±1 driven line). The
gradient $\mathbf{E} = -\nabla V$ is computed via central differences on the
solved $V$ field.

## Effective εr, Z₀, and L

A **second** Laplace solve is run with $\varepsilon_r \equiv 1$ everywhere
(vacuum). Call the resulting capacitance $C_\text{vacuum}$. Then:

$$
L = \frac{\mu_0 \varepsilon_0}{C_\text{vacuum}}, \qquad
\varepsilon_\text{eff} = \frac{C}{C_\text{vacuum}}
$$

$$
v_p = \frac{c}{\sqrt{\varepsilon_\text{eff}}}, \qquad
Z_0 = \frac{1}{v_p \cdot C} = \sqrt{\frac{L}{C}}
$$

This is the same trick atlc v1 uses, and matches Wadell's textbook approach.

## Dielectric loss (Gp)

For a lossy dielectric with loss tangent $\tan\delta$, the per-unit-length
shunt conductance at angular frequency $\omega$ is:

$$
G_p = \omega \cdot \frac{\varepsilon_0}{V^2}
\iint \varepsilon_r \tan\delta \, |\mathbf{E}|^2 \, dA
\quad [\mathrm{S/m}]
$$

Frequency-dependent. For a uniform dielectric this simplifies to
$G_p = \omega C \tan\delta$.

## Open boundary

Phase 2 extends the usermap by edge replication out to a 3200×3200 effective
area, then uses zero-Dirichlet at the outer edge. Phase 4's polish work
implements atlc2's progressive 8×-coarse-pixel extension, which reduces the
equation count for very large unshielded simulations without sacrificing
accuracy in the field-energy regions that matter for C.

## References

- atlc v1 source (GPL): <http://atlc.sourceforge.net/>, especially `do_fd_calculation.c`.
- atlc2 docs §"C and Gp": <http://www.hdtvprimer.com/kq6qv/atlc2.html>.
- B. Wadell, *Transmission Line Design Handbook*, Artech 1991, §3.2 (relaxation methods).
- W. Press et al., *Numerical Recipes*, §17.7 (SOR convergence).
- PyAMG: <https://pyamg.readthedocs.io/>.
