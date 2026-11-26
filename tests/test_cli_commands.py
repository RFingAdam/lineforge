"""CLI command coverage beyond the Phase 0/1 smoke tests in test_cli.py.

Exercises the rich-table output paths, JSON-file geometry input, bitmap
workflows (solve --bmp, import-bmp, render), sweep with CSV/Touchstone export,
target-z0 / optimize, run-script, clear-cache, view and the material
sub-commands, plus their argument-validation exits.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lineforge.cli import app

FIXTURES = Path(__file__).parent / "fixtures" / "usermaps"
COAX_50 = FIXTURES / "air_coax_50ohm.bmp"

MICROSTRIP = ["--type", "microstrip", "--W", "6mil", "--H", "4mil", "--T", "1.4mil", "--er", "4.4"]


@pytest.fixture(scope="module")
def small_coax(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Coarse (~24 px) air coax BMP, Z0 ~ 50 ohm, small enough to solve quickly.

    The checked-in fixtures are fine-grained parity references and take far
    too long for a CLI smoke test.
    """
    from tests.fixtures.geometries import build_coax_usermap

    path = tmp_path_factory.mktemp("usermaps") / "coax_coarse.bmp"
    build_coax_usermap(0.5e-3, 1.15e-3, pixel_width_m=1e-4, er=1.0).to_bmp(path)
    return path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep solver-result caching out of the user's real cache directory."""
    monkeypatch.setenv("ATLC3_CACHE_DIR", str(tmp_path / "cache"))
    from lineforge import cache

    if hasattr(cache, "_CACHE"):
        monkeypatch.setattr(cache, "_CACHE", None, raising=False)


# -- solve ------------------------------------------------------------------


def test_solve_rich_table_with_losses(runner: CliRunner) -> None:
    result = runner.invoke(app, ["solve", *MICROSTRIP, "--tan-delta", "0.02", "-f", "1GHz"])
    assert result.exit_code == 0, result.output
    for label in ("Z0", "εeff", "vp", "td/inch", "αd"):
        assert label in result.output


def test_solve_diff_pair_rich_table(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "solve",
            "--type",
            "edge_coupled_diff_microstrip",
            "--W",
            "4mil",
            "--S",
            "6mil",
            "--H",
            "4mil",
            "--T",
            "1.4mil",
            "--er",
            "4.4",
        ],
    )
    assert result.exit_code == 0, result.output
    for label in ("Z_odd", "Z_even", "Z_diff", "Z_common"):
        assert label in result.output


