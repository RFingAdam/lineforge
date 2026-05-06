"""CLI tests covering Phase 0 (--help, --version, info, mcp-serve guard) and Phase 1 (solve)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from atlc3.cli import app
from atlc3.version import __version__


def _runner() -> CliRunner:
    return CliRunner()


# -- Phase 0 -----------------------------------------------------------------


def test_help_works() -> None:
    result = _runner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "atlc3" in result.stdout


def test_version_flag() -> None:
    result = _runner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_info_command() -> None:
    result = _runner().invoke(app, ["info"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_mcp_serve_unsupported_transport_rejected() -> None:
    result = _runner().invoke(app, ["mcp-serve", "--transport", "sse"])
    assert result.exit_code == 2


# -- Phase 1: solve / list-geometries / describe-geometry --------------------


def test_list_geometries() -> None:
    result = _runner().invoke(app, ["list-geometries"])
    assert result.exit_code == 0
    assert "microstrip" in result.stdout
    assert "stripline_symmetric" in result.stdout
    assert "cpwg" in result.stdout


def test_describe_geometry_known() -> None:
    result = _runner().invoke(app, ["describe-geometry", "microstrip"])
    assert result.exit_code == 0
    assert "microstrip" in result.stdout


def test_describe_geometry_unknown() -> None:
    result = _runner().invoke(app, ["describe-geometry", "not-a-thing"])
    assert result.exit_code == 2


def test_solve_microstrip_via_flags() -> None:
    result = _runner().invoke(
        app,
        [
            "solve",
            "--type", "microstrip",
            "--W", "6mil",
            "--H", "4mil",
            "--T", "1.4mil",
            "--er", "4.4",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Z0" in result.stdout


def test_solve_microstrip_json_output() -> None:
    result = _runner().invoke(
        app,
        [
            "solve",
            "--type", "microstrip",
            "--W", "6mil",
            "--H", "4mil",
            "--T", "1.4mil",
            "--er", "4.4",
            "--output", "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert "z0" in parsed
    assert parsed["z0"] > 0


def test_solve_diff_pair_via_flags() -> None:
    result = _runner().invoke(
        app,
        [
            "solve",
            "--type", "edge_coupled_diff_microstrip",
            "--W", "4mil",
            "--S", "6mil",
            "--H", "4mil",
            "--T", "1.4mil",
            "--er", "4.4",
            "--output", "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert "z_diff" in parsed


def test_solve_validation_error_exits_2() -> None:
    result = _runner().invoke(
        app,
        ["solve", "--type", "microstrip", "--W", "6mil", "--er", "4.4"],
    )
    assert result.exit_code == 2


def test_export_schema() -> None:
    result = _runner().invoke(app, ["export-schema"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "oneOf" in parsed
