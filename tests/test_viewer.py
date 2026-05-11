"""Tests for lineforge.viewer.run_viewer with mocked stdin and solver.

The viewer is a keystroke-driven REPL; we exercise each command path by
patching ``builtins.input`` to feed a scripted sequence of keys. PNG outputs
land in the current working directory, so we run inside ``tmp_path``.

The full solve_cgp call is mocked because it would extend the grid to
3200×3200 and take >5 minutes per test — that's tested elsewhere
(test_atlc_bmp_parity, test_parity). Here we want to drive the *viewer*
control flow, not the solver.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from lineforge.solvers.cgp import CGPResult
from lineforge.viewer import run_viewer

FIXTURE_BMP = Path(__file__).parent / "fixtures" / "usermaps" / "air_coax_50ohm.bmp"
PIXEL_WIDTH = "12.5um"


@pytest.fixture
def viewer_cwd(tmp_path: Path) -> Path:
    """Run inside tmp_path so PNG outputs don't pollute the repo."""
    old = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(old)


def _stub_solve_cgp(usermap, *, return_fields=False, **_kwargs):  # type: ignore[no-untyped-def]
    """Lightweight stub that returns realistic shapes without running the solver."""

    h, w = usermap.rgb.shape[:2]
    v_field = np.linspace(-1.0, 1.0, h * w).reshape(h, w)
    er_field = np.full((h, w), 4.4, dtype=float)

    result = CGPResult(
        C_per_m=1.5e-10,
        Gp_per_m=0.0,
        L_per_m=4e-7,
        z0=49.94,
        vp=3e8,
        eps_eff=1.0,
        iterations=10,
        method="laplace-stub",
    )

    if not return_fields:
        return result

    class _Workspace:
        def __init__(self) -> None:
            self.v_field = v_field
            self.er_field = er_field

    return result, _Workspace()


def _run_with_keys(keys: list[str]) -> None:
    """Invoke run_viewer feeding it ``keys`` (always appends 'Q' to terminate)."""
    keys_iter = iter([*keys, "Q"])
    with (
        patch("builtins.input", side_effect=lambda _prompt="": next(keys_iter)),
        patch("lineforge.viewer.solve_cgp", side_effect=_stub_solve_cgp),
    ):
        run_viewer(FIXTURE_BMP, pixel_width=PIXEL_WIDTH)


class TestViewerCommands:
    def test_quit_immediately(self, viewer_cwd: Path) -> None:
        """Pressing Q at the prompt must exit cleanly."""
        _run_with_keys([])
        # No PNGs created on quit-only.
        assert not list(viewer_cwd.glob("*.png"))

    def test_v_renders_voltage_png(self, viewer_cwd: Path) -> None:
        _run_with_keys(["V"])
        assert (viewer_cwd / "lineforge_view_v.png").exists()

    def test_e_renders_e_field_png(self, viewer_cwd: Path) -> None:
        _run_with_keys(["E"])
        assert (viewer_cwd / "lineforge_view_e.png").exists()

    def test_d_renders_d_field_png(self, viewer_cwd: Path) -> None:
        _run_with_keys(["D"])
        assert (viewer_cwd / "lineforge_view_d.png").exists()

    def test_t_renders_loss_png(self, viewer_cwd: Path) -> None:
        _run_with_keys(["T"])
        assert (viewer_cwd / "lineforge_view_t.png").exists()

    def test_u_renders_usermap_png(self, viewer_cwd: Path) -> None:
        _run_with_keys(["U"])
        assert (viewer_cwd / "lineforge_view_u.png").exists()

    def test_l_renders_v_contours_png(self, viewer_cwd: Path) -> None:
        _run_with_keys(["L"])
        assert (viewer_cwd / "lineforge_view_lines_v.png").exists()

    def test_s_after_render_reports_path(self, viewer_cwd: Path) -> None:
        """S after a render should not crash and should reference the saved path."""
        _run_with_keys(["V", "S"])
        # Just no exception is the test bar.

    def test_s_with_no_render_is_graceful(self, viewer_cwd: Path) -> None:
        """S before any render should print a warning, not raise."""
        _run_with_keys(["S"])

    def test_unknown_command_does_not_crash(self, viewer_cwd: Path) -> None:
        _run_with_keys(["X"])  # invalid

    def test_empty_input_skips(self, viewer_cwd: Path) -> None:
        """Empty input (just Enter) should be a no-op."""
        _run_with_keys(["", "V"])
        assert (viewer_cwd / "lineforge_view_v.png").exists()

    def test_multi_command_sequence(self, viewer_cwd: Path) -> None:
        """A sequence of commands should produce the corresponding PNGs."""
        _run_with_keys(["V", "E", "D", "T", "U"])
        for kind in "vedtu":
            assert (viewer_cwd / f"lineforge_view_{kind}.png").exists()


class TestViewerEofHandling:
    def test_eof_terminates_cleanly(self, viewer_cwd: Path) -> None:
        """EOFError on input (Ctrl+D piped stdin) must cause graceful exit."""

        def raise_eof(_prompt: str = "") -> str:
            raise EOFError

        with (
            patch("builtins.input", side_effect=raise_eof),
            patch("lineforge.viewer.solve_cgp", side_effect=_stub_solve_cgp),
        ):
            run_viewer(FIXTURE_BMP, pixel_width=PIXEL_WIDTH)

    def test_keyboard_interrupt_terminates_cleanly(self, viewer_cwd: Path) -> None:
        """KeyboardInterrupt on input (Ctrl+C) must cause graceful exit."""

        def raise_kbi(_prompt: str = "") -> str:
            raise KeyboardInterrupt

        with (
            patch("builtins.input", side_effect=raise_kbi),
            patch("lineforge.viewer.solve_cgp", side_effect=_stub_solve_cgp),
        ):
            run_viewer(FIXTURE_BMP, pixel_width=PIXEL_WIDTH)
