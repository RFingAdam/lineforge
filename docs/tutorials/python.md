# Python API

Top-level convenience functions for the most common workflows. Full submodule
APIs are in the [reference](../reference/geometries.md).

## Import

```python
import atlc3
```

## One-liners

```python
# Microstrip
r = atlc3.microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
print(r.z0, r.eps_eff)

# Stripline
r = atlc3.stripline(W="5mil", T="1.4mil", B="14mil", er=4.4)

# CPWG
r = atlc3.cpwg(W="5mil", S="8mil", H="4mil", T="1.4mil", er=4.4)

# Edge-coupled differential pair
r = atlc3.edge_coupled_diff(
    W="4mil", S="6mil", H="4mil", T="1.4mil", er=4.4, on="microstrip",
)
print(r.z_diff, r.z_odd, r.z_even, r.z_common)
```

## Geometry models + dispatcher

For more control, build a geometry model directly and dispatch through
`atlc3.solve`:

```python
geom = atlc3.Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4, tan_delta=0.02)
r = atlc3.solve(geom, frequency="1GHz")
```

Or with a dict:

```python
r = atlc3.solve({
    "type": "microstrip",
    "W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4,
})
```

## Sweeps

Phase 1 has no first-class sweep API; just loop:

```python
for w_mil in range(3, 26, 2):
    r = atlc3.microstrip(W=f"{w_mil}mil", H="4mil", T="1.4mil", er=4.4)
    print(w_mil, r.z0)
```

A first-class `atlc3.sweep()` function lands in Phase 3 alongside the L/Rs
Faraday solver.

## Result models

Single-line geometries return [`TLineResult`](../reference/geometries.md);
differential pairs return `DiffResult`. Both are Pydantic v2 models:

```python
r = atlc3.microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)

r.z0              # float, ohms
r.eps_eff         # float
r.vp              # float, m/s
r.td_per_inch     # float, seconds per inch
r.warnings        # list[SolverWarning]

r.model_dump()         # → plain dict
r.model_dump_json()    # → JSON string
```
