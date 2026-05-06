"""Phase 0.2 AC: ``from atlc3._kernel import version; print(version())`` works."""

from __future__ import annotations

import pytest


@pytest.mark.needs_rust
def test_kernel_importable(kernel_available: bool) -> None:
    if not kernel_available:
        pytest.skip("native kernel not built (run: maturin develop)")

    from atlc3 import _kernel

    assert _kernel.version()
    assert isinstance(_kernel.version(), str)


@pytest.mark.needs_rust
def test_kernel_has_parallel_function(kernel_available: bool) -> None:
    if not kernel_available:
        pytest.skip("native kernel not built")

    from atlc3 import _kernel

    assert isinstance(_kernel.has_parallel(), bool)
