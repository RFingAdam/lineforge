"""Cache layer: JSON roundtrips, env disable, and no-unpickle security."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import pytest

from lineforge.cache import _MISS, _hash_args, cached, clear_cache, get_cache, is_disabled
from lineforge.solvers.cgp import CGPResult
from lineforge.solvers.faraday import FaradayResult


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("ATLC3_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("ATLC3_NO_CACHE", raising=False)
    import lineforge.cache as cache_module

    cache_module._cache = None
    yield cache_dir
    cache_module._cache = None


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


def test_cached_decorator_memoizes(isolated_cache: Path) -> None:
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


def test_clear_cache(isolated_cache: Path) -> None:
    @cached("clear-test")
    def g(x: int) -> int:
        return x

    g(1)
    g(2)
    assert clear_cache() >= 0  # may be 0 if disabled
    assert len(get_cache()) == 0


def test_pydantic_and_dataclass_roundtrip(isolated_cache: Path) -> None:
    cgp_calls = 0
    faraday_calls = 0

    @cached("cgp-rt")
    def make_cgp() -> CGPResult:
        nonlocal cgp_calls
        cgp_calls += 1
        return CGPResult(
            z0=50.0,
            eps_eff=3.5,
            vp=1.6e8,
            L_per_m=2.5e-7,
            C_per_m=1.0e-10,
            Gp_per_m=0.0,
            frequency_hz=1e9,
            iterations=12,
            method="laplace-fd",
        )

    @cached("faraday-rt")
    def make_faraday() -> FaradayResult:
        nonlocal faraday_calls
        faraday_calls += 1
        return FaradayResult(
            L_per_m=2.5e-7,
            R_per_m=0.4,
            z0_complex=50.0 + 0.1j,
            frequency_hz=1e9,
            n_conductor_pixels=42,
            rs_low_confidence=False,
            rs_warning=None,
        )

    first_cgp = make_cgp()
    first_faraday = make_faraday()
    cached_cgp = make_cgp()
    cached_faraday = make_faraday()

    assert cgp_calls == 1
    assert faraday_calls == 1
    assert cached_cgp == first_cgp
    assert isinstance(cached_cgp, CGPResult)
    assert cached_faraday == first_faraday
    assert isinstance(cached_faraday, FaradayResult)
    assert cached_faraday.z0_complex == 50.0 + 0.1j


def test_unserializable_result_is_not_cached(isolated_cache: Path) -> None:
    call_count = 0

    class _Opaque:
        pass

    @cached("opaque")
    def f() -> _Opaque:
        nonlocal call_count
        call_count += 1
        return _Opaque()

    assert isinstance(f(), _Opaque)
    assert isinstance(f(), _Opaque)
    assert call_count == 2


def test_corrupt_json_is_a_miss(isolated_cache: Path) -> None:
    call_count = 0

    @cached("corrupt")
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x + 1

    key = f"corrupt:{_hash_args((3,), {})}"
    path = get_cache()._entry_path(key)
    path.write_text("{not-json", encoding="utf-8")

    assert f(3) == 4
    assert call_count == 1
    assert f(3) == 4
    assert call_count == 1


def test_legacy_diskcache_files_do_not_crash(isolated_cache: Path) -> None:
    isolated_cache.mkdir(parents=True, exist_ok=True)
    (isolated_cache / "cache.db").write_bytes(b"sqlite leftover")
    (isolated_cache / "00").mkdir()
    (isolated_cache / "00" / "deadbeef").write_bytes(b"\x80\x04garbage")

    @cached("legacy")
    def f(x: int) -> int:
        return x * 4

    assert f(2) == 8
    assert f(2) == 8


_PICKLE_EXECUTED = False


def _mark_pickle_executed() -> str:
    global _PICKLE_EXECUTED
    _PICKLE_EXECUTED = True
    return "pwned"


class _MaliciousPayload:
    """Pickle payload that runs :func:`_mark_pickle_executed` on load."""

    def __reduce__(self) -> tuple[Any, ...]:
        return (_mark_pickle_executed, ())


def test_planted_pickle_is_not_executed(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #46: a planted cache file must not run code when the cache is read."""
    global _PICKLE_EXECUTED
    _PICKLE_EXECUTED = False

    def _forbid_pickle(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("cache must not unpickle data")

    monkeypatch.setattr(pickle, "loads", _forbid_pickle)
    monkeypatch.setattr(pickle, "load", _forbid_pickle)

    call_count = 0

    @cached("rce")
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 3

    key = f"rce:{_hash_args((7,), {})}"
    planted = pickle.dumps(_MaliciousPayload())
    isolated_cache.mkdir(parents=True, exist_ok=True)
    get_cache()._entry_path(key).write_bytes(planted)
    (isolated_cache / "planted.pkl").write_bytes(planted)

    assert f(7) == 21
    assert f(7) == 21
    assert call_count == 1
    assert _PICKLE_EXECUTED is False


def test_type_smuggling_json_is_refused(isolated_cache: Path) -> None:
    call_count = 0

    @cached("smuggle")
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x + 9

    key = f"smuggle:{_hash_args((1,), {})}"
    payload = {
        "v": 1,
        "key": key,
        "value": {
            "__lf_type__": "dataclass",
            "qualname": "os.system",
            "data": {},
        },
    }
    path = get_cache()._entry_path(key)
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert f(1) == 10
    assert call_count == 1
    assert get_cache().get(key) is not _MISS  # rewritten with the real int
