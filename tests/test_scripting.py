"""Phase 2.15 AC: atlc2 .txt script interpreter."""

from __future__ import annotations

from pathlib import Path

import pytest

from lineforge.scripting import ScriptError, ScriptInterpreter, run_script_file


class TestParser:
    def test_parses_command_line(self) -> None:
        interp = ScriptInterpreter(dry_run=True)
        interp.run("twinlead\n")
        assert interp.state.geometry_kind == "twinlead"

    def test_comments_and_blanks(self) -> None:
        interp = ScriptInterpreter(dry_run=True)
        interp.run("| this is a comment\n\nfrequency 1e9\n")
        assert interp.state.frequency_hz == pytest.approx(1e9)

    def test_unknown_command_raises(self) -> None:
        interp = ScriptInterpreter(dry_run=True)
        with pytest.raises(ScriptError):
            interp.run("flarble 1 2 3\n")

    def test_three_letter_prefix_match(self) -> None:
        # atlc2 examines first 3 chars only: "twi" should match "twinlead"
        interp = ScriptInterpreter(dry_run=True)
        interp.run("twi\n")
        assert interp.state.geometry_kind == "twinlead"

    def test_set_length_with_unit(self) -> None:
        interp = ScriptInterpreter(dry_run=True)
        interp.run("separation 6mm\n")
        assert interp.state.separation == pytest.approx(6e-3)

    def test_box_command(self) -> None:
        interp = ScriptInterpreter(dry_run=True)
        interp.run("box 1 T\n")
        assert interp.state.boxes[1] is True

    def test_terminate(self) -> None:
        interp = ScriptInterpreter(dry_run=True)
        interp.run("frequency 1e9\nterminate\nfrequency 2e9\n")
        # terminate stopped execution before the second frequency
        assert interp.state.frequency_hz == pytest.approx(1e9)


class TestSampleScript:
    def test_atlc2_doc_sample_dry_run(self) -> None:
        script = """\
| A sample script file
twinlead
box 1 F        | restrict to skin depth
total 4000
separation 6mm
diameter 2mm
frequency .001
| sweep frequency 25 4
"""
        interp = ScriptInterpreter(dry_run=True)
        interp.run(script)
        assert interp.state.geometry_kind == "twinlead"
        assert interp.state.boxes[1] is False
        assert interp.state.separation == pytest.approx(6e-3)
        assert interp.state.diameter == pytest.approx(2e-3)
        assert interp.state.total_pixels == 4000


class TestRunScriptFile:
    def test_run_file(self, tmp_path: Path) -> None:
        path = tmp_path / "script.txt"
        path.write_text("name TestRun\n" "twinlead\n" "frequency 1e9\n" "terminate\n")
        interp = run_script_file(path, dry_run=True)
        assert interp.state.name == "TestRun"
