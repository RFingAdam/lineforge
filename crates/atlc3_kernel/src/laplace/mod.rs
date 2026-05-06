//! Laplace solver kernels: 5-point FD with εr-weighted stencil.
//!
//! - `sor`: Successive over-relaxation (Gauss-Seidel + ω accelerator).
//! - `multigrid`: V-cycle multigrid with εr coefficients.
//!
//! Phase 2 implementation. Phase 0 ships only the module skeleton.

use pyo3::prelude::*;

pub mod multigrid;
pub mod sor;

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    sor::register(m)?;
    multigrid::register(m)?;
    Ok(())
}
