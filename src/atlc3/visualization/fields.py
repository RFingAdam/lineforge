"""Field renderers — V, E, D, J, loss → PIL Image.

These mirror atlc2's keyboard-driven view modes:

    U — Usermap (no field)            atlc2 keystroke: U
    V — voltage field                  atlc2 keystroke: V
    E — electric field magnitude       atlc2 keystroke: E
    D — D-field magnitude (εE)         atlc2 keystroke: D
    T — dielectric loss density        atlc2 keystroke: T
    J — current density (Phase 3)      atlc2 keystroke: J

Plus contour line plots for V (atlc2's L key) and E (N key).
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from PIL import Image

FieldKind = Literal["U", "V", "E", "D", "T", "J"]


def _normalize(arr: np.ndarray, mode: str = "linear") -> np.ndarray:
    """Map ``arr`` to the [0, 1] range, optionally with a sqrt boost (atlc2 'H' mode)."""
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr)
    lo = float(finite.min())
    hi = float(finite.max())
    if hi == lo:
        return np.zeros_like(arr)
    norm = (arr - lo) / (hi - lo)
    if mode == "sqrt":
        norm = np.sqrt(np.clip(norm, 0, 1))
    return np.clip(norm, 0, 1)


def _viridis_lut() -> np.ndarray:
    """Tiny 256-step Viridis LUT, no matplotlib dependency."""
    # Seven color stops sampled from matplotlib viridis
    stops = np.array(
        [
            (68, 1, 84),
            (72, 40, 120),
            (62, 73, 137),
            (49, 104, 142),
            (38, 130, 142),
            (53, 183, 121),
            (109, 205, 89),
            (180, 222, 44),
            (253, 231, 37),
        ],
        dtype=np.float64,
    )
    n_stops = len(stops)
    out = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        t = i / 255.0 * (n_stops - 1)
        idx = int(t)
        frac = t - idx
        if idx >= n_stops - 1:
            out[i] = stops[-1].astype(np.uint8)
        else:
            mix = stops[idx] * (1 - frac) + stops[idx + 1] * frac
            out[i] = mix.astype(np.uint8)
    return out


_VIRIDIS = _viridis_lut()


def _seismic_lut() -> np.ndarray:
    """Symmetric blue→white→red colormap for signed fields like V."""
    stops = np.array([(0, 0, 128), (255, 255, 255), (128, 0, 0)], dtype=np.float64)
    out = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        t = i / 255.0 * (len(stops) - 1)
        idx = int(t)
        frac = t - idx
        if idx >= len(stops) - 1:
            out[i] = stops[-1].astype(np.uint8)
        else:
            mix = stops[idx] * (1 - frac) + stops[idx + 1] * frac
            out[i] = mix.astype(np.uint8)
    return out


_SEISMIC = _seismic_lut()


def _e_field(v_field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute (Ex, Ey) via central differences. Pixel units."""
    Ex = np.zeros_like(v_field)
    Ex[:, 1:-1] = -(v_field[:, 2:] - v_field[:, :-2]) / 2.0
    Ey = np.zeros_like(v_field)
    Ey[1:-1, :] = -(v_field[2:, :] - v_field[:-2, :]) / 2.0
    return Ex, Ey


