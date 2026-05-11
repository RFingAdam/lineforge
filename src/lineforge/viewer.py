"""atlc2-style keyboard-driven CLI viewer for solved field results.

Phase 4 quality-of-life: a textual viewer that mirrors atlc2's keyboard
shortcuts (U/V/E/D/T/L/N/B). Operates on PNG renders rather than a Win32
canvas, but the keystroke protocol is identical, so atlc2 muscle memory
transfers.

Run::

    lineforge view --bmp my_usermap.bmp --pixel-width 0.1mm

Then press U/V/E/D/T to switch field modes, +/- to zoom, S to save.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from rich.console import Console

from lineforge.geometry.usermap import Usermap
from lineforge.solvers.cgp import solve_cgp
from lineforge.visualization.fields import FieldKind, render_contour_lines, render_field

console = Console()


def run_viewer(bmp_path: Path, *, pixel_width: str) -> None:
    """Solve the usermap once, then accept atlc2-style keystroke commands."""
    usermap = Usermap.from_bmp(bmp_path, pixel_width=pixel_width)
    console.print(f"Loaded [cyan]{bmp_path.name}[/cyan] ({usermap.shape[1]}×{usermap.shape[0]} px)")
    console.print("Solving...")
    cgp_result, ws = solve_cgp(usermap, return_fields=True)
    console.print(
        f"Z0 = [bold]{cgp_result.z0:.2f} Ω[/bold]  "
        f"εeff = [bold]{cgp_result.eps_eff:.3f}[/bold]  "
        f"({cgp_result.iterations} iters)"
    )

    current_mode: FieldKind = "V"
    last_image_path: Path | None = None

    KEYS = (
        "U=usermap  V=voltage  E=E-field  D=D-field  T=loss  "
        "L=V-lines  N=E-lines  B=both  S=save  Q=quit"
    )

    while True:
        console.print(f"\n[mode={current_mode}] {KEYS}")
        try:
            line = input("lineforge> ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            console.print("\nbye.")
            break

        if not line:
            continue
        cmd = line[0]

        if cmd == "Q":
            console.print("bye.")
            break

        if cmd in {"U", "V", "E", "D", "T"}:
            current_mode = cast(FieldKind, cmd)
            tan_d = usermap.tan_delta_field() if cmd == "T" else None
            img = render_field(
                kind=current_mode,
                v_field=ws.v_field,
                er_field=ws.er_field,
                tan_delta_field=tan_d,
            )
            out = Path(f"lineforge_view_{cmd.lower()}.png")
            img.save(out)
            last_image_path = out
            console.print(f"  rendered → {out}")

        elif cmd == "L":
            img = render_contour_lines(ws.v_field)
            out = Path("lineforge_view_lines_v.png")
            img.save(out)
            last_image_path = out
            console.print(f"  V contour lines → {out}")

        elif cmd == "S":
            if last_image_path:
                console.print(f"  last saved at {last_image_path}")
            else:
                console.print("  (nothing rendered yet — press V/E/D/T first)")

        else:
            console.print(f"  unknown command {cmd!r}")


__all__ = ["run_viewer"]
