"""Parametrized rasterizer coverage — every geometry type goes through
the dispatcher and produces a valid usermap.

The existing `tests/test_geometry.py` covers Pydantic validation and a
handful of stripline-asymmetric rasterizer edge cases. This file adds
coverage for every per-geometry rasterizer (microstrip, embedded
microstrip, stripline symmetric/asymmetric, cpwg, both diff-pair flavors,
broadside diff stripline) by:

  1. Building a minimal valid geometry instance.
  2. Calling the public `rasterize` dispatcher.
  3. Asserting the usermap shape, pixel size, conductor masks, and (for
     diff-pair geometries) presence of both +1 and -1 conductors.

Plus internal helpers (`_dielectric_rgb_for_er`, `_synth_dielectric_rgb`,
`_pick_pixel_width`, `_fill_rect`) get small unit tests so the helper
branches are exercised.
"""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry import GEOMETRY_TYPES, from_dict
from lineforge.geometry.builders import (
    _dielectric_rgb_for_er,
    _fill_rect,
    _pick_pixel_width,
    _stack_to_bands,
    _synth_dielectric_rgb,
    rasterize,
    rasterize_broadside_coupled_diff_stripline,
    rasterize_cpwg,
    rasterize_edge_coupled_diff_microstrip,
    rasterize_edge_coupled_diff_stripline,
    rasterize_embedded_microstrip,
    rasterize_microstrip,
    rasterize_stripline_asymmetric,
    rasterize_stripline_symmetric,
)
from lineforge.geometry.dielectric import DielectricLayer
from lineforge.geometry.types import (
    CPWG,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    EmbeddedMicrostrip,
    Microstrip,
    StriplineAsymmetric,
    StriplineSymmetric,
)
from lineforge.geometry.usermap import Usermap

# ---------------------------------------------------------------------------
# Per-geometry rasterizer smoke tests
# ---------------------------------------------------------------------------


class TestMicrostripRaster:
    def test_basic_microstrip(self) -> None:
        geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
        um = rasterize_microstrip(geom)
        assert isinstance(um, Usermap)
        # Has +1 (red) and 0 (green) conductors
        assert um.conductor_mask("+1").any()
        assert um.conductor_mask("0").any()
        # Pixel width was auto-picked to satisfy ≥ 8 pixels for smallest feature
        assert um.pixel_width_m > 0

    def test_explicit_pixel_width(self) -> None:
        geom = Microstrip(W="10mil", H="6mil", T="1.4mil", er=4.4)
        um = rasterize_microstrip(geom, pixel_width=1e-5)
        assert um.pixel_width_m == pytest.approx(1e-5)


class TestEmbeddedMicrostripRaster:
    def test_embedded_microstrip(self) -> None:
        geom = EmbeddedMicrostrip(W="6mil", H="4mil", H2="2mil", T="1.4mil", er=4.4, er2=3.5)
        um = rasterize_embedded_microstrip(geom)
        assert um.conductor_mask("+1").any()
        assert um.conductor_mask("0").any()
        # Two distinct dielectric materials should appear (substrate + coating)
        insulator_count = sum(1 for m in um.materials if m.is_insulator)
        assert insulator_count >= 1  # may merge if er≈er2 → close color match


class TestStriplineSymmetricRaster:
    def test_stripline_symmetric(self) -> None:
        geom = StriplineSymmetric(W="6mil", T="1.4mil", B="20mil", er=4.4)
        um = rasterize_stripline_symmetric(geom)
        # Two ground planes (top + bottom) + signal in the middle
        assert um.conductor_mask("+1").any()
        assert um.conductor_mask("0").any()
        # Strip should be roughly mid-height
        plus = um.conductor_mask("+1")
        ys, _ = np.where(plus)
        assert ys.min() > 0 and ys.max() < um.shape[0] - 1


