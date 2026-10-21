# L and Rs. The Faraday solver

lineforge's Phase 3 L/Rs pipeline solves a 2D **partial-element equivalent
circuit** (PEEC) system, equivalent to atlc2's "one equation per conductor
pixel" Faraday's-law formulation.

## Per-pixel Ohm + Faraday

Each conductor pixel $n$ carries an unknown longitudinal current $i_n$
(out of the page). For a TEM-mode line driven by a longitudinal voltage drop
$V_c$ on conductor $c$:

$$
V_c = (R_n + j\omega L_\text{partial}) \cdot \mathbf{i}
\quad\text{ for each pixel } n \in c
$$

Expanded:

$$
V_c = \frac{\rho_n}{A_\text{pixel}} \, i_n
+ j\omega \cdot \frac{\mu_0}{2\pi} \sum_k i_k \ln\!\frac{d_\text{ref}}{r_{nk}}
$$

where:
- $\rho_n$ is the resistivity of pixel $n$.
- $A_\text{pixel} = h^2$ is the pixel area (h = pixel side).
- $r_{nk}$ is the center-to-center distance between pixels $n$ and $k$.
- $d_\text{ref}$ is a reference distance (lineforge uses the simulation extent).

The self-pixel term ($n = k$) uses an analytic approximation based on a square
cross-section: $L_\text{self} \approx (\mu_0/2\pi)(\ln(1/h) + 1/2)$.

## Constraint: net current per conductor

For each conductor $c$, lineforge imposes the driver current via:

$$
\sum_{n \in c} i_n = I_c
$$

For a 2-wire line we drive $I_{+1} = +1\text{ A}$ and $I_{-1} = -1\text{ A}$.
A grounded third conductor gets $I_\text{gnd} = 0$ (a Lagrange-multiplier-like
constraint). Floating conductors impose $\sum_{n \in c_\text{float}} i_n = 0$.

## Linear system

The result is an $(N + n_c) \times (N + n_c)$ complex system where $N$ is the
total conductor pixel count and $n_c$ is the number of conductors:

$$
\begin{bmatrix}
\mathbf{Z}_{\text{partial}} & -\mathbf{C}^\top \\
\mathbf{C} & 0
\end{bmatrix}
\begin{bmatrix} \mathbf{i} \\ \mathbf{V}_c \end{bmatrix}
=
\begin{bmatrix} 0 \\ \mathbf{I}_c \end{bmatrix}
$$

where $\mathbf{C}$ is the conductor-membership indicator. The pixel-pixel
sub-block $\mathbf{Z}_\text{partial}$ is dense (every pixel couples to every
other via the logarithm); the $\mathbf{C}$ block is sparse.

## Solver

For $N < 500$, lineforge uses dense `numpy.linalg.solve`. For larger $N$, it
falls back to scipy.sparse.linalg `bicgstab` with an `spilu` preconditioner.

## Extraction of L and R

After solving, the longitudinal impedance per unit length is just:

$$
Z_\text{line}/m = V_{+1} - V_{-1}
\quad (\text{since we drove with } I = 1\text{ A})
$$

with

$$
R/m = \mathrm{Re}(Z_\text{line}/m), \qquad
L/m = \frac{\mathrm{Im}(Z_\text{line}/m)}{\omega}
$$

## Skin-effect restriction

For thick conductors at high frequency, the AC current density falls off
exponentially with depth from the conductor surface. The characteristic
length is the skin depth:

$$
\delta = \sqrt{\frac{2\rho}{\omega \mu}}
$$

lineforge (matching atlc2) optionally blackens conductor pixels deeper than
$3\delta$ from the surface, reducing $N$ dramatically without sacrificing
accuracy. ($e^{-3} \approx 5\%$ remaining current.)

This is the "Restrict to skin depth" toggle in atlc2 (and the
`restrict_to_skin_depth` flag in lineforge's API).

## Accuracy

Per atlc2 docs: Rs is accurate to ±1% when $\delta \ge 30 \cdot h$ (pixel
width). For tighter geometries, accuracy degrades to ±5% with the standard
PEEC formulation, and lineforge emits a `low_confidence` warning when conductors
are too close (matching atlc2's red-text behavior).

## N-conductor extraction workflow

The two-wire formulations above generalize to an arbitrary N-conductor
cross-section built from labels rather than the atlc2 `+1`/`-1`/`0` RGB
roles. The pieces:

1. **Label the conductors.** `Usermap.from_labels` takes an integer
   material-id grid plus an integer `conductor_ids` grid: `-1` marks a
   non-conductor (dielectric or unlabeled) pixel, `0` is the reference
   conductor, `1..N` are the signal conductors, and `-2` marks a floating
   group. This is how a fieldforge-extracted cross-section with more than
   two signal conductors gets into lineforge.
2. **Capacitance and external inductance.** `solvers.mtl.solve_maxwell` runs
   one Laplace solve per signal conductor (that conductor at 1 V, every
   other fixed conductor at 0 V) plus the same set in vacuum, and stores the
   resulting energy matrices partitioned by material code. `rlgc_matrices`
   turns those into the `(N, N)` `C`, `G`, and `L_ext` matrices at any
   frequency via `MaterialRecord.er_complex`, without re-solving.
3. **Skin-effect resistance.** `solvers.wheeler.solve_wheeler_resistance`
   gets `R` from Wheeler's incremental-inductance rule
   ($R = (R_s/\mu_0)\, dL_\text{ext}/dn$): it erodes each conductor by a
   pixel, re-solves the vacuum Maxwell problem, and takes the inductance
   derivative, which needs no separate surface-current extraction.
4. **Roughness.** A `RoughnessSpec` per conductor (Hammerstad, Groisse, or
   Huray/cannonball, `solvers.roughness`) multiplies that conductor's own
   contribution to `R`.
5. **Direct N-conductor PEEC alternative.** `solvers.faraday.solve_impedance_matrix`
   is the N-conductor generalization of the two-wire PEEC system above: the
   same dense complex system, but assembled and factored once (a single LU)
   and solved for N right-hand sides, one per signal-conductor drive. It
   returns `R` and `L` together in one call and raises
   `SolverBudgetExceeded` rather than silently building a system too large
   to factor.
6. **Export.** `touchstone.to_touchstone_nport` writes the resulting
   frequency-swept S-parameters as an N-port Touchstone file (version 1.x
   via scikit-rf, or a native version 2.0 writer with mixed-mode port
   ordering), ready for HyperLynx, ADS, or any other cascade-analysis tool.

## References

- atlc2 docs §"L and Rs": <http://www.hdtvprimer.com/kq6qv/atlc2.html>.
- A. Ruehli, *Inductance Calculations in a Complex Integrated Circuit
  Environment*, IBM J. Res. Dev., Sep. 1972 (PEEC origins).
- C. Paul, *Inductance: Loop and Partial*, Wiley 2010.
- B. Wadell, *Transmission Line Design Handbook*, Artech 1991, §3.7
  (skin-effect resistance).
- SciPy sparse Krylov: <https://docs.scipy.org/doc/scipy/reference/sparse.linalg.html>.
