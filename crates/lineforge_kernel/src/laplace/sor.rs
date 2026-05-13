//! Successive over-relaxation Laplace solver.
//!
//! Deferred to Phase 5 (issue #6). The production path is NumPy + PyAMG +
//! scipy.sparse, which covers practical PCB cross-sections (a few thousand
//! pixels) with adequate performance. Rust acceleration is an optimization,
//! not a correctness gap. When implemented, the kernel will:
//!   - 5-point FD with εr-weighted stencil
//!   - Configurable ω (default 1.9)
//!   - Parallel checkerboard update via `rayon`
//!   - PyO3 binding: `laplace_sor(grid, materials, omega, max_iter, tol)`

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Phase 5 will add laplace_sor(). NumPy + PyAMG is the production path.
    Ok(())
}
