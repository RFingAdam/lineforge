"""Rasterizers — convert parameterized geometry models into Usermaps.

These functions build a usermap from a Pydantic geometry, picking pixel size to
satisfy the atlc2 best-practice rule: gap between conductors must be ≥ 5 px.
The rasterized result is suitable for the Phase 2/3 numerical kernels and is
used by the dispatcher when an analytical formula isn't available or when the
user explicitly requests the bitmap path.

For the standard PCB geometries, the rasterized result agrees with the analytical
closed-form to within 1% (Phase 2.5 AC).
"""

from __future__ import annotations

from typing import Final

import numpy as np

from atlc3.geometry.types import (
    CPWG,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    EmbeddedMicrostrip,
    GeometryUnion,
    Microstrip,
    StriplineAsymmetric,
    StriplineSymmetric,
)
from atlc3.geometry.usermap import Usermap, UsermapMetadata

# atlc2 default colors used by the rasterizer:
RED_PLUS_ONE: Final[tuple[int, int, int]] = (255, 0, 0)  # signal trace (V=+1)
GREEN_GROUND: Final[tuple[int, int, int]] = (0, 255, 0)  # ground plane (V=0)
BLUE_MINUS_ONE: Final[tuple[int, int, int]] = (0, 0, 255)  # signal- (V=-1)
BLACK_VACUUM: Final[tuple[int, int, int]] = (0, 0, 0)
FR4_RGB: Final[tuple[int, int, int]] = (223, 247, 136)  # atlc2's FR4
WHITE_VACUUM: Final[tuple[int, int, int]] = (255, 255, 255)


def _dielectric_rgb_for_er(er: float, tan_delta: float) -> tuple[int, int, int]:
    """Pick a default atlc2 color for a dielectric matching er/tan_delta closely.

    Falls back to FR4 if no good match is found.
    """
    from atlc3.materials.database import ATLC2_DEFAULTS

    best = None
    best_err = float("inf")
    for m in ATLC2_DEFAULTS:
        if not m.is_insulator:
            continue
        # weighted distance: εr matters more than tanδ
        err = abs(m.er - er) + 10 * abs(m.tan_delta - tan_delta)
        if err < best_err:
            best_err = err
            best = m
    return best.rgb if best is not None else FR4_RGB


def _pick_pixel_width(min_feature_m: float, target_pixels: int = 8) -> float:
    """Choose a pixel width such that the smallest feature spans ``target_pixels``."""
    return min_feature_m / target_pixels


def _fill_rect(
    rgb: np.ndarray, y0: int, y1: int, x0: int, x1: int, color: tuple[int, int, int]
) -> None:
    """Fill an inclusive-exclusive box in the RGB array."""
    h, w, _ = rgb.shape
    y0 = max(0, y0)
    y1 = min(h, y1)
    x0 = max(0, x0)
    x1 = min(w, x1)
    if y0 >= y1 or x0 >= x1:
        return
    rgb[y0:y1, x0:x1] = np.array(color, dtype=np.uint8)


# ---------------------------------------------------------------------------
# Per-geometry rasterizers
# ---------------------------------------------------------------------------


def rasterize_microstrip(
    geom: Microstrip,
    *,
    pixel_width: float | None = None,
    margin_pixels: int = 8,
) -> Usermap:
    """Rasterize a Microstrip into a Usermap.

    Layout (top-to-bottom):
        - ``margin_pixels`` of vacuum (air above the strip).
        - The strip (red, ``W`` wide × ``T`` thick), centered horizontally.
        - The dielectric (FR4-colored, ``H`` thick).
        - 1-pixel ground plane (green) at the bottom, then ``margin_pixels`` of vacuum.
    """
    px = pixel_width or _pick_pixel_width(min(geom.H, geom.T, geom.W))
    air_above_px = margin_pixels
    strip_t_px = max(1, round(geom.T / px))
    sub_h_px = max(2, round(geom.H / px))
    ground_px = 1
    air_below_px = margin_pixels

    strip_w_px = max(2, round(geom.W / px))
    horizontal_margin = max(margin_pixels, strip_w_px)
    total_w = strip_w_px + 2 * horizontal_margin

    total_h = air_above_px + strip_t_px + sub_h_px + ground_px + air_below_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)

    # Substrate
    sub_y0 = air_above_px + strip_t_px
    sub_y1 = sub_y0 + sub_h_px
    diel = _dielectric_rgb_for_er(geom.er, geom.tan_delta)
    _fill_rect(rgb, sub_y0, sub_y1, 0, total_w, diel)

    # Ground plane
    _fill_rect(rgb, sub_y1, sub_y1 + ground_px, 0, total_w, GREEN_GROUND)

    # Strip
    strip_x0 = horizontal_margin
    strip_x1 = strip_x0 + strip_w_px
    _fill_rect(rgb, air_above_px, air_above_px + strip_t_px, strip_x0, strip_x1, RED_PLUS_ONE)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name=f"microstrip-W{geom.W * 1e6:.1f}um",
            source="atlc3.geometry.builders.rasterize_microstrip",
        ),
    )