def render_field(
    kind: FieldKind,
    *,
    v_field: np.ndarray | None = None,
    er_field: np.ndarray | None = None,
    tan_delta_field: np.ndarray | None = None,
    j_field: np.ndarray | None = None,
    intensity: Literal["linear", "sqrt"] = "linear",
) -> Image.Image:
    """Render a field as a PIL ``Image`` (RGB, 8-bit).

    Parameters
    ----------
    kind
        One of ``"U"`` (no field, returns black), ``"V"``, ``"E"``, ``"D"``,
        ``"T"``, ``"J"``.
    v_field, er_field, tan_delta_field, j_field
        Pass whichever fields are needed for ``kind``. Missing required fields
        raise :class:`ValueError`.
    intensity
        ``"linear"`` or ``"sqrt"`` (atlc2's 'H' high-intensity mode).
    """
    if kind == "V":
        if v_field is None:
            raise ValueError("V mode needs v_field")
        # signed colormap centered at 0
        norm = (v_field - v_field.min()) / max(1e-12, v_field.max() - v_field.min())
        idx = (np.clip(norm, 0, 1) * 255).astype(np.int32)
        rgb = _SEISMIC[idx]
        return Image.fromarray(rgb, mode="RGB")

    if kind == "E":
        if v_field is None:
            raise ValueError("E mode needs v_field")
        Ex, Ey = _e_field(v_field)
        mag = np.sqrt(Ex * Ex + Ey * Ey)
        norm = _normalize(mag, intensity)
        idx = (norm * 255).astype(np.int32)
        return Image.fromarray(_VIRIDIS[idx], mode="RGB")

    if kind == "D":
        if v_field is None or er_field is None:
            raise ValueError("D mode needs v_field and er_field")
        Ex, Ey = _e_field(v_field)
        mag = er_field * np.sqrt(Ex * Ex + Ey * Ey)
        norm = _normalize(mag, intensity)
        idx = (norm * 255).astype(np.int32)
        return Image.fromarray(_VIRIDIS[idx], mode="RGB")

    if kind == "T":
        if v_field is None or er_field is None or tan_delta_field is None:
            raise ValueError("T mode needs v_field, er_field, tan_delta_field")
        Ex, Ey = _e_field(v_field)
        loss = er_field * tan_delta_field * (Ex * Ex + Ey * Ey)
        norm = _normalize(loss, intensity)
        idx = (norm * 255).astype(np.int32)
        return Image.fromarray(_VIRIDIS[idx], mode="RGB")

    if kind == "J":
        if j_field is None:
            raise ValueError("J mode needs j_field (Phase 3 output)")
        norm = _normalize(np.abs(j_field), intensity)
        idx = (norm * 255).astype(np.int32)
        return Image.fromarray(_VIRIDIS[idx], mode="RGB")

    if kind == "U":
        # No field — caller should fall back to the usermap RGB itself
        h, w = (v_field if v_field is not None else np.zeros((1, 1))).shape
        return Image.new("RGB", (w, h), (0, 0, 0))

    raise ValueError(f"unknown field kind {kind!r}")


def render_contour_lines(
    v_field: np.ndarray,
    *,
    levels: int = 12,
    line_color: tuple[int, int, int] = (255, 255, 255),
    background: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Render an iso-V contour-lines plot (atlc2's 'L' key).

    Phase 2 implementation: for each isovalue, mark pixels where V crosses that
    level by checking sign change against a neighbor. Simpler than skimage's
    marching squares but produces a recognizable result.
    """
    h, w = v_field.shape
    img = np.tile(np.array(background, dtype=np.uint8), (h, w, 1))
    finite = v_field[np.isfinite(v_field)]
    if finite.size == 0:
        return Image.fromarray(img, mode="RGB")
    lo, hi = float(finite.min()), float(finite.max())
    if hi == lo:
        return Image.fromarray(img, mode="RGB")

    isovals = np.linspace(lo, hi, levels + 2)[1:-1]
    line = np.array(line_color, dtype=np.uint8)
    for v in isovals:
        diff = v_field - v
        # crossings: sign changes between adjacent pixels
        sx = np.zeros_like(diff, dtype=bool)
        sx[:, 1:] = (diff[:, 1:] * diff[:, :-1]) < 0
        sy = np.zeros_like(diff, dtype=bool)
        sy[1:, :] = (diff[1:, :] * diff[:-1, :]) < 0
        crossings = sx | sy
        img[crossings] = line
    return Image.fromarray(img, mode="RGB")


__all__ = ["FieldKind", "render_contour_lines", "render_field"]
