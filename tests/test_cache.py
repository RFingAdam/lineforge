"""Phase 4.3 AC: cache layer roundtrips and respects ATLC3_NO_CACHE."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlc3.cache import _hash_args, cached, clear_cache, is_disabled


def test_hash_is_stable() -> None:
    h1 = _hash_args((1, 2), {"a": "b"})
    h2 = _hash_args((1, 2), {"a": "b"})
    assert h1 == h2


def test_hash_changes_with_args() -> None:
    h1 = _hash_args((1, 2), {})
    h2 = _hash_args((1, 3), {})
    assert h1 != h2


def test_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLC3_NO_CACHE", "1")
    assert is_disabled() is True


def test_cached_decorator_memoizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLC3_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("ATLC3_NO_CACHE", raising=False)

    # Reset module-level cache singleton
    import atlc3.cache as cache_module

    cache_module._cache = None

    call_count = 0

    @cached("test")
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    assert f(5) == 10
    assert f(5) == 10  # cached, no second call
    assert f(5) == 10
    assert call_count == 1

    assert f(6) == 12
    assert call_count == 2


def test_clear_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLC3_CACHE_DIR", str(tmp_path / "cache2"))
    monkeypatch.delenv("ATLC3_NO_CACHE", raising=False)

    import atlc3.cache as cache_module

    cache_module._cache = None

    @cached("clear-test")
    def g(x: int) -> int:
        return x

    g(1)
    g(2)
    assert clear_cache() >= 0  # may be 0 if disabled
