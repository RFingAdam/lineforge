"""Tests for lineforge.visualization.fields: covers every FieldKind + edge cases."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from lineforge.visualization.fields import render_contour_lines, render_field


@pytest.fixture
def voltage_field() -> np.ndarray:
    """A 32×32 voltage field with a saddle: V ranges roughly [-1, 1]."""
    n = 32
    y, x = np.mgrid[0:n, 0:n]
    cy, cx = n / 2, n / 2
    r = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    return np.exp(-r * r / 100) - 0.3  # bell shape, signed


@pytest.fixture
def er_field(voltage_field: np.ndarray) -> np.ndarray:
    """A simple 2-region εr map matching the voltage field shape."""
    er = np.full(voltage_field.shape, 4.4, dtype=float)
    er[: voltage_field.shape[0] // 2, :] = 1.0  # top half vacuum
    return er


@pytest.fixture
def tan_field(voltage_field: np.ndarray) -> np.ndarray:
    return np.full(voltage_field.shape, 0.02, dtype=float)


class TestRenderField:
    def test_v_mode(self, voltage_field: np.ndarray) -> None:
        img = render_field("V", v_field=voltage_field)
        assert isinstance(img, Image.Image)
        assert img.size == (voltage_field.shape[1], voltage_field.shape[0])
        assert img.mode == "RGB"
        # Non-trivial output: at least 2 distinct colors
        unique = {tuple(p) for p in np.array(img).reshape(-1, 3)}
        assert len(unique) > 1

    def test_e_mode(self, voltage_field: np.ndarray) -> None:
        img = render_field("E", v_field=voltage_field)
        assert img.size == (voltage_field.shape[1], voltage_field.shape[0])

    def test_d_mode(self, voltage_field: np.ndarray, er_field: np.ndarray) -> None:
        img = render_field("D", v_field=voltage_field, er_field=er_field)
        assert img.size == (voltage_field.shape[1], voltage_field.shape[0])

    def test_t_mode(
        self,
        voltage_field: np.ndarray,
        er_field: np.ndarray,
        tan_field: np.ndarray,
    ) -> None:
        img = render_field("T", v_field=voltage_field, er_field=er_field, tan_delta_field=tan_field)
        assert img.size == (voltage_field.shape[1], voltage_field.shape[0])

    def test_j_mode(self) -> None:
        j = np.random.RandomState(0).rand(20, 20)
        img = render_field("J", j_field=j)
        assert img.size == (20, 20)

    def test_u_mode_returns_black_canvas(self, voltage_field: np.ndarray) -> None:
        img = render_field("U", v_field=voltage_field)
        assert img.size == (voltage_field.shape[1], voltage_field.shape[0])
        # All pixels should be black
        assert (np.array(img) == 0).all()

    def test_intensity_sqrt_changes_output(self, voltage_field: np.ndarray) -> None:
        linear = np.array(render_field("E", v_field=voltage_field, intensity="linear"))
        sqrt = np.array(render_field("E", v_field=voltage_field, intensity="sqrt"))
        assert not np.array_equal(linear, sqrt)


class TestRenderFieldErrors:
    def test_v_mode_missing_v_field(self) -> None:
        with pytest.raises(ValueError, match="V mode needs v_field"):
            render_field("V")

    def test_e_mode_missing_v_field(self) -> None:
        with pytest.raises(ValueError, match="E mode needs v_field"):
            render_field("E")

    def test_d_mode_missing_er_field(self, voltage_field: np.ndarray) -> None:
        with pytest.raises(ValueError, match="D mode needs v_field and er_field"):
            render_field("D", v_field=voltage_field)

    def test_t_mode_missing_tan(self, voltage_field: np.ndarray, er_field: np.ndarray) -> None:
        with pytest.raises(ValueError, match="T mode needs v_field, er_field, tan_delta_field"):
            render_field("T", v_field=voltage_field, er_field=er_field)

    def test_j_mode_missing_j_field(self) -> None:
        with pytest.raises(ValueError, match="J mode needs j_field"):
            render_field("J")

    def test_unknown_kind(self) -> None:
        with pytest.raises(ValueError, match="unknown field kind"):
            render_field("X")  # type: ignore[arg-type]


class TestNormalizeEdgeCases:
    def test_constant_field_renders_as_uniform(self, voltage_field: np.ndarray) -> None:
        """A field with hi == lo should render without crashing (zero-norm path)."""
        flat = np.zeros_like(voltage_field)
        img = render_field("E", v_field=flat)
        assert img.size == (flat.shape[1], flat.shape[0])

    def test_all_nonfinite_field(self, voltage_field: np.ndarray) -> None:
        """A field with no finite values should not crash."""
        nan_field = np.full_like(voltage_field, np.nan)
        img = render_field("E", v_field=nan_field)
        assert img.size == (nan_field.shape[1], nan_field.shape[0])


class TestRenderContourLines:
    def test_basic_contour(self, voltage_field: np.ndarray) -> None:
        img = render_contour_lines(voltage_field, levels=8)
        assert isinstance(img, Image.Image)
        assert img.size == (voltage_field.shape[1], voltage_field.shape[0])
        # Should have BOTH background and line colors
        arr = np.array(img)
        unique = {tuple(p) for p in arr.reshape(-1, 3)}
        assert len(unique) >= 2

    def test_custom_colors(self, voltage_field: np.ndarray) -> None:
        img = render_contour_lines(
            voltage_field,
            levels=4,
            line_color=(255, 0, 0),
            background=(0, 255, 0),
        )
        arr = np.array(img)
        # Only red and green (and possibly nothing else) appear
        unique = {tuple(p) for p in arr.reshape(-1, 3)}
        assert (255, 0, 0) in unique
        assert (0, 255, 0) in unique

    def test_constant_field_no_crash(self) -> None:
        flat = np.full((20, 20), 0.5, dtype=float)
        img = render_contour_lines(flat)
        # All-same field has hi == lo; output is just the background.
        arr = np.array(img)
        unique = {tuple(p) for p in arr.reshape(-1, 3)}
        assert unique == {(0, 0, 0)}  # only background

    def test_all_nonfinite_no_crash(self) -> None:
        nan_field = np.full((20, 20), np.nan, dtype=float)
        img = render_contour_lines(nan_field)
        # Output is still an image, just blank.
        assert img.size == (20, 20)


class TestColorMapsCoverFullRange:
    def test_viridis_low_high_distinct(self, voltage_field: np.ndarray) -> None:
        """An E-field with non-degenerate range should produce both dark and
        light pixels (not a single color)."""
        img = np.array(render_field("E", v_field=voltage_field))
        brightness = img.sum(axis=2)
        assert brightness.min() < brightness.max()

    def test_seismic_blue_white_red_present(self, voltage_field: np.ndarray) -> None:
        """V mode uses a seismic colormap; with a saddle field we should see
        both blueish (low) and reddish (high) pixels."""
        img = np.array(render_field("V", v_field=voltage_field))
        # Pixel with R > B (red-leaning) somewhere
        red_lean = (img[..., 0] > img[..., 2] + 50).any()
        # Pixel with B > R (blue-leaning) somewhere
        blue_lean = (img[..., 2] > img[..., 0] + 50).any()
        assert red_lean and blue_lean
