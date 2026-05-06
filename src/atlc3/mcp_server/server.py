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

from mcp.server.fastmcp import FastMCP

from atlc3.analytical import solve as analytical_solve
from atlc3.geometry import GEOMETRY_TYPES, export_jsonschema, from_dict
from atlc3.geometry.builders import rasterize as rasterize_geom
from atlc3.geometry.usermap import Usermap, UsermapMetadata
from atlc3.materials import ATLC2_DEFAULTS, list_atlc2_default
from atlc3.mcp_server.tasks import TaskRegistry, png_to_bytes
from atlc3.results import DiffResult
from atlc3.solvers.cgp import solve_cgp as run_cgp
from atlc3.units import parse_frequency, parse_length
from atlc3.version import __version__

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


def build_server() -> FastMCP:
    """Construct the FastMCP server with all currently-implemented tools/resources."""
    server = FastMCP(
        name="atlc3",
        instructions=(
            "atlc3.0 — open-source transmission line calculator. "
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
                return_fields=True,
            )

            # Render requested field plots as base64 PNGs into the task object
            if render_fields:
                from atlc3.visualization.fields import render_field

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
            from atlc3.solvers.lrs import solve_lrs as _solve

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
            from atlc3.solvers.lrs import solve_full as _solve

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
    ) -> dict[str, Any]:
        """Sweep a single parameter and return results.

        For ``solver="analytical"`` this is synchronous (microseconds per point).
        For ``"cgp"`` or ``"full"`` it submits a background task and returns
        a ``taskId``; poll ``tasks_get`` for progress.
        """
        try:
            geom = from_dict(geometry)
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}

        freq_hz = parse_frequency(frequency) if isinstance(frequency, str) else frequency

        if solver == "analytical":
            from atlc3.sweep import sweep as _sweep_fn

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
            return {
                "points": [{"params": p.params, "result": p.result.model_dump()} for p in points],
            }

        # Numerical solver: async
        def _run(task_obj: Any) -> dict[str, Any]:
            from atlc3.sweep import sweep as _sweep_fn

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
    def run_atlc2_script(script_text: str, dry_run: bool = False) -> dict[str, Any]:
        """Execute an atlc2-style ``.txt`` script."""
        from atlc3.scripting import ScriptInterpreter

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
    """Run the MCP server on stdio. Used by ``atlc3 mcp-serve``."""
    server = build_server()
    server.run(transport="stdio")


__all__ = ["build_server", "run_stdio"]
