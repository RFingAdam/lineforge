"""Single source of truth for the lineforge Python package version.

Kept in sync with the Rust crate version in ``crates/lineforge_kernel/Cargo.toml``
and the workspace ``Cargo.toml``. The release pipeline asserts equality.
"""

from __future__ import annotations

__version__ = "2.1.0"
