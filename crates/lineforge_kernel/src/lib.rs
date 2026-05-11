//! lineforge_kernel — native numerical kernels for lineforge.
//!
//! Exposes a PyO3 module `lineforge._kernel` consumed by the Python package.
//! Phase 0 ships only a `version()` smoke-test function. Phase 2 adds the Laplace
//! SOR + multigrid solvers; Phase 3 adds the Faraday sparse-system kernels.

use pyo3::prelude::*;

mod charge_shift;
mod extension;
mod faraday;
mod laplace;

/// Returns the kernel version string. Used as a smoke test that the Rust
/// extension is correctly built and importable from Python.
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Returns true if the kernel was built with rayon parallel features.
/// Useful for debugging install issues — a user can confirm the optimized
/// path is available.
#[pyfunction]
fn has_parallel() -> bool {
    rayon::current_num_threads() > 1
}

/// PyO3 module entry point. The Python package imports this as
/// `lineforge._kernel`.
#[pymodule]
fn _kernel(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(has_parallel, m)?)?;

    laplace::register(m)?;
    faraday::register(m)?;
    charge_shift::register(m)?;
    extension::register(m)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_is_set() {
        assert!(!version().is_empty());
    }
}
