"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture
def kernel_available() -> Iterator[bool]:
    """True when the native Rust kernel is importable."""
    try:
        import lineforge._kernel  # noqa: F401

        yield True
    except ImportError:
        yield False