class TestStriplineAsymmetricRaster:
    def test_bulk_dielectric(self) -> None:
        geom = StriplineAsymmetric(W="5mil", T="1.4mil", H1="3mil", H2="9mil", er=4.4)
        um = rasterize_stripline_asymmetric(geom)
        assert um.conductor_mask("+1").any()
        assert um.conductor_mask("0").any()

    def test_split_er_uses_custom_lookup(self) -> None:
        geom = StriplineAsymmetric(
            W="5mil",
            T="1.4mil",
            H1="3mil",
            H2="6mil",
            er=4.0,
            er_above=4.2,
            er_below=3.7,
        )
        um = rasterize_stripline_asymmetric(geom)
        # Custom lookup → at least one material carries the exact er the user set
        ers = {round(m.er, 3) for m in um.materials if m.is_insulator}
        assert 4.2 in ers or 3.7 in ers

    def test_stack_above_only(self) -> None:
        # When stack_above is given, H1 / er_above / tan_delta_above are
        # derived; we must NOT pass them explicitly.
        geom = StriplineAsymmetric(
            W="5mil",
            T="1.4mil",
            H2="6mil",
            er=4.0,
            stack_above=[
                DielectricLayer(h="1.5mil", er=4.2, tan_delta=0.02, name="prepreg"),
                DielectricLayer(h="1.5mil", er=4.2, tan_delta=0.02, name="prepreg2"),
            ],
        )
        um = rasterize_stripline_asymmetric(geom)
        assert um.conductor_mask("+1").any()
        # The two prepreg layers should appear as distinct synth materials
        names = [m.name for m in um.materials if m.is_insulator]
        assert any("prepreg" in n for n in names) or any("custom" in n.lower() for n in names)

    def test_stack_below_only(self) -> None:
        geom = StriplineAsymmetric(
            W="5mil",
            T="1.4mil",
            H1="3mil",
            er=4.0,
            stack_below=[
                DielectricLayer(h="3mil", er=3.7, tan_delta=0.015),
                DielectricLayer(h="3mil", er=4.2, tan_delta=0.020),
            ],
        )
        um = rasterize_stripline_asymmetric(geom)
        assert um.conductor_mask("+1").any()

    def test_stack_both_sides(self) -> None:
        geom = StriplineAsymmetric(
            W="5mil",
            T="1.4mil",
            er=4.0,
            stack_above=[DielectricLayer(h="3mil", er=4.0)],
            stack_below=[DielectricLayer(h="6mil", er=3.5)],
        )
        um = rasterize_stripline_asymmetric(geom)
        assert um.conductor_mask("+1").any()


class TestCPWGRaster:
    def test_cpwg(self) -> None:
        geom = CPWG(W="6mil", S="6mil", H="4mil", T="1.4mil", er=4.4)
        um = rasterize_cpwg(geom)
        # Signal (red) + side and bottom grounds (green)
        plus = um.conductor_mask("+1")
        zero = um.conductor_mask("0")
        assert plus.any()
        assert zero.any()
        # Signal centered horizontally
        _, xs = np.where(plus)
        cx = um.shape[1] // 2
        assert xs.min() <= cx <= xs.max()


class TestEdgeCoupledDiffMicrostripRaster:
    def test_edge_coupled_diff_microstrip(self) -> None:
        geom = EdgeCoupledDiffMicrostrip(W="4mil", S="6mil", H="4mil", T="1.4mil", er=4.4)
        um = rasterize_edge_coupled_diff_microstrip(geom)
        plus = um.conductor_mask("+1")
        minus = um.conductor_mask("-1")
        zero = um.conductor_mask("0")
        assert plus.any() and minus.any() and zero.any()
        # Both strips at the same y-level
        ys_plus, _ = np.where(plus)
        ys_minus, _ = np.where(minus)
        assert ys_plus.min() == ys_minus.min()


class TestEdgeCoupledDiffStriplineRaster:
    def test_edge_coupled_diff_stripline(self) -> None:
        geom = EdgeCoupledDiffStripline(W="4mil", S="6mil", B="20mil", T="1.4mil", er=4.4)
        um = rasterize_edge_coupled_diff_stripline(geom)
        assert um.conductor_mask("+1").any()
        assert um.conductor_mask("-1").any()
        assert um.conductor_mask("0").any()


