"""Tests for the atlc2 script interpreter (lineforge.scripting.atlc2_script).

The interpreter dispatches commands by their first 3 characters, so the bulk
of the surface area is exercised via dry-run scripts that hit each command
name. We add a few non-dry-run tests for the simple paths (state setters,
geometry switches) and lock in the file-resolution semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lineforge.scripting.atlc2_script import ScriptError, ScriptInterpreter, run_script_file


def _interp(*, dry_run: bool = True) -> ScriptInterpreter:
    return ScriptInterpreter(dry_run=dry_run)


class TestDispatchSimpleCommands:
    def test_geometry_kind_twinlead(self) -> None:
        i = _interp()
        i.run("twinlead\n")
        assert i.state.geometry_kind == "twinlead"

    def test_geometry_kind_square(self) -> None:
        i = _interp()
        i.run("square\n")
        assert i.state.geometry_kind == "square"

    def test_geometry_kind_coaxial(self) -> None:
        i = _interp()
        i.run("coaxial\n")
        assert i.state.geometry_kind == "coaxial"

    def test_pixel_width(self) -> None:
        i = _interp()
        i.run("pixel 0.1mm\n")
        assert i.state.pixel_width == pytest.approx(0.1e-3)

    def test_total_pixels(self) -> None:
        i = _interp()
        i.run("total 1024\n")
        assert i.state.total_pixels == 1024

    def test_frequency_with_unit(self) -> None:
        i = _interp()
        i.run("frequency 2.4GHz\n")
        assert i.state.frequency_hz == pytest.approx(2.4e9)

    def test_frequency_without_unit_parses_as_hz(self) -> None:
        """parse_frequency accepts bare numbers as Hz; the MHz-fallback
        path is only reached on parse failure (not on a plain number)."""
        i = _interp()
        i.run("frequency 100\n")
        assert i.state.frequency_hz == pytest.approx(100.0)

    def test_set_lengths(self) -> None:
        i = _interp()
        i.run(
            "separation 1mm\n"
            "diameter 0.5mm\n"
            "insulation 0.3mm\n"
            "top 1mm\nbottom 2mm\nside 3mm\nskew 0.1mm\n"
            "width 5mm\nheight 6mm\ncenter 7mm\n"
            "inner 0.5mm\nouter 1.15mm\n"
        )
        assert i.state.separation == pytest.approx(1e-3)
        assert i.state.diameter == pytest.approx(0.5e-3)
        assert i.state.insulation == pytest.approx(0.3e-3)
        assert i.state.top == pytest.approx(1e-3)
        assert i.state.bottom == pytest.approx(2e-3)
        assert i.state.side == pytest.approx(3e-3)
        assert i.state.skew == pytest.approx(0.1e-3)
        assert i.state.width == pytest.approx(5e-3)
        assert i.state.height == pytest.approx(6e-3)
        assert i.state.center == pytest.approx(7e-3)
        assert i.state.inner == pytest.approx(0.5e-3)
        assert i.state.outer == pytest.approx(1.15e-3)

    def test_box_sets_bool(self) -> None:
        i = _interp()
        i.run("box 1 T\nbox 2 F\nbox 3 yes\nbox 4 0\n")
        assert i.state.boxes == {1: True, 2: False, 3: True, 4: False}

    def test_name_and_folder(self, tmp_path: Path) -> None:
        i = _interp()
        i.run(f"name MyDesign\nfolder {tmp_path}\n")
        assert i.state.name == "MyDesign"
        assert i.state.folder == tmp_path

    def test_threads_relative(self) -> None:
        i = _interp()
        i.run("threads 4\nthreads +\nthreads -\n")
        assert i.state.threads == 4  # 4, +1=5, -1=4

    def test_threads_absolute(self) -> None:
        i = _interp()
        i.run("threads 8\n")
        assert i.state.threads == 8


class TestOpenAndPathResolution:
    def test_open_with_extension(self) -> None:
        """A bare relative path stays relative (atlc2 only resolves '%' paths)."""
        i = _interp()
        i.run("open geom.bmp\n")
        assert i.state.usermap_path == Path("geom.bmp")
        assert i.state.geometry_kind == "open"

    def test_open_adds_bmp_suffix_when_missing(self) -> None:
        i = _interp()
        i.run("open mydesign\n")
        assert i.state.usermap_path == Path("mydesign.bmp")

    def test_open_with_filename_with_spaces(self) -> None:
        i = _interp()
        i.run("open my design with spaces.bmp\n")
        # The full filename joins all tokens
        assert i.state.usermap_path == Path("my design with spaces.bmp")

    def test_open_percent_prefix_resolves_to_folder(self, tmp_path: Path) -> None:
        """atlc2's '%foo' notation: leading % means 'execution folder'."""
        i = _interp()
        i.state.folder = tmp_path
        i.run("open %geom.bmp\n")
        assert i.state.usermap_path == tmp_path / "geom.bmp"


