"""REST endpoints for geometry introspection (delegate to atlc3 library)."""

from __future__ import annotations

from typing import Any

from lineforge.geometry import GEOMETRY_TYPES, export_jsonschema
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/geometries", tags=["geometries"])


@router.get("")
def list_geometries() -> dict[str, Any]:
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


@router.get("/schema")
def schema() -> dict[str, Any]:
    """Discriminated-union JSON Schema across all geometries."""
    return export_jsonschema()


@router.get("/{name}")
def describe_geometry(name: str) -> dict[str, Any]:
    """JSON Schema for a single geometry type."""
    if name not in GEOMETRY_TYPES:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"unknown geometry type {name!r}",
                "valid_types": sorted(GEOMETRY_TYPES.keys()),
            },
        )
    return GEOMETRY_TYPES[name].model_json_schema()