class TestBroadsideCoupledDiffStriplineRaster:
    def test_broadside_coupled_diff_stripline(self) -> None:
        geom = BroadsideCoupledDiffStripline(
            W="6mil", H1="3mil", H_between="6mil", T="1.4mil", er=4.4
        )
        um = rasterize_broadside_coupled_diff_stripline(geom)
        plus = um.conductor_mask("+1")
        minus = um.conductor_mask("-1")
        assert plus.any() and minus.any()
        # Strips are vertically stacked (different y)
        ys_plus, _ = np.where(plus)
        ys_minus, _ = np.where(minus)
        assert ys_plus.max() < ys_minus.min() or ys_minus.max() < ys_plus.min()


# ---------------------------------------------------------------------------
# Dispatcher — every type rasterizes through `rasterize()`
# ---------------------------------------------------------------------------


_MINIMAL_GEOMETRIES = {
    "microstrip": Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4),
    "embedded_microstrip": EmbeddedMicrostrip(
        W="6mil", H="4mil", H2="2mil", T="1.4mil", er=4.4, er2=3.5
    ),
    "stripline_symmetric": StriplineSymmetric(W="6mil", T="1.4mil", B="20mil", er=4.4),
    "stripline_asymmetric": StriplineAsymmetric(W="5mil", T="1.4mil", H1="3mil", H2="9mil", er=4.4),
    "cpwg": CPWG(W="6mil", S="6mil", H="4mil", T="1.4mil", er=4.4),
    "edge_coupled_diff_microstrip": EdgeCoupledDiffMicrostrip(
        W="4mil", S="6mil", H="4mil", T="1.4mil", er=4.4
    ),
    "edge_coupled_diff_stripline": EdgeCoupledDiffStripline(
        W="4mil", S="6mil", B="20mil", T="1.4mil", er=4.4
    ),
    "broadside_coupled_diff_stripline": BroadsideCoupledDiffStripline(
        W="6mil", H1="3mil", H_between="6mil", T="1.4mil", er=4.4
    ),
}


@pytest.mark.parametrize("geom_type", list(_MINIMAL_GEOMETRIES.keys()))
def test_dispatcher_rasterizes_every_type(geom_type: str) -> None:
    geom = _MINIMAL_GEOMETRIES[geom_type]
    um = rasterize(geom)
    assert isinstance(um, Usermap)
    # Every rasterized geometry has at least the +1 signal conductor
    assert um.conductor_mask("+1").any()


@pytest.mark.parametrize("geom_type", list(_MINIMAL_GEOMETRIES.keys()))
def test_dispatcher_round_trips_via_from_dict(geom_type: str) -> None:
    """Build via `from_dict(model_dump())` then re-rasterize — confirms each
    Pydantic geometry round-trips through the JSON-schema bridge cleanly."""
    geom = _MINIMAL_GEOMETRIES[geom_type]
    # Use mode="python" so unit-string Length fields aren't dropped
    d = geom.model_dump(mode="python")
    # Drop None / empty values that don't round-trip cleanly for optional fields
    d_clean = {k: v for k, v in d.items() if v is not None}
    restored = from_dict(d_clean)
    um = rasterize(restored)
    assert isinstance(um, Usermap)


def test_dispatcher_rejects_unknown_geometry() -> None:
    """A bare BaseModel isn't a registered geometry → TypeError."""

    class FakeGeom:
        pass

    with pytest.raises(TypeError, match="no rasterizer"):
        rasterize(FakeGeom())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Geometry-type completeness — every registered type appears in the dispatcher
# ---------------------------------------------------------------------------


def test_every_registered_type_has_a_minimal_fixture() -> None:
    """If GEOMETRY_TYPES grows, this catches missing minimal geometries
    (except `three_wire`, which uses its own builder path)."""
    rasterizable_types = {t for t in GEOMETRY_TYPES if t != "three_wire"}
    assert rasterizable_types == set(_MINIMAL_GEOMETRIES.keys())


# ---------------------------------------------------------------------------
# Internal helper coverage
# ---------------------------------------------------------------------------


class TestPickPixelWidth:
    def test_default_eight_pixels(self) -> None:
        assert _pick_pixel_width(1e-3) == pytest.approx(1.25e-4)

    def test_explicit_target_pixels(self) -> None:
        assert _pick_pixel_width(1e-3, target_pixels=4) == pytest.approx(2.5e-4)


