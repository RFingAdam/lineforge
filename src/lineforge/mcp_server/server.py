"""MCP server entry point.

Phase 2 surface (extending Phase 1's analytical tools):

Tools
-----
Phase 1 (synchronous, fast):
- ``ping``                  — health check
- ``calculate_impedance``   — closed-form solver
- ``list_geometry_types``   — enumerate geometries
- ``describe_geometry``     — JSON Schema for a type
- ``export_geometry_schema``— union schema

Phase 2 (long-running via Tasks pattern):
- ``import_usermap(bmp_base64, pixel_width, name?) -> { uri }``
- ``solve_cgp(geometry_or_uri, options?) -> { taskId }`` — async
- ``tasks_get(taskId) -> { status, result?, error? }``    — poll
- ``tasks_cancel(taskId) -> { cancelled: bool }``
- ``rasterize(geometry, pixel_width?) -> { uri, shape }``
- ``run_atlc2_script(script_text, dry_run?) -> { outputs }``

Resources
---------
- ``atlc://materials``                          — atlc2 default DB
- ``atlc://materials/{name}``                   — by-name lookup
- ``atlc://geometries/{id}``                    — saved Usermaps
- ``atlc://results/{id}``                       — completed task results
- ``atlc://results/{id}/field/{V|E|D|T}``       — field-plot PNGs (base64-encoded in resource read)
"""

from __future__ import annotations

import base64
import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from lineforge.analytical import solve as analytical_solve
from lineforge.geometry import GEOMETRY_TYPES, export_jsonschema, from_dict
from lineforge.geometry.builders import rasterize as rasterize_geom
from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.materials import ATLC2_DEFAULTS, list_atlc2_default
from lineforge.mcp_server.tasks import TaskRegistry, png_to_bytes
from lineforge.results import DiffResult
from lineforge.solvers.cgp import solve_cgp as run_cgp
from lineforge.units import parse_frequency, parse_length
from lineforge.version import __version__

# ---------------------------------------------------------------------------
# In-process resource stores
# ---------------------------------------------------------------------------


