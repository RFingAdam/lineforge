# Geometry reference

Every supported transmission line geometry, with its required dimensional
fields and which closed-form formula it dispatches to.

## Single-line

### Microstrip

::: lineforge.geometry.types.Microstrip

Solver: Hammerstad-Jensen with Wheeler thickness correction.
Validity: `0.05 ≤ W/H ≤ 20`, `εr ≤ 128`.

### Embedded (coated) microstrip

::: lineforge.geometry.types.EmbeddedMicrostrip

Solver: IPC-2141A coated-microstrip blend (η-factor based on coating thickness).

### Symmetric stripline

::: lineforge.geometry.types.StriplineSymmetric

Solver: Cohn wide-strip formula with Wadell finite-thickness correction.
Validity: `W/(B−T) > 0.35`, `T < 0.25·B`.

### Asymmetric stripline

::: lineforge.geometry.types.StriplineAsymmetric

Solver: Wadell two-parallel-stripline approximation.

### CPWG (coplanar waveguide with ground)

::: lineforge.geometry.types.CPWG

Solver: Wen elliptic-integral formula via `scipy.special.ellipk`.

## Differential

### Edge-coupled diff microstrip

::: lineforge.geometry.types.EdgeCoupledDiffMicrostrip

Solver: IPC-2141A coupling correction on the Hammerstad-Jensen single-trace Z₀.

### Edge-coupled diff stripline

::: lineforge.geometry.types.EdgeCoupledDiffStripline

Solver: IPC-2141A coupling correction on the symmetric-stripline Z₀.

### Broadside-coupled diff stripline

::: lineforge.geometry.types.BroadsideCoupledDiffStripline

Solver: Wadell §6.5 broadside formula with finite-thickness correction.

## Result types

::: lineforge.results.TLineResult

::: lineforge.results.DiffResult

::: lineforge.results.SolverWarning
