//! Successive over-relaxation Laplace solver.
//!
//! Implementation lands in Phase 2 (issue 2.6). The kernel will:
//!   - 5-point FD with εr-weighted stencil
//!   - Configurable ω (default 1.9)
//!   - Parallel checkerboard update via `rayon`
//!   - PyO3 binding: `laplace_sor(grid, materials, omega, max_iter, tol)`

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Phase 0: no functions yet. Phase 2 adds laplace_sor().
    Ok(())
}
