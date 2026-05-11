"""Result caching.

Caches solver outputs to disk via :mod:`diskcache`, keyed by a deterministic
hash of (geometry, options, materials, lineforge version). Repeated runs with the
same inputs are returned from cache instantly.

Use cases:
    - Parameter sweeps that revisit similar points (e.g. binary search).
    - Re-running the same script repeatedly during PCB design iteration.
    - Multi-stage workflows where downstream steps reference the same solve.

The cache is invalidated on package version bumps (the version is part of
the key), so upgrades cleanly retire old results.

Disable globally with the ``ATLC3_NO_CACHE=1`` environment variable.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import diskcache

from lineforge.version import __version__

F = TypeVar("F", bound=Callable[..., Any])


def _default_cache_dir() -> Path:
    if env := os.environ.get("ATLC3_CACHE_DIR"):
        return Path(env)
    home = Path.home()
    return home / ".cache" / "lineforge"


_cache: diskcache.Cache | None = None


def get_cache() -> diskcache.Cache:
    global _cache
    if _cache is None:
        _cache = diskcache.Cache(str(_default_cache_dir()))
    return _cache


def clear_cache() -> int:
    """Clear all cached results. Returns the count of evicted entries."""
    cache = get_cache()
    n = len(cache)
    cache.clear()
    return n


def is_disabled() -> bool:
    return os.environ.get("ATLC3_NO_CACHE", "").lower() in {"1", "true", "yes"}


def _hash_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Build a deterministic hash key from positional + keyword args.

    Coercion order:
        1. :class:`lineforge.geometry.usermap.Usermap` → ``(rgb-hash, meta-json)``.
        2. Pydantic models → ``model_dump_json()``.
        3. NumPy arrays → ``(shape, dtype, sha1(bytes))``.
        4. Containers → recurse.
        5. Anything else → ``str(...)``.
    """

    def coerce(v: Any) -> Any:
        # Usermap — we hash the immutable RGB + metadata. Materials are derived
        # from RGB so they're implicitly covered.
        try:
            from lineforge.geometry.usermap import Usermap

            if isinstance(v, Usermap):
                return (
                    "Usermap",
                    v.rgb.shape,
                    hashlib.sha1(v.rgb.tobytes()).hexdigest(),
                    v.meta.model_dump_json(),
                )
        except ImportError:
            pass

        # Pydantic
        if hasattr(v, "model_dump_json"):
            return v.model_dump_json()

        # numpy
        try:
            import numpy as np

            if isinstance(v, np.ndarray):
                return ("np", v.shape, v.dtype.str, hashlib.sha1(v.tobytes()).hexdigest())
        except ImportError:
            pass

        if isinstance(v, dict):
            return {k: coerce(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [coerce(x) for x in v]
        return v

    payload = json.dumps(
        {
            "version": __version__,
            "args": [coerce(a) for a in args],
            "kwargs": {k: coerce(val) for k, val in sorted(kwargs.items())},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached(
    prefix: str,
    *,
    skip_when: Callable[..., bool] | None = None,
) -> Callable[[F], F]:
    """Decorator: memoize a function via diskcache.

    Disabled if ``ATLC3_NO_CACHE=1``. Cache key includes the package version.

    Parameters
    ----------
    prefix
        Cache key prefix — distinguishes between memoized functions.
    skip_when
        Optional predicate ``(*args, **kwargs) -> bool``. If it returns True
        for a given call, the cache is bypassed (call passes through). Used
        to skip caching when ``return_fields=True`` for solvers (whose
        workspace fields are large numpy arrays not worth disk-caching).
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if is_disabled() or (skip_when is not None and skip_when(*args, **kwargs)):
                return fn(*args, **kwargs)
            cache = get_cache()
            key = f"{prefix}:{_hash_args(args, kwargs)}"
            if key in cache:
                return cache[key]
            result = fn(*args, **kwargs)
            # Best-effort: return without caching if result isn't picklable.
            with contextlib.suppress(TypeError, ValueError):
                cache[key] = result
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["cached", "clear_cache", "get_cache", "is_disabled"]
