"""Result caching.

Caches solver outputs to disk as JSON files, keyed by a deterministic hash of
(geometry, options, materials, lineforge version). Repeated runs with the same
inputs are returned from cache instantly.

The on-disk format is JSON (plus a small typed envelope for Pydantic models,
dataclasses, and complex numbers). Entries are never unpickled, so a file
planted in the cache directory cannot execute code when it is read. Leftover
``diskcache`` / pickle files from older lineforge versions are treated as
misses.

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
import importlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar, cast

import numpy as np
from pydantic import BaseModel

from lineforge.version import __version__

F = TypeVar("F", bound=Callable[..., Any])

_FORMAT_VERSION = 1
_TYPE_TAG = "__lf_type__"


class _MissType:
    """Sentinel: distinguish a cache miss from a cached ``None``."""


_MISS = _MissType()


def _default_cache_dir() -> Path:
    if env := os.environ.get("ATLC3_CACHE_DIR"):
        return Path(env)
    home = Path.home()
    return home / ".cache" / "lineforge"


def _resolve_lineforge_type(qualname: str) -> type[Any]:
    """Import a public ``lineforge.*`` class. Refuse everything else."""
    if not isinstance(qualname, str) or ".." in qualname:
        raise ValueError("invalid cached type name")
    module_name, sep, cls_name = qualname.rpartition(".")
    if not sep or not module_name.startswith("lineforge.") or not cls_name:
        raise ValueError(f"refusing to reconstruct type {qualname!r}")
    if "." in cls_name or cls_name.startswith("_"):
        raise ValueError(f"refusing to reconstruct type {qualname!r}")
    for part in module_name.split("."):
        if not part or part.startswith("_"):
            raise ValueError(f"refusing to reconstruct type {qualname!r}")
    module = importlib.import_module(module_name)
    cls = getattr(module, cls_name)
    if not isinstance(cls, type):
        raise ValueError(f"{qualname!r} is not a type")
    return cls


def _encode(value: Any) -> Any:
    """Convert a cached value into a JSON-safe structure.

    Raises
    ------
    TypeError
        If ``value`` cannot be represented without pickle.
    """
    if isinstance(value, np.generic):
        return _encode(value.item())
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, complex):
        return {_TYPE_TAG: "complex", "real": value.real, "imag": value.imag}
    if isinstance(value, BaseModel):
        return {
            _TYPE_TAG: "pydantic",
            "qualname": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
            "data": value.model_dump(mode="json"),
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            _TYPE_TAG: "dataclass",
            "qualname": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
            "data": {f.name: _encode(getattr(value, f.name)) for f in fields(value)},
        }
    if isinstance(value, dict):
        encoded: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("dict keys must be strings")
            encoded[key] = _encode(item)
        return encoded
    if isinstance(value, tuple):
        return {_TYPE_TAG: "tuple", "items": [_encode(x) for x in value]}
    if isinstance(value, list):
        return [_encode(x) for x in value]
    raise TypeError(f"cannot JSON-cache {type(value).__name__}")


def _decode(value: Any) -> Any:
    """Inverse of :func:`_encode`. Raises ``ValueError`` on malformed data."""
    if isinstance(value, dict) and _TYPE_TAG in value:
        tag = value[_TYPE_TAG]
        if tag == "complex":
            return complex(float(value["real"]), float(value["imag"]))
        if tag == "tuple":
            items = value["items"]
            if not isinstance(items, list):
                raise ValueError("tuple items must be a list")
            return tuple(_decode(x) for x in items)
        if tag == "pydantic":
            cls = _resolve_lineforge_type(str(value["qualname"]))
            if not issubclass(cls, BaseModel):
                raise ValueError("cached type is not a Pydantic model")
            return cls.model_validate(value["data"])
        if tag == "dataclass":
            cls = _resolve_lineforge_type(str(value["qualname"]))
            if not (isinstance(cls, type) and is_dataclass(cls)):
                raise ValueError("cached type is not a dataclass")
            raw = value["data"]
            if not isinstance(raw, dict):
                raise ValueError("dataclass data must be an object")
            decoded = {str(k): _decode(v) for k, v in raw.items()}
            return cast(Any, cls)(**decoded)
        raise ValueError(f"unknown cache type tag {tag!r}")
    if isinstance(value, dict):
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(x) for x in value]
    return value


class Cache:
    """Directory-backed JSON cache. Values are never unpickled.

    ``directory`` matches the attribute :class:`diskcache.Cache` exposed so
    ``lineforge clear-cache`` can print the path.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = str(directory)
        self._dir = Path(self.directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    def get(self, key: str) -> Any:
        """Return the cached value, or ``_MISS`` if absent / unreadable."""
        path = self._entry_path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return _MISS
            if payload.get("v") != _FORMAT_VERSION:
                return _MISS
            if payload.get("key") != key:
                return _MISS
            return _decode(payload["value"])
        except FileNotFoundError:
            return _MISS
        except Exception:  # noqa: BLE001 — cache must never crash the solver
            return _MISS

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key) is not _MISS

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is _MISS:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        payload = {
            "v": _FORMAT_VERSION,
            "key": key,
            "value": _encode(value),
        }
        data = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._entry_path(key)
        fd, tmp_name = tempfile.mkstemp(prefix="lfcache-", suffix=".tmp", dir=self._dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp_name, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

    def clear(self) -> None:
        """Remove every file in the cache directory, including leftovers."""
        if self._dir.exists():
            shutil.rmtree(self._dir, ignore_errors=True)
        self._dir.mkdir(parents=True, exist_ok=True)

    def __len__(self) -> int:
        if not self._dir.is_dir():
            return 0
        return sum(1 for p in self._dir.glob("*.json") if p.is_file())


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache(_default_cache_dir())
    return _cache


def clear_cache() -> int:
    """Clear all cached results. Returns the count of evicted JSON entries."""
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
        # Usermap: we hash the immutable RGB + metadata. Materials are derived
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

        if isinstance(v, np.ndarray):
            return ("np", v.shape, v.dtype.str, hashlib.sha1(v.tobytes()).hexdigest())

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
    """Decorator: memoize a function via the on-disk JSON cache.

    Disabled if ``ATLC3_NO_CACHE=1``. Cache key includes the package version.

    Parameters
    ----------
    prefix
        Cache key prefix: distinguishes between memoized functions.
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
            hit = cache.get(key)
            if hit is not _MISS:
                return hit
            result = fn(*args, **kwargs)
            # Best-effort: return without caching if result isn't JSON-safe.
            with contextlib.suppress(TypeError, ValueError, OSError):
                cache[key] = result
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["cached", "clear_cache", "get_cache", "is_disabled"]