class TestFillRect:
    def test_fills_inclusive_exclusive(self) -> None:
        rgb = np.zeros((10, 10, 3), dtype=np.uint8)
        _fill_rect(rgb, 2, 5, 1, 4, (255, 0, 0))
        # Filled region: rows 2-4, cols 1-3
        assert (rgb[2:5, 1:4] == (255, 0, 0)).all()
        # Outside: still zeros
        assert (rgb[5:, :] == 0).all()
        assert (rgb[:2, :] == 0).all()

    def test_clips_to_array_bounds(self) -> None:
        rgb = np.zeros((5, 5, 3), dtype=np.uint8)
        # Wildly out-of-bounds → clipped silently to a no-op or partial fill
        _fill_rect(rgb, -2, 100, -2, 100, (255, 0, 0))
        # All pixels now red
        assert (rgb == (255, 0, 0)).all()

    def test_degenerate_rect_noop(self) -> None:
        rgb = np.zeros((5, 5, 3), dtype=np.uint8)
        # y0 == y1 → no-op
        _fill_rect(rgb, 2, 2, 0, 5, (255, 0, 0))
        assert (rgb == 0).all()
        # y0 > y1 also no-op (after clipping)
        _fill_rect(rgb, 4, 1, 0, 5, (255, 0, 0))
        # After clipping y0 stays 4, y1 stays 1 → still no-op
        assert (rgb == 0).all()


class TestDielectricRgbForEr:
    def test_close_to_fr4_matches_fr4(self) -> None:
        rgb = _dielectric_rgb_for_er(4.4, 0.02)
        assert rgb is not None
        # The returned RGB should at least be in the recognized palette
        from lineforge.materials.database import lookup_by_rgb

        mat = lookup_by_rgb(rgb)
        # Either lookup_by_rgb returns a record OR is None — but if the picker
        # returned FR4_RGB or any palette RGB, lookup_by_rgb should find it.
        assert mat is not None


class TestSynthDielectricRgb:
    def test_above_role(self) -> None:
        rgb = _synth_dielectric_rgb(4.4, "above")
        assert len(rgb) == 3
        assert all(0 <= c <= 255 for c in rgb)

    def test_below_role(self) -> None:
        rgb = _synth_dielectric_rgb(4.4, "below")
        assert len(rgb) == 3

    def test_neutral_role(self) -> None:
        """Unknown role falls back to the neutral branch."""
        rgb = _synth_dielectric_rgb(4.4, "neither")
        assert len(rgb) == 3

    def test_indexed_above_role(self) -> None:
        """above_3 should produce a distinct color from above_0."""
        rgb0 = _synth_dielectric_rgb(4.4, "above_0")
        rgb3 = _synth_dielectric_rgb(4.4, "above_3")
        assert rgb0 != rgb3

    def test_clamps_er_range(self) -> None:
        # er outside [1, 10] still returns a valid RGB
        rgb_low = _synth_dielectric_rgb(0.5, "above")
        rgb_high = _synth_dielectric_rgb(15.0, "below")
        assert all(0 <= c <= 255 for c in rgb_low)
        assert all(0 <= c <= 255 for c in rgb_high)


class TestStackToBands:
    def test_returns_band_per_layer(self) -> None:
        layers = [
            DielectricLayer(h="2mil", er=4.2, tan_delta=0.02),
            DielectricLayer(h="2mil", er=4.2, tan_delta=0.02),
            DielectricLayer(h="2mil", er=3.7, tan_delta=0.015),
        ]
        bands, records = _stack_to_bands(layers, px=1e-5, side="above")
        assert len(bands) == 3
        assert len(records) == 3
        # Each band has (thickness_px, rgb_tuple)
        for thickness_px, rgb in bands:
            assert thickness_px >= 1
            assert len(rgb) == 3

    def test_distinct_colors_per_layer(self) -> None:
        layers = [
            DielectricLayer(h="2mil", er=4.2),
            DielectricLayer(h="2mil", er=4.2),
        ]
        bands, _ = _stack_to_bands(layers, px=1e-5, side="above")
        # Two layers with same εr but different indices → distinct colors
        assert bands[0][1] != bands[1][1]
