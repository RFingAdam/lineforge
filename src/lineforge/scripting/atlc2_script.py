"""Interpreter for atlc2's documented script language.

Reference: http://www.hdtvprimer.com/kq6qv/atlc2.html §"Scripting Facility".

Supported commands (atlc2 inspects only the first 3 letters of the command,
so ``CGP``/``cgp``/``CGProcess`` all match, etc.):

    twinlead, square, coaxial         — internal-geometry generators
    pixel, total, frequency           — set numeric edit boxes
    separation, diameter, insulation  — internal-geometry params
    top, bottom, side, skew           — internal-geometry params
    width, height                     — square-twinlead width/height
    center, inner, outer              — coaxial dims
    box <n> <T|F>                     — set GUI checkbox
    name <s>                          — set the Name field (used as ZZZ)
    folder <s>                        — set the execution folder
    open <s>                          — load a Usermap from <s>.bmp
    solve, LRS, CGP                   — run solvers; append to <name>* output files
    sweep <param> <runs> [per_decade] — parametric L/Rs sweep
    threads <n|+|->                   — set thread count
    terminate                         — end the script
    erase                             — erase the script file (atlc2 quirk; we no-op)
    keyboard <s>                      — feed keystrokes (Phase 4 GUI only; we no-op)
    save                              — save displayed bitmap (Phase 2 saves last solve PNG)
    beep                              — terminal bell
    window <n>, launch <n> <s>        — Phase 4 / GUI commands; we log+no-op

Phase 2 supports the geometry-generator + solve/CGP/sweep subset; Phase 3 fills
in LRS/full-RLGC; Phase 4 fills in the GUI-related no-ops.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lineforge.units import parse_length

log = logging.getLogger(__name__)


class ScriptError(RuntimeError):
    """Raised when a script line fails fatally."""


@dataclass
class _ScriptState:
    """Mutable script-execution state mirroring atlc2's GUI fields."""

    # GUI edit-box equivalents
    pixel_width: float | None = None
    total_pixels: int = 4000
    frequency_hz: float = 1e6
    name: str = "lineforge"
    folder: Path = field(default_factory=Path.cwd)
    threads: int = 0  # 0 = auto

    # Internal-geometry parameters
    diameter: float | None = None
    separation: float | None = None
    insulation: float | None = None
    top: float | None = None
    bottom: float | None = None
    side: float | None = None
    skew: float | None = None
    width: float | None = None
    height: float | None = None
    center: float | None = None
    inner: float | None = None
    outer: float | None = None

    # Checkboxes
    boxes: dict[int, bool] = field(default_factory=dict)

    # Currently selected geometry kind
    geometry_kind: str | None = None  # "twinlead" | "square" | "coaxial" | "open"

    # If kind == "open", the loaded usermap path
    usermap_path: Path | None = None


def _resolve_path(state: _ScriptState, raw: str) -> Path:
    """Replace leading '%' with execution folder, à la atlc2."""
    if raw.startswith("%"):
        return state.folder / raw[1:].lstrip("\\/")
    return Path(raw)


def _strip_comments(line: str) -> str:
    bar = line.find("|")
    return line if bar == -1 else line[:bar]


def _parse_bool(token: str) -> bool:
    return token.upper() in {"T", "TRUE", "1", "Y", "YES"}