def rasterize_embedded_microstrip(
    geom: EmbeddedMicrostrip,
    *,
    pixel_width: float | None = None,
    margin_pixels: int = 8,
) -> Usermap:
    """Like rasterize_microstrip but with a coating dielectric covering the strip."""
    px = pixel_width or _pick_pixel_width(min(geom.H, geom.H2, geom.T, geom.W))
    coat_t_px = max(1, round(geom.H2 / px))
    air_above_px = margin_pixels
    strip_t_px = max(1, round(geom.T / px))
    sub_h_px = max(2, round(geom.H / px))
    ground_px = 1
    air_below_px = margin_pixels

    strip_w_px = max(2, round(geom.W / px))
    horizontal_margin = max(margin_pixels, strip_w_px)
    total_w = strip_w_px + 2 * horizontal_margin
    total_h = air_above_px + coat_t_px + strip_t_px + sub_h_px + ground_px + air_below_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)

    coat_y0 = air_above_px
    strip_y0 = coat_y0 + coat_t_px
    sub_y0 = strip_y0 + strip_t_px
    sub_y1 = sub_y0 + sub_h_px

    coat_color = _dielectric_rgb_for_er(geom.er2, geom.tan_delta_2)
    sub_color = _dielectric_rgb_for_er(geom.er, geom.tan_delta)

    _fill_rect(rgb, coat_y0, strip_y0, 0, total_w, coat_color)
    _fill_rect(rgb, sub_y0, sub_y1, 0, total_w, sub_color)
    _fill_rect(rgb, sub_y1, sub_y1 + ground_px, 0, total_w, GREEN_GROUND)

    strip_x0 = horizontal_margin
    strip_x1 = strip_x0 + strip_w_px
    _fill_rect(rgb, strip_y0, sub_y0, strip_x0, strip_x1, RED_PLUS_ONE)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name="embedded_microstrip",
            source="atlc3.geometry.builders.rasterize_embedded_microstrip",
        ),
    )


def rasterize_stripline_symmetric(
    geom: StriplineSymmetric,
    *,
    pixel_width: float | None = None,
    horizontal_margin_pixels: int = 16,
) -> Usermap:
    """Symmetric stripline: strip centered between two ground planes filled with dielectric."""
    px = pixel_width or _pick_pixel_width(min(geom.B, geom.T, geom.W))
    cavity_px = max(4, round(geom.B / px))
    strip_t_px = max(1, round(geom.T / px))
    strip_w_px = max(2, round(geom.W / px))
    ground_px = 1

    strip_y_offset = (cavity_px - strip_t_px) // 2

    horizontal_margin = max(horizontal_margin_pixels, strip_w_px)
    total_w = strip_w_px + 2 * horizontal_margin
    total_h = 2 * ground_px + cavity_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)

    # Top ground plane
    _fill_rect(rgb, 0, ground_px, 0, total_w, GREEN_GROUND)
    # Cavity (dielectric)
    diel = _dielectric_rgb_for_er(geom.er, geom.tan_delta)
    _fill_rect(rgb, ground_px, ground_px + cavity_px, 0, total_w, diel)
    # Bottom ground plane
    _fill_rect(rgb, ground_px + cavity_px, total_h, 0, total_w, GREEN_GROUND)

    # Strip (red)
    sy0 = ground_px + strip_y_offset
    sy1 = sy0 + strip_t_px
    sx0 = horizontal_margin
    sx1 = sx0 + strip_w_px
    _fill_rect(rgb, sy0, sy1, sx0, sx1, RED_PLUS_ONE)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name="stripline_symmetric",
            source="atlc3.geometry.builders.rasterize_stripline_symmetric",
        ),
    )


