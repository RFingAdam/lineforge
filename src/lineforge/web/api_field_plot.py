"""Field-plot endpoint: render V/E/D/T as PNG via atlc3.visualization.fields.

The frontend's FieldPlotCanvas posts a geometry + field_kind, the backend
rasterizes it, runs the bitmap Laplace solve to populate v_field/er_field,
calls atlc3.visualization.fields.render_field, and returns a base64 data-URI
PNG that <img src=...> can render directly.

For non-trivial geometries this involves a full Laplace solve (~seconds).
The endpoint is synchronous in C1/D1; converting it to a background-task +
WebSocket-progress flow is a follow-up once the user reports the wait
becomes a problem in practice.
"""

from __future__ import annotations

import base64
import io
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, ValidationError

from lineforge.geometry import from_dict
from lineforge.geometry.builders import rasterize as rasterize_geom
from lineforge.geometry.usermap import Usermap
from lineforge.solvers.cgp import solve_cgp
from lineforge.visualization.fields import render_field
from lineforge.web.api_solve import _clean_geometry, _sanitize_error
from lineforge.web.api_usermap import get_usermap_by_uri

router = APIRouter(prefix="/api/solve", tags=["solve"])


FieldKindLiteral = Literal["U", "V", "E", "D", "T"]


class FieldPlotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry: dict[str, Any] | None = None
    usermap_uri: str | None = None
    field_kind: FieldKindLiteral = "E"
    intensity: Literal["linear", "sqrt"] = "linear"


def _png_data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@router.post("/field_plot")
def field_plot(req: FieldPlotRequest) -> dict[str, Any]:
    """Render V/E/D/T field as a PNG for the given geometry or usermap.

    Provide exactly one of ``geometry`` or ``usermap_uri``.
    """
    if (req.geometry is None) == (req.usermap_uri is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of 'geometry' or 'usermap_uri' must be provided",
        )

    if req.usermap_uri is not None:
        usermap: Usermap | None = get_usermap_by_uri(req.usermap_uri)
        if usermap is None:
            raise HTTPException(status_code=404, detail=f"unknown usermap {req.usermap_uri!r}")
    else:
        cleaned = _clean_geometry(req.geometry or {})
        try:
            geom = from_dict(cleaned)
        except (KeyError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc
        try:
            usermap = rasterize_geom(geom)
        except (NotImplementedError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    # Solve, requesting field workspace. extend_grid=False for shielded
    # geometries (coax and similar); for unshielded ones the field is
    # representative even if the C value differs from the extended-grid run.
    try:
        _, ws = solve_cgp(
            usermap,
            method="sor",
            tol=1e-5,
            max_iter=5000,
            extend_grid=False,
            return_fields=True,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"solver failed: {exc}") from exc

    tan_d = usermap.tan_delta_field() if req.field_kind == "T" else None
    try:
        img = render_field(
            kind=req.field_kind,
            v_field=ws.v_field,
            er_field=ws.er_field,
            tan_delta_field=tan_d,
            intensity=req.intensity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    h, w = ws.v_field.shape
    return {
        "field_kind": req.field_kind,
        "intensity": req.intensity,
        "shape": [int(h), int(w)],
        "v_min": float(np.nanmin(ws.v_field)),
        "v_max": float(np.nanmax(ws.v_field)),
        "png_data_uri": _png_data_uri(img),
    }


@router.post("/field_plot/async")
async def field_plot_async(req: FieldPlotRequest) -> dict[str, Any]:
    """Async variant of /field_plot with /ws/progress streaming.

    Returns immediately with ``{task_id}``. The actual solve runs in a
    background asyncio task that pushes ``progress`` / ``result`` /
    ``error`` events to ``/ws/progress/{task_id}``. The frontend
    subscribes there to render a live progress bar instead of a static
    spinner.

    Stage events sent by the worker:
      1. ``rasterizing``  (frac 0.05)
      2. ``solving``      (frac 0.15): Laplace iteration starts here
      3. ``rendering``    (frac 0.85): solver converged, painting PNG
      4. ``result``       (terminal)
    """
    import asyncio
    import uuid as _uuid

    from lineforge.web.ws_progress import send_progress

    task_id = str(_uuid.uuid4())

    async def _run() -> None:
        try:
            await send_progress(
                task_id,
                {"type": "progress", "task_id": task_id, "stage": "rasterizing", "frac": 0.05},
            )
            if (req.geometry is None) == (req.usermap_uri is None):
                await send_progress(
                    task_id,
                    {
                        "type": "error",
                        "task_id": task_id,
                        "error": "exactly one of 'geometry' or 'usermap_uri' must be provided",
                    },
                )
                return

            if req.usermap_uri is not None:
                usermap = get_usermap_by_uri(req.usermap_uri)
                if usermap is None:
                    await send_progress(
                        task_id,
                        {
                            "type": "error",
                            "task_id": task_id,
                            "error": f"unknown usermap {req.usermap_uri!r}",
                        },
                    )
                    return
            else:
                cleaned = _clean_geometry(req.geometry or {})
                geom = from_dict(cleaned)
                usermap = rasterize_geom(geom)

            await send_progress(
                task_id,
                {"type": "progress", "task_id": task_id, "stage": "solving", "frac": 0.15},
            )

            # Run the (blocking) solver in a thread so we don't lock the loop.
            def _solve() -> Any:
                return solve_cgp(
                    usermap,
                    method="sor",
                    tol=1e-5,
                    max_iter=5000,
                    extend_grid=False,
                    return_fields=True,
                )

            _, ws = await asyncio.to_thread(_solve)

            await send_progress(
                task_id,
                {"type": "progress", "task_id": task_id, "stage": "rendering", "frac": 0.85},
            )

            tan_d = usermap.tan_delta_field() if req.field_kind == "T" else None
            img = render_field(
                kind=req.field_kind,
                v_field=ws.v_field,
                er_field=ws.er_field,
                tan_delta_field=tan_d,
                intensity=req.intensity,
            )

            h_, w_ = ws.v_field.shape
            await send_progress(
                task_id,
                {
                    "type": "result",
                    "task_id": task_id,
                    "result": {
                        "field_kind": req.field_kind,
                        "intensity": req.intensity,
                        "shape": [int(h_), int(w_)],
                        "v_min": float(np.nanmin(ws.v_field)),
                        "v_max": float(np.nanmax(ws.v_field)),
                        "png_data_uri": _png_data_uri(img),
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001
            await send_progress(
                task_id,
                {"type": "error", "task_id": task_id, "error": _sanitize_error(exc)},
            )

    asyncio.create_task(_run())
    return {"task_id": task_id}
