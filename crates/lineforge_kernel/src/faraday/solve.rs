//! Sparse linear solve for the Faraday system.
//!
//! Phase 3 (issue 3.3). The default Python path uses scipy.sparse.linalg.bicgstab
//! with an spilu preconditioner; this module provides an optional Rust-native
//! BiCGSTAB + ILU0 path for benchmarking.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
