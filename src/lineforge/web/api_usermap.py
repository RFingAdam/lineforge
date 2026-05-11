"""Custom usermap upload + retrieval (atlc2-style BMP loader).

Lets the GUI ship a custom BMP cross-section that's outside atlc3's nine
canonical geometry types. Users drag-drop a BMP, the backend stores it in
process, and the bitmap solver runs against it via
``POST /api/solve/calculate {usermap_uri: "..."}``.

Wire format:

  POST /api/usermap/upload
    body  {"bmp_base64": "...", "pixel_width": "0.1mm", "name": "..."}
    →     {"uri": "atlc://geometries/<uid>", "shape": [H, W], "preview_png_base64": "..."}

  GET  /api/usermap/<uid>
    →     {"uri": ..., "shape": ..., "pixel_width_m": ..., "name": ..., "preview_png_base64": ...}

The store is in-process; restarting the backend wipes it. For longer-term
persistence, add a sqlite store as a follow-up.
"""

from __future__ import annotations

import base64
import io
import uuid
from typing import Any

import numpy as np
from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.units import parse_length
from fastapi import APIRouter, HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api/usermap", tags=["usermap"])


class UsermapUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bmp_base64: str
    pixel_width: str | float
    name: str = "imported"


class _Store:
    """In-process keyed Usermap store."""

    def __init__(self) -> None:
        self._items: dict[str, Usermap] = {}

    def add(self, usermap: Usermap) -> str:
        uid = str(uuid.uuid4())
        self._items[uid] = usermap
        return uid

    def get(self, uid: str) -> Usermap | None:
        return self._items.get(uid)

    def all(self) -> dict[str, Usermap]:
        return dict(self._items)


store = _Store()


def _make_preview_png(usermap: Usermap, max_dim: int = 512) -> str:
    """Encode the usermap RGB array as a base64 data-URI PNG, downscaled if huge."""
    rgb = usermap.rgb
    h, w = rgb.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    img = Image.fromarray(rgb, mode="RGB")
    if scale < 1.0:
        new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        img = img.resize(new_size, Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@router.post("/upload")
def upload_usermap(req: UsermapUploadRequest) -> dict[str, Any]:
    """Decode a base64-encoded BMP/PNG and store it as a Usermap resource."""
    try:
        blob = base64.b64decode(req.bmp_base64)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"could not decode base64: {exc}") from exc

    try:
        img = Image.open(io.BytesIO(blob))
        if img.mode != "RGB":
            img = img.convert("RGB")
        rgb = np.asarray(img, dtype=np.uint8)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not decode image: {exc}") from exc

    try:
        pixel_width_m = (
            parse_length(req.pixel_width)
            if isinstance(req.pixel_width, str)
            else float(req.pixel_width)
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"pixel_width: {exc}") from exc

    if pixel_width_m <= 0:
        raise HTTPException(status_code=400, detail="pixel_width must be positive")

    meta = UsermapMetadata(pixel_width_m=pixel_width_m, name=req.name, source="upload")
    usermap = Usermap(rgb, meta)
    uid = store.add(usermap)

    return {
        "uri": f"atlc://geometries/{uid}",
        "uid": uid,
        "shape": [int(rgb.shape[0]), int(rgb.shape[1])],
        "pixel_width_m": pixel_width_m,
        "name": req.name,
        "preview_png_base64": _make_preview_png(usermap),
    }


@router.get("/{uid}")
def get_usermap(uid: str) -> dict[str, Any]:
    """Return metadata + preview for a previously uploaded usermap."""
    usermap = store.get(uid)
    if usermap is None:
        raise HTTPException(status_code=404, detail=f"unknown usermap {uid!r}")
    return {
        "uri": f"atlc://geometries/{uid}",
        "uid": uid,
        "shape": [int(usermap.rgb.shape[0]), int(usermap.rgb.shape[1])],
        "pixel_width_m": usermap.meta.pixel_width_m,
        "name": usermap.meta.name,
        "preview_png_base64": _make_preview_png(usermap),
    }


def get_usermap_by_uri(uri: str) -> Usermap | None:
    """Helper for the solve endpoint to look up by ``atlc://geometries/<uid>``."""
    if not uri.startswith("atlc://geometries/"):
        return None
    uid = uri.removeprefix("atlc://geometries/")
    return store.get(uid)
