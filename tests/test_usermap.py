"""Phase 2.4 AC: Usermap class loads/saves images, exposes solver-friendly views."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata


def _tiny_microstrip_array() -> np.ndarray:
    """A 16×24 RGB array: red strip on a green ground over white vacuum (no dielectric)."""
    rgb = np.full((16, 24, 3), 255, dtype=np.uint8)  # white = vacuum
    rgb[3:5, 9:15] = (255, 0, 0)  # red +1 strip
    rgb[14:15, :] = (0, 255, 0)  # green ground
    return rgb


class TestUsermapBasics:
    def test_construct_from_array(self) -> None:
        rgb = _tiny_microstrip_array()
        meta = UsermapMetadata(pixel_width_m=1e-4)
        u = Usermap(rgb, meta)
        assert u.shape == (16, 24)
        assert u.pixel_width_m == 1e-4

    def test_unrecognized_pixel_warns(self) -> None:
        rgb = np.full((4, 4, 3), 123, dtype=np.uint8)  # not a known atlc2 color
        with pytest.warns(UserWarning, match="not in the material database"):
            Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))

    def test_conductor_mask(self) -> None:
        rgb = _tiny_microstrip_array()
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
        plus = u.conductor_mask("+1")
        ground = u.conductor_mask("0")
        assert plus.sum() == 2 * 6  # 2 rows × 6 cols of red
        assert ground.sum() == 1 * 24  # green ground row

    def test_voltage_bc_field(self) -> None:
        rgb = _tiny_microstrip_array()
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
        mask, value = u.voltage_bc_field()
        assert mask.any()
        assert value[3, 9] == pytest.approx(1.0)
        assert value[14, 0] == pytest.approx(0.0)

    def test_er_field_defaults_to_vacuum(self) -> None:
        rgb = _tiny_microstrip_array()
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
        er = u.er_field()
        assert er.shape == u.shape
        assert (er >= 1).all()

    def test_replicate_edges(self) -> None:
        rgb = _tiny_microstrip_array()
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
        u2 = u.replicate_edges(2)
        assert u2.shape == (16 + 4, 24 + 4)
        # corners should be the same as the original corner pixel
        assert tuple(u2.rgb[0, 0]) == tuple(rgb[0, 0])
        assert tuple(u2.rgb[-1, -1]) == tuple(rgb[-1, -1])


class TestUsermapIO:
    def test_bmp_roundtrip(self, tmp_path: Path) -> None:
        rgb = _tiny_microstrip_array()
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
        path = tmp_path / "test.bmp"
        u.to_bmp(path)
        loaded = Usermap.from_bmp(path, pixel_width="0.1mm")
        assert loaded.shape == u.shape
        np.testing.assert_array_equal(loaded.rgb, u.rgb)

    def test_png_roundtrip(self, tmp_path: Path) -> None:
        rgb = _tiny_microstrip_array()
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
        path = tmp_path / "test.png"
        u.to_png(path)
        loaded = Usermap.from_png(path, pixel_width="0.1mm")
        np.testing.assert_array_equal(loaded.rgb, u.rgb)

    def test_json_roundtrip(self, tmp_path: Path) -> None:
        rgb = _tiny_microstrip_array()
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4, name="t"))
        path = tmp_path / "test.json"
        u.to_json(path)
        loaded = Usermap.from_json(path)
        assert loaded.shape == u.shape
        assert loaded.meta.name == "t"