def rasterize_stripline_asymmetric(
    geom: StriplineAsymmetric,
    *,
    pixel_width: float | None = None,
    horizontal_margin_pixels: int = 16,
) -> Usermap:
    px = pixel_width or _pick_pixel_width(min(geom.H1, geom.H2, geom.T, geom.W))
    h1_px = max(2, round(geom.H1 / px))
    h2_px = max(2, round(geom.H2 / px))
    strip_t_px = max(1, round(geom.T / px))
    strip_w_px = max(2, round(geom.W / px))
    ground_px = 1

    cavity_px = h1_px + strip_t_px + h2_px
    horizontal_margin = max(horizontal_margin_pixels, strip_w_px)
    total_w = strip_w_px + 2 * horizontal_margin
    total_h = 2 * ground_px + cavity_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)

    _fill_rect(rgb, 0, ground_px, 0, total_w, GREEN_GROUND)
    diel = _dielectric_rgb_for_er(geom.er, geom.tan_delta)
    _fill_rect(rgb, ground_px, ground_px + cavity_px, 0, total_w, diel)
    _fill_rect(rgb, ground_px + cavity_px, total_h, 0, total_w, GREEN_GROUND)

    sy0 = ground_px + h1_px
    sy1 = sy0 + strip_t_px
    sx0 = horizontal_margin
    sx1 = sx0 + strip_w_px
    _fill_rect(rgb, sy0, sy1, sx0, sx1, RED_PLUS_ONE)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name="stripline_asymmetric",
            source="atlc3.geometry.builders.rasterize_stripline_asymmetric",
        ),
    )


def rasterize_cpwg(
    geom: CPWG,
    *,
    pixel_width: float | None = None,
    side_ground_pixels: int = 16,
    margin_pixels: int = 8,
) -> Usermap:
    """CPWG: signal + two coplanar grounds, with a substrate ground plane below."""
    px = pixel_width or _pick_pixel_width(min(geom.H, geom.T, geom.S, geom.W))
    air_above_px = margin_pixels
    cond_t_px = max(1, round(geom.T / px))
    sub_h_px = max(2, round(geom.H / px))
    bottom_ground_px = 1
    air_below_px = margin_pixels

    sig_w_px = max(2, round(geom.W / px))
    gap_px = max(2, round(geom.S / px))
    side_gnd_px = side_ground_pixels

    total_w = sig_w_px + 2 * (gap_px + side_gnd_px) + 2 * margin_pixels
    total_h = air_above_px + cond_t_px + sub_h_px + bottom_ground_px + air_below_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)

    sub_y0 = air_above_px + cond_t_px
    sub_y1 = sub_y0 + sub_h_px
    diel = _dielectric_rgb_for_er(geom.er, geom.tan_delta)
    _fill_rect(rgb, sub_y0, sub_y1, 0, total_w, diel)
    _fill_rect(rgb, sub_y1, sub_y1 + bottom_ground_px, 0, total_w, GREEN_GROUND)

    # Signal trace
    cx_center = total_w // 2
    sig_x0 = cx_center - sig_w_px // 2
    sig_x1 = sig_x0 + sig_w_px
    _fill_rect(rgb, air_above_px, air_above_px + cond_t_px, sig_x0, sig_x1, RED_PLUS_ONE)

    # Side ground rails
    left_x1 = sig_x0 - gap_px
    left_x0 = left_x1 - side_gnd_px
    right_x0 = sig_x1 + gap_px
    right_x1 = right_x0 + side_gnd_px
    _fill_rect(rgb, air_above_px, air_above_px + cond_t_px, left_x0, left_x1, GREEN_GROUND)
    _fill_rect(rgb, air_above_px, air_above_px + cond_t_px, right_x0, right_x1, GREEN_GROUND)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name="cpwg",
            source="atlc3.geometry.builders.rasterize_cpwg",
        ),
    )


