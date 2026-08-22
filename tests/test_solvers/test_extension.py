"""Tests for `lineforge.solvers.extension`.

Covers `extend` (atlc2-style padding to 3200×3200) and `extend_to_shape`
(explicit target dimensions).
"""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.solvers import extension


def _tiny_usermap(h: int = 21, w: int = 21) -> Usermap:
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)  # vacuum
    rgb[0, :] = (0, 255, 0)  # green ground at top
    rgb[-1, :] = (0, 255, 0)  # green ground at bottom
    rgb[h // 2, w // 2] = (255, 0, 0)  # red signal in the middle
    return Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4, name="tiny", source="test"))


class TestExtend:
    """`extend` pads the usermap toward atlc2's 3200×3200 target."""

    def test_already_large_returns_unchanged(self) -> None:
        """When the input is already ≥ target_size, no padding is applied."""
        # Use a small target_size so we don't need a literal 3200×3200 usermap
        rgb = np.full((50, 50, 3), 255, dtype=np.uint8)
        rgb[0, 0] = (0, 255, 0)  # at least one non-vacuum pixel so materials list isn't empty
        um = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4, name="big", source="test"))
        extended = extension.extend(um, target_size=40, inner_pad=2)
        # h=50, w=50 both ≥ 40 → returned unchanged (identity)
        assert extended is um

    def test_small_target_uses_inner_pad_only(self) -> None:
        """When inner_pad lifts us above target_size, the outer-pad branch is
        a no-op (pad_h==pad_w==0) and we return after the inner pad."""
        um = _tiny_usermap(h=11, w=11)
        # target_size = 21: inner_pad of 6 produces 23×23 (already ≥ 21)
        extended = extension.extend(um, target_size=21, inner_pad=6)
        eh, ew = extended.shape
        assert eh == 11 + 2 * 6
        assert ew == 11 + 2 * 6

    def test_full_pad_to_target(self) -> None:
        """When inner_pad alone doesn't reach target_size, the outer-pad branch
        replicates further to bring the grid to (approximately) target_size."""
        um = _tiny_usermap(h=11, w=11)
        target = 51
        inner = 4
        extended = extension.extend(um, target_size=target, inner_pad=inner)
        eh, ew = extended.shape
        # After inner_pad=4 → 19×19. Then outer-pad adds max((51-19)//2, (51-19)//2) = 16
        # on each side → 51×51 (or close).
        assert eh >= target
        assert ew >= target

    def test_default_target_pads_close_to_target(self) -> None:
        """The outer-pad branch brings the grid close to (but not necessarily
        exactly at) target_size due to integer division."""
        um = _tiny_usermap(h=11, w=11)
        # Raise max_factor so the input-size cap doesn't kick in for this test.
        extended = extension.extend(um, target_size=200, inner_pad=10, max_factor=100)
        eh, ew = extended.shape
        # 11 + 2*10 = 31; pad = (200-31)//2 = 84; final = 31 + 2*84 = 199 (off by 1)
        assert eh >= 199
        assert ew >= 199

    def test_input_size_cap_prevents_3200_blowup(self) -> None:
        """Regression for #32: a small synthetic usermap must not be padded to
        the atlc2 3200 default, which would produce a ~10 M-pixel grid."""
        um = _tiny_usermap(h=44, w=90)  # the microstrip OOM repro size
        extended = extension.extend(um)  # default target_size=3200, max_factor=16
        eh, ew = extended.shape
        # Effective target = min(3200, 16 * max(44, 90)) = 16 * 90 = 1440
        # so the final grid must be well under 3200×3200.
        assert eh < 1700, f"height {eh} exceeded expected cap"
        assert ew < 1700, f"width {ew} exceeded expected cap"

    def test_returns_usermap_instance(self) -> None:
        um = _tiny_usermap()
        out = extension.extend(um, target_size=51, inner_pad=4)
        assert isinstance(out, Usermap)
        # Pixel width is preserved through padding.
        assert out.pixel_width_m == um.pixel_width_m


class TestExtendToShape:
    """`extend_to_shape` pads to specific target dimensions."""

    def test_no_op_when_already_at_target(self) -> None:
        um = _tiny_usermap(h=21, w=21)
        out = extension.extend_to_shape(um, 21, 21)
        assert out is um

    def test_pad_to_larger_shape(self) -> None:
        um = _tiny_usermap(h=11, w=11)
        out = extension.extend_to_shape(um, 31, 31)
        oh, ow = out.shape
        # Padding by `max(pad_h, pad_w) = max(10, 10) = 10` on each side → 31×31
        assert oh == 31
        assert ow == 31

    def test_returns_usermap_instance(self) -> None:
        um = _tiny_usermap(h=11, w=11)
        out = extension.extend_to_shape(um, 21, 21)
        assert isinstance(out, Usermap)
        # Materials are re-parsed but the metadata's pixel_width carries over.
        assert out.pixel_width_m == um.pixel_width_m

    def test_smaller_target_is_no_op(self) -> None:
        """If the requested target is smaller than the input, the function
        bails early with no padding (it does NOT crop)."""
        um = _tiny_usermap(h=21, w=21)
        out = extension.extend_to_shape(um, 5, 5)
        # No-op when pad_h==pad_w==0
        assert out is um


class TestExtendPreservesEdgePixels:
    """Edge replication keeps the outer pixel color around: important so the
    open-boundary BC is a plausible material, not raw black/whatever."""

    def test_edge_replication_extends_ground(self) -> None:
        """Top + bottom rows are green ground; after extension, the extra rows
        replicate green at the top / green at the bottom."""
        um = _tiny_usermap(h=11, w=11)
        out = extension.extend(um, target_size=21, inner_pad=4)
        # The original top row was (0, 255, 0). The replicated rows above
        # should also be green.
        assert tuple(out.rgb[0, out.shape[1] // 2]) == (0, 255, 0)
        # The original bottom row was (0, 255, 0); same for replicated rows below.
        assert tuple(out.rgb[-1, out.shape[1] // 2]) == (0, 255, 0)


@pytest.mark.parametrize("inner_pad", [0, 1, 5, 10])
def test_extend_inner_pad_variations(inner_pad: int) -> None:
    """Every inner_pad value (including 0) produces a valid Usermap with
    dimensions ≥ original."""
    um = _tiny_usermap(h=11, w=11)
    out = extension.extend(um, target_size=21, inner_pad=inner_pad)
    oh, ow = out.shape
    assert oh >= 11
    assert ow >= 11
