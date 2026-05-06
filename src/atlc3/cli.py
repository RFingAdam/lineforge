"""atlc3 command-line interface.

Phases 0-2 surface:

    atlc3 --help / --version / info
    atlc3 list-geometries
    atlc3 describe-geometry <name>
    atlc3 export-schema
    atlc3 mcp-serve

    atlc3 solve --type … (analytical or bitmap, --method auto|analytical|cgp)
    atlc3 solve --bmp <path> --pixel-width <…>          (bitmap)

    atlc3 import-bmp <path> --pixel-width <…> --output <out.json>
    atlc3 render --result <result.json> --field <V|E|D|T> --output <out.png>
    atlc3 run-script <path>                              (atlc2 .txt scripts)

    atlc3 material list / show <name> / load <pack.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from atlc3.analytical import solve as analytical_solve
from atlc3.geometry import GEOMETRY_TYPES, export_jsonschema, from_dict
from atlc3.geometry.usermap import Usermap
from atlc3.results import DiffResult, TLineResult
from atlc3.units import parse_frequency, parse_length
from atlc3.version import __version__

app = typer.Typer(
    name="atlc3",
    help="Open-source MCP-enabled transmission line calculator (atlc3.0).",
    no_args_is_help=True,
    add_completion=False,
)

material_app = typer.Typer(name="material", help="Material database commands.")
app.add_typer(material_app)

console = Console()
err_console = Console(stderr=True, style="bold red")


# ---------------------------------------------------------------------------
# Top-level options
# ---------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"atlc3 [bold]{__version__}[/bold]")
        try:
            from atlc3 import _kernel

            console.print(
                f"  native kernel: {_kernel.version()} "
                f"(parallel={'on' if _kernel.has_parallel() else 'off'})"
            )
        except ImportError:  # pragma: no cover
            console.print("  native kernel: [yellow]not installed[/yellow]")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(  # noqa: ARG001
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """atlc3 — open-source transmission line calculator."""


# ---------------------------------------------------------------------------
# info / mcp-serve
# ---------------------------------------------------------------------------


@app.command(name="mcp-serve")
def mcp_serve(
    transport: str = typer.Option(
        "stdio", "--transport", help="MCP transport (Phase 0/1/2 supports stdio only)."
    ),
) -> None:
    """Run the atlc3 MCP server."""
    if transport != "stdio":
        err_console.print(f"Transport {transport!r} not supported.")
        raise typer.Exit(code=2)
    from atlc3.mcp_server.server import run_stdio

    run_stdio()


@app.command()
def info() -> None:
    """Show package and native-kernel info."""
    console.print(f"atlc3 version: [bold]{__version__}[/bold]")
    try:
        from atlc3 import _kernel

        console.print(f"native kernel: {_kernel.version()}")
        console.print(f"parallel: {'yes' if _kernel.has_parallel() else 'no'}")
    except ImportError:
        console.print("[yellow]native kernel not installed[/yellow]")
    console.print(f"Python: {sys.version.split()[0]}")


# ---------------------------------------------------------------------------
# Geometry introspection
# ---------------------------------------------------------------------------


@app.command(name="list-geometries")
def list_geometries() -> None:
    """List all supported transmission-line geometries."""
    table = Table(title="Supported geometries")
    table.add_column("Type", style="cyan")
    table.add_column("Class")
    table.add_column("Required fields")
    for type_name, cls in GEOMETRY_TYPES.items():
        required = ", ".join(
            name
            for name, field in cls.model_fields.items()
            if field.is_required() and name != "type"
        )
        table.add_row(type_name, cls.__name__, required)
    console.print(table)


@app.command(name="describe-geometry")
def describe_geometry(
    name: str = typer.Argument(..., help="Geometry type, e.g. 'microstrip'."),
) -> None:
    """Print the JSON Schema for a geometry type."""
    if name not in GEOMETRY_TYPES:
        err_console.print(f"Unknown geometry {name!r}.")
        err_console.print(f"Valid: {', '.join(sorted(GEOMETRY_TYPES))}")
        raise typer.Exit(code=2)
    schema = GEOMETRY_TYPES[name].model_json_schema()
    console.print_json(data=schema)


@app.command(name="export-schema")
def export_schema() -> None:
    """Print the unified JSON Schema for all supported geometries."""
    console.print_json(data=export_jsonschema())


# ---------------------------------------------------------------------------
# solve
# ---------------------------------------------------------------------------


def _coerce_lengths(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert any string-valued length fields to meters via parse_length."""
    length_fields = {"W", "H", "T", "S", "B", "H1", "H2", "H_between"}
    out = dict(raw)
    for k in list(out):
        if k in length_fields and isinstance(out[k], str):
            out[k] = parse_length(out[k])
    return out