def rasterize_edge_coupled_diff_microstrip(
    geom: EdgeCoupledDiffMicrostrip,
    *,
    pixel_width: float | None = None,
    margin_pixels: int = 16,
) -> Usermap:
    px = pixel_width or _pick_pixel_width(min(geom.H, geom.T, geom.S, geom.W))
    air_above_px = margin_pixels
    strip_t_px = max(1, round(geom.T / px))
    sub_h_px = max(2, round(geom.H / px))
    ground_px = 1
    air_below_px = margin_pixels

    strip_w_px = max(2, round(geom.W / px))
    gap_px = max(2, round(geom.S / px))
    horizontal_margin = max(margin_pixels, strip_w_px * 2)
    total_w = 2 * strip_w_px + gap_px + 2 * horizontal_margin
    total_h = air_above_px + strip_t_px + sub_h_px + ground_px + air_below_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)
    sub_y0 = air_above_px + strip_t_px
    sub_y1 = sub_y0 + sub_h_px
    diel = _dielectric_rgb_for_er(geom.er, geom.tan_delta)
    _fill_rect(rgb, sub_y0, sub_y1, 0, total_w, diel)
    _fill_rect(rgb, sub_y1, sub_y1 + ground_px, 0, total_w, GREEN_GROUND)

    # Two strips (red = +1, blue = -1)
    cx = total_w // 2
    s1_x0 = cx - gap_px // 2 - strip_w_px
    s1_x1 = s1_x0 + strip_w_px
    s2_x0 = cx + gap_px // 2
    s2_x1 = s2_x0 + strip_w_px
    sy0 = air_above_px
    sy1 = air_above_px + strip_t_px
    _fill_rect(rgb, sy0, sy1, s1_x0, s1_x1, RED_PLUS_ONE)
    _fill_rect(rgb, sy0, sy1, s2_x0, s2_x1, BLUE_MINUS_ONE)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name="edge_coupled_diff_microstrip",
            source="atlc3.geometry.builders.rasterize_edge_coupled_diff_microstrip",
        ),
    )


def rasterize_edge_coupled_diff_stripline(
    geom: EdgeCoupledDiffStripline,
    *,
    pixel_width: float | None = None,
    horizontal_margin_pixels: int = 16,
) -> Usermap:
    px = pixel_width or _pick_pixel_width(min(geom.B, geom.T, geom.S, geom.W))
    cavity_px = max(4, round(geom.B / px))
    strip_t_px = max(1, round(geom.T / px))
    strip_w_px = max(2, round(geom.W / px))
    gap_px = max(2, round(geom.S / px))
    ground_px = 1

    strip_y_offset = (cavity_px - strip_t_px) // 2

    horizontal_margin = max(horizontal_margin_pixels, strip_w_px * 2)
    total_w = 2 * strip_w_px + gap_px + 2 * horizontal_margin
    total_h = 2 * ground_px + cavity_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)
    _fill_rect(rgb, 0, ground_px, 0, total_w, GREEN_GROUND)
    diel = _dielectric_rgb_for_er(geom.er, geom.tan_delta)
    _fill_rect(rgb, ground_px, ground_px + cavity_px, 0, total_w, diel)
    _fill_rect(rgb, ground_px + cavity_px, total_h, 0, total_w, GREEN_GROUND)

    cx = total_w // 2
    s1_x0 = cx - gap_px // 2 - strip_w_px
    s1_x1 = s1_x0 + strip_w_px
    s2_x0 = cx + gap_px // 2
    s2_x1 = s2_x0 + strip_w_px
    sy0 = ground_px + strip_y_offset
    sy1 = sy0 + strip_t_px
    _fill_rect(rgb, sy0, sy1, s1_x0, s1_x1, RED_PLUS_ONE)
    _fill_rect(rgb, sy0, sy1, s2_x0, s2_x1, BLUE_MINUS_ONE)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name="edge_coupled_diff_stripline",
            source="atlc3.geometry.builders.rasterize_edge_coupled_diff_stripline",
        ),
    )


