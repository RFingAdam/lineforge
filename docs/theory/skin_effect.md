# Skin effect, δ, and the 30δ rule

## Skin depth

For a good conductor at angular frequency $\omega$:

$$
\delta = \sqrt{\frac{2\rho}{\omega \mu}}
$$

where $\rho$ is resistivity and $\mu = \mu_0 \mu_r$. For copper at 1 GHz,
$\delta \approx 2.1 \,\mu\mathrm{m}$.

## Why it matters for lineforge's Rs accuracy

The Faraday solver assigns a single current value $i_n$ per conductor pixel.
If the pixel side $h$ is large compared to $\delta$, the discretization can't
resolve the actual current concentration at the surface, and Rs is
underestimated.

atlc2's empirical rule (which lineforge inherits):

> Rs is accurate to ±1% when $\delta \ge 30 \cdot h$.

For coarser grids, accuracy degrades to ±5%, and to **worse than 5%** if
conductors of different voltage are too close (per atlc2's diagram, < 8
pixels for flat surfaces, < 16 pixels for corners).

## "Restrict to skin depth"

atlc2 ships a checkbox; lineforge exposes the equivalent
`restrict_to_skin_depth=True` flag. When enabled, conductor pixels deeper than
$3\delta$ from any conductor surface are blackened (treated as vacuum).
Result: $N$ shrinks drastically at high frequency, keeping the dense
$\mathcal{O}(N^3)$ Faraday solve tractable.

The 3× factor is conservative: $e^{-3} \approx 5\%$ of the surface current
remains, well below the noise floor of the FD discretization itself.

## When to disable the skin restriction

- Low-frequency / DC analysis: $\delta$ is large; nothing is masked anyway.
- Very thin conductors (foil): the conductor is already < $3\delta$ thick.
- Cross-validation against analytical formulas that don't include skin depth.

In lineforge:

```python
result = lineforge.solve_lrs(geom, frequency="1GHz", restrict_to_skin_depth=False)
```

## Low-frequency dispersion

A subtle consequence of skin effect: at low frequency the current spreads
into the conductor interior, increasing the internal inductance contribution.
At high frequency the current is concentrated at the surface, reducing $L$.
This is the well-known **low-frequency dispersion** effect.

lineforge's frequency-resolved Faraday solve captures this naturally: running
solves at multiple frequencies and plotting $L(f)$ shows the dispersion.

## References

- atlc2 docs §"Getting an accurate Rs":
  <http://www.hdtvprimer.com/kq6qv/atlc2.html>.
- C. Paul, *Inductance: Loop and Partial*, Wiley 2010, Chapter 3.
- D. Pozar, *Microwave Engineering*, 4th ed., §1.7 (skin depth, surface
  resistance).