class _UsermapStore:
    """Maps geometry UUIDs to in-memory Usermaps."""

    def __init__(self) -> None:
        self._items: dict[str, Usermap] = {}

    def add(self, usermap: Usermap) -> str:
        import uuid as _uuid

        uid = str(_uuid.uuid4())
        self._items[uid] = usermap
        return uid

    def get(self, uid: str) -> Usermap | None:
        return self._items.get(uid)


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def build_server() -> MCPServer:
    """Construct the MCPServer with all currently-implemented tools/resources."""
    server = MCPServer(
        name="lineforge",
        instructions=(
            "lineforge — open-source transmission line calculator. "
            "Use `calculate_impedance` for fast closed-form solves on standard "
            "PCB geometries. For arbitrary cross-sections, use `import_usermap` "
            "to upload a BMP, then `solve_cgp` (returns a taskId — poll via "
            "`tasks_get` until status='completed'). Field plots are exposed as "
            "resources at `atlc://results/{id}/field/{V|E|D|T}`."
        ),
    )

    usermap_store = _UsermapStore()
    task_registry = TaskRegistry()

    # ============================================================== Phase 1
    # ping, calculate_impedance, list_geometry_types, describe_geometry,
    # export_geometry_schema, atlc://materials, atlc://materials/{name}
    # =====================================================================

    @server.tool()
    def ping() -> dict[str, Any]:
        """Health check. Returns ``{"status": "ok", "version": ..., "phase": 2}``."""
        return {"status": "ok", "version": __version__, "phase": 2}

    @server.tool()
    def list_geometry_types() -> dict[str, Any]:
        """List every supported transmission-line geometry."""
        return {
            "geometries": [
                {
                    "type": type_name,
                    "class": cls.__name__,
                    "doc": (cls.__doc__ or "").splitlines()[0].strip() if cls.__doc__ else "",
                    "required_fields": [
                        name
                        for name, field in cls.model_fields.items()
                        if field.is_required() and name != "type"
                    ],
                }
                for type_name, cls in GEOMETRY_TYPES.items()
            ],
        }

    @server.tool()
    def describe_geometry(name: str) -> dict[str, Any]:
        """JSON Schema for a single geometry type."""
        if name not in GEOMETRY_TYPES:
            return {
                "error": f"unknown geometry type {name!r}",
                "valid_types": sorted(GEOMETRY_TYPES.keys()),
            }
        return GEOMETRY_TYPES[name].model_json_schema()

    @server.tool()
    def export_geometry_schema() -> dict[str, Any]:
        """Discriminated-union JSON Schema across all geometries."""
        return export_jsonschema()

    @server.tool()
    def calculate_impedance(
        geometry: dict[str, Any],
        frequency: float | str | None = None,
    ) -> dict[str, Any]:
        """Closed-form analytical solve. Synchronous (microseconds)."""
        try:
            geom = from_dict(geometry)
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}

        freq_hz = parse_frequency(frequency) if isinstance(frequency, str) else frequency
        try:
            result = analytical_solve(geom, frequency_hz=freq_hz)
        except NotImplementedError as exc:
            return {"error": f"no analytical formula: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"solve failed: {exc}"}

        out = result.model_dump()
        out["_kind"] = "DiffResult" if isinstance(result, DiffResult) else "TLineResult"
        return out

    # ============================================================== Phase 2
    # import_usermap, rasterize, solve_cgp (async + Tasks), tasks_get,
    # tasks_cancel, run_atlc2_script
    # =====================================================================

    @server.tool()
    def import_usermap(
        bmp_base64: str,
        pixel_width: str | float,
        name: str = "imported",
    ) -> dict[str, Any]:
        """Decode a base64-encoded BMP usermap and store it as a resource.

        Parameters
        ----------
        bmp_base64
            Base64-encoded BMP file contents.
        pixel_width
            Physical pixel size, e.g. ``"0.1mm"`` or a float in meters.
        name
            Optional human-readable label.

        Returns
        -------
        dict
            ``{"uri": "atlc://geometries/<id>", "shape": [H, W]}``
        """
        from io import BytesIO

        import numpy as np
        from PIL import Image

        try:
            blob = base64.b64decode(bmp_base64)
            img = Image.open(BytesIO(blob))
            if img.mode != "RGB":
                img = img.convert("RGB")
            rgb = np.asarray(img, dtype=np.uint8)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not decode BMP: {exc}"}

        meta = UsermapMetadata(
            pixel_width_m=(
                parse_length(pixel_width) if isinstance(pixel_width, str) else float(pixel_width)
            ),
            name=name,
            source="mcp:import_usermap",
        )
        usermap = Usermap(rgb, meta)
        uid = usermap_store.add(usermap)
        return {
            "uri": f"atlc://geometries/{uid}",
            "shape": list(usermap.shape),
            "pixel_width_m": usermap.pixel_width_m,
        }

    @server.tool()
    def rasterize(
        geometry: dict[str, Any],
        pixel_width: str | float | None = None,
    ) -> dict[str, Any]:
        """Rasterize a parameterized geometry to a Usermap and store it."""
        try:
            geom = from_dict(geometry)
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}

        px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width
        usermap = rasterize_geom(geom, pixel_width=px)
        uid = usermap_store.add(usermap)
        return {
            "uri": f"atlc://geometries/{uid}",
            "shape": list(usermap.shape),
            "pixel_width_m": usermap.pixel_width_m,
        }

    @server.tool()
    def solve_cgp(
        geometry: dict[str, Any] | None = None,
        usermap_uri: str | None = None,
        frequency: float | str | None = None,
        pixel_width: str | float | None = None,
        use_charge_shift: bool = True,
        method: str = "auto",
        extend_grid: bool = True,
        render_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Solve C and Gp asynchronously via the bitmap Laplace solver.

        Returns a ``taskId`` immediately. Poll ``tasks_get(taskId)`` until status
        becomes ``completed`` or ``failed``.

        Parameters
        ----------
        geometry
            Either a parameterized geometry dict (rasterized first) or omit and
            pass ``usermap_uri`` to use a previously stored usermap.
        usermap_uri
            ``atlc://geometries/<id>`` URI (from ``import_usermap`` or ``rasterize``).
        frequency
            Optional Hz or unit string for Gp.
        pixel_width
            Pixel size (used only if ``geometry`` is parameterized).
        use_charge_shift
            atlc2 "Skip E prediction" toggled off when True.
        method
            ``"sor"`` | ``"amg"`` | ``"auto"``.
        extend_grid
            Pad the usermap for open-boundary simulation (atlc2 default).
            Set False for shielded geometries (coax) or for fast tests —
            unshielded lines need True for accurate Z₀.
        render_fields
            Subset of ``["V", "E", "D", "T"]`` to render as PNGs and attach to
            the result.
        """
        # Resolve the usermap
        if usermap_uri is not None:
            uid = usermap_uri.split("/")[-1]
            usermap = usermap_store.get(uid)
            if usermap is None:
                return {"error": f"unknown usermap URI {usermap_uri!r}"}
        elif geometry is not None:
            try:
                geom = from_dict(geometry)
            except (KeyError, ValueError) as exc:
                return {"error": str(exc)}
            px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width
            usermap = rasterize_geom(geom, pixel_width=px)
        else:
            return {"error": "either `geometry` or `usermap_uri` is required"}

        freq_hz = parse_frequency(frequency) if isinstance(frequency, str) else frequency

        def _run(task_obj: Any) -> dict[str, Any]:
            cgp_result, ws = run_cgp(
                usermap,
                frequency_hz=freq_hz,
                use_charge_shift=use_charge_shift,
                method=method,
                extend_grid=extend_grid,
                return_fields=True,
            )

            # Render requested field plots as base64 PNGs into the task object
            if render_fields:
                from lineforge.visualization.fields import render_field

                for kind in render_fields:
                    img = render_field(
                        kind=kind.upper(),  # type: ignore[arg-type]
                        v_field=ws.v_field,
                        er_field=ws.er_field,
                        tan_delta_field=usermap.tan_delta_field() if kind.upper() == "T" else None,
                    )
                    task_obj.field_plots[kind.upper()] = png_to_bytes(img)

            out = cgp_result.model_dump()
            out["_kind"] = "CGPResult"
            out["fieldPlots"] = sorted(task_obj.field_plots.keys())
            return out

        task = task_registry.submit("solve_cgp", _run)
        return {"taskId": task.id, "status": task.status}

    @server.tool()
    def tasks_get(task_id: str) -> dict[str, Any]:
        """Poll a long-running task for its status and (when complete) its result."""
        t = task_registry.get(task_id)
        if t is None:
            return {"error": f"unknown task {task_id!r} (may have expired)"}
        out = t.to_status()
        if t.status == "completed":
            out["result"] = t.result
        return out

    @server.tool()
    def tasks_cancel(task_id: str) -> dict[str, Any]:
        """Request cancellation of a running task."""
        ok = task_registry.cancel(task_id)
        return {"cancelled": ok}

    @server.tool()
    def solve_lrs(
        geometry: dict[str, Any] | None = None,
        usermap_uri: str | None = None,
        frequency: float | str = 1e9,
        pixel_width: str | float | None = None,
        method: str = "auto",
        restrict_to_skin_depth: bool = True,
    ) -> dict[str, Any]:
        """Solve L and Rs asynchronously via the Phase 3 Faraday/PEEC bitmap solver.

        Returns a ``taskId``. Poll ``tasks_get(taskId)`` until complete.
        """
        if usermap_uri is not None:
            uid = usermap_uri.split("/")[-1]
            usermap = usermap_store.get(uid)
            if usermap is None:
                return {"error": f"unknown usermap URI {usermap_uri!r}"}
        elif geometry is not None:
            try:
                geom = from_dict(geometry)
            except (KeyError, ValueError) as exc:
                return {"error": str(exc)}
            px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width
            usermap = rasterize_geom(geom, pixel_width=px)
        else:
            return {"error": "either `geometry` or `usermap_uri` is required"}

        freq_hz = parse_frequency(frequency) if isinstance(frequency, str) else frequency

        def _run(task_obj: Any) -> dict[str, Any]:
            from lineforge.solvers.lrs import solve_lrs as _solve

            result = _solve(
                usermap,
                frequency_hz=float(freq_hz),
                method=method,
                restrict_to_skin_depth=restrict_to_skin_depth,
            )
            import dataclasses

            out = dataclasses.asdict(result)
            out["_kind"] = "FaradayResult"
            out["z0_complex"] = {
                "real": result.z0_complex.real,
                "imag": result.z0_complex.imag,
            }
            return out

        task = task_registry.submit("solve_lrs", _run)
        return {"taskId": task.id, "status": task.status}

    @server.tool()
    def solve_full(
        geometry: dict[str, Any] | None = None,
        usermap_uri: str | None = None,
        frequency: float | str = 1e9,
        pixel_width: str | float | None = None,
        restrict_to_skin_depth: bool = True,
    ) -> dict[str, Any]:
        """Solve full RLGC (combined C/Gp + L/Rs) asynchronously."""
        if usermap_uri is not None:
            uid = usermap_uri.split("/")[-1]
            usermap = usermap_store.get(uid)
            if usermap is None:
                return {"error": f"unknown usermap URI {usermap_uri!r}"}
        elif geometry is not None:
            try:
                geom = from_dict(geometry)
            except (KeyError, ValueError) as exc:
                return {"error": str(exc)}
            px = parse_length(pixel_width) if isinstance(pixel_width, str) else pixel_width
            usermap = rasterize_geom(geom, pixel_width=px)
        else:
            return {"error": "either `geometry` or `usermap_uri` is required"}

        freq_hz = parse_frequency(frequency) if isinstance(frequency, str) else frequency

        def _run(task_obj: Any) -> dict[str, Any]:
            from lineforge.solvers.lrs import solve_full as _solve

            result = _solve(
                usermap,
                frequency_hz=float(freq_hz),
                restrict_to_skin_depth=restrict_to_skin_depth,
            )
            out = result.model_dump()
            out["_kind"] = "RLGCResult"
            return out

        task = task_registry.submit("solve_full", _run)
        return {"taskId": task.id, "status": task.status}

    @server.tool()
    def sweep(
        geometry: dict[str, Any],
        parameter: str,
        values: list[float],
        solver: str = "analytical",
        frequency: float | str | None = None,
        touchstone_out: str | None = None,
        line_length: str | float = "1in",
        z_ref: float = 50.0,
    ) -> dict[str, Any]:
        """Sweep a single parameter and return results.

        For ``solver="analytical"`` this is synchronous (microseconds per point).
        For ``"cgp"`` or ``"full"`` it submits a background task and returns
        a ``taskId``; poll ``tasks_get`` for progress.

        Optional Touchstone export: pass ``touchstone_out=<path>`` (with
        ``parameter="frequency"``) to also write a 2-port ``.s2p`` file
        modeling a ``line_length``-long section at reference impedance
        ``z_ref`` Ω.
        """
        try:
            geom = from_dict(geometry)
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}

        freq_hz = parse_frequency(frequency) if isinstance(frequency, str) else frequency

        if solver == "analytical":
            from lineforge.sweep import sweep as _sweep_fn

            try:
                points = _sweep_fn(
                    geom,
                    parameter=parameter,
                    values=values,
                    solver="analytical",
                    frequency_hz=freq_hz,
                )
            except Exception as exc:  # noqa: BLE001
                return {"error": f"sweep failed: {exc}"}

            response: dict[str, Any] = {
                "points": [{"params": p.params, "result": p.result.model_dump()} for p in points],
            }
            if touchstone_out is not None:
                from lineforge.touchstone import to_touchstone

                try:
                    out_path = to_touchstone(
                        points, touchstone_out, line_length=line_length, z_ref=z_ref
                    )
                    response["touchstone"] = {
                        "path": str(out_path),
                        "n_ports": 2,
                        "z_ref": z_ref,
                        "line_length": line_length,
                    }
                except (ValueError, OSError) as exc:
                    response["touchstone_error"] = str(exc)
            return response

        # Numerical solver: async
        def _run(task_obj: Any) -> dict[str, Any]:
            from lineforge.sweep import sweep as _sweep_fn

            points = _sweep_fn(
                geom,
                parameter=parameter,
                values=values,
                solver=solver,
                frequency_hz=freq_hz,
            )
            return {
                "points": [
                    {
                        "params": p.params,
                        "result": (
                            p.result.model_dump()
                            if hasattr(p.result, "model_dump")
                            else {"L_per_m": p.result.L_per_m, "R_per_m": p.result.R_per_m}
                        ),
                    }
                    for p in points
                ],
            }

        task = task_registry.submit("sweep", _run)
        return {"taskId": task.id, "status": task.status}

    @server.tool()
    def solve_modes(usermap_uri: str) -> dict[str, Any]:
        """3-wire Y-decomposition (ZoR/ZoG/ZoB + odd/even modes).

        Three Laplace solves, one with each conductor (red, green, blue) in
        turn floating. Combines results via Y-decomposition.

        Parameters
        ----------
        usermap_uri
            ``atlc://geometries/<id>`` URI from a prior ``rasterize`` or
            ``import_usermap`` call. The usermap must contain red (+1),
            blue (−1), and green (0) conductor pixels.

        Returns
        -------
        dict
            Serialized :class:`lineforge.results.ThreeWireResult` plus
            ``"_kind": "ThreeWireResult"``.
        """
        if not usermap_uri.startswith("atlc://geometries/"):
            return {"error": f"expected atlc://geometries/<id>, got {usermap_uri!r}"}
        uid = usermap_uri.removeprefix("atlc://geometries/")
        usermap = usermap_store.get(uid)
        if usermap is None:
            return {"error": f"unknown usermap {uid!r}"}
        from lineforge.solvers import solve_modes as _solve_modes

        try:
            result = _solve_modes(usermap)
        except (ValueError, RuntimeError) as exc:
            return {"error": f"solve_modes failed: {exc}"}
        out = result.model_dump()
        out["_kind"] = "ThreeWireResult"
        return out

    @server.tool()
    def target_z0(
        template: dict[str, Any],
        target_ohms: float,
        vary: str = "W",
        bounds: list[str] | None = None,
        solver: str = "analytical",
        frequency: float | str | None = None,
    ) -> dict[str, Any]:
        """Find a single dimension that lands a target characteristic impedance.

        Ergonomic wrapper around the optimizer for "what trace width gives me
        50 Ω on this stackup?"-style queries.

        Parameters
        ----------
        template
            Geometry dict with ``type`` plus all the fixed fields.
        target_ohms
            Target Z₀ in ohms.
        vary
            Field name to optimize (default ``"W"``).
        bounds
            Two-element ``[low, high]`` bounds for the varied field. Accepts
            unit strings. Defaults to ``["0.1mil", "100mil"]`` if omitted.
        solver
            ``"analytical"`` (default), ``"cgp"``, or ``"full"``.
        frequency
            Required for ``solver="full"``.

        Returns
        -------
        dict with keys ``geometry`` (geometry dict), ``z0_achieved``,
        ``cost``, ``iterations``, ``success``.
        """
        from lineforge.optimize import target_z0 as _target_z0

        freq_hz = parse_frequency(frequency) if isinstance(frequency, str) else frequency
        bounds_tuple: tuple[float | str, float | str] | None
        if bounds is None:
            bounds_tuple = None
        else:
            if len(bounds) != 2:
                return {"error": "bounds must be a 2-element list [low, high]"}
            bounds_tuple = (bounds[0], bounds[1])

        try:
            result = _target_z0(
                template=template,
                vary=vary,
                target_ohms=target_ohms,
                solver=solver,
                frequency_hz=freq_hz,
                bounds=bounds_tuple,
            )
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}
        return {
            "geometry": (
                result.geometry.model_dump()
                if hasattr(result.geometry, "model_dump")
                else dict(result.geometry)
            ),
            "z0_achieved": result.metric.get("z0"),
            "cost": result.cost,
            "iterations": result.iterations,
            "success": result.success,
        }

    @server.tool()
    def run_atlc2_script(script_text: str, dry_run: bool = False) -> dict[str, Any]:
        """Execute an atlc2-style ``.txt`` script."""
        from lineforge.scripting import ScriptInterpreter

        interp = ScriptInterpreter(dry_run=dry_run)
        try:
            interp.run(script_text)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}
        return {
            "ok": True,
            "outputs": {k: "".join(v) for k, v in interp.outputs.items()},
            "name": interp.state.name,
            "geometry_kind": interp.state.geometry_kind,
        }

    # ======================================================== v2.1.0 RF pad / RL tools

    @server.tool()
    def pad_capacitance(
        W: str,
        L: str | None = None,
        h: str | None = None,
        er: float | None = None,
        method: str = "ya",
        T: str | None = None,
    ) -> dict[str, Any]:
        """Compute the capacitance of an electrically small RF pad.

        Parameters
        ----------
        W, L
            Pad width and length as unit-suffixed strings (e.g. "0.4mm", "15mil").
            L defaults to W (square pad).
        h, er
            Dielectric height to reference plane + relative permittivity.
        method
            "pp" (parallel-plate), "ya" (Yamashita-Atsuki finite-pad, default),
            or "hj" (Hammerstad-Jensen upper bound).
        T
            Optional trace thickness for the HJ method.
        """
        from lineforge.analytical.pads import pad_capacitance as _pad_capacitance

        try:
            r = _pad_capacitance(W, L, h=h, er=er, method=method, T=T)  # type: ignore[arg-type]
        except (ValueError, TypeError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        return {
            "C_fF": r.C_fF,
            "C_pF": r.C_pF,
            "method": r.method,
            "W_mm": r.W_m * 1e3,
            "L_mm": r.L_m * 1e3,
            "h_mil": r.h_m / 25.4e-6,
            "eps_eff": r.eps_eff,
            "fringing_factor": r.fringing_factor,
        }

    @server.tool()
    def pad_relief_advisor(
        W: str,
        L: str | None = None,
        relief_options: list[dict[str, Any]] | None = None,
        band_max_ghz: float = 6.0,
        rl_target_dB: float = 30.0,
        Z0_line: float = 50.0,
        method: str = "ya",
    ) -> dict[str, Any]:
        """Rank pad-relief stackup options against an RL target at band edge.

        Each entry in ``relief_options`` is a dict with ``name`` and ``stack``,
        where stack is a list of ``{h, er}`` dicts representing layers between
        pad and reference plane.
        """
        from lineforge.analytical.pads import ReliefOption
        from lineforge.analytical.pads import (
            pad_relief_advisor as _pad_relief_advisor,
        )
        from lineforge.geometry.dielectric import DielectricLayer

        if not relief_options:
            return {"error": "relief_options must be a non-empty list of {name, stack}"}
        try:
            options = [
                ReliefOption(
                    name=opt["name"],
                    stack=[DielectricLayer(**layer) for layer in opt["stack"]],
                )
                for opt in relief_options
            ]
            advice = _pad_relief_advisor(
                W,
                L,
                options=options,
                band_max_ghz=band_max_ghz,
                rl_target_dB=rl_target_dB,
                Z0_line=Z0_line,
                method=method,  # type: ignore[arg-type]
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

        return {
            "recommendation": advice.recommendation,
            "band_max_ghz": advice.band_max_ghz,
            "rl_target_dB": advice.rl_target_dB,
            "rows": [
                {
                    "name": r.name,
                    "C_fF": r.C.C_fF,
                    "Z_at_band_max_ohm": r.Z_at_band_max,
                    "RL_at_band_max_dB": r.RL_at_band_max,
                    "meets_target": r.meets_target,
                    "headroom_dB": r.headroom_dB,
                }
                for r in advice.rows
            ],
        }

    @server.tool()
    def laminate_lookup(name: str, frequency_ghz: float | None = None) -> dict[str, Any]:
        """Look up a PCB laminate by name (fuzzy-matched) with optional
        frequency interpolation. Examples: "FR4 prepreg", "Isola 370HR",
        "Megtron 6", "RO4350B".
        """
        from lineforge.materials.laminates import laminate_lookup as _laminate_lookup

        try:
            r = _laminate_lookup(name, frequency_ghz=frequency_ghz)
        except KeyError as exc:
            return {"error": str(exc)}
        return {
            "name": r.name,
            "er": r.er,
            "tan_delta": r.tan_delta,
            "frequency_ghz": r.frequency_ghz,
            "matched_by": r.matched_by,
        }

    @server.tool()
    def rf_path_budget(
        freq_ghz: list[float],
        source_pad: dict[str, Any] | None = None,
        trace_Z0_ohm: float | None = None,
        end_pad: dict[str, Any] | None = None,
        Z0_port: float = 50.0,
    ) -> dict[str, Any]:
        """Compute end-to-end RF path return-loss budget.

        ``source_pad`` and ``end_pad`` are dicts with at least ``C_fF`` or
        the keys accepted by ``pad_capacitance`` (W, L, h, er, method).
        ``trace_Z0_ohm`` is the trace characteristic impedance.
        """
        from lineforge.analytical.pads import PadCapResult, pad_capacitance as _pad_capacitance
        from lineforge.path_budget import TraceSpec
        from lineforge.path_budget import rf_path_budget as _rf_path_budget

        def _resolve_pad(p: dict[str, Any] | None) -> PadCapResult | None:
            if p is None:
                return None
            if "C_fF" in p:
                # Synthetic PadCapResult-like

                return PadCapResult(
                    C_F=float(p["C_fF"]) * 1e-15,
                    method="pp",
                    W_m=0.0,
                    L_m=0.0,
                    h_m=0.0,
                    eps_eff=1.0,
                    fringing_factor=1.0,
                )
            return _pad_capacitance(**p)

        try:
            src = _resolve_pad(source_pad)
            end = _resolve_pad(end_pad)
            trace = TraceSpec(Z0=trace_Z0_ohm) if trace_Z0_ohm else None
            budget = _rf_path_budget(
                freq_ghz=freq_ghz,
                source_pad=src,
                trace=trace,
                end_pad=end,
                Z0_port=Z0_port,
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

        return {
            "Z0_port": budget.Z0_port,
            "worst_rl_dB": budget.worst_rl_dB,
            "rows": [
                {
                    "frequency_ghz": r.frequency_ghz,
                    "s11_source_dB": r.s11_source_dB,
                    "s11_trace_dB": r.s11_trace_dB,
                    "s11_end_dB": r.s11_end_dB,
                    "combined_rl_dB": r.combined_rl_dB,
                    "dominant": r.dominant,
                }
                for r in budget.rows
            ],
        }

    @server.tool()
    def classify_pad(
        component_type: str,
        has_modular_grant: bool = False,
        is_user_designed_rf: bool = False,
        operating_freq_ghz: float | None = None,
    ) -> dict[str, Any]:
        """Classify a pad into Category 1 (follow reference design),
        Category 2 (optimize freely), or Category 3 (standard practice).

        Use to decide whether to relieve GND under an RF pad vs follow
        the manufacturer's reference layout vs use plain solid GND.
        """
        from lineforge.design_rules import classify_pad as _classify_pad

        r = _classify_pad(
            component_type=component_type,
            has_modular_grant=has_modular_grant,
            is_user_designed_rf=is_user_designed_rf,
            operating_freq_ghz=operating_freq_ghz,
        )
        return {
            "category": r.category.name,
            "category_label": r.category.value,
            "guidance": r.guidance,
            "risks_if_deviating": r.risks_if_deviating,
            "references": r.references,
        }

    # ====================================================== Resources

    @server.resource(
        uri="atlc://materials",
        name="material database",
        description="atlc2-compatible material database (45 standard colors).",
        mime_type="application/json",
    )
    def materials_resource() -> str:
        return json.dumps([m.model_dump() for m in ATLC2_DEFAULTS], indent=2)

    @server.resource(
        uri="atlc://materials/{name}",
        name="material lookup",
        description="Single material record by case-insensitive name match.",
        mime_type="application/json",
    )
    def material_by_name(name: str) -> str:
        needle = name.lower()
        matches = [m.model_dump() for m in list_atlc2_default() if needle in m.name.lower()]
        if not matches:
            return json.dumps({"error": f"no materials matching {name!r}"})
        return json.dumps(matches, indent=2)

    @server.resource(
        uri="atlc://geometries/{id}",
        name="usermap",
        description="A stored usermap (cross-section bitmap with materials).",
        mime_type="application/json",
    )
    def usermap_resource(id: str) -> str:  # noqa: A002
        usermap = usermap_store.get(id)
        if usermap is None:
            return json.dumps({"error": f"unknown geometry id {id!r}"})
        return json.dumps(
            {
                "shape": list(usermap.shape),
                "pixel_width_m": usermap.pixel_width_m,
                "name": usermap.meta.name,
                "n_materials": len(usermap.materials),
            },
            indent=2,
        )

    @server.resource(
        uri="atlc://results/{id}",
        name="task result",
        description="Final result of a completed solve task.",
        mime_type="application/json",
    )
    def result_resource(id: str) -> str:  # noqa: A002
        t = task_registry.get(id)
        if t is None:
            return json.dumps({"error": f"unknown result id {id!r}"})
        return json.dumps(t.to_status() | {"result": t.result}, indent=2)

    @server.resource(
        uri="atlc://results/{id}/field/{kind}",
        name="field plot",
        description=(
            "Field plot PNG (V/E/D/T) from a completed solve. The body is the raw "
            "PNG bytes, base64-encoded in JSON."
        ),
        mime_type="application/json",
    )
    def field_plot_resource(id: str, kind: str) -> str:  # noqa: A002
        t = task_registry.get(id)
        if t is None:
            return json.dumps({"error": f"unknown result id {id!r}"})
        png = t.field_plots.get(kind.upper())
        if png is None:
            return json.dumps(
                {
                    "error": f"no {kind} plot for this result; "
                    f"render_fields not requested at solve time"
                }
            )
        return json.dumps({"png_base64": base64.b64encode(png).decode("ascii")})

    return server


def run_stdio() -> None:
    """Run the MCP server on stdio. Used by ``lineforge mcp-serve``."""
    server = build_server()
    server.run(transport="stdio")


__all__ = ["build_server", "run_stdio"]