def _build_geometry(
    type_: str | None,
    json_path: Path | None,
    overrides: dict[str, Any],
) -> Any:
    if json_path is not None:
        data = json.loads(json_path.read_text())
        data.update(overrides)
        if "type" not in data and type_:
            data["type"] = type_
        return from_dict(_coerce_lengths(data))

    if type_ is None:
        raise typer.BadParameter("either --type, --json, or --bmp is required")

    data = {"type": type_, **overrides}
    return from_dict(_coerce_lengths(data))


def _print_tline(result: TLineResult) -> None:
    table = Table(title=f"Result ({result.method})")
    table.add_column("Quantity", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Z0", f"{result.z0:.3f} Ω")
    table.add_row("εeff", f"{result.eps_eff:.4f}")
    table.add_row("vp", f"{result.vp:.4e} m/s ({result.vp / 299792458:.4f} c)")
    table.add_row("td/inch", f"{result.td_per_inch * 1e12:.3f} ps/in")
    if result.L_per_m is not None:
        table.add_row("L", f"{result.L_per_m * 1e9:.3f} nH/m")
    if result.C_per_m is not None:
        table.add_row("C", f"{result.C_per_m * 1e12:.3f} pF/m")
    if result.conductor_loss_db_per_in is not None:
        table.add_row("αc", f"{result.conductor_loss_db_per_in:.4f} dB/in")
    if result.dielectric_loss_db_per_in is not None:
        table.add_row("αd", f"{result.dielectric_loss_db_per_in:.4f} dB/in")
    console.print(table)
    for w in result.warnings:
        style = "yellow" if w.severity == "warning" else "red"
        console.print(f"[{style}]{w.severity}: {w.message}[/{style}]")


def _print_diff(result: DiffResult) -> None:
    table = Table(title=f"Differential pair ({result.method})")
    table.add_column("Quantity", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Z_odd", f"{result.z_odd:.3f} Ω")
    table.add_row("Z_even", f"{result.z_even:.3f} Ω")
    table.add_row("Z_diff", f"{result.z_diff:.3f} Ω")
    table.add_row("Z_common", f"{result.z_common:.3f} Ω")
    table.add_row("εeff (odd)", f"{result.eps_eff_odd:.4f}")
    table.add_row("εeff (even)", f"{result.eps_eff_even:.4f}")
    console.print(table)


def _print_cgp(result: Any) -> None:
    table = Table(title=f"Bitmap C/Gp result ({result.method})")
    table.add_column("Quantity", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Z0", f"{result.z0:.3f} Ω")
    table.add_row("εeff", f"{result.eps_eff:.4f}")
    table.add_row("vp", f"{result.vp:.4e} m/s ({result.vp / 299792458:.4f} c)")
    table.add_row("L", f"{result.L_per_m * 1e9:.3f} nH/m")
    table.add_row("C", f"{result.C_per_m * 1e12:.3f} pF/m")
    if result.Gp_per_m > 0:
        table.add_row("Gp", f"{result.Gp_per_m:.4e} S/m")
    table.add_row("iterations", str(result.iterations))
    console.print(table)


@app.command()
def solve(
    type_: str = typer.Option(None, "--type", help="Geometry type (e.g. 'microstrip')."),
    json_path: Path = typer.Option(None, "--json", help="Read geometry from a JSON file."),
    bmp_path: Path = typer.Option(None, "--bmp", help="Use a BMP usermap (forces --method=cgp)."),
    method: str = typer.Option("auto", "--method", help="Solver: analytical | cgp | auto."),
    pixel_width: str = typer.Option(
        None, "--pixel-width", help="Pixel size for bitmap solves (e.g. '0.1mm')."
    ),
    output: str = typer.Option("rich", "--output", "-o", help="Output format: rich | json"),
    frequency: str = typer.Option(
        None, "--frequency", "-f", help="Frequency for loss / Gp (e.g. '1GHz')."
    ),
    # Per-field flags (analytical/parameterized path)
    W: str = typer.Option(None, "--W"),
    H: str = typer.Option(None, "--H"),
    H2: str = typer.Option(None, "--H2"),
    H_between: str = typer.Option(None, "--H-between"),  # noqa: N803
    H1: str = typer.Option(None, "--H1"),
    T: str = typer.Option(None, "--T"),
    S: str = typer.Option(None, "--S"),
    B: str = typer.Option(None, "--B"),
    er: float = typer.Option(None, "--er"),
    er2: float = typer.Option(None, "--er2"),
    tan_delta: float = typer.Option(None, "--tan-delta"),
) -> None:
    """Solve a transmission line geometry."""
    freq_hz = parse_frequency(frequency) if frequency else None

    # --bmp branch (bitmap workflow)
    if bmp_path is not None:
        if not pixel_width:
            err_console.print("--bmp requires --pixel-width")
            raise typer.Exit(code=2)
        from atlc3.solvers.cgp import solve_cgp

        usermap = Usermap.from_bmp(bmp_path, pixel_width=pixel_width)
        result = solve_cgp(usermap, frequency_hz=freq_hz)
        if output == "json":
            console.print_json(data=result.model_dump())
        else:
            _print_cgp(result)
        return

    overrides: dict[str, Any] = {}
    for key, val in {
        "W": W,
        "H": H,
        "H1": H1,
        "H2": H2,
        "H_between": H_between,
        "T": T,
        "S": S,
        "B": B,
        "er": er,
        "er2": er2,
        "tan_delta": tan_delta,
    }.items():
        if val is not None:
            overrides[key] = val

    try:
        geometry = _build_geometry(type_, json_path, overrides)
    except ValidationError as exc:
        err_console.print(f"Geometry validation failed:\n{exc}")
        raise typer.Exit(code=2) from exc

    if method == "cgp":
        from atlc3.solvers.dispatcher import solve as dispatch

        result = dispatch(
            geometry,
            method="cgp",
            frequency_hz=freq_hz,
            pixel_width=parse_length(pixel_width) if pixel_width else None,
        )
        if output == "json":
            console.print_json(data=result.model_dump())
        else:
            _print_cgp(result)
        return

    try:
        result = analytical_solve(geometry, frequency_hz=freq_hz)
    except NotImplementedError as exc:
        err_console.print(f"No analytical formula: {exc}")
        raise typer.Exit(code=2) from exc

    if output == "json":
        console.print_json(data=result.model_dump())
        return

    if isinstance(result, DiffResult):
        _print_diff(result)
    else:
        _print_tline(result)


# ---------------------------------------------------------------------------
# Bitmap utilities
# ---------------------------------------------------------------------------


@app.command(name="import-bmp")
def import_bmp(
    bmp_path: Path = typer.Argument(..., help="BMP file to import."),
    pixel_width: str = typer.Option(..., "--pixel-width", help="Pixel size (e.g. '0.1mm')."),
    output: Path = typer.Option(..., "--output", "-o", help="Output .json path."),
) -> None:
    """Convert an atlc/atlc2 BMP usermap to atlc3-native JSON format."""
    usermap = Usermap.from_bmp(bmp_path, pixel_width=pixel_width)
    usermap.to_json(output)
    console.print(f"Wrote [green]{output}[/green] ({usermap.shape[1]}×{usermap.shape[0]} px)")


@app.command()
def render(
    field: str = typer.Option(..., "--field", "-f", help="V | E | D | T"),
    bmp: Path = typer.Option(None, "--bmp", help="Solve this BMP usermap and render its field."),
    pixel_width: str = typer.Option(None, "--pixel-width"),
    output: Path = typer.Option(..., "--output", "-o", help="Output PNG path."),
) -> None:
    """Render a field plot from a usermap by solving and visualizing."""
    if bmp is None:
        err_console.print("--bmp is required (Phase 2)")
        raise typer.Exit(code=2)
    if not pixel_width:
        err_console.print("--pixel-width is required when --bmp is given")
        raise typer.Exit(code=2)

    from atlc3.solvers.cgp import solve_cgp
    from atlc3.visualization.fields import render_field

    usermap = Usermap.from_bmp(bmp, pixel_width=pixel_width)
    _, ws = solve_cgp(usermap, return_fields=True)  # type: ignore[misc]
    img = render_field(
        kind=field.upper(),  # type: ignore[arg-type]
        v_field=ws.v_field,
        er_field=ws.er_field,
        tan_delta_field=usermap.tan_delta_field() if field.upper() == "T" else None,
    )
    img.save(output)
    console.print(f"Wrote [green]{output}[/green]")


# ---------------------------------------------------------------------------
# Phase 3: lrs / sweep
# ---------------------------------------------------------------------------


@app.command()
def lrs(
    type_: str = typer.Option(None, "--type"),
    json_path: Path = typer.Option(None, "--json"),
    bmp_path: Path = typer.Option(None, "--bmp"),
    pixel_width: str = typer.Option(None, "--pixel-width"),
    frequency: str = typer.Option(..., "--frequency", "-f", help="e.g. '1GHz'"),
    output: str = typer.Option("rich", "--output", "-o"),
    skip_skin_depth: bool = typer.Option(False, "--no-skin-mask"),
    W: str = typer.Option(None, "--W"),
    H: str = typer.Option(None, "--H"),
    T: str = typer.Option(None, "--T"),
    S: str = typer.Option(None, "--S"),
    B: str = typer.Option(None, "--B"),
    H1: str = typer.Option(None, "--H1"),
    H2: str = typer.Option(None, "--H2"),
    er: float = typer.Option(None, "--er"),
) -> None:
    """Solve L and Rs via the Phase 3 Faraday/PEEC bitmap solver."""
    import atlc3 as _api

    freq_hz = parse_frequency(frequency)

    if bmp_path is not None:
        if not pixel_width:
            err_console.print("--bmp requires --pixel-width")
            raise typer.Exit(code=2)
        usermap = Usermap.from_bmp(bmp_path, pixel_width=pixel_width)
        result = _api.solve_lrs(
            usermap,
            frequency=freq_hz,
            restrict_to_skin_depth=not skip_skin_depth,
        )
    else:
        overrides = {
            k: v
            for k, v in {
                "W": W,
                "H": H,
                "T": T,
                "S": S,
                "B": B,
                "H1": H1,
                "H2": H2,
                "er": er,
            }.items()
            if v is not None
        }
        try:
            geom = _build_geometry(type_, json_path, overrides)
        except ValidationError as exc:
            err_console.print(f"{exc}")
            raise typer.Exit(code=2) from exc
        result = _api.solve_lrs(
            geom,
            frequency=freq_hz,
            pixel_width=parse_length(pixel_width) if pixel_width else None,
            restrict_to_skin_depth=not skip_skin_depth,
        )

    if output == "json":
        import dataclasses

        console.print_json(data=dataclasses.asdict(result))
        return

    table = Table(title=f"L and Rs at {freq_hz:.3e} Hz")
    table.add_column("Quantity", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("L", f"{result.L_per_m * 1e9:.3f} nH/m")
    table.add_row("R (Rs)", f"{result.R_per_m:.4e} Ω/m")
    table.add_row("conductor pixels", str(result.n_conductor_pixels))
    console.print(table)
    if result.rs_low_confidence:
        console.print(f"[red]Rs warning: {result.rs_warning}[/red]")


@app.command()
def optimize(
    type_: str = typer.Option(..., "--type"),
    target: str = typer.Option(..., "--target", help="key=value, comma-separated. e.g. 'z0=50'."),
    vary: str = typer.Option(
        ..., "--vary", help="key=lo:hi, comma-separated. e.g. 'W=0.5mil:30mil'."
    ),
    fixed: str = typer.Option("", "--fixed", help="key=value, comma-separated fixed fields."),
    solver: str = typer.Option("analytical", "--solver"),
    frequency: str = typer.Option(None, "--frequency", "-f"),
) -> None:
    """Find geometry parameters that hit electrical targets."""
    import atlc3 as _api

    template: dict[str, Any] = {"type": type_}
    for tok in fixed.split(","):
        tok = tok.strip()
        if not tok:
            continue
        k, _, v = tok.partition("=")
        template[k.strip()] = v.strip()

    target_dict: dict[str, float] = {}
    for tok in target.split(","):
        k, _, v = tok.strip().partition("=")
        target_dict[k.strip()] = float(v.strip())

    vary_dict: dict[str, tuple[float | str, float | str]] = {}
    for tok in vary.split(","):
        k, _, rng = tok.strip().partition("=")
        lo, _, hi = rng.partition(":")
        vary_dict[k.strip()] = (lo.strip(), hi.strip())

    result = _api.optimize_for(
        template=template,
        vary=vary_dict,
        target=target_dict,
        solver=solver,
        frequency=frequency,
    )

    table = Table(title="Optimization result")
    table.add_column("Field", style="cyan")
    table.add_column("Value", justify="right")
    for k in vary_dict:
        v = getattr(result.geometry, k, None)
        if v is not None:
            table.add_row(k, f"{v:.4e} m")
    for k, v in result.metric.items():
        table.add_row(f"{k} (achieved)", f"{v:.4f}")
    table.add_row("cost (RMS)", f"{result.cost:.4e}")
    table.add_row("iterations", str(result.iterations))
    table.add_row("success", "yes" if result.success else "no")
    console.print(table)


@app.command()
def sweep(
    type_: str = typer.Option(..., "--type"),
    parameter: str = typer.Option(..., "--param"),
    values: str = typer.Option(..., "--values", help="Comma-separated values."),
    output: Path = typer.Option(None, "--output", "-o", help="CSV output path."),
    solver: str = typer.Option("analytical", "--solver", help="analytical|cgp|full"),
    frequency: str = typer.Option(None, "--frequency", "-f"),
    W: str = typer.Option(None, "--W"),
    H: str = typer.Option(None, "--H"),
    T: str = typer.Option(None, "--T"),
    S: str = typer.Option(None, "--S"),
    B: str = typer.Option(None, "--B"),
    er: float = typer.Option(None, "--er"),
) -> None:
    """Run a parameter sweep and report results."""
    import atlc3 as _api

    freq_hz = parse_frequency(frequency) if frequency else None

    overrides = {
        k: v for k, v in {"W": W, "H": H, "T": T, "S": S, "B": B, "er": er}.items() if v is not None
    }
    geom = _build_geometry(type_, None, overrides)

    parsed_values: list[Any] = []
    for tok in values.split(","):
        tok = tok.strip()
        try:
            parsed_values.append(float(tok))
        except ValueError:
            try:
                parsed_values.append(parse_length(tok))
            except ValueError:
                parsed_values.append(parse_frequency(tok))

    points = _api.sweep(
        geom,
        parameter=parameter,
        values=parsed_values,
        solver=solver,
        frequency=freq_hz,
    )

    table = Table(title=f"Sweep over {parameter}")
    table.add_column(parameter)
    keys: list[str] = []
    for p in points:
        # determine result keys lazily
        d = (
            p.result.model_dump()
            if hasattr(p.result, "model_dump")
            else {
                "L_per_m": getattr(p.result, "L_per_m", None),
                "R_per_m": getattr(p.result, "R_per_m", None),
            }
        )
        if not keys:
            keys = sorted(k for k in d if isinstance(d[k], (int, float)))
            for k in keys:
                table.add_column(k)
        row = [f"{points[points.index(p)].params[parameter]:.4g}"]
        for k in keys:
            row.append(f"{d[k]:.4g}" if d[k] is not None else "-")
        table.add_row(*row)
    console.print(table)

    if output is not None:
        import csv

        with output.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([parameter, *keys])
            for p in points:
                d = p.result.model_dump() if hasattr(p.result, "model_dump") else {}
                row = [p.params[parameter], *(d.get(k) for k in keys)]
                writer.writerow(row)
        console.print(f"Wrote [green]{output}[/green]")


# ---------------------------------------------------------------------------
# Phase 4: viewer
# ---------------------------------------------------------------------------


@app.command()
def view(
    bmp: Path = typer.Option(..., "--bmp", help="BMP usermap to load."),
    pixel_width: str = typer.Option(..., "--pixel-width"),
) -> None:
    """Open the atlc2-style keyboard-driven field viewer."""
    from atlc3.viewer import run_viewer

    run_viewer(bmp, pixel_width=pixel_width)


# ---------------------------------------------------------------------------
# Script runner
# ---------------------------------------------------------------------------


@app.command(name="run-script")
def run_script(
    script_path: Path = typer.Argument(..., help="atlc2 .txt script file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse only, don't solve."),
) -> None:
    """Execute an atlc2-style script file."""
    from atlc3.scripting import run_script_file

    interp = run_script_file(script_path, dry_run=dry_run)
    if dry_run:
        console.print("[green]Script parsed successfully[/green]")
    else:
        console.print(f"[green]Script done.[/green] Outputs: {sorted(interp.outputs)}")


# ---------------------------------------------------------------------------
# Material commands
# ---------------------------------------------------------------------------


@material_app.command("list")
def material_list() -> None:
    """List materials in the atlc2 default database."""
    from atlc3.materials import ATLC2_DEFAULTS

    table = Table(title="atlc2 default materials")
    table.add_column("RGB", style="cyan")
    table.add_column("Use")
    table.add_column("εr", justify="right")
    table.add_column("tanδ", justify="right")
    table.add_column("Name")
    for m in ATLC2_DEFAULTS:
        rgb_str = f"({m.rgb[0]:>3},{m.rgb[1]:>3},{m.rgb[2]:>3})"
        table.add_row(rgb_str, m.use, f"{m.er:.3g}", f"{m.tan_delta:.3g}", m.name)
    console.print(table)


@material_app.command("show")
def material_show(
    name: str = typer.Argument(..., help="Substring match (case-insensitive).")
) -> None:
    """Show materials matching a name."""
    from atlc3.materials import find_by_name

    matches = find_by_name(name)
    if not matches:
        err_console.print(f"No materials matching {name!r}.")
        raise typer.Exit(code=1)
    for m in matches:
        console.print_json(data=m.model_dump())


@material_app.command("load")
def material_load(
    pack: Path = typer.Argument(..., help="JSON pack or MoreColors.txt path."),
) -> None:
    """Load a material pack and print summary (JSON or atlc2 MoreColors.txt format)."""
    from atlc3.materials import load_json_pack, parse_morecolors_file

    if pack.suffix.lower() == ".json":
        records = load_json_pack(pack)
    else:
        records = parse_morecolors_file(pack)
    console.print(f"Loaded [green]{len(records)}[/green] materials from {pack}")
    for m in records[:10]:
        console.print(f"  {m.rgb} {m.use:<6}  {m.name}")
    if len(records) > 10:
        console.print(f"  ... ({len(records) - 10} more)")


if __name__ == "__main__":  # pragma: no cover
    app()
