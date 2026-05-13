//! V-cycle multigrid Laplace solver.
//!
//! Deferred to Phase 5 (issue #6). The production path is PyAMG (Python AMG)
//! which already implements competitive V-cycle multigrid for the Laplace
//! operator with εr coefficients. Rust implementation is optimization, not
//! correctness gap.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Phase 5 will add laplace_multigrid(). PyAMG is the production path.
    Ok(())
}
