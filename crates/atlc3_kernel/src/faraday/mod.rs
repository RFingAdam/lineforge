//! Faraday's-law solver kernels for L and Rs computation.
//!
//! - `assemble`: build sparse N×N system, one row per conductor pixel.
//! - `solve`: BiCGSTAB + ILU0 (or hand off to scipy.sparse for the Krylov part).
//!
//! Phase 3 implementation.

use pyo3::prelude::*;

pub mod assemble;
pub mod solve;

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    assemble::register(m)?;
    solve::register(m)?;
    Ok(())
}
