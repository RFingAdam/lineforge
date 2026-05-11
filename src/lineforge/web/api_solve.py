"""REST endpoints for solve / sweep / target_z0 — wraps atlc3 library calls.

DB1 hardening:
- ``_clean_geometry`` drops empty-string fields and (when the type is known)
  any keys that aren't part of the target geometry's Pydantic model. atlc3's
  models are ``extra="forbid"`` — strict for direct library users — but the
  GUI's free-form input form often submits unrelated empty fields. Filtering
  here keeps the library strict while giving the GUI a forgiving entry point.
- ``_sanitize_error`` strips Pydantic's ``https://errors.pydantic.dev/...``
  URL tail from ``ValidationError`` strings so the UI shows only the human
  message.
- Frequency goes through ``parse_frequency`` regardless of input type, so
  that a JS number ``1`` interpreted as 1 Hz can never silently corrupt a
  solve when the user meant ``"1GHz"`` (numeric inputs from the frontend
  arrive as floats unless explicitly stringified).
"""

from __future__ import annotations

from typing import Any

from lineforge.analytical import solve as analytical_solve
from lineforge.geometry import GEOMETRY_TYPES, from_dict
from lineforge.sweep import sweep as run_sweep
from lineforge.units import parse_frequency, parse_length
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from lineforge.web.state import update_state

router = APIRouter(prefix="/api/solve", tags=["solve"])


# --- helpers ---------------------------------------------------------------


def _clean_geometry(raw: dict[str, Any]) -> dict[str, Any]:
    """Strip empties and unknown fields before handing to atlc3.from_dict.

    Rules:
    - Drop any field whose value is an empty string (typed-but-blank input).
    - If a known ``type`` discriminator is present, drop any keys that aren't
      ``model_fields`` of that geometry's Pydantic class.
    - If ``type`` is missing or unknown, only the empty-string drop runs and
      atlc3 itself will raise the usual "unknown geometry type" error.
    """
    cleaned = {k: v for k, v in raw.items() if v != ""}
    type_name = cleaned.get("type")
    if isinstance(type_name, str) and type_name in GEOMETRY_TYPES:
        allowed = set(GEOMETRY_TYPES[type_name].model_fields.keys())
        cleaned = {k: v for k, v in cleaned.items() if k in allowed}
    return cleaned


def _sanitize_error(exc: BaseException) -> str:
    """Return a one-line UI-friendly error message.

    Pydantic's ValidationError tacks ``For further information visit
    https://errors.pydantic.dev/...`` onto every error (with or without a
    leading newline depending on the v2 minor); strip it unconditionally.
    Then collapse to a single line.
    """
    text = str(exc)
    # Cut at the "For further information" marker regardless of whitespace.
    for marker in ("\n  For further information", " For further information"):
        if marker in text:
            text = text.split(marker)[0]
            break
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " ".join(lines)