class ScriptInterpreter:
    """Executes an atlc2 script file."""

    def __init__(self, *, dry_run: bool = False) -> None:
        self.state = _ScriptState()
        self.dry_run = dry_run
        self.outputs: dict[str, list[str]] = {}  # appended lines per output file
        self.terminated = False

    # ---------------------------------------------------------------- public

    def run(self, source: str) -> None:
        for lineno, raw in enumerate(source.splitlines(), start=1):
            if self.terminated:
                break
            cleaned = _strip_comments(raw).strip()
            if not cleaned:
                continue
            try:
                self._dispatch(cleaned)
            except ScriptError:
                raise
            except Exception as exc:
                raise ScriptError(f"line {lineno}: {exc}") from exc

    def run_file(self, path: str | Path) -> None:
        self.run(Path(path).read_text())

    # ----------------------------------------------------------- dispatch

    def _dispatch(self, line: str) -> None:
        tokens = line.split()
        cmd = tokens[0].lower()[:3]  # atlc2 examines first 3 chars only
        args = tokens[1:]

        Handler = Callable[[list[str]], None]  # noqa: N806
        handler: Handler | None = {
            "twi": self._cmd_twinlead,
            "squ": self._cmd_square,
            "coa": self._cmd_coaxial,
            "pix": lambda a: self._cmd_set_length("pixel_width", a),
            "tot": lambda a: self._cmd_set_int("total_pixels", a),
            "fre": self._cmd_frequency,
            "sep": lambda a: self._cmd_set_length("separation", a),
            "dia": lambda a: self._cmd_set_length("diameter", a),
            "ins": lambda a: self._cmd_set_length("insulation", a),
            "top": lambda a: self._cmd_set_length("top", a),
            "bot": lambda a: self._cmd_set_length("bottom", a),
            "sid": lambda a: self._cmd_set_length("side", a),
            "ske": lambda a: self._cmd_set_length("skew", a),
            "wid": lambda a: self._cmd_set_length("width", a),
            "hei": lambda a: self._cmd_set_length("height", a),
            "cen": lambda a: self._cmd_set_length("center", a),
            "inn": lambda a: self._cmd_set_length("inner", a),
            "out": lambda a: self._cmd_set_length("outer", a),
            "box": self._cmd_box,
            "nam": self._cmd_name,
            "fol": self._cmd_folder,
            "ope": self._cmd_open,
            "sol": lambda a: self._cmd_solve("full"),
            "lrs": lambda a: self._cmd_solve("lrs"),
            "cgp": lambda a: self._cmd_solve("cgp"),
            "swe": self._cmd_sweep,
            "thr": self._cmd_threads,
            "ter": lambda a: setattr(self, "terminated", True),
            "era": lambda a: None,  # atlc2 erased its own file; we don't
            "key": lambda a: log.info("ignored 'keyboard' command (Phase 4)"),
            "sav": self._cmd_save,
            "bee": lambda a: print("\a", end=""),
            "win": lambda a: log.info("ignored 'window' command (no GUI)"),
            "lau": lambda a: log.info("ignored 'launch' command"),
        }.get(cmd)

        if handler is None:
            raise ScriptError(f"unknown command {tokens[0]!r}")
        handler(args)

    # ------------------------------------------------------------ commands

    def _cmd_twinlead(self, args: list[str]) -> None:
        self.state.geometry_kind = "twinlead"

    def _cmd_square(self, args: list[str]) -> None:
        self.state.geometry_kind = "square"

    def _cmd_coaxial(self, args: list[str]) -> None:
        self.state.geometry_kind = "coaxial"

    def _cmd_set_length(self, attr: str, args: list[str]) -> None:
        if not args:
            raise ScriptError(f"{attr} expects an argument")
        setattr(self.state, attr, parse_length(args[0]))

    def _cmd_set_int(self, attr: str, args: list[str]) -> None:
        if not args:
            raise ScriptError(f"{attr} expects an argument")
        setattr(self.state, attr, int(float(args[0])))

    def _cmd_frequency(self, args: list[str]) -> None:
        if not args:
            raise ScriptError("frequency expects an argument")
        # atlc2 frequency box accepts MHz by default per docs; we accept Hz or unit string
        from lineforge.units import parse_frequency

        try:
            self.state.frequency_hz = parse_frequency(args[0])
        except ValueError:
            # Fallback: treat as MHz
            self.state.frequency_hz = float(args[0]) * 1e6

    def _cmd_box(self, args: list[str]) -> None:
        if len(args) < 2:
            raise ScriptError("box <n> <T|F>")
        self.state.boxes[int(args[0])] = _parse_bool(args[1])

    def _cmd_name(self, args: list[str]) -> None:
        if not args:
            raise ScriptError("name expects a string")
        self.state.name = " ".join(args)

    def _cmd_folder(self, args: list[str]) -> None:
        if not args:
            raise ScriptError("folder expects a path")
        self.state.folder = Path(" ".join(args))

    def _cmd_open(self, args: list[str]) -> None:
        if not args:
            raise ScriptError("open expects a filename")
        path = _resolve_path(self.state, " ".join(args))
        if not path.suffix:
            path = path.with_suffix(".bmp")
        self.state.usermap_path = path
        self.state.geometry_kind = "open"

    def _cmd_threads(self, args: list[str]) -> None:
        if not args:
            raise ScriptError("threads expects an argument")
        a = args[0]
        if a == "+":
            self.state.threads = max(1, self.state.threads + 1)
        elif a == "-":
            self.state.threads = max(1, self.state.threads - 1)
        else:
            self.state.threads = int(float(a))

    def _cmd_save(self, args: list[str]) -> None:
        if self.dry_run:
            log.info("[dry-run] would save displayed image")
            return
        log.info("save: not implemented in Phase 2")

    def _cmd_solve(self, mode: str) -> None:
        if self.dry_run:
            log.info(f"[dry-run] would solve mode={mode}")
            return

        from lineforge.solvers.cgp import solve_cgp

        usermap = self._build_current_usermap()
        result = solve_cgp(usermap, frequency_hz=self.state.frequency_hz)

        # Append to per-output files (atlc2 convention)
        self._append_output("Inductances.txt", f"{result.L_per_m:.6e}\n")
        self._append_output("Capacitances.txt", f"{result.C_per_m:.6e}\n")
        self._append_output("Conductances.txt", f"{result.Gp_per_m:.6e}\n")
        self._append_output("VFactors.txt", f"{result.vp / 299_792_458:.6f}\n")

    def _cmd_sweep(self, args: list[str]) -> None:
        if not args:
            raise ScriptError("sweep expects: <param> <runs> [runs_per_decade]")
        param = args[0].lower()
        runs = int(args[1]) if len(args) > 1 else 5
        per_decade = int(args[2]) if len(args) > 2 else 4

        # Sweep multiplier: 10**(1/per_decade) per step
        factor = 10 ** (1.0 / per_decade)
        attr_map = {
            "frequency": "frequency_hz",
            "freq": "frequency_hz",
            "pixel": "pixel_width",
            "total": "total_pixels",
        }
        attr = attr_map.get(param, param)

        if self.dry_run:
            log.info(f"[dry-run] would sweep {attr} for {runs} runs at factor {factor}")
            return

        for _ in range(runs):
            current = getattr(self.state, attr)
            self._cmd_solve("full")
            setattr(self.state, attr, current * factor)

    # ------------------------------------------------------------ helpers

    def _build_current_usermap(self) -> Any:
        """Construct the active Usermap from the script state."""
        from lineforge.geometry.usermap import Usermap

        kind = self.state.geometry_kind or "open"
        if kind == "open":
            if self.state.usermap_path is None:
                raise ScriptError("`open <file>` was not specified before solve")
            if self.state.pixel_width is None:
                raise ScriptError("`pixel <px>` is required when using a usermap file")
            return Usermap.from_bmp(self.state.usermap_path, pixel_width=self.state.pixel_width)

        # Internal-geometry generators map to lineforge builders + parameters
        if kind == "twinlead":
            from lineforge.geometry.builders import rasterize_microstrip
            from lineforge.geometry.types import Microstrip

            sep = self.state.separation or 1e-3
            dia = self.state.diameter or 5e-4
            geom = Microstrip(W=dia, H=sep, T=dia / 4, er=1.0)
            return rasterize_microstrip(geom)

        if kind == "square":
            from lineforge.geometry.builders import rasterize_microstrip
            from lineforge.geometry.types import Microstrip

            w = self.state.width or 1e-3
            h = self.state.height or 1e-3
            geom = Microstrip(W=w, H=self.state.separation or 1e-3, T=h, er=1.0)
            return rasterize_microstrip(geom)

        if kind == "coaxial":
            # We don't have a Coax geometry yet — Phase 4 adds it. For now, fail clearly.
            raise ScriptError(
                "coaxial scripts not yet implemented in lineforge Phase 2 — "
                "use `open <bmp>` with a coax usermap instead"
            )

        raise ScriptError(f"unknown geometry kind {kind!r}")

    def _append_output(self, basename: str, text: str) -> None:
        path = self.state.folder / f"{self.state.name} {basename}"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(text)
        self.outputs.setdefault(basename, []).append(text)


def run_script_file(path: str | Path, *, dry_run: bool = False) -> ScriptInterpreter:
    """Convenience wrapper: run a script file and return the interpreter for inspection."""
    interp = ScriptInterpreter(dry_run=dry_run)
    interp.run_file(path)
    return interp


__all__ = ["ScriptError", "ScriptInterpreter", "run_script_file"]
