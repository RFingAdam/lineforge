"""Type stubs for the native Rust extension ``lineforge._kernel``.

Phase 0 exposes only ``version()`` and ``has_parallel()``. Phase 2 will add
the Laplace SOR + multigrid signatures; Phase 3 adds the Faraday assembly +
solve signatures. Stubs are extended in lockstep with the Rust ``register``
calls in ``crates/lineforge_kernel/src/lib.rs``.
"""

from __future__ import annotations

def version() -> str:
    """Return the native kernel's package version (matches Cargo.toml)."""
    ...

def has_parallel() -> bool:
    """Return True if the kernel was built with rayon parallelism enabled."""
    ...
