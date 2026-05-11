//! Surface-charge E-field prediction.
//!
//! Phase 2 (issue 2.8). ~20-iteration boundary-charge update that distributes
//! surface charge based on the normal component of E at each conductor pixel.
//! Provides a fast initial V-field for the relaxation solver.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
