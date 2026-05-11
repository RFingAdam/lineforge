"""Skin-depth prediction and conductor-pixel masking.

For a good conductor at frequency ω, the AC current density falls off
exponentially with depth from the surface, with characteristic length

    δ = sqrt(2ρ / (ωμ))     [m]

where ρ is resistivity and μ = μ₀·μr.

For thick conductors at high frequency, the interior carries negligible
current. atlc2 introduces a "Restrict to skin depth" checkbox that blackens
out conductor pixels deeper than ``factor·δ`` (factor = 3 by default —
e^-3 ≈ 5% remaining current). This dramatically cuts the equation count for
the Faraday L/Rs solver.

This module provides:
    - :func:`compute_delta` — δ from material + frequency.
    - :func:`mask_skin_depth` — distance-transform-based pixel masking.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt

from lineforge.analytical._constants import MU0
from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.materials import MaterialRecord


def compute_delta(material: MaterialRecord, frequency_hz: float) -> float:
    """Skin depth δ for a given material and frequency.

    Parameters
    ----------
    material
        Conductor material. Insulators get δ = ∞ (returned as 1e6 for safety).
    frequency_hz
        Frequency in Hz.

    Returns
    -------
    float
        δ in meters.
    """
    if material.is_insulator or frequency_hz <= 0:
        return 1e6
    # atlc2's DB stores resistivity in µΩ·cm despite the field name.
    # For copper (1.7241 in atlc2 terms) → 1.7241e-8 Ω·m. Conversion: × 1e-8.
    rho = material.resistivity_ohm_cm * 1e-8
    omega = 2.0 * np.pi * frequency_hz
    mu = MU0 * material.mu_r
    return float(np.sqrt(2.0 * rho / (omega * mu)))


def mask_skin_depth(
    usermap: Usermap,
    frequency_hz: float,
    *,
    factor: float = 3.0,
    blacken_color: tuple[int, int, int] = (0, 0, 0),
) -> Usermap:
    """Return a new Usermap with deep-conductor pixels blackened.

    Pixels in conductor regions further than ``factor·δ`` from the surface are
    replaced with ``blacken_color`` (default vacuum). Different conductor
    regions can have different δ if they're different materials — we compute
    each material's δ separately.

    Parameters
    ----------
    usermap
        Input usermap.
    frequency_hz
        Frequency for δ computation.
    factor
        Multiplier on δ; pixels deeper than ``factor·δ`` from any conductor
        boundary are masked. Default 3 (≈ 95% of current depth).
    blacken_color
        RGB to use for masked pixels. Default (0,0,0) = vacuum.

    Returns
    -------
    Usermap
        New usermap with the masked pixels replaced.
    """
    if frequency_hz <= 0:
        return usermap

    new_rgb = usermap.rgb.copy()
    px = usermap.pixel_width_m

    # For each conductor material, compute δ and mask pixels in that material's
    # region deeper than factor·δ from a non-conductor neighbor.
    for idx, mat in enumerate(usermap.materials):
        if not mat.is_conductor:
            continue
        delta = compute_delta(mat, frequency_hz)
        depth_pixels = factor * delta / px
        if depth_pixels < 1.0:
            continue  # skin depth shallower than one pixel — nothing to mask
        material_mask = usermap.codes == idx
        if not material_mask.any():
            continue
        # Distance from each conductor pixel to its nearest non-conductor pixel
        # (i.e., to the surface of this conductor region)
        conductor_mask_global = np.zeros_like(material_mask)
        for j, mj in enumerate(usermap.materials):
            if mj.is_conductor:
                conductor_mask_global |= usermap.codes == j

        # distance_transform_edt returns distance from each True pixel to the
        # nearest False pixel, in pixel units (with anisotropy 1.0 by default).
        distances = distance_transform_edt(conductor_mask_global)
        if isinstance(distances, tuple):
            distances = distances[0]
        deep = material_mask & (distances > depth_pixels)
        new_rgb[deep] = np.array(blacken_color, dtype=np.uint8)

    return Usermap(
        new_rgb,
        UsermapMetadata(
            pixel_width_m=usermap.pixel_width_m,
            name=usermap.meta.name + " (skin-masked)",
            source=usermap.meta.source,
        ),
        material_lookup=usermap.material_lookup,
        unknown_warning=False,
    )


__all__ = ["compute_delta", "mask_skin_depth"]