def _resolve_frequency(value: Any) -> float | None:
    """Always run frequency through parse_frequency so '1GHz' and 1e9 both work.

    parse_frequency accepts a bare number as Hz (so a numeric ``1e9`` becomes
    1 GHz). For strings like ``"2.4GHz"`` it parses the unit suffix.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return parse_frequency(str(value))


def _validate_sweep_parameter(geom: Any, parameter: str) -> None:
    """Raise HTTPException(400) if ``parameter`` is not a valid sweep field.

    Accepts ``"frequency"`` always, or any name in the geometry model's
    ``model_fields`` (excluding ``type`` itself). A typo like ``"frequnecy"``
    or ``"H"`` on a stripline_asymmetric (which has H1/H2, not H) gets a
    helpful error listing the valid choices.
    """
    valid = {"frequency"} | {name for name in geom.__class__.model_fields if name != "type"}
    if parameter not in valid:
        sorted_valid = sorted(valid)
        raise HTTPException(
            status_code=400,
            detail=(
                f"sweep parameter {parameter!r} is not valid for "
                f"{geom.__class__.__name__}; choose one of: {', '.join(sorted_valid)}"
            ),
        )


# --- request models --------------------------------------------------------


class CalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry: dict[str, Any] | None = None
    usermap_uri: str | None = None
    frequency: float | str | None = None
    solver: str = "analytical"  # "analytical" | "cgp" | "full"


class SweepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry: dict[str, Any]
    parameter: str
    values: list[float]
    solver: str = "analytical"
    frequency: float | str | None = None
    touchstone_out: str | None = None
    line_length: float | str = "1in"
    z_ref: float = 50.0


class TargetZ0Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: dict[str, Any]
    target_ohms: float
    vary: str = "W"
    bounds: tuple[str | float, str | float] | None = None
    solver: str = "analytical"
    frequency: float | str | None = None

    @field_validator("bounds")
    @classmethod
    def _check_bounds(
        cls, v: tuple[str | float, str | float] | None
    ) -> tuple[str | float, str | float] | None:
        """Each bound must parse as a Length and the lower bound must be < upper.

        Catches the common reversal mistake (``["30mil", "0.5mil"]``) and
        unparseable strings (``["wide", "narrow"]``) at the API boundary so
        the user gets a clear "bounds[0] must be less than bounds[1]" rather
        than a cryptic optimizer failure deep in scipy.
        """
        if v is None:
            return v
        lo_raw, hi_raw = v
        try:
            lo_m = parse_length(lo_raw) if isinstance(lo_raw, str) else float(lo_raw)
            hi_m = parse_length(hi_raw) if isinstance(hi_raw, str) else float(hi_raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"bounds: each entry must be a positive length; {exc}") from exc
        if lo_m <= 0 or hi_m <= 0:
            raise ValueError(f"bounds: both entries must be positive (got {lo_m}, {hi_m})")
        if lo_m >= hi_m:
            raise ValueError(
                f"bounds: lower bound must be less than upper "
                f"(got [{lo_raw!r}, {hi_raw!r}] = [{lo_m}, {hi_m}] m)"
            )
        return v


# --- endpoints -------------------------------------------------------------


@router.post("/calculate")
async def calculate(req: CalculateRequest) -> dict[str, Any]:
    """Solve the cross-section.

    Two input modes:
    - ``geometry={...}`` — closed-form analytical solve (default).
    - ``usermap_uri="atlc://geometries/<uid>"`` — bitmap solve against a
      previously-uploaded custom usermap. Forces solver="cgp".
    """
    if (req.geometry is None) == (req.usermap_uri is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of 'geometry' or 'usermap_uri' must be provided",
        )

    try:
        freq_hz = _resolve_frequency(req.frequency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    if req.usermap_uri is not None:
        # Bitmap solve path
        from lineforge.solvers.cgp import solve_cgp

        from lineforge.web.api_usermap import get_usermap_by_uri

        usermap = get_usermap_by_uri(req.usermap_uri)
        if usermap is None:
            raise HTTPException(status_code=404, detail=f"unknown usermap {req.usermap_uri!r}")
        try:
            result = solve_cgp(
                usermap,
                frequency_hz=freq_hz,
                method="sor",
                tol=1e-5,
                max_iter=5000,
                extend_grid=False,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=_sanitize_error(exc)) from exc

        out = result.model_dump()
        out["_kind"] = type(result).__name__
        out["usermap_uri"] = req.usermap_uri
        await update_state(geometry={"usermap_uri": req.usermap_uri}, last_result=out)
        return out

    # Built-in geometry path (analytical)
    cleaned = _clean_geometry(req.geometry or {})
    try:
        geom = from_dict(cleaned)
    except (KeyError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    try:
        result = analytical_solve(geom, frequency_hz=freq_hz)
    except (NotImplementedError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    out = result.model_dump()
    out["_kind"] = type(result).__name__
    await update_state(geometry=cleaned, last_result=out)
    return out


@router.post("/sweep")
async def sweep(req: SweepRequest) -> dict[str, Any]:
    """Parameter sweep. Optional Touchstone export when sweeping frequency."""
    cleaned = _clean_geometry(req.geometry)
    try:
        geom = from_dict(cleaned)
    except (KeyError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    try:
        freq_hz = _resolve_frequency(req.frequency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    _validate_sweep_parameter(geom, req.parameter)

    try:
        points = run_sweep(
            geom,
            parameter=req.parameter,
            values=req.values,
            solver=req.solver,
            frequency_hz=freq_hz,
        )
    except (KeyError, ValueError, ValidationError, RuntimeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    response: dict[str, Any] = {
        "points": [
            {
                "params": p.params,
                "result": p.result.model_dump() if hasattr(p.result, "model_dump") else None,
            }
            for p in points
        ],
    }

    if req.touchstone_out is not None and req.parameter == "frequency":
        import tempfile
        from pathlib import Path as _Path

        from lineforge.touchstone import to_touchstone

        try:
            # Write to a tmp file and read the bytes back so the GUI can
            # download via Blob without exposing the server's filesystem.
            tmp = _Path(tempfile.mkstemp(suffix=".s2p")[1])
            out_path = to_touchstone(
                points, tmp, line_length=req.line_length, z_ref=req.z_ref,
            )
            content = out_path.read_text()
            response["touchstone"] = {
                "filename": _Path(req.touchstone_out).name or "trace.s2p",
                "n_ports": 2,
                "z_ref": req.z_ref,
                "line_length": req.line_length,
                "content": content,
            }
            try:
                out_path.unlink()
            except OSError:
                pass
        except (ValueError, OSError) as exc:
            response["touchstone_error"] = _sanitize_error(exc)

    await update_state(
        geometry=cleaned,
        sweep_config={
            "parameter": req.parameter,
            "values": req.values,
            "solver": req.solver,
        },
    )
    return response


@router.post("/target-z0")
async def target_z0(req: TargetZ0Request) -> dict[str, Any]:
    """Solve for the field that lands the target characteristic impedance."""
    from lineforge.optimize import target_z0 as run_target

    cleaned_template = _clean_geometry(req.template)
    try:
        freq_hz = _resolve_frequency(req.frequency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    try:
        result = run_target(
            template=cleaned_template,
            vary=req.vary,
            target_ohms=req.target_ohms,
            bounds=req.bounds,
            solver=req.solver,
            frequency_hz=freq_hz,
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(exc)) from exc

    geom_dict = (
        result.geometry.model_dump()
        if hasattr(result.geometry, "model_dump")
        else dict(result.geometry)
    )
    response = {
        "geometry": geom_dict,
        "z0_achieved": result.metric.get("z0"),
        "cost": result.cost,
        "iterations": result.iterations,
        "success": result.success,
    }
    await update_state(geometry=geom_dict)
    return response
