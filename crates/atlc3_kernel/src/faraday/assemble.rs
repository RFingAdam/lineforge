//! Sparse Faraday system assembly.
//!
//! Phase 3 (issue 3.2). Builds the N×N sparse system (one row per conductor
//! pixel) using CSR/COO via `sprs`, with a per-conductor net-current = 0
//! constraint. Matrix is exposed to Python as a scipy.sparse.csr_matrix.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
