//! Open-boundary 8× progressive grid extension.
//!
//! Phase 2 (issue 2.9). Pads the usermap with 100 normal-size pixels, then
//! progressively coarser pixels (8× steps) until the simulated region reaches
//! 3200×3200 effective area — approximates an open boundary cheaply.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
