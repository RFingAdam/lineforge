"""Materials catalog endpoint — surface the atlc3 laminate library to the GUI.

Reads ``atlc3.materials.packs.pcb_extended.json`` plus any frequency-aware
records, converts them to a flat JSON the frontend's MaterialPicker can
render in a combobox.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lineforge.materials as atlc3_materials
from lineforge.materials.morecolors import load_json_pack
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api/materials", tags=["materials"])


class SeriesReduceLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    h: float | str
    er: float
    tan_delta: float = 0.0
    name: str | None = None


class SeriesReduceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layers: list[SeriesReduceLayer]


def _packs_dir() -> Path:
    """Locate the bundled materials packs directory inside the installed atlc3."""
    return Path(atlc3_materials.__file__).parent / "packs"


@router.get("/laminates")
def list_laminates() -> dict[str, Any]:
    """Return PCB laminate materials as a flat list for the GUI dropdown.

    Each entry has ``{name, er, tan_delta, er_freq?, tan_freq?, vendor, notes}``.
    The frontend uses this to populate a combobox; selecting a row writes
    er + tan_delta back to the geometry form.
    """
    packs_dir = _packs_dir()
    pcb = packs_dir / "pcb_extended.json"
    if not pcb.exists():
        raise HTTPException(status_code=500, detail="pcb_extended.json not found")
    records = load_json_pack(pcb)
    laminates = [
        {
            "name": rec.name,
            "er": rec.er,
            "tan_delta": rec.tan_delta,
            "er_freq": rec.er_freq,
            "tan_freq": rec.tan_freq,
        }
        for rec in records
        if rec.use == "insul" and rec.er > 1.0
    ]
    laminates.sort(key=lambda r: r["name"])
    return {"laminates": laminates}


@router.post("/series_reduce")
def series_reduce(req: SeriesReduceRequest) -> dict[str, Any]:
    """Collapse a multi-layer dielectric stack via the C-series formula.

    Takes a list of layers (h, εr, tan_δ) and returns the equivalent single
    layer that produces the same parallel-plate capacitance:

        h_total = Σ hᵢ
        εr_eq   = h_total / Σ(hᵢ/εᵢ)
        tan_eq  = Σ(tanᵢ · hᵢ/εᵢ) / Σ(hᵢ/εᵢ)

    Used by the frontend's StackupEditor to feed reduced (H, εr, tan_δ) back
    into the form as the user adds layers.
    """
    from lineforge.geometry.dielectric import DielectricLayer
    from lineforge.geometry.dielectric import series_reduce as run_reduce

    if not req.layers:
        raise HTTPException(status_code=400, detail="layers must not be empty")

    try:
        dl = [
            DielectricLayer(h=layer.h, er=layer.er, tan_delta=layer.tan_delta, name=layer.name)
            for layer in req.layers
        ]
        h_total, er_eq, tan_eq = run_reduce(dl)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"h_total_m": h_total, "er_eq": er_eq, "tan_eq": tan_eq}