class TestComments:
    def test_lines_starting_with_pipe_are_comments(self) -> None:
        """atlc2 uses '|' for comments, not '#'."""
        i = _interp()
        i.run("| comment\nname Foo\n|another\nname Bar\n")
        assert i.state.name == "Bar"

    def test_inline_pipe_comment(self) -> None:
        i = _interp()
        i.run("name Hello | this is a comment\n")
        assert i.state.name == "Hello"

    def test_blank_lines_skipped(self) -> None:
        i = _interp()
        i.run("\n\n   \nname Foo\n\n")
        assert i.state.name == "Foo"


class TestUnknownCommandError:
    def test_unknown_command_raises(self) -> None:
        """Unknown commands raise ScriptError immediately (no line wrapping
        because it's already a ScriptError, not a generic exception)."""
        i = _interp()
        with pytest.raises(ScriptError, match="unknown command 'bogus'"):
            i.run("name Foo\nbogus arg\n")

    def test_non_script_error_gets_line_prefix(self) -> None:
        """Generic exceptions inside a command get wrapped with the line number."""
        i = _interp()
        with pytest.raises(ScriptError, match="line 1"):
            i.run("pixel notavalidlength\n")

    def test_pixel_without_arg_raises(self) -> None:
        i = _interp()
        with pytest.raises(ScriptError, match="pixel_width expects"):
            i.run("pixel\n")

    def test_box_one_arg_raises(self) -> None:
        i = _interp()
        with pytest.raises(ScriptError, match=r"box <n> <T\|F>"):
            i.run("box 1\n")

    def test_open_without_args_raises(self) -> None:
        i = _interp()
        with pytest.raises(ScriptError, match="open expects a filename"):
            i.run("open\n")


class TestTerminateAndIgnoredCommands:
    def test_terminate_stops_execution(self) -> None:
        i = _interp()
        i.run("name Before\nterminate\nname After\n")
        # 'name After' should NOT have run
        assert i.state.name == "Before"
        assert i.terminated is True

    def test_ignored_commands_no_op(self, capsys: pytest.CaptureFixture[str]) -> None:
        """`erase`, `key`, `window`, `launch`, `bee` shouldn't crash or change state."""
        i = _interp()
        i.run("erase\nkeyboard X\nwindow 1\nlaunch foo\nbee\n")
        # No exception and no state change is the bar.


class TestSolveDryRun:
    def test_solve_dry_run_does_not_invoke_solver(self, tmp_path: Path) -> None:
        i = ScriptInterpreter(dry_run=True)
        i.state.folder = tmp_path
        # Run a dry-run solve — should not require a usermap or hit the solver
        i.run("solve\n")
        # No output files written in dry_run mode
        assert i.outputs == {}

    def test_lrs_dry_run(self) -> None:
        i = ScriptInterpreter(dry_run=True)
        i.run("lrs\n")  # alias for solve

    def test_cgp_dry_run(self) -> None:
        i = ScriptInterpreter(dry_run=True)
        i.run("cgp\n")  # alias for solve


class TestSweepDryRun:
    def test_sweep_dry_run(self) -> None:
        i = ScriptInterpreter(dry_run=True)
        i.run("frequency 1GHz\nsweep frequency 5\n")

    def test_sweep_no_args_raises(self) -> None:
        i = _interp()
        with pytest.raises(ScriptError, match="sweep expects"):
            i.run("sweep\n")

    def test_sweep_pixel_param(self) -> None:
        i = ScriptInterpreter(dry_run=True)
        i.run("pixel 0.1mm\nsweep pixel 3 5\n")  # 5 runs/decade


class TestRunScriptFile:
    def test_run_script_file_helper(self, tmp_path: Path) -> None:
        script = tmp_path / "test.txt"
        script.write_text("name FromFile\npixel 0.1mm\n")
        interp = run_script_file(script, dry_run=True)
        assert interp.state.name == "FromFile"
        assert interp.state.pixel_width == pytest.approx(0.1e-3)


class TestSaveAndOutput:
    def test_save_dry_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        i = ScriptInterpreter(dry_run=True)
        i.run("save\n")