def test_solve_from_json_file_matches_flags(runner: CliRunner, tmp_path: Path) -> None:
    geom = tmp_path / "geom.json"
    geom.write_text(json.dumps({"W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4}))
    from_file = runner.invoke(
        app, ["solve", "--json", str(geom), "--type", "microstrip", "-o", "json"]
    )
    from_flags = runner.invoke(app, ["solve", *MICROSTRIP, "-o", "json"])
    assert from_file.exit_code == 0, from_file.output
    assert json.loads(from_file.stdout)["z0"] == pytest.approx(json.loads(from_flags.stdout)["z0"])


def test_solve_json_file_flag_overrides_file(runner: CliRunner, tmp_path: Path) -> None:
    geom = tmp_path / "geom.json"
    geom.write_text(
        json.dumps({"type": "microstrip", "W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4})
    )
    base = runner.invoke(app, ["solve", "--json", str(geom), "-o", "json"])
    wider = runner.invoke(app, ["solve", "--json", str(geom), "--W", "12mil", "-o", "json"])
    assert base.exit_code == 0 and wider.exit_code == 0
    # A wider trace has lower impedance.
    assert json.loads(wider.stdout)["z0"] < json.loads(base.stdout)["z0"]


def test_solve_without_type_or_json_is_usage_error(runner: CliRunner) -> None:
    result = runner.invoke(app, ["solve", "--W", "6mil"])
    assert result.exit_code != 0


def test_solve_bmp_requires_pixel_width(runner: CliRunner) -> None:
    result = runner.invoke(app, ["solve", "--bmp", str(COAX_50)])
    assert result.exit_code == 2


@pytest.mark.slow  # ~40 s cold CG solve of the bitmap
def test_solve_bmp_coax_json(runner: CliRunner, small_coax: Path) -> None:
    result = runner.invoke(
        app, ["solve", "--bmp", str(small_coax), "--pixel-width", "0.1mm", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    # Coarse grid, so only a loose check against the ideal 50 ohm.
    assert data["z0"] == pytest.approx(50.0, rel=0.25)


@pytest.mark.slow  # ~40 s cold CG solve of the bitmap
def test_solve_bmp_rich_table(runner: CliRunner, small_coax: Path) -> None:
    result = runner.invoke(app, ["solve", "--bmp", str(small_coax), "--pixel-width", "0.1mm"])
    assert result.exit_code == 0, result.output
    assert "Bitmap C/Gp result" in result.output
    assert "iterations" in result.output


# -- bitmap utilities ---------------------------------------------------------


def test_import_bmp_writes_json(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "coax.json"
    result = runner.invoke(
        app, ["import-bmp", str(COAX_50), "--pixel-width", "0.1mm", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "px" in result.output


def test_render_requires_bmp(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["render", "-f", "V", "-o", str(tmp_path / "x.png")])
    assert result.exit_code == 2


def test_render_requires_pixel_width(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["render", "-f", "V", "--bmp", str(COAX_50), "-o", str(tmp_path / "x.png")]
    )
    assert result.exit_code == 2


def test_render_rejects_unknown_field(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "render",
            "-f",
            "Q",
            "--bmp",
            str(COAX_50),
            "--pixel-width",
            "0.1mm",
            "-o",
            str(tmp_path / "x.png"),
        ],
    )
    assert result.exit_code == 2


@pytest.mark.slow  # ~40 s cold CG solve of the bitmap
def test_render_writes_png(runner: CliRunner, tmp_path: Path, small_coax: Path) -> None:
    out = tmp_path / "v.png"
    result = runner.invoke(
        app,
        ["render", "-f", "v", "--bmp", str(small_coax), "--pixel-width", "0.1mm", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    from PIL import Image

    with Image.open(out) as img:
        assert img.format == "PNG"
        assert img.size[0] > 0 and img.size[1] > 0


# -- sweep / optimize ----------------------------------------------------------


def test_sweep_width_writes_csv(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "sweep.csv"
    result = runner.invoke(
        app,
        [
            "sweep",
            "--type",
            "microstrip",
            "--param",
            "W",
            "--values",
            "4mil,6mil,8mil",
            "--W",
            "6mil",
            "--H",
            "4mil",
            "--T",
            "1.4mil",
            "--er",
            "4.4",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    rows = list(csv.reader(out.open(encoding="utf-8")))
    header, body = rows[0], rows[1:]
    assert header[0] == "W" and "z0" in header
    assert len(body) == 3
    z0 = [float(r[header.index("z0")]) for r in body]
    assert z0[0] > z0[1] > z0[2]  # impedance falls as the trace widens


def test_sweep_frequency_touchstone_export(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "line.s2p"
    result = runner.invoke(
        app,
        [
            "sweep",
            *MICROSTRIP,
            "--param",
            "frequency",
            "--values",
            "1GHz,2GHz,3GHz",
            "--touchstone-out",
            str(out),
            "--line-length",
            "10mm",
        ],
    )
    assert result.exit_code == 0, result.output
    written = next(tmp_path.glob("line*.s2p"))
    text = written.read_text()
    assert "#" in text  # option line
    assert "length=10mm" in result.output


def test_target_z0_hits_50_ohm(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "target-z0",
            "--type",
            "microstrip",
            "--target",
            "50",
            "--fixed",
            "H=4mil,T=1.4mil,er=4.4",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "W (mil)" in result.output
    assert "success" in result.output and "yes" in result.output


def test_optimize_microstrip_width(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "optimize",
            "--type",
            "microstrip",
            "--target",
            "z0=50",
            "--vary",
            "W=1mil:20mil",
            "--fixed",
            "H=4mil,T=1.4mil,er=4.4",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Optimization result" in result.output
    assert "z0 (achieved)" in result.output


# -- run-script / cache / view / mcp-serve ------------------------------------------


def test_run_script_dry_run(runner: CliRunner, tmp_path: Path) -> None:
    script = tmp_path / "design.txt"
    script.write_text("| comment\nname MyDesign\npixel 0.1mm\nthreads 2\n")
    result = runner.invoke(app, ["run-script", str(script), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "parsed successfully" in result.output


def test_run_script_unknown_command_fails(runner: CliRunner, tmp_path: Path) -> None:
    script = tmp_path / "bad.txt"
    script.write_text("definitely_not_a_command 1\n")
    result = runner.invoke(app, ["run-script", str(script), "--dry-run"])
    assert result.exit_code != 0


def test_clear_cache_reports_count(runner: CliRunner) -> None:
    result = runner.invoke(app, ["clear-cache"])
    assert result.exit_code == 0, result.output
    assert "Cleared" in result.output


def test_view_delegates_to_viewer(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, str]] = []
    import lineforge.viewer

    monkeypatch.setattr(
        lineforge.viewer, "run_viewer", lambda bmp, pixel_width: calls.append((bmp, pixel_width))
    )
    result = runner.invoke(app, ["view", "--bmp", str(COAX_50), "--pixel-width", "0.1mm"])
    assert result.exit_code == 0, result.output
    assert calls == [(COAX_50, "0.1mm")]


def test_mcp_serve_stdio_starts_server(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[bool] = []
    import lineforge.mcp_server.server

    monkeypatch.setattr(lineforge.mcp_server.server, "run_stdio", lambda: started.append(True))
    result = runner.invoke(app, ["mcp-serve"])
    assert result.exit_code == 0, result.output
    assert started == [True]


# -- material sub-commands ------------------------------------------------------


def test_material_list(runner: CliRunner) -> None:
    result = runner.invoke(app, ["material", "list"])
    assert result.exit_code == 0, result.output
    assert "atlc2 default materials" in result.output


def test_material_show_match_and_miss(runner: CliRunner) -> None:
    from lineforge.materials import ATLC2_DEFAULTS

    name = ATLC2_DEFAULTS[0].name
    hit = runner.invoke(app, ["material", "show", name])
    assert hit.exit_code == 0, hit.output
    assert name in hit.output

    miss = runner.invoke(app, ["material", "show", "zzz-no-such-material-zzz"])
    assert miss.exit_code == 1


def test_material_load_json_pack_truncates_listing(runner: CliRunner, tmp_path: Path) -> None:
    from lineforge.materials import ATLC2_DEFAULTS

    records = [m.model_dump(mode="json") for m in ATLC2_DEFAULTS]
    if len(records) <= 10:
        pytest.skip("needs more than 10 default materials to exercise truncation")
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"materials": records}))
    result = runner.invoke(app, ["material", "load", str(pack)])
    assert result.exit_code == 0, result.output
    assert f"Loaded {len(records)} materials" in result.output.replace("\x1b", "")
    assert "more)" in result.output