def rasterize_broadside_coupled_diff_stripline(
    geom: BroadsideCoupledDiffStripline,
    *,
    pixel_width: float | None = None,
    horizontal_margin_pixels: int = 16,
) -> Usermap:
    px = pixel_width or _pick_pixel_width(min(geom.H1, geom.H_between, geom.T, geom.W))
    h1_px = max(2, round(geom.H1 / px))
    hb_px = max(2, round(geom.H_between / px))
    strip_t_px = max(1, round(geom.T / px))
    strip_w_px = max(2, round(geom.W / px))
    ground_px = 1

    cavity_px = h1_px + strip_t_px + hb_px + strip_t_px + h1_px
    horizontal_margin = max(horizontal_margin_pixels, strip_w_px)
    total_w = strip_w_px + 2 * horizontal_margin
    total_h = 2 * ground_px + cavity_px

    rgb = np.full((total_h, total_w, 3), WHITE_VACUUM, dtype=np.uint8)
    _fill_rect(rgb, 0, ground_px, 0, total_w, GREEN_GROUND)
    diel = _dielectric_rgb_for_er(geom.er, geom.tan_delta)
    _fill_rect(rgb, ground_px, ground_px + cavity_px, 0, total_w, diel)
    _fill_rect(rgb, ground_px + cavity_px, total_h, 0, total_w, GREEN_GROUND)

    sx0 = horizontal_margin
    sx1 = sx0 + strip_w_px
    s1_y0 = ground_px + h1_px
    s1_y1 = s1_y0 + strip_t_px
    s2_y0 = s1_y1 + hb_px
    s2_y1 = s2_y0 + strip_t_px
    _fill_rect(rgb, s1_y0, s1_y1, sx0, sx1, RED_PLUS_ONE)
    _fill_rect(rgb, s2_y0, s2_y1, sx0, sx1, BLUE_MINUS_ONE)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=px,
            name="broadside_coupled_diff_stripline",
            source="atlc3.geometry.builders.rasterize_broadside_coupled_diff_stripline",
        ),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def rasterize(
    geometry: GeometryUnion,
    *,
    pixel_width: float | None = None,
) -> Usermap:
    """Convert any supported geometry to a Usermap.

    Parameters
    ----------
    geometry
        Any model from :mod:`atlc3.geometry.types`.
    pixel_width
        Optional pixel side length [m]. If omitted, picked automatically so the
        smallest feature spans about 8 pixels.
    """
    match geometry:
        case Microstrip():
            return rasterize_microstrip(geometry, pixel_width=pixel_width)
        case EmbeddedMicrostrip():
            return rasterize_embedded_microstrip(geometry, pixel_width=pixel_width)
        case StriplineSymmetric():
            return rasterize_stripline_symmetric(geometry, pixel_width=pixel_width)
        case StriplineAsymmetric():
            return rasterize_stripline_asymmetric(geometry, pixel_width=pixel_width)
        case CPWG():
            return rasterize_cpwg(geometry, pixel_width=pixel_width)
        case EdgeCoupledDiffMicrostrip():
            return rasterize_edge_coupled_diff_microstrip(geometry, pixel_width=pixel_width)
        case EdgeCoupledDiffStripline():
            return rasterize_edge_coupled_diff_stripline(geometry, pixel_width=pixel_width)
        case BroadsideCoupledDiffStripline():
            return rasterize_broadside_coupled_diff_stripline(geometry, pixel_width=pixel_width)
        case _:
            raise TypeError(f"no rasterizer for {type(geometry).__name__}")


__all__ = [
    "rasterize",
    "rasterize_broadside_coupled_diff_stripline",
    "rasterize_cpwg",
    "rasterize_edge_coupled_diff_microstrip",
    "rasterize_edge_coupled_diff_stripline",
    "rasterize_embedded_microstrip",
    "rasterize_microstrip",
    "rasterize_stripline_asymmetric",
    "rasterize_stripline_symmetric",
]
