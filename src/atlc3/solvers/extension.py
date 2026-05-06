"""Open-boundary grid extension.

Per atlc2 docs, for unshielded lines the usermap is extended outward with:
    1. ~100 normal-size pixels of edge-replicated material, then
    2. progressively coarser pixels (8× steps) until the simulated region
       covers a 3200×3200 effective area (i.e. infinite-half-plane).

Phase 2 implements a simplified, two-step version that captures the spirit:
    - Replicate edge pixels by ``inner_pad`` (default 100) → preserves materials.
    - Outside that, expand to a target outer extent via ``outer_pad_factor`` ×
      grid size of edge-replicated *uniform* pixels.

The Phase-2 single-grid Laplace solver works on this extended grid directly;
the progressive-coarse-pixel multilevel scheme is a Phase 4 polish item that
only matters for very large unshielded usermaps.
"""

from __future__ import annotations

from atlc3.geometry.usermap import Usermap


def extend(
    usermap: Usermap,
    *,
    target_size: int = 3200,
    inner_pad: int = 100,
) -> Usermap:
    """Extend a usermap to approximate an open boundary.

    Parameters
    ----------
    usermap
        Source usermap.
    target_size
        Target side length in *original* pixel units. Default 3200 matches
        atlc2's hard-coded simulation extent.
    inner_pad
        Number of edge-replicated pixels to insert before further padding.

    Returns
    -------
    Usermap
        Extended usermap (with replicated edges); the outer boundary is the
        original outer pixel color, which the Laplace solver treats as a
        Dirichlet V=0 (or whatever the corner pixel's BC is) boundary.
    """
    h, w = usermap.shape
    if h >= target_size and w >= target_size:
        return usermap

    # First pad with the requested number of normal pixels by edge replication
    extended = usermap.replicate_edges(inner_pad)

    # Then pad outward to ``target_size`` if still smaller
    eh, ew = extended.shape
    pad_h = max(0, (target_size - eh) // 2)
    pad_w = max(0, (target_size - ew) // 2)
    if pad_h == 0 and pad_w == 0:
        return extended

    return extended.replicate_edges(max(pad_h, pad_w))


def extend_to_shape(usermap: Usermap, target_h: int, target_w: int) -> Usermap:
    """Extend to specific target dimensions (centered)."""
    h, w = usermap.shape
    pad_h = max(0, (target_h - h) // 2)
    pad_w = max(0, (target_w - w) // 2)
    if pad_h == 0 and pad_w == 0:
        return usermap
    return usermap.replicate_edges(max(pad_h, pad_w))


__all__ = ["extend", "extend_to_shape"]
