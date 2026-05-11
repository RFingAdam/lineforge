//! V-cycle multigrid Laplace solver.
//!
//! Implementation lands in Phase 2 (issue 2.7). The kernel will provide a
//! V-cycle multigrid for the Laplace operator with εr coefficients.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Phase 0: no functions yet. Phase 2 adds laplace_multigrid().
    Ok(())
}
